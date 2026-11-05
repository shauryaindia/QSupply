"""Candidate-route assignment and deterministic shipment movement for demos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from numbers import Real
from types import MappingProxyType
from typing import Mapping

from .models import DisruptionScenario, ShipmentRequest, TransportationNetwork
from .routing import CandidateRoute, generate_candidate_routes, validate_candidate_route


@dataclass(frozen=True)
class ShipmentProfile:
    """Demo-level business attributes layered over a unit-validated shipment."""

    request: ShipmentRequest
    cargo_category: str
    priority: int
    delay_penalty_per_day: Real
    maximum_transit_time: Real | None
    departure_time: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.request, ShipmentRequest):
            raise TypeError("request must be a ShipmentRequest")
        if not isinstance(self.cargo_category, str) or not self.cargo_category.strip():
            raise ValueError("cargo_category must be non-empty")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be an integer from 1 to 5")
        if not 1 <= self.priority <= 5:
            raise ValueError("priority must be from 1 to 5")
        if isinstance(self.delay_penalty_per_day, bool) or not isinstance(self.delay_penalty_per_day, Real):
            raise TypeError("delay_penalty_per_day must be a real number")
        if not isfinite(self.delay_penalty_per_day) or self.delay_penalty_per_day < 0:
            raise ValueError("delay_penalty_per_day must be finite and non-negative")
        if self.maximum_transit_time is not None:
            if isinstance(self.maximum_transit_time, bool) or not isinstance(self.maximum_transit_time, Real):
                raise TypeError("maximum_transit_time must be a real number or None")
            if not isfinite(self.maximum_transit_time) or self.maximum_transit_time < 0:
                raise ValueError("maximum_transit_time must be finite and non-negative")
        if not isinstance(self.departure_time, datetime) or self.departure_time.tzinfo is None:
            raise ValueError("departure_time must be a timezone-aware datetime")


@dataclass(frozen=True)
class ObjectiveWeights:
    """QSupply Balanced Optimization weights, expressed as percentages."""

    cost: int = 40
    delivery_time: int = 25
    carbon: int = 20
    resilience: int = 15

    def __post_init__(self) -> None:
        values = (self.cost, self.delivery_time, self.carbon, self.resilience)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise TypeError("objective weights must be integers")
        if any(value < 0 or value > 100 for value in values):
            raise ValueError("objective weights must be between 0 and 100")
        if sum(values) != 100:
            raise ValueError("objective weights must total 100")


@dataclass(frozen=True)
class ObjectiveReferences:
    """Fixed normalization denominators computed once from the baseline routes."""

    cost: float
    delivery_time: float
    carbon: float
    resilience: float


@dataclass(frozen=True)
class PlanMetrics:
    freight_cost: float
    delay_penalty: float
    total_cost: float
    delivery_time: float
    carbon_kg: float
    resilience_exposure: float
    weighted_objective: float


@dataclass(frozen=True)
class RouteAssignment:
    routes: Mapping[str, CandidateRoute]
    metrics: PlanMetrics
    capacity_usage: Mapping[str, int]
    capacity_utilization: Mapping[str, float]
    method: str = "exact-enumeration-over-generated-candidates"


@dataclass(frozen=True)
class RecoveryComparison:
    baseline: RouteAssignment
    recovery: RouteAssignment | None
    baseline_candidates: Mapping[str, tuple[CandidateRoute, ...]]
    recovery_candidates: Mapping[str, tuple[CandidateRoute, ...]]
    normalization_references: ObjectiveReferences
    recovery_feasible: bool
    failure_reason: str | None
    scenario_id: str | None


class RecoverySearchLimitError(RuntimeError):
    """Raised when bounded exact assignment enumeration exceeds its guardrail."""


def _route_components(
    profile: ShipmentProfile, route: CandidateRoute
) -> tuple[float, float, float, float]:
    delay = (
        0.0
        if profile.request.deadline is None
        else max(0.0, float(route.transit_time) - float(profile.request.deadline))
    )
    late_penalty = delay * float(profile.delay_penalty_per_day)
    return (
        float(route.freight_cost) + late_penalty,
        float(route.transit_time),
        float(route.carbon_kg),
        float(route.resilience_exposure),
    )


def _references(
    profiles: tuple[ShipmentProfile, ...],
    candidates: Mapping[str, tuple[CandidateRoute, ...]],
) -> ObjectiveReferences:
    sums = [0.0, 0.0, 0.0, 0.0]
    for profile in profiles:
        options = candidates[profile.request.id]
        for index in range(4):
            sums[index] += max(
                _route_components(profile, route)[index] * profile.priority
                for route in options
            )
    # A one-unit floor handles an all-zero objective category without division by zero.
    return ObjectiveReferences(*(max(1.0, value) for value in sums))


def _plan_score(
    profiles: tuple[ShipmentProfile, ...],
    selection: Mapping[str, CandidateRoute],
    weights: ObjectiveWeights,
    references: ObjectiveReferences,
) -> float:
    weight_values = (weights.cost, weights.delivery_time, weights.carbon, weights.resilience)
    reference_values = (
        references.cost,
        references.delivery_time,
        references.carbon,
        references.resilience,
    )
    terms = [0.0, 0.0, 0.0, 0.0]
    for profile in profiles:
        components = _route_components(profile, selection[profile.request.id])
        for index, component in enumerate(components):
            terms[index] += component * profile.priority
    return sum(
        weight_values[index] / 100 * terms[index] / reference_values[index]
        for index in range(4)
    )


def _metrics(
    profiles: tuple[ShipmentProfile, ...],
    selection: Mapping[str, CandidateRoute],
    weights: ObjectiveWeights,
    references: ObjectiveReferences,
) -> PlanMetrics:
    freight = 0.0
    delay_penalty = 0.0
    time = 0.0
    carbon = 0.0
    exposure = 0.0
    for profile in profiles:
        route = selection[profile.request.id]
        late_days = (
            0.0
            if profile.request.deadline is None
            else max(0.0, float(route.transit_time) - float(profile.request.deadline))
        )
        freight += float(route.freight_cost)
        delay_penalty += late_days * float(profile.delay_penalty_per_day)
        time += float(route.transit_time)
        carbon += float(route.carbon_kg)
        exposure += float(route.resilience_exposure)
    return PlanMetrics(
        freight_cost=freight,
        delay_penalty=delay_penalty,
        total_cost=freight + delay_penalty,
        delivery_time=time,
        carbon_kg=carbon,
        resilience_exposure=exposure,
        weighted_objective=_plan_score(profiles, selection, weights, references),
    )


def _capacity_map(
    network: TransportationNetwork, scenario: DisruptionScenario | None
) -> dict[str, int | None]:
    capacities = {link.id: link.capacity for link in network.links}
    if scenario is not None:
        capacities.update(scenario.capacity_overrides)
    return capacities


def assign_routes(
    network: TransportationNetwork,
    profiles: tuple[ShipmentProfile, ...],
    candidates: Mapping[str, tuple[CandidateRoute, ...]],
    weights: ObjectiveWeights,
    references: ObjectiveReferences,
    scenario: DisruptionScenario | None = None,
    *,
    max_states: int = 250_000,
) -> RouteAssignment | None:
    """Find the minimum weighted assignment over a bounded route candidate set.

    Capacity constraints are enforced jointly across shipments. Every returned
    route is independently revalidated against the original network and overlay.
    """
    if not profiles:
        raise ValueError("at least one shipment is required")
    if len(profiles) > 8:
        raise ValueError("exact candidate assignment supports at most 8 shipments")
    shipment_ids = [profile.request.id for profile in profiles]
    if len(set(shipment_ids)) != len(shipment_ids):
        raise ValueError("shipment IDs must be unique")
    if set(candidates) != set(shipment_ids):
        raise ValueError("candidate routes must be provided for each shipment exactly once")
    if any(not candidates[shipment_id] for shipment_id in shipment_ids):
        return None
    for profile in profiles:
        for route in candidates[profile.request.id]:
            validate_candidate_route(network, profile.request, route, scenario)
            if (
                profile.maximum_transit_time is not None
                and route.transit_time > profile.maximum_transit_time
            ):
                raise ValueError("candidate route exceeds the shipment maximum transit time")

    ordered_profiles = tuple(
        sorted(profiles, key=lambda profile: (len(candidates[profile.request.id]), profile.request.id))
    )
    capacities = _capacity_map(network, scenario)
    usage: dict[str, int] = {}
    selection: dict[str, CandidateRoute] = {}
    best_selection: dict[str, CandidateRoute] | None = None
    best_score = float("inf")
    states = 0
    link_map = network.links_by_id

    def search(index: int, partial_score: float) -> None:
        nonlocal states, best_selection, best_score
        states += 1
        if states > max_states:
            raise RecoverySearchLimitError(
                f"route assignment exceeded its {max_states} state limit"
            )
        if partial_score >= best_score:
            return
        if index == len(ordered_profiles):
            best_score = partial_score
            best_selection = dict(selection)
            return
        profile = ordered_profiles[index]
        shipment_id = profile.request.id
        route_options = sorted(
            candidates[shipment_id],
            key=lambda route: (
                _plan_score((profile,), {shipment_id: route}, weights, references),
                route.id,
            ),
        )
        for route in route_options:
            route_link_ids = [leg.link_id for leg in route.legs]
            feasible = True
            for link_id in route_link_ids:
                capacity = capacities[link_id]
                if capacity is not None and usage.get(link_id, 0) + profile.request.quantity > capacity:
                    feasible = False
                    break
            if not feasible:
                continue
            for link_id in route_link_ids:
                usage[link_id] = usage.get(link_id, 0) + profile.request.quantity
            selection[shipment_id] = route
            search(
                index + 1,
                partial_score
                + _plan_score((profile,), {shipment_id: route}, weights, references),
            )
            del selection[shipment_id]
            for link_id in route_link_ids:
                usage[link_id] -= profile.request.quantity
                if usage[link_id] == 0:
                    del usage[link_id]

    search(0, 0.0)
    if best_selection is None:
        return None

    # Validate the complete assignment independently, including shared link loads.
    used: dict[str, int] = {}
    for profile in profiles:
        route = best_selection[profile.request.id]
        validate_candidate_route(network, profile.request, route, scenario)
        for leg in route.legs:
            used[leg.link_id] = used.get(leg.link_id, 0) + profile.request.quantity
    utilization: dict[str, float] = {}
    for link_id, amount in used.items():
        capacity = capacities[link_id]
        if capacity is not None:
            if amount > capacity:
                raise ValueError(f"independent capacity validation failed for link {link_id!r}")
            utilization[link_id] = amount / capacity if capacity else 0.0
    return RouteAssignment(
        routes=MappingProxyType(best_selection),
        metrics=_metrics(profiles, best_selection, weights, references),
        capacity_usage=MappingProxyType(used),
        capacity_utilization=MappingProxyType(utilization),
    )


def compare_recovery(
    network: TransportationNetwork,
    profiles: tuple[ShipmentProfile, ...],
    scenario: DisruptionScenario | None,
    weights: ObjectiveWeights,
    *,
    max_routes: int = 8,
) -> RecoveryComparison:
    """Compare baseline and disrupted plans using one fixed normalization."""
    if scenario is not None:
        scenario.validate_for(network)
    baseline_options = {
        profile.request.id: tuple(
            route
            for route in generate_candidate_routes(
                network, profile.request, max_routes=max_routes
            )
            if profile.maximum_transit_time is None
            or route.transit_time <= profile.maximum_transit_time
        )
        for profile in profiles
    }
    if any(not routes for routes in baseline_options.values()):
        missing = [key for key, routes in baseline_options.items() if not routes]
        raise ValueError(f"baseline has no feasible candidate route for shipments {missing!r}")
    references = _references(profiles, baseline_options)
    baseline = assign_routes(
        network, profiles, baseline_options, weights, references
    )
    if baseline is None:
        raise ValueError("baseline shipment assignment is infeasible")
    if scenario is None:
        return RecoveryComparison(
            baseline=baseline,
            recovery=baseline,
            baseline_candidates=MappingProxyType(baseline_options),
            recovery_candidates=MappingProxyType(baseline_options),
            normalization_references=references,
            recovery_feasible=True,
            failure_reason=None,
            scenario_id=None,
        )

    recovery_options = {
        profile.request.id: tuple(
            route
            for route in generate_candidate_routes(
                network, profile.request, scenario, max_routes=max_routes
            )
            if profile.maximum_transit_time is None
            or route.transit_time <= profile.maximum_transit_time
        )
        for profile in profiles
    }
    recovery = assign_routes(
        network, profiles, recovery_options, weights, references, scenario
    )
    reason = None if recovery is not None else "No capacity-feasible reallocation exists under this disruption."
    return RecoveryComparison(
        baseline=baseline,
        recovery=recovery,
        baseline_candidates=MappingProxyType(baseline_options),
        recovery_candidates=MappingProxyType(recovery_options),
        normalization_references=references,
        recovery_feasible=recovery is not None,
        failure_reason=reason,
        scenario_id=scenario.id,
    )


def simulate_movement(
    route: CandidateRoute,
    departure_time: datetime,
    elapsed_time: float,
    time_unit: str = "day",
) -> dict[str, object]:
    """Return a deterministic interpolated position at elapsed network time units."""
    if not isfinite(elapsed_time) or elapsed_time < 0:
        raise ValueError("elapsed_time must be finite and non-negative")
    total = route.transit_time
    seconds_per_unit = {"day": 86_400, "hour": 3_600, "minute": 60}.get(time_unit)
    if seconds_per_unit is None:
        raise ValueError("simulation time unit must be day, hour, or minute")
    arrival = departure_time + timedelta(seconds=total * seconds_per_unit)
    if elapsed_time >= total:
        return {
            "status": "delivered",
            "position": list(route.geometry[-1]),
            "current_leg_id": None,
            "current_mode": None,
            "elapsed_time": elapsed_time,
            "remaining_time": 0.0,
            "departure_time": departure_time.isoformat(),
            "estimated_arrival": arrival.isoformat(),
        }
    elapsed = elapsed_time
    current_leg = route.legs[0]
    fraction = 0.0
    for leg in route.legs:
        if elapsed <= leg.transit_time:
            current_leg = leg
            fraction = 0.0 if leg.transit_time == 0 else elapsed / leg.transit_time
            break
        elapsed -= leg.transit_time
    position = _interpolate(current_leg.geometry, fraction)
    return {
        "status": "in_transit" if elapsed_time > 0 else "scheduled",
        "position": list(position),
        "current_leg_id": current_leg.link_id,
        "current_mode": current_leg.mode.value,
        "elapsed_time": elapsed_time,
        "remaining_time": max(0.0, total - elapsed_time),
        "departure_time": departure_time.isoformat(),
        "estimated_arrival": arrival.isoformat(),
    }


def _interpolate(points: tuple[tuple[float, float], ...], fraction: float) -> tuple[float, float]:
    if len(points) == 1:
        return points[0]
    lengths = [
        _haversine_km(points[index], points[index + 1])
        for index in range(len(points) - 1)
    ]
    total = sum(lengths)
    if total == 0:
        return points[0]
    remaining = total * min(1.0, max(0.0, fraction))
    for index, segment_length in enumerate(lengths):
        if remaining <= segment_length or index == len(lengths) - 1:
            within = 0.0 if segment_length == 0 else remaining / segment_length
            a, b = points[index], points[index + 1]
            return (a[0] + (b[0] - a[0]) * within, a[1] + (b[1] - a[1]) * within)
        remaining -= segment_length
    return points[-1]


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    from math import asin, cos, radians, sin, sqrt

    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
    value = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(value))
