import json
from pathlib import Path

from execution.policy import validate_cad_code

DEMOS = Path(__file__).parents[2] / "frontend" / "public" / "demos"
SPECS = Path(__file__).parents[1] / "demos" / "specs.json"


def test_every_listed_demo_is_complete_and_safe():
    index = json.loads((DEMOS / "index.json").read_text())["demos"]
    specs = {spec["slug"]: spec for spec in json.loads(SPECS.read_text())["demos"]}

    assert index[0]["slug"] == "drone-frame"  # free users land in this one
    for item in index:
        demo = json.loads((DEMOS / item["slug"] / "demo.json").read_text())
        assert len(demo["steps"]) == item["steps"] == len(specs[item["slug"]]["steps"])
        for number, step in enumerate(demo["steps"], start=1):
            assert step["prompt"] == specs[item["slug"]]["steps"][number - 1]
            validate_cad_code(step["code"])
            assert step["agent"]["inspection"]["valid"]
            glb = (DEMOS / item["slug"] / step["glb"]).read_bytes()
            assert glb[:4] == b"glTF"
            assert step["previews"], f"{item['slug']} step {number} adds no feature"
            for preview in step["previews"]:
                assert (DEMOS / item["slug"] / preview["file"]).read_bytes()[:4] == b"glTF"
            assert all(event["at_ms"] >= 0 for event in step["events"])


def test_no_unused_demo_files_ship():
    for folder in (path for path in DEMOS.iterdir() if path.is_dir()):
        demo = json.loads((folder / "demo.json").read_text())
        used = {"demo.json"}
        for step in demo["steps"]:
            used.add(step["glb"])
            used.update(preview["file"] for preview in step["previews"])
        assert {path.name for path in folder.iterdir()} == used
