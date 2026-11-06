import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from qsupply.api.app import create_app
from qsupply.backends.qulacs import QulacsBackend
from qsupply.backends.qiskit import QiskitBackend


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
        self.assertGreaterEqual(result["exact_reference_time_seconds"], 0)
        self.assertEqual(result["full_energy"], result["ising_energy"])
        self.assertEqual(sum(item["count"] for item in result["sample_frequencies"]), 32)
        self.assertIsInstance(result["feasible"], bool)
        self.assertGreaterEqual(result["feasible_sample_rate"], 0)
        self.assertLessEqual(result["feasible_sample_rate"], 1)


if __name__ == "__main__":
    unittest.main()
