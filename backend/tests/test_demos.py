import json
from pathlib import Path

import pytest

from demos.authored import parse_design
from demos.build import ORDER
from execution.policy import validate_cad_code

DEMOS = Path(__file__).parents[2] / "frontend" / "public" / "demos"
DESIGNS = Path(__file__).parents[1] / "demos" / "designs"


def test_every_listed_demo_is_complete_and_safe():
    index = json.loads((DEMOS / "index.json").read_text())["demos"]

    assert [item["slug"] for item in index] == ORDER
    assert index[0]["slug"] == "fpv-drone"  # free users land in this one
    for item in index:
        design = parse_design(DESIGNS / f"{item['slug']}.cad")
        demo = json.loads((DEMOS / item["slug"] / "demo.json").read_text())
        assert demo["source"] == "example"
        assert len(demo["steps"]) == item["steps"] == len(design.steps)
        for number, step in enumerate(demo["steps"], start=1):
            assert step["prompt"] == design.steps[number - 1].prompt
            # The shipped code is the design's script for this version.
            assert step["code"] == design.code(number)
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


def test_each_version_contains_the_code_of_the_one_before(tmp_path):
    for slug in ORDER:
        design = parse_design(DESIGNS / f"{slug}.cad")
        for number in range(2, len(design.steps) + 1):
            previous = design.code(number - 1).splitlines()
            current = design.code(number).splitlines()
            kept = [line for line in previous if not line.startswith("result =")]
            # Every earlier line is still there, in order: steps only add code.
            position = 0
            for line in kept:
                position = current.index(line, position) + 1


def test_design_files_are_checked(tmp_path):
    path = tmp_path / "broken.cad"
    path.write_text("# title: T\n# summary: S\n# part: p\n\n# == step\n# -- build\n    Box(1, 1, 1)\n")
    with pytest.raises(ValueError, match="needs a prompt and a plan"):
        parse_design(path)

    path.write_text("# title: T\n# summary: S\n# part: p\n\n# == step\n# prompt: P\n# plan: Q\n# -- other\n")
    with pytest.raises(ValueError, match="unknown section"):
        parse_design(path)


def test_code_is_assembled_from_the_sections(tmp_path):
    path = tmp_path / "box.cad"
    path.write_text(
        "# title: Box\n# summary: S\n# part: block\n\n"
        "# == step\n# prompt: A box.\n# plan: A box.\n# -- params\nsize = 10.0\n"
        "# -- build\n    Box(size, size, size)\n\n"
        "# == step\n# prompt: A lid.\n# plan: A lid.\n# -- extra\n"
        "with BuildPart() as lid:\n    Box(size, size, 1)\n"
        "# -- result\nresult = Compound([block.part, lid.part])\n"
    )
    design = parse_design(path)

    assert design.code(1) == (
        "size = 10.0\n\nwith BuildPart() as block:\n    Box(size, size, size)\n\n"
        "result = block.part\n"
    )
    assert design.code(2).endswith(
        "with BuildPart() as lid:\n    Box(size, size, 1)\n\nresult = Compound([block.part, lid.part])\n"
    )
