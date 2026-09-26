from types import SimpleNamespace
from typing import Any

import pytest

from agent.graph import _message_text, create_cad_graph
from agent.models import ModelInspection
from agent.retrieval import RetrievedPattern


class FakeCompletions:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        content = self.responses.pop(0)
        message = SimpleNamespace(content=content, refusal=None, parsed=None)
        usage = SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=25,
            total_tokens=125,
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=usage,
        )


class FakeClient:
    def __init__(self, responses: list[str]):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


class FakeRetriever:
    backend = "fake"

    def retrieve(self, query: str, limit: int = 4):
        assert query == "Make a 10 mm cube"
        assert limit == 4
        return [
            RetrievedPattern(
                id="cube",
                title="Parameterized cube",
                summary="Create a centered box.",
                code="result = Box(size, size, size)",
                keywords=["box", "cube"],
                score=1,
                backend=self.backend,
            )
        ]


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
    graph = create_cad_graph(
        client,
        lambda _code: next(inspections),
        pattern_retriever=FakeRetriever(),
    )

    result = await graph.ainvoke(
        {
            "run_id": "test-run",
            "messages": [{"role": "user", "content": "Make a 10 mm cube"}],
            "current_code": "",
            "model_id": "anthropic/claude-opus-5",
            "supports_structured_outputs": True,
            "selection": None,
            "patterns": [],
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
        "retrieve",
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
    assert all(
        "Parameterized cube"
        in "\n".join(
            str(message["content"]) for message in request["messages"]
        )
        for request in client.chat.completions.requests
    )


def test_message_text_reads_parsed_code_when_content_is_empty():
    message = SimpleNamespace(
        content="",
        refusal=None,
        parsed=SimpleNamespace(code="result = Box(10, 10, 10)"),
    )
    assert _message_text(message) == '{"code": "result = Box(10, 10, 10)"}'


@pytest.mark.asyncio
async def test_generate_retries_when_structured_response_is_empty():
    client = FakeClient(
        [
            "Make a parameterized 10 mm cube.",
            "",
            '{"code":"result = Box(10, 10, 10)"}',
        ]
    )
    graph = create_cad_graph(
        client,
        lambda _code: ModelInspection(
            valid=True,
            shape_type="Solid",
            solid_count=1,
            volume_mm3=1000,
            bounding_box_mm={"x": 10, "y": 10, "z": 10},
        ),
        pattern_retriever=FakeRetriever(),
    )

    result = await graph.ainvoke(
        {
            "run_id": "empty-then-retry",
            "messages": [{"role": "user", "content": "Make a 10 mm cube"}],
            "current_code": "",
            "model_id": "anthropic/claude-opus-5",
            "supports_structured_outputs": True,
            "selection": None,
            "patterns": [],
            "plan": "",
            "code": "",
            "inspection": None,
            "validation_error": None,
            "repair_attempts": 0,
            "trace": [],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        }
    )

    assert result["code"] == "result = Box(10, 10, 10)"
    assert result["validation_error"] is None
    generate_requests = client.chat.completions.requests[1:]
    assert generate_requests[0]["response_format"]["json_schema"]["name"] == "cad_code"
    assert "response_format" not in generate_requests[1]
    assert generate_requests[1]["extra_body"]["reasoning"]["effort"] == "medium"
