import json
import os
import shutil
import site
import subprocess
import sys
import sysconfig
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent.models import FaceSelection, ModelInspection

from .policy import CodePolicyError, validate_cad_code
from .topology import TopologyAnalysis

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


def _decode_worker_response(process: subprocess.CompletedProcess[str]) -> dict:
    lines = [line for line in process.stdout.splitlines() if line.strip()]
    if not lines:
        detail = process.stderr.strip()[-2_000:] or (
            f"Worker exited with status {process.returncode}."
        )
        raise SandboxError("sandbox_process_error", detail)
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


def _run_worker(
    code: str,
    operation: SandboxOperation,
    work_dir: Path,
    output_name: str | None = None,
    timeout_seconds: float | None = None,
    worker_path: Path | None = None,
    selection: FaceSelection | None = None,
) -> dict:
    worker = worker_path or Path(__file__).with_name("worker.py")
    timeout = timeout_seconds or float(
        os.environ.get("CAD_SANDBOX_TIMEOUT_SECONDS", "20")
    )
    payload = {"code": code, "operation": operation}
    if output_name:
        payload["output_name"] = output_name
    if selection:
        payload["selection"] = selection.model_dump(mode="json")

    try:
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
            capture_output=True,
            cwd=work_dir,
            env=_worker_environment(work_dir),
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise SandboxError(
            "sandbox_timeout", f"CAD execution exceeded {timeout:g} seconds."
        ) from error

    return _decode_worker_response(process)


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
