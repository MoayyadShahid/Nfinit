import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import main
from agent import CadRunTimeoutError
from projects import runs
from projects.auth import get_current_user_id
from projects.store import ProjectStore, get_project_store

USER_ID = "00000000-0000-4000-8000-000000000010"
OTHER_USER_ID = "00000000-0000-4000-8000-000000000020"
CUBE = "result = Box(10, 10, 10)"


def agent_state(**overrides):
    state = {
        "code": CUBE,
        "plan": "Create a 10 mm cube.",
        "inspection": {
            "valid": True,
            "shape_type": "Solid",
            "solid_count": 1,
            "volume_mm3": 1000,
            "bounding_box_mm": {"x": 10, "y": 10, "z": 10},
            "error": None,
        },
        "validation_error": None,
        "repair_attempts": 0,
        "trace": [{"node": "inspect", "status": "passed", "detail": "Built 1 solid."}],
        "usage": {"input_tokens": 100, "output_tokens": 25, "total_tokens": 125},
    }
    state.update(overrides)
    return state


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "projects.db")


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    main.app.dependency_overrides[get_project_store] = lambda: store
    main.app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def use_agent(monkeypatch, fake):
    monkeypatch.setattr(runs, "run_cad_agent", fake)


def start(client, content="Make a cube", **extra):
    response = client.post(
        "/cad/runs",
        json={
            "messages": [{"role": "user", "content": content}],
            "modelId": "anthropic/claude-opus-5",
            **extra,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def wait_for(client, run_id):
    for _ in range(100):
        record = client.get(f"/cad/runs/{run_id}").json()
        if record["status"] != "running":
            return record
        time.sleep(0.02)
    raise AssertionError("run never finished")


def test_successful_run_is_saved_as_a_new_project(client, monkeypatch):
    async def fake_agent(*_args, **_kwargs):
        return agent_state()

    use_agent(monkeypatch, fake_agent)
    started = start(client, "A wall-mount bracket, 80 mm wide")
    assert started["status"] == "running"
    assert started["prompt"] == "A wall-mount bracket, 80 mm wide"

    record = wait_for(client, started["runId"])
    assert record["status"] == "succeeded"
    assert record["error"] is None
    assert record["result"]["code"] == CUBE
    assert record["result"]["revisionNumber"] == 1
    assert record["result"]["usage"]["total_tokens"] == 125

    project = client.get(f"/projects/{record['projectId']}").json()
    assert project["name"] == "A wall-mount bracket, 80 mm wide"
    state = project["latestRevision"]["state"]
    assert state["code"] == CUBE
    assert state["lastRunId"] == started["runId"]
    assert [message["role"] for message in state["messages"]] == ["user", "assistant"]
    assert state["messages"][1]["agent"]["runId"] == started["runId"]


def test_run_for_an_existing_project_appends_a_revision(client, monkeypatch):
    async def fake_agent(*_args, **_kwargs):
        return agent_state(code="result = Box(20, 10, 10)")

    use_agent(monkeypatch, fake_agent)
    project = client.post("/projects", json={"name": "Bracket"}).json()

    record = wait_for(
        client, start(client, "Make it wider", projectId=project["id"])["runId"]
    )

    assert record["projectId"] == project["id"]
    assert record["result"]["revisionNumber"] == 2
    latest = client.get(f"/projects/{project['id']}").json()["latestRevision"]
    assert latest["state"]["code"] == "result = Box(20, 10, 10)"


def test_failed_repairs_keep_the_last_attempt(client, monkeypatch):
    async def fake_agent(*_args, **_kwargs):
        return agent_state(
            code="result = broken_shape",
            validation_error="NameError: broken_shape",
            repair_attempts=3,
        )

    use_agent(monkeypatch, fake_agent)
    record = wait_for(client, start(client)["runId"])

    assert record["status"] == "failed"
    assert "NameError: broken_shape" in record["error"]
    assert record["result"]["code"] == "result = broken_shape"
    assert record["result"]["usage"]["total_tokens"] == 125
    assert record["projectId"] is None
    assert client.get("/projects").json() == []


def test_timed_out_run_keeps_partial_work(client, monkeypatch):
    async def fake_agent(*_args, **_kwargs):
        raise CadRunTimeoutError(300, agent_state(code="", plan="Half a plan."))

    use_agent(monkeypatch, fake_agent)
    record = wait_for(client, start(client)["runId"])

    assert record["status"] == "failed"
    assert "300 seconds" in record["error"]
    assert record["result"]["plan"] == "Half a plan."


def test_agent_crash_is_recorded(client, monkeypatch):
    async def fake_agent(*_args, **_kwargs):
        raise RuntimeError("OpenRouter is down")

    use_agent(monkeypatch, fake_agent)
    record = wait_for(client, start(client)["runId"])

    assert record["status"] == "failed"
    assert record["error"] == "CAD agent failed: OpenRouter is down"
    assert record["result"] is None


def test_run_requires_a_trailing_user_message(client):
    response = client.post(
        "/cad/runs",
        json={
            "messages": [{"role": "assistant", "content": "code"}],
            "modelId": "anthropic/claude-opus-5",
        },
    )
    assert response.status_code == 400


def test_run_rejects_someone_elses_project(client, store):
    other = store.create_project(
        runs.ProjectCreate(name="Not yours"), user_id=OTHER_USER_ID
    )
    response = client.post(
        "/cad/runs",
        json={
            "messages": [{"role": "user", "content": "Edit it"}],
            "modelId": "anthropic/claude-opus-5",
            "projectId": other.id,
        },
    )
    assert response.status_code == 404


def test_runs_are_private_to_their_owner(client, store):
    store.create_run(
        "11111111-1111-4111-8111-111111111111",
        user_id=OTHER_USER_ID,
        project_id=None,
        prompt="secret",
        model_id="m",
    )
    response = client.get("/cad/runs/11111111-1111-4111-8111-111111111111")
    assert response.status_code == 404


def test_run_orphaned_by_a_restart_is_reported_as_failed(client, store, monkeypatch):
    store.create_run(
        "22222222-2222-4222-8222-222222222222",
        user_id=USER_ID,
        project_id=None,
        prompt="Make a cube",
        model_id="m",
    )
    later = datetime.now(timezone.utc) + timedelta(hours=1)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return later

    monkeypatch.setattr(runs, "datetime", Clock)
    record = client.get("/cad/runs/22222222-2222-4222-8222-222222222222").json()

    assert record["status"] == "failed"
    assert "interrupted" in record["error"]


def test_thumbnail_round_trip(client):
    project = client.post("/projects", json={"name": "Bracket"}).json()
    assert project["thumbnailUpdatedAt"] is None
    assert client.get(f"/projects/{project['id']}/thumbnail").status_code == 404

    image = b"RIFF\x00\x00\x00\x00WEBPVP8 "
    response = client.put(
        f"/projects/{project['id']}/thumbnail",
        content=image,
        headers={"Content-Type": "image/webp"},
    )
    assert response.status_code == 204

    fetched = client.get(f"/projects/{project['id']}/thumbnail")
    assert fetched.status_code == 200
    assert fetched.content == image
    assert fetched.headers["content-type"] == "image/webp"
    listed = client.get("/projects").json()[0]
    assert listed["thumbnailUpdatedAt"] is not None


def test_thumbnail_rejects_wrong_type_and_oversize(client):
    project = client.post("/projects", json={"name": "Bracket"}).json()
    path = f"/projects/{project['id']}/thumbnail"

    wrong_type = client.put(
        path, content=b"<svg/>", headers={"Content-Type": "image/svg+xml"}
    )
    too_big = client.put(
        path, content=b"x" * (512 * 1024 + 1), headers={"Content-Type": "image/png"}
    )

    assert wrong_type.status_code == 415
    assert too_big.status_code == 413


def test_run_progress_is_returned_after_a_cursor(client, monkeypatch):
    async def fake_agent(*_args, on_event=None, **_kwargs):
        await on_event({"stage": "plan", "status": "started", "message": "Planning."})
        await on_event(
            {"stage": "plan", "status": "complete", "message": "A cube.", "duration_ms": 5}
        )
        return agent_state()

    use_agent(monkeypatch, fake_agent)
    record = wait_for(client, start(client)["runId"])

    stages = [(event["stage"], event["status"]) for event in record["events"]]
    assert stages[:2] == [("plan", "started"), ("plan", "complete")]
    assert record["events"][1]["durationMs"] == 5
    assert [event["seq"] for event in record["events"]] == list(
        range(1, len(record["events"]) + 1)
    )

    later = client.get(f"/cad/runs/{record['runId']}?after=2").json()
    assert [event["seq"] for event in later["events"]] == [
        event["seq"] for event in record["events"][2:]
    ]


def test_run_events_are_private_to_their_owner(client, store, monkeypatch):
    async def fake_agent(*_args, on_event=None, **_kwargs):
        await on_event({"stage": "plan", "status": "started", "message": "Planning."})
        return agent_state()

    use_agent(monkeypatch, fake_agent)
    run_id = wait_for(client, start(client)["runId"])["runId"]

    assert store.list_run_events(run_id, user_id=OTHER_USER_ID) == []
    with pytest.raises(runs.RunNotFoundError):
        store.add_run_event(
            run_id,
            store.list_run_events(run_id, user_id=USER_ID)[0],
            user_id=OTHER_USER_ID,
        )
