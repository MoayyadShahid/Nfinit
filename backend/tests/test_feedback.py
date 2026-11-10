import json

from agent.feedback import agent_view, printability_view
from agent.graph import longest_run_timeout_seconds, run_timeout_seconds

INSPECTION = {
    "valid": True,
    "shape_type": "Part",
    "solid_count": 1,
    "volume_mm3": 1000.0,
    "bounding_box_mm": {"x": 10, "y": 10, "z": 10},
    "checks": [
        {"name": "width", "actual": 10, "expected": 10, "tolerance": 0.01, "passed": True},
        {"name": "spare", "actual": 3, "expected": 4, "tolerance": 0.01, "passed": False},
    ],
    "verification": "failed",
    "solids": [{"volume_mm3": 1000.0, "bounding_box_mm": {}, "min_mm": [0, 0, 0], "manifold": True, "inverted": False}],
    "warnings": [],
    "census": {
        "holes": [{"diameter_mm": 4.0, "count": 9, "axis": [0, 0, 1], "length_mm": 6,
                   "centers_mm": [[index, 0, 0] for index in range(9)]}],
        "bosses": [],
        "rounded_edges": [{"radius_mm": 2.0, "count": 4, "surface": "cylinder"}],
        "partial_cylinders": 0,
        "face_counts": {"plane": 6, "cylinder": 13},
        "features": [{"id": "plate", "operation": "additive", "owned_faces": 6}],
    },
    "acceptance": {
        "verdict": "partial", "passed": 1, "failed": 0, "review": 0, "unverified": 1, "not_measurable": 0,
        "rows": [
            {"id": "width", "text": "Width 10 mm", "status": "passed", "expected": 10, "measured": 10,
             "source": "user", "detail": "Measured 10 against 10 ± 0.01."},
            {"id": "depth", "text": "Depth 10 mm", "status": "unverified", "expected": 10, "measured": None,
             "source": "user", "detail": "No check_measurement named 'depth'."},
        ],
        "rejected_checks": [],
        "assumptions": ["A long assumption the agent wrote itself."],
        "summary": "A 10 mm cube.",
    },
}


def test_agent_view_keeps_decisions_and_drops_echoes():
    view = agent_view(INSPECTION)

    assert view["acceptance"] == {
        "verdict": "partial",
        "rows": [
            {"id": "width", "status": "passed", "measured": 10},
            {"id": "depth", "status": "unverified", "expected": 10,
             "detail": "No check_measurement named 'depth'."},
        ],
    }
    assert view["checks"] == [{"name": "spare", "actual": 3, "expected": 4, "passed": False}]
    assert view["census"] == {
        "holes": [{"diameter_mm": 4.0, "count": 9, "length_mm": 6, "axis": [0, 0, 1],
                   "centers_mm": [[index, 0, 0] for index in range(6)]}],
        "rounded_edges": [[2.0, 4, "cylinder"]],
    }
    assert "solids" not in view and "warnings" not in view
    assert len(json.dumps(view)) < len(json.dumps(INSPECTION)) / 2


def test_agent_view_lists_solids_only_when_something_is_wrong():
    floating = {**INSPECTION, "solid_count": 2, "solids": INSPECTION["solids"] * 2, "warnings": ["2 separate solids"]}
    inverted = {**INSPECTION, "solids": [{**INSPECTION["solids"][0], "inverted": True}]}

    assert len(agent_view(floating)["solids"]) == 2
    assert agent_view(floating)["warnings"] == ["2 separate solids"]
    assert agent_view(inverted)["solids"][0]["inverted"] is True


def test_printability_view_keeps_findings_that_need_action():
    report = {
        "profile": {"min_wall_mm": 1.2},
        "facts": {
            "wall_thickness": {"min_mm": 0.6, "p05_mm": 0.6, "median_mm": 2.0, "thinnest": [{}] * 10},
            "overhangs": {"area_mm2": 0.0, "largest": []},
            "orientations": [{"name": "current_plus_z", "overhang_area_mm2": 0, "build_height_mm": 20}],
            "not_measured": ["warping"],
        },
        "findings": [
            {"rule": "bed_fit", "status": "pass", "measured": [1, 1, 1], "limit": [2, 2, 2], "where": None,
             "face_ids": [], "suggestion": ""},
            {"rule": "min_wall", "status": "fail", "measured": {"p05_mm": 0.6}, "limit": 1.2, "where": [0, 0, 1],
             "face_ids": ["face_1"], "suggestion": "Thicken the walls."},
            {"rule": "warping", "status": "unverified", "measured": None, "limit": None, "where": None,
             "face_ids": [], "suggestion": "Not measured by Nfinit."},
        ],
    }
    view = printability_view(report)

    assert view["findings"] == [{"rule": "min_wall", "status": "fail", "measured": {"p05_mm": 0.6},
                                 "limit": 1.2, "where": [0, 0, 1], "suggestion": "Thicken the walls."}]
    assert view["passed"] == ["bed_fit"]
    assert view["wall_mm"] == {"min_mm": 0.6, "p05_mm": 0.6, "median_mm": 2.0}


def test_bridge_reports_budgets_and_time(tmp_path):
    from agent.cad_mcp import BUDGETS, CadTools

    tools = CadTools(tmp_path)
    result = json.loads(tools.call("declare_requirements", {"summary": "A cube.", "requirements": [
        {"id": "width", "text": "Width 10 mm", "kind": "dimension", "expected": 10}]})["content"][0]["text"])

    assert result["declared"] == 1 and result["ids"] == ["width"]
    assert result["budget_left"] == {**BUDGETS, "declarations": BUDGETS["declarations"] - 1}
    assert isinstance(result["ms"], int)


def test_local_runs_get_a_longer_deadline(monkeypatch):
    monkeypatch.delenv("CAD_RUN_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("CAD_LOCAL_RUN_TIMEOUT_SECONDS", raising=False)

    assert run_timeout_seconds() == 300
    assert run_timeout_seconds("anthropic/claude-sonnet-5.5") == 300
    assert run_timeout_seconds("local/claude") == 900
    monkeypatch.setenv("CAD_LOCAL_RUN_TIMEOUT_SECONDS", "1200")
    assert longest_run_timeout_seconds() == 1200
