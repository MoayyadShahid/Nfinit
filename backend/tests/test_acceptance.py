import json

import pytest

from agent.acceptance import (
    evaluate,
    parse_requirements,
    self_checks,
    stated_numbers,
    uncovered_numbers,
)
from agent.cad_mcp import CadTools
from agent.local import agent_command


def declared(**overrides):
    arguments = {
        "summary": "An 80 by 50 by 6 mm plate with four 4 mm holes.",
        "bounding_box_mm": {"x": 80, "y": 50, "z": 6},
        "solid_count": 1,
        "requirements": [
            {"id": "hole_diameter", "text": "Holes are 4 mm", "kind": "dimension",
             "expected": 4, "unit": "mm", "tolerance": 0.05},
            {"id": "hole_count", "text": "Four holes", "kind": "count", "expected": 4},
            {"id": "looks_clean", "text": "Edges look clean", "kind": "visual"},
        ],
        "assumptions": ["Holes go through."],
    }
    arguments.update(overrides)
    return arguments


def inspection(**overrides):
    data = {
        "valid": True,
        "solid_count": 1,
        "bounding_box_mm": {"x": 80, "y": 50, "z": 6},
        "checks": [
            {"name": "hole_diameter", "actual": 4.0, "expected": 4, "tolerance": 0.05, "passed": True},
            {"name": "hole_count", "actual": 4, "expected": 4, "tolerance": 0, "passed": True},
        ],
    }
    data.update(overrides)
    return data


MEASURED = (
    "with BuildPart() as part:\n    Box(80, 50, 6)\n"
    "faces = part.part.faces()\n"
    "check_measurement('hole_diameter', faces[0].radius * 2, 4, 0.05)\n"
    "check_measurement('hole_count', len(faces), 4, 0)\n"
)


def test_stated_numbers_read_sizes_but_not_thread_names():
    assert stated_numbers("An 80x50 by 6.5 mm plate, four M4 holes, 12 mm walls.") == [80, 50, 6.5, 12]


def test_uncovered_numbers_names_request_numbers_without_a_requirement():
    requirements = parse_requirements(declared())

    assert uncovered_numbers("An 80 by 50 by 6 mm plate with four 4 mm holes 6 mm from each corner", requirements) == []
    assert uncovered_numbers("A 7 mm boss and a 4 mm hole", requirements) == [7]


def test_self_checks_flag_inputs_compared_with_themselves():
    code = (
        "width = 80.0\nhalf = width / 2\n"
        "with BuildPart() as part:\n    Box(width, 10, 5)\n"
        "measured = part.part.bounding_box().size.X\n"
        "for index in range(2):\n    pass\n"
        "check_measurement('a', width, 80)\n"
        "check_measurement('b', half * 2, 80)\n"
        "check_measurement('c', part.part.bounding_box().size.X, 80)\n"
        "check_measurement('d', measured, 80)\n"
        "check_measurement('e', index, 1)\n"
        "check_measurement(name='f', actual=3.0, expected=3)\n"
    )

    assert self_checks(code) == ["a", "b", "f"]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (declared(requirements=[{"id": "Bad", "text": "x", "kind": "dimension"}]), "lowercase"),
        (declared(requirements=[{"id": "a", "text": "x", "kind": "colour"}]), "kind"),
        (declared(requirements=[{"id": "a", "text": "x", "kind": "count"}] * 2), "repeated"),
        (declared(bounding_box_mm={"x": -1}), "positive"),
        (declared(solid_count=0), "solid_count"),
        (declared(extra=True), "Unknown fields"),
        (declared(requirements=[{"id": "a", "text": "x", "kind": "count", "tolerance": -1}]), "negative"),
    ],
)
def test_invalid_declarations_are_refused(arguments, message):
    with pytest.raises(ValueError, match=message):
        parse_requirements(arguments)


def test_measured_requirements_pass_and_visual_ones_are_not_measurable():
    acceptance = evaluate(parse_requirements(declared()), inspection(), MEASURED)

    assert acceptance["verdict"] == "verified"
    assert [(row["id"], row["status"]) for row in acceptance["rows"]] == [
        ("overall_size", "passed"),
        ("solid_count", "passed"),
        ("hole_diameter", "passed"),
        ("hole_count", "passed"),
        ("looks_clean", "not_measurable"),
    ]


def test_missing_and_self_checks_leave_requirements_unverified():
    code = "check_measurement('hole_count', 4, 4, 0)\n"
    acceptance = evaluate(
        parse_requirements(declared()),
        inspection(checks=[{"name": "hole_count", "actual": 4, "expected": 4, "tolerance": 0, "passed": True}]),
        code,
    )
    rows = {row["id"]: row for row in acceptance["rows"]}

    assert acceptance["verdict"] == "partial"
    assert rows["hole_diameter"]["status"] == "unverified"
    assert rows["hole_count"]["status"] == "unverified"
    assert "itself" in rows["hole_count"]["detail"]
    assert acceptance["rejected_checks"] == ["hole_count"]


def test_wrong_size_or_solid_count_fails():
    wrong_size = evaluate(parse_requirements(declared()), inspection(bounding_box_mm={"x": 80, "y": 50, "z": 12}), MEASURED)
    two_solids = evaluate(parse_requirements(declared()), inspection(solid_count=2), MEASURED)

    assert wrong_size["verdict"] == "failed"
    assert "Z is 12 mm" in wrong_size["rows"][0]["detail"]
    assert two_solids["verdict"] == "failed"
    assert two_solids["rows"][1] | {"detail": ""} == {
        "id": "solid_count", "text": "Number of solids", "status": "failed",
        "expected": 1, "measured": 2, "source": "user", "detail": "",
    }


def test_bridge_requires_a_declaration_and_reports_acceptance(tmp_path, monkeypatch):
    from agent.models import ModelInspection

    monkeypatch.setattr("agent.cad_mcp.review_code", lambda code: (ModelInspection.model_validate(
        inspection(solid_count=2)), []))
    (tmp_path / "request.txt").write_text("An 80 by 50 by 6 mm plate with four 4 mm holes and a 9 mm slot")
    tools = CadTools(tmp_path)

    with pytest.raises(ValueError, match="declare_requirements first"):
        tools.call("build_model", {"code": MEASURED})
    assert tools.builds == 0

    declaration = json.loads(tools.call("declare_requirements", declared())["content"][0]["text"])
    assert "9" in declaration["warning"]

    result = tools.call("build_model", {"code": MEASURED})
    reported = json.loads(result["content"][0]["text"])
    assert result["isError"]
    assert reported["acceptance"]["verdict"] == "failed"
    assert json.loads((tmp_path / "inspection.json").read_text())["acceptance"]["verdict"] == "failed"


def test_bridge_limits_declarations(tmp_path):
    tools = CadTools(tmp_path)
    for _ in range(4):
        tools.call("declare_requirements", declared())
    with pytest.raises(ValueError, match="four times"):
        tools.call("declare_requirements", declared())


def test_both_clis_may_call_declare_requirements(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.local.shutil.which", lambda command: "/bin/" + command)

    assert "mcp__nfinit__declare_requirements" in agent_command("local/claude", tmp_path, [])
    assert any("declare_requirements.approval_mode" in arg for arg in agent_command("local/codex", tmp_path, []))


def test_inspect_model_answers_about_the_last_part_that_built(tmp_path, monkeypatch):
    from agent.models import ModelInspection

    asked = []
    monkeypatch.setattr("agent.cad_mcp.query_code", lambda code, query: asked.append((code, query)) or {"count": 0})
    tools = CadTools(tmp_path)

    with pytest.raises(ValueError, match="no part yet"):
        tools.call("inspect_model", {"query": {"kind": "summary"}})

    tools.call("declare_requirements", declared(bounding_box_mm={}, solid_count=None, requirements=[]))
    monkeypatch.setattr("agent.cad_mcp.review_code", lambda code: (ModelInspection(valid=True), []))
    tools.call("build_model", {"code": "result = Box(1, 1, 1)"})
    monkeypatch.setattr("agent.cad_mcp.review_code", lambda code: (ModelInspection(valid=False, error="broken"), []))
    tools.call("build_model", {"code": "result = broken"})
    tools.call("inspect_model", {"query": {"kind": "faces"}})

    assert asked == [("result = Box(1, 1, 1)", {"kind": "faces"})]
    assert tools.builds == 2


def test_inspect_model_has_a_budget(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.cad_mcp.query_code", lambda code, query: {})
    (tmp_path / "built.py").write_text("result = Box(1, 1, 1)")
    tools = CadTools(tmp_path)
    for _ in range(20):
        tools.call("inspect_model", {"query": {"kind": "summary"}})
    with pytest.raises(ValueError, match="budget"):
        tools.call("inspect_model", {"query": {"kind": "summary"}})


def test_starting_design_can_be_inspected_before_a_build(tmp_path):
    from agent.local import prepare_input
    from agent.models import CadRunRequest

    request = CadRunRequest(modelId="local/codex", code="result = Box(1, 1, 1)",
                            messages=[{"role": "user", "content": "Add a hole here"}])
    prepare_input(request, tmp_path)

    assert (tmp_path / "built.py").read_text() == "result = Box(1, 1, 1)"
    assert (tmp_path / "request.txt").read_text() == "Add a hole here"


def test_view_model_draws_the_current_part_within_its_budget(tmp_path, monkeypatch):
    from execution.runner import RenderedView

    drawn = []
    monkeypatch.setattr("agent.cad_mcp.render_code", lambda code, views: drawn.append(views) or [
        RenderedView("top shaded", png=b"png"), RenderedView("iso shaded", error="ValueError: nope")])
    (tmp_path / "built.py").write_text("result = Box(1, 1, 1)")
    tools = CadTools(tmp_path)

    content = tools.call("view_model", {"views": [{"camera": "top"}, {"focus": "nope"}]})["content"]
    assert [item["type"] for item in content] == ["text", "image", "text"]
    assert "could not be drawn" in content[2]["text"]

    for _ in range(2):
        tools.call("view_model", {"views": [{}] * 4})
    with pytest.raises(ValueError, match="2 more views"):
        tools.call("view_model", {"views": [{}] * 4})


def test_check_printability_uses_the_profile_and_a_budget(tmp_path, monkeypatch):
    checked = []
    monkeypatch.setattr("agent.cad_mcp.printability_code",
                        lambda code, profile: checked.append(profile) or {"findings": []})
    (tmp_path / "built.py").write_text("result = Box(1, 1, 1)")
    (tmp_path / "profile.json").write_text(json.dumps({"min_wall_mm": 2.0}))
    tools = CadTools(tmp_path)

    for _ in range(3):
        tools.call("check_printability", {})
    with pytest.raises(ValueError, match="three times"):
        tools.call("check_printability", {})
    assert checked == [{"min_wall_mm": 2.0}] * 3


def test_print_profile_reaches_the_workspace(tmp_path):
    from agent.local import prepare_input
    from agent.models import CadRunRequest

    request = CadRunRequest(modelId="local/codex", printProfile={"min_wall_mm": 0.8},
                            messages=[{"role": "user", "content": "A bracket"}])
    prepare_input(request, tmp_path)

    assert json.loads((tmp_path / "profile.json").read_text())["min_wall_mm"] == 0.8
