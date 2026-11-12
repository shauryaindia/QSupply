"""Optional backend adapters and the explicit quantum backend registry."""

from .registry import (
    DEFAULT_QUANTUM_BACKEND_REGISTRY,
    QuantumBackendRegistration,
    QuantumBackendRegistry,
    UnknownQuantumBackendError,
    create_default_quantum_backend_registry,
)

__all__ = [
    "DEFAULT_QUANTUM_BACKEND_REGISTRY",
    "QuantumBackendRegistration",
    "QuantumBackendRegistry",
    "UnknownQuantumBackendError",
    "create_default_quantum_backend_registry",
]
