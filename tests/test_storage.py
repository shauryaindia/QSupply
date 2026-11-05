import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from qsupply.api.storage import (
    PostgreSQLRunStore,
    SQLiteRunStore,
    create_run_store,
    normalize_database_url,
)
from qsupply.api.schemas import RunResult


def valid_result(**updates):
    result = {
        "instance_id": "synthetic-5",
        "instance_name": "Synthetic CVRP (5 customers)",
        "synthetic": True,
        "customer_count": 5,
        "solver": "exact",
        "routes": {"vehicle-1": ["depot", "customer-1", "depot"]},
        "feasible": True,
        "total_distance": 17.0,
        "total_distance_exact": "17",
        "elapsed_seconds": 0.01,
    }
    return {**result, **updates}


class TestSQLiteRunStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "runs.sqlite3"
        self.store = SQLiteRunStore(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_update_get_and_list_persist_full_run_state(self):
        request = {
            "instance_id": "synthetic-5",
            "solver": "nearest-neighbor+2-opt",
            "include_exact_reference": True,
        }
        queued = self.store.create(
            "run-1", "synthetic-5", "nearest-neighbor+2-opt", request
        )
        self.assertEqual(queued.status, "queued")
        self.assertIsNone(queued.result)

        self.store.mark_running("run-1")
        result = valid_result(total_distance_exact="17/3")
        self.store.mark_completed("run-1", result)
        completed = self.store.get("run-1")
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.result, RunResult.model_validate(result))
        self.assertIsNotNone(completed.started_at)
        self.assertIsNotNone(completed.completed_at)
        self.assertEqual(self.store.list()[0].id, "run-1")

        with self.store._connection() as connection:
            request_json = connection.execute(
                "SELECT request_json FROM optimization_runs WHERE id = ?",
                ("run-1",),
            ).fetchone()["request_json"]
        self.assertEqual(json.loads(request_json), request)

    def test_failure_state_and_invalid_transitions_are_consistent(self):
        self.store.create("run-fail", "synthetic-5", "exact")
        self.store.mark_failed("run-fail", "solver error")
        failed = self.store.get("run-fail")
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error, "solver error")
        self.assertIsNotNone(failed.completed_at)
        with self.assertRaisesRegex(RuntimeError, "status transition"):
            self.store.mark_running("run-fail")

    def test_transaction_rolls_back_a_failed_result_update(self):
        self.store.create("run-rollback", "synthetic-5", "exact")
        self.store.mark_running("run-rollback")
        with self.store._connection() as connection:
            connection.execute(
                """CREATE TRIGGER reject_result
                   BEFORE UPDATE OF result_json ON optimization_runs
                   BEGIN SELECT RAISE(ABORT, 'forced test failure'); END"""
            )

        with self.assertRaises(sqlite3.IntegrityError):
            self.store.mark_completed("run-rollback", {"feasible": True})

        unchanged = self.store.get("run-rollback")
        self.assertEqual(unchanged.status, "running")
        self.assertIsNone(unchanged.result)
        self.assertIsNone(unchanged.completed_at)

    def test_legacy_sqlite_database_is_migrated_without_losing_rows(self):
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """CREATE TABLE optimization_runs (
                    id TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL,
                    solver TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    result_json TEXT,
                    error TEXT
                )"""
            )
            connection.execute(
                """INSERT INTO optimization_runs
                   (id, instance_id, solver, status, created_at, result_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    "legacy-run",
                    "synthetic-5",
                    "nearest-neighbor",
                    "completed",
                    "2025-01-02T03:04:05+00:00",
                    json.dumps(valid_result()),
                ),
            )

        restarted_store = SQLiteRunStore(self.database)
        legacy = restarted_store.get("legacy-run")
        self.assertEqual(legacy.status, "completed")
        self.assertEqual(legacy.result, RunResult.model_validate(valid_result()))
        with restarted_store._connection() as connection:
            versions = {
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations"
                ).fetchall()
            }
            request_json = connection.execute(
                "SELECT request_json FROM optimization_runs WHERE id = ?",
                ("legacy-run",),
            ).fetchone()["request_json"]
        self.assertEqual(versions, {1, 2, 3, 4})
        self.assertEqual(json.loads(request_json), {})

    def test_global_optimization_results_persist_across_store_restarts(self):
        weights = {"cost": 40, "delivery_time": 25, "carbon": 20, "resilience": 15}
        self.store.create_global_optimization(
            "global-run-1", "synthetic-suez-capacity-restriction", weights
        )
        result = {
            "id": "global-run-1",
            "status": "completed",
            "synthetic": True,
            "scenario_id": "synthetic-suez-capacity-restriction",
        }
        self.store.complete_global_optimization("global-run-1", result)

        restarted = SQLiteRunStore(self.database)
        record = restarted.get_global_optimization("global-run-1")
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["weights"], weights)
        self.assertEqual(record["result"], result)
        self.assertEqual(
            [item["id"] for item in restarted.list_global_optimizations()],
            ["global-run-1"],
        )

    def test_custom_scenarios_persist_and_delete_without_touching_saved_runs(self):
        scenario = self.store.create_global_scenario(
            "custom-1",
            "Port closure",
            "Synthetic test scenario",
            {"closed_link_ids": ["link-1"], "transit_time_additions": {"link-2": 3}},
        )
        self.assertEqual(scenario["name"], "Port closure")
        self.store.create_global_optimization("run-scenario", "custom-1", {"cost": 100})
        self.store.complete_global_optimization(
            "run-scenario", {"scenario_snapshot": scenario}
        )
        restarted = SQLiteRunStore(self.database)
        self.assertEqual(restarted.get_global_scenario("custom-1"), scenario)
        self.assertEqual(restarted.list_global_scenarios(), [scenario])
        self.assertTrue(restarted.delete_global_scenario("custom-1"))
        self.assertFalse(restarted.delete_global_scenario("custom-1"))
        self.assertEqual(
            restarted.get_global_optimization("run-scenario")["result"]["scenario_snapshot"],
            scenario,
        )

    def test_global_optimization_status_transitions_are_guarded(self):
        self.store.create_global_optimization("global-failed", None, {"cost": 100})
        self.store.fail_global_optimization("global-failed", "forced failure")
        with self.assertRaisesRegex(RuntimeError, "no longer running"):
            self.store.complete_global_optimization("global-failed", {"status": "completed"})
        record = self.store.get_global_optimization("global-failed")
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["error"], "forced failure")

    def test_concurrent_run_writes_remain_readable(self):
        def create_and_finish(index: int) -> str:
            run_id = f"parallel-{index}"
            self.store.create(run_id, "synthetic-5", "nearest-neighbor")
            self.store.mark_running(run_id)
            self.store.mark_completed(run_id, valid_result())
            return run_id

        with ThreadPoolExecutor(max_workers=8) as executor:
            run_ids = list(executor.map(create_and_finish, range(20)))
        records = [self.store.get(run_id) for run_id in run_ids]
        self.assertTrue(all(record.status == "completed" for record in records))
        self.assertEqual(len(self.store.list(limit=100)), 20)

    def test_database_url_selects_postgres_and_unset_url_falls_back_to_sqlite(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgres://db.example.invalid/q"},
        ):
            selected = create_run_store()
            self.assertIsInstance(selected, PostgreSQLRunStore)
        with patch.dict(
            os.environ,
            {"QSUPPLY_RUNS_DB": str(self.database)},
            clear=True,
        ):
            selected = create_run_store()
            self.assertIsInstance(selected, SQLiteRunStore)
            selected.create("fallback", "synthetic-5", "exact")
            self.assertTrue(self.database.exists())


class TestPostgreSQLConfiguration(unittest.TestCase):
    def test_render_url_schemes_are_normalized_without_changing_credentials(self):
        render_url = "postgres://host.internal/db?sslmode=require"
        self.assertEqual(
            normalize_database_url(render_url),
            "postgresql://host.internal/db?sslmode=require",
        )
        self.assertEqual(
            normalize_database_url("postgresql+psycopg://host/db"),
            "postgresql://host/db",
        )

    def test_non_postgres_url_is_rejected_without_echoing_value(self):
        secret_like_value = "sqlite:///private/path"
        with self.assertRaisesRegex(ValueError, "PostgreSQL URL scheme") as error:
            normalize_database_url(secret_like_value)
        self.assertNotIn(secret_like_value, str(error.exception))


@unittest.skipUnless(
    os.environ.get("QSUPPLY_TEST_POSTGRES_URL"),
    "Set QSUPPLY_TEST_POSTGRES_URL to run real PostgreSQL integration coverage",
)
class TestPostgreSQLRunStoreIntegration(unittest.TestCase):
    def test_create_update_and_retrieve_across_store_restarts(self):
        database_url = os.environ["QSUPPLY_TEST_POSTGRES_URL"]
        run_id = f"storage-integration-{uuid4()}"
        store = PostgreSQLRunStore(database_url)
        request = {
            "instance_id": "synthetic-5",
            "solver": "exact",
            "include_exact_reference": False,
        }
        try:
            store.create(run_id, "synthetic-5", "exact", request)
            store.mark_running(run_id)
            result = valid_result(total_distance_exact="4/3")
            store.mark_completed(run_id, result)

            restarted_store = PostgreSQLRunStore(database_url)
            record = restarted_store.get(run_id)
            self.assertEqual(record.status, "completed")
            self.assertEqual(record.result, RunResult.model_validate(result))
            self.assertIn(run_id, {item.id for item in restarted_store.list()})
        finally:
            with store._connection() as connection:
                store._execute(
                    connection,
                    "DELETE FROM optimization_runs WHERE id = ?",
                    (run_id,),
                )


if __name__ == "__main__":
    unittest.main()
