import json
import os
import threading
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from psycopg.types.json import Jsonb

from .models import (
    CadRunRecord,
    CadRunResult,
    ProjectCreate,
    ProjectDetail,
    ProjectRevision,
    RevisionSummary,
    ProjectState,
    ProjectSummary,
    RunEvent,
)
from .store import (
    PROJECT_COLUMNS,
    REVISION_SUMMARY_COLUMNS,
    RUN_EVENT_RESERVE_BYTES,
    ProjectNotFoundError,
    RevisionNotFoundError,
    RunNotFoundError,
    RunQuotaExceededError,
    StorageQuotaExceededError,
    StoredMesh,
    ThumbnailNotFoundError,
    event_within_budget,
    max_projects_per_user,
    max_revisions_per_user,
    max_storage_bytes_per_user,
)


def _pool_setting(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


class PostgresProjectStore:
    """Supabase Postgres store with request-scoped RLS identity.

    Connections come from a pool. Opening one costs about six network round
    trips (TCP, TLS, login), which used to be paid by every query; a request
    such as opening a saved model made eleven of them. A query now costs
    three: BEGIN with the identity, the query, and COMMIT. The identity is
    transaction-local (`set_config(..., true)`), so it ends with the
    transaction and a pooled connection never carries one user's identity
    into another user's query.
    """

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._pool: ConnectionPool | None = None
        self._pool_lock = threading.Lock()

    def _get_pool(self) -> ConnectionPool:
        # Opened on first use, so constructing a store never touches the network.
        if self._pool is None:
            with self._pool_lock:
                if self._pool is None:
                    self._pool = ConnectionPool(
                        self.database_url,
                        min_size=_pool_setting("NFNIT_DB_POOL_MIN", 1),
                        max_size=_pool_setting("NFNIT_DB_POOL_MAX", 10),
                        # Close idle connections well before Supavisor or a
                        # firewall would, instead of pinging every connection
                        # on checkout (one more round trip per query).
                        max_idle=_pool_setting("NFNIT_DB_POOL_MAX_IDLE_SECONDS", 120),
                        max_lifetime=_pool_setting("NFNIT_DB_POOL_MAX_LIFETIME_SECONDS", 1800),
                        timeout=_pool_setting("NFNIT_DB_POOL_TIMEOUT_SECONDS", 15),
                        # Server-side prepared statements break behind a
                        # transaction-mode pooler (Supavisor port 6543), and a
                        # reused connection would start preparing after five runs
                        # of a query. Keep them off so either pooler mode works.
                        kwargs={"row_factory": dict_row, "prepare_threshold": None},
                        name="nfinit",
                        open=True,
                    )
        return self._pool

    def close(self) -> None:
        """Close the pool's connections, e.g. when the app shuts down."""
        with self._pool_lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    @contextmanager
    def _connect(self, user_id: str):
        # The pool commits when the block ends and rolls back on an error,
        # which also ends the transaction-local identity below.
        with self._get_pool().connection() as connection:
            # BEGIN and the identity go out together in one round trip.
            # set_config('role', ..., true) is SET LOCAL ROLE.
            with connection.pipeline():
                connection.execute(
                    "SELECT set_config('request.jwt.claim.sub', %s, true),"
                    " set_config('role', 'nfinit_backend', true)",
                    (user_id,),
                )
            yield connection

    @staticmethod
    def _state_value(state: ProjectState) -> dict:
        return state.model_dump(mode="json", by_alias=True)

    @staticmethod
    def _lock_storage(connection, user_id: str) -> None:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"nfinit-storage:{user_id}",),
        )

    @staticmethod
    def _storage_bytes(connection, user_id: str) -> int:
        row = connection.execute(
            """
            SELECT
              (SELECT COALESCE(SUM(octet_length(name) +
                  COALESCE(octet_length(thumbnail), 0)), 0)
               FROM public.projects WHERE user_id = %s) +
              (SELECT COALESCE(SUM(pg_column_size(r.state_json)), 0)
               FROM public.project_revisions r
               JOIN public.projects p ON p.id = r.project_id
               WHERE p.user_id = %s) +
              (SELECT COALESCE(SUM(octet_length(glb) +
                  pg_column_size(inspection_json)), 0)
               FROM public.project_meshes WHERE user_id = %s) +
              (SELECT COALESCE(SUM(octet_length(prompt) +
                  octet_length(model_id) +
                  COALESCE(pg_column_size(result_json), 0) +
                  COALESCE(octet_length(error), 0)), 0)
               FROM public.cad_runs WHERE user_id = %s) +
              (SELECT COALESCE(SUM(octet_length(stage) +
                  octet_length(status) + octet_length(message)), 0)
               FROM public.run_events WHERE user_id = %s) AS bytes
            """,
            (user_id, user_id, user_id, user_id, user_id),
        ).fetchone()
        return int(row["bytes"])

    @classmethod
    def _assert_storage_available(cls, connection, user_id: str, additional: int):
        if additional > 0 and (
            cls._storage_bytes(connection, user_id) + additional
            > max_storage_bytes_per_user()
        ):
            raise StorageQuotaExceededError(user_id)

    @staticmethod
    def _assert_project_count(connection, user_id: str) -> None:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM public.projects WHERE user_id = %s",
            (user_id,),
        ).fetchone()["count"]
        if int(count) >= max_projects_per_user():
            raise StorageQuotaExceededError(user_id, "projects")

    @staticmethod
    def _assert_revision_count(connection, user_id: str) -> None:
        count = connection.execute(
            """
            SELECT COUNT(*) AS count FROM public.project_revisions r
            JOIN public.projects p ON p.id = r.project_id
            WHERE p.user_id = %s
            """,
            (user_id,),
        ).fetchone()["count"]
        if int(count) >= max_revisions_per_user():
            raise StorageQuotaExceededError(user_id, "revisions")

    @staticmethod
    def _project_uuid(project_id: str) -> str:
        try:
            return str(UUID(project_id))
        except (ValueError, AttributeError) as error:
            raise ProjectNotFoundError(project_id) from error

    @staticmethod
    def _revision_summary(row: dict) -> RevisionSummary:
        return RevisionSummary(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            revision_number=row["revision_number"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _revision(row: dict) -> ProjectRevision:
        state = row["state_json"]
        if isinstance(state, str):
            state = json.loads(state)
        return ProjectRevision(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            revision_number=row["revision_number"],
            state=ProjectState.model_validate(state),
            created_at=row["created_at"],
        )

    @staticmethod
    def _summary(row: dict) -> ProjectSummary:
        return ProjectSummary(
            id=str(row["id"]),
            name=row["name"],
            revision_count=row["revision_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            thumbnail_updated_at=row["thumbnail_updated_at"],
        )

    @staticmethod
    def _run(row: dict) -> CadRunRecord:
        return CadRunRecord(
            id=str(row["id"]),
            project_id=str(row["project_id"]) if row["project_id"] else None,
            status=row["status"],
            prompt=row["prompt"],
            model_id=row["model_id"],
            result=(
                CadRunResult.model_validate(row["result_json"])
                if row["result_json"] is not None
                else None
            ),
            error=row["error"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    @staticmethod
    def _run_uuid(run_id: str) -> str:
        try:
            return str(UUID(run_id))
        except (ValueError, AttributeError) as error:
            raise RunNotFoundError(run_id) from error

    def _get_project(
        self, connection: psycopg.Connection, project_id: str, user_id: str
    ) -> ProjectDetail:
        project = connection.execute(
            f"""
            SELECT {PROJECT_COLUMNS}, COUNT(r.id) AS revision_count
            FROM public.projects p
            LEFT JOIN public.project_revisions r ON r.project_id = p.id
            WHERE p.id = %s AND p.user_id = %s
            GROUP BY p.id
            """,
            (project_id, user_id),
        ).fetchone()
        if project is None:
            raise ProjectNotFoundError(project_id)
        revision = connection.execute(
            """
            SELECT * FROM public.project_revisions
            WHERE project_id = %s
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

    def create_project(
        self, request: ProjectCreate, *, user_id: str
    ) -> ProjectDetail:
        project_id = str(uuid4())
        revision_id = str(uuid4())
        state_value = self._state_value(request.state)
        state_bytes = len(json.dumps(state_value, separators=(",", ":")).encode())
        with self._connect(user_id) as connection:
            self._lock_storage(connection, user_id)
            self._assert_project_count(connection, user_id)
            self._assert_revision_count(connection, user_id)
            self._assert_storage_available(
                connection, user_id, len(request.name.encode()) + state_bytes
            )
            connection.execute(
                """
                INSERT INTO public.projects (id, user_id, name)
                VALUES (%s, %s, %s)
                """,
                (project_id, user_id, request.name),
            )
            connection.execute(
                """
                INSERT INTO public.project_revisions (
                    id, project_id, revision_number, state_json
                ) VALUES (%s, %s, 1, %s)
                """,
                (revision_id, project_id, Jsonb(state_value)),
            )
            return self._get_project(connection, project_id, user_id)

    def list_projects(
        self, *, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[ProjectSummary]:
        with self._connect(user_id) as connection:
            rows = connection.execute(
                f"""
                SELECT {PROJECT_COLUMNS}, COUNT(r.id) AS revision_count
                FROM public.projects p
                LEFT JOIN public.project_revisions r ON r.project_id = p.id
                WHERE p.user_id = %s
                GROUP BY p.id
                ORDER BY p.updated_at DESC, p.id
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            ).fetchall()
        return [self._summary(row) for row in rows]

    def get_project(self, project_id: str, *, user_id: str) -> ProjectDetail:
        project_id = self._project_uuid(project_id)
        with self._connect(user_id) as connection:
            return self._get_project(connection, project_id, user_id)

    def rename_project(
        self, project_id: str, name: str, *, user_id: str
    ) -> ProjectDetail:
        project_id = self._project_uuid(project_id)
        with self._connect(user_id) as connection:
            self._lock_storage(connection, user_id)
            current = connection.execute(
                "SELECT name FROM public.projects WHERE id = %s AND user_id = %s",
                (project_id, user_id),
            ).fetchone()
            if current is None:
                raise ProjectNotFoundError(project_id)
            self._assert_storage_available(
                connection,
                user_id,
                max(0, len(name.encode()) - len(current["name"].encode())),
            )
            updated = connection.execute(
                """
                UPDATE public.projects
                SET name = %s, updated_at = now()
                WHERE id = %s AND user_id = %s
                RETURNING id
                """,
                (name, project_id, user_id),
            ).fetchone()
            if updated is None:
                raise ProjectNotFoundError(project_id)
            return self._get_project(connection, project_id, user_id)

    def add_revision(
        self, project_id: str, state: ProjectState, *, user_id: str
    ) -> ProjectRevision:
        project_id = self._project_uuid(project_id)
        revision_id = str(uuid4())
        state_value = self._state_value(state)
        state_bytes = len(json.dumps(state_value, separators=(",", ":")).encode())
        with self._connect(user_id) as connection:
            self._lock_storage(connection, user_id)
            project = connection.execute(
                """
                SELECT id FROM public.projects
                WHERE id = %s AND user_id = %s
                FOR UPDATE
                """,
                (project_id, user_id),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError(project_id)
            self._assert_revision_count(connection, user_id)
            self._assert_storage_available(connection, user_id, state_bytes)
            next_number = connection.execute(
                """
                SELECT COALESCE(MAX(revision_number), 0) + 1 AS next_number
                FROM public.project_revisions
                WHERE project_id = %s
                """,
                (project_id,),
            ).fetchone()["next_number"]
            row = connection.execute(
                """
                INSERT INTO public.project_revisions (
                    id, project_id, revision_number, state_json
                ) VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (
                    revision_id,
                    project_id,
                    next_number,
                    Jsonb(state_value),
                ),
            ).fetchone()
            connection.execute(
                """
                UPDATE public.projects SET updated_at = now()
                WHERE id = %s AND user_id = %s
                """,
                (project_id, user_id),
            )
        return self._revision(row)

    def list_revisions(
        self,
        project_id: str,
        *,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
        with_state: bool = True,
    ) -> list[ProjectRevision] | list[RevisionSummary]:
        project_id = self._project_uuid(project_id)
        # Without states the query never reads state_json, which holds the
        # whole chat and code of every version.
        columns = "*" if with_state else REVISION_SUMMARY_COLUMNS
        with self._connect(user_id) as connection:
            project = connection.execute(
                """
                SELECT 1 FROM public.projects
                WHERE id = %s AND user_id = %s
                """,
                (project_id, user_id),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError(project_id)
            rows = connection.execute(
                f"""
                SELECT {columns} FROM public.project_revisions
                WHERE project_id = %s
                ORDER BY revision_number DESC
                LIMIT %s OFFSET %s
                """,
                (project_id, limit, offset),
            ).fetchall()
        if not with_state:
            return [self._revision_summary(row) for row in rows]
        return [self._revision(row) for row in rows]

    def get_revision(
        self, project_id: str, revision_number: int, *, user_id: str
    ) -> ProjectRevision:
        project_id = self._project_uuid(project_id)
        with self._connect(user_id) as connection:
            project = connection.execute(
                """
                SELECT 1 FROM public.projects
                WHERE id = %s AND user_id = %s
                """,
                (project_id, user_id),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError(project_id)
            row = connection.execute(
                """
                SELECT * FROM public.project_revisions
                WHERE project_id = %s AND revision_number = %s
                """,
                (project_id, revision_number),
            ).fetchone()
            if row is None:
                raise RevisionNotFoundError(
                    f"{project_id} revision {revision_number}"
                )
        return self._revision(row)

    def delete_project(self, project_id: str, *, user_id: str) -> None:
        project_id = self._project_uuid(project_id)
        with self._connect(user_id) as connection:
            # Runs contain prompts/results and are project history. Delete
            # even in-flight records so a worker cannot retain deleted data.
            connection.execute(
                """
                DELETE FROM public.cad_runs
                WHERE project_id = %s AND user_id = %s
                """,
                (project_id, user_id),
            )
            deleted = connection.execute(
                """
                DELETE FROM public.projects
                WHERE id = %s AND user_id = %s
                RETURNING id
                """,
                (project_id, user_id),
            ).fetchone()
            if deleted is None:
                raise ProjectNotFoundError(project_id)

    def delete_account(self, *, user_id: str) -> None:
        """Delete the auth user; every user table cascades from it."""
        with self._connect(user_id) as connection:
            connection.execute("SELECT public.nfinit_delete_my_account()")

    def set_thumbnail(
        self, project_id: str, data: bytes, content_type: str, *, user_id: str
    ) -> None:
        project_id = self._project_uuid(project_id)
        with self._connect(user_id) as connection:
            self._lock_storage(connection, user_id)
            existing = connection.execute(
                "SELECT octet_length(thumbnail) AS bytes FROM public.projects "
                "WHERE id = %s AND user_id = %s",
                (project_id, user_id),
            ).fetchone()
            if existing is None:
                raise ProjectNotFoundError(project_id)
            self._assert_storage_available(
                connection, user_id, max(0, len(data) - int(existing["bytes"] or 0))
            )
            updated = connection.execute(
                """
                UPDATE public.projects
                SET thumbnail = %s, thumbnail_content_type = %s,
                    thumbnail_updated_at = now()
                WHERE id = %s AND user_id = %s
                RETURNING id
                """,
                (data, content_type, project_id, user_id),
            ).fetchone()
            if updated is None:
                raise ProjectNotFoundError(project_id)

    def get_thumbnail(
        self, project_id: str, *, user_id: str
    ) -> tuple[bytes, str]:
        project_id = self._project_uuid(project_id)
        with self._connect(user_id) as connection:
            row = connection.execute(
                """
                SELECT thumbnail, thumbnail_content_type FROM public.projects
                WHERE id = %s AND user_id = %s
                """,
                (project_id, user_id),
            ).fetchone()
        if row is None:
            raise ProjectNotFoundError(project_id)
        if row["thumbnail"] is None:
            raise ThumbnailNotFoundError(project_id)
        return bytes(row["thumbnail"]), row["thumbnail_content_type"]

    def get_mesh(self, project_id: str, *, user_id: str) -> StoredMesh | None:
        project_id = self._project_uuid(project_id)
        with self._connect(user_id) as connection:
            row = connection.execute(
                """
                SELECT code_hash, glb, inspection_json FROM public.project_meshes
                WHERE project_id = %s AND user_id = %s
                """,
                (project_id, user_id),
            ).fetchone()
        if row is None:
            return None
        inspection = row["inspection_json"]
        if isinstance(inspection, str):
            inspection = json.loads(inspection)
        return StoredMesh(
            code_hash=row["code_hash"],
            glb=bytes(row["glb"]),
            inspection=inspection,
        )

    def save_mesh(
        self, project_id: str, mesh: StoredMesh, *, user_id: str
    ) -> None:
        project_id = self._project_uuid(project_id)
        inspection_bytes = len(json.dumps(mesh.inspection, separators=(",", ":")).encode())
        with self._connect(user_id) as connection:
            self._lock_storage(connection, user_id)
            project = connection.execute(
                "SELECT 1 FROM public.projects WHERE id = %s AND user_id = %s",
                (project_id, user_id),
            ).fetchone()
            if project is None:
                raise ProjectNotFoundError(project_id)
            existing = connection.execute(
                "SELECT octet_length(glb) + pg_column_size(inspection_json) AS bytes "
                "FROM public.project_meshes WHERE project_id = %s AND user_id = %s",
                (project_id, user_id),
            ).fetchone()
            self._assert_storage_available(
                connection,
                user_id,
                max(
                    0,
                    len(mesh.glb)
                    + inspection_bytes
                    - int(existing["bytes"] if existing else 0),
                ),
            )
            saved = connection.execute(
                """
                INSERT INTO public.project_meshes
                    (project_id, user_id, code_hash, glb, inspection_json,
                     updated_at)
                SELECT id, user_id, %s, %s, %s, now() FROM public.projects
                WHERE id = %s AND user_id = %s
                ON CONFLICT (project_id) DO UPDATE SET
                    code_hash = excluded.code_hash,
                    glb = excluded.glb,
                    inspection_json = excluded.inspection_json,
                    updated_at = excluded.updated_at
                RETURNING project_id
                """,
                (
                    mesh.code_hash,
                    mesh.glb,
                    Jsonb(mesh.inspection),
                    project_id,
                    user_id,
                ),
            ).fetchone()
            if saved is None:
                raise ProjectNotFoundError(project_id)

    def count_runs(
        self, *, user_id: str, since: datetime, running_since: datetime
    ) -> tuple[int, int]:
        with self._connect(user_id) as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE status = 'running' AND created_at >= %s
                    ) AS running,
                    COUNT(*) FILTER (WHERE created_at >= %s) AS recent
                FROM public.cad_runs WHERE user_id = %s
                """,
                (running_since, since, user_id),
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
        run_id = self._run_uuid(run_id)
        if project_id is not None:
            project_id = self._project_uuid(project_id)
        with self._connect(user_id) as connection:
            self._lock_storage(connection, user_id)
            self._assert_storage_available(
                connection,
                user_id,
                len(prompt.encode()) + len(model_id.encode()) + RUN_EVENT_RESERVE_BYTES,
            )
            row = connection.execute(
                """
                INSERT INTO public.cad_runs (
                    id, user_id, project_id, status, prompt, model_id
                ) VALUES (%s, %s, %s, 'running', %s, %s)
                RETURNING *
                """,
                (run_id, user_id, project_id, prompt, model_id),
            ).fetchone()
        return self._run(row)

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
        run_id = self._run_uuid(run_id)
        if project_id is not None:
            project_id = self._project_uuid(project_id)
        now = now.astimezone(timezone.utc)
        with self._connect(user_id) as connection:
            # Transaction-scoped advisory locks are shared by every backend
            # replica and disappear automatically on commit, rollback or a
            # dead connection.  The count and insert therefore form one
            # reservation rather than a check-then-act race.
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"nfinit-run:{user_id}",),
            )
            self._lock_storage(connection, user_id)
            self._assert_storage_available(
                connection,
                user_id,
                len(prompt.encode()) + len(model_id.encode()) + RUN_EVENT_RESERVE_BYTES,
            )
            counts = connection.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE status = 'running' AND created_at >= %s
                    ) AS running,
                    COUNT(*) FILTER (WHERE created_at >= %s) AS hourly,
                    COUNT(*) FILTER (WHERE created_at >= %s) AS daily
                FROM public.cad_runs WHERE user_id = %s
                """,
                (
                    running_since,
                    now - timedelta(hours=1),
                    now - timedelta(days=1),
                    user_id,
                ),
            ).fetchone()
            if int(counts["running"]) >= max_concurrent:
                raise RunQuotaExceededError(
                    "concurrent", running=int(counts["running"])
                )
            if int(counts["daily"]) >= max_daily:
                raise RunQuotaExceededError("daily")
            if int(counts["hourly"]) >= max_hourly:
                raise RunQuotaExceededError("hourly")
            row = connection.execute(
                """
                INSERT INTO public.cad_runs (
                    id, user_id, project_id, status, prompt, model_id, created_at
                ) VALUES (%s, %s, %s, 'running', %s, %s, %s)
                RETURNING *
                """,
                (run_id, user_id, project_id, prompt, model_id, now),
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
        cutoff = now - timedelta(seconds=window_seconds)
        with self._connect(user_id) as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"nfinit-sandbox-rate:{user_id}",),
            )
            connection.execute(
                """
                DELETE FROM public.sandbox_rate_events
                WHERE user_id = %s AND occurred_at <= %s
                """,
                (user_id, cutoff),
            )
            row = connection.execute(
                """
                SELECT COUNT(*) AS calls, MIN(occurred_at) AS oldest
                FROM public.sandbox_rate_events WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
            if limit <= 0:
                return float(window_seconds)
            if int(row["calls"]) >= limit:
                return max(
                    0.0,
                    (
                        row["oldest"]
                        + timedelta(seconds=window_seconds)
                        - now
                    ).total_seconds(),
                )
            connection.execute(
                """
                INSERT INTO public.sandbox_rate_events (user_id, occurred_at)
                VALUES (%s, %s)
                """,
                (user_id, now),
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
        lease_id = str(UUID(lease_id))
        now = now.astimezone(timezone.utc)
        expires_at = expires_at.astimezone(timezone.utc)
        with self._connect(user_id) as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"nfinit-active:{kind}:{user_id}",),
            )
            connection.execute(
                """
                DELETE FROM public.sandbox_active_leases
                WHERE user_id = %s AND kind = %s AND expires_at <= %s
                """,
                (user_id, kind, now),
            )
            active = connection.execute(
                """
                SELECT COUNT(*) AS count FROM public.sandbox_active_leases
                WHERE user_id = %s AND kind = %s
                """,
                (user_id, kind),
            ).fetchone()["count"]
            if limit <= 0 or int(active) >= limit:
                return False
            connection.execute(
                """
                INSERT INTO public.sandbox_active_leases
                    (lease_id, user_id, kind, expires_at)
                VALUES (%s, %s, %s, %s)
                """,
                (lease_id, user_id, kind, expires_at),
            )
        return True

    def release_concurrency_lease(self, *, lease_id: str, user_id: str) -> None:
        lease_id = str(UUID(lease_id))
        with self._connect(user_id) as connection:
            connection.execute(
                """
                DELETE FROM public.sandbox_active_leases
                WHERE lease_id = %s AND user_id = %s
                """,
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
        run_id = self._run_uuid(run_id)
        if project_id is not None:
            project_id = self._project_uuid(project_id)
        result_value = result.model_dump(mode="json", by_alias=True) if result else None
        with self._connect(user_id) as connection:
            self._lock_storage(connection, user_id)
            existing = connection.execute(
                "SELECT COALESCE(pg_column_size(result_json), 0) AS result_bytes, "
                "COALESCE(octet_length(error), 0) AS error_bytes "
                "FROM public.cad_runs "
                "WHERE id = %s AND user_id = %s AND status = 'running'",
                (run_id, user_id),
            ).fetchone()
            if existing is None:
                raise RunNotFoundError(run_id)
            old_bytes = int(existing["result_bytes"]) + int(existing["error_bytes"])
            result_bytes = (
                len(json.dumps(result_value, separators=(",", ":")).encode())
                if result_value is not None
                else 0
            )
            new_bytes = result_bytes + len((error or "").encode())
            self._assert_storage_available(
                connection, user_id, max(0, new_bytes - old_bytes)
            )
            row = connection.execute(
                """
                UPDATE public.cad_runs
                SET status = %s, result_json = %s, error = %s,
                    project_id = COALESCE(%s, project_id), completed_at = now()
                WHERE id = %s AND user_id = %s AND status = 'running'
                RETURNING *
                """,
                (
                    status,
                    Jsonb(result_value) if result_value is not None else None,
                    error,
                    project_id,
                    run_id,
                    user_id,
                ),
            ).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return self._run(row)

    def get_run(self, run_id: str, *, user_id: str) -> CadRunRecord:
        run_id = self._run_uuid(run_id)
        with self._connect(user_id) as connection:
            row = connection.execute(
                """
                SELECT * FROM public.cad_runs
                WHERE id = %s AND user_id = %s
                """,
                (run_id, user_id),
            ).fetchone()
        if row is None:
            raise RunNotFoundError(run_id)
        return self._run(row)

    def add_run_event(self, run_id: str, event: RunEvent, *, user_id: str) -> None:
        run_id = self._run_uuid(run_id)
        stored = event_within_budget(event)
        if stored is None:
            return
        event = stored
        with self._connect(user_id) as connection:
            added = connection.execute(
                """
                INSERT INTO public.run_events
                    (run_id, seq, user_id, stage, status, message, attempt,
                     duration_ms, created_at)
                SELECT id, %s, user_id, %s, %s, %s, %s, %s, %s
                FROM public.cad_runs
                WHERE id = %s AND user_id = %s
                RETURNING seq
                """,
                (
                    event.seq,
                    event.stage,
                    event.status,
                    event.message,
                    event.attempt,
                    event.duration_ms,
                    event.created_at,
                    run_id,
                    user_id,
                ),
            ).fetchone()
            if added is None:
                raise RunNotFoundError(run_id)

    def list_run_events(
        self, run_id: str, *, user_id: str, after: int = 0
    ) -> list[RunEvent]:
        run_id = self._run_uuid(run_id)
        with self._connect(user_id) as connection:
            rows = connection.execute(
                """
                SELECT seq, stage, status, message, attempt, duration_ms,
                    created_at
                FROM public.run_events
                WHERE run_id = %s AND user_id = %s AND seq > %s
                ORDER BY seq
                """,
                (run_id, user_id, after),
            ).fetchall()
        return [RunEvent.model_validate(row) for row in rows]
