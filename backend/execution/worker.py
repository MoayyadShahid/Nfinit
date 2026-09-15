"""Isolated build123d worker.

This file is launched with Python's isolated mode and communicates only through
one JSON request on stdin and one JSON response on stdout.
"""

import contextlib
import json
import os
import resource
import socket
import sys
from pathlib import Path


SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "pow": pow,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


def _apply_resource_limits():
    cpu_seconds = int(os.environ.get("CAD_SANDBOX_CPU_SECONDS", "10"))
    memory_bytes = int(os.environ.get("CAD_SANDBOX_MEMORY_BYTES", str(2 * 1024**3)))
    file_bytes = int(os.environ.get("CAD_SANDBOX_FILE_BYTES", str(256 * 1024**2)))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


def _disable_network():
    def denied(*_args, **_kwargs):
        raise PermissionError("Network access is disabled in the CAD sandbox.")

    socket.socket = denied
    socket.create_connection = denied


def _build_scope():
    import build123d
    from build123d import Location

    scope = {"__builtins__": SAFE_BUILTINS}
    names = getattr(build123d, "__all__", None) or [
        name for name in dir(build123d) if not name.startswith("_")
    ]
    for name in names:
        if not name.lower().startswith(("export", "import", "load", "save", "write")):
            scope[name] = getattr(build123d, name)

    aliases = {
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
    scope.update({name: value for name, value in aliases.items() if value is not None})
    scope["Location"] = Location
    return scope


def _execute(code: str):
    scope = _build_scope()
    with contextlib.redirect_stdout(sys.stderr):
        exec(compile(code, "<generated-cad>", "exec"), scope)

    result = next(
        (
            scope.get(name)
            for name in (
                "result",
                "part",
                "final_shape",
                "frame",
                "assembly",
                "body",
                "model",
            )
            if scope.get(name) is not None
        ),
        None,
    )
    if hasattr(result, "part"):
        result = result.part
    if result is None:
        raise ValueError("No final shape was assigned to 'result'.")
    if getattr(result, "location", None) is None:
        from build123d import Location

        result.location = Location()
    return result


def _inspect(result):
    bounds = result.bounding_box().size
    solids = result.solids() if hasattr(result, "solids") else []
    return {
        "valid": True,
        "shape_type": type(result).__name__,
        "solid_count": len(solids),
        "volume_mm3": round(float(result.volume), 3),
        "bounding_box_mm": {
            "x": round(float(bounds.X), 3),
            "y": round(float(bounds.Y), 3),
            "z": round(float(bounds.Z), 3),
        },
        "error": None,
    }


def _export(result, operation: str, output_name: str):
    from build123d.exporters3d import export_brep, export_gltf, export_step, export_stl

    output_path = (Path.cwd() / output_name).resolve()
    if output_path.parent != Path.cwd().resolve():
        raise PermissionError("Output path must stay inside the sandbox directory.")

    if operation == "glb":
        success = export_gltf(result, str(output_path), binary=True)
    elif operation == "step":
        success = export_step(result, str(output_path))
    elif operation == "brep":
        success = export_brep(result, str(output_path))
    elif operation == "stl":
        success = export_stl(result, str(output_path))
    else:
        raise ValueError(f"Unsupported operation: {operation}")

    if not success or not output_path.is_file():
        raise RuntimeError(f"Failed to export {operation.upper()}.")
    return {"bytes": output_path.stat().st_size}


def main():
    os.umask(0o077)
    _apply_resource_limits()
    request = json.loads(sys.stdin.read())
    _disable_network()
    result = _execute(request["code"])
    operation = request["operation"]
    data = (
        _inspect(result)
        if operation == "inspect"
        else _export(result, operation, request["output_name"])
    )
    print(json.dumps({"ok": True, "data": data}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "type": type(error).__name__,
                        "message": str(error),
                    },
                }
            ),
            flush=True,
        )
        raise SystemExit(1)
