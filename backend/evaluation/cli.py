import argparse
import asyncio
import os
from pathlib import Path

from agent.tracing import flush_tracing

from .config import load_live_config
from .langfuse import publish_live_evaluation
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
    parser.add_argument(
        "--config",
        type=Path,
        help="Live model matrix and LangFuse dataset configuration.",
    )
    parser.add_argument(
        "--publish-langfuse",
        action="store_true",
        help="Publish redacted dataset items and trace scores to LangFuse.",
    )
    parser.add_argument(
        "--dataset-name",
        help="Override the LangFuse dataset name from --config.",
    )
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--category", action="append", dest="categories")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/reports/latest.json"),
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    live_config = load_live_config(args.config) if args.config else None
    dataset_name = args.dataset_name or (
        live_config.langfuse_dataset if live_config else None
    )
    if args.publish_langfuse:
        if args.mode != "live":
            raise ValueError("--publish-langfuse is only available in live mode.")
        if not dataset_name:
            raise ValueError(
                "--dataset-name or a --config with langfuse_dataset is required "
                "when publishing."
            )
        if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv(
            "LANGFUSE_SECRET_KEY"
        ):
            raise ValueError(
                "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required "
                "when publishing."
            )
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
        model_ids = args.models or (
            [model.id for model in live_config.models] if live_config else []
        )
        if not model_ids:
            raise ValueError("At least one --model or --config is required in live mode.")
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required in live mode.")
        structured_output_support = (
            {
                model.id: model.supports_structured_outputs
                for model in live_config.models
            }
            if live_config
            else None
        )
        results = await evaluate_live(
            cases,
            model_ids,
            api_key,
            structured_output_support=structured_output_support,
        )

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

    if args.publish_langfuse:
        assert dataset_name is not None
        published = publish_live_evaluation(cases, report, dataset_name)
        print(
            f"Published {published.dataset_items} dataset item(s), "
            f"{published.traces_scored} trace(s), and "
            f"{published.scores_created} score(s) to LangFuse."
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
    finally:
        flush_tracing()


if __name__ == "__main__":
    raise SystemExit(main())
