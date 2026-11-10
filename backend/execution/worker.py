"""Isolated build123d worker.

This file is launched with Python's isolated mode. It runs in one of two ways:

- One-shot: one JSON request on stdin and one JSON response on stdout.
- Fork server (``serve <socket>``): import build123d once, then fork one fresh
  child per job from that clean process. A child serves exactly one
  connection and exits, so no state leaks from one job into the next.
"""

import contextlib
import errno
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


# Each root-launched job receives a different numeric identity. Linux does not
# require that these IDs exist in /etc/passwd. Distinct IDs make mode-0700 job
# directories unreadable to concurrent jobs; using one shared "nobody" user
# would not.
SANDBOX_UID_BASE = int(os.environ.get("CAD_SANDBOX_UID_BASE", "100000"))
SANDBOX_GID_BASE = int(os.environ.get("CAD_SANDBOX_GID_BASE", "100000"))
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
    from it can do. With a unique numeric uid the job cannot read the server's
    environment (where the secrets are) through /proc, cannot change the app's
    files, and cannot read or write another job's mode-0700 directory. Marking
    it non-dumpable also hides its process memory from other jobs.
    """
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return  # Local development: already unprivileged.
    job_offset = os.getpid()
    sandbox_uid = SANDBOX_UID_BASE + job_offset
    sandbox_gid = SANDBOX_GID_BASE + job_offset
    if sandbox_uid >= 2**32 - 1 or sandbox_gid >= 2**32 - 1:
        raise PermissionError("The CAD sandbox could not allocate a job identity.")
    try:
        for path in (work_dir, *work_dir.iterdir()):
            os.chown(path, sandbox_uid, sandbox_gid)
        if sys.platform.startswith("linux"):
            _prctl(38, 1)  # PR_SET_NO_NEW_PRIVS: setuid binaries gain nothing.
        os.setgroups([])
        os.setgid(sandbox_gid)
        os.setuid(sandbox_uid)
        if sys.platform.startswith("linux"):
            _prctl(4, 0)  # PR_SET_DUMPABLE: no /proc access from other jobs.
    except OSError as error:
        # Fail closed: running untrusted code as root is worse than no job.
        raise PermissionError(
            f"The CAD sandbox could not drop root privileges: {error}"
        ) from error
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("The CAD sandbox is still running as root.")
    _set_limit(resource.RLIMIT_NPROC, SANDBOX_MAX_PROCESSES)


def _restrict_filesystem(work_dir: Path) -> None:
    """Allow filesystem changes only beneath this job's private directory.

    A unique uid protects the application and other jobs, but directories such
    as /tmp are intentionally writable by every uid. Landlock makes the kernel
    reject escaped code that tries to leave artifacts there. Read access is
    deliberately not restricted: OpenCASCADE and font handling still need the
    installed, read-only runtime files after the restriction is installed.
    """
    if not sys.platform.startswith("linux"):
        return

    import ctypes

    # Landlock's three syscalls use the same numbers on the Linux
    # architectures supported by the production Python image (x86_64/arm64).
    create_ruleset = 444
    add_rule = 445
    restrict_self = 446
    create_ruleset_version = 1
    rule_path_beneath = 1

    write_file = 1 << 1
    remove_dir = 1 << 4
    remove_file = 1 << 5
    make_char = 1 << 6
    make_dir = 1 << 7
    make_reg = 1 << 8
    make_sock = 1 << 9
    make_fifo = 1 << 10
    make_block = 1 << 11
    make_sym = 1 << 12
    refer = 1 << 13  # Landlock ABI 2
    truncate = 1 << 14  # Landlock ABI 3

    class RulesetAttr(ctypes.Structure):
        _fields_ = [("handled_access_fs", ctypes.c_uint64)]

    class PathBeneathAttr(ctypes.Structure):
        _pack_ = 1
        _fields_ = [
            ("allowed_access", ctypes.c_uint64),
            ("parent_fd", ctypes.c_int32),
        ]

    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long

    abi = libc.syscall(create_ruleset, None, 0, create_ruleset_version)
    if abi < 1:
        error = ctypes.get_errno()
        raise PermissionError(
            f"The CAD sandbox requires Landlock on Linux: {os.strerror(error)}"
        )

    handled = (
        write_file
        | remove_dir
        | remove_file
        | make_char
        | make_dir
        | make_reg
        | make_sock
        | make_fifo
        | make_block
        | make_sym
    )
    if abi >= 2:
        handled |= refer
    if abi >= 3:
        handled |= truncate

    ruleset_attr = RulesetAttr(handled)
    ruleset_fd = libc.syscall(
        create_ruleset,
        ctypes.byref(ruleset_attr),
        ctypes.sizeof(ruleset_attr),
        0,
    )
    if ruleset_fd < 0:
        error = ctypes.get_errno()
        raise PermissionError(
            f"The CAD sandbox could not create a Landlock ruleset: {os.strerror(error)}"
        )

    directory_fd = -1
    try:
        directory_fd = os.open(
            work_dir,
            os.O_PATH | os.O_CLOEXEC,
        )
        path_rule = PathBeneathAttr(handled, directory_fd)
        result = libc.syscall(
            add_rule,
            ruleset_fd,
            rule_path_beneath,
            ctypes.byref(path_rule),
            0,
        )
        if result != 0:
            error = ctypes.get_errno()
            raise OSError(error, "landlock_add_rule failed")
        # Required even when the process already dropped root.
        _prctl(38, 1)  # PR_SET_NO_NEW_PRIVS
        result = libc.syscall(restrict_self, ruleset_fd, 0)
        if result != 0:
            error = ctypes.get_errno()
            raise OSError(error, "landlock_restrict_self failed")
    except OSError as error:
        raise PermissionError(
            f"The CAD sandbox could not confine its filesystem: {error}"
        ) from error
    finally:
        if directory_fd >= 0:
            os.close(directory_fd)
        os.close(ruleset_fd)


def _disable_network():
    def denied(*_args, **_kwargs):
        raise PermissionError("Network access is disabled in the CAD sandbox.")

    original_socket = socket.socket

    class DeniedSocket(original_socket):
        def __new__(cls, *_args, **_kwargs):
            raise PermissionError("Network access is disabled in the CAD sandbox.")

    socket.socket = DeniedSocket
    socket.create_connection = denied


def _apply_syscall_filter() -> None:
    """Deny OS escape primitives in the Linux kernel, after imports are warm.

    The AST policy and restricted built-ins reduce attack surface, but Python
    object graphs are not a security boundary. This filter is inherited by
    any thread or child an escape manages to create. The job may keep using
    its already-open result socket, but it cannot create a network socket or
    execute an external binary.
    """
    if not sys.platform.startswith("linux"):
        return

    import ctypes

    try:
        library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    except OSError as error:
        raise PermissionError("The CAD sandbox requires libseccomp on Linux.") from error

    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    library.seccomp_rule_add.restype = ctypes.c_int
    library.seccomp_rule_add_array.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_void_p,
    ]
    library.seccomp_rule_add_array.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int

    allow = 0x7FFF0000
    deny = 0x00050000 | errno.EPERM
    not_supported = 0x00050000 | errno.ENOSYS
    context = library.seccomp_init(allow)
    if not context:
        raise PermissionError("The CAD sandbox could not initialize seccomp.")
    blocked = (
        "socket",
        "socketpair",
        "connect",
        "bind",
        "listen",
        "accept",
        "accept4",
        "execve",
        "execveat",
        "ptrace",
        "process_vm_readv",
        "process_vm_writev",
        "mount",
        "umount2",
        "pivot_root",
        "unshare",
        "setns",
        "bpf",
        "userfaultfd",
        "open_by_handle_at",
        "name_to_handle_at",
        "keyctl",
        "add_key",
        "request_key",
        # io_uring performs operations in a kernel worker and has bypassed
        # syscall-oriented sandboxes in the past. The CAD worker does not use
        # it, so deny the whole interface instead of trying to mirror every
        # socket/filesystem rule there.
        "io_uring_setup",
        "io_uring_enter",
        "io_uring_register",
        "fork",
        "vfork",
    )
    try:
        for name in blocked:
            syscall = library.seccomp_syscall_resolve_name(name.encode())
            if syscall < 0:
                continue
            result = library.seccomp_rule_add(context, deny, syscall, 0)
            if result != 0:
                raise OSError(-result, f"seccomp_rule_add({name}) failed")

        # Modern libc tries clone3() for pthreads and falls back to clone()
        # only on ENOSYS. Seccomp cannot inspect clone3's pointed-to argument,
        # so make that fallback happen and allow clone() only when it creates
        # a thread in this process. New processes would multiply the per-job
        # CPU and address-space limits.
        clone3 = library.seccomp_syscall_resolve_name(b"clone3")
        if clone3 >= 0:
            result = library.seccomp_rule_add(context, not_supported, clone3, 0)
            if result != 0:
                raise OSError(-result, "seccomp_rule_add(clone3) failed")

        class ScmpArgCmp(ctypes.Structure):
            _fields_ = [
                ("arg", ctypes.c_uint),
                ("op", ctypes.c_uint),
                ("datum_a", ctypes.c_uint64),
                ("datum_b", ctypes.c_uint64),
            ]

        clone = library.seccomp_syscall_resolve_name(b"clone")
        if clone >= 0:
            clone_thread = 0x00010000
            masked_equal = 7
            comparison = ScmpArgCmp(0, masked_equal, clone_thread, 0)
            result = library.seccomp_rule_add_array(
                context,
                deny,
                clone,
                1,
                ctypes.byref(comparison),
            )
            if result != 0:
                raise OSError(-result, "seccomp_rule_add_array(clone) failed")
        result = library.seccomp_load(context)
        if result != 0:
            raise OSError(-result, "seccomp_load failed")
    except OSError as error:
        raise PermissionError(f"The CAD sandbox could not load seccomp: {error}") from error
    finally:
        library.seccomp_release(context)


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
    scope["mesh_solid"] = _mesh_solid
    checks = []

    def check_measurement(name, actual, expected, tolerance=0.01):
        if len(checks) >= 64 or not isinstance(name, str) or len(name) > 160:
            raise ValueError("Use at most 64 named geometry checks.")
        values = [float(actual), float(expected), float(tolerance)]
        if not all(math.isfinite(v) for v in values) or values[2] < 0:
            raise ValueError("Geometry checks require finite values and nonnegative tolerance.")
        checks.append({"name": name, "actual": values[0], "expected": values[1],
                       "tolerance": values[2], "passed": abs(values[0]-values[1]) <= values[2]})

    scope["check_measurement"] = check_measurement
    return scope, feature_records, constraint_records, checks


def _mesh_solid(chunks):
    """Decode only bounded numeric triangles; never a path, pickle or Python."""
    import base64
    import struct
    import zlib
    from build123d import Face, Wire, Shell, Solid
    if not isinstance(chunks, list) or len(chunks) > 8:
        raise ValueError("Invalid mesh payload.")
    if any(not isinstance(c, str) or len(c) > 16000 for c in chunks):
        raise ValueError("Invalid mesh chunk.")
    decoder = zlib.decompressobj()
    packed = decoder.decompress(base64.b64decode("".join(chunks), validate=True), 2000 * 72 + 1)
    if not decoder.eof or decoder.unused_data or not packed or len(packed) > 2000 * 72 or len(packed) % 72:
        raise ValueError("Mesh must contain at most 2,000 triangles.")
    faces = []
    for values in struct.iter_unpack("<9d", packed):
        if any(not math.isfinite(v) or abs(v) > 1_000_000 for v in values):
            raise ValueError("Invalid mesh coordinate.")
        faces.append(Face(Wire.make_polygon([values[i:i+3] for i in (0, 3, 6)])))
    solid = Solid(Shell(faces))
    if solid.volume < 0:
        solid.wrapped.Reverse()
    if not solid.is_valid or not solid.is_manifold or abs(solid.volume) < 1e-9:
        raise ValueError("Mesh could not be converted into a valid closed solid.")
    return solid


def _execute(code: str):
    scope, feature_records, constraint_records, checks = _build_scope()
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
    return result, feature_records, constraint_records, checks


# Feature ownership compares every face's edges with every edge; skip it on
# parts large enough to make that slow.
MAX_OWNERSHIP_FACES = 400
MAX_LISTED_SOLIDS = 50
WARNED_OPERATIONS = {"additive", "subtractive", "pattern", "fillet", "chamfer"}


def _open_edges(solid):
    """Edges on the solid's free boundary: 0 for a closed solid.

    build123d's is_manifold counts the collapsed edge at a sphere's or cone's
    tip as open, so a plain sphere fails it. The kernel's free-boundary
    analysis skips those edges and joins edges that meet within tolerance.
    """
    from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    bounds = ShapeAnalysis_FreeBounds(solid.wrapped)
    count = 0
    for wires in (bounds.GetClosedWires(), bounds.GetOpenWires()):
        explorer = TopExp_Explorer(wires, TopAbs_EDGE)
        while explorer.More():
            count += 1
            explorer.Next()
    return count


def _solid_facts(solid):
    volume = float(solid.volume)
    bounds = solid.bounding_box()
    return {
        "volume_mm3": round(volume, 3),
        "bounding_box_mm": {
            axis: round(float(value), 3)
            for axis, value in zip("xyz", bounds.size)
        },
        "min_mm": _vector(bounds.min, 3),
        "manifold": _open_edges(solid) == 0,
        # Faces turned inward give a negative volume; the kernel's validity
        # check does not catch it.
        "inverted": not volume > 0,
    }


def _feature_faces(result, feature_records):
    """How many final faces each registered feature owns, or None if skipped."""
    if not feature_records:
        return []
    if len(result.faces()) > MAX_OWNERSHIP_FACES:
        return None
    _, face_records = _entity_records(result)
    features, _ = _feature_tree(feature_records, face_records)
    return [
        {
            "id": feature["id"],
            "operation": feature["operation"],
            "owned_faces": len(feature["ownedFaceIds"]),
        }
        for feature in features
    ]


def _inspect(result, checks=None, feature_records=None):
    bounds = result.bounding_box().size
    solids = result.solids() if hasattr(result, "solids") else []
    checks = checks or []
    failed = [check["name"] for check in checks if not check["passed"]]
    solid_facts = [_solid_facts(solid) for solid in solids]

    # Retrieval also contains legitimate 2D sketches and wires. Kernel
    # validity applies to these too; the solid rules apply only to solids.
    problems = []
    for index, facts in enumerate(solid_facts, start=1):
        if facts["inverted"]:
            problems.append(
                f"Solid {index} is inside out (negative volume). Build it another "
                "way, for example one extruded or revolved profile instead of "
                "stacked Booleans."
            )
        elif not facts["manifold"]:
            problems.append(f"Solid {index} is not a closed, manifold solid.")
    if failed:
        problems.append("Failed geometry checks: " + ", ".join(failed))
    kernel_valid = bool(result.is_valid and math.isfinite(float(result.volume)))
    if not kernel_valid:
        problems.insert(0, "The result must contain valid geometry with finite volume.")

    warnings = []
    if len(solid_facts) > 1:
        total = sum(abs(facts["volume_mm3"]) for facts in solid_facts) or 1.0
        smallest = min(abs(facts["volume_mm3"]) for facts in solid_facts)
        warnings.append(
            f"{len(solid_facts)} separate solids: the smallest is "
            f"{smallest / total:.1%} of the total volume. A feature that should be "
            "joined to the part does not overlap it."
        )

    census = _census(result)
    if "error" not in census:
        try:
            owned = _feature_faces(result, feature_records)
        except Exception as error:  # noqa: BLE001
            owned = None
            warnings.append(f"Feature ownership could not be measured: {type(error).__name__}.")
        if owned is None:
            warnings.append(
                f"Feature ownership skipped: the part has {len(result.faces())} faces."
            )
        else:
            census["features"] = owned
            for feature in owned:
                if feature["owned_faces"] == 0 and feature["operation"] in WARNED_OPERATIONS:
                    warnings.append(
                        f"Feature '{feature['id']}' owns no faces of the final part. "
                        "It may have been skipped, merged into an earlier feature's "
                        "faces, or removed by a later feature."
                    )

    data = {
        "valid": not problems,
        "shape_type": type(result).__name__,
        "solid_count": len(solids),
        "volume_mm3": round(float(result.volume), 3),
        "bounding_box_mm": {
            "x": round(float(bounds.X), 3),
            "y": round(float(bounds.Y), 3),
            "z": round(float(bounds.Z), 3),
        },
        "checks": checks,
        "verification": "failed" if failed else "measured" if checks else "unverified",
        "error": " ".join(problems) or None,
        "solids": solid_facts[:MAX_LISTED_SOLIDS],
        "warnings": warnings,
        "census": census,
    }
    if len(solid_facts) > MAX_LISTED_SOLIDS:
        data["solids_truncated"] = True
    return data


MAX_CENSUS_ENTRIES = 50
MAX_CENSUS_CENTERS = 50


def _census(result):
    """Count holes, bosses and rounded edges from the part's faces.

    Facts only: a census never fails an inspection. A failure is reported in
    the census itself, so a missing count is not read as zero.
    """
    try:
        return _count_features(result)
    except Exception as error:  # noqa: BLE001
        return {"error": f"{type(error).__name__}: {error}"[:300]}


def _cylinder_facts(face, surface):
    """Axis, angular span, axial range and concavity of a cylindrical face."""
    cylinder = surface.Cylinder()
    axis = cylinder.Axis()
    location, direction = axis.Location(), axis.Direction()
    origin = (location.X(), location.Y(), location.Z())
    unit = (direction.X(), direction.Y(), direction.Z())
    u0, u1 = surface.FirstUParameter(), surface.LastUParameter()
    v0, v1 = surface.FirstVParameter(), surface.LastVParameter()
    position = face.position_at(0.5, 0.5)
    point = (position.X, position.Y, position.Z)
    direction_out = face.normal_at(position)
    normal = (direction_out.X, direction_out.Y, direction_out.Z)
    offset = [point[index] - origin[index] for index in range(3)]
    along = sum(offset[index] * unit[index] for index in range(3))
    radial = [offset[index] - along * unit[index] for index in range(3)]
    # A hole's surface faces its axis; a boss's or a rounded edge's faces away.
    concave = sum(normal[index] * radial[index] for index in range(3)) < 0
    return {
        "radius": float(cylinder.Radius()),
        "span": math.degrees(u1 - u0),
        "v0": min(v0, v1),
        "v1": max(v0, v1),
        "origin": origin,
        "unit": unit,
        "concave": concave,
    }


def _count_features(result):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Sphere, GeomAbs_Torus

    cylinders: dict = {}
    rounded = Counter()
    face_counts = Counter()
    for face in result.faces():
        face_counts[face.geom_type.name.lower()] += 1
        surface = BRepAdaptor_Surface(face.wrapped)
        kind = surface.GetType()
        if kind == GeomAbs_Cylinder:
            facts = _cylinder_facts(face, surface)
            # One hole can be split into several faces on the same surface.
            group = cylinders.setdefault(
                (_surface_key(face), facts["concave"]),
                {**facts, "span": 0.0},
            )
            group["span"] += facts["span"]
            group["v0"] = min(group["v0"], facts["v0"])
            group["v1"] = max(group["v1"], facts["v1"])
        elif kind == GeomAbs_Torus:
            rounded[(round(surface.Torus().MinorRadius(), 3), "torus")] += 1
        elif kind == GeomAbs_Sphere:
            rounded[(round(surface.Sphere().Radius(), 3), "sphere")] += 1

    full: dict = {"holes": {}, "bosses": {}}
    partial = 0
    for group in cylinders.values():
        if group["span"] >= 359.0:
            middle = (group["v0"] + group["v1"]) / 2
            center = [
                round(group["origin"][index] + middle * group["unit"][index], 3) + 0.0
                for index in range(3)
            ]
            axis = [round(abs(value), 6) + 0.0 for value in group["unit"]]
            length = round(group["v1"] - group["v0"], 3)
            diameter = round(2 * group["radius"], 3)
            entries = full["holes" if group["concave"] else "bosses"]
            entry = entries.setdefault(
                (diameter, tuple(axis), length),
                {"diameter_mm": diameter, "count": 0, "axis": axis,
                 "length_mm": length, "centers_mm": []},
            )
            entry["count"] += 1
            if len(entry["centers_mm"]) < MAX_CENSUS_CENTERS:
                entry["centers_mm"].append(center)
        elif group["span"] < 180.0:
            rounded[(round(group["radius"], 3), "cylinder")] += 1
        else:
            # Slot ends and other part-round faces.
            partial += 1

    census = {}
    for name, entries in full.items():
        values = sorted(
            entries.values(), key=lambda entry: (-entry["count"], entry["diameter_mm"])
        )
        census[name] = values[:MAX_CENSUS_ENTRIES]
        if len(values) > MAX_CENSUS_ENTRIES:
            census[f"{name}_truncated"] = True
    census["rounded_edges"] = [
        {"radius_mm": radius, "count": count, "surface": surface}
        for (radius, surface), count in sorted(rounded.items())
    ][:MAX_CENSUS_ENTRIES]
    census["partial_cylinders"] = partial
    census["face_counts"] = dict(sorted(face_counts.items()))
    return census


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


MAX_QUERY_ITEMS = 50
MAX_QUERY_BYTES = 20_000


def _radius(shape):
    try:
        return round(float(shape.radius), 6)
    except Exception:  # noqa: BLE001 - only round faces and edges have one
        return None


def _query_index(result, feature_records):
    edge_records, face_records = _entity_records(result)
    features, _ = _feature_tree(feature_records or [], face_records)
    owner = {
        face_id: feature["id"]
        for feature in features
        for face_id in feature["ownedFaceIds"]
    }
    faces = {record["payload"]["id"]: record for record in face_records}
    edges = {record["payload"]["id"]: record for record in edge_records}
    return faces, edges, owner, {feature["id"]: feature for feature in features}


def _face_facts(record, owner):
    payload = record["payload"]
    return {
        "id": payload["id"],
        "surface_type": payload["surface_type"],
        "area_mm2": round(payload["area_mm2"], 3),
        "center_mm": _vector(payload["center_mm"], 3),
        "normal": _vector(payload["normal"], 4),
        "bounds_mm": payload["bounds_mm"],
        "radius_mm": _radius(record["shape"]),
        "feature_id": owner.get(payload["id"]),
    }


def _edge_facts(record):
    payload = record["payload"]
    shape = record["shape"]
    return {
        "id": payload["id"],
        "curve_type": payload["curve_type"],
        "length_mm": round(payload["length_mm"], 3),
        "radius_mm": _radius(shape),
        "start_mm": _vector(shape.position_at(0), 3),
        "end_mm": _vector(shape.position_at(1), 3),
    }


def _unknown(kind, wanted, records):
    nearby = sorted(records, key=lambda key: -records[key]["payload"].get("area_mm2", records[key]["payload"].get("length_mm", 0)))[:5]
    raise ValueError(
        f"No {kind} has id '{wanted}'. Ids come from inspect_model's faces or edges queries"
        + (f"; for example: {', '.join(nearby)}." if nearby else ".")
    )


def _target(spec, faces, edges, features):
    """A face, an edge, a feature's faces or a point, as a shape."""
    from build123d import Compound, Vertex

    if isinstance(spec, list):
        return Vertex(*spec), f"point {spec}"
    if spec in faces:
        return faces[spec]["shape"], f"face {spec}"
    if spec in edges:
        return edges[spec]["shape"], f"edge {spec}"
    if spec in features:
        owned = [faces[face_id]["shape"] for face_id in features[spec]["ownedFaceIds"]]
        if not owned:
            raise ValueError(f"Feature '{spec}' owns no faces of the final part.")
        return Compound(children=owned), f"feature {spec}"
    raise ValueError(f"'{spec}' is not a face id, an edge id, a feature id or a point.")


def _section(result, axis, at):
    from build123d import Face, Plane

    planes = {"x": Plane.YZ, "y": Plane.XZ, "z": Plane.XY}
    bounds = result.bounding_box()
    size = 4 * max(bounds.size.X, bounds.size.Y, bounds.size.Z, 1.0)
    cut = result & (planes[axis].offset(at) * Face.make_rect(size, size))
    faces = cut.faces() if cut is not None else []
    if not faces:
        return {"axis": axis, "at_mm": at, "area_mm2": 0.0, "loops": 0, "bounds_mm": None}
    section_bounds = cut.bounding_box()
    return {
        "axis": axis,
        "at_mm": at,
        "area_mm2": round(sum(face.area for face in faces), 3),
        "regions": len(faces),
        "loops": sum(len(face.wires()) for face in faces),
        "bounds_mm": {"minimum": _vector(section_bounds.min, 3), "maximum": _vector(section_bounds.max, 3)},
    }


def _query(result, query, checks, feature_records):
    """Answer one inspect_model question about the built part."""
    kind = query["kind"]
    if kind == "summary":
        return _inspect(result, checks, feature_records)
    if kind == "section":
        return _section(result, query["axis"], float(query["at"]))

    faces, edges, owner, features = _query_index(result, feature_records)
    limit = min(int(query.get("limit") or MAX_QUERY_ITEMS), MAX_QUERY_ITEMS)
    if kind == "faces":
        items = [_face_facts(record, owner) for record in faces.values()]
        if query.get("surface_type"):
            items = [item for item in items if item["surface_type"] == query["surface_type"]]
        if query.get("feature_id"):
            items = [item for item in items if item["feature_id"] == query["feature_id"]]
        if query.get("normal"):
            wanted = query["normal"]
            length = math.sqrt(sum(value * value for value in wanted)) or 1.0
            cosine = math.cos(math.radians(5))
            items = [
                item for item in items
                if sum(item["normal"][index] * wanted[index] / length for index in range(3)) >= cosine
            ]
        if query.get("min_area_mm2"):
            items = [item for item in items if item["area_mm2"] >= query["min_area_mm2"]]
        items.sort(key=lambda item: (-item["area_mm2"], item["id"]))
        return {"count": len(items), "faces": items[:limit], "truncated": len(items) > limit}
    if kind == "face":
        record = faces.get(query["face_id"]) or _unknown("face", query["face_id"], faces)
        facts = _face_facts(record, owner)
        facts["edges"] = [
            _edge_facts(edges[edge_id]) for edge_id in record["payload"]["edge_ids"][:MAX_QUERY_ITEMS]
        ]
        return facts
    if kind == "edges":
        wanted_feature = query.get("feature_id")
        allowed = None
        if wanted_feature:
            allowed = {
                edge_id
                for face_id, feature_id in owner.items()
                if feature_id == wanted_feature
                for edge_id in faces[face_id]["payload"]["edge_ids"]
            }
        items = [
            _edge_facts(record) for edge_id, record in edges.items()
            if allowed is None or edge_id in allowed
        ]
        if query.get("curve_type"):
            items = [item for item in items if item["curve_type"] == query["curve_type"]]
        items.sort(key=lambda item: (-item["length_mm"], item["id"]))
        return {"count": len(items), "edges": items[:limit], "truncated": len(items) > limit}
    if kind == "distance":
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape

        first, first_label = _target(query["a"], faces, edges, features)
        second, second_label = _target(query["b"], faces, edges, features)
        measure = BRepExtrema_DistShapeShape(first.wrapped, second.wrapped)
        if not measure.IsDone():
            raise ValueError("The distance could not be measured.")
        point_a, point_b = measure.PointOnShape1(1), measure.PointOnShape2(1)
        return {
            "a": first_label,
            "b": second_label,
            "distance_mm": round(float(measure.Value()), 6),
            "point_a_mm": [round(point_a.X(), 4), round(point_a.Y(), 4), round(point_a.Z(), 4)],
            "point_b_mm": [round(point_b.X(), 4), round(point_b.Y(), 4), round(point_b.Z(), 4)],
        }
    raise ValueError(f"Unsupported query kind '{kind}'.")


def _bounded_answer(answer):
    """Drop list items until the answer fits the response limit."""
    encoded = json.dumps(answer)
    while len(encoded) > MAX_QUERY_BYTES:
        lists = [key for key, value in answer.items() if isinstance(value, list) and value]
        if not lists:
            return {"error": "The answer is too large. Narrow the query."}
        longest = max(lists, key=lambda key: len(answer[key]))
        answer[longest] = answer[longest][: max(1, len(answer[longest]) // 2)] if len(answer[longest]) > 1 else []
        answer["truncated"] = True
        encoded = json.dumps(answer)
    return answer


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
    result, feature_records, constraint_records, checks = _execute(request["code"])
    operation = request["operation"]
    if operation == "inspect":
        data = _inspect(result, checks, feature_records)
        if request.get("snapshots"):
            # Previews must never fail an otherwise valid part.
            try:
                data["snapshots"] = _export_build_snapshots(feature_records)
            except Exception as error:  # noqa: BLE001
                data["snapshots"] = []
                data["snapshot_error"] = f"{type(error).__name__}: {error}"
        return data
    if operation == "query":
        return _bounded_answer(_query(result, request["query"], checks, feature_records))
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
        data["inspection"] = _inspect(result, checks, feature_records)
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
    _restrict_filesystem(Path.cwd())
    _disable_network()
    _apply_syscall_filter()
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

    result, _, _, _ = _execute("result = Box(1, 1, 1)")
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
        _restrict_filesystem(work_dir)
        _disable_network()
        _apply_syscall_filter()
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
