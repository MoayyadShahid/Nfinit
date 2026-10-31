import json
import logging
import os
import shutil
import site
import subprocess
import sys
import sysconfig
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent.models import FaceSelection, ModelInspection

from .forkserver import (
    ForkedJobDied,
    ForkedJobTimeout,
    ForkServer,
    ForkServerUnavailable,
    MAX_WORKER_RESPONSE_BYTES,
    bootstrap_command,
)
from .policy import CodePolicyError, validate_cad_code
from .topology import TopologyAnalysis

logger = logging.getLogger(__name__)

SandboxOperation = Literal["inspect", "topology", "glb", "step", "brep", "stl"]

ISOLATED_BOOTSTRAP = (
    "import json,runpy,sys;"
    "sys.path[:0]=json.loads(sys.argv[2]);"
    "runpy.run_path(sys.argv[1],run_name='__main__')"
)


class SandboxError(RuntimeError):
    def __init__(self, kind: str, detail: str):
        self.kind = kind
        self.detail = detail
        super().__init__(f"{kind}: {detail}")


@dataclass
class SandboxArtifact:
    path: Path
    temp_dir: Path

    def cleanup(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)


def _worker_environment(work_dir: Path) -> dict[str, str]:
    configured_limits = {
        name: os.environ[name]
        for name in (
            "CAD_SANDBOX_CPU_SECONDS",
            "CAD_SANDBOX_MEMORY_BYTES",
            "CAD_SANDBOX_FILE_BYTES",
            "CAD_SANDBOX_UID_BASE",
            "CAD_SANDBOX_GID_BASE",
            "CAD_SANDBOX_MAX_PROCESSES",
        )
        if name in os.environ
    }
    return {
        "PATH": os.defpath,
        "HOME": str(work_dir),
        "TMPDIR": str(work_dir),
        "LANG": "C.UTF-8",
        "PYTHONHASHSEED": "random",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        **configured_limits,
    }


def _trusted_package_paths() -> list[str]:
    candidates = [
        *site.getsitepackages(),
        site.getusersitepackages(),
        sysconfig.get_paths().get("purelib", ""),
        sysconfig.get_paths().get("platlib", ""),
    ]
    return list(
        dict.fromkeys(
            str(Path(path).resolve())
            for path in candidates
            if path and Path(path).is_dir()
        )
    )


def _decode_worker_response(stdout: str, failure_detail: str) -> dict:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise SandboxError("sandbox_process_error", failure_detail)
    try:
        response = json.loads(lines[-1])
    except json.JSONDecodeError as error:
        raise SandboxError(
            "sandbox_protocol_error", "Worker returned an invalid response."
        ) from error

    if not response.get("ok"):
        worker_error = response.get("error") or {}
        error_type = worker_error.get("type", "ExecutionError")
        message = worker_error.get("message", "CAD execution failed.")
        raise SandboxError("cad_execution_error", f"{error_type}: {message}")
    return response["data"]


def _sandbox_mode() -> str:
    # The fork server checks that it is single-threaded before it forks, and
    # only Linux lets it see OpenCASCADE's native threads.
    default = "fork" if sys.platform.startswith("linux") else "spawn"
    mode = os.environ.get("CAD_SANDBOX_MODE", default).strip().lower()
    return mode if mode in ("fork", "spawn") else default


def _max_concurrency() -> int:
    try:
        return max(1, int(os.environ.get("CAD_SANDBOX_MAX_CONCURRENCY", "4")))
    except ValueError:
        return 4


_job_slots = threading.BoundedSemaphore(_max_concurrency())
_fork_server: ForkServer | None = None
_fork_server_lock = threading.Lock()


def get_fork_server() -> ForkServer:
    global _fork_server
    with _fork_server_lock:
        if _fork_server is None:
            _fork_server = ForkServer(
                bootstrap_command(
                    Path(__file__).with_name("worker.py"),
                    _trusted_package_paths(),
                    ISOLATED_BOOTSTRAP,
                ),
                _worker_environment,
            )
        return _fork_server


def start_sandbox() -> None:
    """Warm the fork server so the first request does not pay for it."""
    if _sandbox_mode() != "fork":
        return
    try:
        get_fork_server().ensure_started()
    except ForkServerUnavailable as error:
        logger.warning("%s Falling back to one-shot workers.", error)


def stop_sandbox() -> None:
    if _fork_server is not None:
        _fork_server.stop()


def _log_tail(work_dir: Path) -> str:
    try:
        return (work_dir / "worker.log").read_text(errors="replace").strip()[-2_000:]
    except OSError:
        return ""


def _run_forked(payload: dict, work_dir: Path, timeout: float) -> dict:
    try:
        response = get_fork_server().run(
            {**payload, "work_dir": str(work_dir), "deadline_seconds": timeout},
            timeout,
        )
    except ForkedJobTimeout as error:
        raise SandboxError(
            "sandbox_timeout", f"CAD execution exceeded {timeout:g} seconds."
        ) from error
    except ForkedJobDied:
        detail = _log_tail(work_dir) or "Worker exited without a response."
        raise SandboxError("sandbox_process_error", detail) from None
    return _decode_worker_response(response, "Worker exited without a response.")


def _run_spawned(
    payload: dict, worker: Path, work_dir: Path, timeout: float
) -> dict:
    response_path = work_dir / ".worker-response.json"
    error_path = work_dir / ".worker-stderr.log"
    try:
        # Files keep a compromised worker's output out of the API process's
        # memory. The worker's RLIMIT_FSIZE bounds the files; below we refuse
        # to read more than the much smaller protocol limit.
        with response_path.open("wb") as stdout, error_path.open("wb") as stderr:
            process = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    ISOLATED_BOOTSTRAP,
                    str(worker),
                    json.dumps(_trusted_package_paths()),
                ],
                input=json.dumps(payload),
                text=True,
                stdout=stdout,
                stderr=stderr,
                cwd=work_dir,
                env=_worker_environment(work_dir),
                timeout=timeout,
                check=False,
            )
    except subprocess.TimeoutExpired as error:
        raise SandboxError(
            "sandbox_timeout", f"CAD execution exceeded {timeout:g} seconds."
        ) from error

    try:
        if response_path.stat().st_size > MAX_WORKER_RESPONSE_BYTES:
            raise SandboxError(
                "sandbox_protocol_error", "Worker response exceeded its size limit."
            )
        stdout = response_path.read_text(errors="replace")
    except OSError as error:
        raise SandboxError(
            "sandbox_protocol_error", "Worker response was not available."
        ) from error
    try:
        detail = error_path.read_text(errors="replace").strip()[-2_000:]
    except OSError:
        detail = ""
    detail = detail or (
        f"Worker exited with status {process.returncode}."
    )
    return _decode_worker_response(stdout, detail)


def _run_worker(
    code: str,
    operation: SandboxOperation,
    work_dir: Path,
    output_name: str | None = None,
    timeout_seconds: float | None = None,
    worker_path: Path | None = None,
    selection: FaceSelection | None = None,
    snapshots: bool = False,
) -> dict:
    worker = worker_path or Path(__file__).with_name("worker.py")
    timeout = timeout_seconds or float(
        os.environ.get("CAD_SANDBOX_TIMEOUT_SECONDS", "90")
    )
    payload = {"code": code, "operation": operation}
    if output_name:
        payload["output_name"] = output_name
    if selection:
        payload["selection"] = selection.model_dump(mode="json")
    if snapshots:
        payload["snapshots"] = True

    # Waiting for a free slot counts against the same deadline as the job.
    if not _job_slots.acquire(timeout=timeout):
        raise SandboxError(
            "sandbox_timeout", "The CAD sandbox is busy. Please retry."
        )
    try:
        if worker_path is None and _sandbox_mode() == "fork":
            try:
                return _run_forked(payload, work_dir, timeout)
            except ForkServerUnavailable as error:
                logger.warning("%s Running a one-shot worker instead.", error)
        return _run_spawned(payload, worker, work_dir, timeout)
    finally:
        _job_slots.release()


def inspect_code(code: str) -> ModelInspection:
    try:
        validate_cad_code(code)
    except CodePolicyError as error:
        return ModelInspection(
            valid=False, error=f"sandbox_security_error: {str(error)}"
        )

    work_dir = Path(tempfile.mkdtemp(prefix="nfinit-inspect-"))
    try:
        data = _run_worker(code, "inspect", work_dir)
        return ModelInspection.model_validate(data)
    except SandboxError as error:
        return ModelInspection(valid=False, error=str(error))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def analyze_code(
    code: str, selection: FaceSelection | None = None
) -> TopologyAnalysis:
    try:
        validate_cad_code(code)
    except CodePolicyError as error:
        return TopologyAnalysis(
            valid=False, error=f"sandbox_security_error: {str(error)}"
        )

    work_dir = Path(tempfile.mkdtemp(prefix="nfinit-topology-"))
    try:
        data = _run_worker(
            code,
            "topology",
            work_dir,
            selection=selection,
        )
        return TopologyAnalysis.model_validate(data)
    except SandboxError as error:
        return TopologyAnalysis(valid=False, error=str(error))
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def export_code(code: str, operation: SandboxOperation) -> SandboxArtifact:
    if operation in ("inspect", "topology"):
        raise ValueError("Use the corresponding analysis function.")
    try:
        validate_cad_code(code)
    except CodePolicyError as error:
        raise SandboxError("sandbox_security_error", str(error)) from error

    work_dir = Path(tempfile.mkdtemp(prefix="nfinit-export-"))
    extensions = {
        "glb": ".glb",
        "step": ".step",
        "brep": ".brep",
        "stl": ".stl",
    }
    output_name = f"model{extensions[operation]}"
    output_path = work_dir / output_name
    try:
        _run_worker(code, operation, work_dir, output_name=output_name)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise SandboxError(
                "cad_export_error", f"{operation.upper()} export was empty."
            )
        return SandboxArtifact(path=output_path, temp_dir=work_dir)
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


@dataclass
class BuiltMesh:
    glb: bytes
    inspection: ModelInspection


def build_mesh(code: str) -> BuiltMesh:
    """Build a GLB and its geometry facts in one sandbox run."""
    try:
        validate_cad_code(code)
    except CodePolicyError as error:
        raise SandboxError("sandbox_security_error", str(error)) from error

    work_dir = Path(tempfile.mkdtemp(prefix="nfinit-mesh-"))
    output_path = work_dir / "model.glb"
    try:
        data = _run_worker(code, "glb", work_dir, output_name="model.glb")
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise SandboxError("cad_export_error", "GLB export was empty.")
        return BuiltMesh(
            glb=output_path.read_bytes(),
            inspection=ModelInspection.model_validate(data["inspection"]),
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@dataclass
class BuildSnapshot:
    """The part right after one registered feature, as a coarse GLB."""

    feature_id: str
    name: str
    glb: bytes


def inspect_with_snapshots(code: str) -> tuple[ModelInspection, list[BuildSnapshot]]:
    """Inspect the code, and keep a preview of the part after each feature."""
    try:
        validate_cad_code(code)
    except CodePolicyError as error:
        return ModelInspection(valid=False, error=f"sandbox_security_error: {error}"), []

    work_dir = Path(tempfile.mkdtemp(prefix="nfinit-inspect-"))
    try:
        data = _run_worker(code, "inspect", work_dir, snapshots=True)
        previews = []
        for item in data.pop("snapshots", []):
            path = work_dir / item["file"]
            if path.is_file() and path.parent == work_dir:
                previews.append(
                    BuildSnapshot(item["featureId"], item["name"], path.read_bytes())
                )
        if data.pop("snapshot_error", None):
            logger.warning("Build previews failed; the inspection still stands.")
        return ModelInspection.model_validate(data), previews
    except SandboxError as error:
        return ModelInspection(valid=False, error=str(error)), []
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
