import json
from collections import Counter
from pathlib import Path

import pytest

from agent.models import ModelInspection, ModelUsage, TraceStep
from evaluation.models import EvaluationCase, ReplayRecord
from evaluation.reporting import build_report, write_report
from evaluation.runner import (
    evaluate_live,
    evaluate_replays,
    load_cases,
    load_replays,
)
from evaluation.scoring import score_evaluation


def make_case() -> EvaluationCase:
    return EvaluationCase.model_validate(
        {
            "id": "box_case",
            "category": "primitive",
            "description": "A box",
            "messages": [{"role": "user", "content": "Make a box"}],
            "expected": {
                "solid_count": 1,
                "bounding_box_mm": {"x": 10, "y": 20, "z": 30},
                "volume_mm3": 6000,
                "max_repair_attempts": 1,
                "max_latency_ms": 1000,
                "max_total_tokens": 500,
            },
        }
    )


def valid_inspection() -> ModelInspection:
    return ModelInspection(
        valid=True,
        shape_type="Solid",
        solid_count=1,
        volume_mm3=6000,
        bounding_box_mm={"x": 10, "y": 20, "z": 30},
    )


def test_scoring_checks_geometry_policy_repair_latency_and_tokens():
    result = score_evaluation(
        make_case(),
        "test/model",
        "result = Box(10, 20, 30)",
        valid_inspection(),
        [
            TraceStep(
                node="generate",
                status="complete",
                detail="ok",
                duration_ms=400,
            ),
            TraceStep(
                node="inspect",
                status="passed",
                detail="ok",
                duration_ms=100,
            ),
        ],
        ModelUsage(input_tokens=300, output_tokens=100, total_tokens=400),
    )

    assert result.passed
    assert set(result.scores) == {
        "policy",
        "execution",
        "solid_count",
        "bounding_box_x",
        "bounding_box_y",
        "bounding_box_z",
        "volume",
        "repair_attempts",
        "latency",
        "tokens",
    }


def test_scoring_reports_dimension_and_budget_failures():
    inspection = valid_inspection()
    inspection.bounding_box_mm["x"] = 12
    result = score_evaluation(
        make_case(),
        "test/model",
        "result = Box(12, 20, 30)",
        inspection,
        [
            TraceStep(
                node="repair",
                status="complete",
                detail="retry",
                duration_ms=1200,
            ),
            TraceStep(
                node="repair",
                status="complete",
                detail="retry",
                duration_ms=1,
            ),
        ],
        ModelUsage(total_tokens=600),
    )

    assert not result.passed
    assert not result.scores["bounding_box_x"].passed
    assert not result.scores["repair_attempts"].passed
    assert not result.scores["latency"].passed
    assert not result.scores["tokens"].passed


def test_replay_runner_reexecutes_code_and_marks_missing_records():
    case = make_case()
    records = [
        ReplayRecord(
            case_id=case.id,
            model_id="model/a",
            code="result = Box(10, 20, 30)",
        )
    ]
    calls = []

    def inspector(code: str):
        calls.append(code)
        return valid_inspection()

    results = evaluate_replays(
        [case],
        records,
        model_ids=["model/a", "model/missing"],
        inspector=inspector,
    )

    assert results[0].passed
    assert not results[1].passed
    assert results[1].error == "Replay record is missing."
    assert calls == ["result = Box(10, 20, 30)"]


@pytest.mark.asyncio
async def test_live_runner_uses_agent_state(monkeypatch):
    async def fake_agent(_request, _api_key, _inspector):
        return {
            "code": "result = Box(10, 20, 30)",
            "inspection": valid_inspection().model_dump(),
            "trace": [],
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            "validation_error": None,
        }

    monkeypatch.setattr("evaluation.runner.run_cad_agent", fake_agent)
    results = await evaluate_live(
        [make_case()],
        ["model/a"],
        "test-key",
        inspector=lambda _code: valid_inspection(),
    )

    assert len(results) == 1
    assert results[0].passed
    assert results[0].usage.total_tokens == 15


def test_report_compares_models_and_writes_json(tmp_path: Path):
    case = make_case()
    passing = score_evaluation(
        case,
        "model/a",
        "result = Box(10, 20, 30)",
        valid_inspection(),
        [],
        ModelUsage(total_tokens=100),
    )
    failing = score_evaluation(
        case,
        "model/b",
        "",
        ModelInspection(valid=False, error="failed"),
        [],
        ModelUsage(),
        error="failed",
    )

    report = build_report("replay", [passing, failing])
    output = tmp_path / "nested" / "report.json"
    write_report(report, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert report.summary["model/a"].pass_rate == 1
    assert report.summary["model/b"].pass_rate == 0
    assert payload["schema_version"] == "1.0"
    assert len(payload["results"]) == 2


def test_sample_case_and_replay_files_load():
    root = Path(__file__).parents[1] / "evaluation"
    cases = load_cases(root / "cases" / "smoke.json")
    replays = load_replays(root / "replays" / "smoke.json")

    assert len(cases) == 3
    assert len(replays) == 3


def test_cad50_benchmark_has_balanced_complete_coverage():
    root = Path(__file__).parents[1] / "evaluation"
    cases = load_cases(root / "cases" / "cad50.json")
    replays = load_replays(root / "replays" / "cad50.json")

    expected_categories = {
        "primitive",
        "subtractive",
        "pattern",
        "sketch_profile",
        "edge_finish",
        "mechanical_part",
        "iterative_edit",
        "selection_edit",
        "failure_recovery",
        "manufacturing",
    }
    category_counts = Counter(case.category for case in cases)
    case_ids = {case.id for case in cases}
    replay_ids = {replay.case_id for replay in replays}

    assert len(cases) == 50
    assert len(replays) == 50
    assert set(category_counts) == expected_categories
    assert set(category_counts.values()) == {5}
    assert replay_ids == case_ids
    assert len({case.messages[-1].content for case in cases}) == 50
    assert all(case.expected.solid_count is not None for case in cases)
    assert all(case.expected.bounding_box_mm for case in cases)
    assert all(case.tags for case in cases)
    assert all(replay.model_id == "recorded/reference" for replay in replays)
