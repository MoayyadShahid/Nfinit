import importlib.util
from pathlib import Path

import pytest

from execution.policy import CodePolicyError, validate_cad_code
from execution.runner import SandboxError, _run_worker, export_code, inspect_code


@pytest.mark.parametrize(
    "code",
    [
        "import os\nresult = Box(1, 1, 1)",
        "result = open('/etc/passwd').read()",
        "result = Box.__mro__",
        "result = getattr(Box, 'x')",
        "while True:\n    pass\nresult = Box(1, 1, 1)",
        "def escape():\n    return 1\nresult = escape()",
        "try:\n    result = Box(1, 1, 1)\nexcept* Exception:\n    pass",
        "result = export_step(Box(1, 1, 1), '/tmp/model.step')",
        # Audit NFI-001: a generator's frame reaches the real built-ins.
        'g = (g.gi_frame.f_back.f_back.f_builtins["vars"](\n'
        '    g.gi_frame.f_back.f_back.f_builtins["__import__"]("os")\n'
        ')["popen"]("id") for x in [0])\n'
        "h = list(g)[0]\nresult = int(''.join(list(h)))",
        "g = (1 for x in [0])\nf = g.gi_frame\nresult = Box(1, 1, 1)",
        "f = (1 for x in [0]).gi_code\nresult = Box(1, 1, 1)",
        "t = '{0.gi_frame}'.format((1 for x in [0]))\nresult = Box(1, 1, 1)",
        "k = {'a': 1}['__import__']\nresult = Box(1, 1, 1)",
        "c = Box.mro\nresult = Box(1, 1, 1)",
        # MatchClass.kwd_attrs used to bypass visit_Attribute and capture the
        # blocked str.format method.  The constructed format string then read
        # the real built-ins through a generator frame.
        'p = "{" + "0.gi_frame.f_back.f_back.f_builtins" + "}"\n'
        "match p:\n"
        "    case str(format=fmt):\n"
        "        g = (fmt(g) for x in [0])\n"
        "        h = list(g)[0]\n"
        "result = int(h)",
    ],
)
def test_policy_rejects_unsafe_python(code: str):
    with pytest.raises(CodePolicyError):
        validate_cad_code(code)


def test_policy_accepts_parameterized_build123d_code():
    validate_cad_code(
        "size = 10.0\n"
        "with BuildPart() as part:\n"
        "    Box(size, size, size)\n"
        "result = part.part\n"
    )


def test_worker_timeout_is_enforced(tmp_path: Path):
    worker = tmp_path / "slow_worker.py"
    worker.write_text(
        "import time\n"
        "time.sleep(10)\n"
        'print(\'{"ok": true, "data": {}}\')\n',
        encoding="utf-8",
    )

    with pytest.raises(SandboxError, match="sandbox_timeout") as error:
        _run_worker(
            "result = Box(1, 1, 1)",
            "inspect",
            tmp_path,
            timeout_seconds=0.05,
            worker_path=worker,
        )

    assert error.value.kind == "sandbox_timeout"


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d runtime is not installed",
)
def test_valid_geometry_executes_in_worker():
    inspection = inspect_code("result = Box(10, 20, 30)")

    assert inspection.valid
    assert inspection.solid_count == 1
    assert inspection.bounding_box_mm == {"x": 10, "y": 20, "z": 30}


def test_census_counts_holes_bosses_and_rounded_edges():
    inspection = inspect_code(
        "with BuildPart() as part:\n"
        "    Box(80, 50, 6, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
        "    fillet(part.edges().filter_by(Axis.Z), radius=3)\n"
        "    with Locations((0, 0, 6)):\n"
        "        Cylinder(5, 8, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
        "    with Locations((0, 0, 6)):\n"
        "        with GridLocations(60, 30, 2, 2):\n"
        "            Hole(radius=2)\n"
        "result = part.part"
    )

    census = inspection.census
    assert inspection.valid
    assert census["holes"] == [
        {
            "diameter_mm": 4.0,
            "count": 4,
            "axis": [0.0, 0.0, 1.0],
            "length_mm": 6.0,
            "centers_mm": [[-30.0, -15.0, 3.0], [30.0, -15.0, 3.0],
                           [-30.0, 15.0, 3.0], [30.0, 15.0, 3.0]],
        }
    ]
    assert [(boss["diameter_mm"], boss["count"]) for boss in census["bosses"]] == [(10.0, 1)]
    assert census["rounded_edges"] == [{"radius_mm": 3.0, "count": 4, "surface": "cylinder"}]


def test_inside_out_solid_is_invalid():
    inspection = inspect_code("shape = Solid.make_box(1, 1, 1)\nshape.wrapped.Reverse()\nresult = shape")

    assert not inspection.valid
    assert "inside out" in inspection.error
    assert inspection.solids[0]["inverted"]


def test_spheres_cones_and_rounded_boxes_are_closed_solids():
    # build123d's own is_manifold rejects these; the inspection must not.
    for code in (
        "result = Sphere(15)",
        "result = Cone(5, 0, 10)",
        "with BuildPart() as part:\n    Box(40, 30, 12)\n    fillet(part.edges(), radius=2)\nresult = part.part",
    ):
        inspection = inspect_code(code)
        assert inspection.valid, inspection.error
        assert inspection.solids[0]["manifold"]


def test_open_shell_is_not_a_closed_solid():
    from build123d import Box, Shell, Solid

    from execution.worker import _inspect

    data = _inspect(Solid(Shell(list(Box(10, 10, 10).faces())[:5])))

    assert not data["valid"]
    assert not data["solids"][0]["manifold"]


def test_floating_feature_is_a_warning():
    inspection = inspect_code(
        "with BuildPart() as part:\n"
        "    Box(20, 20, 5)\n"
        "    with Locations((0, 0, 10)):\n"
        "        Cylinder(3, 4)\n"
        "result = part.part"
    )

    assert inspection.valid
    assert inspection.solid_count == 2
    assert inspection.warnings[0].startswith("2 separate solids")


def test_feature_without_faces_is_a_warning():
    inspection = inspect_code(
        "with BuildPart() as part:\n"
        "    Box(20, 20, 5)\n"
        "    register_feature('plate', 'Plate', 'additive', part.part)\n"
        "    register_feature('edge_fillet', 'Edge fillet', 'fillet', part.part, parent_id='plate')\n"
        "    Hole(radius=2)\n"
        "    register_feature('hole', 'Hole', 'subtractive', part.part, parent_id='plate')\n"
        "result = part.part"
    )

    assert inspection.valid
    assert inspection.census["features"] == [
        {"id": "plate", "operation": "additive", "owned_faces": 6},
        {"id": "edge_fillet", "operation": "fillet", "owned_faces": 0},
        {"id": "hole", "operation": "subtractive", "owned_faces": 1},
    ]
    assert inspection.warnings == [
        "Feature 'edge_fillet' owns no faces of the final part. It may have been "
        "skipped, merged into an earlier feature's faces, or removed by a later feature."
    ]


def test_census_does_not_count_slot_ends_as_holes_or_rounded_edges():
    inspection = inspect_code(
        "with BuildPart() as part:\n"
        "    Box(60, 30, 5)\n"
        "    with BuildSketch():\n"
        "        SlotCenterToCenter(20, 6)\n"
        "    extrude(amount=5, mode=Mode.SUBTRACT, both=True)\n"
        "result = part.part"
    )

    assert inspection.census["holes"] == []
    assert inspection.census["rounded_edges"] == []
    assert inspection.census["partial_cylinders"] == 2


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d runtime is not installed",
)
@pytest.mark.parametrize("operation", ["glb", "step", "brep", "stl"])
def test_valid_geometry_exports_in_worker(operation: str):
    artifact = export_code("result = Box(10, 20, 30)", operation)
    try:
        assert artifact.path.is_file()
        assert artifact.path.stat().st_size > 0
    finally:
        artifact.cleanup()


@pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d runtime is not installed",
)
def test_inspection_keeps_a_preview_after_each_feature():
    import json
    import struct

    from execution import inspect_with_snapshots

    inspection, previews = inspect_with_snapshots(
        "with BuildPart() as part:\n"
        "    Box(40, 30, 10)\n"
        '    register_feature("base", "Base", "additive", part.part)\n'
        "    Hole(5)\n"
        '    register_feature("hole", "Hole", "subtractive", part.part)\n'
        "result = part.part\n"
    )

    assert inspection.valid
    assert [preview.feature_id for preview in previews] == ["base", "hole"]

    def new_faces(glb):
        length = struct.unpack_from("<I", glb, 12)[0]
        nodes = json.loads(glb[20 : 20 + length])["nodes"]
        return [node for node in nodes if node.get("extras", {}).get("isNew")]

    assert len(new_faces(previews[0].glb)) == 6  # the whole box is new
    assert len(new_faces(previews[1].glb)) == 1  # only the hole wall


def test_code_without_features_has_no_previews():
    from execution import inspect_with_snapshots

    if importlib.util.find_spec("build123d") is None:
        pytest.skip("build123d runtime is not installed")
    inspection, previews = inspect_with_snapshots("result = Box(1, 2, 3)")
    assert inspection.valid
    assert previews == []
