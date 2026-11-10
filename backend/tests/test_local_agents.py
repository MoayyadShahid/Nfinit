import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from agent.local import agent_command, prepare_input
from agent.local_access import local_agents_enabled, require_local_access
from agent.models import CadRunRequest
from agent.graph import _conversation_messages
from agent.prompts import (
    CAD_SYSTEM_PROMPT,
    DIMENSION_READING_RULES,
    KERNEL_PITFALLS,
    PLANNER_PROMPT,
    REVIEW_RULES,
    local_agent_prompt,
)


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


def test_local_prompt_has_the_dimension_pitfall_and_review_rules(tmp_path):
    request = CadRunRequest(modelId="local/codex", messages=[{"role": "user", "content": "A 3 mm base with 12 mm walls"}])
    _images, prompt = prepare_input(request, tmp_path)

    assert prompt == local_agent_prompt((tmp_path / "context.txt").read_text())
    for block in (DIMENSION_READING_RULES, KERNEL_PITFALLS, REVIEW_RULES):
        assert block in prompt
    assert "Return only executable Python code" not in prompt
    assert "Return only Python code" not in prompt
    assert prompt.index("<procedure>") < prompt.index("<available_api>")
    assert prompt.endswith("user: A 3 mm base with 12 mm walls")


def test_hosted_prompts_keep_their_wording():
    # The planner is unchanged; the coder gains only the pitfalls.
    assert hashlib.sha256(PLANNER_PROMPT.encode()).hexdigest() == (
        "57b74437e8913507c46751d1c7c9b9233c8f8a32770003d576f20775c582746d"
    )
    assert DIMENSION_READING_RULES in PLANNER_PROMPT
    assert CAD_SYSTEM_PROMPT.startswith("<role>\nYou are a production build123d CAD code generator")
    assert KERNEL_PITFALLS in CAD_SYSTEM_PROMPT
    assert REVIEW_RULES not in CAD_SYSTEM_PROMPT
