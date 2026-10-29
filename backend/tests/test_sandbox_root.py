"""The second barrier: a job that escapes the policy still runs unprivileged.

These run only as root on Linux, like the production container (CI runs them
with sudo). They call _run_worker directly, which skips the policy check, and
use the audit's escape on purpose to see what escaped code can do.
"""

import importlib.util
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from execution import runner
from execution.runner import SandboxError, _run_worker

pytestmark = [
    pytest.mark.skipif(
        not sys.platform.startswith("linux") or os.geteuid() != 0,
        reason="needs root on Linux, like the production container",
    ),
    pytest.mark.skipif(
        importlib.util.find_spec("build123d") is None,
        reason="build123d runtime is not installed",
    ),
]


def escape(expression: str) -> str:
    """Code that evaluates ``expression`` with the real built-ins as ``B``."""
    return (
        "g = (g.gi_frame.f_back.f_back.f_builtins for x in [0])\n"
        "B = list(g)[0]\n"
        f"value = {expression}\n"
        # int() of a non-number fails, and the error carries the value back.
        "result = int('value=' + str(value))\n"
    )


def run_escaped(expression: str, mode: str, monkeypatch) -> str:
    """What the escaped expression returned (reported through the int error)."""
    monkeypatch.setenv("CAD_SANDBOX_MODE", mode)
    work_dir = job_dir()
    try:
        with pytest.raises(SandboxError) as error:
            _run_worker(escape(expression), "inspect", work_dir)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    return str(error.value)


def job_dir() -> Path:
    # Like the backend: a private directory directly under the system temp
    # directory, which the unprivileged job can reach once it owns it.
    return Path(tempfile.mkdtemp(prefix="nfinit-test-"))


@pytest.fixture(params=["fork", "spawn"])
def mode(request):
    yield request.param
    if request.param == "fork":
        runner.stop_sandbox()


def test_escaped_code_does_not_run_as_root(mode, monkeypatch):
    uid = run_escaped('B["__import__"]("os").getuid()', mode, monkeypatch)
    assert "value=65534" in uid


def test_escaped_code_cannot_read_the_server_environment(mode, monkeypatch):
    message = run_escaped(
        'B["open"]("/proc/1/environ").read()', mode, monkeypatch
    )
    assert "PermissionError" in message


def test_escaped_code_cannot_change_app_files(mode, monkeypatch):
    target = Path(runner.__file__)
    message = run_escaped(
        f'B["open"]({str(target)!r}, "a")', mode, monkeypatch
    )
    assert "PermissionError" in message


def test_real_parts_still_build_unprivileged(mode, monkeypatch):
    monkeypatch.setenv("CAD_SANDBOX_MODE", mode)
    work_dir = job_dir()
    code = (
        "with BuildPart() as plate:\n"
        "    Box(80, 60, 10)\n"
        "    with GridLocations(60, 40, 2, 2):\n"
        "        Hole(4)\n"
        "    fillet(plate.edges().filter_by(Axis.Z), 3)\n"
        "result = plate.part\n"
    )
    try:
        data = _run_worker(code, "glb", work_dir, output_name="model.glb")
        assert (work_dir / "model.glb").stat().st_size > 0
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    assert data["inspection"]["solid_count"] == 1
