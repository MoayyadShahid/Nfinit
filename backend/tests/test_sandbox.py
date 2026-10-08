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
        "result = export_step(Box(1, 1, 1), '/tmp/model.step')",
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
