import asyncio
from collections.abc import Callable
from time import perf_counter
from typing import Any, Literal, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from openai import AsyncOpenAI

from .models import CadRunRequest, ModelInspection
from .prompts import CAD_SYSTEM_PROMPT, PLANNER_PROMPT
from .tracing import RunTracer, summarize_messages, summarize_text
from .validation import extract_code, validate_code

MAX_REPAIR_ATTEMPTS = 3

CAD_CODE_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "cad_code",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
            "additionalProperties": False,
        },
    },
}


class AgentState(TypedDict):
    run_id: str
    messages: list[dict[str, Any]]
    current_code: str
    model_id: str
    supports_structured_outputs: bool
    selection: dict[str, list[float]] | None
    plan: str
    code: str
    inspection: dict[str, Any] | None
    validation_error: str | None
    repair_attempts: int
    trace: list[dict[str, Any]]
    usage: dict[str, int]


class CompletionResult(TypedDict):
    content: str
    usage: dict[str, int]


InspectCode = Callable[[str], ModelInspection]


def _text_of(content: str | list[dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(
        str(part.get("text", ""))
        for part in content
        if part.get("type") == "text"
    )


def _last_user_content(state: AgentState) -> str | list[dict[str, Any]]:
    content = state["messages"][-1]["content"]
    selection = state["selection"]
    selection_text = ""
    if selection:
        point = ", ".join(str(value) for value in selection["point"])
        normal = ", ".join(str(value) for value in selection["normal"])
        selection_text = (
            "\n\nSelected face in the current model:"
            f"\n- point (mm): {point}"
            f"\n- outward normal: {normal}"
            '\nApply "this face", "here", and similar references to this face.'
        )
    code_text = (
        f"\n\nCurrent code:\n{state['current_code']}"
        if state["current_code"].strip()
        else ""
    )
    suffix = selection_text + code_text

    if isinstance(content, str):
        return content + suffix

    text = _text_of(content) + suffix
    images = [part for part in content if part.get("type") == "image_url"]
    return [{"type": "text", "text": text}, *images]


def _conversation_messages(state: AgentState) -> list[dict[str, Any]]:
    history = [
        {"role": message["role"], "content": _text_of(message["content"])}
        for message in state["messages"][:-1]
    ]
    return [
        *history,
        {"role": "user", "content": _last_user_content(state)},
    ]


def _append_trace(
    state: AgentState,
    node: Literal["plan", "generate", "inspect", "repair"],
    status: Literal["complete", "passed", "failed"],
    detail: str,
    duration_ms: int,
) -> list[dict[str, Any]]:
    return [
        *state["trace"],
        {
            "node": node,
            "status": status,
            "detail": detail,
            "duration_ms": duration_ms,
        },
    ]


def _add_usage(state: AgentState, usage: dict[str, int]) -> dict[str, int]:
    return {
        key: state["usage"].get(key, 0) + usage.get(key, 0)
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }


async def _complete(
    client: AsyncOpenAI,
    state: AgentState,
    messages: list[dict[str, Any]],
    tracer: RunTracer,
    operation: str,
    structured: bool = False,
) -> CompletionResult:
    params: dict[str, Any] = {
        "model": state["model_id"],
        "messages": messages,
        "max_tokens": 8192,
        "extra_body": {"reasoning": {"effort": "high"}},
    }
    if structured and state["supports_structured_outputs"]:
        params["response_format"] = CAD_CODE_RESPONSE_FORMAT

    with tracer.observation(
        f"llm.{operation}",
        as_type="generation",
        input=summarize_messages(messages),
        metadata={"structured_output": structured},
        model=state["model_id"],
    ) as generation:
        completion = await client.chat.completions.create(**params)
        content = (completion.choices[0].message.content or "").strip()
        completion_usage = completion.usage
        usage = {
            "input_tokens": getattr(completion_usage, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(completion_usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(completion_usage, "total_tokens", 0) or 0,
        }
        generation.update(
            output=summarize_text(content),
            usage_details={
                "input": usage["input_tokens"],
                "output": usage["output_tokens"],
                "total": usage["total_tokens"],
            },
        )
        return {"content": content, "usage": usage}


def create_cad_graph(
    client: AsyncOpenAI,
    inspect_code: InspectCode,
    tracer: RunTracer | None = None,
):
    tracer = tracer or RunTracer(str(uuid4()))

    async def plan(state: AgentState) -> dict[str, Any]:
        started = perf_counter()
        conversation = [
            {"role": "system", "content": PLANNER_PROMPT},
            *_conversation_messages(state),
        ]
        with tracer.observation(
            "node.plan",
            as_type="chain",
            input=summarize_messages(conversation),
        ) as span:
            completion = await _complete(
                client, state, conversation, tracer, "plan"
            )
            raw = completion["content"]
            span.update(output=summarize_text(raw))
        if not raw:
            raise ValueError("The planning model returned an empty response.")
        duration_ms = round((perf_counter() - started) * 1000)
        return {
            "plan": raw,
            "usage": _add_usage(state, completion["usage"]),
            "trace": _append_trace(
                state,
                "plan",
                "complete",
                "Translated the request into geometry and manufacturing constraints.",
                duration_ms,
            ),
        }

    async def generate(state: AgentState) -> dict[str, Any]:
        started = perf_counter()
        conversation = [
            {"role": "system", "content": CAD_SYSTEM_PROMPT},
            *_conversation_messages(state),
            {
                "role": "user",
                "content": f"Implement this approved design plan:\n\n{state['plan']}",
            },
        ]
        with tracer.observation(
            "node.generate",
            as_type="chain",
            input=summarize_messages(conversation),
        ) as span:
            completion = await _complete(
                client,
                state,
                conversation,
                tracer,
                "generate",
                structured=True,
            )
            raw = completion["content"]
            span.update(output=summarize_text(raw))
        if not raw:
            raise ValueError("The CAD model returned an empty response.")
        code = extract_code(raw, state["supports_structured_outputs"])
        duration_ms = round((perf_counter() - started) * 1000)
        return {
            "code": code,
            "usage": _add_usage(state, completion["usage"]),
            "trace": _append_trace(
                state,
                "generate",
                "complete",
                "Generated parameterized build123d geometry.",
                duration_ms,
            ),
        }

    async def inspect(state: AgentState) -> dict[str, Any]:
        started = perf_counter()
        with tracer.observation(
            "node.inspect",
            as_type="tool",
            input={"code": summarize_text(state["code"])},
        ) as span:
            static_error = validate_code(state["code"])
            if static_error:
                duration_ms = round((perf_counter() - started) * 1000)
                span.update(
                    output={"valid": False, "error_type": "policy"},
                    level="WARNING",
                    status_message="CAD code failed policy validation.",
                )
                return {
                    "validation_error": static_error,
                    "inspection": {"valid": False, "error": static_error},
                    "trace": _append_trace(
                        state, "inspect", "failed", static_error, duration_ms
                    ),
                }

            inspection = await asyncio.to_thread(inspect_code, state["code"])
            span.update(
                output={
                    "valid": inspection.valid,
                    "shape_type": inspection.shape_type,
                    "solid_count": inspection.solid_count,
                    "volume_mm3": inspection.volume_mm3,
                    "bounding_box_mm": inspection.bounding_box_mm,
                    "error_type": "execution" if inspection.error else None,
                },
                level="DEFAULT" if inspection.valid else "WARNING",
            )
        error = None if inspection.valid else inspection.error or "Geometry execution failed."
        dimensions = inspection.bounding_box_mm or {}
        detail = (
            f"Built {inspection.solid_count or 0} solid(s); bounds "
            f"{dimensions.get('x', '?')} × {dimensions.get('y', '?')} × "
            f"{dimensions.get('z', '?')} mm."
            if inspection.valid
            else error
        )
        duration_ms = round((perf_counter() - started) * 1000)
        return {
            "inspection": inspection.model_dump(),
            "validation_error": error,
            "trace": _append_trace(
                state,
                "inspect",
                "passed" if inspection.valid else "failed",
                detail,
                duration_ms,
            ),
        }

    async def repair(state: AgentState) -> dict[str, Any]:
        started = perf_counter()
        conversation = [
            {"role": "system", "content": CAD_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Design plan:\n{state['plan']}\n\n"
                    "The following build123d code failed execution or validation:\n\n"
                    f"{state['code']}\n\nFailure:\n{state['validation_error']}\n\n"
                    "Repair the code while preserving the design intent. "
                    "Return the complete corrected code."
                ),
            },
        ]
        with tracer.observation(
            "node.repair",
            as_type="chain",
            input={
                **summarize_messages(conversation),
                "attempt": state["repair_attempts"] + 1,
            },
        ) as span:
            completion = await _complete(
                client,
                state,
                conversation,
                tracer,
                "repair",
                structured=True,
            )
            raw = completion["content"]
            span.update(output=summarize_text(raw))
        if not raw:
            raise ValueError("The repair model returned an empty response.")
        attempt = state["repair_attempts"] + 1
        duration_ms = round((perf_counter() - started) * 1000)
        return {
            "code": extract_code(raw, state["supports_structured_outputs"]),
            "repair_attempts": attempt,
            "usage": _add_usage(state, completion["usage"]),
            "trace": _append_trace(
                state,
                "repair",
                "complete",
                f"Repaired geometry after validation failure "
                f"(attempt {attempt}/{MAX_REPAIR_ATTEMPTS}).",
                duration_ms,
            ),
        }

    def after_inspection(state: AgentState) -> str:
        if not state["validation_error"]:
            return END
        return "repair" if state["repair_attempts"] < MAX_REPAIR_ATTEMPTS else END

    return (
        StateGraph(AgentState)
        .add_node("plan", plan)
        .add_node("generate", generate)
        .add_node("inspect", inspect)
        .add_node("repair", repair)
        .add_edge(START, "plan")
        .add_edge("plan", "generate")
        .add_edge("generate", "inspect")
        .add_conditional_edges("inspect", after_inspection)
        .add_edge("repair", "inspect")
        .compile()
    )


async def run_cad_agent(
    request: CadRunRequest,
    api_key: str,
    inspect_code: InspectCode,
    run_id: str | None = None,
) -> AgentState:
    run_id = run_id or str(uuid4())
    tracer = RunTracer(run_id)
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    graph = create_cad_graph(client, inspect_code, tracer)
    initial_state: AgentState = {
        "run_id": run_id,
        "messages": [message.model_dump() for message in request.messages],
        "current_code": request.code,
        "model_id": request.model_id,
        "supports_structured_outputs": request.supports_structured_outputs,
        "selection": (
            {
                "point": list(request.selection.point),
                "normal": list(request.selection.normal),
            }
            if request.selection
            else None
        ),
        "plan": "",
        "code": "",
        "inspection": None,
        "validation_error": None,
        "repair_attempts": 0,
        "trace": [],
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }
    with tracer.observation(
        "nfinit.cad.run",
        as_type="agent",
        input={
            "request": summarize_messages(initial_state["messages"]),
            "current_code": summarize_text(request.code),
            "has_selection": request.selection is not None,
        },
        metadata={"model": request.model_id},
        root=True,
    ) as root:
        result = await graph.ainvoke(initial_state)
        root.update(
            output={
                "valid": not bool(result["validation_error"]),
                "repair_attempts": result["repair_attempts"],
                "inspection": result["inspection"],
            },
            metadata={"usage": result["usage"]},
        )
        return result
