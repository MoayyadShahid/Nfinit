import pytest

from execution import analyze_code, query_code
from execution.runner import validate_query

PLATE = (
    "with BuildPart() as part:\n"
    "    Box(80, 50, 6)\n"
    "    register_feature('plate', 'Plate', 'additive', part.part)\n"
    "    with GridLocations(60, 30, 2, 2):\n"
    "        Hole(radius=2)\n"
    "    register_feature('holes', 'Holes', 'pattern', part.part, parent_id='plate')\n"
    "    with Locations((0, 0, 3)):\n"
    "        Cylinder(5, 8, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
    "    register_feature('boss', 'Boss', 'additive', part.part, parent_id='plate')\n"
    "result = part.part"
)


def test_faces_are_filtered_and_owned_by_their_features():
    round_faces = query_code(PLATE, {"kind": "faces", "surface_type": "cylinder"})
    upward = query_code(PLATE, {"kind": "faces", "normal": [0, 0, 1]})

    assert sorted((face["radius_mm"], face["feature_id"]) for face in round_faces["faces"]) == [
        (2.0, "holes"), (2.0, "holes"), (2.0, "holes"), (2.0, "holes"), (5.0, "boss"),
    ]
    assert [(face["center_mm"][2], face["feature_id"]) for face in upward["faces"]] == [
        (3.0, "plate"), (11.0, "boss"),
    ]


def test_face_ids_match_the_studio_and_list_their_edges():
    hole = next(
        face for face in query_code(PLATE, {"kind": "faces", "feature_id": "holes"})["faces"]
    )
    answer = query_code(PLATE, {"kind": "face", "face_id": hole["id"]})

    assert hole["id"] in {face.id for face in analyze_code(PLATE).faces}
    assert sorted(edge["curve_type"] for edge in answer["edges"]) == ["circle", "circle", "line"]


def test_distance_between_a_feature_and_a_point():
    answer = query_code(PLATE, {"kind": "distance", "a": "boss", "b": [40, 25, 3]})

    assert answer["distance_mm"] == pytest.approx((40**2 + 25**2) ** 0.5 - 5, abs=1e-4)


def test_section_measures_area_and_loops():
    answer = query_code(PLATE, {"kind": "section", "axis": "z", "at": 0})

    assert answer["area_mm2"] == pytest.approx(80 * 50 - 4 * 3.14159265 * 4, abs=0.01)
    assert answer["loops"] == 5
    assert query_code(PLATE, {"kind": "section", "axis": "z", "at": 50})["area_mm2"] == 0


def test_unknown_face_names_real_ids():
    with pytest.raises(Exception, match="No face has id"):
        query_code(PLATE, {"kind": "face", "face_id": "face_0123456789abcdef0123"})


@pytest.mark.parametrize(
    "query",
    [
        {"kind": "everything"},
        {"kind": "faces", "limit": 500},
        {"kind": "faces", "surface_type": "nurbs"},
        {"kind": "faces", "normal": [0, 0, 0]},
        {"kind": "face", "face_id": "../../etc/passwd"},
        {"kind": "distance", "a": "boss", "b": [1, 2]},
        {"kind": "distance", "a": "boss", "b": "__class__"},
        {"kind": "section", "axis": "w", "at": 0},
        {"kind": "summary", "extra": 1},
    ],
)
def test_bad_queries_are_refused_before_the_sandbox(query):
    with pytest.raises(ValueError):
        validate_query(query)
