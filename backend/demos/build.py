"""Build the studio's demo parts from the design files in demos/designs/.

Each design is a short build story written as build123d code (see
demos/authored.py). For every step this runs the complete script of that
version in the CAD sandbox and writes into frontend/public/demos/<slug>/:
the finished GLB, the previews of the features the step adds, and a
demo.json entry with the prompt, the reply, the code and the geometry facts.
The studio replays the demos from these static files, without the backend.

Usage, from backend/ (no model calls, so no API key and no cost):

    poetry run python -m demos.build [--only fpv-drone]
"""

import argparse
import json
import shutil
from pathlib import Path

from agent.graph import plan_summary
from execution import build_mesh, inspect_with_snapshots

from .authored import Design, load_designs

# The order of the demo cards; the first is where a free user lands.
ORDER = [
    "fpv-drone",
    "robot-gripper",
    "mini-glider",
    "model-rocket",
    "catapult",
    "electronics-enclosure",
]
OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "public" / "demos"
SOURCE = "example"


class DemoFailed(RuntimeError):
    """A step did not build; its demo is left out instead of half-written."""


def _bounds(inspection) -> str:
    box = inspection.bounding_box_mm or {}
    size = " × ".join(f"{box.get(axis, 0):g}" for axis in ("x", "y", "z"))
    count = inspection.solid_count or 0
    return f"Built {count} solid{'s' if count != 1 else ''}; bounds {size} mm."


def build_demo(design: Design, output: Path) -> dict:
    folder = output / design.slug
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    steps = []
    seen: set[str] = set()
    for number in range(1, len(design.steps) + 1):
        code = design.code(number)
        inspection, previews = inspect_with_snapshots(code)
        if not inspection.valid:
            shutil.rmtree(folder, ignore_errors=True)
            raise DemoFailed(f"{design.slug} step {number} did not build: {inspection.error}")
        built = build_mesh(code)
        (folder / f"step-{number}.glb").write_bytes(built.glb)

        # Each step rebuilds the whole part; keep only what this step adds.
        added = [preview for preview in previews if preview.name not in seen]
        seen.update(preview.name for preview in previews)
        preview_files = []
        for index, preview in enumerate(added or previews[-1:], start=1):
            name = f"step-{number}-preview-{index}.glb"
            (folder / name).write_bytes(preview.glb)
            preview_files.append({"file": name, "name": preview.name})

        plan = design.plan(number)
        summary = plan_summary(plan)
        detail = _bounds(built.inspection)
        # No timings: these builds are examples, not recorded agent runs.
        events = [
            {"stage": "plan", "status": "complete", "message": summary, "at_ms": 0},
            {
                "stage": "inspect",
                "status": "started",
                "message": "Building the part and checking its geometry.",
                "at_ms": 900,
            },
            {"stage": "inspect", "status": "passed", "message": detail, "at_ms": 1500},
        ]
        trace = [
            {"node": "plan", "status": "complete", "detail": summary},
            {"node": "inspect", "status": "passed", "detail": detail},
        ]
        steps.append(
            {
                "prompt": design.steps[number - 1].prompt,
                "summary": summary,
                "code": code,
                "glb": f"step-{number}.glb",
                "previews": preview_files,
                "events": events,
                "agent": {
                    "plan": plan,
                    "trace": trace,
                    "inspection": built.inspection.model_dump(),
                },
            }
        )
        print(f"  {design.slug} step {number}: ok, {len(preview_files)} previews")

    demo = {
        "slug": design.slug,
        "title": design.title,
        "summary": design.summary,
        "source": SOURCE,
        "steps": steps,
    }
    (folder / "demo.json").write_text(json.dumps(demo, indent=1) + "\n", encoding="utf-8")
    return demo


def write_index(output: Path) -> None:
    """List every demo on disk, in ORDER, and remove folders not in it."""
    for folder in output.iterdir():
        if folder.is_dir() and folder.name not in ORDER:
            shutil.rmtree(folder)
    index = []
    for slug in ORDER:
        path = output / slug / "demo.json"
        if path.is_file():
            demo = json.loads(path.read_text(encoding="utf-8"))
            index.append(
                {key: demo[key] for key in ("slug", "title", "summary")}
                | {"steps": len(demo["steps"])}
            )
    (output / "index.json").write_text(
        json.dumps({"demos": index}, indent=1) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", action="append", help="Build only this demo slug.")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    chosen = [slug for slug in ORDER if not args.only or slug in args.only]
    args.output.mkdir(parents=True, exist_ok=True)
    failures = []
    for design in load_designs(chosen):
        print(f"Building {design.slug}…")
        try:
            build_demo(design, args.output)
        except DemoFailed as error:
            failures.append(str(error))
            print(f"  skipped: {error}")
    write_index(args.output)
    if failures:
        raise SystemExit("Some demos did not build:\n" + "\n".join(failures))


if __name__ == "__main__":
    main()
