"""Isolated build123d worker.

This file is launched with Python's isolated mode. It runs in one of two ways:

- One-shot: one JSON request on stdin and one JSON response on stdout.
- Fork server (``serve <socket>``): import build123d once, then fork one fresh
  child per job from that clean process. A child serves exactly one
  connection and exits, so no state leaks from one job into the next.
"""

import contextlib
import hashlib
import json
import math
import os
import re
import resource
import select
import signal
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
MAX_SEMANTIC_FEATURES = 64
MAX_SEMANTIC_CONSTRAINTS = 128


def _set_limit(resource_id: int, soft: int, hard: int | None = None) -> None:
    """Apply a rlimit when the host allows it.

    Docker, CI, and some macOS sandboxes reject raising a hard ceiling.
    Skip that limit instead of crashing the worker or clamping it so
    tightly that OpenCASCADE hangs.
    """
    hard = soft if hard is None else hard
    try:
        _current_soft, current_hard = resource.getrlimit(resource_id)
    except (OSError, ValueError):
        return
    if current_hard != resource.RLIM_INFINITY and hard > current_hard:
        return
    try:
        resource.setrlimit(resource_id, (min(soft, hard), hard))
    except (OSError, ValueError, PermissionError):
        return


def _apply_resource_limits():
    # Fillets and booleans on detailed parts can need well over 10 CPU-seconds;
    # a legitimate model killed here would be "repaired" at the model's expense.
    cpu_seconds = int(os.environ.get("CAD_SANDBOX_CPU_SECONDS", "45"))
    memory_bytes = int(os.environ.get("CAD_SANDBOX_MEMORY_BYTES", str(2 * 1024**3)))
    file_bytes = int(os.environ.get("CAD_SANDBOX_FILE_BYTES", str(256 * 1024**2)))
    _set_limit(resource.RLIMIT_CPU, cpu_seconds, cpu_seconds + 1)
    _set_limit(resource.RLIMIT_AS, memory_bytes)
    _set_limit(resource.RLIMIT_FSIZE, file_bytes)
    _set_limit(resource.RLIMIT_NOFILE, 128)


# The unprivileged account jobs run as when the server runs as root.
SANDBOX_UID = int(os.environ.get("CAD_SANDBOX_UID", "65534"))
SANDBOX_GID = int(os.environ.get("CAD_SANDBOX_GID", "65534"))
# Processes the sandbox account may own at once, threads included. It must
# leave room for OpenCASCADE's thread pool in every concurrent job, and stops a
# fork bomb.
SANDBOX_MAX_PROCESSES = int(os.environ.get("CAD_SANDBOX_MAX_PROCESSES", "256"))


def _prctl(option: int, value: int) -> None:
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(option, value, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), f"prctl({option}) failed")


def _drop_privileges(work_dir: Path) -> None:
    """Run the job as an unprivileged account when the server runs as root.

    The policy check is the first barrier; this one limits what an escape
    from it can do. As "nobody" the job cannot read the server's environment
    (where the secrets are) through /proc, cannot change the app's files, and
    cannot read or write other jobs' directories (each is private to root
    until its own job takes it). Not "dumpable", it is also hidden from other
    jobs running as the same account.
    """
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return  # Local development: already unprivileged.
    try:
        for path in (work_dir, *work_dir.iterdir()):
            os.chown(path, SANDBOX_UID, SANDBOX_GID)
        if sys.platform.startswith("linux"):
            _prctl(38, 1)  # PR_SET_NO_NEW_PRIVS: setuid binaries gain nothing.
        os.setgroups([])
        os.setgid(SANDBOX_GID)
        os.setuid(SANDBOX_UID)
        if sys.platform.startswith("linux"):
            _prctl(4, 0)  # PR_SET_DUMPABLE: no /proc access from other jobs.
    except OSError as error:
        if os.environ.get("CAD_SANDBOX_ALLOW_ROOT", "").lower() in {"1", "true", "yes"}:
            return
        # Fail closed: running untrusted code as root is worse than no job.
        raise PermissionError(
            f"The CAD sandbox could not drop root privileges: {error}"
        ) from error
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("The CAD sandbox is still running as root.")
    _set_limit(resource.RLIMIT_NPROC, SANDBOX_MAX_PROCESSES)


def _disable_network():
    def denied(*_args, **_kwargs):
        raise PermissionError("Network access is disabled in the CAD sandbox.")

    original_socket = socket.socket

    class DeniedSocket(original_socket):
        def __new__(cls, *_args, **_kwargs):
            raise PermissionError("Network access is disabled in the CAD sandbox.")

    socket.socket = DeniedSocket
    socket.create_connection = denied


def _json_parameters(parameters, label):
    parameters = parameters or {}
    if not isinstance(parameters, dict):
        raise ValueError(f"{label} parameters must be a dictionary.")
    try:
        encoded = json.dumps(
            parameters,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{label} parameters must be finite JSON values."
        ) from error
    if len(encoded.encode("utf-8")) > 4096:
        raise ValueError(f"{label} parameters may not exceed 4096 bytes.")
    return json.loads(encoded)


def _build_scope():
    import build123d
    from build123d import Location

    scope = {"__builtins__": SAFE_BUILTINS}
    feature_records = []
    constraint_records = []
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
        if len(feature_records) >= MAX_SEMANTIC_FEATURES:
            raise ValueError(
                f"CAD scripts may register at most {MAX_SEMANTIC_FEATURES} features."
            )
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
        encoded_parameters = _json_parameters(parameters, "Feature")
        feature_records.append(
            {
                "id": feature_id,
                "name": name.strip(),
                "operation": operation,
                "parentId": parent_id,
                "parameters": encoded_parameters,
                "face_signatures": _snapshot_face_signatures(shape),
                "surface_keys": _snapshot_surface_keys(shape),
                # Shapes are immutable; later operations make new ones.
                "shape": shape,
            }
        )

    def register_constraint(
        constraint_id,
        kind,
        feature_ids,
        parameters=None,
    ):
        if len(constraint_records) >= MAX_SEMANTIC_CONSTRAINTS:
            raise ValueError(
                "CAD scripts may register at most "
                f"{MAX_SEMANTIC_CONSTRAINTS} constraints."
            )
        if not isinstance(constraint_id, str) or not re.fullmatch(
            r"[a-z][a-z0-9_]{0,63}", constraint_id
        ):
            raise ValueError(
                "Constraint IDs must use lowercase letters, numbers, and underscores."
            )
        if any(record["id"] == constraint_id for record in constraint_records):
            raise ValueError(f"Constraint ID '{constraint_id}' is duplicated.")
        allowed_kinds = {
            "distance",
            "angle",
            "radius",
            "diameter",
            "thickness",
            "count",
            "equal",
            "symmetry",
            "concentric",
            "coincident",
            "parallel",
            "perpendicular",
            "fixed",
            "other",
        }
        if kind not in allowed_kinds:
            raise ValueError(f"Unsupported constraint kind '{kind}'.")
        if (
            not isinstance(feature_ids, (list, tuple))
            or not feature_ids
            or len(feature_ids) > 8
            or any(not isinstance(value, str) for value in feature_ids)
        ):
            raise ValueError(
                "Constraint feature IDs must be a list of 1 to 8 feature IDs."
            )
        if len(set(feature_ids)) != len(feature_ids):
            raise ValueError(
                "Constraint feature IDs must not contain duplicates."
            )
        feature_ids = list(feature_ids)
        known_ids = {record["id"] for record in feature_records}
        unknown_ids = sorted(set(feature_ids) - known_ids)
        if unknown_ids:
            raise ValueError(
                "Constraint features must be registered first; unknown IDs: "
                + ", ".join(unknown_ids)
            )
        pair_kinds = {
            "equal",
            "concentric",
            "coincident",
            "parallel",
            "perpendicular",
        }
        if kind in pair_kinds and len(feature_ids) < 2:
            raise ValueError(
                f"Constraint kind '{kind}' requires at least two features."
            )
        encoded_parameters = _json_parameters(parameters, "Constraint")
        dimensional_kinds = {
            "distance",
            "angle",
            "radius",
            "diameter",
            "thickness",
            "count",
        }
        if kind in dimensional_kinds:
            value = encoded_parameters.get("value")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(
                    f"Constraint kind '{kind}' requires a finite numeric value."
                )
            if kind == "count":
                if not isinstance(value, int) or value < 1:
                    raise ValueError(
                        "Count constraints require a positive integer value."
                    )
            elif kind in {"radius", "diameter", "thickness"} and value <= 0:
                raise ValueError(
                    f"Constraint kind '{kind}' requires a positive value."
                )
        constraint_records.append(
            {
                "id": constraint_id,
                "kind": kind,
                "featureIds": feature_ids,
                "parameters": encoded_parameters,
            }
        )

    scope["register_feature"] = register_feature
    scope["register_constraint"] = register_constraint
    return scope, feature_records, constraint_records


def _execute(code: str):
    scope, feature_records, constraint_records = _build_scope()
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
    return result, feature_records, constraint_records


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


def _canonical_direction(direction):
    """A unit vector with one sign for both directions along the same line."""
    values = [float(component) for component in direction]
    for value in values:
        if abs(value) > 1e-9:
            if value < 0:
                values = [-component for component in values]
            break
    return values


def _rounded(values, digits: int = 4):
    # Adding 0.0 turns -0.0 into 0.0, so equal surfaces give equal keys.
    return [round(value, digits) + 0.0 for value in values]


def _surface_key(face):
    """The surface a face lies on, or None when it cannot be described simply.

    A later feature can reshape a face's outline (a fillet rounds its corners,
    a hole cuts through it) while the face stays on the same plane or
    cylinder. The key ignores the outline, so the face keeps the feature that
    first created it.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import (
        GeomAbs_Cone,
        GeomAbs_Cylinder,
        GeomAbs_Plane,
        GeomAbs_Sphere,
        GeomAbs_Torus,
    )

    def axis_key(axis):
        direction = _canonical_direction(
            (axis.Direction().X(), axis.Direction().Y(), axis.Direction().Z())
        )
        location = axis.Location()
        point = (location.X(), location.Y(), location.Z())
        along = sum(point[index] * direction[index] for index in range(3))
        # The point on the axis closest to the origin names the axis.
        closest = [point[index] - along * direction[index] for index in range(3)]
        return _rounded(direction, 6) + _rounded(closest)

    surface = BRepAdaptor_Surface(face.wrapped)
    kind = surface.GetType()
    if kind == GeomAbs_Plane:
        normal = [float(value) for value in face.normal_at()]
        center = [float(value) for value in face.center()]
        offset = sum(normal[index] * center[index] for index in range(3))
        # Oriented: the top and bottom of a sheet are different faces.
        return ("plane", *_rounded(normal, 6), *_rounded([offset]))
    if kind == GeomAbs_Cylinder:
        cylinder = surface.Cylinder()
        return ("cylinder", *axis_key(cylinder.Axis()), *_rounded([cylinder.Radius()]))
    if kind == GeomAbs_Cone:
        cone = surface.Cone()
        apex = cone.Apex()
        return (
            "cone",
            *axis_key(cone.Axis()),
            *_rounded([apex.X(), apex.Y(), apex.Z(), cone.SemiAngle()]),
        )
    if kind == GeomAbs_Sphere:
        sphere = surface.Sphere()
        center = sphere.Location()
        return ("sphere", *_rounded([center.X(), center.Y(), center.Z(), sphere.Radius()]))
    if kind == GeomAbs_Torus:
        torus = surface.Torus()
        return (
            "torus",
            *axis_key(torus.Axis()),
            *_rounded([torus.MajorRadius(), torus.MinorRadius()]),
        )
    return None


def _snapshot_surface_keys(shape):
    return {key for key in (_surface_key(face) for face in shape.faces()) if key}


def _entity_id(prefix: str, payload: dict, occurrence: int = 0):
    canonical = json.dumps(
        {"geometry": payload, "occurrence": occurrence},
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _feature_tree(feature_records, face_records):
    """Give each final face to the feature that first created it.

    A face belongs to the first feature whose snapshot already has a face on
    the same surface (plane, cylinder, ...), even if later features reshaped
    its outline. Faces on surfaces without a simple key (splines, lofts) fall
    back to the exact face signature: the feature that last produced exactly
    this face. Faces that no snapshot explains stay unassigned.
    """
    owners: dict[str, int] = {}
    for record in face_records:
        key = record["surface_key"]
        if key is None:
            continue
        index = next(
            (
                index
                for index, feature in enumerate(feature_records)
                if key in feature["surface_keys"]
            ),
            None,
        )
        if index is not None:
            owners[record["payload"]["id"]] = index

    final_faces = {}
    for record in face_records:
        if record["payload"]["id"] in owners:
            continue
        final_faces.setdefault(record["ownership_signature"], []).append(
            record["payload"]["id"]
        )
    for face_ids in final_faces.values():
        face_ids.sort()

    assigned = set(owners)
    previous = Counter()
    for index, record in enumerate(feature_records):
        current = Counter(record["face_signatures"])
        introduced = current - previous
        for signature, count in sorted(introduced.items()):
            candidates = [
                face_id
                for face_id in final_faces.get(signature, [])
                if face_id not in assigned
            ]
            for face_id in candidates[:count]:
                owners[face_id] = index
                assigned.add(face_id)
        previous = current

    features = []
    for index, record in enumerate(feature_records):
        features.append(
            {
                "id": record["id"],
                "name": record["name"],
                "operation": record["operation"],
                "parentId": record["parentId"],
                "parameters": record["parameters"],
                "sequence": index,
                "ownedFaceIds": sorted(
                    face_id for face_id, owner in owners.items() if owner == index
                ),
            }
        )

    all_face_ids = {record["payload"]["id"] for record in face_records}
    return features, sorted(all_face_ids - assigned)


def _entity_records(result):
    """Index the shape's edges and faces with content-addressed IDs."""
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
                "surface_key": _surface_key(face),
            }
        )

    occurrences = {}
    for record in sorted(face_records, key=lambda item: item["signature"]):
        occurrence = occurrences.get(record["signature"], 0)
        occurrences[record["signature"]] = occurrence + 1
        record["payload"]["id"] = _entity_id(
            "face", record["payload"], occurrence
        )
    return edge_records, face_records


def _topology(
    result,
    selection=None,
    feature_records=None,
    constraint_records=None,
    entity_records=None,
):
    edge_records, face_records = entity_records or _entity_records(result)
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
    constraints = [
        {**record, "sequence": index}
        for index, record in enumerate(constraint_records or [])
    ]

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
        "constraints": constraints,
        "unassignedFaceIds": unassigned_face_ids,
        "selectedFace": selected_face,
        "error": None,
    }


VIEWER_FORMAT = "nfinit-brep-2"
# glTF is Y-up; CAD is Z-up. Same root rotation as build123d's exporter.
Z_UP_TO_Y_UP = [-0.7071067811865475, 0.0, 0.0, 0.7071067811865475]
MM_TO_M = 0.001


def _face_mesh(face):
    """Positions (m), normals and triangle indices of one meshed face."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepLib import BRepLib_ToolTriangulatedShape
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location

    location = TopLoc_Location()
    triangulation = BRep_Tool.Triangulation_s(face.wrapped, location)
    if triangulation is None or triangulation.NbTriangles() == 0:
        return None
    reversed_face = face.wrapped.Orientation() == TopAbs_REVERSED
    transform = location.Transformation()
    BRepLib_ToolTriangulatedShape.ComputeNormals_s(face.wrapped, triangulation)
    positions, normals, indices = [], [], []
    sign = -1.0 if reversed_face else 1.0
    for index in range(1, triangulation.NbNodes() + 1):
        point = triangulation.Node(index).Transformed(transform)
        positions += [point.X() * MM_TO_M, point.Y() * MM_TO_M, point.Z() * MM_TO_M]
        normal = triangulation.Normal(index).Transformed(transform)
        normals += [normal.X() * sign, normal.Y() * sign, normal.Z() * sign]
    for index in range(1, triangulation.NbTriangles() + 1):
        a, b, c = triangulation.Triangle(index).Get()
        indices += [a - 1, c - 1, b - 1] if reversed_face else [a - 1, b - 1, c - 1]
    return positions, normals, indices


def _edge_segments(edge, angular: float, linear: float):
    """Line segments (pairs of points, m) that trace one B-rep edge."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_TangentialDeflection

    sampler = GCPnts_TangentialDeflection(BRepAdaptor_Curve(edge.wrapped), angular, linear)
    points = [sampler.Value(index) for index in range(1, sampler.NbPoints() + 1)]
    segments = []
    for start, end in zip(points, points[1:]):
        segments += [
            start.X() * MM_TO_M, start.Y() * MM_TO_M, start.Z() * MM_TO_M,
            end.X() * MM_TO_M, end.Y() * MM_TO_M, end.Z() * MM_TO_M,
        ]
    return segments


def _write_viewer_glb(path: Path, faces, edge_segments, scene_extras):
    """Write one glTF node per face and one line node for all edges."""
    import struct

    import numpy

    buffer = bytearray()
    buffer_views, accessors = [], []

    def add_accessor(values, dtype, component_type, kind, target, bounds=False):
        data = numpy.asarray(values, dtype=dtype)
        while len(buffer) % 4:
            buffer.append(0)
        offset = len(buffer)
        buffer.extend(data.tobytes())
        buffer_views.append(
            {"buffer": 0, "byteOffset": offset, "byteLength": data.nbytes, "target": target}
        )
        width = {"SCALAR": 1, "VEC3": 3}[kind]
        accessor = {
            "bufferView": len(buffer_views) - 1,
            "componentType": component_type,
            "count": len(data) // width,
            "type": kind,
        }
        if bounds:
            grid = data.reshape(-1, 3)
            accessor["min"] = grid.min(axis=0).tolist()
            accessor["max"] = grid.max(axis=0).tolist()
        accessors.append(accessor)
        return len(accessors) - 1

    meshes, nodes = [], []
    for face in faces:
        positions, normals, indices = face["mesh"]
        meshes.append(
            {
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": add_accessor(positions, "<f4", 5126, "VEC3", 34962, True),
                            "NORMAL": add_accessor(normals, "<f4", 5126, "VEC3", 34962),
                        },
                        "indices": add_accessor(indices, "<u4", 5125, "SCALAR", 34963),
                        "material": 0,
                    }
                ]
            }
        )
        nodes.append({"name": face["id"], "mesh": len(meshes) - 1, "extras": face["extras"]})
    if edge_segments:
        meshes.append(
            {
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": add_accessor(
                                edge_segments, "<f4", 5126, "VEC3", 34962, True
                            )
                        },
                        "mode": 1,  # LINES
                        "material": 1,
                    }
                ]
            }
        )
        nodes.append({"name": "edges", "mesh": len(meshes) - 1, "extras": {"kind": "edges"}})
    nodes.append(
        {"name": "part", "rotation": Z_UP_TO_Y_UP, "children": list(range(len(nodes)))}
    )
    document = {
        "asset": {"version": "2.0", "generator": "nfinit"},
        "scene": 0,
        "scenes": [{"nodes": [len(nodes) - 1], "extras": scene_extras}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": [
            {
                "name": "body",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.28, 0.32, 0.39, 1.0],
                    "metallicFactor": 0.18,
                    "roughnessFactor": 0.48,
                },
            },
            {"name": "edges", "pbrMetallicRoughness": {"baseColorFactor": [0.08, 0.09, 0.11, 1.0]}},
        ],
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(buffer)}],
    }
    json_chunk = json.dumps(document, separators=(",", ":")).encode()
    json_chunk += b" " * (-len(json_chunk) % 4)
    while len(buffer) % 4:
        buffer.append(0)
    with open(path, "wb") as output:
        output.write(struct.pack("<III", 0x46546C67, 2, 28 + len(json_chunk) + len(buffer)))
        output.write(struct.pack("<II", len(json_chunk), 0x4E4F534A) + json_chunk)
        output.write(struct.pack("<II", len(buffer), 0x004E4942) + bytes(buffer))


def _export_viewer_glb(result, output_path: Path, feature_records, constraint_records):
    """A GLB the studio can show as CAD: faces with their IDs, and edges."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh

    entity_records = _entity_records(result)
    edge_records, face_records = entity_records
    topology = _topology(
        result,
        feature_records=feature_records,
        constraint_records=constraint_records,
        entity_records=entity_records,
    )
    owner = {
        face_id: feature["id"]
        for feature in topology["features"]
        for face_id in feature["ownedFaceIds"]
    }

    bounds = result.bounding_box()
    diagonal = math.dist(tuple(bounds.min), tuple(bounds.max))
    linear = min(0.5, max(0.01, diagonal / 2000))
    angular = 0.15
    BRepMesh_IncrementalMesh(result.wrapped, linear, False, angular, True)

    faces = []
    seams = []
    for record in face_records:
        mesh = _face_mesh(record["shape"])
        face_shape = record["shape"]
        seams += [
            edge for edge in face_shape.edges()
            if BRep_Tool.IsClosed_s(edge.wrapped, face_shape.wrapped)
        ]
        if mesh is None:
            continue
        payload = record["payload"]
        faces.append(
            {
                "id": payload["id"],
                "mesh": mesh,
                "extras": {
                    "faceId": payload["id"],
                    "surfaceType": payload["surface_type"],
                    "featureId": owner.get(payload["id"]),
                },
            }
        )

    edge_segments = []
    for record in edge_records:
        # A seam (where a cylinder closes on itself) is not a real edge.
        if any(record["shape"].is_same(seam) for seam in seams):
            continue
        edge_segments += _edge_segments(record["shape"], angular, linear)

    _write_viewer_glb(
        output_path,
        faces,
        edge_segments,
        {
            "format": VIEWER_FORMAT,
            "topologyVersion": topology["topologyVersion"],
            "features": [
                {key: feature[key] for key in ("id", "name", "operation", "parentId", "ownedFaceIds")}
                for feature in topology["features"]
            ],
        },
    )
    return {"faces": len(faces), "edgeSegments": len(edge_segments) // 6}


MAX_BUILD_SNAPSHOTS = 16


def _snapshot_glb(shape, path: Path, previous_keys: set, feature: dict):
    """A coarse GLB of the part after one feature; new faces are tagged."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh

    bounds = shape.bounding_box()
    diagonal = math.dist(tuple(bounds.min), tuple(bounds.max))
    # Coarser than the final mesh: a preview shown for half a second.
    linear = min(2.0, max(0.05, diagonal / 400))
    angular = 0.25
    BRepMesh_IncrementalMesh(shape.wrapped, linear, False, angular, True)

    faces, seams = [], []
    for face in shape.faces():
        seams += [
            edge for edge in face.edges()
            if BRep_Tool.IsClosed_s(edge.wrapped, face.wrapped)
        ]
        mesh = _face_mesh(face)
        if mesh is None:
            continue
        key = _surface_key(face)
        faces.append(
            {
                "id": f"preview_{len(faces)}",
                "mesh": mesh,
                "extras": {"isNew": key is None or key not in previous_keys},
            }
        )
    edge_segments = []
    for edge in shape.edges():
        if not any(edge.is_same(seam) for seam in seams):
            edge_segments += _edge_segments(edge, angular, linear)
    _write_viewer_glb(
        path,
        faces,
        edge_segments,
        {"format": "nfinit-preview-1", "featureId": feature["id"], "name": feature["name"]},
    )


def _export_build_snapshots(feature_records) -> list[dict]:
    """One preview GLB per registered feature, in build order (at most 16)."""
    if not feature_records:
        return []
    count = len(feature_records)
    if count > MAX_BUILD_SNAPSHOTS:
        # Evenly spaced, always ending with the last feature.
        step = (count - 1) / (MAX_BUILD_SNAPSHOTS - 1)
        chosen = sorted({round(index * step) for index in range(MAX_BUILD_SNAPSHOTS)})
    else:
        chosen = list(range(count))
    snapshots = []
    previous_keys: set = set()
    for index in chosen:
        record = feature_records[index]
        name = f"snapshot-{len(snapshots)}.glb"
        _snapshot_glb(record["shape"], Path.cwd() / name, previous_keys, record)
        snapshots.append({"featureId": record["id"], "name": record["name"], "file": name})
        previous_keys = record["surface_keys"]
    return snapshots


def _export(result, operation: str, output_name: str):
    from build123d.exporters3d import export_brep, export_step, export_stl

    output_path = (Path.cwd() / output_name).resolve()
    if output_path.parent != Path.cwd().resolve():
        raise PermissionError("Output path must stay inside the sandbox directory.")

    if operation == "glb":
        success = output_path.is_file()
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


def handle_request(request: dict) -> dict:
    result, feature_records, constraint_records = _execute(request["code"])
    operation = request["operation"]
    if operation == "inspect":
        data = _inspect(result)
        if request.get("snapshots"):
            # Previews must never fail an otherwise valid part.
            try:
                data["snapshots"] = _export_build_snapshots(feature_records)
            except Exception as error:  # noqa: BLE001
                data["snapshots"] = []
                data["snapshot_error"] = f"{type(error).__name__}: {error}"
        return data
    if operation == "topology":
        return _topology(
            result,
            request.get("selection"),
            feature_records=feature_records,
            constraint_records=constraint_records,
        )
    if operation == "glb":
        output_path = (Path.cwd() / request["output_name"]).resolve()
        if output_path.parent != Path.cwd().resolve():
            raise PermissionError("Output path must stay inside the sandbox directory.")
        _export_viewer_glb(result, output_path, feature_records, constraint_records)
    data = _export(result, operation, request["output_name"])
    if operation == "glb":
        # Geometry facts cost about a millisecond once the shape exists, and
        # save the viewer a second sandbox run just to read them.
        data["inspection"] = _inspect(result)
    return data


def _failure(error: BaseException) -> dict:
    return {
        "ok": False,
        "error": {"type": type(error).__name__, "message": str(error)},
    }


def main():
    os.umask(0o077)
    _drop_privileges(Path.cwd())
    _apply_resource_limits()
    request = json.loads(sys.stdin.read())
    _disable_network()
    data = handle_request(request)
    print(json.dumps({"ok": True, "data": data}), flush=True)


def _thread_count() -> int:
    try:
        return len(os.listdir("/proc/self/task"))
    except OSError:
        import threading

        return threading.active_count()


def _warm_up():
    """Load build123d and the OpenCASCADE code that every job uses.

    Only single-threaded work belongs here. Booleans, fillets and meshing start
    OpenCASCADE's thread pool, and a child forked from a multi-threaded process
    can deadlock on a lock that one of those threads held.
    """
    import build123d  # noqa: F401
    import build123d.exporters3d  # noqa: F401

    result, _, _ = _execute("result = Box(1, 1, 1)")
    _inspect(result)


def _read_request(connection) -> dict:
    connection.settimeout(10)
    chunks = []
    while True:
        chunk = connection.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
    return json.loads(b"".join(chunks))


def _serve_job(listener, connection):
    """Run one job in a freshly forked child. Never returns."""
    status = 1
    try:
        listener.close()
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        connection.sendall(json.dumps({"pid": os.getpid()}).encode() + b"\n")
        request = _read_request(connection)
        # The server kills a late job, but if the server itself dies the job
        # must still end: SIGALRM terminates the child even when it is stuck.
        signal.alarm(math.ceil(float(request.get("deadline_seconds", 90))) + 5)

        work_dir = Path(request["work_dir"])
        os.chdir(work_dir)
        os.environ["HOME"] = os.environ["TMPDIR"] = str(work_dir)
        os.umask(0o077)
        # Keep generated output away from the server's pipes; the parent
        # reads this log when a job dies without answering.
        log = os.open(work_dir / "worker.log", os.O_WRONLY | os.O_CREAT, 0o600)
        null = os.open(os.devnull, os.O_RDONLY)
        os.dup2(null, 0)
        os.dup2(log, 1)
        os.dup2(log, 2)
        os.close(null)
        os.close(log)

        _drop_privileges(work_dir)
        _apply_resource_limits()
        _disable_network()
        try:
            response = {"ok": True, "data": handle_request(request)}
        except BaseException as error:
            response = _failure(error)
        connection.sendall(json.dumps(response).encode() + b"\n")
        status = 0
    finally:
        os._exit(status)


def serve(socket_path: str):
    _warm_up()
    if _thread_count() != 1:
        print(f"refused: {_thread_count()} threads after warm-up", flush=True)
        return
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(socket_path)
    listener.listen(64)
    # Children are never waited on; the kernel reaps them.
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    print("ready", flush=True)

    while True:
        readable, _, _ = select.select([listener, sys.stdin], [], [])
        if sys.stdin in readable and not sys.stdin.buffer.read1(1):
            return  # The server closed our stdin: it has exited.
        if listener not in readable:
            continue
        connection, _ = listener.accept()
        try:
            pid = os.fork()
        except OSError:
            pid = None  # Out of processes or memory: drop only this job.
        if pid == 0:
            _serve_job(listener, connection)
        connection.close()


if __name__ == "__main__":
    if len(sys.argv) > 4 and sys.argv[3] == "serve":
        serve(sys.argv[4])
        raise SystemExit(0)
    try:
        main()
    except BaseException as error:
        print(json.dumps(_failure(error)), flush=True)
        raise SystemExit(1)
