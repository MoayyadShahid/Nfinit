"""The loop20 benchmark must see the failures it was written for.

Each wrong solution below builds without an error. Scoring must still fail it,
for the reason its category names.
"""
from collections import Counter
from pathlib import Path

import pytest

from agent.models import ModelInspection, ModelUsage
from evaluation.models import EvaluationCase
from evaluation.runner import load_cases, load_replays
from evaluation.scoring import score_evaluation
from execution import inspect_code

ROOT = Path(__file__).parents[1] / "evaluation"
CASES = {case.id: case for case in load_cases(ROOT / "cases" / "loop20.json")}


def score(case_id: str, code: str):
    inspection = inspect_code(code)
    assert inspection.valid, inspection.error
    return score_evaluation(
        CASES[case_id], "test/wrong", code, inspection, [], ModelUsage()
    )


def failed_metrics(result) -> set[str]:
    return {name for name, metric in result.scores.items() if not metric.passed}


def test_loop20_has_four_cases_per_category_and_a_replay_for_each():
    replays = load_replays(ROOT / "replays" / "loop20.json")

    assert Counter(case.category for case in CASES.values()) == {
        "silent_finish": 4,
        "detached": 4,
        "stacked_reading": 4,
        "hole_pattern": 4,
        "edit_regression": 4,
    }
    assert {replay.case_id for replay in replays} == set(CASES)
    assert all(case.expected.bounding_box_mm for case in CASES.values())


@pytest.mark.parametrize(
    ("case_id", "code", "metric"),
    [
        (
            # The fillets were left out.
            "finish_vertical_fillets",
            "result = Box(40, 30, 12)",
            "feature_0_rounded_edge",
        ),
        (
            # The boss floats 1 mm above the plate.
            "detached_boss_on_plate",
            "with BuildPart() as part:\n"
            "    Box(60, 40, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
            "    with Locations((0, 0, 6)):\n"
            "        Cylinder(5, 7, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
            "result = part.part",
            "solid_count",
        ),
        (
            # The walls were read as the overall height.
            "stacked_tray",
            "with BuildPart() as part:\n"
            "    Box(80, 50, 12, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
            "    with Locations((0, 0, 3)):\n"
            "        Box(76, 46, 9, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)\n"
            "result = part.part",
            "bounding_box_z",
        ),
        (
            # One corner hole is missing.
            "holes_corner_four",
            "with BuildPart() as part:\n"
            "    Box(80, 50, 6)\n"
            "    with Locations((-34, -19), (34, -19), (-34, 19)):\n"
            "        Hole(radius=2)\n"
            "result = part.part",
            "feature_0_hole",
        ),
        (
            # The holes are 5 mm from the edges, not 6.
            "holes_corner_four",
            "with BuildPart() as part:\n"
            "    Box(80, 50, 6)\n"
            "    with GridLocations(70, 40, 2, 2):\n"
            "        Hole(radius=2)\n"
            "result = part.part",
            "feature_0_hole",
        ),
        (
            # The thickness edit rebuilt the plate and lost the rounded corners.
            "edit_thickness_keeps_features",
            "with BuildPart() as part:\n"
            "    Box(70, 40, 8)\n"
            "    with Locations((-20, 0), (20, 0)):\n"
            "        Hole(radius=3)\n"
            "result = part.part",
            "feature_1_rounded_edge",
        ),
    ],
)
def test_loop20_fails_parts_that_build_but_are_wrong(case_id, code, metric):
    result = score(case_id, code)

    assert not result.passed
    assert metric in failed_metrics(result)


def make_feature_case(feature: dict) -> EvaluationCase:
    return EvaluationCase.model_validate(
        {
            "id": "feature_case",
            "category": "test",
            "description": "A feature check",
            "messages": [{"role": "user", "content": "Make it"}],
            "expected": {"features": [feature]},
        }
    )


def inspection_with(census) -> ModelInspection:
    return ModelInspection(valid=True, solid_count=1, census=census)


HOLES = {
    "holes": [
        {"diameter_mm": 4.0, "count": 2, "axis": [0, 0, 1], "length_mm": 6,
         "centers_mm": [[-10, 0, 0], [10, 0, 0]]},
        {"diameter_mm": 4.0, "count": 1, "axis": [1, 0, 0], "length_mm": 6,
         "centers_mm": [[0, 5, 0]]},
    ],
    "bosses": [],
    "rounded_edges": [{"radius_mm": 2.0, "count": 4, "surface": "cylinder"}],
}


@pytest.mark.parametrize(
    ("feature", "passed"),
    [
        ({"kind": "hole", "diameter_mm": 4, "count": 3}, True),
        ({"kind": "hole", "diameter_mm": 4, "count": 2}, False),
        ({"kind": "hole", "diameter_mm": 4.04, "min_count": 3}, True),
        ({"kind": "hole", "diameter_mm": 4.2}, False),
        ({"kind": "hole", "diameter_mm": 5, "count": 0}, True),
        ({"kind": "hole", "diameter_mm": 4, "center_span_mm": {"x": 20, "y": 5}}, True),
        ({"kind": "hole", "diameter_mm": 4, "center_span_mm": {"x": 18}}, False),
        ({"kind": "rounded_edge", "radius_mm": 2, "count": 4}, True),
        ({"kind": "boss", "diameter_mm": 4}, False),
    ],
)
def test_feature_scoring_counts_matching_census_entries(feature, passed):
    result = score_evaluation(
        make_feature_case(feature), "test", "", inspection_with(HOLES), [], ModelUsage()
    )

    assert result.scores["feature_0_" + feature["kind"]].passed is passed


def test_feature_scoring_fails_without_a_census():
    case = make_feature_case({"kind": "hole", "diameter_mm": 4})
    for census in (None, {"error": "TypeError: broken"}):
        result = score_evaluation(case, "test", "", inspection_with(census), [], ModelUsage())
        metric = result.scores["feature_0_hole"]
        assert not metric.passed
        assert "census is not available" in metric.message


def test_feature_expectation_needs_its_size():
    with pytest.raises(ValueError, match="radius_mm"):
        make_feature_case({"kind": "rounded_edge", "diameter_mm": 4})


def test_inverted_solids_are_scored_when_solids_are_reported():
    case = make_feature_case({"kind": "hole", "diameter_mm": 4})
    inverted = ModelInspection(valid=False, solids=[{"inverted": True}], census=HOLES)
    older = ModelInspection(valid=True, census=HOLES)

    assert not score_evaluation(case, "t", "", inverted, [], ModelUsage()).scores["inverted_solids"].passed
    assert "inverted_solids" not in score_evaluation(case, "t", "", older, [], ModelUsage()).scores
