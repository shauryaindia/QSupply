"""Data model and feasibility checks for capacitated vehicle routing."""

from collections.abc import Mapping, Sequence
from math import isfinite
from numbers import Real
from types import MappingProxyType

from ._costs import exact_number, exact_transportation_cost


def _non_negative_finite(value: object, label: str) -> Real:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{label} must be a real number")
    try:
        finite = isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return value


class CVRPProblem:
    """A single-depot CVRP instance with named customers and vehicles.

    ``distances[(a, b)]`` is the travel distance/cost from location ``a`` to
    ``b``. The matrix must contain every ordered pair of locations, including
    zero-cost diagonal entries. Routes supplied to :meth:`validate_routes` and
    :meth:`transportation_cost` explicitly include the depot at both ends.

    This class validates and scores routes; it does not search for routes.
    """

    def __init__(
        self,
        depot: str,
        customer_demands: Mapping[str, Real],
        vehicle_capacities: Mapping[str, Real],
        distances: Mapping[tuple[str, str], Real],
    ) -> None:
        if not isinstance(depot, str) or not depot:
            raise ValueError("depot must be a non-empty string")
        if not isinstance(customer_demands, Mapping) or not customer_demands:
            raise ValueError("customer_demands must be a non-empty mapping")
        if not isinstance(vehicle_capacities, Mapping) or not vehicle_capacities:
            raise ValueError("vehicle_capacities must be a non-empty mapping")
        if not isinstance(distances, Mapping):
            raise TypeError("distances must be a mapping of location pairs to values")

        customers = dict(customer_demands)
        vehicles = dict(vehicle_capacities)
        for name in customers:
            if not isinstance(name, str) or not name:
                raise ValueError("customer names must be non-empty strings")
            if name == depot:
                raise ValueError("depot cannot also be a customer")
        for name in vehicles:
            if not isinstance(name, str) or not name:
                raise ValueError("vehicle names must be non-empty strings")

        self._depot = depot
        self._customer_demands = MappingProxyType(
            {
                customer: _non_negative_finite(demand, f"demand for {customer!r}")
                for customer, demand in customers.items()
            }
        )
        self._vehicle_capacities = MappingProxyType(
            {
                vehicle: _non_negative_finite(capacity, f"capacity for {vehicle!r}")
                for vehicle, capacity in vehicles.items()
            }
        )

        locations = {depot, *customers}
        copied_distances: dict[tuple[str, str], Real] = {}
        for pair, distance in distances.items():
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not all(isinstance(location, str) for location in pair)
                or pair[0] not in locations
                or pair[1] not in locations
            ):
                raise ValueError(f"distance key {pair!r} must be a pair of known locations")
            copied_distances[pair] = _non_negative_finite(
                distance, f"distance for {pair!r}"
            )

        expected_arcs = {(origin, destination) for origin in locations for destination in locations}
        missing_arcs = expected_arcs - copied_distances.keys()
        if missing_arcs:
            raise ValueError(f"distance matrix is missing entries: {sorted(missing_arcs)!r}")
        nonzero_diagonal = [
            (location, location)
            for location in locations
            if copied_distances[(location, location)] != 0
        ]
        if nonzero_diagonal:
            raise ValueError(f"distance matrix diagonal must be zero: {nonzero_diagonal!r}")

        self._distances = MappingProxyType(copied_distances)

    @property
    def depot(self) -> str:
        return self._depot

    @property
    def customer_demands(self) -> Mapping[str, Real]:
        return self._customer_demands

    @property
    def vehicle_capacities(self) -> Mapping[str, Real]:
        return self._vehicle_capacities

    @property
    def distances(self) -> Mapping[tuple[str, str], Real]:
        return self._distances

    def validate_routes(self, routes: Mapping[str, Sequence[str]]) -> None:
        """Raise ``ValueError`` unless routes form a feasible full delivery plan."""
        if not isinstance(routes, Mapping):
            raise TypeError("routes must map vehicle names to location sequences")

        expected_vehicles = set(self._vehicle_capacities)
        supplied_vehicles = set(routes)
        missing_vehicles = expected_vehicles - supplied_vehicles
        unknown_vehicles = supplied_vehicles - expected_vehicles
        if missing_vehicles:
            raise ValueError(f"routes are missing vehicles: {sorted(missing_vehicles)!r}")
        if unknown_vehicles:
            raise ValueError(f"routes contain unknown vehicles: {sorted(unknown_vehicles)!r}")

        visited: set[str] = set()
        for vehicle, route in routes.items():
            if isinstance(route, (str, bytes)) or not isinstance(route, Sequence):
                raise TypeError(f"route for vehicle {vehicle!r} must be a location sequence")
            if len(route) < 2 or route[0] != self._depot or route[-1] != self._depot:
                raise ValueError(
                    f"route for vehicle {vehicle!r} must start and end at depot {self._depot!r}"
                )

            load = 0
            for customer in route[1:-1]:
                if not isinstance(customer, str) or customer not in self._customer_demands:
                    raise ValueError(f"route for vehicle {vehicle!r} contains invalid customer {customer!r}")
                if customer in visited:
                    raise ValueError(f"customer {customer!r} is delivered more than once")
                visited.add(customer)
                load += exact_number(self._customer_demands[customer])
            capacity = self._vehicle_capacities[vehicle]
            if load > exact_number(capacity):
                raise ValueError(
                    f"route for vehicle {vehicle!r} has load {load}, exceeding capacity {capacity}"
                )

        missing_customers = set(self._customer_demands) - visited
        if missing_customers:
            raise ValueError(f"customers are not delivered: {sorted(missing_customers)!r}")

    def transportation_cost(self, routes: Mapping[str, Sequence[str]]) -> Real:
        """Return exact sum of route arc values after validating feasibility.

        Float arc values are interpreted as their exact stored binary rational
        values; the total may therefore be a :class:`fractions.Fraction`.
        """
        self.validate_routes(routes)
        return exact_transportation_cost(self._distances, routes)
