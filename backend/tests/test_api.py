from fastapi.testclient import TestClient

import main
from execution import RevisionComparison, SandboxArtifact, TopologyAnalysis
from execution.topology import ResolvedFaceSelection


def test_health_reports_optional_services():
    client = TestClient(main.app)
    for path in ("/", "/health"):
        response = client.get(path)
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert {"openrouter", "langfuse", "pinecone", "supabase"} <= set(
            payload["services"]
        )


def test_inspection_rejects_code_that_accesses_files():
    client = TestClient(main.app)

    response = client.post(
        "/inspect-model",
        json={"code": "result = open('/etc/passwd').read()"},
    )

    assert response.status_code == 200
    assert response.json()["valid"] is False
    assert "sandbox_security_error" in response.json()["error"]


def test_analyze_model_exposes_resolved_brep_face(monkeypatch):
    def fake_analyze(code, selection):
        assert code == "result = Box(10, 10, 10)"
        assert selection.entity_id is None
        return TopologyAnalysis(
            valid=True,
            topology_version="topology-123",
            selected_face=ResolvedFaceSelection(
                face_id="face-123",
                surface_type="plane",
                distance_mm=0,
                normal_alignment=1,
                confidence=1,
            ),
        )

    monkeypatch.setattr(main, "analyze_code", fake_analyze)
    client = TestClient(main.app)
    response = client.post(
        "/analyze-model",
        json={
            "code": "result = Box(10, 10, 10)",
            "selection": {"point": [5, 0, 0], "normal": [1, 0, 0]},
        },
    )

    assert response.status_code == 200
    assert response.json()["topologyVersion"] == "topology-123"
    assert response.json()["selectedFace"] == {
        "faceId": "face-123",
        "surfaceType": "plane",
        "distanceMm": 0.0,
        "normalAlignment": 1.0,
        "confidence": 1.0,
    }


def test_compare_models_exposes_revision_matches(monkeypatch):
    def fake_compare(previous_code, current_code, previous_face_id=None):
        assert previous_code == "result = Box(10, 10, 10)"
        assert current_code == "result = Box(20, 10, 10)"
        assert previous_face_id == "face-before"
        return RevisionComparison(
            valid=True,
            previous_topology_version="before",
            current_topology_version="after",
            added_feature_ids=["new_feature"],
        )

    monkeypatch.setattr(main, "compare_code", fake_compare)
    client = TestClient(main.app)
    response = client.post(
        "/compare-models",
        json={
            "previousCode": "result = Box(10, 10, 10)",
            "currentCode": "result = Box(20, 10, 10)",
            "previousFaceId": "face-before",
        },
    )

    assert response.status_code == 200
    assert response.json()["previousTopologyVersion"] == "before"
    assert response.json()["currentTopologyVersion"] == "after"
    assert response.json()["addedFeatureIds"] == ["new_feature"]


def test_mesh_generation_uses_sandbox_artifact(monkeypatch, tmp_path):
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()
    artifact_path = artifact_dir / "model.glb"
    artifact_path.write_bytes(b"glTF-test")

    def fake_export(code, operation):
        assert code == "result = Box(1, 1, 1)"
        assert operation == "glb"
        return SandboxArtifact(path=artifact_path, temp_dir=artifact_dir)

    monkeypatch.setattr(main, "export_code", fake_export)
    client = TestClient(main.app)
    response = client.post(
        "/generate-mesh",
        json={"code": "result = Box(1, 1, 1)"},
    )

    assert response.status_code == 200
    assert response.content == b"glTF-test"
