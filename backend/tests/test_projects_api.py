import pytest
from fastapi.testclient import TestClient

import main
from projects.store import ProjectStore, get_project_store


@pytest.fixture
def client(tmp_path):
    store = ProjectStore(tmp_path / "projects.db")
    main.app.dependency_overrides[get_project_store] = lambda: store
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def test_project_api_manages_snapshots_and_history(client):
    created_response = client.post(
        "/projects",
        json={
            "name": "Phone mount",
            "state": {
                "code": "result = Box(10, 20, 30)",
                "messages": [{"role": "user", "content": "Make a mount"}],
                "modelId": "anthropic/claude-opus-5",
                "lastRunId": "run-one",
            },
        },
    )

    assert created_response.status_code == 201
    created = created_response.json()
    project_id = created["id"]
    assert created["revisionCount"] == 1
    assert created["latestRevision"]["state"]["modelId"] == (
        "anthropic/claude-opus-5"
    )
    assert "model_id" not in created["latestRevision"]["state"]

    revision_response = client.post(
        f"/projects/{project_id}/revisions",
        json={
            "state": {
                "code": "result = Box(20, 20, 30)",
                "messages": [{"role": "user", "content": "Make it wider"}],
                "modelId": "openai/gpt-6-astra-pro",
                "lastRunId": "run-two",
            }
        },
    )

    assert revision_response.status_code == 201
    assert revision_response.json()["revisionNumber"] == 2
    assert client.get(f"/projects/{project_id}").json()["revisionCount"] == 2
    history = client.get(f"/projects/{project_id}/revisions").json()
    assert [revision["revisionNumber"] for revision in history] == [2, 1]
    assert client.get(
        f"/projects/{project_id}/revisions/1"
    ).json()["state"]["lastRunId"] == "run-one"
    comparison = client.get(
        f"/projects/{project_id}/compare",
        params={"previousRevision": 1, "currentRevision": 2},
    )
    assert comparison.status_code == 200
    assert comparison.json()["valid"] is True
    assert comparison.json()["previousTopologyVersion"] != (
        comparison.json()["currentTopologyVersion"]
    )
    assert comparison.json()["faceMatches"]

    renamed = client.patch(
        f"/projects/{project_id}", json={"name": "Wide phone mount"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Wide phone mount"
    assert client.get("/projects").json()[0]["id"] == project_id

    assert client.delete(f"/projects/{project_id}").status_code == 204
    assert client.get(f"/projects/{project_id}").status_code == 404


def test_project_api_validates_limits_and_missing_resources(client):
    assert client.post("/projects", json={"name": "   "}).status_code == 422
    assert client.get("/projects?limit=101").status_code == 422
    assert client.post(
        "/projects/missing/revisions",
        json={"state": {"code": "result = Box(1, 1, 1)"}},
    ).status_code == 404
    assert client.get("/projects/missing/revisions/1").status_code == 404
