import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from agent.local import agent_command, prepare_input
from agent.local_access import local_agents_enabled, require_local_access
from agent.models import CadRunRequest
from agent.graph import _conversation_messages


@pytest.fixture
def local_env(monkeypatch):
    monkeypatch.setenv("NFNIT_LOCAL_AGENTS", "true")
    monkeypatch.setenv("NFNIT_LOCAL_TOKEN", "a" * 40)
    monkeypatch.setenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS", "true")


def test_local_access_requires_token_and_loopback(local_env):
    assert local_agents_enabled()
    request = SimpleNamespace(headers={"x-nfinit-local-token": "a" * 40}, client=SimpleNamespace(host="127.0.0.1"))
    require_local_access(request)
    request.client.host = "198.51.100.2"
    with pytest.raises(HTTPException):
        require_local_access(request)
    request.client.host = "127.0.0.1"
    request.headers = {}
    with pytest.raises(HTTPException):
        require_local_access(request)


def test_local_agents_need_the_local_workspace(local_env, monkeypatch):
    monkeypatch.delenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS")
    assert not local_agents_enabled()
    monkeypatch.setenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS", "true")
    monkeypatch.setenv("NFNIT_LOCAL_TOKEN", "too-short")
    assert not local_agents_enabled()


def test_cli_commands_keep_permissions_and_own_auth(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.local.shutil.which", lambda command: "/bin/" + command)
    for provider in ("local/claude", "local/codex"):
        args = agent_command(provider, tmp_path, [])
        assert not any("dangerously" in arg for arg in args)
        assert not any("api-key" in arg or "token" in arg for arg in args)
        assert "nfinit" in " ".join(args)
    assert "read-only" in agent_command("local/codex", tmp_path, [])
    assert "--strict-mcp-config" in agent_command("local/claude", tmp_path, [])


def test_reference_images_survive_followup(tmp_path):
    content = [{"type": "text", "text": "Use this shape"},
               {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}}]
    messages = [{"role": "user", "content": content}, {"role": "user", "content": "Add holes"}]
    history = _conversation_messages({"messages": messages, "selection": None, "current_code": ""})
    assert history[0]["content"] == content
    request = CadRunRequest(modelId="local/claude", messages=messages)
    images, payload = prepare_input(request, tmp_path)
    assert images[0].read_bytes() == b"hello"
    assert any(part["type"] == "image" for part in json.loads(payload)["message"]["content"])
    assert "Add holes" in (tmp_path / "context.txt").read_text()
