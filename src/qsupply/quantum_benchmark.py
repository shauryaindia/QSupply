"""Comparable local exact and QAOA benchmark records for one QUBO instance."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Any, Sequence

from .ising import qubo_to_ising
from .solver import (
    BackendType,
    ExactQUBOSolver,
    ProblemRepresentation,
    Solver,
    SolverRequest,
)


@dataclass(frozen=True)
class QuantumBenchmarkRecord:
    """One method's result against the same full-energy exact reference."""

    problem_id: str
    solver_id: str
    backend_name: str
    backend_version: str | None
    backend_type: BackendType
    variable_count: int
    qaoa_depth: int | None
    shots: int | None
    optimizer_iterations: int
    random_seed: int | None
    exact_optimum: Real | None
    best_sampled_energy: Real | None
    absolute_energy_gap: Real | None
    relative_energy_gap_percent: float | None
    feasible_sample_fraction: float | None
    best_sample_feasible: bool | None
    business_objective: Real | None
    circuit_depth: int | None
    execution_time_seconds: float
    execution_mode: str
    status: str


def benchmark_qaoa_backends(
    problem_id: str,
    request: SolverRequest,
    solvers: Sequence[Solver],
    *,
    exact_solver: ExactQUBOSolver | None = None,
) -> tuple[QuantumBenchmarkRecord, ...]:
    """Run the exact reference and selected QAOA adapters on one QUBO problem.

    The QUBO, full energy offset, validator, decoder and business objective are
    preserved for every solver. QAOA adapters receive the mathematically
    equivalent Ising representation. Timing is whole-call wall time and should
    be read as one local measurement, not a statistical performance claim.
    """
    if not isinstance(problem_id, str) or not problem_id.strip():
        raise ValueError("problem_id must be a non-empty string")
    if not isinstance(request, SolverRequest):
        raise TypeError("request must be a SolverRequest")
    if request.representation is not ProblemRepresentation.QUBO:
        raise ValueError("benchmark source request must use the QUBO representation")
    if isinstance(solvers, (str, bytes)) or not isinstance(solvers, Sequence):
        raise TypeError("solvers must be a sequence of QAOA solver adapters")

    reference_solver = exact_solver or ExactQUBOSolver()
    exact = reference_solver.solve(request)
    records = [
        QuantumBenchmarkRecord(
            problem_id=problem_id,
            solver_id=exact.solver_id,
            backend_name=exact.solver_name,
            backend_version=exact.solver_version,
            backend_type=exact.backend_type,
            variable_count=len(request.variable_order),
            qaoa_depth=None,
            shots=None,
            optimizer_iterations=0,
            random_seed=exact.random_seed,
            exact_optimum=exact.full_energy,
            best_sampled_energy=exact.full_energy,
            absolute_energy_gap=0,
            relative_energy_gap_percent=0.0,
            feasible_sample_fraction=(
                1.0 if exact.feasible is True else 0.0 if exact.feasible is False else None
            ),
            best_sample_feasible=exact.feasible,
            business_objective=exact.business_objective,
            circuit_depth=None,
            execution_time_seconds=exact.execution_time_seconds,
            execution_mode="classical exact enumeration",
            status=exact.status.value,
        )
    ]
    ising_request = SolverRequest(
        qubo=request.qubo,
        constant_offset=request.constant_offset,
        representation=ProblemRepresentation.ISING,
        ising_model=qubo_to_ising(request.qubo, offset=request.constant_offset),
        validator=request.validator,
        decoder=request.decoder,
        business_objective=request.business_objective,
        configuration=request.configuration,
        random_seed=request.random_seed,
    )
    for solver in solvers:
        if not isinstance(solver, Solver):
            raise TypeError("every solver must implement metadata and solve(request)")
        if ProblemRepresentation.ISING not in solver.metadata.supported_representations:
            raise ValueError(f"solver {solver.metadata.solver_id!r} must support Ising input")
        result = solver.solve(ising_request)
        exact_energy = exact.full_energy
        energy = result.full_energy
        absolute_gap: Real | None = None
        relative_gap: float | None = None
        if exact_energy is not None and energy is not None:
            absolute_gap = energy - exact_energy
            if exact_energy != 0:
                relative_gap = float(absolute_gap / abs(exact_energy) * 100)
        configuration: dict[str, Any] = dict(result.configuration)
        qaoa_depth = _optional_int(configuration.get("depth"))
        shots = _optional_int(configuration.get("shots_per_evaluation"))
        records.append(
            QuantumBenchmarkRecord(
                problem_id=problem_id,
                solver_id=result.solver_id,
                backend_name=result.backend_name or result.solver_name,
                backend_version=result.backend_version,
                backend_type=result.backend_type,
                variable_count=len(result.variable_order),
                qaoa_depth=qaoa_depth,
                shots=shots,
                optimizer_iterations=result.optimizer_iterations,
                random_seed=result.random_seed,
                exact_optimum=exact_energy,
                best_sampled_energy=energy,
                absolute_energy_gap=absolute_gap,
                relative_energy_gap_percent=relative_gap,
                feasible_sample_fraction=result.feasible_sample_rate,
                best_sample_feasible=result.feasible,
                business_objective=result.business_objective,
                circuit_depth=result.circuit_depth,
                execution_time_seconds=result.execution_time_seconds,
                execution_mode=_execution_mode(result.backend_type),
                status=result.status.value,
            )
        )
    return tuple(records)


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _execution_mode(backend_type: BackendType) -> str:
    if backend_type is BackendType.SIMULATOR:
        return "local simulator execution"
    if backend_type is BackendType.QUANTUM:
        return "quantum backend execution"
    return "classical solver execution"
