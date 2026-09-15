from types import SimpleNamespace
from typing import Any

import pytest

from agent.graph import create_cad_graph
from agent.models import ModelInspection


class FakeCompletions:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        content = self.responses.pop(0)
        message = SimpleNamespace(content=content)
        usage = SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=25,
            total_tokens=125,
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=usage,
        )


class FakeClient:
    def __init__(self, responses: list[str]):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


@pytest.mark.asyncio
async def test_graph_repairs_failed_geometry_and_reinspects():
    client = FakeClient(
        [
            "Make a parameterized 10 mm cube.",
            '{"code":"result = broken_shape"}',
            '{"code":"result = Box(10, 10, 10)"}',
        ]
    )
    inspections = iter(
        [
            ModelInspection(valid=False, error="NameError: broken_shape"),
            ModelInspection(
                valid=True,
                shape_type="Solid",
                solid_count=1,
                volume_mm3=1000,
                bounding_box_mm={"x": 10, "y": 10, "z": 10},
            ),
        ]
    )
    graph = create_cad_graph(client, lambda _code: next(inspections))

    result = await graph.ainvoke(
        {
            "run_id": "test-run",
            "messages": [{"role": "user", "content": "Make a 10 mm cube"}],
            "current_code": "",
            "model_id": "anthropic/claude-opus-5",
            "supports_structured_outputs": True,
            "selection": None,
            "plan": "",
            "code": "",
            "inspection": None,
            "validation_error": None,
            "repair_attempts": 0,
            "trace": [],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }
    )

    assert result["validation_error"] is None
    assert result["repair_attempts"] == 1
    assert result["code"] == "result = Box(10, 10, 10)"
    assert [step["node"] for step in result["trace"]] == [
        "plan",
        "generate",
        "inspect",
        "repair",
        "inspect",
    ]
    assert len(client.chat.completions.requests) == 3
    assert result["usage"] == {
        "input_tokens": 300,
        "output_tokens": 75,
        "total_tokens": 375,
    }
    assert all(step["duration_ms"] >= 0 for step in result["trace"])
