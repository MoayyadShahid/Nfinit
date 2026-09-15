import argparse
import asyncio
import os
from pathlib import Path

from .reporting import build_report, write_report
from .runner import (
    evaluate_live,
    evaluate_replays,
    filter_cases,
    load_cases,
    load_replays,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nfinit-eval",
        description="Run Nfinit CAD evaluations in replay or live mode.",
    )
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--mode", choices=("replay", "live"), default="replay")
    parser.add_argument("--replays", type=Path)
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--category", action="append", dest="categories")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/reports/latest.json"),
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    cases = filter_cases(
        load_cases(args.cases),
        set(args.case_ids or []),
        set(args.categories or []),
    )
    if not cases:
        raise ValueError("No evaluation cases matched the supplied filters.")

    if args.mode == "replay":
        if not args.replays:
            raise ValueError("--replays is required in replay mode.")
        results = evaluate_replays(
            cases,
            load_replays(args.replays),
            model_ids=args.models,
        )
    else:
        if not args.models:
            raise ValueError("At least one --model is required in live mode.")
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required in live mode.")
        results = await evaluate_live(cases, args.models, api_key)

    report = build_report(args.mode, results)
    write_report(report, args.output)

    print(f"Wrote {len(results)} result(s) to {args.output}")
    for model_id, summary in report.summary.items():
        print(
            f"{model_id}: {summary.passed}/{summary.cases} passed "
            f"({summary.pass_rate:.1%}), "
            f"{summary.mean_latency_ms:.0f} ms mean, "
            f"{summary.mean_total_tokens:.0f} mean tokens"
        )
    return 0 if all(result.passed for result in results) else 1


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except ValueError as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
