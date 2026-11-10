import argparse
import asyncio
from collections import Counter
import os
from pathlib import Path
import secrets


from .config import load_live_config
from .reporting import build_report, write_report
from .runner import (
    evaluate_live,
    evaluate_local,
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
        "--agent",
        action="append",
        dest="agents",
        choices=("local/claude", "local/codex"),
        help="Run live cases through your installed Claude Code or Codex CLI.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Live model matrix configuration.",
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
    cases = filter_cases(
        load_cases(args.cases),
        set(args.case_ids or []),
        set(args.categories or []),
    )
    if not cases:
        raise ValueError("No evaluation cases matched the supplied filters.")

    if args.agents and args.mode != "live":
        raise ValueError("--agent requires --mode live.")

    if args.mode == "replay":
        if not args.replays:
            raise ValueError("--replays is required in replay mode.")
        results = evaluate_replays(
            cases,
            load_replays(args.replays),
            model_ids=args.models,
        )
    elif args.agents and not args.models and not live_config:
        enable_local_agents()
        results = await evaluate_local(cases, args.agents)
    else:
        model_ids = args.models or (
            [model.setup_id for model in live_config.models] if live_config else []
        )
        if not model_ids:
            raise ValueError(
                "At least one --model, --agent or --config is required in live mode."
            )
        if args.agents:
            raise ValueError("Run --agent separately from --model and --config.")
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required in live mode.")
        structured_output_support = (
            {
                model.setup_id: model.supports_structured_outputs
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
            f"{summary.mean_total_tokens:.0f} mean tokens, "
            f"${summary.total_cost_usd:.2f} total"
        )
    print_run_errors(results)

    return 0 if all(result.passed for result in results) else 1


def enable_local_agents() -> None:
    """Turn on local agents for this process, as the local launcher does."""
    os.environ["NFNIT_LOCAL_AGENTS"] = "true"
    os.environ["NFNIT_ALLOW_LOCAL_AUTH_BYPASS"] = "true"
    os.environ.setdefault("NFNIT_LOCAL_TOKEN", secrets.token_urlsafe(32))


def print_run_errors(results, limit: int = 5) -> None:
    """Print the most common agent errors, so a failed CI run shows why."""
    errors = Counter(
        (result.model_id, str(result.scores["agent_run"].value)[:300])
        for result in results
        if "agent_run" in result.scores
    )
    for (model_id, error), count in errors.most_common(limit):
        print(f"{model_id}: {count} run(s) raised {error}")


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
