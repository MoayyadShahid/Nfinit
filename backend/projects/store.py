import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .models import (
    CadRunRecord,
    CadRunResult,
    ProjectCreate,
    ProjectDetail,
    ProjectRevision,
    ProjectState,
    ProjectSummary,
    SubscriptionRecord,
)


class ProjectNotFoundError(LookupError):
    pass


class RevisionNotFoundError(LookupError):
    pass


class RunNotFoundError(LookupError):
    pass


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


class ProjectStoreProtocol(Protocol):
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

    def get_subscription(self, *, user_id: str) -> SubscriptionRecord | None: ...

    def save_subscription(
        self, subscription: SubscriptionRecord, *, user_id: str
    ) -> None: ...


def _timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class ProjectStore:
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
                PRAGMA user_version = 5;
                """
            )

    @staticmethod
    def _state_json(state: ProjectState) -> str:
        return json.dumps(
            state.model_dump(mode="json", by_alias=True),
            separators=(",", ":"),
        )

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
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
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
                (revision_id, project_id, self._state_json(request.state), now),
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
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project = connection.execute(
                "SELECT id FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError(project_id)
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
                    self._state_json(state),
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
            cursor = connection.execute(
                "DELETE FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            )
            if cursor.rowcount == 0:
                raise ProjectNotFoundError(project_id)

    def set_thumbnail(
        self, project_id: str, data: bytes, content_type: str, *, user_id: str
    ) -> None:
        with self._connect() as connection:
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
        with self._connect() as connection:
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
                    json.dumps(mesh.inspection, separators=(",", ":")),
                    _timestamp(),
                    project_id,
                    user_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ProjectNotFoundError(project_id)

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
            connection.execute(
                """
                INSERT INTO cad_runs (
                    id, user_id, project_id, status, prompt, model_id, created_at
                ) VALUES (?, ?, ?, 'running', ?, ?, ?)
                """,
                (run_id, user_id, project_id, prompt, model_id, _timestamp()),
            )
        return self.get_run(run_id, user_id=user_id)

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
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE cad_runs
                SET status = ?, result_json = ?, error = ?,
                    project_id = COALESCE(?, project_id), completed_at = ?
                WHERE id = ? AND user_id = ? AND status = 'running'
                """,
                (
                    status,
                    result.model_dump_json(by_alias=True) if result else None,
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
