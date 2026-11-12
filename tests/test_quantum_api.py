import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from qsupply.api.app import create_app
from qsupply.backends.registry import (
    DEFAULT_QUANTUM_BACKEND_REGISTRY,
    QuantumBackendRegistry,
)
from qsupply.backends.qulacs import QulacsBackend
from qsupply.backends.qiskit import QiskitBackend
from qsupply.solver import (
    BackendType,
    ExecutionStatus,
    ProblemRepresentation,
    SolverMetadata,
    SolverResult,
)


class TestQuantumAPI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.client_context = TestClient(create_app(Path(self.temp_dir.name) / "runs.sqlite3"))
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def test_configuration_errors_are_rejected(self):
        response = self.client.post(
            "/api/v1/quantum/qubo-runs",
            json={"depth": 4, "shots": 32},
        )
        self.assertEqual(response.status_code, 422)

    def test_quantum_response_schema_exposes_standardized_metadata_and_energies(self):
        schema = self.client.get("/openapi.json").json()
        response_schema = schema["components"]["schemas"]["QuantumQAOAResponse"]
        properties = response_schema["properties"]
        self.assertIn("sample_energies", properties)
        self.assertIn("execution_metadata", properties)
        self.assertIn("error_details", properties)
        self.assertIn("exact_reference_feasible", properties)
        timing_schema = schema["components"]["schemas"]["QuantumExecutionTimings"]
        for field in (
            "submission_seconds",
            "queue_seconds",
            "remote_execution_seconds",
            "result_retrieval_seconds",
        ):
            self.assertIn(field, timing_schema["properties"])

    def test_capabilities_discover_registered_backends_and_keep_qarp_unregistered(self):
        response = self.client.get("/api/v1/capabilities")
        self.assertEqual(response.status_code, 200)
        backends = response.json()["backends"]
        self.assertEqual({item["id"] for item in backends}, {"qiskit", "qulacs"})
        for backend in backends:
            self.assertIn("available", backend)
            self.assertIn("supported_representations", backend)
            self.assertIn("execution_mode", backend)
            self.assertIn("optional_dependency", backend)
            self.assertIn("dependency_requirements", backend)
            self.assertIn("version", backend)
            self.assertIn("supported_configuration", backend)
        integrations = response.json()["integrations"]
        self.assertIn("fujitsu-qarp", {item["id"] for item in integrations})

    def test_unknown_backend_is_rejected_without_fallback(self):
        response = self.client.post(
            "/api/v1/quantum/qubo-runs",
            json={"backend": "unknown-backend", "depth": 1, "shots": 16},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("Unknown quantum backend", response.json()["detail"])

    def test_unavailable_registered_backend_is_rejected_before_factory_call(self):
        registry = QuantumBackendRegistry()
        registration = DEFAULT_QUANTUM_BACKEND_REGISTRY.get("qiskit")
        factory_called = []
        from dataclasses import replace

        registry.register(
            replace(
                registration,
                availability_check=lambda: False,
                solver_factory=lambda config: factory_called.append(config),
            )
        )
        temp_dir = tempfile.TemporaryDirectory()
        try:
            client_context = TestClient(
                create_app(
                    Path(temp_dir.name) / "unavailable.sqlite3",
                    quantum_backend_registry=registry,
                )
            )
            with client_context as client:
                response = client.post(
                    "/api/v1/quantum/qubo-runs",
                    json={"backend": "qiskit", "depth": 1, "shots": 16},
                )
            self.assertEqual(response.status_code, 503)
            self.assertIn("requirements-qiskit.txt", response.json()["detail"])
            self.assertEqual(factory_called, [])
        finally:
            temp_dir.cleanup()

    def test_backend_specific_configuration_is_rejected_before_factory_call(self):
        registry = QuantumBackendRegistry()
        registration = DEFAULT_QUANTUM_BACKEND_REGISTRY.get("qiskit")
        factory_called = []
        registry.register(
            replace(
                registration,
                supported_configuration={"depth": {"minimum": 2, "maximum": 2}},
                availability_check=lambda: True,
                solver_factory=lambda config: factory_called.append(config),
            )
        )
        temp_dir = tempfile.TemporaryDirectory()
        try:
            client_context = TestClient(
                create_app(
                    Path(temp_dir.name) / "unsupported-config.sqlite3",
                    quantum_backend_registry=registry,
                )
            )
            with client_context as client:
                response = client.post(
                    "/api/v1/quantum/qubo-runs",
                    json={"backend": "qiskit", "depth": 1, "shots": 16},
                )
            self.assertEqual(response.status_code, 422)
            self.assertIn("Unsupported configuration", response.json()["detail"])
            self.assertEqual(factory_called, [])
        finally:
            temp_dir.cleanup()

    def test_exact_reference_feasibility_is_returned_and_nullable_when_unrequested(self):
        class StubSolver:
            @property
            def metadata(self):
                return SolverMetadata(
                    "qiskit-qaoa", "Stub QAOA", "test", BackendType.SIMULATOR,
                    frozenset({ProblemRepresentation.ISING}),
                )

            def solve(self, request):
                variables = request.variable_order
                assignment = dict.fromkeys(variables, 0)
                spins = dict.fromkeys(variables, 1)
                qubo_energy = request.qubo.energy(assignment)
                full_energy = request.constant_offset + qubo_energy
                return SolverResult(
                    run_id="stub-run", solver_id="qiskit-qaoa", solver_name="Stub QAOA",
                    solver_version="test", backend_type=BackendType.SIMULATOR,
                    representation=ProblemRepresentation.ISING, variable_order=variables,
                    best_binary_assignment=assignment, best_spin_assignment=spins,
                    solver_reported_energy=full_energy, qubo_energy=qubo_energy,
                    full_energy=full_energy, ising_energy=full_energy,
                    decoded_solution=None, business_objective=None, feasible=False,
                    feasibility_details=(), candidate_assignments_evaluated=0,
                    execution_time_seconds=0.001, configuration={}, random_seed=request.random_seed,
                    status=ExecutionStatus.COMPLETED, backend_name="Stub QAOA",
                    backend_version="test",
                )

        registry = QuantumBackendRegistry()
        registry.register(
            replace(
                DEFAULT_QUANTUM_BACKEND_REGISTRY.get("qiskit"),
                availability_check=lambda: True,
                solver_factory=lambda _config: StubSolver(),
            )
        )
        temp_dir = tempfile.TemporaryDirectory()
        try:
            client_context = TestClient(
                create_app(
                    Path(temp_dir.name) / "exact-feasibility.sqlite3",
                    quantum_backend_registry=registry,
                )
            )
            with client_context as client:
                compared = client.post(
                    "/api/v1/quantum/qubo-runs",
                    json={"backend": "qiskit", "depth": 1, "max_iterations": 1, "shots": 16},
                )
                unrequested = client.post(
                    "/api/v1/quantum/qubo-runs",
                    json={"backend": "qiskit", "depth": 1, "max_iterations": 1, "shots": 16, "compare_exact": False},
                )
            self.assertEqual(compared.status_code, 201, compared.text)
            self.assertIs(compared.json()["exact_reference_feasible"], True)
            self.assertEqual(compared.json()["exact_reference_energy"], "17")
            self.assertEqual(unrequested.status_code, 201, unrequested.text)
            self.assertIsNone(unrequested.json()["exact_reference_feasible"])
            self.assertIsNone(unrequested.json()["exact_reference_energy"])
        finally:
            temp_dir.cleanup()

    def test_qiskit_backend_selection_is_explicit_and_never_falls_back(self):
        response = self.client.post(
            "/api/v1/quantum/qubo-runs",
            json={"backend": "qiskit", "depth": 1, "max_iterations": 1, "shots": 16},
        )
        if not QiskitBackend.is_available():
            self.assertEqual(response.status_code, 503)
            self.assertIn("requirements-qiskit.txt", response.json()["detail"])
            return
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        self.assertEqual(result["backend_id"], "qiskit")
        self.assertIn("Qiskit", result["backend_name"])
        self.assertEqual(result["final_sample_count"], 16)
        self.assertEqual(sum(item["count"] for item in result["sample_frequencies"]), 16)
        self.assertTrue(all(len(item["bitstring"]) == result["variable_count"] for item in result["sample_frequencies"]))
        self.assertEqual(result["full_energy"], result["ising_energy"])

    @unittest.skipIf(QulacsBackend.is_available(), "Qulacs is installed")
    def test_missing_optional_backend_returns_unavailable(self):
        response = self.client.post(
            "/api/v1/quantum/qubo-runs",
            json={"depth": 1, "max_iterations": 1, "shots": 16},
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("optional dependency", response.json()["detail"])

    @unittest.skipUnless(QulacsBackend.is_available(), "optional Qulacs package not installed")
    def test_endpoint_executes_qaoa_and_returns_exact_reference_comparison(self):
        response = self.client.post(
            "/api/v1/quantum/qubo-runs",
            json={
                "depth": 1,
                "optimizer": "spsa",
                "max_iterations": 1,
                "shots": 32,
                "random_seed": 317,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["synthetic"], True)
        self.assertEqual(result["variable_count"], 5)
        self.assertEqual(result["backend_version"], QulacsBackend.version())
        self.assertEqual(result["algorithm_name"], "Quantum Approximate Optimization Algorithm")
        self.assertTrue(result["cost_normalization_scale"])
        self.assertEqual(result["final_sample_count"], 32)
        self.assertEqual(result["total_sample_count"], 160)
        self.assertEqual(result["exact_reference_energy"], "17")
        self.assertIs(result["exact_reference_feasible"], True)
        self.assertGreaterEqual(result["exact_reference_time_seconds"], 0)
        self.assertEqual(result["full_energy"], result["ising_energy"])
        self.assertEqual(sum(item["count"] for item in result["sample_frequencies"]), 32)
        self.assertIsInstance(result["feasible"], bool)
        self.assertGreaterEqual(result["feasible_sample_rate"], 0)
        self.assertLessEqual(result["feasible_sample_rate"], 1)


if __name__ == "__main__":
    unittest.main()
