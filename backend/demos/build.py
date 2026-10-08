"""Build the studio's demo parts by running the real agent, step by step.

Each demo is a short chat: every step is one prompt, run through the
production agent with the previous step's code, exactly as in the studio.
For each step this writes the recorded progress events, the plan, the code,
the finished GLB and the build previews into frontend/public/demos/<slug>/,
so the studio can replay the demo without the backend.

Usage, from backend/ (costs a few cents per step; see docs/BILLING_AND_DEMOS.md):

    CAD_SANDBOX_MODE=fork poetry run python -m demos.build [--only drone-frame]
"""

import argparse
import asyncio
import json
import os
import shutil
import time
from pathlib import Path

from agent import CadRunRequest, run_cad_agent
from agent.graph import plan_summary
from execution import build_mesh, inspect_with_snapshots

SPECS = Path(__file__).with_name("specs.json")


class DemoFailed(RuntimeError):
    """A step did not build; its demo is left out instead of half-written."""
OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demos"


async def build_demo(spec: dict, model_id: str, api_key: str, output: Path) -> dict:
    folder = output / spec["slug"]
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    messages: list[dict] = []
    code = ""
    steps = []
    cost = 0.0
    seen_features: set[str] = set()
    for index, prompt in enumerate(spec["steps"], start=1):
        events: list[dict] = []
        started = time.monotonic()

        async def record(event: dict) -> None:
            events.append({**event, "at_ms": round((time.monotonic() - started) * 1000)})

        snapshots: list = []

        def inspect(candidate: str):
            inspection, previews = inspect_with_snapshots(candidate)
            snapshots[:] = previews  # keep the previews of the latest attempt
            return inspection

        messages.append({"role": "user", "content": prompt})
        try:
            state = await run_cad_agent(
                CadRunRequest(
                    messages=messages,
                    code=code,
                    modelId=model_id,
                    supportsStructuredOutputs=True,
                ),
                api_key,
                inspect,
                on_event=record,
            )
        except TimeoutError as error:  # CadRunTimeoutError is a TimeoutError
            shutil.rmtree(folder, ignore_errors=True)
            raise DemoFailed(f"{spec['slug']} step {index} timed out: {error}") from error
        cost += state["usage"].get("cost_usd", 0)
        if state["validation_error"]:
            shutil.rmtree(folder, ignore_errors=True)
            raise DemoFailed(
                f"{spec['slug']} step {index} did not build: {state['validation_error']}"
            )
        code = state["code"]
        built = build_mesh(code)
        (folder / f"step-{index}.glb").write_bytes(built.glb)
        # Each step rebuilds the whole part; keep only what this step adds.
        added = [preview for preview in snapshots if preview.feature_id not in seen_features]
        seen_features.update(preview.feature_id for preview in snapshots)
        preview_files = []
        for number, preview in enumerate(added or snapshots[-1:], start=1):
            name = f"step-{index}-preview-{number}.glb"
            (folder / name).write_bytes(preview.glb)
            preview_files.append({"file": name, "name": preview.name})

        agent = {
            "plan": state["plan"],
            "trace": state["trace"],
            "inspection": built.inspection.model_dump(),
        }
        messages.append({"role": "assistant", "content": code, "agent": agent})
        steps.append(
            {
                "prompt": prompt,
                "summary": plan_summary(state["plan"]),
                "code": code,
                "glb": f"step-{index}.glb",
                "previews": preview_files,
                "events": events,
                "agent": agent,
            }
        )
        print(f"  {spec['slug']} step {index}: ok, {len(preview_files)} previews")

    demo = {key: spec[key] for key in ("slug", "title", "summary")}
    demo.update({"model_id": model_id, "steps": steps})
    (folder / "demo.json").write_text(json.dumps(demo, indent=1) + "\n", encoding="utf-8")
    return {**{key: spec[key] for key in ("slug", "title", "summary")},
            "steps": len(steps), "cost_usd": round(cost, 4)}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", action="append", help="Build only this demo slug.")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is required.")

    config = json.loads(SPECS.read_text(encoding="utf-8"))
    chosen = [spec for spec in config["demos"] if not args.only or spec["slug"] in args.only]
    args.output.mkdir(parents=True, exist_ok=True)
    costs, failures = {}, []
    for spec in chosen:
        print(f"Building {spec['slug']}…")
        try:
            built = await build_demo(spec, config["model_id"], api_key, args.output)
            costs[spec["slug"]] = built["cost_usd"]
        except (DemoFailed, TimeoutError) as error:
            failures.append(str(error))
            print(f"  skipped: {error}")

    # The index lists every demo on disk, in the order of specs.json.
    index = []
    for spec in config["demos"]:
        demo_path = args.output / spec["slug"] / "demo.json"
        if demo_path.is_file():
            demo = json.loads(demo_path.read_text(encoding="utf-8"))
            index.append(
                {key: demo[key] for key in ("slug", "title", "summary")}
                | {"steps": len(demo["steps"])}
            )
    (args.output / "index.json").write_text(
        json.dumps({"demos": index}, indent=1) + "\n", encoding="utf-8"
    )
    print("Cost:", costs, "| total $%.2f" % sum(costs.values()))
    if failures:
        raise SystemExit("Some demos did not build:\n" + "\n".join(failures))


if __name__ == "__main__":
    asyncio.run(main())
