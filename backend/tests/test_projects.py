import sqlite3

import pytest

from projects import models as project_models
from projects.models import ProjectCreate, ProjectState
from projects.postgres_store import PostgresProjectStore
from projects.store import LEGACY_LOCAL_USER_ID, ProjectNotFoundError, ProjectStore

USER_ID = "00000000-0000-4000-8000-000000000010"
OTHER_USER_ID = "00000000-0000-4000-8000-000000000020"


def initial_state() -> ProjectState:
    return ProjectState(
        code="result = Box(10, 10, 10)",
        messages=[
            {"role": "user", "content": "Make a cube"},
            {
                "role": "assistant",
                "content": "result = Box(10, 10, 10)",
                "agent": {"runId": "run-one", "plan": "Build a cube"},
            },
        ],
        modelId="anthropic/claude-opus-5",
        lastRunId="run-one",
    )


def test_project_store_persists_immutable_revision_history(tmp_path):
    database = tmp_path / "nested" / "projects.db"
    store = ProjectStore(database)
    created = store.create_project(
        ProjectCreate(name="  Mount prototype  ", state=initial_state()),
        user_id=USER_ID,
    )

    assert created.name == "Mount prototype"
    assert created.revision_count == 1
    assert created.latest_revision.revision_number == 1
    assert created.latest_revision.state.last_run_id == "run-one"

    updated_state = initial_state().model_copy(
        update={
            "code": "result = Box(20, 10, 10)",
            "last_run_id": "run-two",
        }
    )
    second = store.add_revision(created.id, updated_state, user_id=USER_ID)

    reopened = ProjectStore(database)
    loaded = reopened.get_project(created.id, user_id=USER_ID)
    revisions = reopened.list_revisions(created.id, user_id=USER_ID)

    assert second.revision_number == 2
    assert loaded.revision_count == 2
    assert loaded.latest_revision.state.code == "result = Box(20, 10, 10)"
    assert [revision.revision_number for revision in revisions] == [2, 1]
    assert reopened.get_revision(created.id, 1, user_id=USER_ID).state.code == (
        "result = Box(10, 10, 10)"
    )


def test_project_store_renames_lists_and_cascades_delete(tmp_path):
    store = ProjectStore(tmp_path / "projects.db")
    created = store.create_project(
        ProjectCreate(name="First"), user_id=USER_ID
    )

    renamed = store.rename_project(
        created.id, "Desk mount", user_id=USER_ID
    )

    assert renamed.name == "Desk mount"
    assert store.list_projects(user_id=USER_ID)[0].revision_count == 1

    store.delete_project(created.id, user_id=USER_ID)

    assert store.list_projects(user_id=USER_ID) == []
    with pytest.raises(ProjectNotFoundError):
        store.get_project(created.id, user_id=USER_ID)


def test_project_store_isolates_projects_by_user(tmp_path):
    store = ProjectStore(tmp_path / "projects.db")
    created = store.create_project(
        ProjectCreate(name="Private mount"), user_id=USER_ID
    )

    assert [project.id for project in store.list_projects(user_id=USER_ID)] == [
        created.id
    ]
    assert store.list_projects(user_id=OTHER_USER_ID) == []
    with pytest.raises(ProjectNotFoundError):
        store.get_project(created.id, user_id=OTHER_USER_ID)
    with pytest.raises(ProjectNotFoundError):
        store.add_revision(
            created.id, initial_state(), user_id=OTHER_USER_ID
        )


def test_postgres_store_rejects_malformed_project_ids_before_querying():
    store = PostgresProjectStore("postgresql://unused")

    with pytest.raises(ProjectNotFoundError):
        store.get_project("not-a-uuid", user_id=USER_ID)


def test_sqlite_store_assigns_existing_projects_to_local_identity(tmp_path):
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO projects (id, name, created_at, updated_at)
            VALUES ('legacy-project', 'Legacy part', '2026-01-01', '2026-01-01')
            """
        )

    store = ProjectStore(database)

    assert store.list_projects(user_id=LEGACY_LOCAL_USER_ID)[0].id == (
        "legacy-project"
    )


def test_project_state_rejects_oversized_snapshots(monkeypatch):
    monkeypatch.setattr(project_models, "MAX_PROJECT_STATE_BYTES", 100)

    with pytest.raises(ValueError, match="20 MB persisted snapshot limit"):
        ProjectState(
            messages=[{"role": "user", "content": "x" * 200}],
        )
