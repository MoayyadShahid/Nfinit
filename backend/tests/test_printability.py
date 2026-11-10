import time

import pytest

from execution import printability_code
from execution.runner import DEFAULT_PRINT_PROFILE, validate_profile


def statuses(report) -> dict[str, str]:
    return {row["rule"]: row["status"] for row in report["findings"] if row["status"] != "unverified"}


def test_a_cube_prints_without_findings():
    report = printability_code("result = Box(10, 10, 10)")

    assert statuses(report) == {"bed_fit": "pass", "min_wall": "pass", "overhangs": "pass"}
    assert report["facts"]["wall_thickness"]["min_mm"] == pytest.approx(10)
    unverified = {row["rule"] for row in report["findings"] if row["status"] == "unverified"}
    assert unverified == {"bridges", "minimum_positive_feature_size", "warping", "strength"}


def test_a_thin_wall_fails_and_is_located():
    report = printability_code(
        "with BuildPart() as part:\n"
        "    Box(40, 40, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
        "    with Locations((0, 0, 0.6)):\n"
        "        Box(38.8, 38.8, 20, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)\n"
        "result = part.part"
    )
    wall = next(row for row in report["findings"] if row["rule"] == "min_wall")

    assert wall["status"] == "fail"
    assert wall["measured"]["p05_mm"] == pytest.approx(0.6, abs=0.01)
    assert wall["face_ids"] and wall["where"]
    assert "1.2 mm" in wall["suggestion"]


def test_an_overhang_needs_support_and_another_orientation_avoids_it():
    report = printability_code(
        "with BuildPart() as part:\n"
        "    Box(10, 10, 30, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
        "    with Locations((0, 0, 30)):\n"
        "        Box(60, 10, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
        "result = part.part"
    )
    facts = report["facts"]

    assert facts["overhangs"]["area_mm2"] == pytest.approx(500, abs=0.01)
    assert facts["orientations"][0]["overhang_area_mm2"] < 500
    assert statuses(report)["overhangs"] == "review"
    assert all(region["face_id"].startswith("face_") for region in facts["overhangs"]["largest"])


def test_bed_fit_small_holes_and_the_profile():
    big = printability_code("result = Box(300, 20, 20)")
    turned = printability_code("result = Box(20, 240, 20)", {"bed_mm": [250, 210, 200]})
    holes = printability_code(
        "with BuildPart() as part:\n    Box(30, 30, 5)\n    Hole(radius=0.5)\nresult = part.part",
        {"min_hole_mm": 1.5},
    )

    assert statuses(big)["bed_fit"] == "fail"
    assert statuses(turned)["bed_fit"] == "pass" and turned["facts"]["bed_fit"]["needs_turn"]
    assert statuses(holes)["min_hole"] == "review"
    assert holes["profile"]["min_hole_mm"] == 1.5


def test_results_repeat_and_large_parts_stay_bounded():
    code = (
        "with BuildPart() as part:\n"
        "    Box(120, 120, 6)\n"
        "    with GridLocations(8, 8, 14, 14):\n"
        "        Hole(radius=2.5)\n"
        "result = part.part"
    )
    started = time.monotonic()
    first = printability_code(code)
    elapsed = time.monotonic() - started

    assert first == printability_code(code)
    assert first["facts"]["triangles"] <= 20_000
    assert elapsed < 60


@pytest.mark.parametrize(
    "profile",
    [
        {"bed": [1, 2, 3]},
        {"bed_mm": [100, 100]},
        {"min_wall_mm": -1},
        {"overhang_limit_deg": 95},
        {"process": "laser"},
        "fdm",
    ],
)
def test_bad_profiles_are_refused(profile):
    with pytest.raises(ValueError):
        validate_profile(profile)


def test_profile_defaults_are_copied():
    profile = validate_profile(None)
    profile["bed_mm"][0] = 1

    assert DEFAULT_PRINT_PROFILE["bed_mm"][0] == 220
