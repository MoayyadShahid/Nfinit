import json

import pytest

from agent.cad_mcp import CadTools
from agent.local import ProgressRelay
from agent.models import ModelInspection


def lines(workspace):
    return [json.loads(line) for line in (workspace / "progress.jsonl").read_text().splitlines()]


def test_bridge_reports_each_tool_call(tmp_path, monkeypatch):
    def fake_review(code, topology=False, draw=True, glb_to=None):
        glb_to.write_bytes(b"glb")
        return ModelInspection(valid=True, solid_count=1, bounding_box_mm={"x": 40, "y": 30, "z": 12},
                               checks=[{"name": "width", "actual": 40, "expected": 40, "tolerance": 0.01, "passed": True}],
                               warnings=["2 separate solids"]), [], None

    monkeypatch.setattr("agent.cad_mcp.review_code", fake_review)
    monkeypatch.setattr("agent.cad_mcp.query_code", lambda code, query: {"distance_mm": 4.25})
    monkeypatch.setattr("agent.cad_mcp.printability_code", lambda code, profile: {
        "profile": {}, "facts": {"overhangs": {"area_mm2": 0}, "orientations": [], "not_measured": []},
        "findings": [{"rule": "min_wall", "status": "fail", "measured": 0.6, "limit": 1.2, "where": None,
                      "face_ids": [], "suggestion": ""}]})
    tools = CadTools(tmp_path)
    tools.call("declare_requirements", {"summary": "A 40 by 30 by 12 mm box.", "requirements": [
        {"id": "width", "text": "Width 40 mm", "kind": "dimension", "expected": 40},
        {"id": "depth", "text": "Depth 30 mm", "kind": "dimension", "expected": 30}]})
    tools.call("build_model", {"code": "result = Box(40, 30, 12)"})
    tools.call("inspect_model", {"query": {"kind": "distance", "a": "boss", "b": [0, 0, 0]}})
    tools.call("check_printability", {})

    assert lines(tmp_path) == [
        {"stage": "requirements", "status": "complete", "message": "2 requirements: A 40 by 30 by 12 mm box.", "attempt": None},
        {"stage": "build", "status": "started", "message": "Build 1", "attempt": 1},
        {"stage": "build", "status": "complete",
         "message": "Build 1: 1 of 2 requirements pass, 40 × 30 × 12 mm, 1 warning", "attempt": 1},
        {"stage": "snapshot", "status": "ready", "message": "build 1", "attempt": None, "glb": "build-1.glb"},
        {"stage": "measure", "status": "complete", "message": "Distance: 4.25 mm", "attempt": None},
        {"stage": "printability", "status": "complete", "message": "1 to look at: min wall", "attempt": None},
    ]


def test_a_failed_build_is_reported_without_a_preview(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.cad_mcp.review_code", lambda code, **_: (
        ModelInspection(valid=False, error="cad_execution_error: NameError: Bx"), [], None))
    tools = CadTools(tmp_path)
    tools.call("declare_requirements", {"summary": "A box.", "requirements": []})
    tools.call("build_model", {"code": "result = Bx(1, 1, 1)"})

    assert lines(tmp_path)[-1] == {"stage": "build", "status": "failed",
                                   "message": "Build 1 failed: cad_execution_error: NameError: Bx", "attempt": 1}


@pytest.mark.asyncio
async def test_relay_passes_new_lines_and_previews_once(tmp_path):
    received = []

    async def on_event(event, glb=None):
        received.append((event, glb))

    relay = ProgressRelay(tmp_path, on_event)
    await relay.flush()
    assert received == []

    (tmp_path / "build-1.glb").write_bytes(b"model")
    (tmp_path / "progress.jsonl").write_text(
        json.dumps({"stage": "requirements", "status": "complete", "message": "2 requirements", "attempt": None}) + "\n"
        + json.dumps({"stage": "snapshot", "status": "ready", "message": "build 1", "attempt": None, "glb": "build-1.glb"}) + "\n"
        + json.dumps({"stage": "snapshot", "status": "ready", "message": "x", "glb": "../secret.glb"}) + "\n"
        + '{"stage": "build", "status": "sta'
    )
    await relay.flush()
    await relay.flush()

    assert received == [
        ({"stage": "plan", "status": "complete", "message": "Plan ready"}, None),
        ({"stage": "requirements", "status": "complete", "message": "2 requirements", "attempt": None}, None),
        ({"stage": "snapshot", "status": "ready", "message": "build 1", "attempt": None}, b"model"),
    ]

    with (tmp_path / "progress.jsonl").open("a") as handle:
        handle.write('rted", "message": "Build 2", "attempt": 2}\n')
    await relay.flush()
    assert received[-1] == ({"stage": "build", "status": "started", "message": "Build 2", "attempt": 2}, None)
