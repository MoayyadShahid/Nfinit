from agent.models import ModelInspection, ModelUsage, TraceStep
from agent.validation import validate_code

from .models import EvaluationCase, EvaluationResult, MetricScore


def _score(
    passed: bool,
    value,
    expected,
    success_message: str,
    failure_message: str,
) -> MetricScore:
    return MetricScore(
        passed=passed,
        value=value,
        expected=expected,
        message=success_message if passed else failure_message,
    )


def score_evaluation(
    case: EvaluationCase,
    model_id: str,
    code: str,
    inspection: ModelInspection,
    trace: list[TraceStep],
    usage: ModelUsage,
    error: str | None = None,
) -> EvaluationResult:
    expected = case.expected
    scores: dict[str, MetricScore] = {}

    policy_error = validate_code(code)
    scores["policy"] = _score(
        policy_error is None,
        policy_error or "compliant",
        "compliant",
        "Generated code complies with the CAD policy.",
        f"Generated code violated policy: {policy_error}",
    )

    scores["execution"] = _score(
        inspection.valid == expected.valid,
        inspection.valid,
        expected.valid,
        "Geometry execution matched the expected validity.",
        inspection.error or "Geometry validity did not match the expectation.",
    )

    if expected.solid_count is not None:
        scores["solid_count"] = _score(
            inspection.solid_count == expected.solid_count,
            inspection.solid_count,
            expected.solid_count,
            "Solid count matched.",
            "Solid count did not match.",
        )

    if expected.bounding_box_mm:
        actual_bounds = inspection.bounding_box_mm or {}
        for axis, target in expected.bounding_box_mm.items():
            actual = actual_bounds.get(axis)
            passed = (
                actual is not None
                and abs(actual - target) <= expected.dimension_tolerance_mm
            )
            scores[f"bounding_box_{axis}"] = _score(
                passed,
                actual,
                {
                    "target": target,
                    "tolerance_mm": expected.dimension_tolerance_mm,
                },
                f"{axis.upper()} dimension was within tolerance.",
                f"{axis.upper()} dimension was outside tolerance.",
            )

    if expected.volume_mm3 is not None:
        actual_volume = inspection.volume_mm3
        tolerance = abs(expected.volume_mm3) * (
            expected.volume_tolerance_percent / 100
        )
        passed = (
            actual_volume is not None
            and abs(actual_volume - expected.volume_mm3) <= tolerance
        )
        scores["volume"] = _score(
            passed,
            actual_volume,
            {
                "target": expected.volume_mm3,
                "tolerance_percent": expected.volume_tolerance_percent,
            },
            "Volume was within tolerance.",
            "Volume was outside tolerance.",
        )

    repair_attempts = sum(step.node == "repair" for step in trace)
    if expected.max_repair_attempts is not None:
        scores["repair_attempts"] = _score(
            repair_attempts <= expected.max_repair_attempts,
            repair_attempts,
            {"maximum": expected.max_repair_attempts},
            "Repair attempts stayed within the limit.",
            "Repair attempts exceeded the limit.",
        )

    latency_ms = sum(step.duration_ms for step in trace)
    if expected.max_latency_ms is not None:
        scores["latency"] = _score(
            latency_ms <= expected.max_latency_ms,
            latency_ms,
            {"maximum_ms": expected.max_latency_ms},
            "Latency stayed within the limit.",
            "Latency exceeded the limit.",
        )

    if expected.max_total_tokens is not None:
        scores["tokens"] = _score(
            usage.total_tokens <= expected.max_total_tokens,
            usage.total_tokens,
            {"maximum": expected.max_total_tokens},
            "Token usage stayed within the limit.",
            "Token usage exceeded the limit.",
        )

    if error:
        scores["agent_run"] = MetricScore(
            passed=False,
            value=error,
            expected="success",
            message="The agent run raised an error.",
        )

    return EvaluationResult(
        case_id=case.id,
        category=case.category,
        model_id=model_id,
        passed=all(score.passed for score in scores.values()),
        scores=scores,
        inspection=inspection,
        repair_attempts=repair_attempts,
        latency_ms=latency_ms,
        usage=usage,
        error=error,
    )
