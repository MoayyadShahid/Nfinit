from pathlib import Path

from agent.models import ModelInspection, ModelUsage
from evaluation.gate import (
    RegressionPolicy,
    check_regressions,
    load_policy,
    markdown_summary,
)
from evaluation.models import EvaluationCase
from evaluation.reporting import build_report
from evaluation.runner import load_cases
from evaluation.scoring import score_evaluation


def case_fixture() -> EvaluationCase:
    return EvaluationCase.model_validate(
        {
            "id": "gate_box",
            "category": "primitive",
            "description": "Gate fixture",
            "messages": [{"role": "user", "content": "Make a box"}],
            "expected": {
                "solid_count": 1,
                "bounding_box_mm": {"x": 10, "y": 20, "z": 30},
            },
        }
    )


def policy_fixture() -> RegressionPolicy:
    return RegressionPolicy(
        suite="test",
        required_case_count=1,
        minimum_pass_rate=1,
        maximum_failed_cases=0,
        required_categories={"primitive": 1},
        required_metrics=[
            "policy",
            "execution",
            "solid_count",
            "repair_attempts",
        ],
    )


def passing_report():
    case = case_fixture()
    result = score_evaluation(
        case,
        "recorded/reference",
        "result = Box(10, 20, 30)",
        ModelInspection(
            valid=True,
            solid_count=1,
            volume_mm3=6000,
            bounding_box_mm={"x": 10, "y": 20, "z": 30},
        ),
        [],
        ModelUsage(),
    )
    return case, build_report("replay", [result])


def test_regression_gate_accepts_complete_passing_report():
    case, report = passing_report()

    assert check_regressions(report, [case], policy_fixture()) == []
    assert "CAD evaluation gate: PASS" in markdown_summary(
        report, policy_fixture(), []
    )


def test_regression_gate_rejects_failures_and_missing_metrics():
    case, report = passing_report()
    result = report.results[0]
    result.passed = False
    del result.scores["policy"]
    report.summary["recorded/reference"].passed = 0
    report.summary["recorded/reference"].pass_rate = 0

    issues = check_regressions(report, [case], policy_fixture())

    assert any("pass rate" in issue for issue in issues)
    assert any("failed cases" in issue for issue in issues)
    assert any("missing metrics: policy" in issue for issue in issues)
    assert "CAD evaluation gate: FAIL" in markdown_summary(
        report, policy_fixture(), issues
    )


def test_regression_gate_rejects_case_and_category_drift():
    case, report = passing_report()
    changed_case = case.model_copy(
        update={"id": "renamed_case", "category": "subtractive"}
    )

    issues = check_regressions(report, [changed_case], policy_fixture())

    assert any("category distribution changed" in issue for issue in issues)
    assert any("missing cases: renamed_case" in issue for issue in issues)
    assert any("unknown cases: gate_box" in issue for issue in issues)


def test_cad50_policy_matches_committed_corpus():
    evaluation_root = Path(__file__).parents[1] / "evaluation"
    cases = load_cases(evaluation_root / "cases" / "cad50.json")
    policy = load_policy(evaluation_root / "baselines" / "cad50.json")

    assert len(cases) == policy.required_case_count
    assert {case.category for case in cases} == set(policy.required_categories)
