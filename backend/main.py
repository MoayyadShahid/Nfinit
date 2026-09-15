import logging
import os
import re
import tempfile
import traceback
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv
from pydantic import BaseModel

from agent import (
    MAX_REPAIR_ATTEMPTS,
    CadRunRequest,
    CadRunResponse,
    ModelInspection,
    run_cad_agent,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).with_name(".env"))

app = FastAPI(title="Nfinit Geometry Engine")

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateMeshRequest(BaseModel):
    code: str


class ExportModelRequest(BaseModel):
    code: str
    format: str  # "step" | "brep" | "stl"


def _execute_code(code: str, scope: dict) -> object:
    """Execute build123d code and return the result shape."""
    if code.startswith("```"):
        code = re.sub(r"^```(?:python|py)?\s*\n?", "", code)
    if code.rstrip().endswith("```"):
        code = re.sub(r"\n?```\s*$", "", code).rstrip()

    exec(code, scope)

    result = scope.get("result")
    if result is None:
        result = (
            scope.get("part")
            or scope.get("final_shape")
            or scope.get("frame")
            or scope.get("assembly")
            or scope.get("body")
            or scope.get("model")
        )
    if result is None:
        values = [
            v
            for v in scope.values()
            if hasattr(v, "wrapped") and hasattr(v, "location")
        ]
        if values:
            result = values[-1]
        else:
            raise ValueError(
                "No 'result' variable found. Assign the final 3D part to a variable named 'result'."
            )

    if result.location is None:
        from build123d import Location
        result.location = Location()

    return result


def _build_scope():
    """Build the execution scope with build123d and aliases."""
    import build123d
    from build123d import Location
    from build123d.exporters3d import export_gltf, export_step, export_brep, export_stl

    scope = {"__builtins__": __builtins__}
    exports = getattr(build123d, "__all__", None) or [
        n for n in dir(build123d) if not n.startswith("_")
    ]
    for name in exports:
        scope[name] = getattr(build123d, name)
    scope["export_gltf"] = export_gltf
    scope["export_step"] = export_step
    scope["export_brep"] = export_brep
    scope["export_stl"] = export_stl

    ALIASES = {
        "regular_polygon": scope.get("RegularPolygon"),
        "make_polygon": scope.get("Polygon"),
        "create_polygon": scope.get("Polygon"),
        "make_regular_polygon": scope.get("RegularPolygon"),
        "create_regular_polygon": scope.get("RegularPolygon"),
        "cube": scope.get("Box"),
        "make_box": scope.get("Box"),
        "create_box": scope.get("Box"),
        "make_cylinder": scope.get("Cylinder"),
        "create_cylinder": scope.get("Cylinder"),
        "make_sphere": scope.get("Sphere"),
        "create_sphere": scope.get("Sphere"),
        "make_circle": scope.get("Circle"),
        "create_circle": scope.get("Circle"),
        "make_rectangle": scope.get("Rectangle"),
        "create_rectangle": scope.get("Rectangle"),
    }
    for alias, target in ALIASES.items():
        if alias and target is not None:
            scope[alias] = target

    return scope


def _inspect_code(code: str) -> ModelInspection:
    """Execute CAD code and return geometry facts."""
    try:
        scope = _build_scope()
        result = _execute_code(code.strip(), scope)
        bounding_box = result.bounding_box()
        size = bounding_box.size
        solids = result.solids() if hasattr(result, "solids") else []

        return ModelInspection(
            valid=True,
            shape_type=type(result).__name__,
            solid_count=len(solids),
            volume_mm3=round(float(result.volume), 3),
            bounding_box_mm={
                "x": round(float(size.X), 3),
                "y": round(float(size.Y), 3),
                "z": round(float(size.Z), 3),
            },
        )
    except Exception as e:
        logger.info("Model inspection failed: %s", e)
        return ModelInspection(valid=False, error=f"{type(e).__name__}: {str(e)}")


@app.post("/inspect-model", response_model=ModelInspection)
async def inspect_model(request: GenerateMeshRequest):
    """Execute CAD code and return geometry facts."""
    return _inspect_code(request.code)


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

    try:
        result = await run_cad_agent(request, api_key, _inspect_code)
    except Exception as e:
        logger.error("CAD agent failed: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"CAD agent failed: {str(e)}") from e

    if result["validation_error"]:
        return JSONResponse(
            status_code=422,
            content={
                "error": (
                    "The CAD agent could not produce valid geometry after "
                    f"{MAX_REPAIR_ATTEMPTS} repairs: {result['validation_error']}"
                ),
                "plan": result["plan"],
                "trace": result["trace"],
            },
        )

    return CadRunResponse(
        code=result["code"],
        plan=result["plan"],
        inspection=ModelInspection.model_validate(result["inspection"]),
        trace=result["trace"],
    )


@app.post("/export-model")
async def export_model(request: ExportModelRequest, background_tasks: BackgroundTasks):
    """Execute build123d code and return the model in the requested format (STEP, BREP, 3MF, STL)."""
    fmt = request.format.lower()
    if fmt not in ("step", "brep", "stl"):
        raise HTTPException(
            status_code=400,
            detail="Format must be one of: step, brep, stl",
        )

    try:
        from build123d.exporters3d import export_step, export_brep, export_stl
    except ImportError as e:
        logger.error("build123d import failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "build123d is not installed. Install it with: "
                "conda install -c conda-forge pythonocc-core && pip install build123d"
            ),
        ) from e

    scope = _build_scope()

    try:
        result = _execute_code(request.code.strip(), scope)
    except Exception as e:
        logger.error(
            "Code execution failed: %s\nTraceback:\n%s",
            e,
            traceback.format_exc(),
        )
        raise HTTPException(status_code=400, detail=f"Code execution failed: {str(e)}")

    temp_dir = tempfile.mkdtemp()
    ext = {"step": ".step", "brep": ".brep", "stl": ".stl"}[fmt]
    temp_path = Path(temp_dir) / f"model{ext}"

    try:
        if fmt == "step":
            success = export_step(result, str(temp_path))
        elif fmt == "brep":
            success = export_brep(result, str(temp_path))
        else:  # stl
            success = export_stl(result, str(temp_path))

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to export {fmt.upper()}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Export failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

    media_types = {
        "step": "application/step",
        "brep": "application/octet-stream",
        "stl": "model/stl",
    }
    filename = f"model{ext}"

    def cleanup():
        try:
            temp_path.unlink(missing_ok=True)
            Path(temp_dir).rmdir()
        except OSError:
            pass

    background_tasks.add_task(cleanup)
    logger.info("Exported model as %s", filename)
    return FileResponse(
        str(temp_path),
        media_type=media_types[fmt],
        filename=filename,
    )


@app.post("/generate-mesh")
async def generate_mesh(request: GenerateMeshRequest, background_tasks: BackgroundTasks):
    """Execute build123d code and return a GLB file."""
    try:
        from build123d.exporters3d import export_gltf
    except ImportError as e:
        logger.error("build123d import failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "build123d is not installed. Install it with: "
                "conda install -c conda-forge pythonocc-core && pip install build123d"
            ),
        ) from e

    scope = _build_scope()
    try:
        result = _execute_code(request.code.strip(), scope)
    except Exception as e:
        logger.error(
            "Code execution failed: %s\nCode:\n%s\nTraceback:\n%s",
            e,
            request.code[:500] + ("..." if len(request.code) > 500 else ""),
            traceback.format_exc(),
        )
        raise HTTPException(status_code=400, detail=f"Code execution failed: {str(e)}")

    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir) / "output.glb"

    try:
        success = export_gltf(result, str(temp_path), binary=True)
        if not success:
            logger.error("export_gltf returned False")
            raise HTTPException(status_code=500, detail="Failed to export GLB")
    except Exception as e:
        logger.error("Export failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

    def cleanup():
        try:
            temp_path.unlink(missing_ok=True)
            Path(temp_dir).rmdir()
        except OSError:
            pass

    background_tasks.add_task(cleanup)
    logger.info("Successfully generated GLB (result type: %s)", type(result).__name__)
    return FileResponse(
        str(temp_path),
        media_type="model/gltf-binary",
        filename="model.glb",
    )
