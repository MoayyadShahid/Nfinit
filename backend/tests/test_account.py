import pytest
from fastapi.testclient import TestClient

import main
from projects.auth import get_current_user_id
from projects.models import CadRunResult, ProjectCreate, ProjectState
from projects.store import ProjectStore, StoredMesh, get_project_store

USER_ID = "00000000-0000-4000-8000-000000000010"
OTHER_USER_ID = "00000000-0000-4000-8000-000000000020"


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "projects.db")


@pytest.fixture
def client(store):
    main.app.dependency_overrides[get_project_store] = lambda: store
    main.app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def fill(store, user_id):
    project = store.create_project(
        ProjectCreate(name="Bracket", state=ProjectState(code="result = Box(1, 1, 1)")),
        user_id=user_id,
    )
    store.add_revision(
        project.id, ProjectState(code="result = Box(2, 1, 1)"), user_id=user_id
    )
    store.set_thumbnail(project.id, b"webp", "image/webp", user_id=user_id)
    store.save_mesh(
        project.id,
        StoredMesh(code_hash="h", glb=b"glTF", inspection={"valid": True}),
        user_id=user_id,
    )
    run = store.create_run(
        f"run-{user_id[-2:]}",
        user_id=user_id,
        project_id=project.id,
        prompt="A bracket",
        model_id="anthropic/claude-sonnet-5.5",
    )
    store.finish_run(
        run.id,
        user_id=user_id,
        status="succeeded",
        result=CadRunResult(code="result = Box(2, 1, 1)"),
        error=None,
        project_id=project.id,
    )
    return project.id, run.id


def everything_of(store, user_id):
    with store._connect() as connection:
        return {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (user_id,)
            ).fetchone()[0]
            for table in ("projects", "cad_runs", "project_meshes")
        }


def test_deleting_the_account_removes_all_data(client, store):
    fill(store, USER_ID)
    other_project, _ = fill(store, OTHER_USER_ID)
    now = "2026-10-30T00:00:00+00:00"
    with store._connect() as connection:
        connection.execute(
            "INSERT INTO sandbox_rate_events (user_id, occurred_at) VALUES (?, ?)",
            (USER_ID, now),
        )
        connection.execute(
            "INSERT INTO sandbox_active_leases "
            "(lease_id, user_id, kind, expires_at) VALUES (?, ?, ?, ?)",
            ("lease-1", USER_ID, "sandbox", now),
        )

    response = client.delete("/account")

    assert response.status_code == 204
    assert everything_of(store, USER_ID) == {
        "projects": 0,
        "cad_runs": 0,
        "project_meshes": 0,
    }
    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM project_revisions").fetchone()[
            0
        ] == 2  # only the other user's two revisions remain
        assert connection.execute(
            "SELECT COUNT(*) FROM sandbox_rate_events WHERE user_id = ?", (USER_ID,)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM sandbox_active_leases WHERE user_id = ?", (USER_ID,)
        ).fetchone()[0] == 0
    # Nobody else is touched.
    assert store.get_project(other_project, user_id=OTHER_USER_ID).name == "Bracket"
