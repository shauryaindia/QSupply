"""Backend-neutral QAOA circuit planning and bounded parameter optimization."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from math import isfinite, pi
from numbers import Real
from random import Random
from time import perf_counter
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from .execution import ExecutionMetadata
from .ising import IsingModel
from .qubo import QUBO
from .solver import (
    ProblemRepresentation,
    SampleEnergyRecord,
    SolverRequest,
    average_recomputed_full_energy,
    recompute_sample_energies,
)


MAX_QAOA_VARIABLES = 12
MAX_QAOA_DEPTH = 3
MAX_QAOA_SHOTS = 2048
MAX_QAOA_ITERATIONS = 25


@dataclass(frozen=True)
class QAOAConfig:
    """Explicitly bounded QAOA configuration for the initial simulator path."""

    depth: int = 1
    optimizer: str = "spsa"
    max_iterations: int = 10
    shots: int = 128
    random_seed: int = 2026
    max_variables: int = MAX_QAOA_VARIABLES

    def __post_init__(self) -> None:
        for name, value, maximum in (
            ("depth", self.depth, MAX_QAOA_DEPTH),
            ("max_iterations", self.max_iterations, MAX_QAOA_ITERATIONS),
            ("shots", self.shots, MAX_QAOA_SHOTS),
            ("max_variables", self.max_variables, MAX_QAOA_VARIABLES),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            minimum = 16 if name == "shots" else 1
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")
        if self.optimizer not in {"spsa", "coordinate"}:
            raise ValueError("optimizer must be 'spsa' or 'coordinate'")
        if isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int):
            raise TypeError("random_seed must be an integer")


@dataclass(frozen=True)
class CircuitOperation:
    """Canonical rotation instruction; qubit indices follow variable order.

    ``rz``, ``rzz`` and ``rx`` angles use the mathematical convention
    ``R_P(theta) = exp(-i * theta * P / 2)``. Backend adapters translate this
    convention to their SDK's gate definitions.
    """

    gate: str
    qubits: tuple[int, ...]
    angle: float | None = None


@dataclass(frozen=True)
class SamplingRequest:
    """One backend-neutral QAOA sampling request.

    Sample indices always follow ``ising_model.variables``. ``seed`` is a
    requested seed passed to the backend; it does not promise reproducibility
    unless that backend documents and honors seeded sampling.
    """

    ising_model: IsingModel
    gammas: tuple[float, ...]
    betas: tuple[float, ...]
    shots: int
    seed: int

    def __post_init__(self) -> None:
        if not isinstance(self.ising_model, IsingModel):
            raise TypeError("ising_model must be an IsingModel")
        if not isinstance(self.gammas, tuple) or not isinstance(self.betas, tuple):
            raise TypeError("gammas and betas must be tuples")
        if not self.gammas or len(self.gammas) != len(self.betas):
            raise ValueError("gammas and betas must have equal nonzero depth")
        if any(
            isinstance(angle, bool) or not isinstance(angle, Real) or not isfinite(angle)
            for angle in (*self.gammas, *self.betas)
        ):
            raise ValueError("gamma and beta values must be finite real numbers")
        if isinstance(self.shots, bool) or not isinstance(self.shots, int) or self.shots <= 0:
            raise ValueError("shots must be a positive integer")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")

    @property
    def variable_order(self) -> tuple[str, ...]:
        """Canonical ordering required for every returned bit tuple."""
        return self.ising_model.variables


@dataclass(frozen=True)
class SampleBatch:
    """Counted binary samples in variable order and backend call metadata.

    Identity and request metadata are optional for compatibility with legacy
    sampling callbacks. Implementations of :class:`QAOASamplingBackend` should
    populate them. ``shots`` is the actual count total; ``requested_shots``
    records the requested budget and may differ if a backend reports a partial
    result.
    """

    counts: Mapping[tuple[int, ...], int]
    execution_time_seconds: float
    variable_order: tuple[str, ...] | None = None
    backend_id: str | None = None
    backend_name: str | None = None
    backend_version: str | None = None
    requested_shots: int | None = None
    seed: int | None = None
    execution_metadata: Mapping[str, object] | ExecutionMetadata = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not isinstance(self.counts, Mapping) or not self.counts:
            raise ValueError("counts must be a non-empty mapping")
        normalized: dict[tuple[int, ...], int] = {}
        width: int | None = None
        for bits, count in self.counts.items():
            bit_tuple = tuple(bits)
            if any(
                isinstance(bit, bool) or not isinstance(bit, int) or bit not in (0, 1)
                for bit in bit_tuple
            ):
                raise ValueError("sample bitstrings must contain only integer 0 and 1")
            if width is None:
                width = len(bit_tuple)
            if len(bit_tuple) != width:
                raise ValueError("all sampled bitstrings must have the same length")
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise ValueError("sample counts must be positive integers")
            normalized[bit_tuple] = count
        if not isfinite(self.execution_time_seconds) or self.execution_time_seconds < 0:
            raise ValueError("execution_time_seconds must be finite and non-negative")
        if self.variable_order is not None:
            order = tuple(self.variable_order)
            if (
                any(not isinstance(name, str) or not name for name in order)
                or len(set(order)) != len(order)
            ):
                raise ValueError("variable_order must contain unique non-empty names")
            if len(order) != width:
                raise ValueError("variable_order width must match sampled bitstrings")
            object.__setattr__(self, "variable_order", order)
        for name in ("backend_id", "backend_name", "backend_version"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{name} must be a non-empty string or None")
        if self.requested_shots is not None and (
            isinstance(self.requested_shots, bool)
            or not isinstance(self.requested_shots, int)
            or self.requested_shots <= 0
        ):
            raise ValueError("requested_shots must be a positive integer or None")
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise TypeError("seed must be an integer or None")
        if isinstance(self.execution_metadata, ExecutionMetadata):
            structured_metadata = self.execution_metadata
            if (
                structured_metadata.backend_id != self.backend_id
                or structured_metadata.backend_name != self.backend_name
                or structured_metadata.backend_version != self.backend_version
            ):
                raise ValueError("structured execution identity must match sample batch identity")
        elif isinstance(self.execution_metadata, Mapping):
            object.__setattr__(
                self, "execution_metadata", MappingProxyType(dict(self.execution_metadata))
            )
        else:
            raise TypeError("execution_metadata must be a mapping or ExecutionMetadata")
        object.__setattr__(self, "counts", MappingProxyType(normalized))

    @property
    def structured_execution_metadata(self) -> ExecutionMetadata | None:
        """Return structured metadata, or None for a legacy mapping response."""
        if isinstance(self.execution_metadata, ExecutionMetadata):
            return self.execution_metadata
        return None

    @property
    def shots(self) -> int:
        return sum(self.counts.values())


@dataclass(frozen=True)
class QAOAExecution:
    """Optimizer output plus final measured sample statistics."""

    gammas: tuple[float, ...]
    betas: tuple[float, ...]
    optimizer_iterations: int
    optimization_time_seconds: float
    circuit_execution_time_seconds: float
    optimizer_sample_count: int
    final_samples: SampleBatch
    average_sampled_energy: Real
    best_bits: tuple[int, ...]
    best_sample_frequency: int
    cost_normalization_scale: Real
    sample_energies: Mapping[tuple[int, ...], SampleEnergyRecord] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "sample_energies", MappingProxyType(dict(self.sample_energies))
        )


SampleFunction = Callable[
    [IsingModel, tuple[float, ...], tuple[float, ...], int, int], SampleBatch
]


@runtime_checkable
class QAOASamplingBackend(Protocol):
    """Backend contract for sampling one canonical QAOA request.

    Implementations return bit tuples in ``request.variable_order`` and report
    backend identity, requested shots, seed and sample-call duration. A seed is
    an input request, not a reproducibility guarantee.
    """

    def sample(self, request: SamplingRequest, /) -> SampleBatch: ...


def build_qaoa_circuit_plan(
    ising: IsingModel, gammas: tuple[float, ...], betas: tuple[float, ...]
) -> tuple[CircuitOperation, ...]:
    """Create canonical QAOA rotations, omitting the Ising constant phase.

    For the variable-dependent Hamiltonian
    ``H_C = sum(h_i Z_i) + sum(J_ij Z_i Z_j)``, the cost is scaled by its
    maximum absolute coefficient ``s`` (a positive scale preserving its
    minimizer). This plan therefore represents
    ``exp(-i * gamma * H_C / s)`` with canonical rotations
    ``RZ(2*gamma*h_i/s)``, ``RZZ(2*gamma*J_ij/s)`` and ``RX(2*beta)``.
    ``R_P(theta)`` means ``exp(-i*theta*P/2)`` for every SDK-independent
    operation. Backend adapters translate that convention to native gates.

    The Ising constant is excluded from circuit evolution because it adds only
    a global phase. It remains part of reported Ising/full energy.
    """
    if not isinstance(ising, IsingModel):
        raise TypeError("ising must be an IsingModel")
    if len(gammas) != len(betas) or not gammas:
        raise ValueError("gammas and betas must have equal nonzero depth")
    if len(gammas) > MAX_QAOA_DEPTH:
        raise ValueError(f"QAOA depth must not exceed {MAX_QAOA_DEPTH}")
    if len(ising.variables) > MAX_QAOA_VARIABLES:
        raise ValueError(f"QAOA supports at most {MAX_QAOA_VARIABLES} variables")
    for value in (*gammas, *betas):
        if not isinstance(value, Real) or not isfinite(value):
            raise ValueError("QAOA angles must be finite real values")

    scale = _cost_scale(ising)
    instructions: list[CircuitOperation] = [
        CircuitOperation("h", (index,)) for index in range(len(ising.variables))
    ]
    indices = ising.variable_indices
    for gamma, beta in zip(gammas, betas, strict=True):
        for variable in ising.variables:
            coefficient = ising.linear[variable]
            angle = float(2 * gamma * _scaled(coefficient, scale))
            if angle:
                instructions.append(CircuitOperation("rz", (indices[variable],), angle))
        for left_index, left in enumerate(ising.variables):
            for right in ising.variables[left_index + 1 :]:
                coefficient = ising.quadratic.get((left, right), 0)
                if not coefficient:
                    continue
                angle = float(2 * gamma * _scaled(coefficient, scale))
                if angle:
                    instructions.append(
                        CircuitOperation(
                            "rzz", (indices[left], indices[right]), angle
                        )
                    )
        for index in range(len(ising.variables)):
            instructions.append(CircuitOperation("rx", (index,), float(2 * beta)))
    return tuple(instructions)


def run_qaoa(
    ising: IsingModel,
    sample: SampleFunction | QAOASamplingBackend,
    config: QAOAConfig,
    *,
    source_qubo: QUBO | None = None,
    constant_offset: Real = 0,
) -> QAOAExecution:
    """Optimize QAOA parameters through a backend sampling callback.

    SPSA uses two stochastic objective estimates per gradient plus one estimate
    at each updated point. Coordinate search changes one angle per iteration
    and compares its two neighboring points. Both methods use seeded parameter
    and backend sampling streams, then take a separate final measurement batch.
    """
    if not isinstance(ising, IsingModel):
        raise TypeError("ising must be an IsingModel")
    if not isinstance(config, QAOAConfig):
        raise TypeError("config must be a QAOAConfig")
    if not isinstance(sample, QAOASamplingBackend) and not callable(sample):
        raise TypeError("sample must be a QAOASamplingBackend or legacy callable")
    if not ising.variables:
        raise ValueError("QAOA requires at least one variable")
    if len(ising.variables) > config.max_variables:
        raise ValueError(
            f"QAOA supports at most {config.max_variables} variables; "
            f"received {len(ising.variables)}"
        )
    energy_request: SolverRequest | None = None
    if source_qubo is not None:
        energy_request = SolverRequest(
            qubo=source_qubo,
            constant_offset=constant_offset,
            representation=ProblemRepresentation.ISING,
            ising_model=ising,
        )
    elif constant_offset != 0:
        raise ValueError("constant_offset requires source_qubo for independent energy checks")

    rng = Random(config.random_seed)
    depth = config.depth
    cost_scale = _cost_scale(ising)
    params = [rng.uniform(0.0, 2 * pi) for _ in range(depth)] + [
        rng.uniform(0.0, pi) for _ in range(depth)
    ]
    optimization_started = perf_counter()
    execution_seconds = 0.0
    optimizer_samples = 0

    def take_sample(gammas: tuple[float, ...], betas: tuple[float, ...]) -> SampleBatch:
        seed = rng.randrange(0, 2**31)
        if isinstance(sample, QAOASamplingBackend):
            sampling_request = SamplingRequest(
                ising_model=ising,
                gammas=gammas,
                betas=betas,
                shots=config.shots,
                seed=seed,
            )
            batch = sample.sample(sampling_request)
            if not isinstance(batch, SampleBatch):
                raise TypeError("sampling backend must return SampleBatch")
            if batch.structured_execution_metadata is None:
                raise ValueError("sampling backend response must include structured execution metadata")
            if batch.backend_id is None or batch.backend_name is None:
                raise ValueError("sampling backend response must identify its backend")
            if batch.variable_order != sampling_request.variable_order:
                raise ValueError("sampling backend response variable_order mismatch")
            if batch.requested_shots != sampling_request.shots:
                raise ValueError("sampling backend response requested_shots mismatch")
            if batch.seed != sampling_request.seed:
                raise ValueError("sampling backend response seed mismatch")
        else:
            batch = sample(ising, gammas, betas, config.shots, seed)
        if not isinstance(batch, SampleBatch):
            raise TypeError("sampling backend must return SampleBatch")
        if any(len(bits) != len(ising.variables) for bits in batch.counts):
            raise ValueError("backend sample width does not match Ising variable count")
        return batch

    def evaluate(candidate: list[float]) -> float:
        nonlocal execution_seconds, optimizer_samples
        gammas = tuple(candidate[:depth])
        betas = tuple(candidate[depth:])
        batch = take_sample(gammas, betas)
        execution_seconds += batch.execution_time_seconds
        optimizer_samples += batch.shots
        return _average_scaled_energy(ising, batch.counts, cost_scale)

    current = list(params)
    current_energy = evaluate(current)
    best_params = list(current)
    best_energy = current_energy

    for iteration in range(config.max_iterations):
        if config.optimizer == "spsa":
            delta = [rng.choice((-1.0, 1.0)) for _ in current]
            ck = 0.2 / ((iteration + 1) ** 0.101)
            plus = [value + ck * direction for value, direction in zip(current, delta)]
            minus = [value - ck * direction for value, direction in zip(current, delta)]
            plus_energy = evaluate(plus)
            minus_energy = evaluate(minus)
            gradient = [
                (plus_energy - minus_energy) / (2 * ck * direction)
                for direction in delta
            ]
            ak = 0.2 / ((iteration + 1) ** 0.602)
            current = [
                value - ak * derivative
                for value, derivative in zip(current, gradient)
            ]
            current_energy = evaluate(current)
            for candidate, energy in ((plus, plus_energy), (minus, minus_energy), (current, current_energy)):
                if energy < best_energy:
                    best_params, best_energy = list(candidate), energy
        else:
            coordinate = iteration % len(current)
            step = 0.25 / ((iteration // len(current) + 1) ** 0.1)
            candidates: list[tuple[list[float], float]] = []
            for direction in (-1.0, 1.0):
                candidate = list(current)
                candidate[coordinate] += direction * step
                candidates.append((candidate, evaluate(candidate)))
            current, current_energy = min(candidates, key=lambda item: item[1])
            if current_energy < best_energy:
                best_params, best_energy = list(current), current_energy

    optimization_seconds = perf_counter() - optimization_started
    final_samples = take_sample(
        tuple(best_params[:depth]), tuple(best_params[depth:])
    )
    execution_seconds += final_samples.execution_time_seconds
    sample_energies = (
        recompute_sample_energies(energy_request, final_samples.counts)
        if energy_request is not None
        else MappingProxyType({})
    )
    average = (
        average_recomputed_full_energy(sample_energies)
        if sample_energies
        else _average_energy(ising, final_samples.counts)
    )
    scored = [
        (ising.energy(_spins(ising, bits)), bits, count)
        for bits, count in final_samples.counts.items()
    ]
    best_energy_exact = min(item[0] for item in scored)
    best_bits, best_frequency = min(
        ((bits, count) for energy, bits, count in scored if energy == best_energy_exact),
        key=lambda item: item[0],
    )
    return QAOAExecution(
        gammas=tuple(best_params[:depth]),
        betas=tuple(best_params[depth:]),
        optimizer_iterations=config.max_iterations,
        optimization_time_seconds=optimization_seconds,
        circuit_execution_time_seconds=execution_seconds,
        optimizer_sample_count=optimizer_samples,
        final_samples=final_samples,
        average_sampled_energy=average,
        best_bits=best_bits,
        best_sample_frequency=best_frequency,
        cost_normalization_scale=cost_scale,
        sample_energies=sample_energies,
    )


def _spins(ising: IsingModel, bits: tuple[int, ...]) -> Mapping[str, int]:
    return {
        variable: 1 - 2 * bits[index]
        for index, variable in enumerate(ising.variables)
    }


def _average_energy(
    ising: IsingModel, counts: Mapping[tuple[int, ...], int]
) -> Real:
    weighted: Real = 0
    shots = sum(counts.values())
    for bits, count in counts.items():
        weighted += ising.energy(_spins(ising, bits)) * count
    return weighted / shots


def _cost_scale(ising: IsingModel) -> Real:
    coefficients = (*ising.linear.values(), *ising.quadratic.values())
    maximum = max((abs(value) for value in coefficients), default=0)
    return maximum if maximum else 1


def _scaled(value: Real, scale: Real) -> Fraction:
    """Normalize coefficients exactly before converting gate angles to float."""
    return Fraction(value) / Fraction(scale)


def _average_scaled_energy(
    ising: IsingModel,
    counts: Mapping[tuple[int, ...], int],
    scale: Real,
) -> float:
    """Expected variable-dependent energy on a bounded scale for optimization."""
    weighted = Fraction(0)
    shots = sum(counts.values())
    for bits, count in counts.items():
        spins = _spins(ising, bits)
        variable_energy = sum(
            Fraction(coefficient) * spins[variable]
            for variable, coefficient in ising.linear.items()
        ) + sum(
            Fraction(coefficient) * spins[left] * spins[right]
            for (left, right), coefficient in ising.quadratic.items()
        )
        weighted += variable_energy * count
    return float(weighted / shots / Fraction(scale))
