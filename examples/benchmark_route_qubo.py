"""Run a reproducible four-method benchmark for the synthetic route QUBO.

This reports measurements from the current machine only; timings are not
statistical performance guarantees. Install both optional SDK requirements
before running this example.
"""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from qsupply.backends.qiskit import QiskitBackend, QiskitQAOASolver
from qsupply.backends.qulacs import QulacsBackend, QulacsQAOASolver
from qsupply.network import ObjectiveWeights
from qsupply.network.planning import assign_routes
from qsupply.network.route_qubo_demo import build_route_qubo_demo
from qsupply.qaoa import QAOAConfig
from qsupply.quantum_benchmark import benchmark_qaoa_backends_repeated
from qsupply.solver import ProblemRepresentation


SEEDS = (11, 22, 33, 44, 55)
DEPTH = 1
SHOTS = 128
MAX_ITERATIONS = 3


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _gap_percent(value: Any, reference: Any) -> float | None:
    if value is None or reference is None or reference == 0:
        return None
    return float((value - reference) / abs(reference) * 100)


def benchmark_profile(name: str, weights: ObjectiveWeights) -> dict[str, Any]:
    formulation, comparison = build_route_qubo_demo(weights)
    request = formulation.solver_request(ProblemRepresentation.QUBO)

    solvers = []
    if QiskitBackend.is_available():
        solvers.append(
            QiskitQAOASolver(
                QAOAConfig(
                    depth=DEPTH,
                    max_iterations=MAX_ITERATIONS,
                    shots=SHOTS,
                    random_seed=SEEDS[0],
                )
            )
        )
    if QulacsBackend.is_available():
        solvers.append(
            QulacsQAOASolver(
                QAOAConfig(
                    depth=DEPTH,
                    max_iterations=MAX_ITERATIONS,
                    shots=SHOTS,
                    random_seed=SEEDS[0],
                )
            )
        )
    if len(solvers) != 2:
        raise RuntimeError(
            "Both repository-supported Qiskit and Qulacs versions must be available"
        )

    report = benchmark_qaoa_backends_repeated(
        name, request, solvers, seeds=SEEDS
    )
    # Use the exact record returned by the common benchmark call as the one
    # penalized-model reference.
    exact = report.exact_reference
    feasible_business_optimum = exact.best_feasible_business_objective
    exact_routes = (
        dict(formulation.decode(exact.best_feasible_business_assignment))
        if exact.best_feasible_business_assignment is not None
        else None
    )
    exact_energy_routes = (
        dict(formulation.decode(exact.best_feasible_full_energy_assignment))
        if exact.best_feasible_full_energy_assignment is not None
        else None
    )

    classical_started = perf_counter()
    classical = assign_routes(
        formulation.network,
        formulation.profiles,
        comparison.recovery_candidates,
        formulation.weights,
        formulation.normalization_references,
        formulation.scenario,
    )
    classical_seconds = perf_counter() - classical_started
    if classical is None:
        classical_result: dict[str, Any] = {
            "solver": "classical-assignment",
            "backend": "QSupply assign_routes",
            "binary_variables": formulation.variable_count,
            "feasible": False,
            "full_penalized_energy": None,
            "business_objective": None,
            "optimality_gap_percent": None,
            "execution_time_seconds": classical_seconds,
            "timing_scope": "assign_routes call, including search, validation and objective calculation",
        }
    else:
        classical_routes = {
            shipment_id: route.id for shipment_id, route in classical.routes.items()
        }
        classical_assignment = formulation.encode_plan(classical_routes)
        classical_evaluation = formulation.evaluate_assignment(classical_assignment)
        classical_result = {
            "solver": "classical-assignment",
            "backend": "QSupply assign_routes",
            "binary_variables": formulation.variable_count,
            "feasible": classical_evaluation.feasibility.feasible,
            "routes": classical_routes,
            "full_penalized_energy": _text(classical_evaluation.full_penalized_energy),
            "business_objective": _text(classical_evaluation.business_metrics.weighted_objective),
            "optimality_gap_percent": _gap_percent(
                classical_evaluation.business_metrics.weighted_objective,
                feasible_business_optimum,
            ),
            "execution_time_seconds": classical_seconds,
            "timing_scope": "assign_routes call, including search, validation and objective calculation",
        }

    qaoa_results = []
    for result in report.runs:
        qaoa_results.append(
            {
                "solver": result.solver_id,
                "backend": result.backend_name,
                "backend_version": result.backend_version,
                "status": result.status,
                "variables": result.variable_count,
                "depth": result.qaoa_depth,
                "shots": result.shots,
                "seed": result.requested_seed,
                "seed_applied": result.seed_applied,
                "optimizer_iterations": result.optimizer_iterations,
                "feasible": result.best_sample_feasible,
                "full_penalized_energy": _text(result.best_sampled_energy),
                "business_objective": _text(result.business_objective),
                "decoded_solution": (
                    dict(result.decoded_solution)
                    if result.decoded_solution is not None
                    else None
                ),
                "optimality_gap_percent": _gap_percent(
                    result.business_objective,
                    feasible_business_optimum
                    if result.best_sample_feasible
                    else None,
                ),
                "feasible_sample_fraction": result.feasible_sample_fraction,
                "execution_time_seconds": result.execution_time_seconds,
                "optimization_time_seconds": result.optimization_time_seconds,
                "circuit_execution_time_seconds": result.circuit_execution_time_seconds,
                "timing_scope": result.timing_scope,
                "timing_note": (
                    "whole solver wall time includes optimization and sampling; optimizer wall time "
                    "overlaps sampling, and circuit time is accumulated sample-call time, so do not sum"
                ),
                "execution_metadata": (
                    dict(result.execution_metadata)
                    if result.execution_metadata is not None
                    else None
                ),
            }
        )

    return {
        "profile": name,
        "weights": {
            "cost": weights.cost,
            "delivery_time": weights.delivery_time,
            "carbon": weights.carbon,
            "resilience": weights.resilience,
        },
        "problem": {
            "synthetic": True,
            "scenario_id": formulation.scenario.id,
            "shipment_count": len(formulation.profiles),
            "candidate_count": sum(len(items) for items in formulation.candidates.values()),
            "decision_variables": formulation.decision_variable_count,
            "slack_variables": formulation.slack_variable_count,
            "binary_variables": formulation.variable_count,
            "variable_order": formulation.variable_order,
            "constant_offset": _text(formulation.offset),
            "penalty": _text(formulation.penalty),
            "reference_scope": "exact over the fixed generated candidate routes only",
        },
        "exact_reference": {
            "solver": exact.solver_id,
            "backend": exact.backend_name,
            "binary_variables": exact.variable_count,
            "status": exact.status,
            "feasible": exact.penalized_minimum_feasibility == "feasible",
            "penalized_minimum_feasible": exact.penalized_minimum_feasibility,
            "full_penalized_energy": _text(exact.penalized_model_minimum),
            "business_objective": _text(exact.best_feasible_business_objective),
            "best_feasible_full_energy": _text(exact.best_feasible_full_energy),
            "best_feasible_business_routes": exact_routes,
            "best_feasible_full_energy_routes": exact_energy_routes,
            "execution_time_seconds": exact.execution_time_seconds,
            "timing_scope": exact.timing_scope,
        },
        "classical_assignment": classical_result,
        "qaoa_runs": qaoa_results,
        "qaoa_summaries": [
            {
                "solver": summary.solver_id,
                "backend": summary.backend_name,
                "run_count": summary.run_count,
                "feasibility_rate": summary.feasibility_rate,
                "optimal_feasible_success_probability": summary.optimal_feasible_success_probability,
                "mean_feasible_sample_fraction": summary.mean_feasible_sample_fraction,
                "per_run_end_to_end_seconds": summary.per_run_execution_times_seconds,
                "aggregate_end_to_end_seconds": summary.aggregate_execution_time_seconds,
                "timing_scope": summary.timing_scope,
            }
            for summary in report.summaries
        ],
    }


def main() -> None:
    results = [
        benchmark_profile("balanced", ObjectiveWeights()),
        benchmark_profile(
            "carbon-priority",
            ObjectiveWeights(cost=0, delivery_time=0, carbon=100, resilience=0),
        ),
    ]
    print(json.dumps({"seeds": SEEDS, "results": results}, indent=2, default=str))


if __name__ == "__main__":
    main()
