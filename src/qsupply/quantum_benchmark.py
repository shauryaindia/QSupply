"""Comparable exact and QAOA benchmark records for one QUBO instance.

The legacy ``exact_optimum`` field means the global minimum of the penalized
QUBO objective. It is not necessarily a feasible business solution. Feasible
references are reported separately after exhaustive domain validation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import product
from math import isfinite, isqrt
from numbers import Rational, Real
from statistics import fmean, median, pstdev
from types import MappingProxyType
from time import perf_counter
from typing import Any, Mapping, Sequence

from .execution import ExecutionMetadata
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
    """One exact or QAOA run, retaining legacy fields and explicit references."""

    problem_id: str
    solver_id: str
    backend_name: str
    backend_version: str | None
    backend_type: BackendType
    variable_count: int
    qaoa_depth: int | None
    shots: int | None
    optimizer_iterations: int | None
    random_seed: int | None
    exact_optimum: Real | None
    best_sampled_energy: Real | None
    absolute_energy_gap: Real | None
    relative_energy_gap_percent: float | None
    feasible_sample_fraction: float | None
    best_sample_feasible: bool | None
    business_objective: Real | None
    circuit_depth: int | None
    execution_time_seconds: float | None
    execution_mode: str
    status: str
    penalized_model_minimum: Real | None = None
    penalized_minimum_feasibility: str = "unknown"
    best_feasible_full_energy: Real | None = None
    best_feasible_business_objective: Real | None = None
    best_feasible_full_energy_assignment: Mapping[str, int] | None = None
    best_feasible_business_assignment: Mapping[str, int] | None = None
    feasibility_status: str = "unknown"
    gap_reference: str = "penalized_qubo_minimum"
    execution_mode_detail: str | None = None
    execution_mode_source: str = "legacy_backend_type_category"
    timing_scope: str = "whole solver call (per run)"
    feasible_reference_enumeration_time_seconds: float | None = None
    execution_metadata: Mapping[str, object] | None = None
    requested_seed: int | None = None
    seed_applied: bool | None = None
    run_index: int | None = None
    optimization_time_seconds: float | None = None
    circuit_execution_time_seconds: float | None = None
    decoded_solution: Mapping[str, Any] | None = None
    best_binary_assignment: Mapping[str, int] | None = None
    qubo_energy: Real | None = None
    ising_energy: Real | None = None
    optimizer_evaluations: int | None = None


@dataclass(frozen=True)
class ObjectiveStatistics:
    """Descriptive statistics over the objective values that were available."""

    metric: str
    count: int
    best: Real | None
    worst: Real | None
    mean: float | None
    median: float | None
    standard_deviation: float | None
    mean_exact: Rational | None = None
    median_exact: Rational | None = None
    variance_exact: Rational | None = None
    standard_deviation_exact: Rational | None = None


@dataclass(frozen=True)
class QuantumBenchmarkSummary:
    """Aggregate descriptive results for independent runs of one solver."""

    solver_id: str
    backend_name: str
    backend_version: str | None
    backend_type: BackendType
    run_count: int
    objective_statistics: ObjectiveStatistics
    full_energy_statistics: ObjectiveStatistics
    business_objective_statistics: ObjectiveStatistics
    feasibility_evaluated_run_count: int
    seeded_run_count: int
    feasibility_rate: float | None
    optimal_feasible_success_probability: float | None
    mean_feasible_sample_fraction: float | None
    per_run_execution_times_seconds: tuple[float, ...]
    aggregate_execution_time_seconds: float | None
    timing_scope: str
    execution_metadata: tuple[Mapping[str, object] | None, ...]


@dataclass(frozen=True)
class QuantumBenchmarkReport:
    """Exact reference, individual seeded runs and per-backend summaries."""

    exact_reference: QuantumBenchmarkRecord
    runs: tuple[QuantumBenchmarkRecord, ...]
    summaries: tuple[QuantumBenchmarkSummary, ...]


@dataclass(frozen=True)
class _FeasibleReference:
    full_energy: Real | None
    business_objective: Real | None
    full_energy_assignment: Mapping[str, int] | None
    business_assignment: Mapping[str, int] | None


def benchmark_qaoa_backends(
    problem_id: str,
    request: SolverRequest,
    solvers: Sequence[Solver],
    *,
    exact_solver: ExactQUBOSolver | None = None,
) -> tuple[QuantumBenchmarkRecord, ...]:
    """Run one exact reference and each selected QAOA adapter once.

    The legacy ``exact_optimum`` and gap fields refer to the penalized QUBO
    minimum. ``penalized_minimum_feasibility`` makes clear whether that minimum
    passes the original domain validator. ``best_feasible_*`` are computed by
    exhaustive validation over the same assignment space. Timing is one whole
    solver-call measurement per row, not a performance claim.
    """
    _validate_inputs(problem_id, request, solvers)
    exact = (exact_solver or ExactQUBOSolver()).solve(request)
    reference_started = perf_counter()
    feasible_reference = _best_feasible_reference(request)
    reference_elapsed = (
        perf_counter() - reference_started if request.validator is not None else None
    )
    return _records_for_runs(
        problem_id,
        request,
        solvers,
        exact,
        feasible_reference,
        (request.random_seed,),
        feasible_reference_enumeration_seconds=reference_elapsed,
    )


def benchmark_qaoa_backends_repeated(
    problem_id: str,
    request: SolverRequest,
    solvers: Sequence[Solver],
    *,
    seeds: Sequence[int],
    record_backend_exceptions: bool = False,
    stop_backend_on_failure: bool = False,
    exact_solver: ExactQUBOSolver | None = None,
) -> QuantumBenchmarkReport:
    """Run independent solver trials with explicit per-run seeds.

    The exact reference is evaluated once. Each QAOA adapter receives each
    seed in order via ``SolverRequest.random_seed``. The reported success
    probability is the empirical fraction of seed-confirmed runs whose
    returned best assignment is feasible and matches the best feasible
    reference objective; it is not a hardware or population-level performance
    claim. If an adapter does not report the requested seed as applied, this
    probability is unavailable. With record_backend_exceptions enabled, raised
    solver errors become failed trials. stop_backend_on_failure leaves later
    seeds for that solver unexecuted and explicitly marked not_run.
    """
    _validate_inputs(problem_id, request, solvers)
    if isinstance(seeds, (str, bytes)) or not isinstance(seeds, Sequence) or not seeds:
        raise ValueError("seeds must be a non-empty sequence of explicit integers")
    if any(isinstance(seed, bool) or not isinstance(seed, int) for seed in seeds):
        raise TypeError("every seed must be an integer")
    if len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be unique to represent independent runs")
    solver_ids = [solver.metadata.solver_id for solver in solvers]
    if len(set(solver_ids)) != len(solver_ids):
        raise ValueError(
            "solver IDs must be unique in repeated benchmarks so summaries remain distinct"
        )

    exact = (exact_solver or ExactQUBOSolver()).solve(request)
    reference_started = perf_counter()
    feasible_reference = _best_feasible_reference(request)
    reference_elapsed = (
        perf_counter() - reference_started if request.validator is not None else None
    )
    exact_record = _exact_record(
        problem_id, request, exact, feasible_reference, reference_elapsed
    )
    all_runs: list[QuantumBenchmarkRecord] = []
    stopped_solvers: set[str] = set()
    for run_index, seed in enumerate(seeds, start=1):
        seeded_request = replace(request, random_seed=seed)
        batch = _records_for_runs(
            problem_id,
            seeded_request,
            solvers,
            exact,
            feasible_reference,
            (seed,),
            include_exact=False,
            run_index=run_index,
            stopped_solvers=stopped_solvers,
            record_backend_exceptions=record_backend_exceptions or stop_backend_on_failure,
            feasible_reference_enumeration_seconds=reference_elapsed,
        )
        all_runs.extend(batch)
        if stop_backend_on_failure:
            stopped_solvers.update(record.solver_id for record in batch if record.status == "failed")
    summaries = tuple(
        _summarize(
            solver,
            tuple(record for record in all_runs if record.solver_id == solver.metadata.solver_id),
            request,
            feasible_reference,
        )
        for solver in solvers
    )
    return QuantumBenchmarkReport(exact_record, tuple(all_runs), summaries)


def _validate_inputs(problem_id: str, request: SolverRequest, solvers: Sequence[Solver]) -> None:
    if not isinstance(problem_id, str) or not problem_id.strip():
        raise ValueError("problem_id must be a non-empty string")
    if not isinstance(request, SolverRequest):
        raise TypeError("request must be a SolverRequest")
    if request.representation is not ProblemRepresentation.QUBO:
        raise ValueError("benchmark source request must use the QUBO representation")
    if isinstance(solvers, (str, bytes)) or not isinstance(solvers, Sequence):
        raise TypeError("solvers must be a sequence of QAOA solver adapters")
    for solver in solvers:
        if not isinstance(solver, Solver):
            raise TypeError("every solver must implement metadata and solve(request)")
        if ProblemRepresentation.ISING not in solver.metadata.supported_representations:
            raise ValueError(f"solver {solver.metadata.solver_id!r} must support Ising input")


def _records_for_runs(
    problem_id: str,
    request: SolverRequest,
    solvers: Sequence[Solver],
    exact: Any,
    feasible_reference: _FeasibleReference,
    seeds: tuple[int | None, ...],
    *,
    include_exact: bool = True,
    stopped_solvers: set[str] | None = None,
    record_backend_exceptions: bool = False,
    run_index: int | None = None,
    feasible_reference_enumeration_seconds: float | None = None,
) -> tuple[QuantumBenchmarkRecord, ...]:
    records: list[QuantumBenchmarkRecord] = []
    if include_exact:
        records.append(_exact_record(
            problem_id, request, exact, feasible_reference,
            feasible_reference_enumeration_seconds,
        ))
    for solver in solvers:
        ising_request = SolverRequest(
            qubo=request.qubo,
            constant_offset=request.constant_offset,
            representation=ProblemRepresentation.ISING,
            ising_model=qubo_to_ising(request.qubo, offset=request.constant_offset),
            validator=request.validator,
            decoder=request.decoder,
            business_objective=request.business_objective,
            configuration=request.configuration,
            random_seed=seeds[0],
        )
        failure_details = None
        elapsed = None
        if stopped_solvers and solver.metadata.solver_id in stopped_solvers:
            status = "not_run"
            failure_details = {"reason": "backend stopped after an earlier failed trial"}
        else:
            started = perf_counter()
            try:
                result = solver.solve(ising_request)
            except Exception as error:
                if not record_backend_exceptions:
                    raise
                elapsed = perf_counter() - started
                status = "failed"
                failure_details = {"error_type": type(error).__name__, "error": str(error)}
        if failure_details is not None:
            metadata = solver.metadata
            records.append(QuantumBenchmarkRecord(
                problem_id=problem_id, solver_id=metadata.solver_id, backend_name=metadata.name,
                backend_version=None, backend_type=metadata.backend_type,
                variable_count=len(request.variable_order), qaoa_depth=None, shots=None,
                optimizer_iterations=None, random_seed=None, exact_optimum=exact.full_energy,
                best_sampled_energy=None, absolute_energy_gap=None, relative_energy_gap_percent=None,
                feasible_sample_fraction=None, best_sample_feasible=None, business_objective=None,
                circuit_depth=None, execution_time_seconds=elapsed, execution_mode=_execution_mode(metadata.backend_type),
                status=status, requested_seed=seeds[0], run_index=run_index,
                timing_scope="not measured" if elapsed is None else "whole solver call (per run)",
                penalized_model_minimum=exact.full_energy,
                penalized_minimum_feasibility=_feasibility_status(exact.feasible),
                best_feasible_business_objective=feasible_reference.business_objective,
                best_feasible_full_energy=feasible_reference.full_energy,
                execution_metadata=MappingProxyType(failure_details),
            ))
            continue
        energy = result.full_energy
        exact_energy = exact.full_energy
        absolute_gap: Real | None = None
        relative_gap: float | None = None
        if exact_energy is not None and energy is not None:
            absolute_gap = energy - exact_energy
            if exact_energy != 0:
                relative_gap = float(absolute_gap / abs(exact_energy) * 100)
        configuration: dict[str, Any] = dict(result.configuration)
        metadata = result.execution_metadata
        details = metadata.as_dict() if metadata is not None else {}
        if result.error:
            details["error"] = result.error
        records.append(
            QuantumBenchmarkRecord(
                problem_id=problem_id,
                solver_id=result.solver_id,
                backend_name=result.backend_name or result.solver_name,
                backend_version=result.backend_version,
                backend_type=result.backend_type,
                variable_count=len(result.variable_order),
                qaoa_depth=_optional_int(configuration.get("depth")),
                shots=_optional_int(configuration.get("shots_per_evaluation")),
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
                penalized_model_minimum=exact_energy,
                penalized_minimum_feasibility=_feasibility_status(exact.feasible),
                best_feasible_full_energy=feasible_reference.full_energy,
                best_feasible_business_objective=feasible_reference.business_objective,
                best_feasible_full_energy_assignment=feasible_reference.full_energy_assignment,
                best_feasible_business_assignment=feasible_reference.business_assignment,
                feasibility_status=_feasibility_status(result.feasible),
                execution_mode_detail=(
                    metadata.execution_mode.value if metadata is not None else None
                ),
                execution_mode_source=(
                    "execution_metadata" if metadata is not None
                    else "legacy_backend_type_category"
                ),
                timing_scope="whole solver call (per run)",
                feasible_reference_enumeration_time_seconds=feasible_reference_enumeration_seconds,
                execution_metadata=MappingProxyType(details) if details else None,
                requested_seed=seeds[0],
                seed_applied=(
                    result.random_seed == seeds[0] if seeds[0] is not None else None
                ),
                run_index=run_index,
                optimization_time_seconds=result.optimization_time_seconds,
                circuit_execution_time_seconds=result.circuit_execution_time_seconds,
                decoded_solution=result.decoded_solution,
                best_binary_assignment=result.best_binary_assignment,
                qubo_energy=result.qubo_energy,
                ising_energy=result.ising_energy,
                optimizer_evaluations=_optional_int(configuration.get("optimizer_evaluations")),
            )
        )
    return tuple(records)


def _exact_record(
    problem_id: str,
    request: SolverRequest,
    exact: Any,
    feasible_reference: _FeasibleReference,
    feasible_reference_enumeration_seconds: float | None,
) -> QuantumBenchmarkRecord:
    energy = exact.full_energy
    return QuantumBenchmarkRecord(
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
        exact_optimum=energy,
        best_sampled_energy=energy,
        absolute_energy_gap=0 if energy is not None else None,
        relative_energy_gap_percent=0.0 if energy not in (None, 0) else None,
        feasible_sample_fraction=None,
        best_sample_feasible=exact.feasible,
        business_objective=exact.business_objective,
        circuit_depth=None,
        execution_time_seconds=exact.execution_time_seconds,
        execution_mode="classical exact enumeration",
        status=exact.status.value,
        penalized_model_minimum=energy,
        penalized_minimum_feasibility=_feasibility_status(exact.feasible),
        best_feasible_full_energy=feasible_reference.full_energy,
        best_feasible_business_objective=feasible_reference.business_objective,
        best_feasible_full_energy_assignment=feasible_reference.full_energy_assignment,
        best_feasible_business_assignment=feasible_reference.business_assignment,
        feasibility_status=_feasibility_status(exact.feasible),
        execution_mode_detail="classical_exact_enumeration",
        execution_mode_source="exact_solver_kind",
        timing_scope="whole exact solver call (single measurement)",
        feasible_reference_enumeration_time_seconds=feasible_reference_enumeration_seconds,
        requested_seed=request.random_seed,
        decoded_solution=exact.decoded_solution,
        best_binary_assignment=exact.best_binary_assignment,
        qubo_energy=exact.qubo_energy,
        ising_energy=exact.ising_energy,
    )


def _best_feasible_reference(request: SolverRequest) -> _FeasibleReference:
    """Return min feasible full energy and min feasible business objective.

    If domain validation is not supplied, feasibility is unknown and no
    feasible reference is claimed. Callback failures are surfaced rather than
    converted into a fabricated reference.
    """
    if request.validator is None:
        return _FeasibleReference(None, None, None, None)
    best_energy: Real | None = None
    best_business: Real | None = None
    best_energy_assignment: Mapping[str, int] | None = None
    best_business_assignment: Mapping[str, int] | None = None
    for bits in product((0, 1), repeat=len(request.variable_order)):
        assignment = dict(zip(request.variable_order, bits))
        validation = request.validator(MappingProxyType(assignment))
        feasible = _validation_is_feasible(validation)
        if not feasible:
            continue
        decoded: dict[str, Any] | None = None
        business: Real | None = None
        if request.decoder is not None:
            decoded = dict(request.decoder(MappingProxyType(assignment)))
        if request.business_objective is not None:
            if decoded is None:
                raise ValueError("business objective reference requires a decoded solution")
            business = request.business_objective(decoded)
            if isinstance(business, bool) or not isinstance(business, Real) or not isfinite(business):
                raise ValueError("business objective callback must return a finite real number")
            if best_business is None or business < best_business:
                best_business = business
                best_business_assignment = MappingProxyType(dict(assignment))
        full_energy = request.constant_offset + request.qubo.energy(assignment)
        if best_energy is None or full_energy < best_energy:
            best_energy = full_energy
            best_energy_assignment = MappingProxyType(dict(assignment))
    return _FeasibleReference(
        best_energy,
        best_business,
        best_energy_assignment,
        best_business_assignment,
    )


def _validation_is_feasible(validation: Any) -> bool:
    if isinstance(validation, bool):
        return validation
    if hasattr(validation, "feasible"):
        return bool(validation.feasible)
    raise TypeError("validator must return bool or an object with a feasible attribute")


def optimal_feasible_rate(reference: Real | None,
                          trials: Sequence[tuple[bool | None, bool, Real | None]]) -> float | None:
    """Fraction of all requested trials returning a validated exact match.

    Each trial supplies seed confirmation, completed-and-feasible status, and
    independently scored objective. Missing references or seed evidence give null.
    """
    if reference is None or not trials or any(seed is not True for seed, _, _ in trials):
        return None
    return sum(valid and value == reference for _, valid, value in trials) / len(trials)


def _summarize(solver: Solver, runs: tuple[QuantumBenchmarkRecord, ...], request: SolverRequest,
               feasible_reference: _FeasibleReference) -> QuantumBenchmarkSummary:
    use_business = request.business_objective is not None
    values = [
        run.business_objective if use_business else run.best_sampled_energy
        for run in runs
    ]
    present = [value for value in values if value is not None]
    metric = "business_objective (feasible runs only)" if use_business else "full_penalized_energy"
    stats = _objective_statistics(metric, present)
    energy_stats = _objective_statistics(
        "full_penalized_energy",
        [run.best_sampled_energy for run in runs if run.best_sampled_energy is not None],
    )
    business_stats = _objective_statistics(
        "business_objective (feasible runs only)",
        [run.business_objective for run in runs if run.business_objective is not None],
    )
    known = [run for run in runs if run.feasibility_status != "unknown"]
    feasibility_rate = (
        sum(run.feasibility_status == "feasible" for run in known) / len(known)
        if known else None
    )
    reference = feasible_reference.business_objective if use_business else feasible_reference.full_energy
    optimal_success = optimal_feasible_rate(reference, [
        (run.seed_applied, run.status == "completed" and run.best_sample_feasible is True, value)
        for run, value in zip(runs, values, strict=True)
    ])
    fractions = [run.feasible_sample_fraction for run in runs if run.feasible_sample_fraction is not None]
    times = tuple(run.execution_time_seconds for run in runs if run.execution_time_seconds is not None)
    return QuantumBenchmarkSummary(
        solver_id=solver.metadata.solver_id,
        backend_name=runs[0].backend_name if runs else solver.metadata.name,
        backend_version=runs[0].backend_version if runs else solver.metadata.version,
        backend_type=solver.metadata.backend_type,
        run_count=len(runs),
        objective_statistics=stats,
        full_energy_statistics=energy_stats,
        business_objective_statistics=business_stats,
        feasibility_evaluated_run_count=len(known),
        seeded_run_count=sum(run.seed_applied is True for run in runs),
        feasibility_rate=feasibility_rate,
        optimal_feasible_success_probability=optimal_success,
        mean_feasible_sample_fraction=(float(fmean(fractions)) if fractions else None),
        per_run_execution_times_seconds=times,
        aggregate_execution_time_seconds=sum(times) if times else None,
        timing_scope="per-run whole solver call; aggregate is the sum of run wall times",
        execution_metadata=tuple(run.execution_metadata for run in runs),
    )


def _feasibility_status(value: bool | None) -> str:
    return "feasible" if value is True else "infeasible" if value is False else "unknown"


def _objective_statistics(metric: str, values: Sequence[Real]) -> ObjectiveStatistics:
    if not values:
        return ObjectiveStatistics(metric, 0, None, None, None, None, None)
    exact_values = (
        [Fraction(value) for value in values]
        if all(isinstance(value, Rational) for value in values)
        else None
    )
    exact_mean: Rational | None = None
    exact_median: Rational | None = None
    exact_variance: Rational | None = None
    exact_std: Rational | None = None
    if exact_values is not None:
        exact_mean = sum(exact_values, Fraction()) / len(exact_values)
        ordered = sorted(exact_values)
        middle = len(ordered) // 2
        exact_median = (
            ordered[middle]
            if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2
        )
        exact_variance = sum(
            ((value - exact_mean) ** 2 for value in exact_values), Fraction()
        ) / len(exact_values)
        numerator_root = isqrt(exact_variance.numerator)
        denominator_root = isqrt(exact_variance.denominator)
        if (
            numerator_root * numerator_root == exact_variance.numerator
            and denominator_root * denominator_root == exact_variance.denominator
        ):
            exact_std = Fraction(numerator_root, denominator_root)

    # Keep the legacy float fields for callers and API compatibility; exact
    # rational companions above avoid discarding precision for integer/Fraction data.
    # Extremely large exact values can exceed the legacy fields' float range.
    try:
        floats = [float(value) for value in values]
        legacy_mean = float(fmean(floats))
        legacy_median = float(median(floats))
        legacy_std = float(pstdev(floats))
        if not all(isfinite(value) for value in (*floats, legacy_mean, legacy_median, legacy_std)):
            legacy_mean = legacy_median = legacy_std = None
    except (OverflowError, ValueError):
        legacy_mean = legacy_median = legacy_std = None
    return ObjectiveStatistics(
        metric=metric,
        count=len(values),
        best=min(values),
        worst=max(values),
        mean=legacy_mean,
        median=legacy_median,
        standard_deviation=legacy_std,
        mean_exact=exact_mean,
        median_exact=exact_median,
        variance_exact=exact_variance,
        standard_deviation_exact=exact_std,
    )


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _execution_mode(backend_type: BackendType) -> str:
    if backend_type is BackendType.SIMULATOR:
        return "local simulator execution"
    if backend_type is BackendType.QUANTUM:
        return "quantum backend execution"
    return "classical solver execution"
