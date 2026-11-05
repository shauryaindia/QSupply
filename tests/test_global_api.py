import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from qsupply.api.app import create_app


class TestGlobalMultimodalAPI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "runs.sqlite3"
        self.app = create_app(self.database)
        self.context = TestClient(self.app)
        self.client = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def test_global_network_and_shipments_are_geospatial_and_synthetic(self):
        network = self.client.get("/api/v1/global/network")
        self.assertEqual(network.status_code, 200)
        body = network.json()
        self.assertTrue(body["synthetic"])
        self.assertEqual(len(body["nodes"]), 32)
        self.assertTrue(
            all(node["latitude"] is not None and node["longitude"] is not None for node in body["nodes"])
        )
        self.assertTrue(all(link["geometry"] and link["distance_km"] for link in body["links"]))
        shipments = self.client.get("/api/v1/global/shipments").json()
        self.assertEqual({shipment["id"] for shipment in shipments}, {"EXP-104", "EXP-205"})
        self.assertTrue(all(shipment["synthetic"] for shipment in shipments))
        self.assertEqual(
            self.client.get("/api/v1/global/scenarios").json()[0]["id"],
            "synthetic-suez-capacity-restriction",
        )

    def test_route_generation_returns_validated_baseline_and_disrupted_options(self):
        request = {"shipment_id": "EXP-104", "max_routes": 8}
        baseline = self.client.post("/api/v1/global/routes", json=request)
        disrupted = self.client.post(
            "/api/v1/global/routes",
            json={**request, "scenario_id": "synthetic-suez-capacity-restriction"},
        )
        self.assertEqual(baseline.status_code, 200)
        self.assertEqual(disrupted.status_code, 200)
        self.assertGreaterEqual(len(baseline.json()), 3)
        self.assertTrue(all(route["geometry"] for route in baseline.json()))
        self.assertTrue(
            any("sea-jebel-rotterdam" not in route["link_ids"] for route in disrupted.json())
        )
        self.assertEqual(
            self.client.post("/api/v1/global/routes", json={"shipment_id": "missing"}).status_code,
            404,
        )

    def test_route_intelligence_uses_route_metrics_and_fixed_baseline(self):
        response = self.client.post(
            "/api/v1/global/route-intelligence",
            json={
                "shipment_id": "EXP-104",
                "scenario_id": "synthetic-suez-capacity-restriction",
                "weights": {"cost": 20, "delivery_time": 30, "carbon": 35, "resilience": 15},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["synthetic"])
        self.assertTrue(body["recovery_feasible"])
        self.assertIn(body["assignment_route_id"], {route["id"] for route in body["routes"]})
        self.assertFalse(next(iter(body["analyses"].values()))["uses_llm"])
        self.assertEqual(body["rankings"]["balanced"][0], body["recommended_route_id"])
        self.assertEqual(set(body["analyses"]), {route["id"] for route in body["routes"]})
        for route in body["routes"]:
            analysis = body["analyses"][route["id"]]
            self.assertEqual(analysis["delta_vs_baseline"]["baseline_route_id"], body["baseline_route"]["id"])
            baseline = body["baseline_route"]
            baseline_cost = baseline["freight_cost"] + max(0, baseline["transit_time"] - 24) * 18
            route_cost = route["freight_cost"] + max(0, route["transit_time"] - 24) * 18
            self.assertAlmostEqual(analysis["total_cost"], route_cost)
            self.assertAlmostEqual(analysis["delta_vs_baseline"]["cost_savings"], baseline_cost - route_cost)
            self.assertAlmostEqual(analysis["delta_vs_baseline"]["time_savings_days"], baseline["transit_time"] - route["transit_time"])
            self.assertAlmostEqual(analysis["delta_vs_baseline"]["carbon_savings_kg"], baseline["carbon_kg"] - route["carbon_kg"])
            self.assertAlmostEqual(
                sum(analysis["carbon_by_mode_kg"].values()), route["carbon_kg"]
            )
            self.assertTrue(analysis["recommendation"])
            self.assertEqual(analysis["analysis_type"], "deterministic_rule_based")
        self.assertTrue(any("customs" in assumption.lower() for assumption in body["assumptions"]))

    def test_global_optimization_reallocates_capacity_and_persists_history(self):
        response = self.client.post("/api/v1/global/optimizations", json={})
        self.assertEqual(response.status_code, 201, response.text)
        record = response.json()
        result = record["result"]
        self.assertEqual(record["status"], "completed")
        self.assertTrue(result["recovery_feasible"])
        self.assertEqual(result["algorithm"], "bounded route generation + exact candidate assignment enumeration")
        self.assertEqual(result["optimality_scope"], "exact only over the generated candidate routes; route generation is bounded")
        self.assertEqual(result["baseline"]["capacity_usage"]["sea-jebel-rotterdam"], 4)
        self.assertLessEqual(result["recovery"]["capacity_usage"]["sea-jebel-rotterdam"], 3)
        self.assertNotEqual(
            result["baseline"]["metrics"]["total_cost"],
            result["recovery"]["metrics"]["total_cost"],
        )
        self.assertEqual(
            self.client.get("/api/v1/global/optimizations").json()["items"][0]["id"],
            record["id"],
        )
        retrieved = self.client.get(f"/api/v1/global/optimizations/{record['id']}")
        self.assertEqual(retrieved.status_code, 200)
        self.assertEqual(retrieved.json(), record)
        report = self.client.get(f"/api/v1/global/optimizations/{record['id']}/report.csv")
        self.assertEqual(report.status_code, 200)
        self.assertIn("text/csv", report.headers["content-type"])
        self.assertIn("QSupply synthetic route comparison report", report.text)
        self.assertIn("Carbon estimate (kgCO2e)", report.text)
        self.assertIn("sea-jebel-rotterdam", report.text)
        self.assertEqual(
            self.client.get("/api/v1/global/optimizations/not-a-run/report.csv").status_code,
            404,
        )

        position_url = (
            f"/api/v1/global/optimizations/{record['id']}"
            "/shipments/EXP-104/position?elapsed_time=7"
        )
        first = self.client.get(position_url)
        second = self.client.get(position_url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(first.json()["current_leg_id"], "sea-singapore-colombo")
        self.assertEqual(first.json()["status"], "in_transit")

        restarted = TestClient(create_app(self.database))
        with restarted:
            self.assertEqual(
                restarted.get(f"/api/v1/global/optimizations/{record['id']}").json(), record
            )

    def test_invalid_weights_scenarios_and_unknown_runs_are_rejected(self):
        invalid_weights = self.client.post(
            "/api/v1/global/optimizations",
            json={"weights": {"cost": 50, "delivery_time": 25, "carbon": 20, "resilience": 0}},
        )
        self.assertEqual(invalid_weights.status_code, 422)
        unknown_scenario = self.client.post(
            "/api/v1/global/optimizations", json={"scenario_id": "not-a-scenario"}
        )
        self.assertEqual(unknown_scenario.status_code, 404)
        unknown_analysis_scenario = self.client.post(
            "/api/v1/global/route-intelligence",
            json={"shipment_id": "EXP-104", "scenario_id": "not-a-scenario"},
        )
        self.assertEqual(unknown_analysis_scenario.status_code, 404)
        self.assertEqual(
            self.client.get("/api/v1/global/optimizations/not-a-run").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/global/optimizations/not-a-run/shipments/EXP-104/position"
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
