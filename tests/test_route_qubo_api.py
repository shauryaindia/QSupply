import unittest
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from qsupply.api.app import create_app
from qsupply.backends.qiskit import QiskitBackend
from qsupply.backends.qulacs import QulacsBackend


class TestRouteQUBOAPI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.context = TestClient(create_app(f"{self.temp_dir.name}/runs.sqlite3"))
        self.client = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def test_example_exposes_candidate_set_qubo_variables_and_backend_availability(self):
        response = self.client.get("/api/v1/quantum/route-assignment/example")
        self.assertEqual(response.status_code, 200, response.text)
        example = response.json()
        self.assertTrue(example["synthetic"])
        self.assertEqual(example["shipment_ids"], ["EXP-104", "EXP-407"])
        self.assertEqual(example["variable_count"], 8)
        self.assertEqual(example["decision_variable_count"], 6)
        self.assertEqual(example["slack_variable_count"], 2)
        self.assertEqual(len(example["variable_mapping"]), 8)
        self.assertEqual(example["variable_mapping"][-1]["slack_weight"], 2)
        self.assertIn("port-road access", example["scenario_description"])
        self.assertEqual(len(example["candidates"]["EXP-104"]), 3)
        self.assertEqual(len(example["candidates"]["EXP-407"]), 3)
        self.assertEqual(len(example["qubo_coefficients"][0]), 3)
        methods = {item["id"]: item for item in example["available_methods"]}
        self.assertTrue(methods["exact-qubo"]["available"])
        self.assertTrue(methods["classical-assignment"]["available"])
        self.assertIn("qiskit", methods)
        self.assertIn("qulacs", methods)

    def test_exact_qbo_run_returns_feasible_route_plan_and_energy_reconciliation(self):
        response = self.client.post(
            "/api/v1/quantum/route-assignment/runs", json={"backend": "exact-qubo"}
        )
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["exact_reference_feasible"])
        self.assertTrue(result["classical_reference_feasible"])
        self.assertEqual(result["exact_reference_routes"], result["classical_reference_routes"])
        self.assertTrue(result["feasible"])
        self.assertEqual(result["variable_count"], 8)
        self.assertEqual(len(result["variable_mapping"]), 8)
        self.assertEqual(set(result["decoded_routes"]), {"EXP-104", "EXP-407"})
        self.assertEqual(
            result["full_penalized_energy"], result["exact_reference_objective"]
        )
        self.assertEqual(result["full_penalized_energy"], result["exact_reference_full_energy"])
        self.assertEqual(result["full_penalized_energy"], result["ising_energy"])
        self.assertEqual(result["objective_gap_percent"], 0.0)
        self.assertEqual(result["capacity_usage"]["road-shanghai-port"], 2)
        self.assertIn("exact optimum over", result["reference_scope"])

    def test_classical_reference_uses_same_qubo_register_and_feasibility(self):
        response = self.client.post(
            "/api/v1/quantum/route-assignment/runs",
            json={"backend": "classical-assignment", "weights": {
                "cost": 20, "delivery_time": 30, "carbon": 30, "resilience": 20
            }},
        )
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        self.assertTrue(result["feasible"])
        self.assertTrue(result["exact_reference_feasible"])
        self.assertEqual(result["business_metrics"]["weighted_objective"], result["classical_reference_objective"])
        self.assertEqual(result["full_penalized_energy"], result["business_metrics"]["weighted_objective"])
        self.assertAlmostEqual(result["objective_gap_percent"], 0.0, places=10)
        self.assertEqual(result["backend_id"], "classical-assignment")
        self.assertTrue(result["timing_scope"])

    def test_unknown_and_unavailable_backend_are_explicit(self):
        unknown = self.client.post(
            "/api/v1/quantum/route-assignment/runs", json={"backend": "qarp"}
        )
        self.assertEqual(unknown.status_code, 422)
        capabilities = {
            item["id"]: item
            for item in self.client.get("/api/v1/quantum/route-assignment/example").json()["available_methods"]
        }
        unavailable = next(
            (backend_id for backend_id in ("qiskit", "qulacs") if not capabilities[backend_id]["available"]),
            None,
        )
        if unavailable:
            response = self.client.post(
                "/api/v1/quantum/route-assignment/runs", json={"backend": unavailable}
            )
            self.assertEqual(response.status_code, 503)
            self.assertIn("unavailable", response.json()["detail"])

    def test_rejects_invalid_weights_and_extra_request_fields(self):
        invalid = self.client.post(
            "/api/v1/quantum/route-assignment/runs",
            json={"backend": "exact-qubo", "weights": {
                "cost": 25, "delivery_time": 25, "carbon": 25, "resilience": 20
            }},
        )
        self.assertEqual(invalid.status_code, 422)
        extra = self.client.post(
            "/api/v1/quantum/route-assignment/runs",
            json={"backend": "exact-qubo", "pretend_quantum_advantage": True},
        )
        self.assertEqual(extra.status_code, 422)

    @unittest.skipUnless(
        QiskitBackend.is_available() and QulacsBackend.is_available(),
        "Qiskit and Qulacs SDKs are both required for API integration coverage",
    )
    def test_api_executes_route_qubo_on_both_available_qaoa_backends(self):
        for backend in ("qiskit", "qulacs"):
            with self.subTest(backend=backend):
                response = self.client.post(
                    "/api/v1/quantum/route-assignment/runs",
                    json={
                        "backend": backend,
                        "depth": 1,
                        "max_iterations": 1,
                        "shots": 16,
                        "random_seed": 2718,
                    },
                )
                self.assertEqual(response.status_code, 201, response.text)
                result = response.json()
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["backend_id"], backend)
                self.assertEqual(result["execution_mode"], "local_simulator")
                self.assertEqual(result["variable_count"], 8)
                self.assertGreaterEqual(result["optimization_time_seconds"], 0)
                self.assertGreaterEqual(result["circuit_execution_time_seconds"], 0)
                self.assertIn("whole QAOA solver call", result["timing_scope"])
                self.assertIn(
                    "local sample-call wall time",
                    result["execution_metadata"]["timing_scope"],
                )
                self.assertIsNotNone(result["best_binary_assignment"])
                self.assertEqual(
                    result["full_penalized_energy"], result["ising_energy"]
                )
                if result["feasible"]:
                    self.assertTrue(result["decoded_routes"])
                    self.assertIsNotNone(result["business_metrics"])
                    self.assertIsNotNone(result["objective_gap_percent"])
                else:
                    self.assertIsNone(result["business_metrics"])
                    self.assertIsNone(result["objective_gap_percent"])
                    self.assertTrue(result["feasibility_violations"])
