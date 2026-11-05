"""Transactional run-history stores for local SQLite and PostgreSQL deployments."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit

from .schemas import RunRecord

_POSTGRES_SCHEMA_LOCK = 0x51535550504C59
_LATEST_SCHEMA_VERSION = 3


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_database_path() -> Path:
    configured = os.environ.get("QSUPPLY_RUNS_DB")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".qsupply" / "runs.sqlite3"


def normalize_database_url(database_url: str) -> str:
    """Normalize Render/PostgreSQL URL schemes without exposing URL contents."""
    parts = urlsplit(database_url.strip())
    scheme = parts.scheme.lower()
    if scheme == "postgres":
        scheme = "postgresql"
    elif scheme == "postgresql+psycopg":
        scheme = "postgresql"
    if scheme != "postgresql":
        raise ValueError("DATABASE_URL must use a PostgreSQL URL scheme")
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


class RunStore:
    """Shared run-store behavior; each operation owns its own transaction."""

    dialect: str

    def __init__(self) -> None:
        self._initialized = False
        self._initialization_lock = threading.Lock()

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        raise NotImplementedError

    def _execute(
        self, connection: Any, sql: str, parameters: tuple[Any, ...] = ()
    ) -> Any:
        if self.dialect == "postgresql":
            sql = sql.replace("?", "%s")
        return connection.execute(sql, parameters)

    def _table_columns(self, connection: Any) -> set[str]:
        if self.dialect == "sqlite":
            rows = self._execute(
                connection, "PRAGMA table_info(optimization_runs)"
            ).fetchall()
            return {row["name"] for row in rows}
        rows = self._execute(
            connection,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ?",
            ("optimization_runs",),
        ).fetchall()
        return {row["column_name"] for row in rows}

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._initialization_lock:
            if self._initialized:
                return
            with self._connection() as connection:
                if self.dialect == "sqlite":
                    connection.execute("BEGIN IMMEDIATE")
                if self.dialect == "postgresql":
                    self._execute(
                        connection,
                        "SELECT pg_advisory_xact_lock(?)",
                        (_POSTGRES_SCHEMA_LOCK,),
                    )
                    migration_time_type = "TIMESTAMPTZ"
                    timestamp_type = "TIMESTAMPTZ"
                else:
                    migration_time_type = "TEXT"
                    timestamp_type = "TEXT"

                self._execute(
                    connection,
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    f"version INTEGER PRIMARY KEY, applied_at {migration_time_type} NOT NULL)",
                )
                applied = {
                    row["version"]
                    for row in self._execute(
                        connection, "SELECT version FROM schema_migrations"
                    ).fetchall()
                }
                if applied and max(applied) > _LATEST_SCHEMA_VERSION:
                    raise RuntimeError(
                        "Run-history schema is newer than this QSupply version"
                    )

                if 1 not in applied:
                    self._execute(
                        connection,
                        "CREATE TABLE IF NOT EXISTS optimization_runs ("
                        "id TEXT PRIMARY KEY,"
                        "instance_id TEXT NOT NULL,"
                        "solver TEXT NOT NULL,"
                        "status TEXT NOT NULL,"
                        f"created_at {timestamp_type} NOT NULL,"
                        f"started_at {timestamp_type},"
                        f"completed_at {timestamp_type},"
                        "result_json TEXT,"
                        "error TEXT)",
                    )
                    self._execute(
                        connection,
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                        (1, self._timestamp()),
                    )
                    applied.add(1)

                if 2 not in applied:
                    columns = self._table_columns(connection)
                    if "request_json" not in columns:
                        self._execute(
                            connection,
                            "ALTER TABLE optimization_runs ADD COLUMN "
                            "request_json TEXT NOT NULL DEFAULT '{}'",
                        )
                    self._execute(
                        connection,
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                        (2, self._timestamp()),
                    )
                    applied.add(2)

                if 3 not in applied:
                    self._execute(
                        connection,
                        "CREATE TABLE IF NOT EXISTS global_optimization_runs ("
                        "id TEXT PRIMARY KEY,"
                        "status TEXT NOT NULL,"
                        f"created_at {timestamp_type} NOT NULL,"
                        "scenario_id TEXT,"
                        "weights_json TEXT NOT NULL,"
                        "result_json TEXT,"
                        "error TEXT)",
                    )
                    self._execute(
                        connection,
                        "CREATE INDEX IF NOT EXISTS idx_global_runs_created_at "
                        "ON global_optimization_runs(created_at DESC)",
                    )
                    self._execute(
                        connection,
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                        (3, self._timestamp()),
                    )

                self._execute(
                    connection,
                    "CREATE INDEX IF NOT EXISTS idx_runs_created_at "
                    "ON optimization_runs(created_at DESC)",
                )
                columns = self._table_columns(connection)
                required = {
                    "id",
                    "instance_id",
                    "solver",
                    "status",
                    "created_at",
                    "started_at",
                    "completed_at",
                    "result_json",
                    "error",
                    "request_json",
                }
                if not required.issubset(columns):
                    raise RuntimeError("Run-history schema is missing required columns")
            self._initialized = True

    def _timestamp(self) -> datetime | str:
        now = utc_now()
        return now if self.dialect == "postgresql" else now.isoformat()

    def create(
        self,
        run_id: str,
        instance_id: str,
        solver: str,
        request_payload: dict[str, Any] | None = None,
    ) -> RunRecord:
        self.initialize()
        with self._connection() as connection:
            self._execute(
                connection,
                "INSERT INTO optimization_runs "
                "(id, instance_id, solver, status, created_at, request_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    instance_id,
                    solver,
                    "queued",
                    self._timestamp(),
                    json.dumps(request_payload or {}, separators=(",", ":")),
                ),
            )
        record = self.get(run_id)
        if record is None:
            raise RuntimeError("Run creation did not persist a record")
        return record

    def _transition(
        self,
        run_id: str,
        from_statuses: tuple[str, ...],
        sql: str,
        params: tuple[Any, ...],
    ) -> None:
        self.initialize()
        placeholders = ", ".join("?" for _ in from_statuses)
        statement = f"{sql} WHERE id = ? AND status IN ({placeholders})"
        with self._connection() as connection:
            cursor = self._execute(
                connection, statement, (*params, run_id, *from_statuses)
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Run not found or status transition is no longer valid"
                )

    def mark_running(self, run_id: str) -> None:
        self._transition(
            run_id,
            ("queued",),
            "UPDATE optimization_runs SET status='running', started_at=?",
            (self._timestamp(),),
        )

    def mark_completed(self, run_id: str, result: dict[str, Any]) -> None:
        self._transition(
            run_id,
            ("running",),
            "UPDATE optimization_runs SET status='completed', completed_at=?, "
            "result_json=?, error=NULL",
            (self._timestamp(), json.dumps(result, separators=(",", ":"))),
        )

    def mark_failed(self, run_id: str, message: str) -> None:
        self._transition(
            run_id,
            ("queued", "running"),
            "UPDATE optimization_runs SET status='failed', completed_at=?, error=?",
            (self._timestamp(), message),
        )

    @staticmethod
    def _record(row: Any | None) -> RunRecord | None:
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
            row = self._execute(
                connection,
                "SELECT * FROM optimization_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        return self._record(row)

    def list(self, limit: int = 100) -> list[RunRecord]:
        self.initialize()
        with self._connection() as connection:
            rows = self._execute(
                connection,
                "SELECT * FROM optimization_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [record for row in rows if (record := self._record(row)) is not None]

    @staticmethod
    def _global_record(row: Any | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": row["id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "scenario_id": row["scenario_id"],
            "weights": json.loads(row["weights_json"]),
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": row["error"],
        }

    def create_global_optimization(
        self, run_id: str, scenario_id: str | None, weights: dict[str, int]
    ) -> dict[str, Any]:
        self.initialize()
        with self._connection() as connection:
            self._execute(
                connection,
                "INSERT INTO global_optimization_runs "
                "(id, status, created_at, scenario_id, weights_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    run_id,
                    "running",
                    self._timestamp(),
                    scenario_id,
                    json.dumps(weights, separators=(",", ":")),
                ),
            )
        record = self.get_global_optimization(run_id)
        if record is None:
            raise RuntimeError("Global optimization run was not persisted")
        return record

    def complete_global_optimization(
        self, run_id: str, result: dict[str, Any]
    ) -> None:
        self.initialize()
        with self._connection() as connection:
            cursor = self._execute(
                connection,
                "UPDATE global_optimization_runs SET status='completed', "
                "result_json=?, error=NULL WHERE id=? AND status='running'",
                (json.dumps(result, separators=(",", ":")), run_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Global optimization run is missing or no longer running")

    def fail_global_optimization(self, run_id: str, message: str) -> None:
        self.initialize()
        with self._connection() as connection:
            cursor = self._execute(
                connection,
                "UPDATE global_optimization_runs SET status='failed', error=? "
                "WHERE id=? AND status='running'",
                (message, run_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Global optimization run is missing or no longer running")

    def get_global_optimization(self, run_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._connection() as connection:
            row = self._execute(
                connection,
                "SELECT * FROM global_optimization_runs WHERE id=?",
                (run_id,),
            ).fetchone()
        return self._global_record(row)

    def list_global_optimizations(self, limit: int = 100) -> list[dict[str, Any]]:
        self.initialize()
        with self._connection() as connection:
            rows = self._execute(
                connection,
                "SELECT * FROM global_optimization_runs "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [record for row in rows if (record := self._global_record(row)) is not None]


class SQLiteRunStore(RunStore):
    """SQLite run store retained for local use and existing tests."""

    dialect = "sqlite"

    def __init__(self, database_path: str | Path | None = None) -> None:
        super().__init__()
        self.path = (
            Path(database_path) if database_path is not None else default_database_path()
        )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=15000")
        with closing(connection):
            with connection:
                yield connection


class PostgreSQLRunStore(RunStore):
    """PostgreSQL store using a fresh transactional Psycopg connection per operation."""

    dialect = "postgresql"

    def __init__(self, database_url: str) -> None:
        super().__init__()
        self._database_url = normalize_database_url(database_url)

    def __repr__(self) -> str:
        return "PostgreSQLRunStore(<DATABASE_URL configured>)"

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError(
                "PostgreSQL was selected by DATABASE_URL, but the Psycopg driver is not installed"
            ) from error
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection


def create_run_store(
    database_path: str | Path | None = None,
    database_url: str | None = None,
) -> RunStore:
    """Select PostgreSQL from DATABASE_URL, otherwise use the SQLite fallback."""
    if database_url is not None:
        return PostgreSQLRunStore(database_url)
    if database_path is not None:
        return SQLiteRunStore(database_path)
    configured_url = os.environ.get("DATABASE_URL")
    if configured_url:
        return PostgreSQLRunStore(configured_url)
    return SQLiteRunStore()
