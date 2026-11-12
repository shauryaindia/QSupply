"""Registry for the quantum backends exposed by QSupply's QAOA API."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Any

from ..execution import ExecutionMode
from ..qaoa import QAOAConfig
from ..solver import BackendType, ProblemRepresentation, Solver
from .qiskit import QiskitBackend, QiskitQAOASolver
from .qulacs import QulacsBackend, QulacsQAOASolver


SolverFactory = Callable[[QAOAConfig], Solver]
AvailabilityCheck = Callable[[], bool]
VersionCheck = Callable[[], str | None]


def _freeze_metadata(value: Any) -> Any:
    """Copy supported JSON metadata into recursively immutable containers."""
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("metadata mapping keys must be strings")
        return MappingProxyType({key: _freeze_metadata(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_metadata(item) for item in value)
    if isinstance(value, (set, frozenset)):
        raise TypeError("supported configuration must use ordered JSON-compatible collections")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    raise TypeError("supported configuration must contain finite JSON-compatible values")


def _copy_metadata(value: Any) -> Any:
    """Return mutable JSON-compatible values for capability serialization."""
    if isinstance(value, Mapping):
        return {key: _copy_metadata(item) for key, item in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_copy_metadata(item) for item in value]
    return value


@dataclass(frozen=True)
class QuantumBackendRegistration:
    """Metadata and constructors for one selectable quantum backend."""

    backend_id: str
    name: str
    description: str
    backend_type: BackendType
    supported_representations: tuple[ProblemRepresentation, ...]
    execution_mode: ExecutionMode
    optional_dependency: str
    dependency_requirements: str
    availability_check: AvailabilityCheck
    version_check: VersionCheck
    solver_factory: SolverFactory
    supported_configuration: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name in (
            "backend_id",
            "name",
            "description",
            "optional_dependency",
            "dependency_requirements",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.backend_type, BackendType):
            raise TypeError("backend_type must be a BackendType")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode")
        if isinstance(self.supported_representations, (str, bytes)):
            raise TypeError("supported_representations must be a sequence")
        try:
            representations = tuple(self.supported_representations)
        except TypeError as error:
            raise TypeError("supported_representations must be iterable") from error
        if not representations or any(
            not isinstance(item, ProblemRepresentation) for item in representations
        ):
            raise ValueError("supported_representations must not be empty")
        if len(set(representations)) != len(representations):
            raise ValueError("supported_representations must not contain duplicates")
        object.__setattr__(self, "supported_representations", representations)
        for name in ("availability_check", "version_check", "solver_factory"):
            if not callable(getattr(self, name)):
                raise TypeError(f"{name} must be callable")
        if not isinstance(self.supported_configuration, Mapping):
            raise TypeError("supported_configuration must be a mapping")
        object.__setattr__(
            self,
            "supported_configuration",
            _freeze_metadata(self.supported_configuration),
        )

    def configuration_errors(self, values: Mapping[str, Any]) -> tuple[str, ...]:
        """Return request settings that violate declared capability constraints."""
        if not isinstance(values, Mapping):
            raise TypeError("configuration values must be a mapping")
        errors: list[str] = []
        for name, constraint in self.supported_configuration.items():
            if name not in values:
                continue
            if not isinstance(constraint, Mapping):
                errors.append(f"{name} has an invalid backend configuration constraint")
                continue
            value = values[name]
            has_minimum = "minimum" in constraint
            has_maximum = "maximum" in constraint
            if has_minimum or has_maximum:
                if not (has_minimum and has_maximum):
                    errors.append(f"{name} has an incomplete backend configuration range")
                    continue
                minimum = constraint["minimum"]
                maximum = constraint["maximum"]
                if (
                    isinstance(minimum, bool)
                    or isinstance(maximum, bool)
                    or not isinstance(minimum, (int, float))
                    or not isinstance(maximum, (int, float))
                    or not isfinite(minimum)
                    or not isfinite(maximum)
                    or minimum > maximum
                ):
                    errors.append(f"{name} has an invalid backend configuration range")
                    continue
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not isfinite(value)
                    or value < minimum
                    or value > maximum
                ):
                    errors.append(f"{name} must be between {minimum} and {maximum}")
            elif "values" in constraint:
                allowed_values = constraint["values"]
                if not isinstance(allowed_values, tuple):
                    errors.append(f"{name} has an invalid backend configuration choice list")
                elif value not in allowed_values:
                    errors.append(f"{name} must be one of {list(allowed_values)!r}")
            else:
                errors.append(f"{name} has an unsupported backend configuration constraint")
        return tuple(errors)

    def is_available(self) -> bool:
        """Return false if the optional dependency check itself fails."""
        try:
            return bool(self.availability_check())
        except Exception:
            return False

    def version(self) -> str | None:
        try:
            return self.version_check()
        except Exception:
            return None

    def capability(self) -> dict[str, Any]:
        """Return a JSON-compatible capability record for the API."""
        available = self.is_available()
        detected_version = self.version()
        return {
            "id": self.backend_id,
            "name": self.name,
            "description": self.description,
            "available": available,
            "status": (
                "available"
                if available
                else "unsupported_dependency_version"
                if detected_version is not None
                else "optional_dependency_missing"
            ),
            "supported_representations": [
                item.value for item in self.supported_representations
            ],
            "backend_type": self.backend_type.value,
            "execution_mode": self.execution_mode.value,
            "optional_dependency": self.optional_dependency,
            "dependency_requirements": self.dependency_requirements,
            "version": detected_version,
            "supported_configuration": _copy_metadata(self.supported_configuration),
        }


class UnknownQuantumBackendError(KeyError):
    """Raised when a requested backend ID is not registered."""


class QuantumBackendRegistry:
    """Small explicit registry; registration never probes or imports SDKs itself."""

    def __init__(self) -> None:
        self._backends: dict[str, QuantumBackendRegistration] = {}

    def register(self, backend: QuantumBackendRegistration) -> None:
        if not isinstance(backend, QuantumBackendRegistration):
            raise TypeError("backend must be a QuantumBackendRegistration")
        if backend.backend_id in self._backends:
            raise ValueError(f"quantum backend {backend.backend_id!r} is already registered")
        self._backends[backend.backend_id] = backend

    def get(self, backend_id: str) -> QuantumBackendRegistration:
        if not isinstance(backend_id, str) or not backend_id:
            raise ValueError("backend_id must be a non-empty string")
        try:
            return self._backends[backend_id]
        except KeyError as error:
            raise UnknownQuantumBackendError(backend_id) from error

    def all(self) -> tuple[QuantumBackendRegistration, ...]:
        return tuple(self._backends.values())

    def capabilities(self) -> list[dict[str, Any]]:
        return [backend.capability() for backend in self.all()]


_QAOA_CONFIGURATION: Mapping[str, Any] = MappingProxyType(
    {
        "depth": {"minimum": 1, "maximum": 3},
        "optimizer": {"values": ["spsa", "coordinate"]},
        "max_iterations": {"minimum": 1, "maximum": 25},
        "shots": {"minimum": 16, "maximum": 2048},
        "random_seed": {"minimum": 0, "maximum": 2147483647},
    }
)


def create_default_quantum_backend_registry() -> QuantumBackendRegistry:
    """Register only adapters whose local execution paths are implemented."""
    registry = QuantumBackendRegistry()
    shared_representations = (ProblemRepresentation.ISING,)
    registry.register(
        QuantumBackendRegistration(
            backend_id="qulacs",
            name="Qulacs state-vector simulator",
            description="Local QAOA simulation through the optional Qulacs package.",
            backend_type=BackendType.SIMULATOR,
            supported_representations=shared_representations,
            execution_mode=ExecutionMode.LOCAL_SIMULATOR,
            optional_dependency="Qulacs",
            dependency_requirements="requirements-quantum.txt",
            availability_check=QulacsBackend.is_available,
            version_check=QulacsBackend.version,
            solver_factory=lambda config: QulacsQAOASolver(config),
            supported_configuration=_QAOA_CONFIGURATION,
        )
    )
    registry.register(
        QuantumBackendRegistration(
            backend_id="qiskit",
            name="Qiskit StatevectorSampler",
            description="Local QAOA simulation through Qiskit SDK 2.x StatevectorSampler.",
            backend_type=BackendType.SIMULATOR,
            supported_representations=shared_representations,
            execution_mode=ExecutionMode.LOCAL_SIMULATOR,
            optional_dependency="Qiskit SDK 2.x",
            dependency_requirements="requirements-qiskit.txt",
            availability_check=QiskitBackend.is_available,
            version_check=QiskitBackend.version,
            solver_factory=lambda config: QiskitQAOASolver(config),
            supported_configuration=_QAOA_CONFIGURATION,
        )
    )
    return registry


DEFAULT_QUANTUM_BACKEND_REGISTRY = create_default_quantum_backend_registry()
