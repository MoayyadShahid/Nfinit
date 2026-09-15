import importlib.util

import pytest

from execution import compare_analyses, compare_code
from execution.topology import TopologyAnalysis, TopologyBounds, TopologyFace


pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d runtime is not installed",
)

REVISION_TEMPLATE = """
width, depth, thickness = {width}, 20.0, 4.0
with BuildPart() as part:
    Box(width, depth, thickness)
    register_feature(
        "base_plate",
        "Base plate",
        "additive",
        part.part,
        parameters={{"width": width, "depth": depth, "thickness": thickness}},
    )
register_constraint(
    "plate_width",
    "distance",
    ["base_plate"],
    parameters={{"parameter": "width", "value": width, "unit": "mm"}},
)
result = part.part
"""


def test_authored_features_and_constraints_match_across_parameter_edit():
    comparison = compare_code(
        REVISION_TEMPLATE.format(width=30),
        REVISION_TEMPLATE.format(width=45),
    )

    assert comparison.valid
    assert comparison.previous_topology_version != comparison.current_topology_version
    assert len(comparison.feature_matches) == 1
    feature = comparison.feature_matches[0]
    assert feature.previous_id == feature.current_id == "base_plate"
    assert feature.status == "modified"
    assert feature.confidence == 1
    assert {"parameters", "geometry"} <= set(feature.changes)
    constraint = comparison.constraint_matches[0]
    assert constraint.previous_id == constraint.current_id == "plate_width"
    assert constraint.status == "modified"
    assert constraint.changes == ["parameters"]
    assert comparison.constraint_evaluations[0].status == "satisfied"
    assert comparison.face_matches
    assert all(
        match.previous_feature_id == match.current_feature_id == "base_plate"
        for match in comparison.face_matches
    )


def test_identical_revision_preserves_exact_face_identity():
    code = REVISION_TEMPLATE.format(width=30)

    comparison = compare_code(code, code)

    assert comparison.valid
    assert comparison.feature_matches[0].status == "unchanged"
    assert comparison.constraint_matches[0].status == "unchanged"
    assert len(comparison.face_matches) == 6
    assert all(match.status == "unchanged" for match in comparison.face_matches)
    assert all(
        match.reason == "exact_geometry" for match in comparison.face_matches
    )
    assert comparison.unmatched_previous_face_ids == []
    assert comparison.unmatched_current_face_ids == []


def test_renamed_authored_ids_are_reported_as_removed_and_added():
    previous = REVISION_TEMPLATE.format(width=30)
    current = previous.replace("base_plate", "renamed_plate").replace(
        "plate_width", "renamed_width"
    )

    comparison = compare_code(previous, current)

    assert comparison.feature_matches == []
    assert comparison.removed_feature_ids == ["base_plate"]
    assert comparison.added_feature_ids == ["renamed_plate"]
    assert comparison.constraint_matches == []
    assert comparison.removed_constraint_ids == ["plate_width"]
    assert comparison.added_constraint_ids == ["renamed_width"]


def test_legacy_faces_rematch_geometrically_without_inventing_features():
    comparison = compare_code(
        "result = Box(10, 20, 30)",
        "result = Box(15, 20, 30)",
    )

    assert comparison.valid
    assert comparison.feature_matches == []
    assert len(comparison.face_matches) == 6
    assert all(match.reason == "legacy_geometry" for match in comparison.face_matches)
    assert comparison.unmatched_previous_face_ids == []
    assert comparison.unmatched_current_face_ids == []


def _ambiguous_face(face_id: str) -> TopologyFace:
    return TopologyFace(
        id=face_id,
        surface_type="plane",
        area_mm2=100,
        center_mm=(0, 0, 0),
        normal=(0, 0, 1),
        bounds_mm=TopologyBounds(
            minimum=(-5, -5, 0), maximum=(5, 5, 0)
        ),
        edge_ids=["edge-a", "edge-b", "edge-c", "edge-d"],
    )


def test_ambiguous_geometry_is_left_unmatched_instead_of_guessed():
    previous = TopologyAnalysis(
        valid=True,
        topology_version="before",
        faces=[_ambiguous_face("before-a"), _ambiguous_face("before-b")],
    )
    current = TopologyAnalysis(
        valid=True,
        topology_version="after",
        faces=[_ambiguous_face("after-a"), _ambiguous_face("after-b")],
    )

    comparison = compare_analyses(
        previous, current, previous_face_id="before-a"
    )

    assert comparison.face_matches == []
    assert comparison.ambiguous_previous_face_ids == ["before-a", "before-b"]
    assert comparison.ambiguous_current_face_ids == ["after-a", "after-b"]
    assert comparison.unmatched_previous_face_ids == ["before-a", "before-b"]
    assert comparison.unmatched_current_face_ids == ["after-a", "after-b"]
    assert comparison.selection_remap.status == "ambiguous"


def test_selected_face_is_remapped_to_current_revision():
    code = REVISION_TEMPLATE.format(width=30)
    first = compare_code(code, code)
    previous_face_id = first.face_matches[0].previous_face_id

    comparison = compare_code(
        code,
        REVISION_TEMPLATE.format(width=32),
        previous_face_id=previous_face_id,
    )

    assert comparison.selection_remap is not None
    assert comparison.selection_remap.status == "matched"
    assert comparison.selection_remap.current_face_id
    assert comparison.selection_remap.confidence > 0


def test_constraint_evaluation_detects_parameter_drift():
    previous = REVISION_TEMPLATE.format(width=30)
    current = REVISION_TEMPLATE.format(width=45).replace(
        '"value": width', '"value": 30'
    )

    comparison = compare_code(previous, current)

    evaluation = comparison.constraint_evaluations[0]
    assert evaluation.constraint_id == "plate_width"
    assert evaluation.status == "violated"
    assert evaluation.expected == 30
    assert evaluation.actual == 45


def test_geometric_relation_is_explicitly_unevaluated():
    code = """
with BuildPart() as part:
    Box(20, 20, 5)
    register_feature("plate", "Plate", "additive", part.part)
    Hole(3, depth=5)
    register_feature("hole", "Hole", "subtractive", part.part)
register_constraint("alignment", "concentric", ["plate", "hole"])
result = part.part
"""

    comparison = compare_code(code, code)

    evaluation = comparison.constraint_evaluations[0]
    assert evaluation.constraint_id == "alignment"
    assert evaluation.status == "unevaluated"


def test_invalid_revision_returns_comparison_error():
    comparison = compare_code(
        "result = open('/etc/passwd').read()",
        "result = Box(10, 10, 10)",
    )

    assert not comparison.valid
    assert "Previous revision: sandbox_security_error" in comparison.error
