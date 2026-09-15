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
