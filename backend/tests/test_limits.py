import base64
import time

import pytest
from fastapi.testclient import TestClient

import main
from projects import limits, runs
from projects.auth import get_current_user_id
from projects.store import ProjectStore, get_project_store

USER_ID = "00000000-0000-4000-8000-000000000010"
PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()


@pytest.fixture
def store(tmp_path):
    return ProjectStore(tmp_path / "projects.db")


@pytest.fixture
def client(store, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("CAD_ALLOWED_MODELS", raising=False)
    main.app.dependency_overrides[get_project_store] = lambda: store
    main.app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


@pytest.fixture
def slow_agent(monkeypatch):
    """An agent that never finishes, so started runs stay "running"."""
    import asyncio

    async def never(*_args, **_kwargs):
        await asyncio.sleep(3600)

    monkeypatch.setattr(runs, "run_cad_agent", never)


def start(client, content="A bracket", model="anthropic/claude-sonnet-5.5", **extra):
    return client.post(
        "/cad/runs",
        json={"messages": [{"role": "user", "content": content}], "modelId": model, **extra},
    )


def test_only_the_studio_models_can_be_used(client, slow_agent):
    assert start(client, model="openai/o1-pro").status_code == 400
    assert start(client, planModelId="openai/o1-pro").status_code == 400
    assert start(client).status_code == 202


def test_images_must_be_inline_pictures(client, slow_agent):
    def with_image(url):
        return start(
            client,
            content=[{"type": "text", "text": "Like this"}, {"type": "image_url", "image_url": {"url": url}}],
        )

    assert with_image("http://169.254.169.254/latest/meta-data").status_code == 400
    assert with_image("data:text/html;base64,PHNjcmlwdD4=").status_code == 400
    assert with_image(PNG).status_code == 202


def test_oversized_requests_are_refused(client, slow_agent):
    assert start(client, content="x" * (limits.MAX_TEXT_CHARS + 1)).status_code == 413
    too_many = [{"type": "image_url", "image_url": {"url": PNG}}] * (limits.MAX_IMAGES + 1)
    assert start(client, content=too_many).status_code == 413
    assert start(client, code="x" * (limits.MAX_CODE_CHARS + 1)).status_code == 413


def test_concurrent_runs_are_capped(client, slow_agent, monkeypatch):
    monkeypatch.setenv("CAD_MAX_CONCURRENT_RUNS", "2")
    assert start(client).status_code == 202
    assert start(client).status_code == 202
    third = start(client)
    assert third.status_code == 429
    assert "building" in third.json()["detail"]


def test_hourly_runs_are_capped(client, store, monkeypatch):
    async def instant(*_args, **_kwargs):
        raise RuntimeError("done")

    monkeypatch.setattr(runs, "run_cad_agent", instant)
    monkeypatch.setenv("CAD_MAX_RUNS_PER_HOUR", "3")
    for _ in range(3):
        assert start(client).status_code == 202
    for _ in range(50):  # let the failed runs finish
        epoch = limits.datetime.min.replace(tzinfo=limits.timezone.utc)
        if store.count_runs(user_id=USER_ID, since=epoch, running_since=epoch)[0] == 0:
            break
        time.sleep(0.02)
    response = start(client)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "600"


def test_sandbox_calls_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(limits, "_sandbox_limiter", limits.SlidingWindowLimiter(2, 60))
    monkeypatch.setattr(main, "_inspect_code", lambda _code: main.ModelInspection(valid=True))
    for _ in range(2):
        assert client.post("/inspect-model", json={"code": "result = Box(1, 1, 1)"}).status_code == 200
    limited = client.post("/inspect-model", json={"code": "result = Box(1, 1, 1)"})
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1


def test_sandbox_code_size_is_capped(client):
    response = client.post("/generate-mesh", json={"code": "x" * (limits.MAX_CODE_CHARS + 1)})
    assert response.status_code == 422


def test_responses_carry_security_headers(client):
    headers = client.get("/health").headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]


def test_runs_lost_by_a_restart_do_not_block_new_runs(client, store, slow_agent, monkeypatch):
    monkeypatch.setenv("CAD_MAX_CONCURRENT_RUNS", "1")
    with store._connect() as connection:
        connection.execute(
            "INSERT INTO cad_runs (id, user_id, status, prompt, model_id, created_at) "
            "VALUES ('lost', ?, 'running', '', '', '2020-01-01T00:00:00+00:00')",
            (USER_ID,),
        )
    assert start(client).status_code == 202


def test_declared_oversized_body_is_refused_before_reading(client, monkeypatch):
    monkeypatch.setenv("CAD_MAX_REQUEST_BYTES", "2048")
    response = client.post(
        "/cad/runs", content=b"x" * 4096, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


def test_streamed_oversized_body_is_stopped(client, monkeypatch):
    monkeypatch.setenv("CAD_MAX_REQUEST_BYTES", "2048")

    def chunks():
        for _ in range(8):
            yield b"x" * 1024

    response = client.post(
        "/cad/runs", content=chunks(), headers={"content-type": "application/json"}
    )
    # Stopped either by this limit (413) or by FastAPI reporting the unread
    # body (400); never parsed as a request.
    assert response.status_code in (400, 413)
