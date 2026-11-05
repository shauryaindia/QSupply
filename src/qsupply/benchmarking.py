"""Reproducible synthetic CVRP benchmarks and solver comparisons."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil, dist
from numbers import Real
from random import Random
from time import perf_counter
from types import MappingProxyType
from fractions import Fraction

from ._costs import exact_transportation_cost
from .exact_routing import MAX_EXACT_CUSTOMERS, ExactCVRPSolver, InfeasibleCVRPError
from .routing import CVRPProblem
from .routing_heuristics import NearestNeighborTwoOptSolver


@dataclass(frozen=True)
class BenchmarkMethodResult:
    """Standardized measurements for one method on one CVRP instance.

    ``status`` is ``success``, ``construction_failed`` (heuristic did not find
    a plan; this does not prove infeasibility), or ``problem_infeasible``
    (established by the exact solver). Distance, routes, vehicle count and gap
    are ``None`` when no solution is available.
    """

    method: str
    status: str
    routes: Mapping[str, tuple[str, ...]] | None
    total_distance: Real | None
    feasible: bool | None
    vehicles_used: int | None
    elapsed_seconds: float
    optimality_gap_percent: float | None
    failure_reason: str | None = None


@dataclass(frozen=True)
class CVRPBenchmarkReport:
    """Comparable heuristic and exact results for one configured instance."""

    instance_name: str
    customer_count: int
    results: tuple[BenchmarkMethodResult, ...]
    instance_seed: int | None
    instance_configuration: Mapping[str, object]

    def result_for(self, method: str) -> BenchmarkMethodResult:
        """Return the entry with the requested method name."""
        for result in self.results:
            if result.method == method:
                return result
        raise KeyError(f"no benchmark result for method {method!r}")


def generate_synthetic_cvrp(customer_count: int, seed: int = 2026) -> CVRPProblem:
    """Create a reproducible Euclidean CVRP instance using only stdlib RNG.

    Demand and capacity profiles vary with customer count. Distances are
    generated from integer coordinates and are not real-world map distances.
    """
    if isinstance(customer_count, bool) or not isinstance(customer_count, int):
        raise TypeError("customer_count must be an integer")
    if customer_count < 1:
        raise ValueError("customer_count must be positive")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")

    rng = Random(seed)
    depot = "Depot"
    customer_names = tuple(f"Customer {index:02d}" for index in range(1, customer_count + 1))
    coordinates: dict[str, tuple[int, int]] = {depot: (50, 50)}
    for customer in customer_names:
        coordinates[customer] = (rng.randint(0, 100), rng.randint(0, 100))

    demands = {customer: rng.randint(1, 3) for customer in customer_names}
    base_capacity = {5: 9, 7: 10, 9: 11}.get(customer_count, 7 + customer_count // 2)
    vehicle_count = max(2, ceil(sum(demands.values()) / base_capacity))
    capacities = {
        f"Vehicle {index + 1}": base_capacity + (index % 2)
        for index in range(vehicle_count)
    }
    locations = (depot, *customer_names)
    distances = {
        (origin, destination): dist(coordinates[origin], coordinates[destination])
        for origin in locations
        for destination in locations
    }
    return CVRPProblem(depot, demands, capacities, distances)


def synthetic_benchmark_suite(seed: int = 2026) -> Mapping[str, CVRPProblem]:
    """Return reproducible 5-, 7-, and 9-customer synthetic instances."""
    return MappingProxyType(
        {
            f"synthetic-{count}": generate_synthetic_cvrp(count, seed + count)
            for count in (5, 7, 9)
        }
    )


def _instance_configuration(problem: CVRPProblem) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "depot": problem.depot,
            "customer_demands": MappingProxyType(dict(problem.customer_demands)),
            "vehicle_capacities": MappingProxyType(dict(problem.vehicle_capacities)),
            "distances": MappingProxyType(dict(problem.distances)),
        }
    )


def benchmark_cvrp(
    problem: CVRPProblem,
    instance_name: str = "cvrp-instance",
    seed: int | None = None,
) -> CVRPBenchmarkReport:
    """Compare NN, NN+2-opt, and exact results for one instance.

    The common objective is the exact sum of represented arc values: integers
    and rationals remain exact, while a Python float is treated as its exact
    stored IEEE-754 binary rational value. Gaps use
    ``100 * (method distance - exact distance) / exact distance`` and are
    undefined when exact distance is zero or no exact solution exists.

    Each timer covers method execution plus common route validation and
    objective scoring. Times are one-run observations, not statistically
    reliable performance estimates. Heuristic construction failures are
    recorded and do not prevent other methods from running.
    """
    if not isinstance(problem, CVRPProblem):
        raise TypeError("problem must be a CVRPProblem")
    if not isinstance(instance_name, str) or not instance_name:
        raise ValueError("instance_name must be a non-empty string")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise TypeError("seed must be an integer or None")
    customer_count = len(problem.customer_demands)
    if customer_count > MAX_EXACT_CUSTOMERS:
        raise ValueError(
            f"benchmark exact reference supports at most {MAX_EXACT_CUSTOMERS} customers"
        )

    heuristic = NearestNeighborTwoOptSolver()

    def run_heuristic(method: str, solve) -> BenchmarkMethodResult:
        started = perf_counter()
        try:
            routes = solve()
            problem.validate_routes(routes)
            distance = exact_transportation_cost(problem.distances, routes)
            elapsed = perf_counter() - started
            return BenchmarkMethodResult(
                method=method,
                status="success",
                routes=MappingProxyType(dict(routes)),
                total_distance=distance,
                feasible=True,
                vehicles_used=sum(bool(route[1:-1]) for route in routes.values()),
                elapsed_seconds=elapsed,
                optimality_gap_percent=None,
            )
        except ValueError as error:
            elapsed = perf_counter() - started
            return BenchmarkMethodResult(
                method=method,
                status="construction_failed",
                routes=None,
                total_distance=None,
                feasible=None,
                vehicles_used=None,
                elapsed_seconds=elapsed,
                optimality_gap_percent=None,
                failure_reason=str(error),
            )

    nearest = run_heuristic(
        "nearest-neighbour",
        lambda: heuristic.construct_initial_routes(problem),
    )
    improved = run_heuristic(
        "nearest-neighbour+2-opt",
        lambda: heuristic.solve(problem).routes,
    )

    started = perf_counter()
    try:
        exact = ExactCVRPSolver().solve(problem)
    except InfeasibleCVRPError as error:
        exact_elapsed = perf_counter() - started
        exact_result = BenchmarkMethodResult(
            method="exact",
            status="problem_infeasible",
            routes=None,
            total_distance=None,
            feasible=False,
            vehicles_used=None,
            elapsed_seconds=exact_elapsed,
            optimality_gap_percent=None,
            failure_reason=str(error),
        )
        exact_distance = None
    else:
        problem.validate_routes(exact.routes)
        exact_distance = exact_transportation_cost(problem.distances, exact.routes)
        exact_elapsed = perf_counter() - started
        exact_result = BenchmarkMethodResult(
            method="exact",
            status="success",
            routes=MappingProxyType(dict(exact.routes)),
            total_distance=exact_distance,
            feasible=True,
            vehicles_used=sum(bool(route[1:-1]) for route in exact.routes.values()),
            elapsed_seconds=exact_elapsed,
            optimality_gap_percent=0.0 if exact_distance != 0 else None,
        )

    def with_gap(result: BenchmarkMethodResult) -> BenchmarkMethodResult:
        if result.status != "success" or exact_distance is None or exact_distance == 0:
            return result
        assert result.total_distance is not None
        gap = float(
            (Fraction(result.total_distance) - Fraction(exact_distance))
            / Fraction(exact_distance)
            * 100
        )
        return BenchmarkMethodResult(
            method=result.method,
            status=result.status,
            routes=result.routes,
            total_distance=result.total_distance,
            feasible=result.feasible,
            vehicles_used=result.vehicles_used,
            elapsed_seconds=result.elapsed_seconds,
            optimality_gap_percent=gap,
            failure_reason=result.failure_reason,
        )

    return CVRPBenchmarkReport(
        instance_name=instance_name,
        customer_count=customer_count,
        results=(with_gap(nearest), with_gap(improved), exact_result),
        instance_seed=seed,
        instance_configuration=_instance_configuration(problem),
    )


def benchmark_suite(
    instances: Mapping[str, CVRPProblem] | None = None,
    seed: int = 2026,
) -> tuple[CVRPBenchmarkReport, ...]:
    """Benchmark supplied instances or the standard reproducible suite."""
    if instances is None:
        selected = synthetic_benchmark_suite(seed)
        return tuple(
            benchmark_cvrp(problem, name, seed + count)
            for count, (name, problem) in zip((5, 7, 9), selected.items())
        )
    if not isinstance(instances, Mapping) or not instances:
        raise ValueError("instances must be a non-empty mapping of names to CVRPProblem objects")
    return tuple(benchmark_cvrp(problem, name) for name, problem in instances.items())
