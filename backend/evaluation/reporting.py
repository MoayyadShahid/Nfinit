import json
from collections import defaultdict
from pathlib import Path
from typing import Literal

from .models import EvaluationReport, EvaluationResult, ModelSummary


def build_report(
    mode: Literal["replay", "live"], results: list[EvaluationResult]
) -> EvaluationReport:
    grouped: dict[str, list[EvaluationResult]] = defaultdict(list)
    for result in results:
        grouped[result.model_id].append(result)

    summary = {}
    for model_id, model_results in sorted(grouped.items()):
        count = len(model_results)
        repaired = sum(result.repair_attempts > 0 for result in model_results)
        summary[model_id] = ModelSummary(
            cases=count,
            passed=sum(result.passed for result in model_results),
            pass_rate=round(
                sum(result.passed for result in model_results) / count, 4
            ),
            mean_latency_ms=round(
                sum(result.latency_ms for result in model_results) / count, 2
            ),
            mean_total_tokens=round(
                sum(result.usage.total_tokens for result in model_results) / count,
                2,
            ),
            repair_rate=round(repaired / count, 4),
            mean_cost_usd=round(
                sum(result.usage.cost_usd for result in model_results) / count, 6
            ),
            total_cost_usd=round(
                sum(result.usage.cost_usd for result in model_results), 4
            ),
            p95_latency_ms=_percentile(
                [result.latency_ms for result in model_results], 0.95
            ),
        )

    return EvaluationReport(
        mode=mode,
        models=sorted(grouped),
        summary=summary,
        results=results,
    )


def write_report(report: EvaluationReport, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(float(ordered[index]), 2)
