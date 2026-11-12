"""Backend-neutral execution metadata and error records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from types import MappingProxyType


class ExecutionMode(str, Enum):
    """Where the backend work was executed, when known."""

    LOCAL_SIMULATOR = "local_simulator"
    REMOTE_SIMULATOR = "remote_simulator"
    QUANTUM_HARDWARE = "quantum_hardware"
    UNSPECIFIED = "unspecified"


@dataclass(frozen=True)
class ExecutionTimings:
    """Optional separately measured execution stages, in seconds.

    ``None`` means the duration was unavailable or not separately measured.
    These values are not inferred from total wall time.
    """

    submission_seconds: float | None = None
    queue_seconds: float | None = None
    remote_execution_seconds: float | None = None
    result_retrieval_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "submission_seconds",
            "queue_seconds",
            "remote_execution_seconds",
            "result_retrieval_seconds",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name} must be finite and non-negative or None")


@dataclass(frozen=True)
class ExecutionMetadata(Mapping[str, object]):
    """Common backend identity, execution mode, stage timings and attributes."""

    backend_id: str
    backend_name: str
    backend_version: str | None = None
    execution_mode: ExecutionMode = ExecutionMode.UNSPECIFIED
    timing_scope: str | None = None
    timings: ExecutionTimings = field(default_factory=ExecutionTimings)
    attributes: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("backend_id", "backend_name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if self.backend_version is not None and (
            not isinstance(self.backend_version, str) or not self.backend_version
        ):
            raise ValueError("backend_version must be a non-empty string or None")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise TypeError("execution_mode must be an ExecutionMode")
        if self.timing_scope is not None and (
            not isinstance(self.timing_scope, str) or not self.timing_scope
        ):
            raise ValueError("timing_scope must be a non-empty string or None")
        if not isinstance(self.timings, ExecutionTimings):
            raise TypeError("timings must be ExecutionTimings")
        if not isinstance(self.attributes, Mapping):
            raise TypeError("attributes must be a mapping")
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))

    def as_dict(self) -> dict[str, object]:
        """Return a plain backend-neutral representation of the metadata."""
        return {
            "backend_id": self.backend_id,
            "backend_name": self.backend_name,
            "backend_version": self.backend_version,
            "execution_mode": self.execution_mode.value,
            "timing_scope": self.timing_scope,
            "submission_seconds": self.timings.submission_seconds,
            "queue_seconds": self.timings.queue_seconds,
            "remote_execution_seconds": self.timings.remote_execution_seconds,
            "result_retrieval_seconds": self.timings.result_retrieval_seconds,
            "attributes": dict(self.attributes),
        }

    def __getitem__(self, key: str) -> object:
        return self.as_dict()[key]

    def __iter__(self):
        return iter(self.as_dict())

    def __len__(self) -> int:
        return len(self.as_dict())


class ExecutionErrorCategory(str, Enum):
    """Stable, backend-neutral categories for unsuccessful executions."""

    UNAVAILABLE_DEPENDENCY = "unavailable_dependency"
    INVALID_CONFIGURATION = "invalid_configuration"
    EXECUTION_FAILURE = "execution_failure"
    TIMEOUT = "timeout"
    VALIDATION_FAILURE = "validation_failure"


@dataclass(frozen=True)
class ExecutionError:
    """Structured failure detail alongside the legacy result error string."""

    category: ExecutionErrorCategory
    message: str
    exception_type: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.category, ExecutionErrorCategory):
            raise TypeError("category must be an ExecutionErrorCategory")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("message must be a non-empty string")
        if self.exception_type is not None and (
            not isinstance(self.exception_type, str) or not self.exception_type
        ):
            raise ValueError("exception_type must be a non-empty string or None")


def classify_execution_error(
    error: Exception,
    *,
    unavailable_dependency: bool = False,
    invalid_configuration: bool = False,
) -> ExecutionError:
    """Classify failures without guessing from generic Python exception types.

    A backend can raise ``TypeError`` or ``ValueError`` while executing valid
    configuration, so callers must explicitly mark a known configuration
    validation boundary with ``invalid_configuration=True``.
    """
    if unavailable_dependency:
        category = ExecutionErrorCategory.UNAVAILABLE_DEPENDENCY
    elif isinstance(error, TimeoutError):
        category = ExecutionErrorCategory.TIMEOUT
    elif invalid_configuration:
        category = ExecutionErrorCategory.INVALID_CONFIGURATION
    else:
        category = ExecutionErrorCategory.EXECUTION_FAILURE
    message = str(error) or type(error).__name__
    return ExecutionError(category, message, type(error).__name__)
