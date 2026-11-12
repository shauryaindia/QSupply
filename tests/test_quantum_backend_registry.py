import unittest
from dataclasses import replace

from qsupply.backends.registry import (
    DEFAULT_QUANTUM_BACKEND_REGISTRY,
    QuantumBackendRegistration,
    QuantumBackendRegistry,
    UnknownQuantumBackendError,
    create_default_quantum_backend_registry,
)
from qsupply.execution import ExecutionMode
from qsupply.qaoa import QAOAConfig
from qsupply.solver import BackendType, ProblemRepresentation


class TestQuantumBackendRegistry(unittest.TestCase):
    def test_default_registry_has_qiskit_and_qulacs_only(self):
        registry = create_default_quantum_backend_registry()
        self.assertEqual({item.backend_id for item in registry.all()}, {"qiskit", "qulacs"})
        self.assertNotIn("fujitsu-qarp", {item.backend_id for item in registry.all()})
        for item in registry.all():
            self.assertEqual(
                item.supported_representations, (ProblemRepresentation.ISING,)
            )
            self.assertEqual(item.backend_type, BackendType.SIMULATOR)
            self.assertEqual(item.execution_mode, ExecutionMode.LOCAL_SIMULATOR)
            self.assertEqual(item.solver_factory(QAOAConfig()).metadata.backend_type, BackendType.SIMULATOR)

    def test_registration_rejects_duplicates_and_unknown_ids(self):
        registry = QuantumBackendRegistry()
        registration = DEFAULT_QUANTUM_BACKEND_REGISTRY.get("qiskit")
        registry.register(registration)
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(registration)
        with self.assertRaises(UnknownQuantumBackendError):
            registry.get("not-installed")

    def test_capabilities_report_unavailable_dependencies_and_version(self):
        registry = QuantumBackendRegistry()
        original = DEFAULT_QUANTUM_BACKEND_REGISTRY.get("qiskit")
        unavailable = replace(
            original,
            availability_check=lambda: False,
            version_check=lambda: None,
        )
        registry.register(unavailable)
        capability = registry.capabilities()[0]
        self.assertEqual(capability["id"], "qiskit")
        self.assertFalse(capability["available"])
        self.assertEqual(capability["status"], "optional_dependency_missing")
        self.assertEqual(capability["optional_dependency"], "Qiskit SDK 2.x")
        self.assertEqual(capability["dependency_requirements"], "requirements-qiskit.txt")
        self.assertIsNone(capability["version"])
        self.assertEqual(capability["execution_mode"], "local_simulator")
        self.assertIn("shots", capability["supported_configuration"])

    def test_invalid_registration_metadata_is_rejected(self):
        with self.assertRaises(ValueError):
            QuantumBackendRegistration(
                backend_id="",
                name="Invalid",
                description="Invalid registration",
                backend_type=BackendType.SIMULATOR,
                supported_representations=(ProblemRepresentation.ISING,),
                execution_mode=ExecutionMode.LOCAL_SIMULATOR,
                optional_dependency="test",
                dependency_requirements="requirements-test.txt",
                availability_check=lambda: True,
                version_check=lambda: "1",
                solver_factory=lambda config: object(),
                supported_configuration={},
            )

    def test_capabilities_copy_and_freeze_nested_metadata(self):
        representations = [ProblemRepresentation.ISING]
        choices = ["spsa", "coordinate"]
        nested = {"minimum": 1, "maximum": 3, "labels": ["low", {"name": "depth"}]}
        configuration = {"optimizer": {"values": choices}, "extra": nested}
        registration = QuantumBackendRegistration(
            backend_id="immutable-test", name="Test", description="Test backend",
            backend_type=BackendType.SIMULATOR, supported_representations=representations,
            execution_mode=ExecutionMode.LOCAL_SIMULATOR, optional_dependency="test",
            dependency_requirements="test", availability_check=lambda: True,
            version_check=lambda: "1", solver_factory=lambda _config: object(),
            supported_configuration=configuration,
        )
        representations.clear()
        choices.append("unsupported")
        nested["labels"].append("mutated")
        configuration["new"] = {"values": [1]}

        self.assertEqual(registration.supported_representations, (ProblemRepresentation.ISING,))
        self.assertEqual(
            registration.supported_configuration["optimizer"]["values"],
            ("spsa", "coordinate"),
        )
        self.assertEqual(
            registration.supported_configuration["extra"]["labels"][1]["name"], "depth"
        )
        with self.assertRaises(TypeError):
            registration.supported_configuration["extra"]["labels"][1]["name"] = "changed"
        capability = registration.capability()
        capability["supported_configuration"]["optimizer"]["values"].append("also-unsupported")
        capability["supported_representations"].clear()
        self.assertEqual(
            registration.capability()["supported_configuration"]["optimizer"]["values"],
            ["spsa", "coordinate"],
        )
        self.assertEqual(registration.capability()["supported_representations"], ["ising"])

    def test_unordered_metadata_collections_are_rejected(self):
        registration = DEFAULT_QUANTUM_BACKEND_REGISTRY.get("qiskit")
        with self.assertRaisesRegex(TypeError, "ordered JSON-compatible"):
            replace(registration, supported_configuration={"optimizer": {"values": {"spsa"}}})


if __name__ == "__main__":
    unittest.main()
