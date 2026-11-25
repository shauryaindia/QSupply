"""QUBO formulation and independent evaluation for multimodal route assignments.

The model assigns exactly one generated route to each shipment. Shared link
capacities are encoded with bounded integer slack bits and squared equality
penalties. This module is backend-neutral; QAOA adapters consume its ordinary
QUBO through QSupply's existing solver contracts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite
from numbers import Real
from types import MappingProxyType
from typing import Any

from ..ising import qubo_to_ising
from ..qubo import QUBO
from ..qaoa import MAX_QAOA_VARIABLES
from ..solver import ExactQUBOSolver, ProblemRepresentation, SolverRequest
from .models import DisruptionScenario, TransportationNetwork
from .planning import ObjectiveReferences, ObjectiveWeights, ShipmentProfile
from .routing import CandidateRoute, validate_candidate_route


MAX_ROUTE_QUBO_VARIABLES = min(
    MAX_QAOA_VARIABLES, ExactQUBOSolver.DEFAULT_MAX_VARIABLES
)


class UnsupportedRouteQUBOError(ValueError):
    """Raised when an assignment formulation exceeds the explicit variable cap."""
    variable_count: int | None = None


@dataclass(frozen=True)
class RoutePlanFeasibility:
    """Independent domain check for decoded route IDs and shared link loads."""

    feasible: bool
    violations: tuple[str, ...]
    selected_routes: Mapping[str, str]
    capacity_usage: Mapping[str, int]
    capacity_utilization: Mapping[str, float]


@dataclass(frozen=True)
class RouteBusinessMetrics:
    """Unweighted route totals plus the fixed-reference QBO objective."""

    freight_cost: Real
    delay_penalty: Real
    total_cost: Real
    delivery_time: Real
    carbon_kg: Real
    resilience_exposure: Real
    weighted_objective: Real


@dataclass(frozen=True)
class RouteQUBOEvaluation:
    """Independent energy decomposition for one complete binary assignment."""

    feasibility: RoutePlanFeasibility
    business_metrics: RouteBusinessMetrics | None
    objective_contribution: Real
    penalty_contribution: Real
    qubo_offset: Real
    qubo_energy: Real
    full_penalized_energy: Real


@dataclass(frozen=True)
class CapacityEncoding:
    """A binding shared-link inequality represented by an equality and slack."""

    link_id: str
    capacity: int
    route_load_coefficients: Mapping[str, int]
    slack_variables: tuple[tuple[str, int], ...]


def _fraction(value: Real) -> Fraction:
    """Use exact integers/rationals and the exact stored value of Python floats."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("objective and route metrics must be real numbers")
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("objective and route metrics must be finite")
        return Fraction.from_float(value)
    return Fraction(value)


def _bounded_slack_weights(capacity: int) -> tuple[int, ...]:
    """Return positive bit weights whose subset sums cover exactly 0..capacity.

    The final weight may be smaller than a power of two. The weights sum to
    capacity, so no bit pattern can encode slack above the link capacity.
    """
    if capacity <= 0:
        return ()
    weights: list[int] = []
    remaining = capacity
    next_weight = 1
    while remaining:
        weight = min(next_weight, remaining)
        weights.append(weight)
        remaining -= weight
        next_weight *= 2
    return tuple(weights)


def _route_components(profile: ShipmentProfile, route: CandidateRoute) -> tuple[Fraction, ...]:
    transit = _fraction(route.transit_time)
    delay = (
        Fraction(0)
        if profile.request.deadline is None
        else max(Fraction(0), transit - _fraction(profile.request.deadline))
    )
    penalty = delay * _fraction(profile.delay_penalty_per_day)
    return (
        _fraction(route.freight_cost) + penalty,
        transit,
        _fraction(route.carbon_kg),
        _fraction(route.resilience_exposure),
    )


def _route_score(
    profile: ShipmentProfile,
    route: CandidateRoute,
    weights: ObjectiveWeights,
    references: ObjectiveReferences,
) -> Fraction:
    values = _route_components(profile, route)
    refs = tuple(
        _fraction(value)
        for value in (
            references.cost,
            references.delivery_time,
            references.carbon,
            references.resilience,
        )
    )
    percentages = (weights.cost, weights.delivery_time, weights.carbon, weights.resilience)
    return sum(
        (Fraction(weight, 100) * component * profile.priority / reference
         for weight, component, reference in zip(percentages, values, refs, strict=True)),
        Fraction(0),
    )


def _effective_capacities(
    network: TransportationNetwork, scenario: DisruptionScenario | None
) -> dict[str, int | None]:
    result = {link.id: link.capacity for link in network.links}
    if scenario is not None:
        result.update(scenario.capacity_overrides)
    return result


@dataclass(frozen=True)
class RouteAssignmentQUBO:
    """QUBO and domain data for one finite candidate-route assignment problem.

    ``variable_order`` is deterministic: shipment-route bits in supplied
    shipment/candidate order, followed by capacity slack bits in network-link
    order. Route suggestions remain distinct from the jointly feasible plan.
    """

    network: TransportationNetwork
    profiles: tuple[ShipmentProfile, ...]
    candidates: Mapping[str, tuple[CandidateRoute, ...]]
    weights: ObjectiveWeights
    normalization_references: ObjectiveReferences
    scenario: DisruptionScenario | None
    qubo: QUBO
    offset: Real
    penalty: Real
    route_variables: Mapping[tuple[str, str], str]
    slack_variables: Mapping[str, tuple[tuple[str, int], ...]]
    capacity_encodings: tuple[CapacityEncoding, ...]
    objective_coefficients: Mapping[str, Real]
    variable_kinds: Mapping[str, str]
    effective_capacities: Mapping[str, int | None]

    @property
    def variable_order(self) -> tuple[str, ...]:
        return self.qubo.variables

    @property
    def decision_variable_count(self) -> int:
        return len(self.route_variables)

    @property
    def slack_variable_count(self) -> int:
        return sum(len(bits) for bits in self.slack_variables.values())

    @property
    def variable_count(self) -> int:
        return len(self.variable_order)

    def _validate_binary_assignment(self, assignment: Mapping[str, int]) -> None:
        # The public QUBO validator is the canonical completeness/type check.
        self.qubo.energy(assignment)

    def check_plan(self, selected_routes: Mapping[str, str]) -> RoutePlanFeasibility:
        """Check route selection, link restrictions, deadlines and joint capacity.

        This deliberately does not inspect QUBO energies or penalty values.
        """
        if not isinstance(selected_routes, Mapping):
            raise TypeError("selected_routes must map shipment IDs to route IDs")
        expected = {profile.request.id for profile in self.profiles}
        supplied = set(selected_routes)
        violations: list[str] = []
        if expected - supplied:
            violations.append(
                f"missing shipments: {sorted(expected - supplied, key=repr)!r}"
            )
        if supplied - expected:
            violations.append(
                f"unknown shipments: {sorted(supplied - expected, key=repr)!r}"
            )

        route_by_shipment = {
            profile.request.id: {route.id: route for route in self.candidates[profile.request.id]}
            for profile in self.profiles
        }
        selected: dict[str, CandidateRoute] = {}
        for profile in self.profiles:
            shipment_id = profile.request.id
            if shipment_id not in selected_routes:
                continue
            route_id = selected_routes[shipment_id]
            route = route_by_shipment[shipment_id].get(route_id) if isinstance(route_id, str) else None
            if route is None:
                violations.append(f"shipment {shipment_id!r} selected an unknown route")
                continue
            if route.shipment_id != shipment_id:
                violations.append(f"route {route_id!r} is incompatible with shipment {shipment_id!r}")
                continue
            try:
                validate_candidate_route(self.network, profile.request, route, self.scenario)
            except (KeyError, ValueError) as error:
                violations.append(f"route {route_id!r} is invalid: {error}")
                continue
            if (
                profile.maximum_transit_time is not None
                and route.transit_time > profile.maximum_transit_time
            ):
                violations.append(f"route {route_id!r} exceeds the modeled maximum transit time")
                continue
            selected[shipment_id] = route

        usage: dict[str, int] = {}
        for profile in self.profiles:
            route = selected.get(profile.request.id)
            if route is None:
                continue
            traversals = Counter(leg.link_id for leg in route.legs)
            for link_id, count in traversals.items():
                usage[link_id] = usage.get(link_id, 0) + profile.request.quantity * count

        utilization: dict[str, float] = {}
        for link_id, amount in usage.items():
            capacity = self.effective_capacities[link_id]
            if capacity is None:
                continue
            if amount > capacity:
                violations.append(
                    f"shared capacity exceeded on link {link_id!r}: {amount} > {capacity}"
                )
            utilization[link_id] = 0.0 if capacity == 0 else amount / capacity

        return RoutePlanFeasibility(
            feasible=not violations and set(selected) == expected,
            violations=tuple(violations),
            selected_routes=MappingProxyType(
                {key: route.id for key, route in selected.items()}
            ),
            capacity_usage=MappingProxyType(usage),
            capacity_utilization=MappingProxyType(utilization),
        )

    def validate_assignment(self, assignment: Mapping[str, int]) -> RoutePlanFeasibility:
        """Independently validate one complete QUBO bit assignment as a plan."""
        self._validate_binary_assignment(assignment)
        selected: dict[str, str] = {}
        violations: list[str] = []
        for profile in self.profiles:
            options = [
                (route.id, assignment[self.route_variables[(profile.request.id, route.id)]])
                for route in self.candidates[profile.request.id]
            ]
            chosen = [route_id for route_id, bit in options if bit == 1]
            if len(chosen) != 1:
                violations.append(
                    f"shipment {profile.request.id!r} must select exactly one route; selected {len(chosen)}"
                )
            else:
                selected[profile.request.id] = chosen[0]
        if violations:
            base = self.check_plan(selected) if selected else RoutePlanFeasibility(
                False, (), MappingProxyType({}), MappingProxyType({}), MappingProxyType({})
            )
            return RoutePlanFeasibility(
                False,
                tuple(violations) + base.violations,
                base.selected_routes,
                base.capacity_usage,
                base.capacity_utilization,
            )
        return self.check_plan(selected)

    def decode(self, assignment: Mapping[str, int]) -> Mapping[str, str]:
        """Decode a complete, feasible bit assignment to shipment/route IDs."""
        report = self.validate_assignment(assignment)
        if not report.feasible:
            raise ValueError("cannot decode infeasible route assignment: " + "; ".join(report.violations))
        return report.selected_routes

    def decode_routes(self, assignment: Mapping[str, int]) -> Mapping[str, CandidateRoute]:
        selected = self.decode(assignment)
        by_id = {
            profile.request.id: {route.id: route for route in self.candidates[profile.request.id]}
            for profile in self.profiles
        }
        return MappingProxyType({key: by_id[key][route_id] for key, route_id in selected.items()})

    def encode_plan(self, selected_routes: Mapping[str, str]) -> Mapping[str, int]:
        """Encode a feasible route plan and exact capacity slack values.

        This is used to place the classical assignment result in the same QUBO
        variable register for energy reconciliation and backend comparisons.
        """
        report = self.check_plan(selected_routes)
        if not report.feasible:
            raise ValueError("cannot encode infeasible route plan: " + "; ".join(report.violations))
        assignment = {variable: 0 for variable in self.variable_order}
        for shipment_id, route_id in selected_routes.items():
            assignment[self.route_variables[(shipment_id, route_id)]] = 1
        for encoding in self.capacity_encodings:
            needed = encoding.capacity - report.capacity_usage.get(encoding.link_id, 0)
            for variable, weight in sorted(
                encoding.slack_variables, key=lambda item: item[1], reverse=True
            ):
                if weight <= needed:
                    assignment[variable] = 1
                    needed -= weight
            if needed:
                raise ArithmeticError(
                    f"capacity slack encoding cannot represent {encoding.link_id!r} remainder"
                )
        return MappingProxyType(assignment)

    def evaluate_business_objective(
        self, selected_routes: Mapping[str, str]
    ) -> RouteBusinessMetrics:
        """Recompute raw business metrics and QBO score from validated routes."""
        feasibility = self.check_plan(selected_routes)
        if not feasibility.feasible:
            raise ValueError("business objective requires a feasible plan: " + "; ".join(feasibility.violations))
        route_lookup = {
            profile.request.id: {route.id: route for route in self.candidates[profile.request.id]}
            for profile in self.profiles
        }
        freight = delay_penalty = delivery = carbon = resilience = Fraction(0)
        objective = Fraction(0)
        for profile in self.profiles:
            route = route_lookup[profile.request.id][selected_routes[profile.request.id]]
            delay = _route_components(profile, route)
            freight += _fraction(route.freight_cost)
            delay_penalty += delay[0] - _fraction(route.freight_cost)
            delivery += delay[1]
            carbon += delay[2]
            resilience += delay[3]
            objective += _route_score(
                profile, route, self.weights, self.normalization_references
            )
        return RouteBusinessMetrics(
            freight_cost=freight,
            delay_penalty=delay_penalty,
            total_cost=freight + delay_penalty,
            delivery_time=delivery,
            carbon_kg=carbon,
            resilience_exposure=resilience,
            weighted_objective=objective,
        )

    def evaluate_assignment(self, assignment: Mapping[str, int]) -> RouteQUBOEvaluation:
        """Reconcile business objective, penalties, offset and QUBO energy."""
        self._validate_binary_assignment(assignment)
        feasibility = self.validate_assignment(assignment)
        objective = sum(
            (coefficient * assignment[variable] for variable, coefficient in self.objective_coefficients.items()),
            Fraction(0),
        )
        penalty = Fraction(0)
        for profile in self.profiles:
            count = sum(
                assignment[self.route_variables[(profile.request.id, route.id)]]
                for route in self.candidates[profile.request.id]
            )
            penalty += self.penalty * (1 - count) ** 2
        for encoding in self.capacity_encodings:
            usage = sum(
                coefficient * assignment[variable]
                for variable, coefficient in encoding.route_load_coefficients.items()
            )
            slack = sum(weight * assignment[variable] for variable, weight in encoding.slack_variables)
            penalty += self.penalty * (usage + slack - encoding.capacity) ** 2
        qubo_energy = self.qubo.energy(assignment)
        full_energy = self.offset + qubo_energy
        if full_energy != objective + penalty:
            raise ArithmeticError("direct business/penalty decomposition disagrees with QUBO energy")
        metrics = (
            self.evaluate_business_objective(feasibility.selected_routes)
            if feasibility.feasible
            else None
        )
        if metrics is not None and metrics.weighted_objective != objective:
            raise ArithmeticError("decoded business objective disagrees with QUBO objective contribution")
        return RouteQUBOEvaluation(
            feasibility=feasibility,
            business_metrics=metrics,
            objective_contribution=objective,
            penalty_contribution=penalty,
            qubo_offset=self.offset,
            qubo_energy=qubo_energy,
            full_penalized_energy=full_energy,
        )

    def solver_request(self, representation: ProblemRepresentation) -> SolverRequest:
        """Create the existing backend-neutral request for exact or QAOA solvers."""
        ising = qubo_to_ising(self.qubo, offset=self.offset)
        return SolverRequest(
            qubo=self.qubo,
            constant_offset=self.offset,
            representation=representation,
            ising_model=ising,
            validator=self.validate_assignment,
            decoder=self.decode,
            business_objective=lambda selected: self.evaluate_business_objective(
                selected
            ).weighted_objective,
            configuration={
                "problem_kind": "multimodal-route-assignment",
                "variable_count": self.variable_count,
                "decision_variable_count": self.decision_variable_count,
                "slack_variable_count": self.slack_variable_count,
            },
        )


def formulate_route_assignment_qubo(
    network: TransportationNetwork,
    profiles: Sequence[ShipmentProfile],
    candidates: Mapping[str, Sequence[CandidateRoute]],
    weights: ObjectiveWeights,
    normalization_references: ObjectiveReferences,
    scenario: DisruptionScenario | None = None,
) -> RouteAssignmentQUBO:
    """Build an exact QBO-scored QUBO for the supplied finite candidate set.

    The penalty is one greater than an upper bound on every feasible weighted
    objective. Route scores are non-negative, and integer capacity residuals
    are either zero or at least one, so a feasible assignment (when one exists)
    has lower full penalized energy than every domain-infeasible assignment.
    Capacity inequalities use a bounded slack encoding; no pairwise-conflict
    approximation is used.
    """
    if not isinstance(network, TransportationNetwork):
        raise TypeError("network must be a TransportationNetwork")
    profiles = tuple(profiles)
    if not profiles or any(not isinstance(item, ShipmentProfile) for item in profiles):
        raise ValueError("profiles must be a non-empty sequence of ShipmentProfile objects")
    if len({item.request.id for item in profiles}) != len(profiles):
        raise ValueError("shipment IDs must be unique")
    if not isinstance(weights, ObjectiveWeights):
        raise TypeError("weights must be ObjectiveWeights")
    if not isinstance(normalization_references, ObjectiveReferences):
        raise TypeError("normalization_references must be ObjectiveReferences")
    refs = tuple(
        _fraction(value)
        for value in (
            normalization_references.cost,
            normalization_references.delivery_time,
            normalization_references.carbon,
            normalization_references.resilience,
        )
    )
    if any(value <= 0 for value in refs):
        raise ValueError("normalization references must be positive")
    if scenario is not None:
        if not isinstance(scenario, DisruptionScenario):
            raise TypeError("scenario must be a DisruptionScenario or None")
        scenario.validate_for(network)

    shipment_ids = [profile.request.id for profile in profiles]
    if not isinstance(candidates, Mapping) or set(candidates) != set(shipment_ids):
        raise ValueError("candidates must contain exactly one route sequence per shipment")
    normalized: dict[str, tuple[CandidateRoute, ...]] = {}
    for profile in profiles:
        route_list = tuple(candidates[profile.request.id])
        if not route_list or any(not isinstance(route, CandidateRoute) for route in route_list):
            raise ValueError(f"shipment {profile.request.id!r} needs non-empty CandidateRoute options")
        if len({route.id for route in route_list}) != len(route_list):
            raise ValueError(f"route IDs for shipment {profile.request.id!r} must be unique")
        for route in route_list:
            if route.shipment_id != profile.request.id:
                raise ValueError(f"route {route.id!r} is incompatible with shipment {profile.request.id!r}")
            validate_candidate_route(network, profile.request, route, scenario)
            if profile.maximum_transit_time is not None and route.transit_time > profile.maximum_transit_time:
                raise ValueError(f"route {route.id!r} exceeds the modeled maximum transit time")
        normalized[profile.request.id] = route_list

    route_variables: dict[tuple[str, str], str] = {}
    variable_kinds: dict[str, str] = {}
    variables: list[str] = []
    route_by_variable: dict[str, CandidateRoute] = {}
    for shipment_index, profile in enumerate(profiles):
        for route_index, route in enumerate(normalized[profile.request.id]):
            variable = f"route_s{shipment_index}_r{route_index}"
            route_variables[(profile.request.id, route.id)] = variable
            route_by_variable[variable] = route
            variable_kinds[variable] = "route_choice"
            variables.append(variable)

    objective_coefficients: dict[str, Fraction] = {
        variable: _route_score(
            next(profile for profile in profiles if profile.request.id == shipment_id),
            route_by_variable[variable],
            weights,
            normalization_references,
        )
        for (shipment_id, _), variable in route_variables.items()
    }
    objective_bound = sum(
        (
            max(
                objective_coefficients[route_variables[(profile.request.id, route.id)]]
                for route in normalized[profile.request.id]
            )
            for profile in profiles
        ),
        Fraction(0),
    )
    penalty = objective_bound + 1

    capacities = _effective_capacities(network, scenario)
    all_route_loads: dict[str, dict[str, int]] = {}
    for profile in profiles:
        for route in normalized[profile.request.id]:
            variable = route_variables[(profile.request.id, route.id)]
            for link_id, count in Counter(leg.link_id for leg in route.legs).items():
                load = profile.request.quantity * count
                route_loads = all_route_loads.setdefault(link_id, {})
                route_loads[variable] = route_loads.get(variable, 0) + load

    # Only links that can actually overload under one route per shipment need
    # a capacity encoding. Redundant constraints would consume qubits needlessly.
    binding_links: list[str] = []
    for link in network.links:
        capacity = capacities[link.id]
        if capacity is None:
            continue
        possible_load = 0
        route_loads = all_route_loads.get(link.id, {})
        for profile in profiles:
            possible_load += max(
                (
                    route_loads.get(route_variables[(profile.request.id, route.id)], 0)
                    for route in normalized[profile.request.id]
                ),
                default=0,
            )
        if possible_load > capacity:
            binding_links.append(link.id)

    slack_variables: dict[str, tuple[tuple[str, int], ...]] = {}
    capacity_encodings: list[CapacityEncoding] = []
    for link_index, link_id in enumerate(binding_links):
        capacity = capacities[link_id]
        assert capacity is not None
        bits = tuple(
            (f"slack_l{link_index}_b{bit_index}", weight)
            for bit_index, weight in enumerate(_bounded_slack_weights(capacity))
        )
        slack_variables[link_id] = bits
        for variable, _ in bits:
            variables.append(variable)
            variable_kinds[variable] = "capacity_slack"
        capacity_encodings.append(
            CapacityEncoding(
                link_id=link_id,
                capacity=capacity,
                route_load_coefficients=MappingProxyType(dict(all_route_loads[link_id])),
                slack_variables=bits,
            )
        )

    if len(variables) > MAX_ROUTE_QUBO_VARIABLES:
        error = UnsupportedRouteQUBOError(
            f"route assignment requires {len(variables)} binary variables "
            f"({len(route_variables)} route choices, "
            f"{sum(len(bits) for bits in slack_variables.values())} capacity slack); "
            f"the current exact/QAOA limit is {MAX_ROUTE_QUBO_VARIABLES}. "
            "Reduce the explicitly selected candidate set or shipment scope and formulate again."
        )

        error.variable_count = len(variables)
        raise error

    coefficients: dict[tuple[str, str], Fraction] = {}
    offset = Fraction(0)

    def add_coefficient(pair: tuple[str, str], value: Fraction) -> None:
        coefficients[pair] = coefficients.get(pair, Fraction(0)) + value

    # The objective is linear in route-choice bits.
    for variable, value in objective_coefficients.items():
        add_coefficient((variable, variable), value)

    # A*(sum(x)-1)^2, using x_i^2 = x_i for binary variables.
    for profile in profiles:
        terms = [route_variables[(profile.request.id, route.id)] for route in normalized[profile.request.id]]
        offset += penalty
        for variable in terms:
            add_coefficient((variable, variable), -penalty)
        for index, left in enumerate(terms):
            for right in terms[index + 1 :]:
                add_coefficient((left, right), 2 * penalty)

    # A*(sum(load*x) + sum(slack_weight*b) - capacity)^2.
    variable_index = {variable: index for index, variable in enumerate(variables)}
    for encoding in capacity_encodings:
        terms = list(encoding.route_load_coefficients.items()) + list(encoding.slack_variables)
        terms.sort(key=lambda item: variable_index[item[0]])
        target = encoding.capacity
        offset += penalty * target**2
        for variable, weight in terms:
            add_coefficient(
                (variable, variable), penalty * (weight**2 - 2 * target * weight)
            )
        for index, (left, left_weight) in enumerate(terms):
            for right, right_weight in terms[index + 1 :]:
                add_coefficient(
                    (left, right), 2 * penalty * left_weight * right_weight
                )

    qubo = QUBO(tuple(variables), coefficients)
    # Keep unused zero-capacity links explicit only when they can overload;
    # their equality has no slack and is still enforced by a squared residual.
    return RouteAssignmentQUBO(
        network=network,
        profiles=profiles,
        candidates=MappingProxyType(normalized),
        weights=weights,
        normalization_references=normalization_references,
        scenario=scenario,
        qubo=qubo,
        offset=offset,
        penalty=penalty,
        route_variables=MappingProxyType(route_variables),
        slack_variables=MappingProxyType(slack_variables),
        capacity_encodings=tuple(capacity_encodings),
        objective_coefficients=MappingProxyType(objective_coefficients),
        variable_kinds=MappingProxyType(variable_kinds),
        effective_capacities=MappingProxyType(capacities),
    )
