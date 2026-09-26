import json
from contextlib import contextmanager
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import (
    ProjectCreate,
    ProjectDetail,
    ProjectRevision,
    ProjectState,
    ProjectSummary,
)
from .store import ProjectNotFoundError, RevisionNotFoundError


class PostgresProjectStore:
    """Supabase Postgres store with request-scoped RLS identity."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    @contextmanager
    def _connect(self, user_id: str):
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            connection.execute(
                "SELECT set_config('request.jwt.claim.sub', %s, true)",
                (user_id,),
            )
            connection.execute("SET LOCAL ROLE nfinit_backend")
            yield connection

    @staticmethod
    def _state_value(state: ProjectState) -> dict:
        return state.model_dump(mode="json", by_alias=True)

    @staticmethod
    def _project_uuid(project_id: str) -> str:
        try:
            return str(UUID(project_id))
        except (ValueError, AttributeError) as error:
            raise ProjectNotFoundError(project_id) from error

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
        )

    def _get_project(
        self, connection: psycopg.Connection, project_id: str, user_id: str
    ) -> ProjectDetail:
        project = connection.execute(
            """
            SELECT p.*, COUNT(r.id) AS revision_count
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
            latest_revision=self._revision(revision) if revision else None,
        )

    def create_project(
        self, request: ProjectCreate, *, user_id: str
    ) -> ProjectDetail:
        project_id = str(uuid4())
        revision_id = str(uuid4())
        with self._connect(user_id) as connection:
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
                (revision_id, project_id, Jsonb(self._state_value(request.state))),
            )
            return self._get_project(connection, project_id, user_id)

    def list_projects(
        self, *, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[ProjectSummary]:
        with self._connect(user_id) as connection:
            rows = connection.execute(
                """
                SELECT p.*, COUNT(r.id) AS revision_count
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
        with self._connect(user_id) as connection:
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
                    Jsonb(self._state_value(state)),
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
    ) -> list[ProjectRevision]:
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
            rows = connection.execute(
                """
                SELECT * FROM public.project_revisions
                WHERE project_id = %s
                ORDER BY revision_number DESC
                LIMIT %s OFFSET %s
                """,
                (project_id, limit, offset),
            ).fetchall()
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
