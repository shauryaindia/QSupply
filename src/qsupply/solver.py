"""Backend-independent QUBO solver contracts and exact reference execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from itertools import product
from math import isclose, isfinite
from numbers import Real
from time import perf_counter
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from .ising import IsingModel, qubo_to_ising
from .qubo import QUBO


class BackendType(str, Enum):
    """Execution environment category, independent of a vendor SDK."""

    CLASSICAL = "classical"
    SIMULATOR = "simulator"
    QUANTUM = "quantum"


class ProblemRepresentation(str, Enum):
    """Mathematical representation accepted by a solver adapter."""

    QUBO = "qubo"
    ISING = "ising"


class ExecutionStatus(str, Enum):
    """Terminal status for a solver request."""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class SolverMetadata:
    """Stable descriptive metadata exposed by every solver implementation."""

    solver_id: str
    name: str
    version: str
    backend_type: BackendType
    supported_representations: frozenset[ProblemRepresentation]

    def __post_init__(self) -> None:
        for field_name in ("solver_id", "name", "version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.backend_type, BackendType):
            raise TypeError("backend_type must be a BackendType")
        try:
            representations = frozenset(self.supported_representations)
        except TypeError as error:
            raise TypeError("supported_representations must be iterable") from error
        if not representations or any(
            not isinstance(item, ProblemRepresentation) for item in representations
        ):
            raise ValueError("supported_representations must contain representations")
        object.__setattr__(self, "supported_representations", representations)


Validator = Callable[[Mapping[str, int]], bool | Any]
Decoder = Callable[[Mapping[str, int]], Mapping[str, Any]]
BusinessObjective = Callable[[Mapping[str, Any]], Real]


@dataclass(frozen=True)
class SolverRequest:
    """A QUBO and optional domain callbacks/configuration for one solver run.

    ``validator`` receives the complete assignment and may return a boolean or
    an object with ``feasible`` and optional ``violations`` attributes. The
    decoder and business objective are called only when it reports feasible.
    """

    qubo: QUBO
    constant_offset: Real = 0
    representation: ProblemRepresentation = ProblemRepresentation.QUBO
    ising_model: IsingModel | None = None
    validator: Validator | None = None
    decoder: Decoder | None = None
    business_objective: BusinessObjective | None = None
    configuration: Mapping[str, Any] = field(default_factory=dict)
    random_seed: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.qubo, QUBO):
            raise TypeError("qubo must be a QUBO instance")
        _finite_real(self.constant_offset, "constant_offset")
        if not isinstance(self.representation, ProblemRepresentation):
            raise TypeError("representation must be a ProblemRepresentation")
        ising_model = self.ising_model
        if ising_model is not None and not isinstance(ising_model, IsingModel):
            raise TypeError("ising_model must be an IsingModel or None")
        if ising_model is not None:
            canonical_ising = qubo_to_ising(self.qubo, offset=self.constant_offset)
            if (
                ising_model.variables != canonical_ising.variables
                or ising_model.constant != canonical_ising.constant
                or dict(ising_model.linear) != dict(canonical_ising.linear)
                or dict(ising_model.quadratic) != dict(canonical_ising.quadratic)
            ):
                raise ValueError(
                    "Ising model must be equivalent to the source QUBO and offset"
                )
        elif self.representation is ProblemRepresentation.ISING:
            object.__setattr__(
                self,
                "ising_model",
                qubo_to_ising(self.qubo, offset=self.constant_offset),
            )
        for name in ("validator", "decoder", "business_objective"):
            callback = getattr(self, name)
            if callback is not None and not callable(callback):
                raise TypeError(f"{name} must be callable or None")
        if self.decoder is not None and self.validator is None:
            raise ValueError("decoder requires a domain validator")
        if self.business_objective is not None and self.decoder is None:
            raise ValueError("business_objective requires a decoder")
        if not isinstance(self.configuration, Mapping):
            raise TypeError("configuration must be a mapping")
        if self.random_seed is not None and (
            isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int)
        ):
            raise TypeError("random_seed must be an integer or None")
        object.__setattr__(self, "configuration", MappingProxyType(dict(self.configuration)))

    @property
    def variable_order(self) -> tuple[str, ...]:
        """Original variable ordering shared by submitted representations."""
        return self.qubo.variables

    @property
    def representation_model(self) -> QUBO | IsingModel:
        """Return the mathematical model selected for a backend adapter."""
        if self.representation is ProblemRepresentation.ISING:
            assert self.ising_model is not None
            return self.ising_model
        return self.qubo


@dataclass(frozen=True)
class SolverResult:
    """Immutable, auditable output shared across classical and quantum solvers."""

    run_id: str
    solver_id: str
    solver_name: str
    solver_version: str
    backend_type: BackendType
    representation: ProblemRepresentation
    variable_order: tuple[str, ...]
    best_binary_assignment: Mapping[str, int] | None
    best_spin_assignment: Mapping[str, int] | None
    solver_reported_energy: Real | None
    qubo_energy: Real | None
    full_energy: Real | None
    ising_energy: Real | None
    decoded_solution: Mapping[str, Any] | None
    business_objective: Real | None
    feasible: bool | None
    feasibility_details: tuple[str, ...]
    candidate_assignments_evaluated: int
    execution_time_seconds: float
    configuration: Mapping[str, Any]
    random_seed: int | None
    status: ExecutionStatus
    termination_reason: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable_order", tuple(self.variable_order))
        for name in ("best_binary_assignment", "best_spin_assignment", "decoded_solution"):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, Mapping):
                    raise TypeError(f"{name} must be a mapping or None")
                if name != "decoded_solution" and set(value) != set(self.variable_order):
                    raise ValueError(f"{name} must contain all variables in variable_order")
                if name == "decoded_solution":
                    copied = dict(value)
                else:
                    copied = {key: value[key] for key in self.variable_order}
                object.__setattr__(self, name, MappingProxyType(copied))
        if not isinstance(self.configuration, Mapping):
            raise TypeError("configuration must be a mapping")
        object.__setattr__(self, "configuration", MappingProxyType(dict(self.configuration)))
        object.__setattr__(self, "feasibility_details", tuple(self.feasibility_details))


@dataclass(frozen=True)
class SolverBenchmarkRecord:
    """Comparable benchmark fields for one standardized solver result."""

    solver_id: str
    solver_name: str
    solver_version: str
    backend_type: BackendType
    problem_size: int
    variable_count: int
    best_energy: Real | None
    feasible: bool | None
    candidate_assignments_evaluated: int
    execution_time_seconds: float
    configuration: Mapping[str, Any]
    random_seed: int | None
    result: SolverResult

    @classmethod
    def from_result(cls, result: SolverResult) -> SolverBenchmarkRecord:
        """Project a run into common benchmark fields without losing details."""
        if not isinstance(result, SolverResult):
            raise TypeError("result must be a SolverResult")
        return cls(
            solver_id=result.solver_id,
            solver_name=result.solver_name,
            solver_version=result.solver_version,
            backend_type=result.backend_type,
            problem_size=len(result.variable_order),
            variable_count=len(result.variable_order),
            best_energy=result.full_energy,
            feasible=result.feasible,
            candidate_assignments_evaluated=result.candidate_assignments_evaluated,
            execution_time_seconds=result.execution_time_seconds,
            configuration=result.configuration,
            random_seed=result.random_seed,
            result=result,
        )


@runtime_checkable
class Solver(Protocol):
    """Backend-neutral contract implemented by classical and future adapters."""

    @property
    def metadata(self) -> SolverMetadata: ...

    def solve(self, request: SolverRequest) -> SolverResult: ...


class ExactQUBOSolver:
    """Deterministic exhaustive QUBO reference solver for small instances.

    The default limit of 12 variables caps enumeration at 4,096 candidate
    assignments. Exhaustive work grows as ``2**n``; dense models also evaluate
    every supplied coefficient at each candidate. Increase the limit only
    when the expected workload is acceptable.
    """

    VERSION = "1.0"
    DEFAULT_MAX_VARIABLES = 12

    def __init__(self, max_variables: int = DEFAULT_MAX_VARIABLES) -> None:
        if isinstance(max_variables, bool) or not isinstance(max_variables, int):
            raise TypeError("max_variables must be an integer")
        if max_variables < 0:
            raise ValueError("max_variables must be non-negative")
        self.max_variables = max_variables

    @property
    def metadata(self) -> SolverMetadata:
        return SolverMetadata(
            solver_id="exact-qubo",
            name="Exact QUBO Enumeration",
            version=self.VERSION,
            backend_type=BackendType.CLASSICAL,
            supported_representations=frozenset({ProblemRepresentation.QUBO}),
        )

    def solve(self, request: SolverRequest) -> SolverResult:
        """Return the global minimum over all binary assignments.

        Ties resolve to the lexicographically first bit tuple in declared
        variable order (0 before 1). The QUBO's own energy function evaluates
        every candidate; offsets do not affect which assignment minimizes it.
        """
        if not isinstance(request, SolverRequest):
            raise TypeError("request must be a SolverRequest")
        if request.representation not in self.metadata.supported_representations:
            raise ValueError(
                f"{self.metadata.solver_id!r} does not support "
                f"{request.representation.value} input"
            )
        variables = request.qubo.variables
        if len(variables) > self.max_variables:
            raise ValueError(
                f"exact QUBO solver supports at most {self.max_variables} variables; "
                f"received {len(variables)}"
            )

        started = perf_counter()
        best_assignment: dict[str, int] | None = None
        best_energy: Real | None = None
        candidates = 0
        for bits in product((0, 1), repeat=len(variables)):
            assignment = dict(zip(variables, bits))
            energy = request.qubo.energy(assignment)
            candidates += 1
            if best_energy is None or energy < best_energy:
                best_energy = energy
                best_assignment = assignment

        assert best_assignment is not None and best_energy is not None
        # Re-evaluate through the public model API to record an independent
        # QSupply-side energy alongside the selected solver candidate energy.
        qubo_energy = request.qubo.energy(best_assignment)
        full_energy = request.constant_offset + qubo_energy
        ising = request.ising_model or qubo_to_ising(
            request.qubo, offset=request.constant_offset
        )
        spins = {
            variable: 1 - 2 * best_assignment[variable] for variable in variables
        }
        ising_energy = ising.energy(spins)
        if not _energies_equal(ising_energy, full_energy):
            raise ArithmeticError("QUBO and Ising energies disagree for the selected assignment")

        feasible: bool | None = None
        feasibility_details: tuple[str, ...] = ()
        decoded: Mapping[str, Any] | None = None
        business_objective: Real | None = None
        status = ExecutionStatus.COMPLETED
        error: str | None = None
        if request.validator is not None:
            try:
                validation = request.validator(MappingProxyType(best_assignment))
                if isinstance(validation, bool):
                    feasible = validation
                elif hasattr(validation, "feasible"):
                    feasible = bool(validation.feasible)
                    raw_details = getattr(validation, "violations", ())
                    if isinstance(raw_details, str):
                        feasibility_details = (raw_details,)
                    else:
                        feasibility_details = tuple(str(item) for item in raw_details)
                else:
                    raise TypeError(
                        "validator must return bool or an object with a feasible attribute"
                    )
                if feasible and request.decoder is not None:
                    decoded = MappingProxyType(
                        dict(request.decoder(MappingProxyType(best_assignment)))
                    )
                    if request.business_objective is not None:
                        business_objective = _finite_real(
                            request.business_objective(decoded), "business objective"
                        )
            except Exception as exception:  # callback failure is a failed run, not feasibility
                feasible = None
                decoded = None
                business_objective = None
                feasibility_details = ()
                status = ExecutionStatus.FAILED
                error = f"{type(exception).__name__}: {exception}"

        elapsed = perf_counter() - started
        configuration = dict(request.configuration)
        configuration["max_variables"] = self.max_variables
        return SolverResult(
            run_id=str(uuid4()),
            solver_id=self.metadata.solver_id,
            solver_name=self.metadata.name,
            solver_version=self.metadata.version,
            backend_type=self.metadata.backend_type,
            representation=request.representation,
            variable_order=variables,
            best_binary_assignment=MappingProxyType(best_assignment),
            best_spin_assignment=MappingProxyType(spins),
            solver_reported_energy=best_energy,
            qubo_energy=qubo_energy,
            full_energy=full_energy,
            ising_energy=ising_energy,
            decoded_solution=decoded,
            business_objective=business_objective,
            feasible=feasible,
            feasibility_details=feasibility_details,
            candidate_assignments_evaluated=candidates,
            execution_time_seconds=elapsed,
            configuration=MappingProxyType(configuration),
            random_seed=request.random_seed,
            status=status,
            termination_reason=("all binary assignments enumerated" if status is ExecutionStatus.COMPLETED else None),
            error=error,
        )


def benchmark_solvers(
    request: SolverRequest, solvers: Sequence[Solver]
) -> tuple[SolverBenchmarkRecord, ...]:
    """Run compatible solvers on one request and return comparable summaries."""
    if not isinstance(request, SolverRequest):
        raise TypeError("request must be a SolverRequest")
    records: list[SolverBenchmarkRecord] = []
    for solver in solvers:
        if not isinstance(solver, Solver):
            raise TypeError("every solver must implement metadata and solve(request)")
        if request.representation not in solver.metadata.supported_representations:
            raise ValueError(
                f"solver {solver.metadata.solver_id!r} does not support "
                f"{request.representation.value} input"
            )
        records.append(SolverBenchmarkRecord.from_result(solver.solve(request)))
    return tuple(records)


def _finite_real(value: Real, name: str) -> Real:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    try:
        finite = isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{name} must be finite")
    return value


def _energies_equal(left: Real, right: Real) -> bool:
    if isinstance(left, float) or isinstance(right, float):
        return isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
    return left == right
