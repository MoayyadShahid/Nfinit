from fastapi.testclient import TestClient

import main
from execution import SandboxArtifact, TopologyAnalysis
from execution.topology import ResolvedFaceSelection


def test_cad_run_exposes_agent_response(monkeypatch):
    async def fake_run_cad_agent(_request, _api_key, _inspect_code, run_id=None):
        return {
            "run_id": run_id,
            "code": "result = Box(10, 10, 10)",
            "plan": "Create a 10 mm cube.",
            "inspection": {
                "valid": True,
                "shape_type": "Solid",
                "solid_count": 1,
                "volume_mm3": 1000,
                "bounding_box_mm": {"x": 10, "y": 10, "z": 10},
                "error": None,
            },
            "validation_error": None,
            "repair_attempts": 0,
            "trace": [
                {
                    "node": "inspect",
                    "status": "passed",
                    "detail": "Built 1 solid.",
                }
            ],
            "usage": {
                "input_tokens": 100,
                "output_tokens": 25,
                "total_tokens": 125,
            },
        }

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(main, "run_cad_agent", fake_run_cad_agent)
    client = TestClient(main.app)

    response = client.post(
        "/cad/run",
        json={
            "messages": [{"role": "user", "content": "Make a cube"}],
            "code": "",
            "modelId": "anthropic/claude-opus-5",
            "supportsStructuredOutputs": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["inspection"]["bounding_box_mm"]["x"] == 10
    assert response.json()["runId"]
    assert response.json()["usage"]["total_tokens"] == 125


def test_cad_run_requires_user_message(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    client = TestClient(main.app)

    response = client.post(
        "/cad/run",
        json={
            "messages": [{"role": "assistant", "content": "code"}],
            "modelId": "anthropic/claude-opus-5",
        },
    )

    assert response.status_code == 400


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
