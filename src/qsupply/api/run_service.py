"""Orchestrate actual QSupply CVRP solvers and persist their validated results."""

from time import perf_counter
from typing import Any

from qsupply import (
    ExactCVRPSolver,
    NearestNeighborTwoOptSolver,
)

from .instances import get_cvrp_instance
from .schemas import RunResult, SolverId
from .storage import SQLiteRunStore


def _distance_value(value: Any) -> float:
    return float(value)


def _gap_percent(method_distance: Any, exact_distance: Any) -> float | None:
    if exact_distance == 0:
        return None
    return float((method_distance - exact_distance) / exact_distance * 100)


def execute_run(
    store: SQLiteRunStore,
    run_id: str,
    instance_id: str,
    solver_id: SolverId,
    include_exact_reference: bool,
) -> None:
    """Run a selected solver, validate its output, and persist completion."""
    store.mark_running(run_id)
    try:
        problem = get_cvrp_instance(instance_id)
        started = perf_counter()
        initial_distance = None
        improvement_percent = None
        if solver_id is SolverId.NEAREST_NEIGHBOR:
            solver = NearestNeighborTwoOptSolver()
            routes = solver.construct_initial_routes(problem)
            total_distance = problem.transportation_cost(routes)
            initial_distance = total_distance
        elif solver_id is SolverId.NEAREST_NEIGHBOR_TWO_OPT:
            solver = NearestNeighborTwoOptSolver()
            result = solver.solve(problem)
            routes = result.routes
            total_distance = result.total_distance
            initial_distance = result.initial_distance
            improvement_percent = result.improvement_percent
        elif solver_id is SolverId.EXACT:
            result = ExactCVRPSolver().solve(problem)
            routes = result.routes
            total_distance = result.total_distance
        else:  # pragma: no cover - request validation constrains this enum
            raise ValueError(f"unsupported CVRP solver: {solver_id}")

        elapsed_seconds = perf_counter() - started
        problem.validate_routes(routes)
        independently_scored_distance = problem.transportation_cost(routes)
        if independently_scored_distance != total_distance:
            raise RuntimeError("solver distance does not match independent route validation")

        exact_distance = None
        exact_elapsed = None
        optimality_gap = None
        if include_exact_reference and solver_id is not SolverId.EXACT:
            reference_started = perf_counter()
            reference = ExactCVRPSolver().solve(problem)
            exact_elapsed = perf_counter() - reference_started
            problem.validate_routes(reference.routes)
            exact_distance = problem.transportation_cost(reference.routes)
            optimality_gap = _gap_percent(total_distance, exact_distance)

        run_result = RunResult(
            instance_id=instance_id,
            instance_name=f"Synthetic CVRP ({len(problem.customer_demands)} customers)",
            synthetic=True,
            customer_count=len(problem.customer_demands),
            solver=solver_id,
            routes={vehicle: list(route) for vehicle, route in routes.items()},
            feasible=True,
            total_distance=_distance_value(total_distance),
            total_distance_exact=str(total_distance),
            elapsed_seconds=elapsed_seconds,
            initial_distance=(
                _distance_value(initial_distance) if initial_distance is not None else None
            ),
            initial_distance_exact=(
                str(initial_distance) if initial_distance is not None else None
            ),
            improvement_percent=improvement_percent,
            exact_reference_distance=(
                _distance_value(exact_distance) if exact_distance is not None else None
            ),
            exact_reference_distance_exact=(
                str(exact_distance) if exact_distance is not None else None
            ),
            exact_reference_elapsed_seconds=exact_elapsed,
            optimality_gap_percent=optimality_gap,
        )
        store.mark_completed(run_id, run_result.model_dump(mode="json"))
    except Exception as error:
        store.mark_failed(run_id, f"{type(error).__name__}: {error}")
