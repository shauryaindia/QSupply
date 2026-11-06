import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from qsupply import ExactCVRPSolver, NearestNeighborTwoOptSolver, generate_synthetic_cvrp
from qsupply.backends.qulacs import QulacsBackend
from qsupply.api.app import create_app


class TestQSupplyAPI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "runs.sqlite3"
        self.app = create_app(self.database)
        self.client_context = TestClient(self.app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def submit(self, instance_id="synthetic-5", solver="nearest-neighbor+2-opt", **extra):
        return self.client.post(
            "/api/v1/runs",
            json={"instance_id": instance_id, "solver": solver, **extra},
        )

    def test_health_capabilities_and_synthetic_instances(self):
        self.assertEqual(self.client.get("/api/v1/health").json(), {
            "status": "ok", "service": "q-supply-api"
        })
        capabilities = self.client.get("/api/v1/capabilities").json()
        self.assertEqual(capabilities["exact_cvrp_customer_limit"], 10)
        self.assertEqual(
            {solver["id"] for solver in capabilities["solvers"]},
            {"nearest-neighbor", "nearest-neighbor+2-opt", "exact"},
        )
        statuses = {feature["id"]: feature["status"] for feature in capabilities["features"]}
        self.assertEqual(statuses["qubo-formulation"], "available")
        self.assertEqual(statuses["milp"], "unavailable")
        integrations = {
            feature["id"]: feature["status"] for feature in capabilities["integrations"]
        }
        self.assertEqual(integrations["qiskit-qaoa"], "not_implemented")
        self.assertEqual(
            integrations["qulacs-qaoa"],
            "available" if QulacsBackend.is_available() else "optional_dependency_missing",
        )
        self.assertEqual(integrations["fujitsu-qarp"], "not_configured_or_verified")
        instances = self.client.get("/api/v1/instances").json()
        self.assertTrue(all(instance["synthetic"] for instance in instances))
        self.assertFalse(next(item for item in instances if item["id"] == "synthetic-11")["exact_supported"])

    def test_cors_allows_local_and_production_frontend_origins(self):
        allowed_origins = (
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://qsupply.netlify.app",
            "https://qsupply.macrovisionai.com",
        )

        for origin in allowed_origins:
            with self.subTest(origin=origin):
                response = self.client.get(
                    "/api/v1/health", headers={"Origin": origin}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers.get("access-control-allow-origin"), origin)

    def test_post_executes_actual_nearest_neighbor_and_persists_validated_routes(self):
        response = self.submit(solver="nearest-neighbor")
        self.assertEqual(response.status_code, 202)
        created = response.json()
        completed = self.client.get(f"/api/v1/runs/{created['id']}").json()
        self.assertEqual(completed["status"], "completed")
        result = completed["result"]
        problem = generate_synthetic_cvrp(5, 2031)
        self.assertTrue(result["feasible"])
        problem.validate_routes(result["routes"])
        self.assertAlmostEqual(
            result["total_distance"],
            float(problem.transportation_cost(result["routes"])),
        )
        expected = NearestNeighborTwoOptSolver().construct_initial_routes(problem)
        self.assertEqual(result["routes"], {vehicle: list(route) for vehicle, route in expected.items()})
        self.assertTrue(result["synthetic"])

    def test_post_executes_actual_two_opt_and_exact_solvers(self):
        heuristic_response = self.submit(solver="nearest-neighbor+2-opt", include_exact_reference=True)
        heuristic = self.client.get(f"/api/v1/runs/{heuristic_response.json()['id']}").json()
        self.assertEqual(heuristic["status"], "completed")
        self.assertIsNotNone(heuristic["result"]["exact_reference_distance"])
        self.assertGreaterEqual(heuristic["result"]["optimality_gap_percent"], 0)

        exact_response = self.submit(solver="exact")
        exact = self.client.get(f"/api/v1/runs/{exact_response.json()['id']}").json()
        problem = generate_synthetic_cvrp(5, 2031)
        expected = ExactCVRPSolver().solve(problem)
        self.assertEqual(exact["status"], "completed")
        problem.validate_routes(exact["result"]["routes"])
        self.assertEqual(
            exact["result"]["total_distance_exact"], str(expected.total_distance)
        )

    def test_rejects_unknown_instances_unsupported_solvers_and_extra_fields(self):
        self.assertEqual(self.submit(instance_id="missing").status_code, 404)
        self.assertEqual(self.submit(solver="milp").status_code, 422)
        extra = self.client.post(
            "/api/v1/runs",
            json={"instance_id": "synthetic-5", "solver": "exact", "made_up": True},
        )
        self.assertEqual(extra.status_code, 422)

    def test_enforces_exact_and_comparison_limits_before_creating_runs(self):
        exact = self.submit(instance_id="synthetic-11", solver="exact")
        self.assertEqual(exact.status_code, 422)
        self.assertIn("at most 10 customers", exact.json()["detail"])
        comparison = self.submit(
            instance_id="synthetic-11",
            solver="nearest-neighbor",
            include_exact_reference=True,
        )
        self.assertEqual(comparison.status_code, 422)
        self.assertEqual(self.client.get("/api/v1/runs").json()["items"], [])

    def test_run_history_survives_new_app_and_run_detail_has_404(self):
        response = self.submit(solver="nearest-neighbor")
        run_id = response.json()["id"]
        self.assertEqual(self.client.get("/api/v1/runs/not-a-run").status_code, 404)
        self.assertEqual(len(self.client.get("/api/v1/runs").json()["items"]), 1)

        second_app = create_app(self.database)
        with TestClient(second_app) as second_client:
            record = second_client.get(f"/api/v1/runs/{run_id}").json()
            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["id"], run_id)

    def test_demo_network_uses_validated_models_and_is_marked_synthetic(self):
        network = self.client.get("/api/v1/networks/demo").json()
        self.assertTrue(network["synthetic"])
        self.assertEqual(network["quantity_unit"], "load_unit")
        self.assertEqual({link["mode"] for link in network["links"]}, {"road", "rail", "sea", "air"})
        scenario = network["scenarios"][0]
        self.assertIn("sea-hormuz", scenario["closed_link_ids"])
        self.assertIn("no route recovery is computed", scenario["description"])


if __name__ == "__main__":
    unittest.main()
