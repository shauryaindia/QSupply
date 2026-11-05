"""Small SQLite-backed persistence for local optimization run history."""

import json
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schemas import RunRecord


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_database_path() -> Path:
    configured = os.environ.get("QSUPPLY_RUNS_DB")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".qsupply" / "runs.sqlite3"


class SQLiteRunStore:
    """Persist run requests and results in one local SQLite database."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.path = Path(database_path) if database_path is not None else default_database_path()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        """Commit/rollback a short operation and always close its connection."""
        with closing(self._connect()) as connection:
            with connection:
                yield connection

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS optimization_runs (
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
                "CREATE INDEX IF NOT EXISTS idx_runs_created_at "
                "ON optimization_runs(created_at DESC)"
            )

    def create(self, run_id: str, instance_id: str, solver: str) -> RunRecord:
        self.initialize()
        created_at = utc_now()
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO optimization_runs "
                "(id, instance_id, solver, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, instance_id, solver, "queued", created_at),
            )
        record = self.get(run_id)
        assert record is not None
        return record

    def mark_running(self, run_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE optimization_runs SET status='running', started_at=? WHERE id=?",
                (utc_now(), run_id),
            )

    def mark_completed(self, run_id: str, result: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE optimization_runs SET status='completed', completed_at=?, "
                "result_json=?, error=NULL WHERE id=?",
                (utc_now(), json.dumps(result, separators=(",", ":")), run_id),
            )

    def mark_failed(self, run_id: str, message: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE optimization_runs SET status='failed', completed_at=?, error=? "
                "WHERE id=?",
                (utc_now(), message, run_id),
            )

    @staticmethod
    def _record(row: sqlite3.Row | None) -> RunRecord | None:
        if row is None:
            return None
        result = json.loads(row["result_json"]) if row["result_json"] else None
        return RunRecord(
            id=row["id"],
            instance_id=row["instance_id"],
            solver=row["solver"],
            status=row["status"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            result=result,
            error=row["error"],
        )

    def get(self, run_id: str) -> RunRecord | None:
        self.initialize()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM optimization_runs WHERE id=?", (run_id,)
            ).fetchone()
        return self._record(row)

    def list(self, limit: int = 100) -> list[RunRecord]:
        self.initialize()
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM optimization_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [record for row in rows if (record := self._record(row)) is not None]
