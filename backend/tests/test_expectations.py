from typing import Any

import pytest

from agent.expectations import check_geometry, describe, split_plan
from agent.graph import create_cad_graph
from agent.models import ModelInspection
from tests.test_graph import FakeClient

TRAY_PLAN = """Overall 80 × 50 × 20 mm open tray.

1. base_plate: 80 × 50 × 2 mm.
2. perimeter_walls: 5 mm thick, 18 mm above the base.

```expectations
{"bounding_box_mm": {"x": 80, "y": 50, "z": 20}, "solid_count": 1,
 "assumptions": ["The walls rise 18 mm above the 2 mm base"]}
```"""


def _built(z: float, solids: int = 1) -> ModelInspection:
    return ModelInspection(
        valid=True,
        shape_type="Solid",
        solid_count=solids,
        volume_mm3=1000,
        bounding_box_mm={"x": 80, "y": 50, "z": z},
    )


def _state(prompt: str = "Create an 80 by 50 mm tray") -> dict[str, Any]:
    return {
        "run_id": "test-run",
        "messages": [{"role": "user", "content": prompt}],
        "current_code": "",
        "model_id": "anthropic/claude-sonnet-5.5",
        "supports_structured_outputs": True,
        "selection": None,
        "patterns": [],
        "plan": "",
        "code": "",
        "inspection": None,
        "validation_error": None,
        "expectations": None,
        "geometry_mismatch": None,
        "last_valid": None,
        "repair_attempts": 0,
        "trace": [],
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


class NoPatterns:
    backend = "none"

    def retrieve(self, query: str, limit: int = 4):
        return []


def test_split_plan_removes_the_block_and_leads_with_the_assumption():
    plan, expectations = split_plan(TRAY_PLAN)

    assert "```" not in plan
    assert plan.startswith("Assumed: The walls rise 18 mm above the 2 mm base.\n\n")
    assert "Overall 80 × 50 × 20 mm open tray." in plan
    assert expectations == {
        "bounding_box_mm": {"x": 80.0, "y": 50.0, "z": 20.0},
        "solid_count": 1,
        "assumptions": ["The walls rise 18 mm above the 2 mm base"],
    }
    assert describe(expectations) == "overall bounds X 80 mm, Y 50 mm, Z 20 mm; 1 solid"


def test_plan_without_a_block_is_unchanged():
    assert split_plan("Make a parameterized 10 mm cube.") == (
        "Make a parameterized 10 mm cube.",
        None,
    )


@pytest.mark.parametrize(
    "block",
    [
        "not json",
        "[1, 2]",
        '{"bounding_box_mm": {"x": "wide", "y": -4, "z": true}, "solid_count": 0}',
    ],
)
def test_invalid_blocks_give_no_expectations(block):
    plan, expectations = split_plan(f"A part.\n\n```expectations\n{block}\n```")

    assert plan == "A part."
    assert expectations is None


def test_null_axes_are_not_checked():
    _, expectations = split_plan(
        '```expectations\n{"bounding_box_mm": {"x": 40, "y": null, "z": null},'
        ' "solid_count": null, "assumptions": []}\n```'
    )

    assert expectations["bounding_box_mm"] == {"x": 40.0}
    assert check_geometry(expectations, {"valid": True, "bounding_box_mm": {"x": 40.05, "y": 7}}) is None


def test_check_names_each_axis_and_the_solid_count_that_differ():
    _, expectations = split_plan(TRAY_PLAN)

    message = check_geometry(expectations, _built(18, solids=2).model_dump())

    assert message is not None
    assert "it has 2 solids, but the plan expects 1" in message
    assert "Z is 18 mm, but the plan expects 20 mm (2 mm too short)" in message
    assert "X is" not in message


def test_check_ignores_failed_builds_and_kernel_rounding():
    _, expectations = split_plan(TRAY_PLAN)

    assert check_geometry(expectations, _built(20.000001).model_dump()) is None
    assert check_geometry(expectations, {"valid": False, "error": "boom"}) is None
    assert check_geometry(None, _built(18).model_dump()) is None


@pytest.mark.asyncio
async def test_graph_repairs_a_part_that_builds_at_the_wrong_size():
    client = FakeClient(
        [
            TRAY_PLAN,
            '{"code":"result = short_tray"}',
            '{"code":"result = tray"}',
        ]
    )
    inspections = iter([_built(18), _built(20)])
    graph = create_cad_graph(
        client, lambda _code: next(inspections), pattern_retriever=NoPatterns()
    )

    result = await graph.ainvoke(_state())

    assert result["validation_error"] is None
    assert result["geometry_mismatch"] is None
    assert result["repair_attempts"] == 1
    assert result["code"] == "result = tray"
    assert result["plan"].startswith("Assumed: The walls rise 18 mm")
    assert [(step["node"], step["status"]) for step in result["trace"]][-3:] == [
        ("inspect", "failed"),
        ("repair", "complete"),
        ("inspect", "passed"),
    ]
    generate, repair = client.chat.completions.requests[1:]
    generate_prompt = generate["messages"][-1]["content"]
    repair_prompt = repair["messages"][-1]["content"]
    assert "```expectations" not in generate_prompt
    assert "checked for: overall bounds X 80 mm, Y 50 mm, Z 20 mm; 1 solid" in generate_prompt
    assert "Z is 18 mm, but the plan expects 20 mm" in repair_prompt


@pytest.mark.asyncio
async def test_a_part_that_never_matches_is_still_returned():
    client = FakeClient(
        [TRAY_PLAN] + ['{"code":"result = short_tray"}'] * 4
    )
    graph = create_cad_graph(
        client, lambda _code: _built(18), pattern_retriever=NoPatterns()
    )

    result = await graph.ainvoke(_state())

    assert result["repair_attempts"] == 3
    assert result["validation_error"] is None
    assert "Z is 18 mm" in result["geometry_mismatch"]
    assert result["code"] == "result = short_tray"


@pytest.mark.asyncio
async def test_a_failed_last_repair_keeps_the_previous_part():
    client = FakeClient(
        [
            TRAY_PLAN,
            '{"code":"result = short_tray"}',
            '{"code":"result = broken_one"}',
            '{"code":"result = broken_two"}',
            '{"code":"result = broken_three"}',
        ]
    )
    inspections = iter(
        [_built(18)]
        + [ModelInspection(valid=False, error="NameError: broken")] * 3
    )
    graph = create_cad_graph(
        client, lambda _code: next(inspections), pattern_retriever=NoPatterns()
    )

    result = await graph.ainvoke(_state())

    assert result["repair_attempts"] == 3
    assert result["validation_error"] is None
    assert result["code"] == "result = short_tray"
    assert result["inspection"]["bounding_box_mm"]["z"] == 18
    assert "Z is 18 mm" in result["geometry_mismatch"]
    assert result["trace"][-1]["detail"].startswith(
        "The last repair did not build, so the previous part was kept."
    )


@pytest.mark.asyncio
async def test_execution_failures_without_a_built_part_still_fail_the_run():
    client = FakeClient(
        [TRAY_PLAN] + ['{"code":"result = broken"}'] * 4
    )
    graph = create_cad_graph(
        client,
        lambda _code: ModelInspection(valid=False, error="NameError: broken"),
        pattern_retriever=NoPatterns(),
    )

    result = await graph.ainvoke(_state())

    assert result["repair_attempts"] == 3
    assert result["validation_error"] == "NameError: broken"
    assert result["geometry_mismatch"] is None
