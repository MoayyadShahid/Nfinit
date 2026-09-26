import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from agent import (
    MAX_REPAIR_ATTEMPTS,
    CadRunRequest,
    CadRunResponse,
    FaceSelection,
    ModelInspection,
    flush_tracing,
    run_cad_agent,
)
from execution import (
    SandboxError,
    RevisionComparison,
    TopologyAnalysis,
    analyze_code,
    compare_code,
    export_code,
    inspect_code as sandbox_inspect_code,
)
from projects import router as projects_router
from projects.config import validate_project_configuration

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).with_name(".env"))


def _optional_service_status() -> dict[str, str]:
    langfuse = (
        "enabled"
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
        else "disabled (optional)"
    )
    pinecone = (
        "enabled"
        if os.getenv("PINECONE_API_KEY")
        and (os.getenv("PINECONE_INDEX_HOST") or os.getenv("PINECONE_INDEX_NAME"))
        else "local corpus (optional cloud RAG unset)"
    )
    supabase = (
        "configured"
        if os.getenv("SUPABASE_URL") or os.getenv("NFNIT_DATABASE_URL")
        else "unset (SQLite + local auth bypass)"
    )
    return {
        "openrouter": "configured" if os.getenv("OPENROUTER_API_KEY") else "MISSING",
        "langfuse": langfuse,
        "pinecone": pinecone,
        "supabase": supabase,
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_project_configuration()
    for name, status in _optional_service_status().items():
        logger.info("Service %s: %s", name, status)
    yield
    flush_tracing()


app = FastAPI(title="Nfinit Geometry Engine", lifespan=lifespan)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(projects_router)


@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok", "services": _optional_service_status()}


class GenerateMeshRequest(BaseModel):
    code: str


class ExportModelRequest(BaseModel):
    code: str
    format: str  # "step" | "brep" | "stl"


class AnalyzeModelRequest(BaseModel):
    code: str
    selection: FaceSelection | None = None


class CompareModelsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    previous_code: str = Field(alias="previousCode")
    current_code: str = Field(alias="currentCode")
    previous_face_id: str | None = Field(default=None, alias="previousFaceId")


def _inspect_code(code: str) -> ModelInspection:
    """Execute CAD code in the sandbox and return geometry facts."""
    return sandbox_inspect_code(code)


@app.post("/inspect-model", response_model=ModelInspection)
async def inspect_model(request: GenerateMeshRequest):
    """Execute CAD code and return geometry facts."""
    return _inspect_code(request.code)


@app.post("/analyze-model", response_model=TopologyAnalysis)
async def analyze_model(request: AnalyzeModelRequest):
    """Index B-rep entities and optionally resolve a geometric face selection."""
    return analyze_code(request.code, request.selection)


@app.post("/compare-models", response_model=RevisionComparison)
def compare_models(request: CompareModelsRequest):
    """Match semantic features, constraints, and faces across two revisions."""
    return compare_code(
        request.previous_code,
        request.current_code,
        previous_face_id=request.previous_face_id,
    )


@app.post("/cad/run", response_model=CadRunResponse)
async def cad_run(request: CadRunRequest):
    """Plan, generate, execute, and repair a CAD request through LangGraph."""
    if not request.messages or request.messages[-1].role != "user":
        raise HTTPException(
            status_code=400,
            detail="A non-empty message list ending with a user message is required.",
        )

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY is not configured on the backend.",
        )

    run_id = str(uuid4())
    try:
        result = await run_cad_agent(request, api_key, _inspect_code, run_id=run_id)
    except Exception as e:
        logger.error("CAD agent run %s failed: %s", run_id, e, exc_info=True)
        return JSONResponse(
            status_code=502,
            headers={"X-Run-ID": run_id},
            content={"error": f"CAD agent failed: {str(e)}", "runId": run_id},
        )

    if result["validation_error"]:
        return JSONResponse(
            status_code=422,
            headers={"X-Run-ID": run_id},
            content={
                "error": (
                    "The CAD agent could not produce valid geometry after "
                    f"{MAX_REPAIR_ATTEMPTS} repairs: {result['validation_error']}"
                ),
                "plan": result["plan"],
                "trace": result["trace"],
                "runId": run_id,
                "usage": result["usage"],
            },
        )

    return CadRunResponse(
        run_id=run_id,
        code=result["code"],
        plan=result["plan"],
        inspection=ModelInspection.model_validate(result["inspection"]),
        trace=result["trace"],
        usage=result["usage"],
    )


@app.post("/export-model")
async def export_model(request: ExportModelRequest, background_tasks: BackgroundTasks):
    """Execute build123d code in the sandbox and export the requested format."""
    fmt = request.format.lower()
    if fmt not in ("step", "brep", "stl"):
        raise HTTPException(
            status_code=400,
            detail="Format must be one of: step, brep, stl",
        )

    ext = {"step": ".step", "brep": ".brep", "stl": ".stl"}[fmt]
    try:
        artifact = export_code(request.code, fmt)
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
async def generate_mesh(request: GenerateMeshRequest, background_tasks: BackgroundTasks):
    """Execute build123d code in the sandbox and return a GLB file."""
    try:
        artifact = export_code(request.code, "glb")
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
