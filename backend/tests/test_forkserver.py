import asyncio
import importlib.util
import os
import threading
import time
from pathlib import Path

import httpx
import pytest

import main
from execution import runner
from execution.forkserver import ForkServerUnavailable
from execution.runner import SandboxError, _run_worker, inspect_code

requires_build123d = pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d runtime is not installed",
)

FILLETED_PLATE = (
    "with BuildPart() as plate:\n"
    "    Box(80, 60, 10)\n"
    "    with GridLocations(60, 40, 2, 2):\n"
    "        Hole(4)\n"
    "    fillet(plate.edges().filter_by(Axis.Z), 3)\n"
    "result = plate.part\n"
)


@pytest.fixture
def fork_mode(monkeypatch):
    monkeypatch.setenv("CAD_SANDBOX_MODE", "fork")
    runner.get_fork_server().ensure_started()
    yield runner.get_fork_server()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@requires_build123d
def test_warm_jobs_skip_the_opencascade_import(fork_mode):
    inspect_code(FILLETED_PLATE)  # first fork after start-up

    started = time.monotonic()
    inspection = inspect_code(FILLETED_PLATE)
    elapsed = time.monotonic() - started

    assert inspection.valid
    assert inspection.solid_count == 1
    # A one-shot worker spends about 2 s importing OpenCASCADE alone.
    assert elapsed < 1.5


@requires_build123d
def test_each_job_runs_in_a_fresh_child(fork_mode, tmp_path: Path):
    # _run_worker skips the AST policy, so this reaches the child's scope.
    _run_worker("Box.leaked = 5\nresult = Box(1, 1, 1)", "inspect", tmp_path)

    with pytest.raises(SandboxError, match="AttributeError"):
        _run_worker("result = Box(1, 1, Box.leaked)", "inspect", tmp_path)


@requires_build123d
def test_forked_child_keeps_restricted_builtins(fork_mode, tmp_path: Path):
    with pytest.raises(SandboxError, match="NameError: name 'open'"):
        _run_worker(
            "data = open('/etc/passwd').read()\nresult = Box(1, 1, 1)",
            "inspect",
            tmp_path,
        )


@requires_build123d
def test_forked_job_past_its_deadline_is_killed(fork_mode, tmp_path: Path):
    children_before = set(_children(fork_mode))

    with pytest.raises(SandboxError) as error:
        _run_worker(
            "total = 0\nfor index in range(10 ** 12):\n    total += index\n"
            "result = Box(1, 1, 1)",
            "inspect",
            tmp_path,
            timeout_seconds=1,
        )

    assert error.value.kind == "sandbox_timeout"
    deadline = time.monotonic() + 5
    stuck = set(_children(fork_mode)) - children_before
    while stuck and time.monotonic() < deadline:
        time.sleep(0.05)
        stuck = {pid for pid in stuck if _alive(pid)}
    assert not stuck


def _children(server) -> list[int]:
    path = Path(f"/proc/{server._process.pid}/task/{server._process.pid}/children")
    if not path.exists():
        return []
    return [int(pid) for pid in path.read_text().split()]


@requires_build123d
def test_unavailable_fork_server_falls_back_to_one_shot_worker(monkeypatch):
    monkeypatch.setenv("CAD_SANDBOX_MODE", "fork")

    def unavailable(*_args, **_kwargs):
        raise ForkServerUnavailable("down for the test.")

    monkeypatch.setattr(runner, "_run_forked", unavailable)

    inspection = inspect_code("result = Box(10, 20, 30)")

    assert inspection.valid
    assert inspection.bounding_box_mm == {"x": 10, "y": 20, "z": 30}


def test_spawn_mode_never_contacts_the_fork_server(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CAD_SANDBOX_MODE", "spawn")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("spawn mode must not use the fork server")

    monkeypatch.setattr(runner, "_run_forked", forbidden)
    monkeypatch.setattr(
        runner, "_run_spawned", lambda *_args, **_kwargs: {"valid": True}
    )

    assert _run_worker("result = Box(1, 1, 1)", "inspect", tmp_path) == {
        "valid": True
    }


def test_busy_sandbox_times_out_instead_of_queueing_forever(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(runner, "_job_slots", threading.BoundedSemaphore(1))
    runner._job_slots.acquire()
    try:
        with pytest.raises(SandboxError, match="busy") as error:
            _run_worker(
                "result = Box(1, 1, 1)", "inspect", tmp_path, timeout_seconds=0.05
            )
    finally:
        runner._job_slots.release()

    assert error.value.kind == "sandbox_timeout"


@pytest.mark.asyncio
async def test_slow_mesh_does_not_block_other_requests(monkeypatch):
    release = threading.Event()

    def slow_export(_code, _operation):
        release.wait(5)
        raise SandboxError("sandbox_timeout", "slow on purpose")

    monkeypatch.setattr(main, "export_code", slow_export)
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        mesh = asyncio.create_task(
            client.post("/generate-mesh", json={"code": "result = Box(1, 1, 1)"})
        )
        await asyncio.sleep(0.1)
        health = await asyncio.wait_for(client.get("/health"), timeout=2)
        release.set()
        assert health.status_code == 200
        assert (await mesh).status_code == 408


@requires_build123d
def test_orphaned_child_ends_at_its_own_deadline(fork_mode, tmp_path: Path):
    import json
    import socket

    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.connect(str(fork_mode.socket_path))
    reader = connection.makefile("rb")
    pid = json.loads(reader.readline())["pid"]
    connection.sendall(
        json.dumps(
            {
                "code": "total = 0\nfor index in range(10 ** 12):\n"
                "    total += index\nresult = Box(1, 1, 1)",
                "operation": "inspect",
                "work_dir": str(tmp_path),
                "deadline_seconds": 0.01,
            }
        ).encode()
    )
    connection.shutdown(socket.SHUT_WR)
    connection.close()  # Nobody waits for this job any more.

    deadline = time.monotonic() + 15
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _alive(pid)
