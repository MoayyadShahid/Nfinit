import asyncio
import base64
import binascii
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from agent import (
    FaceSelection,
    ModelInspection,
)
from execution import (
    SandboxError,
    RevisionComparison,
    TopologyAnalysis,
    analyze_code,
    compare_code,
    export_code,
    inspect_code as sandbox_inspect_code,
    start_sandbox,
    stop_sandbox,
)
from projects import router as projects_router
from projects.billing import billing_enabled
from projects.body_limit import BodySizeLimitMiddleware
from projects.limits import MAX_CODE_CHARS, SandboxUserId
from projects.store import get_project_store
from projects.account import router as account_router
from projects.billing import router as billing_router
from projects.meshes import router as meshes_router
from projects.runs import router as runs_router
from projects.config import validate_project_configuration
from projects.store import (
    StorageQuotaExceededError,
    max_projects_per_user,
    max_revisions_per_user,
    max_storage_bytes_per_user,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).with_name(".env"))


def _optional_service_status() -> dict[str, str]:
    supabase = (
        "configured"
        if os.getenv("SUPABASE_URL") or os.getenv("NFNIT_DATABASE_URL")
        else "unset (SQLite + local auth bypass)"
    )
    return {
        "openrouter": "configured" if os.getenv("OPENROUTER_API_KEY") else "MISSING",
        "supabase": supabase,
        "stripe": (
            "enabled"
            if billing_enabled()
            else "disabled (everyone can generate and export)"
        ),
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_project_configuration()
    for name, status in _optional_service_status().items():
        logger.info("Service %s: %s", name, status)
    # Warm the CAD sandbox in the background: a cold OpenCASCADE import can
    # outlast the platform health check, which must answer meanwhile.
    threading.Thread(target=start_sandbox, name="cad-sandbox-start", daemon=True).start()
    yield
    stop_sandbox()
    # Close pooled database connections, if this deployment uses Postgres.
    close = getattr(get_project_store(), "close", None)
    if callable(close):
        close()


app = FastAPI(title="Nfinit Geometry Engine", lifespan=lifespan)


@app.exception_handler(StorageQuotaExceededError)
async def storage_quota_exceeded(_request: Request, _error: StorageQuotaExceededError):
    limit_mib = max_storage_bytes_per_user() // (1024 * 1024)
    if _error.reason == "projects":
        detail = (
            f"Your account has reached its {max_projects_per_user()} project limit. "
            "Delete an old project and try again."
        )
    elif _error.reason == "revisions":
        detail = (
            f"Your account has reached its {max_revisions_per_user()} revision limit. "
            "Delete an old project and try again."
        )
    else:
        detail = (
            f"Your saved projects have reached the {limit_mib} MiB storage limit. "
            "Delete an old project and try again."
        )
    return JSONResponse(
        status_code=413,
        content={"detail": detail},
    )

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models, exports and JSON leave compressed when the client accepts gzip. A
# GLB shrinks to about 30%. Event streams are never compressed (Starlette
# excludes text/event-stream), so progress still arrives as it happens.
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)

# Outermost: oversized bodies are refused before anything reads them.
app.add_middleware(BodySizeLimitMiddleware)

# The API serves JSON and binary files only; these headers stop browsers from
# guessing other content types, framing responses or leaking URLs.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


app.include_router(projects_router)
app.include_router(runs_router)
app.include_router(billing_router)
app.include_router(account_router)
app.include_router(meshes_router)


@app.get("/")
@app.get("/health")
def health():
    # Keep operator configuration in startup logs. A public health probe need
    # only say whether the process can answer; service inventory is useful
    # reconnaissance and should not be exposed anonymously.
    return {"status": "ok"}


@app.get("/local-agents")
def local_agents(request: Request):
    from agent.local_access import agent_inventory, local_agents_enabled, require_local_access
    if not local_agents_enabled():
        return {"local": False, "agents": []}
    require_local_access(request)
    return {"local": True, "agents": agent_inventory()}


class StlImportRequest(BaseModel):
    data: str = Field(max_length=14_000_000)
    units: Literal["mm", "in"]
    mode: Literal["preserve", "reconstruct"] = "preserve"


@app.post("/import-stl")
async def import_stl(request: StlImportRequest, _user: SandboxUserId):
    from execution.references import faceted_code, mesh_facts, parse_stl, render_views
    try:
        data = base64.b64decode(request.data, validate=True)
        triangles = await asyncio.to_thread(parse_stl, data, 25.4 if request.units == "in" else 1.0)
        facts = await asyncio.to_thread(mesh_facts, triangles)
        views = await asyncio.to_thread(render_views, triangles)
        code = await asyncio.to_thread(faceted_code, triangles) if request.mode == "preserve" else ""
        inspection = await asyncio.to_thread(_inspect_code, code) if code else None
        if inspection and not inspection.valid:
            raise ValueError("The mesh did not form a valid solid. Repair the STL or choose reconstruction.")
        return {"code": code, "facts": facts, "views": views,
                "inspection": inspection.model_dump() if inspection else None,
                "mode": request.mode}
    except (ValueError, binascii.Error) as error:
        raise HTTPException(400, str(error)) from error


class GenerateMeshRequest(BaseModel):
    code: str = Field(max_length=MAX_CODE_CHARS)


class ExportModelRequest(BaseModel):
    code: str = Field(max_length=MAX_CODE_CHARS)
    format: str  # "step" | "brep" | "stl"


class AnalyzeModelRequest(BaseModel):
    code: str = Field(max_length=MAX_CODE_CHARS)
    selection: FaceSelection | None = None


class CompareModelsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    previous_code: str = Field(alias="previousCode", max_length=MAX_CODE_CHARS)
    current_code: str = Field(alias="currentCode", max_length=MAX_CODE_CHARS)
    previous_face_id: str | None = Field(default=None, alias="previousFaceId")


def _inspect_code(code: str) -> ModelInspection:
    """Execute CAD code in the sandbox and return geometry facts."""
    return sandbox_inspect_code(code)


@app.post("/inspect-model", response_model=ModelInspection)
async def inspect_model(
    request: GenerateMeshRequest, _user: SandboxUserId
):
    """Execute CAD code and return geometry facts."""
    return await asyncio.to_thread(_inspect_code, request.code)


@app.post("/analyze-model", response_model=TopologyAnalysis)
async def analyze_model(
    request: AnalyzeModelRequest, _user: SandboxUserId
):
    """Index B-rep entities and optionally resolve a geometric face selection."""
    return await asyncio.to_thread(analyze_code, request.code, request.selection)


@app.post("/compare-models", response_model=RevisionComparison)
def compare_models(
    request: CompareModelsRequest, _user: SandboxUserId
):
    """Match semantic features, constraints, and faces across two revisions."""
    return compare_code(
        request.previous_code,
        request.current_code,
        previous_face_id=request.previous_face_id,
    )


@app.post("/export-model")
async def export_model(
    request: ExportModelRequest,
    background_tasks: BackgroundTasks,
    _user: SandboxUserId,
):
    """Execute build123d code in the sandbox and export the requested format."""
    fmt = request.format.lower()
    if fmt not in ("step", "brep", "stl"):
        raise HTTPException(
            status_code=400,
            detail="Format must be one of: step, brep, stl",
        )

    ext = {"step": ".step", "brep": ".brep", "stl": ".stl"}[fmt]
    try:
        artifact = await asyncio.to_thread(export_code, request.code, fmt)
    except SandboxError as error:
        status = 408 if error.kind == "sandbox_timeout" else 400
        raise HTTPException(status_code=status, detail=str(error)) from error

    media_types = {
        "step": "application/step",
        "brep": "application/octet-stream",
        "stl": "model/stl",
    }
    filename = f"model{ext}"
    background_tasks.add_task(artifact.cleanup)
    logger.info("Exported model as %s", filename)
    return FileResponse(
        str(artifact.path),
        media_type=media_types[fmt],
        filename=filename,
    )


@app.post("/generate-mesh")
async def generate_mesh(
    request: GenerateMeshRequest,
    background_tasks: BackgroundTasks,
    _user: SandboxUserId,
):
    """Execute build123d code in the sandbox and return a GLB file."""
    try:
        artifact = await asyncio.to_thread(export_code, request.code, "glb")
    except SandboxError as error:
        status = 408 if error.kind == "sandbox_timeout" else 400
        raise HTTPException(status_code=status, detail=str(error)) from error

    background_tasks.add_task(artifact.cleanup)
    logger.info("Successfully generated GLB in sandbox")
    return FileResponse(
        str(artifact.path),
        media_type="model/gltf-binary",
        filename="model.glb",
    )
