from fastapi.testclient import TestClient

import main


def test_cad_run_exposes_agent_response(monkeypatch):
    async def fake_run_cad_agent(_request, _api_key, _inspect_code):
        return {
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
