"""Reproducible route-assignment QUBO example and exact reference comparison."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ..solver import ExactQUBOSolver, ProblemRepresentation, SolverResult
from .global_demo import global_demo_network, global_demo_shipments
from .models import DisruptionScenario
from .planning import (
    ObjectiveWeights,
    RecoveryComparison,
    RouteAssignment,
    ShipmentProfile,
    assign_routes,
    compare_recovery,
)
from .route_qubo import RouteAssignmentQUBO, formulate_route_assignment_qubo


ROUTE_QUBO_DEMO_SHIPMENT_IDS = ("EXP-104", "EXP-407")
ROUTE_QUBO_DEMO_SCENARIO = DisruptionScenario(
    id="synthetic-route-qubo-shanghai-access-capacity",
    capacity_overrides={"road-shanghai-port": 3},
)


@dataclass(frozen=True)
class RouteQUBOReferenceComparison:
    """Exact QUBO result and classical assignment over identical route options."""

    formulation: RouteAssignmentQUBO
    exact_result: SolverResult
    classical_result: RouteAssignment | None
    candidate_comparison: RecoveryComparison
    same_objective: bool


def route_qubo_demo_profiles() -> tuple[ShipmentProfile, ...]:
    """Return two synthetic Shanghai-origin shipments with distinct destinations."""
    profiles_by_id = {profile.request.id: profile for profile in global_demo_shipments()}
    return tuple(profiles_by_id[item] for item in ROUTE_QUBO_DEMO_SHIPMENT_IDS)


def build_route_qubo_demo(
    weights: ObjectiveWeights | None = None,
) -> tuple[RouteAssignmentQUBO, RecoveryComparison]:
    """Build the small disruption example with baseline-fixed normalization.

    Three recovery candidates per shipment are intentionally selected. With
    these candidates the assignment has six route-choice bits and two exact
    capacity-slack bits, within the shared 12-variable exact/QAOA limit.
    """
    network = global_demo_network()
    profiles = route_qubo_demo_profiles()
    selected_weights = weights or ObjectiveWeights()
    comparison = compare_recovery(
        network,
        profiles,
        ROUTE_QUBO_DEMO_SCENARIO,
        selected_weights,
        max_routes=3,
    )
    if not comparison.recovery_feasible:
        raise ValueError(
            "the configured synthetic route-QUBO example has no feasible recovery assignment"
        )
    formulation = formulate_route_assignment_qubo(
        network,
        profiles,
        comparison.recovery_candidates,
        selected_weights,
        comparison.normalization_references,
        ROUTE_QUBO_DEMO_SCENARIO,
    )
    return formulation, comparison


def compare_route_qubo_to_classical(
    weights: ObjectiveWeights | None = None,
) -> RouteQUBOReferenceComparison:
    """Solve both methods over the identical finite recovery candidate set."""
    formulation, comparison = build_route_qubo_demo(weights)
    classical = assign_routes(
        formulation.network,
        formulation.profiles,
        comparison.recovery_candidates,
        formulation.weights,
        formulation.normalization_references,
        formulation.scenario,
    )
    result = ExactQUBOSolver().solve(
        formulation.solver_request(ProblemRepresentation.QUBO)
    )
    exact_objective = result.business_objective
    classical_objective = (
        None if classical is None else Fraction(str(classical.metrics.weighted_objective))
    )
    same_objective = (
        classical is not None
        and result.feasible is True
        and exact_objective is not None
        and abs(float(exact_objective) - float(classical_objective)) <= 1e-12
    )
    return RouteQUBOReferenceComparison(
        formulation=formulation,
        exact_result=result,
        classical_result=classical,
        candidate_comparison=comparison,
        same_objective=same_objective,
    )
