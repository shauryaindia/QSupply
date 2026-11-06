"""Optional Qiskit SDK 2.x StatevectorSampler QAOA backend."""

from __future__ import annotations

from fractions import Fraction
import importlib
from importlib.metadata import PackageNotFoundError, version
from math import isclose, isfinite
from numbers import Real
from time import perf_counter
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from ..ising import IsingModel
from ..qaoa import (
    MAX_QAOA_DEPTH,
    MAX_QAOA_SHOTS,
    MAX_QAOA_VARIABLES,
    QAOAConfig,
    SampleBatch,
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


class QiskitUnavailableError(ImportError):
    """Raised when Qiskit execution is requested without the optional SDK."""


def _load_qiskit() -> tuple[Any, Any, Any]:
    try:
        qiskit = importlib.import_module("qiskit")
        circuit_module = importlib.import_module("qiskit.circuit")
        primitives = importlib.import_module("qiskit.primitives")
        sdk_version = version("qiskit")
        if sdk_version.split(".", maxsplit=1)[0] != "2":
            raise QiskitUnavailableError(
                f"QSupply requires Qiskit SDK 2.x; found {sdk_version}"
            )
        return (
            qiskit.QuantumCircuit,
            circuit_module.ParameterVector,
            primitives.StatevectorSampler,
        )
    except QiskitUnavailableError:
        raise
    except (ImportError, AttributeError, OSError, PackageNotFoundError) as error:
        raise QiskitUnavailableError(
            "Qiskit SDK 2.x is an optional dependency and is not installed"
        ) from error


class QiskitBackend:
    """Build canonical QAOA circuits and sample them with Qiskit V2 primitives.

    QSupply variable index ``i`` maps to Qiskit qubit ``i``. The single
    ``measure_all`` classical register prints the highest index on the left,
    so count strings are reversed by :func:`decode_qiskit_counts`.
    """

    name = "Qiskit StatevectorSampler (local state-vector simulator)"

    @staticmethod
    def is_available() -> bool:
        try:
            _load_qiskit()
        except QiskitUnavailableError:
            return False
        return True

    @staticmethod
    def version() -> str | None:
        try:
            return version("qiskit")
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
        if not isinstance(ising, IsingModel):
            raise TypeError("ising must be an IsingModel")
        if not 1 <= len(ising.variables) <= MAX_QAOA_VARIABLES:
            raise ValueError(f"Qiskit QAOA supports 1 to {MAX_QAOA_VARIABLES} variables")
        if len(gammas) != len(betas) or not 1 <= len(gammas) <= MAX_QAOA_DEPTH:
            raise ValueError(f"QAOA depth must be between 1 and {MAX_QAOA_DEPTH}")
        if (
            isinstance(shots, bool)
            or not isinstance(shots, int)
            or not 1 <= shots <= MAX_QAOA_SHOTS
        ):
            raise ValueError(f"shots must be between 1 and {MAX_QAOA_SHOTS}")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("seed must be an integer")

        started = perf_counter()
        circuit, parameters = build_qiskit_qaoa_circuit(ising, len(gammas))
        gamma_parameters, beta_parameters = parameters
        bindings = {
            **dict(zip(gamma_parameters, gammas, strict=True)),
            **dict(zip(beta_parameters, betas, strict=True)),
        }
        bound_circuit = circuit.assign_parameters(bindings)
        _, _, sampler_type = _load_qiskit()
        sampler = sampler_type(seed=seed)
        result = sampler.run([bound_circuit], shots=shots).result()
        counts = result[0].data.meas.get_counts()
        elapsed = perf_counter() - started
        return SampleBatch(
            decode_qiskit_counts(counts, len(ising.variables)), elapsed
        )

    def circuit_depth(self, ising: IsingModel, depth: int) -> int:
        circuit, _ = build_qiskit_qaoa_circuit(ising, depth)
        return circuit.remove_final_measurements(inplace=False).depth()


def build_qiskit_qaoa_circuit(
    ising: IsingModel, depth: int
) -> tuple[Any, tuple[tuple[Any, ...], tuple[Any, ...]]]:
    """Create a parameterized circuit for the shared canonical QAOA equations."""
    if not isinstance(ising, IsingModel):
        raise TypeError("ising must be an IsingModel")
    if not 1 <= len(ising.variables) <= MAX_QAOA_VARIABLES:
        raise ValueError(f"Qiskit QAOA supports 1 to {MAX_QAOA_VARIABLES} variables")
    if (
        isinstance(depth, bool)
        or not isinstance(depth, int)
        or not 1 <= depth <= MAX_QAOA_DEPTH
    ):
        raise ValueError(f"depth must be between 1 and {MAX_QAOA_DEPTH}")
    QuantumCircuit, ParameterVector, _ = _load_qiskit()
    qubit_count = len(ising.variables)
    gammas = ParameterVector("gamma", depth)
    betas = ParameterVector("beta", depth)
    circuit = QuantumCircuit(qubit_count)
    for index in range(qubit_count):
        circuit.h(index)

    coefficients = (*ising.linear.values(), *ising.quadratic.values())
    scale = max((abs(value) for value in coefficients), default=0) or 1
    indices = ising.variable_indices
    for layer in range(depth):
        for variable in ising.variables:
            coefficient = ising.linear[variable]
            angle_scale = float(Fraction(coefficient) / Fraction(scale))
            if angle_scale:
                circuit.rz(2 * gammas[layer] * angle_scale, indices[variable])
        for left_index, left in enumerate(ising.variables):
            for right in ising.variables[left_index + 1 :]:
                coefficient = ising.quadratic.get((left, right), 0)
                if coefficient:
                    circuit.rzz(
                        2
                        * gammas[layer]
                        * float(Fraction(coefficient) / Fraction(scale)),
                        indices[left],
                        indices[right],
                    )
        for index in range(qubit_count):
            circuit.rx(2 * betas[layer], index)
    circuit.measure_all()
    return circuit, (tuple(gammas), tuple(betas))


def decode_qiskit_counts(
    counts: dict[str, int], variable_count: int
) -> dict[tuple[int, ...], int]:
    """Decode Qiskit display-order bit strings into QSupply variable order."""
    if isinstance(variable_count, bool) or not isinstance(variable_count, int):
        raise TypeError("variable_count must be an integer")
    if variable_count < 0:
        raise ValueError("variable_count must be non-negative")
    if not isinstance(counts, dict):
        raise TypeError("counts must be a mapping of bitstrings to counts")
    decoded: dict[tuple[int, ...], int] = {}
    for raw, count in counts.items():
        if not isinstance(raw, str):
            raise TypeError("Qiskit count keys must be strings")
        compact = raw.replace(" ", "")
        if len(compact) != variable_count or any(bit not in "01" for bit in compact):
            raise ValueError("Qiskit bitstring has an invalid register width or value")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("Qiskit sample counts must be positive integers")
        bits = tuple(int(bit) for bit in reversed(compact))
        decoded[bits] = decoded.get(bits, 0) + count
    return decoded


class QiskitQAOASolver:
    """Common solver adapter that reuses QSupply's bounded QAOA optimizer."""

    def __init__(
        self,
        config: QAOAConfig | None = None,
        *,
        backend: QiskitBackend | None = None,
    ) -> None:
        self.config = config or QAOAConfig()
        if not isinstance(self.config, QAOAConfig):
            raise TypeError("config must be a QAOAConfig")
        self.backend = backend or QiskitBackend()

    @property
    def metadata(self) -> SolverMetadata:
        return SolverMetadata(
            solver_id="qiskit-qaoa",
            name="QAOA on Qiskit StatevectorSampler",
            version=QAOA_ALGORITHM_VERSION,
            backend_type=BackendType.SIMULATOR,
            supported_representations=frozenset({ProblemRepresentation.ISING}),
        )

    @classmethod
    def available(cls) -> bool:
        return QiskitBackend.is_available()

    def solve(self, request: SolverRequest) -> SolverResult:
        if not isinstance(request, SolverRequest):
            raise TypeError("request must be a SolverRequest")
        if request.representation is not ProblemRepresentation.ISING:
            raise ValueError("Qiskit QAOA requires an Ising SolverRequest")
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
            assignment = dict(zip(request.variable_order, execution.best_bits, strict=True))
            spins = {
                variable: 1 - 2 * assignment[variable]
                for variable in request.variable_order
            }
            qubo_energy = request.qubo.energy(assignment)
            full_energy = request.constant_offset + qubo_energy
            ising_energy = ising.energy(spins)
            if not _energy_equivalent(full_energy, ising_energy):
                raise ArithmeticError("measured sample QUBO and Ising energies disagree")
            feasible, details, decoded, objective, validation_error = _validate_solution(
                request, assignment
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
                run_id=str(uuid4()), solver_id=self.metadata.solver_id,
                solver_name=self.metadata.name, solver_version=self.metadata.version,
                backend_type=self.metadata.backend_type,
                representation=ProblemRepresentation.ISING,
                variable_order=request.variable_order,
                best_binary_assignment=assignment, best_spin_assignment=spins,
                solver_reported_energy=ising_energy, qubo_energy=qubo_energy,
                full_energy=full_energy, ising_energy=ising_energy,
                decoded_solution=decoded, business_objective=objective,
                feasible=feasible, feasibility_details=details,
                candidate_assignments_evaluated=sample_count,
                execution_time_seconds=perf_counter() - started,
                configuration=MappingProxyType(configuration),
                random_seed=config.random_seed, status=status,
                termination_reason=(
                    "optimizer completed and final measurement batch sampled"
                    if status is ExecutionStatus.COMPLETED else None
                ),
                error=validation_error, backend_name=self.backend.name,
                backend_version=self.backend.version(),
                algorithm_name="Quantum Approximate Optimization Algorithm",
                algorithm_version=QAOA_ALGORITHM_VERSION,
                sample_count=sample_count,
                sample_frequencies=execution.final_samples.counts,
                best_sample_frequency=execution.best_sample_frequency,
                average_sampled_energy=execution.average_sampled_energy,
                feasible_sample_rate=feasible_sample_rate,
                optimizer_iterations=execution.optimizer_iterations,
                circuit_depth=self.backend.circuit_depth(ising, config.depth),
                optimization_time_seconds=execution.optimization_time_seconds,
                circuit_execution_time_seconds=execution.circuit_execution_time_seconds,
            )
        except Exception as error:
            return self._failed_result(request, error, started)

    def _failed_result(
        self, request: SolverRequest, error: Exception, started: float
    ) -> SolverResult:
        config = self.config
        return SolverResult(
            run_id=str(uuid4()), solver_id=self.metadata.solver_id,
            solver_name=self.metadata.name, solver_version=self.metadata.version,
            backend_type=self.metadata.backend_type,
            representation=request.representation, variable_order=request.variable_order,
            best_binary_assignment=None, best_spin_assignment=None,
            solver_reported_energy=None, qubo_energy=None, full_energy=None,
            ising_energy=None, decoded_solution=None, business_objective=None,
            feasible=None, feasibility_details=(), candidate_assignments_evaluated=0,
            execution_time_seconds=perf_counter() - started,
            configuration=MappingProxyType({
                **dict(request.configuration), "depth": config.depth,
                "optimizer": config.optimizer, "max_iterations": config.max_iterations,
                "shots_per_evaluation": config.shots, "random_seed": config.random_seed,
                "max_variables": config.max_variables,
            }), random_seed=config.random_seed, status=ExecutionStatus.FAILED,
            error=f"{type(error).__name__}: {error}", backend_name=self.backend.name,
            backend_version=self.backend.version(),
            algorithm_name="Quantum Approximate Optimization Algorithm",
            algorithm_version=QAOA_ALGORITHM_VERSION, circuit_depth=None,
        )


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
            details = (
                (raw_details,)
                if isinstance(raw_details, str)
                else tuple(map(str, raw_details))
            )
        else:
            raise TypeError(
                "validator must return bool or an object with a feasible attribute"
            )
        decoded = None
        business = None
        if feasible and request.decoder is not None:
            decoded = MappingProxyType(
                dict(request.decoder(MappingProxyType(assignment)))
            )
            if request.business_objective is not None:
                business = request.business_objective(decoded)
                if isinstance(business, bool) or not isinstance(business, Real):
                    raise TypeError("business objective must be a real number")
                if not isfinite(business):
                    raise ValueError("business objective must be finite")
        return feasible, details, decoded, business, None
    except Exception as error:
        return None, (), None, None, f"{type(error).__name__}: {error}"


def _sample_feasibility_rate(request: SolverRequest, counts: Any) -> float | None:
    if request.validator is None:
        return None
    total = 0
    feasible = 0
    for bits, count in counts.items():
        assignment = dict(zip(request.variable_order, bits, strict=True))
        value = request.validator(MappingProxyType(assignment))
        if isinstance(value, bool):
            is_feasible = value
        elif hasattr(value, "feasible"):
            is_feasible = bool(value.feasible)
        else:
            raise TypeError(
                "validator must return bool or an object with a feasible attribute"
            )
        total += count
        if is_feasible:
            feasible += count
    return feasible / total if total else None
