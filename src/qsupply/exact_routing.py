"""Exact CVRP solver intended for small reference instances."""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from fractions import Fraction
from numbers import Real
from types import MappingProxyType
from typing import TYPE_CHECKING

from ._costs import exact_number, exact_transportation_cost

if TYPE_CHECKING:
    from .routing import CVRPProblem


# Held-Karp subset route costs plus a vehicle/subset partition dynamic program
# are practical for this small limit, but grow exponentially beyond it.
MAX_EXACT_CUSTOMERS = 10


class InfeasibleCVRPError(ValueError):
    """Raised when vehicle capacities cannot cover all customer demands."""


@dataclass(frozen=True)
class ExactCVRPSolution:
    """Minimum-distance routes for the exact sum of represented arc values.

    Integer/rational arc values are summed exactly. A Python float is treated
    as its exact stored IEEE-754 binary rational value, with no tolerance.
    """

    routes: Mapping[str, tuple[str, ...]]
    total_distance: Real


class ExactCVRPSolver:
    """Find a minimum-distance CVRP solution by subset dynamic programming.

    Route costs are computed with Held-Karp dynamic programming, then customer
    subsets are partitioned across the available vehicles subject to capacity.
    The time/memory requirements grow exponentially; at most
    :data:`MAX_EXACT_CUSTOMERS` are supported.
    """

    def solve(self, problem: "CVRPProblem") -> ExactCVRPSolution:
        """Return the globally optimal supported solution or raise ``ValueError``.

        Raises ``TypeError`` for a non-CVRP input and ``ValueError`` when the
        instance exceeds the exact limit or has no feasible vehicle assignment.
        """
        from .routing import CVRPProblem

        if not isinstance(problem, CVRPProblem):
            raise TypeError("problem must be a CVRPProblem")
        customers = tuple(problem.customer_demands)
        customer_count = len(customers)
        if customer_count > MAX_EXACT_CUSTOMERS:
            raise ValueError(
                f"exact CVRP solver supports at most {MAX_EXACT_CUSTOMERS} customers; "
                f"received {customer_count}"
            )

        total_demand = sum(
            (exact_number(demand) for demand in problem.customer_demands.values()), Fraction(0)
        )
        total_capacity = sum(
            (exact_number(capacity) for capacity in problem.vehicle_capacities.values()), Fraction(0)
        )
        largest_capacity = max(problem.vehicle_capacities.values())
        oversized = [
            customer
            for customer, demand in problem.customer_demands.items()
            if demand > largest_capacity
        ]
        if oversized:
            raise InfeasibleCVRPError(
                f"customer {oversized[0]!r} demand exceeds every vehicle capacity"
            )
        if total_demand > total_capacity:
            raise InfeasibleCVRPError(
                f"total customer demand {total_demand} exceeds total vehicle capacity {total_capacity}"
            )

        count = customer_count
        full_mask = (1 << count) - 1
        depot = problem.depot
        distances = problem.distances

        @lru_cache(maxsize=None)
        def path_to(mask: int, last: int) -> tuple[Fraction, tuple[int, ...]]:
            """Minimum depot-to-last path visiting exactly ``mask``."""
            previous_mask = mask & ~(1 << last)
            if previous_mask == 0:
                return exact_number(distances[(depot, customers[last])]), (last,)

            best_cost: Fraction | None = None
            best_path: tuple[int, ...] = ()
            for previous in range(count):
                if previous_mask & (1 << previous):
                    previous_cost, previous_path = path_to(previous_mask, previous)
                    cost = previous_cost + exact_number(
                        distances[(customers[previous], customers[last])]
                    )
                    if best_cost is None or cost < best_cost:
                        best_cost = cost
                        best_path = previous_path + (last,)
            assert best_cost is not None
            return best_cost, best_path

        subset_routes: dict[int, tuple[Fraction, tuple[str, ...]]] = {
            0: (Fraction(0), (depot, depot))
        }
        subset_demands = [Fraction(0)] * (full_mask + 1)
        for mask in range(1, full_mask + 1):
            bit = mask & -mask
            index = bit.bit_length() - 1
            subset_demands[mask] = (
                subset_demands[mask ^ bit]
                + exact_number(problem.customer_demands[customers[index]])
            )
            best_route_cost: Fraction | None = None
            best_route: tuple[str, ...] = ()
            for last in range(count):
                if mask & (1 << last):
                    path_cost, path = path_to(mask, last)
                    route_cost = path_cost + exact_number(distances[(customers[last], depot)])
                    if best_route_cost is None or route_cost < best_route_cost:
                        best_route_cost = route_cost
                        best_route = (depot, *(customers[i] for i in path), depot)
            assert best_route_cost is not None
            subset_routes[mask] = best_route_cost, best_route

        vehicles = tuple(problem.vehicle_capacities.items())

        @lru_cache(maxsize=None)
        def partition(vehicle_index: int, remaining_mask: int):
            if remaining_mask == 0:
                return Fraction(0), ()
            if vehicle_index == len(vehicles):
                return None

            _, capacity = vehicles[vehicle_index]
            best: tuple[Fraction, tuple[int, ...]] | None = None
            subset = remaining_mask
            while True:
                if subset_demands[subset] <= exact_number(capacity):
                    suffix = partition(vehicle_index + 1, remaining_mask ^ subset)
                    if suffix is not None:
                        cost = subset_routes[subset][0] + suffix[0]
                        if best is None or cost < best[0]:
                            best = cost, (subset, *suffix[1])
                if subset == 0:
                    break
                subset = (subset - 1) & remaining_mask
            return best

        assignment = partition(0, full_mask)
        if assignment is None:
            raise InfeasibleCVRPError(
                "no feasible customer assignment satisfies the vehicle capacities"
            )

        routes: dict[str, tuple[str, ...]] = {}
        for index, (vehicle, _) in enumerate(vehicles):
            subset = assignment[1][index] if index < len(assignment[1]) else 0
            routes[vehicle] = subset_routes[subset][1]

        problem.validate_routes(routes)
        actual_distance = exact_transportation_cost(distances, routes)
        return ExactCVRPSolution(
            routes=MappingProxyType(routes),
            total_distance=actual_distance,
        )
