import argparse
import json
import os
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field

from .models import EvaluationCase, EvaluationReport
from .runner import load_cases


class RegressionPolicy(BaseModel):
    schema_version: str = "1.0"
    suite: str
    required_case_count: int = Field(gt=0)
    minimum_pass_rate: float = Field(ge=0, le=1)
    maximum_failed_cases: int = Field(ge=0)
    required_categories: dict[str, int]
    required_metrics: list[str]
    require_bounding_box_metric: bool = True


def load_report(path: Path) -> EvaluationReport:
    return EvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))


def load_policy(path: Path) -> RegressionPolicy:
    return RegressionPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def check_regressions(
    report: EvaluationReport,
    cases: list[EvaluationCase],
    policy: RegressionPolicy,
) -> list[str]:
    issues: list[str] = []
    case_map = {case.id: case for case in cases}
    expected_ids = set(case_map)

    if len(cases) != policy.required_case_count:
        issues.append(
            f"Case corpus has {len(cases)} cases; "
            f"policy requires {policy.required_case_count}."
        )

    corpus_categories = Counter(case.category for case in cases)
    if dict(sorted(corpus_categories.items())) != dict(
        sorted(policy.required_categories.items())
    ):
        issues.append(
            "Case category distribution changed: "
            f"{dict(sorted(corpus_categories.items()))}."
        )

    if not report.models:
        issues.append("Report contains no models.")
    result_models = {result.model_id for result in report.results}
    if result_models != set(report.models):
        issues.append(
            "Report model list does not match result models: "
            f"{sorted(result_models)}."
        )

    for model_id in report.models:
        results = [
            result for result in report.results if result.model_id == model_id
        ]
        result_ids = [result.case_id for result in results]
        actual_ids = set(result_ids)
        missing = sorted(expected_ids - actual_ids)
        unexpected = sorted(actual_ids - expected_ids)
        if missing:
            issues.append(f"{model_id} is missing cases: {', '.join(missing)}.")
        if unexpected:
            issues.append(
                f"{model_id} contains unknown cases: {', '.join(unexpected)}."
            )
        if len(result_ids) != len(actual_ids):
            issues.append(f"{model_id} contains duplicate case results.")

        failures = [result.case_id for result in results if not result.passed]
        summary = report.summary.get(model_id)
        if summary is None:
            issues.append(f"{model_id} has no summary.")
        else:
            calculated_passed = sum(result.passed for result in results)
            calculated_rate = calculated_passed / len(results) if results else 0
            if summary.cases != len(results) or summary.passed != calculated_passed:
                issues.append(f"{model_id} summary counts do not match its results.")
            if abs(summary.pass_rate - calculated_rate) > 0.0001:
                issues.append(f"{model_id} summary pass rate does not match its results.")
            if summary.pass_rate < policy.minimum_pass_rate:
                issues.append(
                    f"{model_id} pass rate {summary.pass_rate:.1%} is below "
                    f"{policy.minimum_pass_rate:.1%}."
                )
            if len(failures) > policy.maximum_failed_cases:
                issues.append(
                    f"{model_id} has {len(failures)} failed cases "
                    f"(maximum {policy.maximum_failed_cases}): "
                    f"{', '.join(failures)}."
                )

        for result in results:
            expected_case = case_map.get(result.case_id)
            if expected_case and result.category != expected_case.category:
                issues.append(
                    f"{model_id}/{result.case_id} reports category "
                    f"'{result.category}', expected '{expected_case.category}'."
                )
            failed_metrics = [
                name for name, score in result.scores.items() if not score.passed
            ]
            if result.passed == bool(failed_metrics):
                issues.append(
                    f"{model_id}/{result.case_id} pass status disagrees with "
                    "its metric scores."
                )
            missing_metrics = sorted(
                set(policy.required_metrics) - set(result.scores)
            )
            if missing_metrics:
                issues.append(
                    f"{model_id}/{result.case_id} is missing metrics: "
                    f"{', '.join(missing_metrics)}."
                )
            if policy.require_bounding_box_metric and not any(
                name.startswith("bounding_box_") for name in result.scores
            ):
                issues.append(
                    f"{model_id}/{result.case_id} has no bounding-box metric."
                )

    return issues


def markdown_summary(
    report: EvaluationReport,
    policy: RegressionPolicy,
    issues: list[str],
) -> str:
    lines = [
        f"## CAD evaluation gate: {'PASS' if not issues else 'FAIL'}",
        "",
        f"Suite: `{policy.suite}`",
        "",
        "| Model | Passed | Cases | Pass rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for model_id in report.models:
        summary = report.summary.get(model_id)
        if summary:
            lines.append(
                f"| `{model_id}` | {summary.passed} | {summary.cases} | "
                f"{summary.pass_rate:.1%} |"
            )
    if issues:
        lines.extend(["", "### Regressions", ""])
        lines.extend(f"- {issue}" for issue in issues)
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nfinit-eval-gate",
        description="Check a CAD evaluation report against a regression policy.",
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = load_report(args.report)
    cases = load_cases(args.cases)
    policy = load_policy(args.policy)
    issues = check_regressions(report, cases, policy)
    summary = markdown_summary(report, policy, issues)
    print(summary, end="")

    summary_path = args.summary or (
        Path(os.environ["GITHUB_STEP_SUMMARY"])
        if os.getenv("GITHUB_STEP_SUMMARY")
        else None
    )
    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(summary, encoding="utf-8")

    if issues:
        print(json.dumps({"regressions": issues}, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
