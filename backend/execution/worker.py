"""Isolated build123d worker.

This file is launched with Python's isolated mode and communicates only through
one JSON request on stdin and one JSON response on stdout.
"""

import contextlib
import hashlib
import json
import math
import os
import re
import resource
import socket
import sys
from collections import Counter
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

APPROVED_BUILD123D_NAMES = {
    "Add",
    "Align",
    "Axis",
    "Bezier",
    "Box",
    "BuildLine",
    "BuildPart",
    "BuildSketch",
    "CenterArc",
    "Circle",
    "Compound",
    "Cone",
    "CounterBoreHole",
    "CounterSinkHole",
    "Cylinder",
    "Edge",
    "Ellipse",
    "Face",
    "FilletPolyline",
    "GeomType",
    "GridLocations",
    "Helix",
    "HexLocations",
    "Hole",
    "Keep",
    "Kind",
    "Line",
    "Location",
    "Locations",
    "Mode",
    "Part",
    "Plane",
    "PolarLine",
    "PolarLocations",
    "Polygon",
    "Polyline",
    "Pos",
    "RadiusArc",
    "Rectangle",
    "RectangleRounded",
    "RegularPolygon",
    "Rot",
    "Rotation",
    "SagittaArc",
    "Select",
    "SlotArc",
    "SlotCenterPoint",
    "SlotCenterToCenter",
    "SlotOverall",
    "Solid",
    "SortBy",
    "Sphere",
    "Spline",
    "TangentArc",
    "Text",
    "ThreePointArc",
    "Torus",
    "Transition",
    "Trapezoid",
    "Triangle",
    "Until",
    "Vector",
    "Wedge",
    "Wire",
    "add",
    "chamfer",
    "draft",
    "extrude",
    "fillet",
    "full_round",
    "loft",
    "make_face",
    "make_hull",
    "mirror",
    "offset",
    "revolve",
    "scale",
    "section",
    "split",
    "sweep",
    "trace",
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

    original_socket = socket.socket

    class DeniedSocket(original_socket):
        def __new__(cls, *_args, **_kwargs):
            raise PermissionError("Network access is disabled in the CAD sandbox.")

    socket.socket = DeniedSocket
    socket.create_connection = denied


def _build_scope():
    import build123d
    from build123d import Location

    scope = {"__builtins__": SAFE_BUILTINS}
    feature_records = []
    for name in APPROVED_BUILD123D_NAMES:
        if hasattr(build123d, name):
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

    def register_feature(
        feature_id,
        name,
        operation,
        shape,
        parent_id=None,
        parameters=None,
    ):
        if not isinstance(feature_id, str) or not re.fullmatch(
            r"[a-z][a-z0-9_]{0,63}", feature_id
        ):
            raise ValueError(
                "Feature IDs must use lowercase letters, numbers, and underscores."
            )
        if any(record["id"] == feature_id for record in feature_records):
            raise ValueError(f"Feature ID '{feature_id}' is duplicated.")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("Feature names must contain 1 to 120 characters.")
        allowed_operations = {
            "additive",
            "subtractive",
            "pattern",
            "fillet",
            "chamfer",
            "transform",
            "reference",
            "other",
        }
        if operation not in allowed_operations:
            raise ValueError(f"Unsupported feature operation '{operation}'.")
        known_ids = {record["id"] for record in feature_records}
        if parent_id is not None and parent_id not in known_ids:
            raise ValueError(
                f"Feature parent '{parent_id}' must be registered first."
            )
        if hasattr(shape, "part"):
            shape = shape.part
        if not hasattr(shape, "faces"):
            raise ValueError("Feature snapshots require a build123d shape.")
        parameters = parameters or {}
        try:
            encoded_parameters = json.dumps(
                parameters, sort_keys=True, separators=(",", ":")
            )
        except (TypeError, ValueError) as error:
            raise ValueError("Feature parameters must be JSON serializable.") from error
        if len(encoded_parameters.encode("utf-8")) > 4096:
            raise ValueError("Feature parameters may not exceed 4096 bytes.")
        feature_records.append(
            {
                "id": feature_id,
                "name": name.strip(),
                "operation": operation,
                "parentId": parent_id,
                "parameters": json.loads(encoded_parameters),
                "face_signatures": _snapshot_face_signatures(shape),
            }
        )

    scope["register_feature"] = register_feature
    return scope, feature_records


def _execute(code: str):
    scope, feature_records = _build_scope()
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
    return result, feature_records


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


def _vector(value, digits: int = 6):
    return [round(float(component), digits) for component in value]


def _bounds(shape):
    bounds = shape.bounding_box()
    return {
        "minimum": _vector(bounds.min),
        "maximum": _vector(bounds.max),
    }


def _edge_geometry(edge):
    return {
        "curve_type": edge.geom_type.name.lower(),
        "length_mm": round(float(edge.length), 6),
        "center_mm": _vector(edge.center()),
        "bounds_mm": _bounds(edge),
    }


def _face_snapshot_signature(face):
    edge_signatures = sorted(
        json.dumps(
            _edge_geometry(edge),
            sort_keys=True,
            separators=(",", ":"),
        )
        for edge in face.edges()
    )
    payload = {
        "surface_type": face.geom_type.name.lower(),
        "area_mm2": round(float(face.area), 6),
        "center_mm": _vector(face.center()),
        "normal": _vector(face.normal_at()),
        "bounds_mm": _bounds(face),
        "edges": edge_signatures,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _snapshot_face_signatures(shape):
    return sorted(_face_snapshot_signature(face) for face in shape.faces())


def _entity_id(prefix: str, payload: dict, occurrence: int = 0):
    canonical = json.dumps(
        {"geometry": payload, "occurrence": occurrence},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _feature_tree(feature_records, face_records):
    final_faces = {}
    for record in face_records:
        final_faces.setdefault(record["ownership_signature"], []).append(
            record["payload"]["id"]
        )
    for face_ids in final_faces.values():
        face_ids.sort()

    assigned = set()
    previous = Counter()
    features = []
    for index, record in enumerate(feature_records):
        current = Counter(record["face_signatures"])
        introduced = current - previous
        owned_face_ids = []
        for signature, count in sorted(introduced.items()):
            candidates = [
                face_id
                for face_id in final_faces.get(signature, [])
                if face_id not in assigned
            ]
            owned_face_ids.extend(candidates[:count])
        assigned.update(owned_face_ids)
        features.append(
            {
                "id": record["id"],
                "name": record["name"],
                "operation": record["operation"],
                "parentId": record["parentId"],
                "parameters": record["parameters"],
                "sequence": index,
                "ownedFaceIds": sorted(owned_face_ids),
            }
        )
        previous = current

    all_face_ids = {record["payload"]["id"] for record in face_records}
    return features, sorted(all_face_ids - assigned)


def _topology(result, selection=None, feature_records=None):
    edge_records = []
    for edge in result.edges():
        payload = _edge_geometry(edge)
        signature = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        edge_records.append({"shape": edge, "payload": payload, "signature": signature})

    occurrences = {}
    for record in sorted(edge_records, key=lambda item: item["signature"]):
        occurrence = occurrences.get(record["signature"], 0)
        occurrences[record["signature"]] = occurrence + 1
        record["payload"]["id"] = _entity_id(
            "edge", record["payload"], occurrence
        )

    face_records = []
    for face in result.faces():
        edge_ids = sorted(
            record["payload"]["id"]
            for face_edge in face.edges()
            for record in edge_records
            if record["shape"].is_same(face_edge)
        )
        payload = {
            "surface_type": face.geom_type.name.lower(),
            "area_mm2": round(float(face.area), 6),
            "center_mm": _vector(face.center()),
            "normal": _vector(face.normal_at()),
            "bounds_mm": _bounds(face),
            "edge_ids": edge_ids,
        }
        signature = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        ownership_signature = _face_snapshot_signature(face)
        face_records.append(
            {
                "shape": face,
                "payload": payload,
                "signature": signature,
                "ownership_signature": ownership_signature,
            }
        )

    occurrences = {}
    for record in sorted(face_records, key=lambda item: item["signature"]):
        occurrence = occurrences.get(record["signature"], 0)
        occurrences[record["signature"]] = occurrence + 1
        record["payload"]["id"] = _entity_id(
            "face", record["payload"], occurrence
        )

    edges = sorted(
        (record["payload"] for record in edge_records),
        key=lambda item: item["id"],
    )
    faces = sorted(
        (record["payload"] for record in face_records),
        key=lambda item: item["id"],
    )
    topology_version = hashlib.sha256(
        json.dumps(
            {
                "edges": [edge["id"] for edge in edges],
                "faces": [face["id"] for face in faces],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:20]
    features, unassigned_face_ids = _feature_tree(
        feature_records or [], face_records
    )

    selected_face = None
    if selection and face_records:
        point = tuple(float(value) for value in selection["point"])
        supplied_normal = tuple(float(value) for value in selection["normal"])
        normal_length = math.sqrt(sum(value * value for value in supplied_normal))
        if normal_length == 0:
            raise ValueError("Selection normal must be non-zero.")
        supplied_normal = tuple(value / normal_length for value in supplied_normal)
        bounds = result.bounding_box()
        diagonal = math.dist(tuple(bounds.min), tuple(bounds.max))
        matches = []
        for record in face_records:
            face = record["shape"]
            distance = float(face.distance_to(point))
            surface_point = face.closest_points(point)[0]
            normal = tuple(face.normal_at(surface_point))
            normal_alignment = max(
                -1.0,
                min(
                    1.0,
                    sum(
                        normal[index] * supplied_normal[index]
                        for index in range(3)
                    ),
                ),
            )
            score = distance / max(diagonal, 1.0) + (1.0 - normal_alignment) * 0.5
            matches.append((score, distance, normal_alignment, record))

        _, distance, normal_alignment, record = min(
            matches, key=lambda match: (match[0], match[3]["payload"]["id"])
        )
        if distance <= max(2.0, diagonal * 0.05) and normal_alignment > 0:
            tolerance = max(0.1, diagonal * 0.005)
            confidence = normal_alignment / (1.0 + distance / tolerance)
            selected_face = {
                "faceId": record["payload"]["id"],
                "surfaceType": record["payload"]["surface_type"],
                "distanceMm": round(distance, 6),
                "normalAlignment": round(normal_alignment, 6),
                "confidence": round(max(0.0, min(1.0, confidence)), 4),
            }

    return {
        "valid": True,
        "topologyVersion": topology_version,
        "faces": faces,
        "edges": edges,
        "features": features,
        "unassignedFaceIds": unassigned_face_ids,
        "selectedFace": selected_face,
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
    result, feature_records = _execute(request["code"])
    operation = request["operation"]
    if operation == "inspect":
        data = _inspect(result)
    elif operation == "topology":
        data = _topology(
            result,
            request.get("selection"),
            feature_records=feature_records,
        )
    else:
        data = _export(result, operation, request["output_name"])
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
