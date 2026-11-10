import json
from pathlib import Path

import pytest

from agent.acceptance import change_report, evaluate, parse_requirements
from agent.cad_mcp import CadTools
from execution import review_code

ROOT = Path(__file__).parents[1] / "evaluation"
START = next(
    case["current_code"]
    for case in json.loads((ROOT / "cases" / "loop20.json").read_text())["cases"]
    if case["id"] == "edit_thickness_keeps_features"
)


def report(code: str) -> dict:
    before, _, start_topology = review_code(START, topology=True, draw=False)
    after, _, topology = review_code(code, topology=True, draw=False)
    assert before.valid and after.valid, after.error
    return change_report(
        {"topology": start_topology, "inspection": before.model_dump()}, topology, after.model_dump()
    )


def test_a_requested_change_raises_no_flags():
    changes = report(START.replace("70.0, 40.0, 5.0", "70.0, 40.0, 8.0"))

    assert changes["flags"] == []
    assert changes["bounds_delta_mm"] == {"x": 0, "y": 0, "z": 3}
    assert changes["features"]["removed"] == []
    assert "plate" in changes["features"]["modified"]


def test_losing_the_rounded_corners_is_flagged():
    code = "\n".join(
        line for line in START.splitlines()
        if "fillet(" not in line and "corner_fillets" not in line and "parent_id=\"plate\", parameters={\"radius\"" not in line
    )
    changes = report(code)

    assert "Feature 'corner_fillets' was removed." in changes["flags"]
    assert "Rounded edges went from 4 to 0 (4 mm 4 → 0)." in changes["flags"]
    assert changes["census_delta"]["Rounded edges of 4 mm"] == "4 → 0"


def test_flags_make_the_acceptance_need_review():
    requirements = parse_requirements({"summary": "A plate.", "requirements": []})
    flagged = evaluate(requirements, {"valid": True, "changes": {"flags": ["Feature 'x' was removed."]}})
    clean = evaluate(requirements, {"valid": True, "changes": {"flags": []}})

    assert flagged["verdict"] == "partial" and flagged["review"] == 1
    assert flagged["rows"][-1]["detail"] == "Feature 'x' was removed."
    assert clean["verdict"] == "verified"


def test_the_bridge_measures_the_start_once_and_reports_changes(tmp_path, monkeypatch):
    from agent.models import ModelInspection

    calls = []

    def fake_review(code, topology=False, draw=True):
        calls.append((code, topology, draw))
        return ModelInspection(valid=True, census={"rounded_edges": []}), [], {"valid": True}

    monkeypatch.setattr("agent.cad_mcp.review_code", fake_review)
    monkeypatch.setattr("agent.cad_mcp.change_report", lambda previous, topology, current: {"flags": ["x"]})
    (tmp_path / "start.py").write_text("result = Box(1, 1, 1)")
    tools = CadTools(tmp_path)
    tools.call("declare_requirements", {"summary": "A box.", "requirements": []})
    for _ in range(2):
        result = tools.call("build_model", {"code": "result = Box(2, 1, 1)"})

    assert calls == [
        ("result = Box(1, 1, 1)", True, False),
        ("result = Box(2, 1, 1)", True, True),
        ("result = Box(2, 1, 1)", True, True),
    ]
    reported = json.loads(result["content"][0]["text"])
    assert reported["changes"] == {"flags": ["x"]}
    assert reported["acceptance"]["rows"][-1]["status"] == "review"


def test_a_new_part_has_no_change_report(tmp_path, monkeypatch):
    from agent.models import ModelInspection

    monkeypatch.setattr("agent.cad_mcp.review_code", lambda code, topology=False, draw=True: (
        ModelInspection(valid=True), [], {"valid": True} if topology else None))
    tools = CadTools(tmp_path)
    tools.call("declare_requirements", {"summary": "A box.", "requirements": []})
    reported = json.loads(tools.call("build_model", {"code": "result = Box(1, 1, 1)"})["content"][0]["text"])

    assert "changes" not in reported
    assert json.loads((tmp_path / "previous.json").read_text()) == {}


def test_resizing_holes_is_not_a_loss():
    changes = report(START.replace("hole_diameter = 6.0", "hole_diameter = 8.0"))

    assert changes["flags"] == []
    assert changes["census_delta"] == {"Holes of 6 mm": "2 → 0", "Holes of 8 mm": "0 → 2"}


def test_dropping_a_hole_is_a_loss():
    code = START.replace(
        "Locations((-(length / 2 - hole_offset), 0, 0), (length / 2 - hole_offset, 0, 0))",
        "Locations((-(length / 2 - hole_offset), 0, 0))",
    )
    changes = report(code)

    assert "Holes went from 2 to 1 (6 mm 2 → 1)." in changes["flags"]
