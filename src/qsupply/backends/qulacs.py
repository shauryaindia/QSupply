"""Optional Qulacs circuit backend and QAOA solver adapter."""

from __future__ import annotations

import importlib
from importlib.metadata import PackageNotFoundError, version
from math import isclose
from time import perf_counter
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from ..ising import IsingModel
from ..qaoa import (
    MAX_QAOA_DEPTH,
    MAX_QAOA_ITERATIONS,
    MAX_QAOA_SHOTS,
    MAX_QAOA_VARIABLES,
    QAOAConfig,
    SampleBatch,
    build_qaoa_circuit_plan,
    run_qaoa,
)
from ..solver import (
    BackendType,
    ExecutionStatus,
    ProblemRepresentation,
    SolverMetadata,
    SolverRequest,
    SolverResult,
)


QAOA_ALGORITHM_VERSION = "1.0"


class QulacsUnavailableError(ImportError):
    """Raised when a Qulacs execution is requested without its optional package."""


class QulacsBackend:
    """Translate canonical QAOA rotations and sample Qulacs state vectors.

    Qulacs ``RX``, ``RZ`` and Pauli rotations implement ``exp(+i*theta*P/2)``.
    QSupply's shared plan uses ``exp(-i*theta*P/2)``, so this adapter negates
    rotation angles locally. See Qulacs' Python advanced guide for the SDK
    convention: https://docs.qulacs.org/en/latest/guide/2.0_python_advanced.html
    """

    name = "Qulacs state-vector simulator"

    @staticmethod
    def is_available() -> bool:
        try:
            importlib.import_module("qulacs")
        except (ImportError, OSError):
            return False
        return True

    @staticmethod
    def version() -> str | None:
        try:
            return version("qulacs")
        except PackageNotFoundError:
            return None

    def sample(
        self,
        ising: IsingModel,
        gammas: tuple[float, ...],
        betas: tuple[float, ...],
        shots: int,
        seed: int,
    ) -> SampleBatch:
        """Build, evolve and sample one real Qulacs circuit."""
        if not isinstance(ising, IsingModel):
            raise TypeError("ising must be an IsingModel")
        if not 1 <= len(ising.variables) <= MAX_QAOA_VARIABLES:
            raise ValueError(f"Qulacs QAOA supports 1 to {MAX_QAOA_VARIABLES} variables")
        if len(gammas) != len(betas) or not 1 <= len(gammas) <= MAX_QAOA_DEPTH:
            raise ValueError(f"QAOA depth must be between 1 and {MAX_QAOA_DEPTH}")
        if isinstance(shots, bool) or not isinstance(shots, int) or not 1 <= shots <= MAX_QAOA_SHOTS:
            raise ValueError(f"shots must be between 1 and {MAX_QAOA_SHOTS}")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("seed must be an integer")

        qulacs = _load_qulacs()
        started = perf_counter()
        plan = build_qaoa_circuit_plan(ising, gammas, betas)
        circuit = qulacs.QuantumCircuit(len(ising.variables))
        for operation in plan:
            _append_operation(circuit, operation)
        state = qulacs.QuantumState(len(ising.variables))
        circuit.update_quantum_state(state)
        raw_samples = state.sampling(shots, seed)

        # Qulacs returns each measurement as an integer whose bit i is qubit i.
        # QSupply register index i is the variable at Ising variable_order[i].
        counts = decode_qulacs_samples(raw_samples, len(ising.variables))
        elapsed = perf_counter() - started
        return SampleBatch(counts=counts, execution_time_seconds=elapsed)


class QulacsQAOASolver:
    """Common solver adapter that runs QAOA circuits using Qulacs sampling."""

    def __init__(
        self,
        config: QAOAConfig | None = None,
        *,
        backend: QulacsBackend | None = None,
    ) -> None:
        self.config = config or QAOAConfig()
        if not isinstance(self.config, QAOAConfig):
            raise TypeError("config must be a QAOAConfig")
        self.backend = backend or QulacsBackend()

    @property
    def metadata(self) -> SolverMetadata:
        return SolverMetadata(
            solver_id="qulacs-qaoa",
            name="QAOA on Qulacs",
            version=QAOA_ALGORITHM_VERSION,
            backend_type=BackendType.SIMULATOR,
            supported_representations=frozenset({ProblemRepresentation.ISING}),
        )

    @classmethod
    def available(cls) -> bool:
        return QulacsBackend.is_available()

    def solve(self, request: SolverRequest) -> SolverResult:
        """Run configured QAOA and independently validate its best sample."""
        if not isinstance(request, SolverRequest):
            raise TypeError("request must be a SolverRequest")
        if request.representation is not ProblemRepresentation.ISING:
            raise ValueError("Qulacs QAOA requires an Ising SolverRequest")
        if len(request.variable_order) > self.config.max_variables:
            raise ValueError(
                f"QAOA supports at most {self.config.max_variables} variables; "
                f"received {len(request.variable_order)}"
            )

        started = perf_counter()
        try:
            ising = request.ising_model
            assert ising is not None
            config = self.config
            if request.random_seed is not None and request.random_seed != config.random_seed:
                from dataclasses import replace

                config = replace(config, random_seed=request.random_seed)
            execution = run_qaoa(ising, self.backend.sample, config)
            bits = execution.best_bits
            assignment = dict(zip(request.variable_order, bits))
            spins = {variable: 1 - 2 * assignment[variable] for variable in request.variable_order}
            q_energy = request.qubo.energy(assignment)
            full_energy = request.constant_offset + q_energy
            ising_energy = ising.energy(spins)
            if not _energy_equivalent(full_energy, ising_energy):
                raise ArithmeticError("measured sample QUBO and Ising energies disagree")

            feasible, details, decoded, business_objective, validation_error = (
                _validate_solution(request, assignment)
            )
            feasible_sample_rate = _sample_feasibility_rate(
                request, execution.final_samples.counts
            )
            status = (
                ExecutionStatus.FAILED
                if validation_error is not None
                else ExecutionStatus.COMPLETED
            )
            sample_count = execution.optimizer_sample_count + execution.final_samples.shots
            configuration = {
                **dict(request.configuration),
                "depth": config.depth,
                "optimizer": config.optimizer,
                "max_iterations": config.max_iterations,
                "shots_per_evaluation": config.shots,
                "random_seed": config.random_seed,
                "max_variables": config.max_variables,
                "cost_normalization_scale": str(execution.cost_normalization_scale),
            }
            return SolverResult(
                run_id=str(uuid4()),
                solver_id=self.metadata.solver_id,
                solver_name=self.metadata.name,
                solver_version=self.metadata.version,
                backend_type=self.metadata.backend_type,
                representation=ProblemRepresentation.ISING,
                variable_order=request.variable_order,
                best_binary_assignment=assignment,
                best_spin_assignment=spins,
                solver_reported_energy=ising_energy,
                qubo_energy=q_energy,
                full_energy=full_energy,
                ising_energy=ising_energy,
                decoded_solution=decoded,
                business_objective=business_objective,
                feasible=feasible,
                feasibility_details=details,
                candidate_assignments_evaluated=sample_count,
                execution_time_seconds=perf_counter() - started,
                configuration=MappingProxyType(configuration),
                random_seed=config.random_seed,
                status=status,
                termination_reason=(
                    "optimizer completed and final measurement batch sampled"
                    if status is ExecutionStatus.COMPLETED
                    else None
                ),
                error=validation_error,
                backend_name=self.backend.name,
                backend_version=self.backend.version(),
                algorithm_name="Quantum Approximate Optimization Algorithm",
                algorithm_version=QAOA_ALGORITHM_VERSION,
                sample_count=sample_count,
                sample_frequencies=execution.final_samples.counts,
                best_sample_frequency=execution.best_sample_frequency,
                average_sampled_energy=execution.average_sampled_energy,
                feasible_sample_rate=feasible_sample_rate,
                optimizer_iterations=execution.optimizer_iterations,
                circuit_depth=config.depth,
                optimization_time_seconds=execution.optimization_time_seconds,
                circuit_execution_time_seconds=execution.circuit_execution_time_seconds,
            )
        except QulacsUnavailableError as error:
            return self._failed_result(request, error, started)
        except Exception as error:
            return self._failed_result(request, error, started)

    def _failed_result(
        self, request: SolverRequest, error: Exception, started: float
    ) -> SolverResult:
        config = self.config
        return SolverResult(
            run_id=str(uuid4()),
            solver_id=self.metadata.solver_id,
            solver_name=self.metadata.name,
            solver_version=self.metadata.version,
            backend_type=self.metadata.backend_type,
            representation=request.representation,
            variable_order=request.variable_order,
            best_binary_assignment=None,
            best_spin_assignment=None,
            solver_reported_energy=None,
            qubo_energy=None,
            full_energy=None,
            ising_energy=None,
            decoded_solution=None,
            business_objective=None,
            feasible=None,
            feasibility_details=(),
            candidate_assignments_evaluated=0,
            execution_time_seconds=perf_counter() - started,
            configuration=MappingProxyType(
                {
                    **dict(request.configuration),
                    "depth": config.depth,
                    "optimizer": config.optimizer,
                    "max_iterations": config.max_iterations,
                    "shots_per_evaluation": config.shots,
                    "random_seed": config.random_seed,
                    "max_variables": config.max_variables,
                }
            ),
            random_seed=config.random_seed,
            status=ExecutionStatus.FAILED,
            error=f"{type(error).__name__}: {error}",
            backend_name=self.backend.name,
            backend_version=self.backend.version(),
            algorithm_name="Quantum Approximate Optimization Algorithm",
            algorithm_version=QAOA_ALGORITHM_VERSION,
            circuit_depth=config.depth,
        )


def _append_operation(circuit: Any, operation: Any) -> None:
    if operation.gate == "h":
        circuit.add_H_gate(operation.qubits[0])
    elif operation.gate == "rz":
        assert operation.angle is not None
        circuit.add_RZ_gate(operation.qubits[0], -operation.angle)
    elif operation.gate == "rx":
        assert operation.angle is not None
        circuit.add_RX_gate(operation.qubits[0], -operation.angle)
    elif operation.gate == "rzz":
        assert operation.angle is not None
        control, target = operation.qubits
        # CNOT-RZ-CNOT realizes RZZ; negate the canonical angle because
        # Qulacs RZ(theta) = exp(+i*theta*Z/2).
        circuit.add_CNOT_gate(control, target)
        circuit.add_RZ_gate(target, -operation.angle)
        circuit.add_CNOT_gate(control, target)
    elif operation.gate == "cx":
        circuit.add_CNOT_gate(*operation.qubits)
    else:
        raise ValueError(f"unsupported QAOA gate {operation.gate!r}")


def decode_qulacs_samples(
    raw_samples: Any, variable_count: int
) -> dict[tuple[int, ...], int]:
    """Decode Qulacs integer samples with qubit 0 as the least-significant bit."""
    if isinstance(variable_count, bool) or not isinstance(variable_count, int):
        raise TypeError("variable_count must be an integer")
    if variable_count < 0:
        raise ValueError("variable_count must be non-negative")
    counts: dict[tuple[int, ...], int] = {}
    for raw in raw_samples:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise TypeError("Qulacs samples must be non-negative integers")
        if raw < 0 or raw >= 1 << variable_count:
            raise ValueError("Qulacs sample is outside the requested register width")
        bits = tuple((raw >> index) & 1 for index in range(variable_count))
        counts[bits] = counts.get(bits, 0) + 1
    return counts


def _load_qulacs() -> Any:
    try:
        return importlib.import_module("qulacs")
    except (ImportError, OSError) as error:
        raise QulacsUnavailableError(
            "Qulacs is optional and is not installed; install requirements-quantum.txt"
        ) from error


def _energy_equivalent(left: Any, right: Any) -> bool:
    if isinstance(left, float) or isinstance(right, float):
        return isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
    return left == right


def _validate_solution(request: SolverRequest, assignment: dict[str, int]):
    if request.validator is None:
        return None, (), None, None, None
    try:
        validation = request.validator(MappingProxyType(assignment))
        if isinstance(validation, bool):
            feasible = validation
            details: tuple[str, ...] = ()
        elif hasattr(validation, "feasible"):
            feasible = bool(validation.feasible)
            raw_details = getattr(validation, "violations", ())
            details = (raw_details,) if isinstance(raw_details, str) else tuple(map(str, raw_details))
        else:
            raise TypeError("validator must return bool or an object with a feasible attribute")
        decoded = None
        business = None
        if feasible and request.decoder is not None:
            decoded = MappingProxyType(dict(request.decoder(MappingProxyType(assignment))))
            if request.business_objective is not None:
                business = request.business_objective(decoded)
                from math import isfinite
                from numbers import Real

                if isinstance(business, bool) or not isinstance(business, Real):
                    raise TypeError("business objective must be a real number")
                if not isfinite(business):
                    raise ValueError("business objective must be finite")
        return feasible, details, decoded, business, None
    except Exception as error:
        return None, (), None, None, f"{type(error).__name__}: {error}"


def _sample_feasibility_rate(
    request: SolverRequest, counts: Any
) -> float | None:
    if request.validator is None:
        return None
    total = sum(counts.values())
    feasible_count = 0
    for bits, count in counts.items():
        assignment = dict(zip(request.variable_order, bits))
        validation = request.validator(MappingProxyType(assignment))
        if isinstance(validation, bool):
            feasible = validation
        elif hasattr(validation, "feasible"):
            feasible = bool(validation.feasible)
        else:
            raise TypeError(
                "validator must return bool or an object with a feasible attribute"
            )
        if feasible:
            feasible_count += count
    return feasible_count / total
