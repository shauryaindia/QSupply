"""Small, backend-neutral import-export supply-chain QUBO formulation."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from math import isfinite
from numbers import Real
from types import MappingProxyType

from .qubo import QUBO


def _finite_non_negative(value: object, label: str) -> Real:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{label} must be a real number")
    try:
        finite = isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return value


def _non_empty_name(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _binary_assignment(
    assignment: Mapping[str, int], expected_variables: Sequence[str]
) -> None:
    if not isinstance(assignment, Mapping):
        raise TypeError("assignment must be a mapping of variable names to 0 or 1")
    expected = set(expected_variables)
    supplied = set(assignment)
    missing = expected - supplied
    unknown = supplied - expected
    if missing:
        raise ValueError(f"assignment is missing variables: {sorted(missing)!r}")
    if unknown:
        raise ValueError(f"assignment contains unknown variables: {sorted(unknown)!r}")
    for variable in expected_variables:
        value = assignment[variable]
        if isinstance(value, bool):
            continue
        if not isinstance(value, Real) or value not in (0, 1):
            raise ValueError(
                f"assignment for variable {variable!r} must be 0 or 1; got {value!r}"
            )


@dataclass(frozen=True)
class TransportOption:
    """One shipment's candidate route/mode and its lane resource usage."""

    name: str
    freight_cost: Real
    delivery_time: Real
    carbon_impact: Real
    lane_usage: Mapping[str, int]

    def __post_init__(self) -> None:
        _non_empty_name(self.name, "option name")
        for attribute in ("freight_cost", "delivery_time", "carbon_impact"):
            value = _finite_non_negative(getattr(self, attribute), attribute)
            object.__setattr__(self, attribute, value)
        if not isinstance(self.lane_usage, Mapping):
            raise TypeError("lane_usage must map lane names to non-negative integer units")
        usage: dict[str, int] = {}
        for lane, units in self.lane_usage.items():
            _non_empty_name(lane, "lane name")
            if isinstance(units, bool) or not isinstance(units, int):
                raise TypeError(f"lane usage for {lane!r} must be a non-negative integer")
            if units < 0:
                raise ValueError(f"lane usage for {lane!r} must be non-negative")
            usage[lane] = units
        object.__setattr__(self, "lane_usage", MappingProxyType(usage))


@dataclass(frozen=True)
class Shipment:
    """A shipment deadline, lateness rate, and its available options."""

    name: str
    deadline: Real
    delay_penalty_per_unit: Real
    options: tuple[TransportOption, ...]

    def __post_init__(self) -> None:
        _non_empty_name(self.name, "shipment name")
        object.__setattr__(self, "deadline", _finite_non_negative(self.deadline, "deadline"))
        object.__setattr__(
            self,
            "delay_penalty_per_unit",
            _finite_non_negative(self.delay_penalty_per_unit, "delay_penalty_per_unit"),
        )
        try:
            options = tuple(self.options)
        except TypeError as error:
            raise TypeError(
                "options must be a non-empty sequence of TransportOption objects"
            ) from error
        if not options or any(not isinstance(option, TransportOption) for option in options):
            raise ValueError("each shipment must have at least one TransportOption")
        names = [option.name for option in options]
        if len(set(names)) != len(names):
            raise ValueError(f"option names for shipment {self.name!r} must be unique")
        object.__setattr__(self, "options", options)


@dataclass(frozen=True)
class ImportExportProblem:
    """Discrete import-export assignment data and business-cost parameters.

    Lane usage and capacities are integer-scaled units. Cost inputs may be
    finite non-negative real values. Python floats are interpreted as their
    exact stored IEEE-754 rational values during objective construction.
    """

    shipments: tuple[Shipment, ...]
    lane_capacities: Mapping[str, int]
    delivery_time_cost_per_unit: Real = 1
    carbon_cost_per_unit: Real = 1

    def __post_init__(self) -> None:
        shipments = tuple(self.shipments)
        if not shipments or any(not isinstance(item, Shipment) for item in shipments):
            raise ValueError("shipments must be a non-empty sequence of Shipment objects")
        names = [shipment.name for shipment in shipments]
        if len(set(names)) != len(names):
            raise ValueError("shipment names must be unique")
        object.__setattr__(self, "shipments", shipments)

        if not isinstance(self.lane_capacities, Mapping) or not self.lane_capacities:
            raise ValueError("lane_capacities must be a non-empty mapping")
        capacities: dict[str, int] = {}
        for lane, capacity in self.lane_capacities.items():
            _non_empty_name(lane, "lane name")
            if isinstance(capacity, bool) or not isinstance(capacity, int):
                raise TypeError(f"capacity for lane {lane!r} must be a non-negative integer")
            if capacity < 0:
                raise ValueError(f"capacity for lane {lane!r} must be non-negative")
            capacities[lane] = capacity
        known_lanes = set(capacities)
        for shipment in shipments:
            for option in shipment.options:
                unknown = set(option.lane_usage) - known_lanes
                if unknown:
                    raise ValueError(
                        f"option {shipment.name!r}/{option.name!r} uses unknown lanes: "
                        f"{sorted(unknown)!r}"
                    )
        object.__setattr__(self, "lane_capacities", MappingProxyType(capacities))
        for attribute in ("delivery_time_cost_per_unit", "carbon_cost_per_unit"):
            value = _finite_non_negative(getattr(self, attribute), attribute)
            object.__setattr__(self, attribute, value)


@dataclass(frozen=True)
class FeasibilityReport:
    """Independent result of checking a binary plan against domain data."""

    feasible: bool
    violations: tuple[str, ...]
    selected_options: Mapping[str, str]
    lane_usage: Mapping[str, int]


@dataclass(frozen=True)
class ImportExportEvaluation:
    """Separate business cost, penalty, offset, and QUBO energy values."""

    business_cost: Real
    penalty_contribution: Real
    qubo_offset: Real
    qubo_energy: Real
    full_penalized_energy: Real


@dataclass(frozen=True)
class ImportExportFormulation:
    """QUBO plus its domain mapping and constant offset."""

    problem: ImportExportProblem
    qubo: QUBO
    penalty: Real
    offset: Real
    decision_variables: Mapping[tuple[str, str], str]
    slack_variables: Mapping[str, tuple[tuple[str, int], ...]]

    def full_energy(self, assignment: Mapping[str, int]) -> Real:
        """Return the QUBO energy including the separately stored constant."""
        return self.offset + self.qubo.energy(assignment)

    def decode(self, assignment: Mapping[str, int]) -> Mapping[str, str]:
        """Decode a complete binary assignment to one option per shipment.

        One-hot selection is required for decoding. Lane capacity is checked
        separately by :meth:`check_feasibility`.
        """
        _binary_assignment(assignment, self.qubo.variables)
        selections: dict[str, str] = {}
        for shipment in self.problem.shipments:
            selected = [
                option.name
                for option in shipment.options
                if assignment[self.decision_variables[(shipment.name, option.name)]] == 1
            ]
            if len(selected) != 1:
                raise ValueError(
                    f"shipment {shipment.name!r} must select exactly one option; "
                    f"selected {len(selected)}"
                )
            selections[shipment.name] = selected[0]
        return MappingProxyType(selections)

    def check_feasibility(self, assignment: Mapping[str, int]) -> FeasibilityReport:
        """Check one-hot choices and lane limits directly from problem data.

        This check does not use the QUBO coefficients, penalty energy, or slack
        values to decide whether the selected operational plan is feasible.
        """
        violations: list[str] = []
        selected_options: dict[str, str] = {}
        lane_usage = {lane: 0 for lane in self.problem.lane_capacities}
        if not isinstance(assignment, Mapping):
            raise TypeError("assignment must be a mapping of variable names to 0 or 1")
        decision_variables = set(self.decision_variables.values())
        slack_variables = {
            variable
            for lane_bits in self.slack_variables.values()
            for variable, _ in lane_bits
        }
        recognized = decision_variables | slack_variables
        supplied = set(assignment)
        missing = decision_variables - supplied
        unknown = supplied - recognized
        if missing:
            violations.append(f"assignment is missing variables: {sorted(missing)!r}")
        if unknown:
            violations.append(f"assignment contains unknown variables: {sorted(unknown)!r}")
        invalid_values = {
            variable: assignment[variable]
            for variable in decision_variables & supplied
            if not isinstance(assignment[variable], bool)
            and (
                not isinstance(assignment[variable], Real)
                or assignment[variable] not in (0, 1)
            )
        }
        if invalid_values:
            violations.append(f"assignment contains non-binary values: {invalid_values!r}")
        if missing or unknown or invalid_values:
            return FeasibilityReport(
                False,
                tuple(violations),
                MappingProxyType(selected_options),
                MappingProxyType(lane_usage),
            )

        for shipment in self.problem.shipments:
            selected = [
                option
                for option in shipment.options
                if assignment[self.decision_variables[(shipment.name, option.name)]] == 1
            ]
            if len(selected) != 1:
                violations.append(
                    f"shipment {shipment.name!r} must select exactly one option; "
                    f"selected {len(selected)}"
                )
            else:
                selected_options[shipment.name] = selected[0].name
            for option in selected:
                for lane, units in option.lane_usage.items():
                    lane_usage[lane] += units

        for lane, used in lane_usage.items():
            capacity = self.problem.lane_capacities[lane]
            if used > capacity:
                violations.append(
                    f"lane {lane!r} usage {used} exceeds capacity {capacity}"
                )
        return FeasibilityReport(
            not violations,
            tuple(violations),
            MappingProxyType(selected_options),
            MappingProxyType(lane_usage),
        )

    def penalty_contribution(self, assignment: Mapping[str, int]) -> Real:
        """Evaluate the one-hot and slack equality penalties independently."""
        _binary_assignment(assignment, self.qubo.variables)
        total: Real = 0
        for shipment in self.problem.shipments:
            selected_count = sum(
                assignment[self.decision_variables[(shipment.name, option.name)]]
                for option in shipment.options
            )
            total += self.penalty * (1 - selected_count) ** 2
        for lane, capacity in self.problem.lane_capacities.items():
            usage = sum(
                option.lane_usage.get(lane, 0)
                * assignment[self.decision_variables[(shipment.name, option.name)]]
                for shipment in self.problem.shipments
                for option in shipment.options
            )
            slack = sum(
                weight * assignment[variable]
                for variable, weight in self.slack_variables[lane]
            )
            total += self.penalty * (usage + slack - capacity) ** 2
        return total

    def business_cost_of_assignment(self, assignment: Mapping[str, int]) -> Real:
        """Sum original option costs for all active decision bits."""
        _binary_assignment(assignment, self.qubo.variables)
        return sum(
            _option_business_cost(self.problem, shipment, option)
            * assignment[self.decision_variables[(shipment.name, option.name)]]
            for shipment in self.problem.shipments
            for option in shipment.options
        )

    def evaluate(self, assignment: Mapping[str, int]) -> ImportExportEvaluation:
        """Return separately auditable objective, penalty, offset, and energy."""
        business_cost = self.business_cost_of_assignment(assignment)
        penalty = self.penalty_contribution(assignment)
        qubo_energy = self.qubo.energy(assignment)
        return ImportExportEvaluation(
            business_cost=business_cost,
            penalty_contribution=penalty,
            qubo_offset=self.offset,
            qubo_energy=qubo_energy,
            full_penalized_energy=self.offset + qubo_energy,
        )


def _option_business_cost(
    problem: ImportExportProblem, shipment: Shipment, option: TransportOption
) -> Real:
    freight = Fraction(option.freight_cost)
    delivery_time = Fraction(option.delivery_time)
    deadline = Fraction(shipment.deadline)
    delay_rate = Fraction(shipment.delay_penalty_per_unit)
    time_weight = Fraction(problem.delivery_time_cost_per_unit)
    carbon_weight = Fraction(problem.carbon_cost_per_unit)
    carbon = Fraction(option.carbon_impact)
    lateness = max(Fraction(0), delivery_time - deadline)
    return (
        freight
        + time_weight * delivery_time
        + delay_rate * lateness
        + carbon_weight * carbon
    )


def evaluate_business_objective(
    problem: ImportExportProblem, selections: Mapping[str, str]
) -> Real:
    """Evaluate business cost for a complete shipment-to-option plan."""
    if not isinstance(problem, ImportExportProblem):
        raise TypeError("problem must be an ImportExportProblem")
    if not isinstance(selections, Mapping):
        raise TypeError("selections must map shipment names to option names")
    expected = {shipment.name for shipment in problem.shipments}
    supplied = set(selections)
    if expected - supplied:
        raise ValueError(f"plan is missing shipments: {sorted(expected - supplied)!r}")
    if supplied - expected:
        raise ValueError(f"plan contains unknown shipments: {sorted(supplied - expected)!r}")
    total: Real = 0
    for shipment in problem.shipments:
        option_name = selections[shipment.name]
        option = next((item for item in shipment.options if item.name == option_name), None)
        if option is None:
            raise ValueError(
                f"plan for shipment {shipment.name!r} references unknown option {option_name!r}"
            )
        total += _option_business_cost(problem, shipment, option)
    return total


def formulate_import_export_qubo(
    problem: ImportExportProblem,
) -> ImportExportFormulation:
    """Build a QUBO with a provably sufficient penalty for this cost range.

    All business costs are non-negative. Float inputs are converted to their
    exact stored binary rational values before costs and coefficients are
    formed. ``penalty`` is one greater than the
    sum of each shipment's maximum option cost, which bounds every feasible
    plan. Integer lane units make every nonzero capacity residual at least one.
    Thus, whenever a feasible plan exists, no infeasible assignment can
    minimize the full penalized energy. The guarantee does not assert that the
    instance itself is feasible.
    """
    if not isinstance(problem, ImportExportProblem):
        raise TypeError("problem must be an ImportExportProblem")

    decision_variables: dict[tuple[str, str], str] = {}
    variables: list[str] = []
    for shipment_index, shipment in enumerate(problem.shipments):
        for option_index, option in enumerate(shipment.options):
            variable = f"select_s{shipment_index}_o{option_index}"
            decision_variables[(shipment.name, option.name)] = variable
            variables.append(variable)

    slack_variables: dict[str, tuple[tuple[str, int], ...]] = {}
    for lane_index, (lane, capacity) in enumerate(problem.lane_capacities.items()):
        bits: list[tuple[str, int]] = []
        representable = 0
        bit_index = 0
        while representable < capacity:
            weight = 1 << bit_index
            variable = f"slack_l{lane_index}_b{bit_index}"
            bits.append((variable, weight))
            variables.append(variable)
            representable += weight
            bit_index += 1
        slack_variables[lane] = tuple(bits)

    option_costs = {
        (shipment.name, option.name): _option_business_cost(problem, shipment, option)
        for shipment in problem.shipments
        for option in shipment.options
    }
    feasible_cost_bound = sum(
        max(option_costs[(shipment.name, option.name)] for option in shipment.options)
        for shipment in problem.shipments
    )
    penalty = feasible_cost_bound + 1
    coefficients: dict[tuple[str, str], Real] = {}
    offset: Real = 0

    def add_square(terms: list[tuple[str, Real]], target: Real) -> None:
        """Add penalty*(sum(weight*bit)-target)^2 to Q and its offset."""
        nonlocal offset
        offset += penalty * target**2
        for variable, weight in terms:
            coefficients[(variable, variable)] = coefficients.get(
                (variable, variable), 0
            ) + penalty * (weight**2 - 2 * target * weight)
        for (left, left_weight), (right, right_weight) in combinations(terms, 2):
            pair = (left, right)
            coefficients[pair] = coefficients.get(pair, 0) + (
                2 * penalty * left_weight * right_weight
            )

    for shipment in problem.shipments:
        terms: list[tuple[str, Real]] = []
        for option in shipment.options:
            variable = decision_variables[(shipment.name, option.name)]
            terms.append((variable, 1))
            coefficients[(variable, variable)] = (
                coefficients.get((variable, variable), 0)
                + option_costs[(shipment.name, option.name)]
            )
        add_square(terms, 1)

    for lane, capacity in problem.lane_capacities.items():
        terms = []
        for shipment in problem.shipments:
            for option in shipment.options:
                units = option.lane_usage.get(lane, 0)
                if units:
                    terms.append(
                        (decision_variables[(shipment.name, option.name)], units)
                    )
        terms.extend(slack_variables[lane])
        add_square(terms, capacity)

    return ImportExportFormulation(
        problem=problem,
        qubo=QUBO(tuple(variables), coefficients),
        penalty=penalty,
        offset=offset,
        decision_variables=MappingProxyType(decision_variables),
        slack_variables=MappingProxyType(slack_variables),
    )


def synthetic_import_export_problem() -> ImportExportProblem:
    """Return the documented two-shipment, two-option synthetic problem."""
    return ImportExportProblem(
        shipments=(
            Shipment(
                name="S1",
                deadline=3,
                delay_penalty_per_unit=2,
                options=(
                    TransportOption("A", 4, 2, 2, {"L1": 1}),
                    TransportOption("B", 2, 4, 1, {}),
                ),
            ),
            Shipment(
                name="S2",
                deadline=4,
                delay_penalty_per_unit=2,
                options=(
                    TransportOption("A", 3, 3, 2, {"L1": 1}),
                    TransportOption("B", 5, 2, 3, {}),
                ),
            ),
        ),
        lane_capacities={"L1": 1},
        delivery_time_cost_per_unit=1,
        carbon_cost_per_unit=1,
    )
