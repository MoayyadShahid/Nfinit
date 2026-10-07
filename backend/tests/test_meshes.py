import importlib.util
import time

import pytest
from fastapi.testclient import TestClient

import main
from agent import ModelInspection
from execution import BuiltMesh, SandboxError
from projects import meshes, runs
from projects.auth import get_current_user_id
from projects.models import ProjectCreate, ProjectState
from projects.store import ProjectStore, get_project_store

USER_ID = "00000000-0000-4000-8000-000000000010"
OTHER_USER_ID = "00000000-0000-4000-8000-000000000020"
CUBE = "result = Box(10, 10, 10)"
WIDE = "result = Box(20, 10, 10)"


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


@pytest.fixture
def builds(monkeypatch):
    """Replace the sandbox with a fake that records each build."""
    built: list[str] = []

    def fake_build(code: str) -> BuiltMesh:
        built.append(code)
        return BuiltMesh(
            glb=f"glTF:{code}".encode(),
            inspection=ModelInspection(valid=True, solid_count=1, volume_mm3=1000),
        )

    monkeypatch.setattr(meshes, "build_mesh", fake_build)
    return built


def project_with(store, *codes: str, user_id: str = USER_ID) -> str:
    project = store.create_project(
        ProjectCreate(name="Part", state=ProjectState(code=codes[0])),
        user_id=user_id,
    )
    for code in codes[1:]:
        store.add_revision(project.id, ProjectState(code=code), user_id=user_id)
    return project.id


def mesh_link(client, project_id: str, revision: int):
    response = client.get(f"/projects/{project_id}/revisions/{revision}/mesh")
    assert response.status_code == 200, response.text
    return response.json()


def test_link_downloads_the_glb_without_a_second_build(client, store, builds):
    project_id = project_with(store, CUBE)

    link = mesh_link(client, project_id, 1)
    assert link["url"].startswith("/meshes/")
    assert link["bytes"] == len(f"glTF:{CUBE}")
    assert link["inspection"]["volume_mm3"] == 1000

    # The browser downloads with the signed link alone: no session needed.
    main.app.dependency_overrides.pop(get_current_user_id)
    download = client.get(link["url"])
    assert download.status_code == 200
    assert download.content == f"glTF:{CUBE}".encode()
    assert download.headers["content-type"] == "model/gltf-binary"
    assert builds == [CUBE]


def test_stored_mesh_is_reused_until_another_revision_is_viewed(
    client, store, builds
):
    project_id = project_with(store, CUBE, WIDE)

    mesh_link(client, project_id, 2)
    mesh_link(client, project_id, 2)
    assert builds == [WIDE]

    mesh_link(client, project_id, 1)  # replaces the one stored mesh
    mesh_link(client, project_id, 1)
    assert builds == [WIDE, CUBE]


def test_link_is_refused_when_tampered_or_expired(client, store, builds):
    project_id = project_with(store, CUBE)
    token = mesh_link(client, project_id, 1)["url"].removeprefix("/meshes/")

    body, _, signature = token.partition(".")
    forged = meshes.sign_mesh_token(
        user_id=OTHER_USER_ID,
        project_id=project_id,
        revision_number=1,
        expires_at=int(time.time()) + 60,
    ).partition(".")[0]
    assert client.get(f"/meshes/{forged}.{signature}").status_code == 404
    assert client.get(f"/meshes/{body}.{'0' * 64}").status_code == 404
    assert client.get("/meshes/not-a-token").status_code == 404

    expired = meshes.sign_mesh_token(
        user_id=USER_ID,
        project_id=project_id,
        revision_number=1,
        expires_at=int(time.time()) - 1,
    )
    assert client.get(f"/meshes/{expired}").status_code == 410


def test_other_users_cannot_get_a_link_or_a_mesh(client, store, builds):
    project_id = project_with(store, CUBE, user_id=OTHER_USER_ID)

    response = client.get(f"/projects/{project_id}/revisions/1/mesh")
    assert response.status_code == 404

    # A validly signed link for the wrong owner finds nothing either.
    token = meshes.sign_mesh_token(
        user_id=USER_ID,
        project_id=project_id,
        revision_number=1,
        expires_at=int(time.time()) + 60,
    )
    assert client.get(f"/meshes/{token}").status_code == 404
    assert builds == []


def test_mesh_is_served_when_its_storage_fails(client, store, builds, monkeypatch):
    project_id = project_with(store, CUBE)

    def missing_table(*_args, **_kwargs):
        raise RuntimeError('relation "public.project_meshes" does not exist')

    monkeypatch.setattr(store, "get_mesh", missing_table)
    monkeypatch.setattr(store, "save_mesh", missing_table)

    link = mesh_link(client, project_id, 1)
    assert client.get(link["url"]).content == f"glTF:{CUBE}".encode()
    assert builds == [CUBE, CUBE]  # nothing stored: the download rebuilds


def test_geometry_errors_are_reported(client, store, monkeypatch):
    project_id = project_with(store, CUBE)

    def broken(_code):
        raise SandboxError("cad_execution_error", "ValueError: bad fillet")

    monkeypatch.setattr(meshes, "build_mesh", broken)
    response = client.get(f"/projects/{project_id}/revisions/1/mesh")
    assert response.status_code == 422
    assert "bad fillet" in response.json()["detail"]


def test_successful_run_stores_its_mesh(client, store, builds, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    async def fake_agent(*_args, **_kwargs):
        return {
            "code": CUBE,
            "plan": "A cube.",
            "inspection": {"valid": True},
            "validation_error": None,
            "trace": [],
            "usage": {},
        }

    monkeypatch.setattr(runs, "run_cad_agent", fake_agent)
    started = client.post(
        "/cad/runs",
        json={
            "messages": [{"role": "user", "content": "A cube"}],
            "modelId": "anthropic/claude-opus-5",
        },
    ).json()
    for _ in range(100):
        record = client.get(f"/cad/runs/{started['runId']}").json()
        if record["status"] != "running":
            break
        time.sleep(0.02)

    assert record["status"] == "succeeded"
    assert builds == [CUBE]
    mesh_link(client, record["projectId"], 1)
    assert builds == [CUBE]  # the first view reuses the run's mesh


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d runtime is not installed",
)
def test_build_mesh_returns_glb_and_inspection():
    from execution import build_mesh

    built = build_mesh("result = Box(10, 20, 30)")

    assert built.glb[:4] == b"glTF"
    assert built.inspection.valid
    assert built.inspection.bounding_box_mm == {"x": 10, "y": 20, "z": 30}
