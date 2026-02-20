import logging
import re
import tempfile
import traceback
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Nfinit Geometry Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
        "regular_polygon": scope.get("Polygon"),
        "make_polygon": scope.get("Polygon"),
        "create_polygon": scope.get("Polygon"),
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
