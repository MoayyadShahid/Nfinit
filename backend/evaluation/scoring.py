from typing import Any

from agent.models import ModelInspection, ModelUsage, TraceStep
from agent.validation import validate_code

from .models import EvaluationCase, EvaluationResult, FeatureExpectation, MetricScore


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


CENSUS_LISTS = {"hole": "holes", "boss": "bosses", "rounded_edge": "rounded_edges"}


def _score_feature(
    feature: FeatureExpectation, census: dict[str, Any] | None
) -> MetricScore:
    rounded = feature.kind == "rounded_edge"
    size_key = "radius_mm" if rounded else "diameter_mm"
    target = feature.radius_mm if rounded else feature.diameter_mm
    label = f"{feature.kind.replace('_', ' ')} of {size_key[:-3]} {target:g} mm"
    expected = {
        size_key: target,
        "count": feature.count,
        "min_count": feature.min_count,
        "center_span_mm": feature.center_span_mm,
    }
    if not census or "error" in census:
        reason = (census or {}).get("error", "the inspection has no census")
        return MetricScore(
            passed=False,
            value=None,
            expected=expected,
            message=f"Feature census is not available: {reason}.",
        )

    matches = [
        entry
        for entry in census.get(CENSUS_LISTS[feature.kind], [])
        if abs(entry[size_key] - target) <= feature.tolerance_mm
    ]
    count = sum(entry["count"] for entry in matches)
    if feature.count is not None:
        passed = count == feature.count
    elif feature.min_count is not None:
        passed = count >= feature.min_count
    else:
        passed = count >= 1

    span = None
    if feature.center_span_mm and passed:
        centers = [center for entry in matches for center in entry.get("centers_mm", [])]
        span = {
            axis: round(
                max(center[index] for center in centers)
                - min(center[index] for center in centers),
                3,
            )
            for index, axis in enumerate("xyz")
        } if centers else {}
        passed = all(
            axis in span and abs(span[axis] - value) <= feature.tolerance_mm
            for axis, value in feature.center_span_mm.items()
        )

    value = {"count": count, **({"center_span_mm": span} if span is not None else {})}
    return MetricScore(
        passed=passed,
        value=value,
        expected=expected,
        message=f"Found {count} {label}." if passed else f"Expected {label}; found {count}"
        + (f" with centres spanning {span}." if span else "."),
    )


def score_evaluation(
    case: EvaluationCase,
    model_id: str,
    code: str,
    inspection: ModelInspection,
    trace: list[TraceStep],
    usage: ModelUsage,
    error: str | None = None,
    run_id: str | None = None,
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

    for index, feature in enumerate(expected.features):
        scores[f"feature_{index}_{feature.kind}"] = _score_feature(
            feature, inspection.census
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
        run_id=run_id,
        passed=all(score.passed for score in scores.values()),
        scores=scores,
        inspection=inspection,
        repair_attempts=repair_attempts,
        latency_ms=latency_ms,
        usage=usage,
        error=error,
    )
