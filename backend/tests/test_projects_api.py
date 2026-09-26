from importlib import import_module

import pytest
from fastapi.testclient import TestClient

import main
from execution.topology import (
    FaceRevisionMatch,
    RevisionComparison,
    SelectionRemap,
)
from projects.auth import get_current_user_id
from projects.store import ProjectStore, get_project_store

USER_ID = "00000000-0000-4000-8000-000000000010"


@pytest.fixture
def client(tmp_path):
    store = ProjectStore(tmp_path / "projects.db")
    main.app.dependency_overrides[get_project_store] = lambda: store
    main.app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def test_project_api_manages_snapshots_and_history(client, monkeypatch):
    def fake_compare(previous_code, current_code, previous_face_id=None):
        assert previous_code == "result = Box(10, 20, 30)"
        assert current_code == "result = Box(20, 20, 30)"
        assert previous_face_id == "face-stale"
        return RevisionComparison(
            valid=True,
            previous_topology_version="before",
            current_topology_version="after",
            face_matches=[
                FaceRevisionMatch(
                    previous_face_id="face-a",
                    current_face_id="face-b",
                    status="modified",
                    confidence=1,
                    reason="legacy_geometry",
                )
            ],
            selection_remap=SelectionRemap(
                previous_face_id="face-stale",
                status="stale",
                confidence=0,
            ),
        )

    monkeypatch.setattr(
        import_module("projects.router"), "compare_code", fake_compare
    )
    created_response = client.post(
        "/projects",
        json={
            "name": "Phone mount",
            "state": {
                "code": "result = Box(10, 20, 30)",
                "messages": [{"role": "user", "content": "Make a mount"}],
                "modelId": "anthropic/claude-opus-5",
                "lastRunId": "run-one",
                "selection": {
                    "point": [5, 0, 0],
                    "normal": [1, 0, 0],
                    "entityId": "face-stale",
                    "topologyVersion": "old-topology",
                },
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
    assert comparison.json()["selectionRemap"]["status"] == "stale"

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
