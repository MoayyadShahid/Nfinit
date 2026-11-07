import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import ContextManager, Protocol
from uuid import uuid4

from .models import (
    CadRunRecord,
    CadRunResult,
    ProjectCreate,
    ProjectDetail,
    ProjectRevision,
    ProjectState,
    ProjectSummary,
    RunEvent,
    SubscriptionRecord,
)


class ProjectNotFoundError(LookupError):
    pass


class RevisionNotFoundError(LookupError):
    pass


class RunNotFoundError(LookupError):
    pass


class RunQuotaExceededError(RuntimeError):
    """An atomic run reservation found that one of the user's caps is full."""

    def __init__(self, reason: str, *, running: int = 0):
        super().__init__(reason)
        self.reason = reason
        self.running = running


class StorageQuotaExceededError(RuntimeError):
    """A write would take one user's persisted content over its hard cap."""

    def __init__(self, user_id: str, reason: str = "bytes"):
        super().__init__(reason)
        self.user_id = user_id
        self.reason = reason


class ThumbnailNotFoundError(LookupError):
    pass


@dataclass
class StoredMesh:
    """A project's latest built mesh. ``code_hash`` names the code it came from."""

    code_hash: str
    glb: bytes
    inspection: dict


# Thumbnail bytes stay out of list/detail queries; only the timestamp is read.
PROJECT_COLUMNS = "p.id, p.name, p.created_at, p.updated_at, p.thumbnail_updated_at"


LEGACY_LOCAL_USER_ID = "00000000-0000-4000-8000-000000000001"
DEFAULT_MAX_STORAGE_BYTES_PER_USER = 128 * 1024 * 1024


def max_storage_bytes_per_user() -> int:
    try:
        return max(
            1024 * 1024,
            int(
                os.getenv(
                    "CAD_MAX_STORAGE_BYTES_PER_USER",
                    str(DEFAULT_MAX_STORAGE_BYTES_PER_USER),
                )
            ),
        )
    except ValueError:
        return DEFAULT_MAX_STORAGE_BYTES_PER_USER


def _positive_setting(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def max_projects_per_user() -> int:
    return _positive_setting("CAD_MAX_PROJECTS_PER_USER", 100)


def max_revisions_per_user() -> int:
    return _positive_setting("CAD_MAX_REVISIONS_PER_USER", 1000)


# A run records at most MAX_RUN_EVENTS progress events, each with a message of
# at most MAX_EVENT_MESSAGE characters. Their storage is reserved when the run
# starts, so recording an event needs no storage check: that check sums every
# table the user owns, and a run records 10 to 20 events on its critical path.
MAX_RUN_EVENTS = 256
MAX_EVENT_MESSAGE = 500
RUN_EVENT_RESERVE_BYTES = MAX_RUN_EVENTS * 4 * (100 + 100 + MAX_EVENT_MESSAGE)


def event_within_budget(event: RunEvent) -> RunEvent | None:
    """The event as stored: its message capped, or None past the run's budget."""
    if event.seq > MAX_RUN_EVENTS:
        return None
    if len(event.message) > MAX_EVENT_MESSAGE:
        return event.model_copy(update={"message": event.message[:MAX_EVENT_MESSAGE]})
    return event


class ProjectStoreProtocol(Protocol):
    def billing_operation_lock(self, user_id: str) -> ContextManager[None]:
        """Serialize checkout creation and destructive billing changes."""
        ...

    def create_project(
        self, request: ProjectCreate, *, user_id: str
    ) -> ProjectDetail: ...

    def list_projects(
        self, *, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[ProjectSummary]: ...

    def get_project(self, project_id: str, *, user_id: str) -> ProjectDetail: ...

    def rename_project(
        self, project_id: str, name: str, *, user_id: str
    ) -> ProjectDetail: ...

    def add_revision(
        self, project_id: str, state: ProjectState, *, user_id: str
    ) -> ProjectRevision: ...

    def list_revisions(
        self,
        project_id: str,
        *,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProjectRevision]: ...

    def get_revision(
        self, project_id: str, revision_number: int, *, user_id: str
    ) -> ProjectRevision: ...

    def delete_project(self, project_id: str, *, user_id: str) -> None: ...

    def delete_account(self, *, user_id: str) -> None: ...

    def set_thumbnail(
        self, project_id: str, data: bytes, content_type: str, *, user_id: str
    ) -> None: ...

    def get_thumbnail(
        self, project_id: str, *, user_id: str
    ) -> tuple[bytes, str]: ...

    def get_mesh(self, project_id: str, *, user_id: str) -> StoredMesh | None: ...

    def save_mesh(
        self, project_id: str, mesh: StoredMesh, *, user_id: str
    ) -> None: ...

    def create_run(
        self,
        run_id: str,
        *,
        user_id: str,
        project_id: str | None,
        prompt: str,
        model_id: str,
    ) -> CadRunRecord: ...

    def create_run_with_quota(
        self,
        run_id: str,
        *,
        user_id: str,
        project_id: str | None,
        prompt: str,
        model_id: str,
        now: datetime,
        running_since: datetime,
        max_concurrent: int,
        max_hourly: int,
        max_daily: int,
    ) -> CadRunRecord:
        """Check every run cap and insert under one cross-process lock."""
        ...

    def finish_run(
        self,
        run_id: str,
        *,
        user_id: str,
        status: str,
        result: CadRunResult | None,
        error: str | None,
        project_id: str | None,
    ) -> CadRunRecord: ...

    def get_run(self, run_id: str, *, user_id: str) -> CadRunRecord: ...

    def count_runs(
        self, *, user_id: str, since: datetime, running_since: datetime
    ) -> tuple[int, int]:
        """(runs still running that started after ``running_since``, and runs
        started at or after ``since``). An older "running" run died with its
        server and must not count."""
        ...

    def add_run_event(self, run_id: str, event: RunEvent, *, user_id: str) -> None: ...

    def list_run_events(
        self, run_id: str, *, user_id: str, after: int = 0
    ) -> list[RunEvent]: ...

    def get_subscription(self, *, user_id: str) -> SubscriptionRecord | None: ...

    def save_subscription(
        self, subscription: SubscriptionRecord, *, user_id: str
    ) -> None: ...

    def hit_sandbox_rate(
        self,
        *,
        user_id: str,
        now: datetime,
        limit: int,
        window_seconds: int,
    ) -> float | None:
        """Atomically consume a shared sandbox allowance, or return wait seconds."""
        ...

    def acquire_concurrency_lease(
        self,
        *,
        lease_id: str,
        user_id: str,
        kind: str,
        now: datetime,
        expires_at: datetime,
        limit: int,
    ) -> bool:
        """Atomically reserve one shared sandbox execution slot."""
        ...

    def release_concurrency_lease(self, *, lease_id: str, user_id: str) -> None: ...


def _timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class ProjectStore:
    _billing_locks_guard = threading.Lock()
    _billing_locks: dict[tuple[str, str], threading.RLock] = {}

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def billing_operation_lock(self, user_id: str):
        """Local equivalent of the PostgreSQL per-user advisory lock.

        The key includes the resolved database path so separately constructed
        store objects in the same local process still serialize one account.
        """
        key = (str(self.path.resolve()), user_id)
        with self._billing_locks_guard:
            lock = self._billing_locks.setdefault(key, threading.RLock())
        with lock:
            yield

    def _initialize(self):
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_revisions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    revision_number INTEGER NOT NULL CHECK (revision_number > 0),
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                        ON DELETE CASCADE,
                    UNIQUE (project_id, revision_number)
                );
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(projects)").fetchall()
            }
            if "user_id" not in columns:
                try:
                    connection.execute(
                        "ALTER TABLE projects ADD COLUMN user_id TEXT NOT NULL "
                        f"DEFAULT '{LEGACY_LOCAL_USER_ID}'"
                    )
                except sqlite3.OperationalError as error:
                    if "duplicate column name" not in str(error).lower():
                        raise
            for column, definition in (
                ("thumbnail", "BLOB"),
                ("thumbnail_content_type", "TEXT"),
                ("thumbnail_updated_at", "TEXT"),
            ):
                if column not in columns:
                    connection.execute(
                        f"ALTER TABLE projects ADD COLUMN {column} {definition}"
                    )
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_projects_user_updated
                    ON projects(user_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_project_revisions_project
                    ON project_revisions(project_id, revision_number DESC);
                CREATE TABLE IF NOT EXISTS cad_runs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
                    status TEXT NOT NULL
                        CHECK (status IN ('running', 'succeeded', 'failed')),
                    prompt TEXT NOT NULL DEFAULT '',
                    model_id TEXT NOT NULL DEFAULT '',
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_cad_runs_user_created
                    ON cad_runs(user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id TEXT PRIMARY KEY,
                    stripe_customer_id TEXT NOT NULL UNIQUE,
                    stripe_subscription_id TEXT,
                    status TEXT NOT NULL DEFAULT 'none',
                    current_period_end TEXT,
                    cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_meshes (
                    project_id TEXT PRIMARY KEY
                        REFERENCES projects(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    glb BLOB NOT NULL,
                    inspection_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    run_id TEXT NOT NULL
                        REFERENCES cad_runs(id) ON DELETE CASCADE,
                    seq INTEGER NOT NULL CHECK (seq > 0),
                    user_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    attempt INTEGER,
                    duration_ms INTEGER,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, seq)
                );
                CREATE TABLE IF NOT EXISTS sandbox_rate_events (
                    user_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sandbox_rate_user_time
                    ON sandbox_rate_events(user_id, occurred_at);
                CREATE TABLE IF NOT EXISTS sandbox_active_leases (
                    lease_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'sandbox',
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sandbox_leases_user_expiry
                    ON sandbox_active_leases(user_id, expires_at);
                PRAGMA user_version = 8;
                """
            )
            lease_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(sandbox_active_leases)"
                ).fetchall()
            }
            if "kind" not in lease_columns:
                connection.execute(
                    "ALTER TABLE sandbox_active_leases "
                    "ADD COLUMN kind TEXT NOT NULL DEFAULT 'sandbox'"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sandbox_leases_user_kind_expiry "
                "ON sandbox_active_leases(user_id, kind, expires_at)"
            )

    @staticmethod
    def _state_json(state: ProjectState) -> str:
        return json.dumps(
            state.model_dump(mode="json", by_alias=True),
            separators=(",", ":"),
        )

    @staticmethod
    def _storage_bytes(connection: sqlite3.Connection, user_id: str) -> int:
        row = connection.execute(
            """
            SELECT
              (SELECT COALESCE(SUM(LENGTH(name) +
                  COALESCE(LENGTH(thumbnail), 0)), 0)
               FROM projects WHERE user_id = ?) +
              (SELECT COALESCE(SUM(LENGTH(r.state_json)), 0)
               FROM project_revisions r
               JOIN projects p ON p.id = r.project_id
               WHERE p.user_id = ?) +
              (SELECT COALESCE(SUM(LENGTH(glb) + LENGTH(inspection_json)), 0)
               FROM project_meshes WHERE user_id = ?) +
              (SELECT COALESCE(SUM(LENGTH(prompt) + LENGTH(model_id) +
                  COALESCE(LENGTH(result_json), 0) +
                  COALESCE(LENGTH(error), 0)), 0)
               FROM cad_runs WHERE user_id = ?) +
              (SELECT COALESCE(SUM(LENGTH(stage) + LENGTH(status) +
                  LENGTH(message)), 0)
               FROM run_events WHERE user_id = ?) AS bytes
            """,
            (user_id, user_id, user_id, user_id, user_id),
        ).fetchone()
        return int(row["bytes"])

    @classmethod
    def _assert_storage_available(
        cls, connection: sqlite3.Connection, user_id: str, additional: int
    ) -> None:
        if additional > 0 and (
            cls._storage_bytes(connection, user_id) + additional
            > max_storage_bytes_per_user()
        ):
            raise StorageQuotaExceededError(user_id)

    @staticmethod
    def _assert_project_count(connection: sqlite3.Connection, user_id: str) -> None:
        count = connection.execute(
            "SELECT COUNT(*) FROM projects WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        if int(count) >= max_projects_per_user():
            raise StorageQuotaExceededError(user_id, "projects")

    @staticmethod
    def _assert_revision_count(connection: sqlite3.Connection, user_id: str) -> None:
        count = connection.execute(
            """
            SELECT COUNT(*) FROM project_revisions r
            JOIN projects p ON p.id = r.project_id
            WHERE p.user_id = ?
            """,
            (user_id,),
        ).fetchone()[0]
        if int(count) >= max_revisions_per_user():
            raise StorageQuotaExceededError(user_id, "revisions")

    @staticmethod
    def _revision(row: sqlite3.Row) -> ProjectRevision:
        return ProjectRevision(
            id=row["id"],
            project_id=row["project_id"],
            revision_number=row["revision_number"],
            state=ProjectState.model_validate_json(row["state_json"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _summary(row: sqlite3.Row) -> ProjectSummary:
        return ProjectSummary(
            id=row["id"],
            name=row["name"],
            revision_count=row["revision_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            thumbnail_updated_at=row["thumbnail_updated_at"],
        )

    @staticmethod
    def _run(row: sqlite3.Row) -> CadRunRecord:
        return CadRunRecord(
            id=row["id"],
            project_id=row["project_id"],
            status=row["status"],
            prompt=row["prompt"],
            model_id=row["model_id"],
            result=(
                CadRunResult.model_validate_json(row["result_json"])
                if row["result_json"]
                else None
            ),
            error=row["error"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    def create_project(
        self, request: ProjectCreate, *, user_id: str
    ) -> ProjectDetail:
        project_id = str(uuid4())
        revision_id = str(uuid4())
        now = _timestamp()
        state_json = self._state_json(request.state)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_project_count(connection, user_id)
            self._assert_revision_count(connection, user_id)
            self._assert_storage_available(
                connection, user_id, len(request.name.encode()) + len(state_json.encode())
            )
            connection.execute(
                """
                INSERT INTO projects (id, user_id, name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, user_id, request.name, now, now),
            )
            connection.execute(
                """
                INSERT INTO project_revisions (
                    id, project_id, revision_number, state_json, created_at
                ) VALUES (?, ?, 1, ?, ?)
                """,
                (revision_id, project_id, state_json, now),
            )
        return self.get_project(project_id, user_id=user_id)

    def list_projects(
        self, *, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[ProjectSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {PROJECT_COLUMNS}, COUNT(r.id) AS revision_count
                FROM projects p
                LEFT JOIN project_revisions r ON r.project_id = p.id
                WHERE p.user_id = ?
                GROUP BY p.id
                ORDER BY p.updated_at DESC, p.id
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            ).fetchall()
        return [self._summary(row) for row in rows]

    def get_project(self, project_id: str, *, user_id: str) -> ProjectDetail:
        with self._connect() as connection:
            project = connection.execute(
                f"""
                SELECT {PROJECT_COLUMNS}, COUNT(r.id) AS revision_count
                FROM projects p
                LEFT JOIN project_revisions r ON r.project_id = p.id
                WHERE p.id = ? AND p.user_id = ?
                GROUP BY p.id
                """,
                (project_id, user_id),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError(project_id)
            revision = connection.execute(
                """
                SELECT * FROM project_revisions
                WHERE project_id = ?
                ORDER BY revision_number DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()

        summary = self._summary(project)
        return ProjectDetail(
            id=summary.id,
            name=summary.name,
            revision_count=summary.revision_count,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            thumbnail_updated_at=summary.thumbnail_updated_at,
            latest_revision=self._revision(revision) if revision else None,
        )

    def rename_project(
        self, project_id: str, name: str, *, user_id: str
    ) -> ProjectDetail:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT name FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            ).fetchone()
            if current is None:
                raise ProjectNotFoundError(project_id)
            self._assert_storage_available(
                connection,
                user_id,
                max(0, len(name.encode()) - len(current["name"].encode())),
            )
            cursor = connection.execute(
                """
                UPDATE projects SET name = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (name, _timestamp(), project_id, user_id),
            )
            if cursor.rowcount == 0:
                raise ProjectNotFoundError(project_id)
        return self.get_project(project_id, user_id=user_id)

    def add_revision(
        self, project_id: str, state: ProjectState, *, user_id: str
    ) -> ProjectRevision:
        revision_id = str(uuid4())
        now = _timestamp()
        state_json = self._state_json(state)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project = connection.execute(
                "SELECT id FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError(project_id)
            self._assert_revision_count(connection, user_id)
            self._assert_storage_available(connection, user_id, len(state_json.encode()))
            next_number = connection.execute(
                """
                SELECT COALESCE(MAX(revision_number), 0) + 1
                FROM project_revisions
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO project_revisions (
                    id, project_id, revision_number, state_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    project_id,
                    next_number,
                    state_json,
                    now,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )
            row = connection.execute(
                "SELECT * FROM project_revisions WHERE id = ?",
                (revision_id,),
            ).fetchone()
        return self._revision(row)

    def list_revisions(
        self,
        project_id: str,
        *,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProjectRevision]:
        with self._connect() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM projects WHERE id = ? AND user_id = ?",
                    (project_id, user_id),
                ).fetchone()
                is None
            ):
                raise ProjectNotFoundError(project_id)
            rows = connection.execute(
                """
                SELECT * FROM project_revisions
                WHERE project_id = ?
                ORDER BY revision_number DESC
                LIMIT ? OFFSET ?
                """,
                (project_id, limit, offset),
            ).fetchall()
        return [self._revision(row) for row in rows]

    def get_revision(
        self, project_id: str, revision_number: int, *, user_id: str
    ) -> ProjectRevision:
        with self._connect() as connection:
            project_exists = connection.execute(
                "SELECT 1 FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            ).fetchone()
            if project_exists is None:
                raise ProjectNotFoundError(project_id)
            row = connection.execute(
                """
                SELECT * FROM project_revisions
                WHERE project_id = ? AND revision_number = ?
                """,
                (project_id, revision_number),
            ).fetchone()
            if row is None:
                raise RevisionNotFoundError(
                    f"{project_id} revision {revision_number}"
                )
        return self._revision(row)

    def delete_project(self, project_id: str, *, user_id: str):
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            # Runs are part of the project's history and can carry prompts and
            # generated source. Delete even in-flight records: their worker
            # may finish, but it must not preserve or recreate deleted data.
            connection.execute(
                "DELETE FROM cad_runs WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            cursor = connection.execute(
                "DELETE FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            )
            if cursor.rowcount == 0:
                raise ProjectNotFoundError(project_id)

    def delete_account(self, *, user_id: str) -> None:
        """Delete everything stored for the user, in one transaction."""
        with self._connect() as connection:
            connection.execute("DELETE FROM run_events WHERE user_id = ?", (user_id,))
            connection.execute(
                "DELETE FROM project_meshes WHERE user_id = ?", (user_id,)
            )
            connection.execute("DELETE FROM cad_runs WHERE user_id = ?", (user_id,))
            connection.execute("DELETE FROM projects WHERE user_id = ?", (user_id,))
            connection.execute(
                "DELETE FROM subscriptions WHERE user_id = ?", (user_id,)
            )
            connection.execute(
                "DELETE FROM sandbox_rate_events WHERE user_id = ?", (user_id,)
            )
            connection.execute(
                "DELETE FROM sandbox_active_leases WHERE user_id = ?", (user_id,)
            )

    def set_thumbnail(
        self, project_id: str, data: bytes, content_type: str, *, user_id: str
    ) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT LENGTH(thumbnail) AS bytes FROM projects "
                "WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            ).fetchone()
            if existing is None:
                raise ProjectNotFoundError(project_id)
            self._assert_storage_available(
                connection, user_id, max(0, len(data) - int(existing["bytes"] or 0))
            )
            cursor = connection.execute(
                """
                UPDATE projects
                SET thumbnail = ?, thumbnail_content_type = ?,
                    thumbnail_updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (data, content_type, _timestamp(), project_id, user_id),
            )
            if cursor.rowcount == 0:
                raise ProjectNotFoundError(project_id)

    def get_thumbnail(
        self, project_id: str, *, user_id: str
    ) -> tuple[bytes, str]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT thumbnail, thumbnail_content_type FROM projects
                WHERE id = ? AND user_id = ?
                """,
                (project_id, user_id),
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError(project_id)
        if row["thumbnail"] is None:
            raise ThumbnailNotFoundError(project_id)
        return bytes(row["thumbnail"]), row["thumbnail_content_type"]

    def get_mesh(self, project_id: str, *, user_id: str) -> StoredMesh | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT code_hash, glb, inspection_json FROM project_meshes
                WHERE project_id = ? AND user_id = ?
                """,
                (project_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return StoredMesh(
            code_hash=row["code_hash"],
            glb=bytes(row["glb"]),
            inspection=json.loads(row["inspection_json"]),
        )

    def save_mesh(
        self, project_id: str, mesh: StoredMesh, *, user_id: str
    ) -> None:
        inspection_json = json.dumps(mesh.inspection, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project = connection.execute(
                "SELECT 1 FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError(project_id)
            existing = connection.execute(
                "SELECT LENGTH(glb) + LENGTH(inspection_json) AS bytes "
                "FROM project_meshes WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            ).fetchone()
            new_bytes = len(mesh.glb) + len(inspection_json.encode())
            self._assert_storage_available(
                connection,
                user_id,
                max(0, new_bytes - int(existing["bytes"] if existing else 0)),
            )
            cursor = connection.execute(
                """
                INSERT INTO project_meshes
                    (project_id, user_id, code_hash, glb, inspection_json,
                     updated_at)
                SELECT id, user_id, ?, ?, ?, ? FROM projects
                WHERE id = ? AND user_id = ?
                ON CONFLICT (project_id) DO UPDATE SET
                    code_hash = excluded.code_hash,
                    glb = excluded.glb,
                    inspection_json = excluded.inspection_json,
                    updated_at = excluded.updated_at
                """,
                (
                    mesh.code_hash,
                    mesh.glb,
                    inspection_json,
                    _timestamp(),
                    project_id,
                    user_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ProjectNotFoundError(project_id)

    def count_runs(
        self, *, user_id: str, since: datetime, running_since: datetime
    ) -> tuple[int, int]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COALESCE(SUM(status = 'running' AND created_at >= ?), 0)
                        AS running,
                    COALESCE(SUM(created_at >= ?), 0) AS recent
                FROM cad_runs WHERE user_id = ?
                """,
                (
                    running_since.astimezone(timezone.utc).isoformat(),
                    since.astimezone(timezone.utc).isoformat(),
                    user_id,
                ),
            ).fetchone()
        return int(row["running"]), int(row["recent"])

    def create_run(
        self,
        run_id: str,
        *,
        user_id: str,
        project_id: str | None,
        prompt: str,
        model_id: str,
    ) -> CadRunRecord:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_storage_available(
                connection,
                user_id,
                len(prompt.encode()) + len(model_id.encode()) + RUN_EVENT_RESERVE_BYTES,
            )
            connection.execute(
                """
                INSERT INTO cad_runs (
                    id, user_id, project_id, status, prompt, model_id, created_at
                ) VALUES (?, ?, ?, 'running', ?, ?, ?)
                """,
                (run_id, user_id, project_id, prompt, model_id, _timestamp()),
            )
        return self.get_run(run_id, user_id=user_id)

    def create_run_with_quota(
        self,
        run_id: str,
        *,
        user_id: str,
        project_id: str | None,
        prompt: str,
        model_id: str,
        now: datetime,
        running_since: datetime,
        max_concurrent: int,
        max_hourly: int,
        max_daily: int,
    ) -> CadRunRecord:
        now = now.astimezone(timezone.utc)
        running_since = running_since.astimezone(timezone.utc).isoformat()
        hourly_since = (now - timedelta(hours=1)).isoformat()
        daily_since = (now - timedelta(days=1)).isoformat()
        created_at = now.isoformat()
        with self._connect() as connection:
            # A reserved SQLite write transaction serializes separate local
            # processes, not just coroutines in this interpreter.
            connection.execute("BEGIN IMMEDIATE")
            self._assert_storage_available(
                connection,
                user_id,
                len(prompt.encode()) + len(model_id.encode()) + RUN_EVENT_RESERVE_BYTES,
            )
            counts = connection.execute(
                """
                SELECT
                    COALESCE(SUM(status = 'running' AND created_at >= ?), 0)
                        AS running,
                    COALESCE(SUM(created_at >= ?), 0) AS hourly,
                    COALESCE(SUM(created_at >= ?), 0) AS daily
                FROM cad_runs WHERE user_id = ?
                """,
                (running_since, hourly_since, daily_since, user_id),
            ).fetchone()
            if int(counts["running"]) >= max_concurrent:
                raise RunQuotaExceededError(
                    "concurrent", running=int(counts["running"])
                )
            if int(counts["daily"]) >= max_daily:
                raise RunQuotaExceededError("daily")
            if int(counts["hourly"]) >= max_hourly:
                raise RunQuotaExceededError("hourly")
            connection.execute(
                """
                INSERT INTO cad_runs (
                    id, user_id, project_id, status, prompt, model_id, created_at
                ) VALUES (?, ?, ?, 'running', ?, ?, ?)
                """,
                (run_id, user_id, project_id, prompt, model_id, created_at),
            )
            row = connection.execute(
                "SELECT * FROM cad_runs WHERE id = ? AND user_id = ?",
                (run_id, user_id),
            ).fetchone()
        return self._run(row)

    def hit_sandbox_rate(
        self,
        *,
        user_id: str,
        now: datetime,
        limit: int,
        window_seconds: int,
    ) -> float | None:
        now = now.astimezone(timezone.utc)
        cutoff = (now - timedelta(seconds=window_seconds)).isoformat()
        occurred_at = now.isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM sandbox_rate_events "
                "WHERE user_id = ? AND occurred_at <= ?",
                (user_id, cutoff),
            )
            row = connection.execute(
                """
                SELECT COUNT(*) AS calls, MIN(occurred_at) AS oldest
                FROM sandbox_rate_events WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            if limit <= 0:
                return float(window_seconds)
            if int(row["calls"]) >= limit:
                oldest = datetime.fromisoformat(row["oldest"])
                return max(
                    0.0,
                    (oldest + timedelta(seconds=window_seconds) - now).total_seconds(),
                )
            connection.execute(
                "INSERT INTO sandbox_rate_events (user_id, occurred_at) VALUES (?, ?)",
                (user_id, occurred_at),
            )
        return None

    def acquire_concurrency_lease(
        self,
        *,
        lease_id: str,
        user_id: str,
        kind: str,
        now: datetime,
        expires_at: datetime,
        limit: int,
    ) -> bool:
        now_value = now.astimezone(timezone.utc).isoformat()
        expiry_value = expires_at.astimezone(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM sandbox_active_leases "
                "WHERE user_id = ? AND kind = ? AND expires_at <= ?",
                (user_id, kind, now_value),
            )
            active = connection.execute(
                "SELECT COUNT(*) AS count FROM sandbox_active_leases "
                "WHERE user_id = ? AND kind = ?",
                (user_id, kind),
            ).fetchone()["count"]
            if limit <= 0 or int(active) >= limit:
                return False
            connection.execute(
                "INSERT INTO sandbox_active_leases "
                "(lease_id, user_id, kind, expires_at) VALUES (?, ?, ?, ?)",
                (lease_id, user_id, kind, expiry_value),
            )
        return True

    def release_concurrency_lease(self, *, lease_id: str, user_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sandbox_active_leases "
                "WHERE lease_id = ? AND user_id = ?",
                (lease_id, user_id),
            )

    def finish_run(
        self,
        run_id: str,
        *,
        user_id: str,
        status: str,
        result: CadRunResult | None,
        error: str | None,
        project_id: str | None,
    ) -> CadRunRecord:
        result_json = result.model_dump_json(by_alias=True) if result else None
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT LENGTH(result_json) AS result_bytes, "
                "LENGTH(error) AS error_bytes FROM cad_runs "
                "WHERE id = ? AND user_id = ? AND status = 'running'",
                (run_id, user_id),
            ).fetchone()
            if existing is None:
                raise RunNotFoundError(run_id)
            old_bytes = int(existing["result_bytes"] or 0) + int(
                existing["error_bytes"] or 0
            )
            new_bytes = len((result_json or "").encode()) + len((error or "").encode())
            self._assert_storage_available(
                connection, user_id, max(0, new_bytes - old_bytes)
            )
            cursor = connection.execute(
                """
                UPDATE cad_runs
                SET status = ?, result_json = ?, error = ?,
                    project_id = COALESCE(?, project_id), completed_at = ?
                WHERE id = ? AND user_id = ? AND status = 'running'
                """,
                (
                    status,
                    result_json,
                    error,
                    project_id,
                    _timestamp(),
                    run_id,
                    user_id,
                ),
            )
            if cursor.rowcount == 0:
                raise RunNotFoundError(run_id)
        return self.get_run(run_id, user_id=user_id)

    def add_run_event(self, run_id: str, event: RunEvent, *, user_id: str) -> None:
        stored = event_within_budget(event)
        if stored is None:
            return
        event = stored
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO run_events
                    (run_id, seq, user_id, stage, status, message, attempt,
                     duration_ms, created_at)
                SELECT id, ?, user_id, ?, ?, ?, ?, ?, ? FROM cad_runs
                WHERE id = ? AND user_id = ?
                """,
                (
                    event.seq,
                    event.stage,
                    event.status,
                    event.message,
                    event.attempt,
                    event.duration_ms,
                    event.created_at.isoformat(),
                    run_id,
                    user_id,
                ),
            )
            if cursor.rowcount == 0:
                raise RunNotFoundError(run_id)

    def list_run_events(
        self, run_id: str, *, user_id: str, after: int = 0
    ) -> list[RunEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT seq, stage, status, message, attempt, duration_ms,
                    created_at
                FROM run_events
                WHERE run_id = ? AND user_id = ? AND seq > ?
                ORDER BY seq
                """,
                (run_id, user_id, after),
            ).fetchall()
        return [RunEvent.model_validate(dict(row)) for row in rows]

    def get_run(self, run_id: str, *, user_id: str) -> CadRunRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM cad_runs WHERE id = ? AND user_id = ?",
                (run_id, user_id),
            ).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return self._run(row)

    def get_subscription(self, *, user_id: str) -> SubscriptionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM subscriptions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return SubscriptionRecord(
            stripe_customer_id=row["stripe_customer_id"],
            stripe_subscription_id=row["stripe_subscription_id"],
            status=row["status"],
            current_period_end=row["current_period_end"],
            cancel_at_period_end=bool(row["cancel_at_period_end"]),
        )

    def save_subscription(
        self, subscription: SubscriptionRecord, *, user_id: str
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO subscriptions (
                    user_id, stripe_customer_id, stripe_subscription_id, status,
                    current_period_end, cancel_at_period_end, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                    stripe_customer_id = excluded.stripe_customer_id,
                    stripe_subscription_id = excluded.stripe_subscription_id,
                    status = excluded.status,
                    current_period_end = excluded.current_period_end,
                    cancel_at_period_end = excluded.cancel_at_period_end,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    subscription.stripe_customer_id,
                    subscription.stripe_subscription_id,
                    subscription.status,
                    subscription.current_period_end.isoformat()
                    if subscription.current_period_end
                    else None,
                    int(subscription.cancel_at_period_end),
                    _timestamp(),
                ),
            )


@lru_cache(maxsize=1)
def get_project_store() -> ProjectStoreProtocol:
    database_url = os.getenv("NFNIT_DATABASE_URL", "").strip()
    if database_url:
        from .postgres_store import PostgresProjectStore

        return PostgresProjectStore(database_url)

    default_path = Path(__file__).parents[1] / "data" / "nfinit.db"
    configured_path = Path(os.getenv("NFNIT_DATABASE_PATH", default_path))
    return ProjectStore(configured_path.expanduser())
