"""Backend-neutral QAOA circuit planning and bounded parameter optimization."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite, pi
from numbers import Real
from random import Random
from time import perf_counter
from types import MappingProxyType

from .ising import IsingModel


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
    """SDK-neutral gate instruction; qubit indices follow variable order."""

    gate: str
    qubits: tuple[int, ...]
    angle: float | None = None


@dataclass(frozen=True)
class SampleBatch:
    """Counted binary samples in variable order and backend sampling duration."""

    counts: Mapping[tuple[int, ...], int]
    execution_time_seconds: float

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
        object.__setattr__(self, "counts", MappingProxyType(normalized))

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


SampleFunction = Callable[
    [IsingModel, tuple[float, ...], tuple[float, ...], int, int], SampleBatch
]


def build_qaoa_circuit_plan(
    ising: IsingModel, gammas: tuple[float, ...], betas: tuple[float, ...]
) -> tuple[CircuitOperation, ...]:
    """Create standard cost-then-mixer QAOA gates, omitting constant phase.

    The variable-dependent cost Hamiltonian is divided by its maximum
    absolute coefficient (a positive constant, preserving its minimizer),
    then evolved as ``exp(-i * gamma * H_cost_scaled)``. Qulacs ``R_axis``
    gates use ``exp(+i*theta*axis/2)``, so emitted ``RZ`` and ``RX`` angles
    are negative twice the QAOA parameters times scaled Hamiltonian
    coefficients. For a ``ZZ`` term, ``CNOT-RZ-CNOT`` implements its phase. The
    constant Ising offset is omitted since it contributes only a global phase.
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
    for gamma, beta in zip(gammas, betas):
        for variable, coefficient in ising.linear.items():
            angle = float(-2 * gamma * _scaled(coefficient, scale))
            if angle:
                instructions.append(CircuitOperation("rz", (indices[variable],), angle))
        for (left, right), coefficient in ising.quadratic.items():
            angle = float(-2 * gamma * _scaled(coefficient, scale))
            if angle:
                control, target = indices[left], indices[right]
                instructions.extend(
                    (
                        CircuitOperation("cx", (control, target)),
                        CircuitOperation("rz", (target,), angle),
                        CircuitOperation("cx", (control, target)),
                    )
                )
        for index in range(len(ising.variables)):
            instructions.append(CircuitOperation("rx", (index,), float(-2 * beta)))
    return tuple(instructions)


def run_qaoa(
    ising: IsingModel,
    sample: SampleFunction,
    config: QAOAConfig,
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
    if not callable(sample):
        raise TypeError("sample must be callable")
    if not ising.variables:
        raise ValueError("QAOA requires at least one variable")
    if len(ising.variables) > config.max_variables:
        raise ValueError(
            f"QAOA supports at most {config.max_variables} variables; "
            f"received {len(ising.variables)}"
        )

    rng = Random(config.random_seed)
    depth = config.depth
    cost_scale = _cost_scale(ising)
    params = [rng.uniform(0.0, 2 * pi) for _ in range(depth)] + [
        rng.uniform(0.0, pi) for _ in range(depth)
    ]
    optimization_started = perf_counter()
    execution_seconds = 0.0
    optimizer_samples = 0

    def evaluate(candidate: list[float]) -> float:
        nonlocal execution_seconds, optimizer_samples
        gammas = tuple(candidate[:depth])
        betas = tuple(candidate[depth:])
        batch = sample(
            ising, gammas, betas, config.shots, rng.randrange(0, 2**31)
        )
        if not isinstance(batch, SampleBatch):
            raise TypeError("sampling backend must return SampleBatch")
        if any(len(bits) != len(ising.variables) for bits in batch.counts):
            raise ValueError("backend sample width does not match Ising variable count")
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
    final_samples = sample(
        ising,
        tuple(best_params[:depth]),
        tuple(best_params[depth:]),
        config.shots,
        rng.randrange(0, 2**31),
    )
    if not isinstance(final_samples, SampleBatch):
        raise TypeError("sampling backend must return SampleBatch")
    if any(len(bits) != len(ising.variables) for bits in final_samples.counts):
        raise ValueError("backend sample width does not match Ising variable count")
    execution_seconds += final_samples.execution_time_seconds
    average = _average_energy(ising, final_samples.counts)
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
