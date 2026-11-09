"""Bounded STL parsing and preview rendering. No source file is executed."""
import base64
from collections import Counter
import io
import math
import struct
import zlib

MAX_STL_BYTES = 10 * 1024 * 1024
MAX_REFERENCE_TRIANGLES = 100_000
MAX_SOLID_TRIANGLES = 2_000


def parse_stl(data: bytes, scale: float = 1.0) -> list:
    if not data or len(data) > MAX_STL_BYTES:
        raise ValueError("STL files must be nonempty and at most 10 MB.")
    if scale not in (1.0, 25.4):
        raise ValueError("Choose millimeters or inches for the STL units.")
    triangles = []
    count = struct.unpack_from("<I", data, 80)[0] if len(data) >= 84 else 0
    if count and 84 + count * 50 == len(data):
        if count > MAX_REFERENCE_TRIANGLES:
            raise ValueError("STL exceeds 100,000 triangles. Simplify it before importing.")
        for i in range(count):
            values = struct.unpack_from("<9f", data, 84 + i * 50 + 12)
            triangles.append([tuple(v * scale for v in values[j:j+3]) for j in (0, 3, 6)])
    else:
        try:
            text = data.decode("ascii")
        except UnicodeDecodeError as error:
            raise ValueError("Malformed binary STL.") from error
        if not text.lstrip().lower().startswith("solid") or "endsolid" not in text.lower():
            raise ValueError("Expected a binary or ASCII STL file.")
        vertices = []
        for line in text.splitlines():
            fields = line.split()
            if fields and fields[0].lower() == "vertex":
                if len(fields) != 4:
                    raise ValueError("Malformed STL vertex.")
                vertices.append(tuple(float(v) * scale for v in fields[1:]))
                if len(vertices) > MAX_REFERENCE_TRIANGLES * 3:
                    raise ValueError("STL exceeds 100,000 triangles. Simplify it before importing.")
        if not vertices or len(vertices) % 3:
            raise ValueError("STL must contain complete triangles.")
        triangles = [vertices[i:i+3] for i in range(0, len(vertices), 3)]
    if not triangles:
        raise ValueError("STL contains no triangles.")
    if any(not math.isfinite(v) or abs(v) > 1_000_000 for t in triangles for p in t for v in p):
        raise ValueError("STL coordinates must be finite and within ±1,000,000 mm.")
    for a, b, c in triangles:
        u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
        area2 = sum(x*x for x in (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]))
        if area2 < 1e-20:
            raise ValueError("STL contains degenerate triangles; repair the mesh before importing.")
    return triangles


def mesh_facts(triangles: list) -> dict:
    points = [p for t in triangles for p in t]
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    edges = Counter()
    directed = Counter()
    for tri in triangles:
        keys = [tuple(round(v, 6) for v in p) for p in tri]
        for a, b in zip(keys, keys[1:] + keys[:1]):
            edges[tuple(sorted((a, b)))] += 1
            directed[(a, b)] += 1
    closed = all(n == 2 for n in edges.values())
    oriented = closed and all(directed[(b, a)] == n for (a, b), n in directed.items())
    volume = abs(sum(a[0]*(b[1]*c[2]-b[2]*c[1]) - a[1]*(b[0]*c[2]-b[2]*c[0])
                     + a[2]*(b[0]*c[1]-b[1]*c[0]) for a, b, c in triangles) / 6)
    return {"triangles": len(triangles), "closed": closed, "oriented": oriented,
            "volume_mm3": round(volume, 6) if closed else None,
            "bounds": dict(zip("xyz", [round(high[i]-low[i], 6) for i in range(3)])),
            "min": low, "max": high}


def compare_reference(inspection, facts: dict) -> dict:
    bounds = inspection.bounding_box_mm or {}
    return {"bounds_delta_mm": {axis: round(bounds.get(axis, 0) - facts["bounds"][axis], 6) for axis in "xyz"},
            "reference_volume_mm3": facts.get("volume_mm3"),
            "model_volume_mm3": inspection.volume_mm3,
            "coverage": "Envelope and volume only. Matching values do not establish shape equivalence or recovered features."}


def faceted_code(triangles: list) -> str:
    facts = mesh_facts(triangles)
    if len(triangles) > MAX_SOLID_TRIANGLES:
        raise ValueError("Exact faceted editing supports up to 2,000 triangles. Use reconstruction or simplify the STL.")
    if not facts["closed"] or not facts["oriented"]:
        raise ValueError("Exact editing needs a closed, consistently oriented mesh. Repair it or use reconstruction.")
    packed = b"".join(struct.pack("<9d", *(v for p in tri for v in p)) for tri in triangles)
    encoded = base64.b64encode(zlib.compress(packed)).decode("ascii")
    chunks = [encoded[i:i+16000] for i in range(0, len(encoded), 16000)]
    code = ("# Imported STL: faceted geometry, not recovered parametric features.\n"
            f"source_mesh = mesh_solid({chunks!r})\n"
            "result = source_mesh\n"
            "register_feature('source_mesh', 'Original STL', 'reference', result)\n")
    if len(code.encode()) > 95_000:
        raise ValueError("STL is too large for an editable faceted solid. Use reconstruction.")
    return code


def render_views(triangles: list) -> list[str]:
    """Orthographic reference views, capped for bounded CPU and memory use."""
    from PIL import Image, ImageDraw
    matrices = [((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
                ((.707, -.707, 0), (.408, .408, .816), (-.577, -.577, .577))]
    labels = ["Top (X/Y)", "Front (X/Z)", "Isometric"]
    views = []
    # All triangles remain in the geometry; previews alone are sampled.
    sampled = triangles[::max(1, math.ceil(len(triangles) / 15000))]
    for matrix, label in zip(matrices, labels):
        projected = [[[sum(p[i]*axis[i] for i in range(3)) for axis in matrix] for p in t] for t in sampled]
        points = [p for t in projected for p in t]
        low = [min(p[i] for p in points) for i in (0, 1)]
        high = [max(p[i] for p in points) for i in (0, 1)]
        scale = min(560 / max(high[0]-low[0], 1e-9), 400 / max(high[1]-low[1], 1e-9))
        center = [(high[i]+low[i])/2 for i in (0, 1)]
        image = Image.new("RGB", (640, 480), "#f4f1eb")
        draw = ImageDraw.Draw(image)
        for tri in sorted(projected, key=lambda t: sum(p[2] for p in t)):
            draw.polygon([(320+(p[0]-center[0])*scale, 250-(p[1]-center[1])*scale) for p in tri],
                         fill="#819496", outline="#53696d")
        draw.text((16, 12), label + " — reference view; measure geometry for dimensions", fill="#172e34")
        output = io.BytesIO()
        image.save(output, format="PNG")
        views.append("data:image/png;base64," + base64.b64encode(output.getvalue()).decode())
    return views


def model_views(code: str) -> list[str]:
    from .runner import export_code
    artifact = export_code(code, "stl")
    try:
        return render_views(parse_stl(artifact.path.read_bytes()))
    finally:
        artifact.cleanup()
