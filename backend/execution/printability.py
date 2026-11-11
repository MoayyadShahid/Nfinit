"""Measurements that decide whether a part prints, and findings against a profile.

``measure`` returns facts with locations and face ids; ``findings`` compares
them with a printer profile. The two are separate so that a fact is never
mistaken for a verdict, and a check that could not run is reported as
unverified rather than passed. The worker loads this module by path; it must
not import anything from Nfinit. numpy is a build123d dependency.
"""

import math

ORIENTATIONS = {
    # Name: (axis, degrees) rotating the part before printing.
    "current_plus_z": None,
    "flip_180_x": ((1, 0, 0), 180),
    "rot_plus_90_x": ((1, 0, 0), 90),
    "rot_minus_90_x": ((1, 0, 0), -90),
    "rot_plus_90_y": ((0, 1, 0), 90),
    "rot_minus_90_y": ((0, 1, 0), -90),
}
WALL_SAMPLES = 2000
WALL_SEED = 42
RAY_CHUNK = 64
MAX_TRIANGLES = 20_000
# A ray leaves through the wall's other side when that face's normal is at
# least 120 degrees from the starting face's: cos 120 = -0.5.
OPPOSITE = -0.5
RESTING_MM = 0.05
LISTED = 10
NOT_MEASURED = ["bridges", "minimum positive feature size", "warping", "strength"]


def _mesh(shape, face_ids):
    """Triangles as numpy arrays, each with the index of its face."""
    import numpy as np
    from OCP.BRepTools import BRepTools

    bounds = shape.bounding_box()
    diagonal = math.dist(
        (bounds.min.X, bounds.min.Y, bounds.min.Z), (bounds.max.X, bounds.max.Y, bounds.max.Z)
    )
    tolerance = max(0.02, diagonal * 0.002)
    angular = 0.3
    for _ in range(6):
        points, triangles, owners = [], [], []
        for index, face in enumerate(shape.faces()):
            vertices, face_triangles = face.tessellate(tolerance, angular)
            offset = len(points)
            points += [(vertex.X, vertex.Y, vertex.Z) for vertex in vertices]
            triangles += [(a + offset, b + offset, c + offset) for a, b, c in face_triangles]
            owners += [index] * len(face_triangles)
        if len(triangles) <= MAX_TRIANGLES:
            break
        # Round faces keep a minimum count set by the angle, so loosen both,
        # and drop the stored mesh: the kernel reuses a finer one.
        tolerance *= 2
        angular = min(angular * 1.6, 1.2)
        BRepTools.Clean_s(shape.wrapped)
    corners = np.asarray(points, dtype=float)[np.asarray(triangles, dtype=int)]
    return corners, np.asarray(owners, dtype=int), [face_ids[index] if index < len(face_ids) else None
                                                  for index in range(len(shape.faces()))]


def _normals_and_areas(corners):
    import numpy as np

    cross = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    length = np.linalg.norm(cross, axis=1)
    safe = np.where(length > 0, length, 1.0)
    return cross / safe[:, None], length / 2


def _rotate(corners, rotation):
    import numpy as np

    if rotation is None:
        return corners
    (x, y, z), degrees = rotation
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    # Rodrigues' rotation about a unit axis.
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]], dtype=float)
    matrix = np.eye(3) + sin * k + (1 - cos) * (k @ k)
    return corners @ matrix.T


def _overhangs(corners, normals, areas, limit):
    """Triangles that face down more steeply than the limit, off the bed."""
    import numpy as np

    lowest = corners[:, :, 2].min()
    down = normals[:, 2] < 0
    angle = np.degrees(np.arccos(np.clip(-normals[:, 2], -1.0, 1.0)))
    on_bed = corners[:, :, 2].max(axis=1) <= lowest + RESTING_MM
    needs_support = down & (angle < limit) & ~on_bed
    return needs_support, lowest


def best_orientation(shape, limit=45.0):
    """The axis-aligned turn with the least overhang, then the lowest height."""
    import numpy as np

    corners, _, _ = _mesh(shape, [])
    _, areas = _normals_and_areas(corners)
    ranked = []
    for name, rotation in ORIENTATIONS.items():
        turned = _rotate(corners, rotation)
        normals, _ = _normals_and_areas(turned)
        support, low = _overhangs(turned, normals, areas, limit)
        ranked.append((round(float(areas[support].sum()), 3), round(float(turned[:, :, 2].max() - low), 3), name))
    ranked.sort()
    return ranked[0][2], ORIENTATIONS[ranked[0][2]]


def measure(shape, profile, face_ids=(), census=None):
    import numpy as np

    corners, owners, ids = _mesh(shape, list(face_ids))
    normals, areas = _normals_and_areas(corners)
    total_area = float(areas.sum())
    limit = float(profile["overhang_limit_deg"])
    facts = {"triangles": int(len(corners)), "surface_area_mm2": round(total_area, 3)}

    bounds = shape.bounding_box()
    size = [float(bounds.size.X), float(bounds.size.Y), float(bounds.size.Z)]
    bed = profile["bed_mm"]
    fits = size[0] <= bed[0] and size[1] <= bed[1] and size[2] <= bed[2]
    turned = size[1] <= bed[0] and size[0] <= bed[1] and size[2] <= bed[2]
    facts["bed_fit"] = {"size_mm": [round(value, 3) for value in size], "bed_mm": bed,
                        "fits": fits or turned, "needs_turn": not fits and turned}

    needs_support, lowest = _overhangs(corners, normals, areas, limit)
    regions = {}
    for index in np.nonzero(needs_support)[0]:
        region = regions.setdefault(int(owners[index]), {"area": 0.0, "weighted": np.zeros(3)})
        region["area"] += float(areas[index])
        region["weighted"] += corners[index].mean(axis=0) * float(areas[index])
    largest = sorted(regions.items(), key=lambda item: -item[1]["area"])[:LISTED]
    overhang_area = float(areas[needs_support].sum())
    facts["overhangs"] = {
        "limit_deg": limit,
        "area_mm2": round(overhang_area, 3),
        "share_of_surface": round(overhang_area / total_area, 4) if total_area else 0.0,
        "largest": [
            {"face_id": ids[face], "area_mm2": round(region["area"], 3),
             "centroid_mm": [round(float(value), 3) for value in region["weighted"] / region["area"]]}
            for face, region in largest
        ],
    }

    heights = corners[:, :, 2].mean(axis=1) - lowest
    projected = areas * np.abs(normals[:, 2])
    support = float((projected * heights)[needs_support].sum())
    volume = abs(float(shape.volume))
    facts["support_volume"] = {
        "estimate_mm3": round(support, 3),
        "part_volume_mm3": round(volume, 3),
        "ratio": round(support / volume, 4) if volume else None,
        "note": "An upper bound: a prism from each overhanging triangle down to the bed.",
    }

    facts["orientations"] = []
    for name, rotation in ORIENTATIONS.items():
        turned_corners = _rotate(corners, rotation)
        turned_normals, _ = _normals_and_areas(turned_corners)
        support_mask, low = _overhangs(turned_corners, turned_normals, areas, limit)
        facts["orientations"].append({
            "name": name,
            "overhang_area_mm2": round(float(areas[support_mask].sum()), 3),
            "build_height_mm": round(float(turned_corners[:, :, 2].max() - low), 3),
        })
    facts["orientations"].sort(key=lambda item: (item["overhang_area_mm2"], item["build_height_mm"]))

    facts["wall_thickness"] = _walls(corners, normals, areas, owners, ids)

    holes = (census or {}).get("holes") or []
    facts["small_holes"] = [
        {"diameter_mm": hole["diameter_mm"], "count": hole["count"], "centers_mm": hole["centers_mm"][:LISTED]}
        for hole in holes if hole["diameter_mm"] < float(profile["min_hole_mm"])
    ]
    facts["sealed_voids"] = sum(max(0, len(solid.shells()) - 1) for solid in shape.solids())
    facts["not_measured"] = NOT_MEASURED
    return facts


def _walls(corners, normals, areas, owners, ids):
    """Thickness along inward rays from area-weighted surface samples."""
    import numpy as np

    if not len(corners):
        return {"samples": 0}
    generator = np.random.default_rng(WALL_SEED)
    weights = areas / areas.sum()
    chosen = generator.choice(len(corners), size=WALL_SAMPLES, p=weights)
    r1, r2 = generator.random(WALL_SAMPLES), generator.random(WALL_SAMPLES)
    flip = r1 + r2 > 1
    r1, r2 = np.where(flip, 1 - r1, r1), np.where(flip, 1 - r2, r2)
    a, b, c = corners[chosen, 0], corners[chosen, 1], corners[chosen, 2]
    starts = a + r1[:, None] * (b - a) + r2[:, None] * (c - a)
    directions = -normals[chosen]

    edge1 = corners[:, 1] - corners[:, 0]
    edge2 = corners[:, 2] - corners[:, 0]
    distances = np.full(WALL_SAMPLES, np.inf)
    # A wall's far side faces against the ray, so each group of rays with
    # about the same direction is tested only against triangles that face
    # roughly opposite it. The exact test below still applies to every pair.
    _, groups = np.unique(np.round(directions, 1), axis=0, return_inverse=True)
    for group in np.unique(groups):
        rays = np.nonzero(groups == group)[0]
        start_normal = -directions[rays].mean(axis=0)
        start_normal /= np.linalg.norm(start_normal) or 1.0
        candidates = np.nonzero((normals * start_normal).sum(axis=1) < OPPOSITE + 0.3)[0]
        if not len(candidates):
            continue
        for begin in range(0, len(rays), RAY_CHUNK):
            chosen_rays = rays[begin:begin + RAY_CHUNK]
            distances[chosen_rays] = _first_hits(
                starts[chosen_rays], directions[chosen_rays],
                corners[candidates, 0], edge1[candidates], edge2[candidates], normals[candidates],
            )

    found = np.isfinite(distances)
    if not found.any():
        return {"samples": 0}
    values = distances[found]
    order = np.argsort(distances)[:LISTED]
    return {
        "samples": int(found.sum()),
        "min_mm": round(float(values.min()), 3),
        "p05_mm": round(float(np.percentile(values, 5)), 3),
        "median_mm": round(float(np.median(values)), 3),
        "thinnest": [
            {"thickness_mm": round(float(distances[index]), 3),
             "at_mm": [round(float(value), 3) for value in starts[index]],
             "face_id": ids[int(owners[chosen[index]])]}
            for index in order if np.isfinite(distances[index])
        ],
    }


def _first_hits(origins, directions, vertex0, edge1, edge2, normals):
    """Distance along each ray to the first triangle facing against it."""
    import numpy as np

    # Moller-Trumbore for every ray in the chunk against every triangle.
    direction = directions[:, None, :]
    p = np.cross(direction, edge2[None])
    determinant = np.einsum("rtk,tk->rt", p, edge1)
    usable = np.abs(determinant) > 1e-12
    inverse = np.where(usable, 1.0 / np.where(usable, determinant, 1.0), 0.0)
    offset = origins[:, None, :] - vertex0[None]
    u = np.einsum("rtk,rtk->rt", offset, p) * inverse
    q = np.cross(offset, edge1[None])
    v = np.einsum("rk,rtk->rt", directions, q) * inverse
    t = np.einsum("tk,rtk->rt", edge2, q) * inverse
    facing = np.einsum("rk,tk->rt", -directions, normals) < OPPOSITE
    hit = usable & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-4) & facing
    return np.where(hit, t, np.inf).min(axis=1)


def findings(facts, profile):
    """Rows comparing each fact with the profile: pass, fail, review or unverified."""
    rows = []

    def row(rule, status, measured, limit, suggestion="", where=None, face_ids=()):
        rows.append({"rule": rule, "status": status, "measured": measured, "limit": limit,
                     "where": where, "face_ids": [face for face in face_ids if face][:20],
                     "suggestion": suggestion})

    bed = facts["bed_fit"]
    printer = profile.get("printer_name") or "the printer"
    if bed["fits"]:
        row("bed_fit", "pass", bed["size_mm"], bed["bed_mm"],
            "Turn the part 90 degrees on the bed." if bed["needs_turn"] else "")
    else:
        row("bed_fit", "fail", bed["size_mm"], bed["bed_mm"],
            f"The part does not fit the {bed['bed_mm'][0]:g} × {bed['bed_mm'][1]:g} × "
            f"{bed['bed_mm'][2]:g} mm build volume of {printer}. Split it, scale it, or "
            "print on a larger printer.")

    walls = facts["wall_thickness"]
    minimum = float(profile["min_wall_mm"])
    if not walls.get("samples"):
        row("min_wall", "unverified", None, minimum, "No wall could be measured.")
    else:
        thinnest = walls["thinnest"][0] if walls["thinnest"] else {}
        if walls["p05_mm"] < minimum:
            row("min_wall", "fail", {"p05_mm": walls["p05_mm"], "min_mm": walls["min_mm"]}, minimum,
                f"Thicken the walls to at least {minimum:g} mm; the thinnest is "
                f"{walls['min_mm']:g} mm near {thinnest.get('at_mm')}.",
                thinnest.get("at_mm"), [sample["face_id"] for sample in walls["thinnest"]])
        elif walls["min_mm"] < minimum:
            row("min_wall", "review", {"p05_mm": walls["p05_mm"], "min_mm": walls["min_mm"]}, minimum,
                f"One small place is {walls['min_mm']:g} mm thick near {thinnest.get('at_mm')}: "
                "a web, a rim or a sharp edge. Check whether it matters.",
                thinnest.get("at_mm"),
                [sample["face_id"] for sample in walls["thinnest"] if sample["thickness_mm"] < minimum])
        else:
            row("min_wall", "pass", {"p05_mm": walls["p05_mm"], "min_mm": walls["min_mm"]}, minimum)

    overhangs = facts["overhangs"]
    limit = overhangs["limit_deg"]
    if overhangs["area_mm2"] <= 0:
        row("overhangs", "pass", 0.0, limit)
    else:
        best = facts["orientations"][0]
        hint = ""
        if best["name"] != "current_plus_z" and best["overhang_area_mm2"] < overhangs["area_mm2"] * 0.5:
            hint = (f" Printing it {best['name'].replace('_', ' ')} leaves "
                    f"{best['overhang_area_mm2']:g} mm² of overhang at a build height of "
                    f"{best['build_height_mm']:g} mm.")
        largest = overhangs["largest"][0]
        row("overhangs", "review", overhangs["area_mm2"], limit,
            f"{overhangs['area_mm2']:g} mm² faces down more steeply than {limit:g} degrees and needs "
            f"support; the largest area is near {largest['centroid_mm']}. Chamfer it to {limit:g} "
            "degrees or more, or reorient the part." + hint,
            largest["centroid_mm"], [region["face_id"] for region in overhangs["largest"]])

    support = facts["support_volume"]
    ratio = support["ratio"]
    if ratio is not None and ratio > float(profile["max_support_ratio"]):
        row("support_volume", "review", ratio, profile["max_support_ratio"],
            "Supports may cost more than the part. Consider another orientation.")

    small = facts["small_holes"]
    if small:
        row("min_hole", "review", [hole["diameter_mm"] for hole in small], profile["min_hole_mm"],
            f"Holes under {profile['min_hole_mm']:g} mm may close up; drill them after printing or "
            "make them larger.", small[0]["centers_mm"][0] if small[0]["centers_mm"] else None)
    if facts["sealed_voids"]:
        row("sealed_voids", "review", facts["sealed_voids"], 0,
            "A sealed cavity traps support or resin; add an opening if that matters.")
    for item in facts["not_measured"]:
        row(item.replace(" ", "_"), "unverified", None, None, "Not measured by Nfinit.")
    return rows
