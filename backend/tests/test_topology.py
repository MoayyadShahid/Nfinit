import importlib.util

import pytest

from agent.models import FaceSelection
from execution import analyze_code


pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("build123d") is None,
    reason="build123d runtime is not installed",
)


def test_topology_ids_are_deterministic_for_identical_brep_geometry():
    first = analyze_code("result = Box(10, 20, 30)")
    second = analyze_code("result = Box(10, 20, 30)")

    assert first.valid
    assert first.topology_version == second.topology_version
    assert len(first.faces) == 6
    assert len(first.edges) == 12
    assert [face.id for face in first.faces] == [
        face.id for face in second.faces
    ]
    assert [edge.id for edge in first.edges] == [
        edge.id for edge in second.edges
    ]
    assert all(face.edge_ids for face in first.faces)


def test_topology_resolves_planar_selection_by_point_and_outward_normal():
    analysis = analyze_code(
        "result = Box(10, 20, 30)",
        FaceSelection(point=(5, 0, 0), normal=(1, 0, 0)),
    )

    assert analysis.valid
    assert analysis.selected_face is not None
    assert analysis.selected_face.face_id in {
        face.id for face in analysis.faces
    }
    assert analysis.selected_face.surface_type == "plane"
    assert analysis.selected_face.distance_mm == pytest.approx(0, abs=1e-6)
    assert analysis.selected_face.normal_alignment == pytest.approx(1)
    assert analysis.selected_face.confidence == pytest.approx(1)


def test_topology_resolves_curved_cylindrical_face():
    analysis = analyze_code(
        "result = Cylinder(5, 10)",
        FaceSelection(point=(5, 0, 0), normal=(1, 0, 0)),
    )

    assert analysis.valid
    assert analysis.selected_face is not None
    assert analysis.selected_face.surface_type == "cylinder"
    assert analysis.selected_face.confidence > 0.99


def test_topology_rejects_unsafe_code_before_worker_execution():
    analysis = analyze_code("result = open('/etc/passwd').read()")

    assert not analysis.valid
    assert "sandbox_security_error" in analysis.error


def test_explicit_feature_tree_attributes_surviving_brep_faces():
    analysis = analyze_code(
        """
width, depth, height = 20.0, 16.0, 4.0
hole_radius = 3.0
with BuildPart() as part:
    Box(width, depth, height)
    register_feature(
        "base_plate",
        "Base plate",
        "additive",
        part.part,
        parameters={"width": width, "depth": depth, "height": height},
    )
    Hole(hole_radius, depth=height)
    register_feature(
        "center_hole",
        "Center hole",
        "subtractive",
        part.part,
        parent_id="base_plate",
        parameters={"radius": hole_radius},
    )
result = part.part
"""
    )

    assert analysis.valid
    assert [feature.id for feature in analysis.features] == [
        "base_plate",
        "center_hole",
    ]
    assert analysis.features[1].parent_id == "base_plate"
    assert analysis.features[0].parameters["width"] == 20
    owned_faces = {
        face_id
        for feature in analysis.features
        for face_id in feature.owned_face_ids
    }
    assert owned_faces == {face.id for face in analysis.faces}
    assert analysis.unassigned_face_ids == []


def test_authored_feature_ids_survive_parameter_changes():
    template = """
size = {size}
with BuildPart() as part:
    Box(size, 10, 5)
    register_feature(
        "main_body",
        "Main body",
        "additive",
        part.part,
        parameters={{"size": size}},
    )
result = part.part
"""

    first = analyze_code(template.format(size=20))
    second = analyze_code(template.format(size=30))

    assert first.topology_version != second.topology_version
    assert [feature.id for feature in first.features] == ["main_body"]
    assert [feature.id for feature in second.features] == ["main_body"]


def test_legacy_code_reports_unassigned_faces_without_inventing_history():
    analysis = analyze_code("result = Box(10, 20, 30)")

    assert analysis.features == []
    assert analysis.unassigned_face_ids == [face.id for face in analysis.faces]


def test_duplicate_feature_ids_fail_validation_in_worker():
    analysis = analyze_code(
        """
with BuildPart() as part:
    Box(10, 10, 10)
    register_feature("body", "Body", "additive", part.part)
    register_feature("body", "Duplicate", "other", part.part)
result = part.part
"""
    )

    assert not analysis.valid
    assert "duplicated" in analysis.error


def test_semantic_feature_count_is_bounded():
    registrations = "\n".join(
        f'register_feature("feature_{index}", "Feature {index}", '
        '"reference", result)'
        for index in range(65)
    )

    analysis = analyze_code(f"result = Box(10, 10, 10)\n{registrations}")

    assert not analysis.valid
    assert "at most 64 features" in analysis.error


def test_semantic_constraints_capture_authored_design_intent():
    analysis = analyze_code(
        """
width, depth, thickness = 30.0, 20.0, 4.0
with BuildPart() as part:
    Box(width, depth, thickness)
    register_feature(
        "base_plate",
        "Base plate",
        "additive",
        part.part,
        parameters={"width": width, "depth": depth, "thickness": thickness},
    )
register_constraint(
    "plate_thickness",
    "thickness",
    ["base_plate"],
    parameters={"parameter": "thickness", "value": thickness, "unit": "mm"},
)
result = part.part
"""
    )

    assert analysis.valid
    assert len(analysis.constraints) == 1
    constraint = analysis.constraints[0]
    assert constraint.id == "plate_thickness"
    assert constraint.kind == "thickness"
    assert constraint.feature_ids == ["base_plate"]
    assert constraint.parameters["value"] == 4
    assert constraint.sequence == 0


def test_semantic_constraint_rejects_unknown_feature_reference():
    analysis = analyze_code(
        """
result = Box(10, 10, 10)
register_constraint("width", "distance", ["missing"], {"value": 10})
"""
    )

    assert not analysis.valid
    assert "unknown IDs: missing" in analysis.error


def test_dimensional_constraint_requires_finite_numeric_value():
    analysis = analyze_code(
        """
result = Box(10, 10, 10)
register_feature("body", "Body", "additive", result)
register_constraint("width", "distance", ["body"], {"value": "ten"})
"""
    )

    assert not analysis.valid
    assert "requires a finite numeric value" in analysis.error


def test_semantic_constraint_count_is_bounded():
    registrations = "\n".join(
        f'register_constraint("constraint_{index}", "fixed", ["body"])'
        for index in range(129)
    )
    analysis = analyze_code(
        "result = Box(10, 10, 10)\n"
        'register_feature("body", "Body", "additive", result)\n'
        f"{registrations}"
    )

    assert not analysis.valid
    assert "at most 128 constraints" in analysis.error
