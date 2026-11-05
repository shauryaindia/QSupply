"""Deterministic classical heuristics for CVRP route construction."""

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from numbers import Real
from types import MappingProxyType
from typing import TYPE_CHECKING

from ._costs import exact_number

if TYPE_CHECKING:
    from .routing import CVRPProblem


@dataclass(frozen=True)
class RouteOptimizationResult:
    """Routes and distance measurements returned by the heuristic solver."""

    routes: Mapping[str, tuple[str, ...]]
    initial_distance: Real
    total_distance: Real

    @property
    def improvement_percent(self) -> float:
        """Percentage distance reduction from nearest-neighbour seed to 2-opt."""
        if self.initial_distance == 0:
            return 0.0
        return float(
            100
            * (Fraction(self.initial_distance) - Fraction(self.total_distance))
            / Fraction(self.initial_distance)
        )


class NearestNeighborTwoOptSolver:
    """Build capacity-feasible routes, then improve each route with 2-opt.

    Customers are considered in the order provided by the problem. Vehicles
    are filled in their declared order; at each step, the closest unserved
    customer that fits the remaining capacity is selected. Each resulting
    route is then improved by deterministic best-improvement 2-opt.

    This is a heuristic and does not guarantee a globally optimal solution.
    """

    def solve(self, problem: "CVRPProblem") -> RouteOptimizationResult:
        """Return feasible heuristic routes or raise ``ValueError`` if none
        can be constructed by this greedy assignment strategy.
        """
        from .routing import CVRPProblem

        if not isinstance(problem, CVRPProblem):
            raise TypeError("problem must be a CVRPProblem")

        initial_routes = self.construct_initial_routes(problem)
        initial_distance = problem.transportation_cost(initial_routes)
        improved_routes = {
            vehicle: self._two_opt(problem, route)
            for vehicle, route in initial_routes.items()
        }
        problem.validate_routes(improved_routes)
        total_distance = problem.transportation_cost(improved_routes)
        return RouteOptimizationResult(
            routes=MappingProxyType(improved_routes),
            initial_distance=initial_distance,
            total_distance=total_distance,
        )

    def construct_initial_routes(self, problem: "CVRPProblem") -> Mapping[str, tuple[str, ...]]:
        """Construct and return the deterministic capacity-feasible NN seed."""
        from .routing import CVRPProblem

        if not isinstance(problem, CVRPProblem):
            raise TypeError("problem must be a CVRPProblem")

        total_demand = sum(
            (exact_number(value) for value in problem.customer_demands.values()), Fraction(0)
        )
        total_capacity = sum(
            (exact_number(value) for value in problem.vehicle_capacities.values()), Fraction(0)
        )
        largest_capacity = max(problem.vehicle_capacities.values())
        oversized = [
            (customer, demand)
            for customer, demand in problem.customer_demands.items()
            if demand > largest_capacity
        ]
        if oversized:
            customer, demand = oversized[0]
            raise ValueError(
                f"customer {customer!r} demand {demand} exceeds every vehicle capacity"
            )
        if total_demand > total_capacity:
            raise ValueError(
                f"total customer demand {total_demand} exceeds total vehicle capacity {total_capacity}"
            )

        remaining = list(problem.customer_demands)
        routes: dict[str, tuple[str, ...]] = {}
        for vehicle, capacity in problem.vehicle_capacities.items():
            route = [problem.depot]
            load = 0
            current = problem.depot
            while True:
                feasible = [
                    customer
                    for customer in remaining
                    if load + exact_number(problem.customer_demands[customer])
                    <= exact_number(capacity)
                ]
                if not feasible:
                    break
                next_customer = min(
                    feasible,
                    key=lambda customer: problem.distances[(current, customer)],
                )
                route.append(next_customer)
                remaining.remove(next_customer)
                load += exact_number(problem.customer_demands[next_customer])
                current = next_customer
            route.append(problem.depot)
            routes[vehicle] = tuple(route)

        if remaining:
            raise ValueError(
                "nearest-neighbour construction could not assign all customers "
                f"within vehicle capacities; unassigned customers: {remaining!r}. "
                "A different customer-to-vehicle allocation may be required."
            )

        problem.validate_routes(routes)
        return MappingProxyType(routes)

    @staticmethod
    def _two_opt(problem: "CVRPProblem", route: tuple[str, ...]) -> tuple[str, ...]:
        """Apply best-improvement 2-opt until no reversal shortens the route."""
        current_route = list(route)

        def distance(candidate: list[str]) -> Fraction:
            return sum(
                (
                    exact_number(problem.distances[(origin, destination)])
                    for origin, destination in zip(candidate, candidate[1:])
                ),
                Fraction(0),
            )

        best_distance = distance(current_route)
        while True:
            candidate_best = current_route
            candidate_distance = best_distance
            for start in range(1, len(current_route) - 2):
                for end in range(start + 1, len(current_route) - 1):
                    candidate = (
                        current_route[:start]
                        + list(reversed(current_route[start : end + 1]))
                        + current_route[end + 1 :]
                    )
                    new_distance = distance(candidate)
                    if new_distance < candidate_distance:
                        candidate_best = candidate
                        candidate_distance = new_distance
            if candidate_distance >= best_distance:
                return tuple(current_route)
            current_route = candidate_best
            best_distance = candidate_distance
