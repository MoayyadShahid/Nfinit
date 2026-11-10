import json
import logging
import math
import os
import re
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

SandboxOperation = Literal[
    "inspect", "topology", "query", "review", "render", "printability",
    "glb", "step", "brep", "stl",
]

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
    query: dict | None = None,
    views: list[dict] | None = None,
    profile: dict | None = None,
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
    if query is not None:
        payload["query"] = query
    if views is not None:
        payload["views"] = views
    if profile is not None:
        payload["profile"] = profile

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


QUERY_KINDS = ("summary", "faces", "face", "edges", "distance", "section")
ENTITY_ID = re.compile(r"(face|edge)_[0-9a-f]{20}|[a-z][a-z0-9_]{0,63}")
SURFACE_TYPES = ("plane", "cylinder", "cone", "sphere", "torus", "bspline", "bezier",
                 "revolution", "extrusion", "offset", "other")
CURVE_TYPES = ("line", "circle", "ellipse", "hyperbola", "parabola", "bezier", "bspline",
               "offset", "other")


def _number(value, name: str, low: float = -1e6, high: float = 1e6) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not low <= value <= high:
        raise ValueError(f"{name} must be a number from {low:g} to {high:g}.")
    return float(value)


def _entity(value, name: str):
    if isinstance(value, list):
        if len(value) != 3:
            raise ValueError(f"{name} as a point needs three coordinates.")
        return [_number(item, name) for item in value]
    if not isinstance(value, str) or not ENTITY_ID.fullmatch(value):
        raise ValueError(f"{name} must be a face id, an edge id, a feature id or [x, y, z].")
    return value


def validate_query(query) -> dict:
    """A bounded copy of an inspect_model query, or ValueError."""
    if not isinstance(query, dict) or query.get("kind") not in QUERY_KINDS:
        raise ValueError(f"query.kind must be one of {', '.join(QUERY_KINDS)}.")
    kind = query["kind"]
    allowed = {
        "summary": set(),
        "faces": {"surface_type", "feature_id", "normal", "min_area_mm2", "limit"},
        "face": {"face_id"},
        "edges": {"curve_type", "feature_id", "limit"},
        "distance": {"a", "b"},
        "section": {"axis", "at"},
    }[kind]
    unknown = set(query) - allowed - {"kind"}
    if unknown:
        raise ValueError(f"A {kind} query does not take: {', '.join(sorted(unknown))}.")
    clean: dict = {"kind": kind}
    if "limit" in query:
        clean["limit"] = int(_number(query["limit"], "limit", 1, 50))
    if "surface_type" in query:
        if query["surface_type"] not in SURFACE_TYPES:
            raise ValueError(f"surface_type must be one of {', '.join(SURFACE_TYPES)}.")
        clean["surface_type"] = query["surface_type"]
    if "curve_type" in query:
        if query["curve_type"] not in CURVE_TYPES:
            raise ValueError(f"curve_type must be one of {', '.join(CURVE_TYPES)}.")
        clean["curve_type"] = query["curve_type"]
    if "feature_id" in query:
        clean["feature_id"] = _entity(query["feature_id"], "feature_id")
    if "normal" in query:
        normal = query["normal"]
        if not isinstance(normal, list) or len(normal) != 3:
            raise ValueError("normal must be [x, y, z].")
        clean["normal"] = [_number(value, "normal", -1, 1) for value in normal]
        if not any(clean["normal"]):
            raise ValueError("normal must not be zero.")
    if "min_area_mm2" in query:
        clean["min_area_mm2"] = _number(query["min_area_mm2"], "min_area_mm2", 0, 1e12)
    if kind == "face":
        face_id = query.get("face_id")
        if not isinstance(face_id, str) or not re.fullmatch(r"face_[0-9a-f]{20}", face_id):
            raise ValueError("face_id must be a face id such as face_0123456789abcdef0123.")
        clean["face_id"] = face_id
    if kind == "distance":
        clean["a"] = _entity(query.get("a"), "a")
        clean["b"] = _entity(query.get("b"), "b")
    if kind == "section":
        if query.get("axis") not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z.")
        clean["axis"] = query["axis"]
        clean["at"] = _number(query.get("at"), "at")
    return clean


def query_code(code: str, query: dict) -> dict:
    """Build the code once and answer one question about the part."""
    clean = validate_query(query)
    validate_cad_code(code)
    work_dir = Path(tempfile.mkdtemp(prefix="nfinit-query-"))
    try:
        return _run_worker(code, "query", work_dir, query=clean)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


VIEW_PRESETS = ("iso", "iso_back", "front", "back", "right", "left", "top", "bottom")
VIEW_MODES = ("shaded", "hidden_line", "xray")
MAX_VIEWS = 4
MAX_HIGHLIGHTS = 20


def validate_views(views) -> list[dict]:
    """A bounded copy of view_model's views, or ValueError."""
    if not isinstance(views, list) or not 1 <= len(views) <= MAX_VIEWS:
        raise ValueError(f"views must be a list of 1 to {MAX_VIEWS} views.")
    clean = []
    for index, view in enumerate(views):
        label = f"views[{index}]"
        if not isinstance(view, dict):
            raise ValueError(f"{label} must be an object.")
        unknown = set(view) - {"camera", "mode", "section", "focus", "highlight", "size"}
        if unknown:
            raise ValueError(f"{label} does not take: {', '.join(sorted(unknown))}.")
        item: dict = {}
        camera = view.get("camera", "iso")
        if isinstance(camera, str):
            if camera not in VIEW_PRESETS:
                raise ValueError(f"{label}.camera must be one of {', '.join(VIEW_PRESETS)} or an azimuth/elevation.")
            item["camera"] = camera
        elif isinstance(camera, dict) and set(camera) == {"azimuth", "elevation"}:
            item["camera"] = {
                "azimuth": _number(camera["azimuth"], "azimuth", -360, 360),
                "elevation": _number(camera["elevation"], "elevation", -90, 90),
            }
        else:
            raise ValueError(f"{label}.camera must be a preset name or {{azimuth, elevation}}.")
        mode = view.get("mode", "shaded")
        if mode not in VIEW_MODES:
            raise ValueError(f"{label}.mode must be one of {', '.join(VIEW_MODES)}.")
        item["mode"] = mode
        if view.get("size", "normal") not in ("normal", "large"):
            raise ValueError(f"{label}.size must be normal or large.")
        item["size"] = view.get("size", "normal")
        if "section" in view:
            section = view["section"]
            if not isinstance(section, dict) or set(section) - {"axis", "at", "keep"} \
                    or section.get("axis") not in ("x", "y", "z") \
                    or section.get("keep", "below") not in ("below", "above"):
                raise ValueError(f"{label}.section needs axis x|y|z, at in mm, and keep below|above.")
            item["section"] = {"axis": section["axis"], "at": _number(section.get("at"), "section.at"),
                               "keep": section.get("keep", "below")}
        if "focus" in view:
            item["focus"] = _entity(view["focus"], f"{label}.focus")
            if isinstance(item["focus"], list):
                raise ValueError(f"{label}.focus must be a face id or a feature id.")
        if "highlight" in view:
            highlight = view["highlight"]
            if not isinstance(highlight, list) or len(highlight) > MAX_HIGHLIGHTS:
                raise ValueError(f"{label}.highlight must be a list of at most {MAX_HIGHLIGHTS} ids.")
            item["highlight"] = []
            for entity in highlight:
                entity = _entity(entity, f"{label}.highlight")
                if isinstance(entity, list):
                    raise ValueError(f"{label}.highlight takes face ids and feature ids.")
                item["highlight"].append(entity)
        clean.append(item)
    return clean


@dataclass
class RenderedView:
    name: str
    png: bytes | None = None
    error: str | None = None


def _read_views(data: dict, work_dir: Path) -> list[RenderedView]:
    views = []
    for item in data.pop("views", []):
        if item.get("file"):
            path = work_dir / item["file"]
            if path.is_file() and path.parent == work_dir:
                views.append(RenderedView(item["name"], png=path.read_bytes()))
                continue
        views.append(RenderedView(item["name"], error=item.get("error") or "The view was not written."))
    return views


def review_code(code: str) -> tuple[ModelInspection, list[RenderedView]]:
    """Inspect the code and draw the two default views in one sandbox run."""
    try:
        validate_cad_code(code)
    except CodePolicyError as error:
        return ModelInspection(valid=False, error=f"sandbox_security_error: {error}"), []
    work_dir = Path(tempfile.mkdtemp(prefix="nfinit-review-"))
    try:
        data = _run_worker(code, "review", work_dir)
        views = _read_views(data, work_dir)
        return ModelInspection.model_validate(data), views
    except SandboxError as error:
        return ModelInspection(valid=False, error=str(error)), []
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def render_code(code: str, views: list[dict]) -> list[RenderedView]:
    """Draw the requested views of the part."""
    clean = validate_views(views)
    validate_cad_code(code)
    work_dir = Path(tempfile.mkdtemp(prefix="nfinit-render-"))
    try:
        return _read_views(_run_worker(code, "render", work_dir, views=clean), work_dir)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# Conservative FDM defaults from public design guides (Hubs, Prusa, Formlabs).
# They are starting points, not physics: a printer's own limits replace them.
DEFAULT_PRINT_PROFILE = {
    "process": "fdm",
    "bed_mm": [220.0, 220.0, 250.0],
    "nozzle_mm": 0.4,
    "min_wall_mm": 1.2,
    "overhang_limit_deg": 45.0,
    "min_hole_mm": 2.0,
    "max_support_ratio": 0.30,
}


def validate_profile(profile: dict | None) -> dict:
    """The default print profile with valid overrides applied, or ValueError."""
    clean = {**DEFAULT_PRINT_PROFILE, "bed_mm": list(DEFAULT_PRINT_PROFILE["bed_mm"])}
    if profile is None:
        return clean
    if not isinstance(profile, dict) or set(profile) - set(DEFAULT_PRINT_PROFILE):
        raise ValueError(f"A print profile takes only: {', '.join(DEFAULT_PRINT_PROFILE)}.")
    if "process" in profile:
        if profile["process"] not in ("fdm", "sla", "sls"):
            raise ValueError("process must be fdm, sla or sls.")
        clean["process"] = profile["process"]
    if "bed_mm" in profile:
        bed = profile["bed_mm"]
        if not isinstance(bed, list) or len(bed) != 3:
            raise ValueError("bed_mm must be [x, y, z].")
        clean["bed_mm"] = [_number(value, "bed_mm", 10, 5000) for value in bed]
    ranges = {"nozzle_mm": (0.05, 3), "min_wall_mm": (0.1, 20), "overhang_limit_deg": (0, 89),
              "min_hole_mm": (0.1, 50), "max_support_ratio": (0, 10)}
    for name, (low, high) in ranges.items():
        if name in profile:
            clean[name] = _number(profile[name], name, low, high)
    return clean


def printability_code(code: str, profile: dict | None = None) -> dict:
    """Printability facts of the part, and findings against the profile."""
    clean = validate_profile(profile)
    validate_cad_code(code)
    work_dir = Path(tempfile.mkdtemp(prefix="nfinit-print-"))
    try:
        return _run_worker(code, "printability", work_dir, profile=clean)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def export_code(code: str, operation: SandboxOperation) -> SandboxArtifact:
    if operation in ("inspect", "topology", "query", "review", "render", "printability"):
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
