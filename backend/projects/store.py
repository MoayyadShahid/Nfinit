import json
import os
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .models import (
    ProjectCreate,
    ProjectDetail,
    ProjectRevision,
    ProjectState,
    ProjectSummary,
)


class ProjectNotFoundError(LookupError):
    pass


class RevisionNotFoundError(LookupError):
    pass


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
                connection.execute(
                    "ALTER TABLE projects ADD COLUMN user_id TEXT NOT NULL "
                    f"DEFAULT '{LEGACY_LOCAL_USER_ID}'"
                )
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_projects_user_updated
                    ON projects(user_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_project_revisions_project
                    ON project_revisions(project_id, revision_number DESC);
                PRAGMA user_version = 2;
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
                """
                SELECT p.*, COUNT(r.id) AS revision_count
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
                """
                SELECT p.*, COUNT(r.id) AS revision_count
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


@lru_cache(maxsize=1)
def get_project_store() -> ProjectStoreProtocol:
    database_url = os.getenv("NFNIT_DATABASE_URL", "").strip()
    if database_url:
        from .postgres_store import PostgresProjectStore

        return PostgresProjectStore(database_url)

    default_path = Path(__file__).parents[1] / "data" / "nfinit.db"
    configured_path = Path(os.getenv("NFNIT_DATABASE_PATH", default_path))
    return ProjectStore(configured_path.expanduser())
