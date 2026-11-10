"""Each kernel pitfall in the prompt, shown on the locked build123d.

A pitfall without a test here does not belong in KERNEL_PITFALLS.
"""
from execution import inspect_code


def cylinder_z_range(code: str) -> tuple[float, float]:
    """The Z extent of the part's only hole, read from its census."""
    inspection = inspect_code(code)
    assert inspection.valid, inspection.error
    (hole,) = inspection.census["holes"]
    middle = hole["centers_mm"][0][2]
    return middle - hole["length_mm"] / 2, middle + hole["length_mm"] / 2


def test_primitives_are_centred_on_every_axis():
    inspection = inspect_code("result = Box(40, 30, 12)")

    assert inspection.bounding_box_mm == {"x": 40, "y": 30, "z": 12}
    assert inspect_code(
        "result = Box(40, 30, 12)\ncheck_measurement('bottom', result.bounding_box().min.Z, -6, 1e-6)"
    ).valid


def test_hole_cuts_its_depth_below_and_above_its_location():
    def hole(z: float, depth: float):
        return cylinder_z_range(
            "with BuildPart() as part:\n"
            "    Box(80, 50, 6)\n"
            f"    with Locations((0, 0, {z})):\n"
            f"        Hole(radius=2, depth={depth})\n"
            "result = part.part"
        )

    # From the middle of a centred 6 mm plate, a 2 mm hole is 4 mm long.
    assert hole(0, 2) == (-2, 2)
    assert hole(-1, 1) == (-2, 0)
    # Placed on the top face, it is the requested 2 mm deep.
    assert hole(3, 2) == (1, 3)


def test_a_cut_that_misses_removes_nothing_without_an_error():
    inspection = inspect_code(
        "with BuildPart() as part:\n"
        "    Box(20, 20, 5)\n"
        "    with Locations((50, 0, 0)):\n"
        "        Box(5, 5, 5, mode=Mode.SUBTRACT)\n"
        "result = part.part"
    )

    assert inspection.valid
    assert inspection.volume_mm3 == 2000


def test_features_that_miss_or_only_touch_stay_separate_solids():
    floating = inspect_code(
        "with BuildPart() as part:\n"
        "    Box(20, 20, 5)\n"
        "    with Locations((0, 0, 10)):\n"
        "        Cylinder(3, 4)\n"
        "result = part.part"
    )
    edge_touching = inspect_code(
        "with BuildPart() as part:\n"
        "    Box(10, 10, 10, align=(Align.MIN, Align.MIN, Align.MIN))\n"
        "    with Locations((10, 10, 0)):\n"
        "        Box(10, 10, 10, align=(Align.MIN, Align.MIN, Align.MIN))\n"
        "result = part.part"
    )

    assert floating.valid and floating.solid_count == 2
    assert edge_touching.valid and edge_touching.solid_count == 2


def test_a_fillet_over_half_the_wall_fails():
    inspection = inspect_code(
        "with BuildPart() as part:\n"
        "    Box(20, 20, 5)\n"
        "    fillet(part.edges(), radius=2.6)\n"
        "result = part.part"
    )

    assert not inspection.valid
    assert "Failed creating a fillet" in inspection.error


def test_a_face_from_a_clockwise_wire_extrudes_downward():
    clockwise = "[(0, 0, 0), (0, 10, 0), (10, 10, 0), (10, 0, 0)]"
    direct = inspect_code(
        f"profile = Face(Wire.make_polygon({clockwise}, close=True))\n"
        "result = extrude(profile, amount=5)\n"
        "check_measurement('bottom', result.bounding_box().min.Z, -5, 1e-6)"
    )
    sketched = inspect_code(
        "with BuildPart() as part:\n"
        "    with BuildSketch():\n"
        "        Polygon((0, 0), (0, 10), (10, 10), (10, 0), align=None)\n"
        "    extrude(amount=5)\n"
        "result = part.part\n"
        "check_measurement('bottom', result.bounding_box().min.Z, 0, 1e-6)"
    )

    assert direct.valid, direct.error
    assert sketched.valid, sketched.error
