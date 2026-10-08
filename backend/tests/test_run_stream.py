import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

import main
from projects import meshes, runs
from projects.auth import get_current_user_id
from projects.store import ProjectStore, get_project_store

USER_ID = "00000000-0000-4000-8000-000000000010"
OTHER_USER_ID = "00000000-0000-4000-8000-000000000020"
CUBE = "result = Box(10, 10, 10)"


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "projects.db")


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    # The fake agent's code never reaches the sandbox.
    monkeypatch.setattr(runs, "store_mesh_for_code", lambda *_a, **_k: None)
    main.app.dependency_overrides[get_project_store] = lambda: store
    main.app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


def agent_that_takes(seconds: float):
    async def fake_agent(*_args, on_event=None, **_kwargs):
        await on_event({"stage": "plan", "status": "started", "message": "Planning."})
        await asyncio.sleep(seconds)
        await on_event(
            {"stage": "plan", "status": "complete", "message": "A cube.", "duration_ms": 1}
        )
        return {
            "code": CUBE,
            "plan": "A cube.",
            "inspection": {"valid": True},
            "validation_error": None,
            "trace": [],
            "usage": {},
        }

    return fake_agent


def start(client) -> str:
    response = client.post(
        "/cad/runs",
        json={
            "messages": [{"role": "user", "content": "A cube"}],
            "modelId": "anthropic/claude-opus-5",
        },
    )
    assert response.status_code == 202, response.text
    return response.json()["runId"]


def stream_url(client, run_id: str) -> str:
    response = client.post(f"/cad/runs/{run_id}/stream")
    assert response.status_code == 200, response.text
    return response.json()["url"]


def read_stream(client, url: str, headers: dict | None = None):
    """Return the stream's messages as (event, id, data) tuples, and comments."""
    messages, comments, current = [], [], {}
    with client.stream("GET", url, headers=headers or {}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith(":"):
                comments.append(line)
            elif line == "":
                if "event" in current:
                    messages.append(
                        (current["event"], current.get("id"), json.loads(current["data"]))
                    )
                current = {}
            else:
                field, _, value = line.partition(": ")
                current[field] = value
    return messages, comments


def test_stream_sends_each_event_live_then_done(client, monkeypatch):
    monkeypatch.setattr(runs, "run_cad_agent", agent_that_takes(0.5))
    run_id = start(client)

    started = time.monotonic()
    messages, _ = read_stream(client, stream_url(client, run_id))
    elapsed = time.monotonic() - started

    progress = [m for m in messages if m[0] == "progress"]
    assert [(m[2]["stage"], m[2]["status"]) for m in progress] == [
        ("plan", "started"),
        ("plan", "complete"),
        ("mesh", "started"),
    ]
    assert [m[1] for m in progress] == ["1", "2", "3"]
    assert messages[-1] == ("done", None, {"status": "succeeded"})
    # Woken by the run itself, not by the 2 s database poll.
    assert elapsed < 1.8


def test_stream_resumes_after_the_last_event_id(client, monkeypatch):
    monkeypatch.setattr(runs, "run_cad_agent", agent_that_takes(0))
    run_id = start(client)
    url = stream_url(client, run_id)
    read_stream(client, url)  # wait for the run to finish

    messages, _ = read_stream(client, url, headers={"Last-Event-ID": "2"})

    assert [m[1] for m in messages if m[0] == "progress"] == ["3"]
    assert messages[-1][0] == "done"


def test_quiet_stream_sends_heartbeats(client, monkeypatch):
    monkeypatch.setattr(runs, "run_cad_agent", agent_that_takes(1.0))
    monkeypatch.setattr(runs, "STREAM_HEARTBEAT_SECONDS", 0.2)
    monkeypatch.setattr(runs, "STREAM_POLL_SECONDS", 0.1)
    run_id = start(client)

    _, comments = read_stream(client, stream_url(client, run_id))

    assert ": ping" in comments


def test_stream_links_are_checked(client, store, monkeypatch):
    monkeypatch.setattr(runs, "run_cad_agent", agent_that_takes(0))
    run_id = start(client)
    other_run = start(client)
    token = stream_url(client, run_id).split("token=")[1]

    # A link for one run does not open another run's stream.
    assert client.get(f"/cad/runs/{other_run}/events?token={token}").status_code == 404
    # A changed or missing token is refused.
    changed = token[:-1] + ("1" if token[-1] == "0" else "0")
    assert client.get(f"/cad/runs/{run_id}/events?token={changed}").status_code == 404
    assert client.get(f"/cad/runs/{run_id}/events").status_code == 422
    # A mesh link is not an event stream link, even with the same secret.
    mesh_token = meshes.sign_mesh_token(
        user_id=USER_ID, project_id=run_id, revision_number=1,
        expires_at=int(time.time()) + 60,
    )
    assert client.get(f"/cad/runs/{run_id}/events?token={mesh_token}").status_code == 404
    # Only the run's owner can ask for a link.
    main.app.dependency_overrides[get_current_user_id] = lambda: OTHER_USER_ID
    assert client.post(f"/cad/runs/{run_id}/stream").status_code == 404


def test_expired_stream_link_is_refused(client, monkeypatch):
    monkeypatch.setattr(runs, "run_cad_agent", agent_that_takes(0))
    run_id = start(client)
    expired = runs.sign_token(
        "run-events", {"u": USER_ID, "r": run_id}, expires_at=int(time.time()) - 1
    )
    assert client.get(f"/cad/runs/{run_id}/events?token={expired}").status_code == 410


def test_build_previews_become_events_with_fetchable_meshes(client, store, monkeypatch):
    from agent import ModelInspection
    from execution import BuildSnapshot

    def fake_inspect(code):
        return ModelInspection(valid=True), [
            BuildSnapshot("base", "Base plate", b"glTF-base"),
            BuildSnapshot("holes", "Mounting holes", b"glTF-holes"),
        ]

    async def fake_agent(_request, _api_key, inspect_code, on_event=None, **_kwargs):
        await on_event({"stage": "inspect", "status": "started", "message": "Checking."})
        inspection = await asyncio.to_thread(inspect_code, CUBE)
        await on_event({"stage": "inspect", "status": "passed", "message": "Built."})
        assert inspection.valid
        return {
            "code": CUBE, "plan": "A cube.", "inspection": {"valid": True},
            "validation_error": None, "trace": [], "usage": {},
        }

    monkeypatch.setattr(runs, "inspect_with_snapshots", fake_inspect)
    monkeypatch.setattr(runs, "run_cad_agent", fake_agent)
    run_id = start(client)
    messages, _ = read_stream(client, stream_url(client, run_id))
    progress = [m[2] for m in messages if m[0] == "progress"]

    snapshots = [event for event in progress if event["stage"] == "snapshot"]
    assert [event["message"] for event in snapshots] == ["Base plate", "Mounting holes"]
    # Previews arrive while the check step runs, before it passes.
    stages = [(event["stage"], event["status"]) for event in progress]
    assert stages.index(("snapshot", "ready")) < stages.index(("inspect", "passed"))

    first = client.get(f"/cad/runs/{run_id}/snapshots/{snapshots[0]['seq']}")
    assert first.status_code == 200
    assert first.content == b"glTF-base"
    assert first.headers["content-type"] == "model/gltf-binary"
    assert client.get(f"/cad/runs/{run_id}/snapshots/999").status_code == 404

    main.app.dependency_overrides[get_current_user_id] = lambda: OTHER_USER_ID
    assert (
        client.get(f"/cad/runs/{run_id}/snapshots/{snapshots[0]['seq']}").status_code
        == 404
    )


def test_snapshot_cache_drops_the_oldest_previews(monkeypatch):
    monkeypatch.setattr(runs, "_snapshots", runs.OrderedDict())
    monkeypatch.setattr(runs, "_snapshot_bytes", 0)
    monkeypatch.setattr(runs, "SNAPSHOT_CACHE_BYTES", 10)

    for seq in range(1, 5):
        runs._remember_snapshot("run", seq, USER_ID, b"1234")

    assert list(runs._snapshots) == [("run", 3), ("run", 4)]
