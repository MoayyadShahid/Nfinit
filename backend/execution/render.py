"""Technical views of a part for the agent to review, drawn inside the sandbox.

Faces come from the kernel's tessellation and are shaded with a light fixed
to the camera. Edges come from the kernel's hidden-line removal
(``project_to_viewport``), so silhouettes and feature edges are exact. The
worker loads this module by path; it must not import anything from Nfinit.
"""

import io
import math

PRESETS = {
    "iso": (-45.0, 35.264),
    "iso_back": (135.0, -35.264),
    "front": (-90.0, 0.0),
    "back": (90.0, 0.0),
    "right": (0.0, 0.0),
    "left": (180.0, 0.0),
    "top": (-90.0, 90.0),
    "bottom": (-90.0, -90.0),
}
SIZES = {"normal": (800, 600), "large": (1200, 900)}
MAX_TRIANGLES = 60_000

BACKGROUND = (246, 244, 239)
INK = (28, 33, 38)
MUTED = (120, 126, 132)
BASE = (176, 182, 188)
ACCENT = (230, 120, 40)
CAP = (196, 72, 72)
AXIS_COLORS = {"X": (205, 55, 55), "Y": (45, 150, 70), "Z": (50, 90, 205)}


def _vector(value):
    if hasattr(value, "X"):
        return (float(value.X), float(value.Y), float(value.Z))
    return (float(value[0]), float(value[1]), float(value[2]))


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    length = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / length, a[1] / length, a[2] / length)


def camera(spec, look_at, diagonal):
    """Origin, up and the camera frame for a preset name or an az/el pair."""
    if isinstance(spec, str):
        azimuth, elevation = PRESETS[spec]
    else:
        azimuth, elevation = float(spec["azimuth"]), float(spec["elevation"])
    az, el = math.radians(azimuth), math.radians(elevation)
    direction = (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))
    distance = 4 * max(diagonal, 1.0)
    origin = tuple(look_at[index] + distance * direction[index] for index in range(3))
    up = (0.0, 1.0, 0.0) if abs(elevation) > 89.0 else (0.0, 0.0, 1.0)
    forward = _unit(_sub(look_at, origin))
    right = _unit(_cross(forward, up))
    camera_up = _cross(right, forward)
    return {"origin": origin, "up": up, "look_at": look_at, "forward": forward,
            "right": right, "camera_up": camera_up}


def _project(point, frame):
    offset = _sub(point, frame["look_at"])
    return (_dot(offset, frame["right"]), _dot(offset, frame["camera_up"]), _dot(offset, frame["forward"]))


def _section(shape, section):
    """The part cut by a plane, keeping one side, and the cut plane's test."""
    from build123d import Align, Box, Pos

    bounds = shape.bounding_box()
    size = 4 * max(bounds.size.X, bounds.size.Y, bounds.size.Z, 1.0)
    axis, at = section["axis"], float(section["at"])
    keep_below = section.get("keep", "below") == "below"
    align = [Align.CENTER, Align.CENTER, Align.CENTER]
    index = "xyz".index(axis)
    align[index] = Align.MAX if keep_below else Align.MIN
    center = [float(bounds.center().X), float(bounds.center().Y), float(bounds.center().Z)]
    center[index] = at
    keeper = Pos(*center) * Box(size, size, size, align=tuple(align))
    cut = shape & keeper

    def on_plane(face):
        normal = _vector(face.normal_at())
        middle = _vector(face.center())
        return abs(abs(normal[index]) - 1) < 1e-6 and abs(middle[index] - at) < 1e-6

    return cut, on_plane


def _triangles(shape, diagonal):
    """Tessellate face by face, coarsening until the count is bounded."""
    tolerance = max(0.02, diagonal * 0.0025)
    for _ in range(4):
        faces = []
        total = 0
        for face in shape.faces():
            vertices, triangles = face.tessellate(tolerance, 0.3)
            points = [_vector(vertex) for vertex in vertices]
            faces.append((face, points, triangles))
            total += len(triangles)
        if total <= MAX_TRIANGLES:
            return faces
        tolerance *= 2
    return faces


def _polyline(edge, frame_scale):
    """Points along a projected edge, enough to look smooth."""
    length = float(edge.length)
    if edge.geom_type.name == "LINE":
        count = 2
    else:
        count = max(8, min(96, int(length * frame_scale / 4)))
    return [(float(point.X), float(point.Y)) for point in
            (edge.position_at(index / (count - 1)) for index in range(count))]


def _font(size):
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow without a bundled scalable font
        return ImageFont.load_default()


def _round_length(length):
    if length <= 0:
        return 1.0
    power = 10 ** math.floor(math.log10(length))
    for step in (5, 2, 1):
        if step * power <= length:
            return step * power
    return power


def render(shape, view, highlight=(), focus=None):
    """One PNG of the shape; raises when the view cannot be drawn."""
    from PIL import Image, ImageDraw

    width, height = SIZES[view.get("size", "normal")]
    mode = view.get("mode", "shaded")
    bounds = shape.bounding_box()
    diagonal = math.dist(_vector(bounds.min), _vector(bounds.max))
    look_at = _vector(focus.center()) if focus is not None else _vector(bounds.center())
    frame = camera(view.get("camera", "iso"), look_at, diagonal)

    drawn = shape
    on_plane = None
    if view.get("section"):
        drawn, on_plane = _section(shape, view["section"])
        if not drawn.faces():
            raise ValueError("The section plane misses the part.")
    highlighted = [face for face in highlight]

    faces = _triangles(drawn, diagonal)
    projected_faces = []
    xs, ys = [], []
    for face, points, triangles in faces:
        projected = [_project(point, frame) for point in points]
        projected_faces.append((face, points, projected, triangles))
        xs += [point[0] for point in projected]
        ys += [point[1] for point in projected]
    if not xs:
        raise ValueError("The part has no faces to draw.")

    margin, header = 48, 34
    if focus is not None:
        box = focus.bounding_box()
        corners = [_project((x, y, z), frame) for x in (box.min.X, box.max.X)
                   for y in (box.min.Y, box.max.Y) for z in (box.min.Z, box.max.Z)]
        half_x = max(abs(corner[0]) for corner in corners) * 3 + 1
        half_y = max(abs(corner[1]) for corner in corners) * 3 + 1
        center_x, center_y = 0.0, 0.0
    else:
        half_x = (max(xs) - min(xs)) / 2 or 1.0
        half_y = (max(ys) - min(ys)) / 2 or 1.0
        center_x, center_y = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    scale = min((width / 2 - margin) / half_x, (height / 2 - margin - header / 2) / half_y)
    middle_x, middle_y = width / 2, height / 2 + header / 2

    def to_pixels(x, y):
        return (middle_x + (x - center_x) * scale, middle_y - (y - center_y) * scale)

    image = Image.new("RGB", (width, height), BACKGROUND)
    light = _unit(tuple(-frame["forward"][index] + 0.45 * frame["camera_up"][index]
                        - 0.35 * frame["right"][index] for index in range(3)))
    if mode != "hidden_line":
        polygons = []
        for face, points, projected, triangles in projected_faces:
            if on_plane is not None and on_plane(face):
                color = CAP
            elif any(face.is_same(other) for other in highlighted):
                color = ACCENT
            else:
                color = BASE
            for a, b, c in triangles:
                normal = _cross(_sub(points[b], points[a]), _sub(points[c], points[a]))
                if _dot(normal, frame["forward"]) >= 0:
                    continue  # faces away from the camera
                unit = _unit(normal)
                shade = 0.35 + 0.65 * max(0.0, _dot(unit, light))
                depth = (projected[a][2] + projected[b][2] + projected[c][2]) / 3
                polygons.append((depth, [to_pixels(*projected[i][:2]) for i in (a, b, c)],
                                 tuple(int(channel * shade) for channel in color)))
        polygons.sort(key=lambda item: -item[0])
        layer = Image.new("RGB", (width, height), BACKGROUND)
        draw = ImageDraw.Draw(layer)
        for _, corners, color in polygons:
            draw.polygon(corners, fill=color, outline=color)
        image = Image.blend(image, layer, 0.35) if mode == "xray" else layer

    draw = ImageDraw.Draw(image)
    visible, hidden = drawn.project_to_viewport(
        frame["origin"], viewport_up=frame["up"], look_at=frame["look_at"]
    )
    if mode in ("hidden_line", "xray"):
        for edge in hidden:
            line = [to_pixels(x, y) for x, y in _polyline(edge, scale)]
            for index in range(0, len(line) - 1, 2):
                draw.line(line[index:index + 2], fill=MUTED, width=1)
    for edge in visible:
        draw.line([to_pixels(x, y) for x, y in _polyline(edge, scale)], fill=INK, width=2)

    _overlays(draw, view, mode, frame, scale, width, height)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _overlays(draw, view, mode, frame, scale, width, height):
    camera_spec = view.get("camera", "iso")
    name = camera_spec if isinstance(camera_spec, str) else (
        f"az {camera_spec['azimuth']:g}, el {camera_spec['elevation']:g}")
    title = f"{name} · {mode.replace('_', ' ')}"
    if view.get("section"):
        section = view["section"]
        title += f" · section {section['axis']} = {section['at']:g} mm, {section.get('keep', 'below')} kept"
    draw.text((14, 10), title, fill=INK, font=_font(15))
    draw.text((14, height - 22), "Reference view. Measure geometry for dimensions.", fill=MUTED, font=_font(12))

    # Scale bar: a round length about a fifth of the width.
    length = _round_length(width / 5 / scale)
    pixels = length * scale
    x0, y0 = 14, height - 34
    draw.line([(x0, y0), (x0 + pixels, y0)], fill=INK, width=2)
    for x in (x0, x0 + pixels):
        draw.line([(x, y0 - 4), (x, y0 + 4)], fill=INK, width=2)
    draw.text((x0 + pixels + 6, y0 - 8), f"{length:g} mm", fill=INK, font=_font(12))

    # Axis triad in the corner.
    origin = (width - 46, height - 46)
    for label, axis in (("X", (1, 0, 0)), ("Y", (0, 1, 0)), ("Z", (0, 0, 1))):
        x, y = _dot(axis, frame["right"]), _dot(axis, frame["camera_up"])
        if abs(x) < 1e-6 and abs(y) < 1e-6:
            draw.ellipse([origin[0] - 3, origin[1] - 3, origin[0] + 3, origin[1] + 3],
                         outline=AXIS_COLORS[label])
            continue
        end = (origin[0] + 28 * x, origin[1] - 28 * y)
        draw.line([origin, end], fill=AXIS_COLORS[label], width=2)
        draw.text((end[0] + 3 * (1 if x >= 0 else -3), end[1] - 7), label,
                  fill=AXIS_COLORS[label], font=_font(12))
