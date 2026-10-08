import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from agent.graph import (
    CadRunTimeoutError,
    _message_text,
    create_cad_graph,
    run_cad_agent,
)
from agent.models import CadRunRequest, ModelInspection
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
        "cost_usd": 0.0,  # the fake client reports no cost
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
    # Anthropic models get a reasoning token budget, not an effort level.
    assert generate_requests[1]["extra_body"]["reasoning"] == {"max_tokens": 3_000}


class SlowAfterPlanCompletions(FakeCompletions):
    async def create(self, **kwargs):
        if self.requests:
            await asyncio.sleep(30)
        return await super().create(**kwargs)


@pytest.mark.asyncio
async def test_run_deadline_keeps_the_last_finished_step(monkeypatch):
    client = FakeClient(["Make a parameterized 10 mm cube."])
    client.chat.completions = SlowAfterPlanCompletions(
        ["Make a parameterized 10 mm cube."]
    )
    monkeypatch.setattr("agent.graph.AsyncOpenAI", lambda **_kwargs: client)
    request = CadRunRequest(
        messages=[{"role": "user", "content": "Make a 10 mm cube"}],
        modelId="anthropic/claude-opus-5",
    )

    with pytest.raises(CadRunTimeoutError) as raised:
        await run_cad_agent(
            request,
            "test-key",
            lambda _code: ModelInspection(valid=True),
            run_id="deadline-run",
            timeout_seconds=0.5,
        )

    assert raised.value.state["plan"] == "Make a parameterized 10 mm cube."
    assert raised.value.state["usage"]["total_tokens"] == 125


def _repairing_run(monkeypatch):
    client = FakeClient(
        [
            "## Intent\n**Intent:** A 10 mm cube. Centered on the origin.",
            '{"code":"result = broken_shape"}',
            '{"code":"result = Box(10, 10, 10)"}',
        ]
    )
    monkeypatch.setattr("agent.graph.AsyncOpenAI", lambda **_kwargs: client)
    monkeypatch.setattr("agent.graph.get_pattern_retriever", FakeRetriever)
    inspections = iter(
        [
            ModelInspection(valid=False, error="NameError: broken_shape"),
            ModelInspection(
                valid=True, solid_count=1, bounding_box_mm={"x": 10, "y": 10, "z": 10}
            ),
        ]
    )
    request = CadRunRequest(
        messages=[{"role": "user", "content": "Make a 10 mm cube"}],
        modelId="anthropic/claude-opus-5",
        supportsStructuredOutputs=True,
    )
    return request, lambda _code: next(inspections)


@pytest.mark.asyncio
async def test_run_reports_each_step_as_it_starts_and_finishes(monkeypatch):
    request, inspect = _repairing_run(monkeypatch)
    events: list[dict[str, Any]] = []

    async def record(event):
        events.append(event)

    result = await run_cad_agent(
        request, "test-key", inspect, run_id="progress-run", on_event=record
    )

    assert result["validation_error"] is None
    assert [(event["stage"], event["status"]) for event in events] == [
        ("retrieve", "started"),
        ("retrieve", "complete"),
        ("plan", "started"),
        ("plan", "complete"),
        ("generate", "started"),
        ("generate", "complete"),
        ("inspect", "started"),
        ("inspect", "failed"),
        ("repair", "started"),
        ("repair", "complete"),
        ("inspect", "started"),
        ("inspect", "passed"),
    ]
    plan_done = events[3]
    assert plan_done["message"] == "A 10 mm cube."
    assert events[8]["attempt"] == 1
    assert "attempt 1 of 3" in events[8]["message"]
    assert events[7]["message"] == "NameError: broken_shape"
    assert all(
        isinstance(event["duration_ms"], int)
        for event in events
        if event["status"] != "started"
    )


@pytest.mark.asyncio
async def test_failing_progress_handler_does_not_fail_the_run(monkeypatch):
    request, inspect = _repairing_run(monkeypatch)

    async def broken(_event):
        raise RuntimeError('relation "public.run_events" does not exist')

    result = await run_cad_agent(
        request, "test-key", inspect, run_id="progress-run", on_event=broken
    )

    assert result["validation_error"] is None
    assert result["code"] == "result = Box(10, 10, 10)"


class CostingCompletions(FakeCompletions):
    async def create(self, **kwargs):
        completion = await super().create(**kwargs)
        completion.usage.cost = 0.0125
        return completion


@pytest.mark.asyncio
async def test_plan_step_can_use_its_own_model_and_cost_is_reported(monkeypatch):
    client = FakeClient([])
    client.chat.completions = CostingCompletions(
        ["A 10 mm cube.", '{"code":"result = Box(10, 10, 10)"}']
    )
    monkeypatch.setattr("agent.graph.AsyncOpenAI", lambda **_kwargs: client)
    monkeypatch.setattr("agent.graph.get_pattern_retriever", FakeRetriever)
    request = CadRunRequest(
        messages=[{"role": "user", "content": "Make a 10 mm cube"}],
        modelId="anthropic/claude-opus-5.5",
        planModelId="openai/gpt-5.6-luna",
        supportsStructuredOutputs=True,
    )

    result = await run_cad_agent(
        request, "test-key", lambda _code: ModelInspection(valid=True), run_id="mixed"
    )

    requests = client.chat.completions.requests
    assert [call["model"] for call in requests] == [
        "openai/gpt-5.6-luna",
        "anthropic/claude-opus-5.5",
    ]
    assert all(call["extra_body"]["usage"] == {"include": True} for call in requests)
    assert result["usage"]["cost_usd"] == pytest.approx(0.025)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "reasoning"),
    [
        ("anthropic/claude-sonnet-5.5", {"max_tokens": 8_000}),
        ("openai/gpt-5.6-sol", {"effort": "high"}),
    ],
)
async def test_reasoning_leaves_room_for_the_answer(monkeypatch, model, reasoning):
    from agent.graph import MAX_OUTPUT_TOKENS

    client = FakeClient(["A 10 mm cube.", '{"code":"result = Box(10, 10, 10)"}'])
    monkeypatch.setattr("agent.graph.AsyncOpenAI", lambda **_kwargs: client)
    monkeypatch.setattr("agent.graph.get_pattern_retriever", FakeRetriever)
    request = CadRunRequest(
        messages=[{"role": "user", "content": "Make a 10 mm cube"}],
        modelId=model,
        supportsStructuredOutputs=True,
    )

    await run_cad_agent(
        request, "test-key", lambda _code: ModelInspection(valid=True), run_id="budget"
    )

    for call in client.chat.completions.requests:
        assert call["extra_body"]["reasoning"] == reasoning
        assert call["max_tokens"] == MAX_OUTPUT_TOKENS
    if "max_tokens" in reasoning:
        # The answer keeps at least three quarters of the output room.
        assert reasoning["max_tokens"] <= MAX_OUTPUT_TOKENS / 4
