import asyncio
from collections.abc import Callable
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from openai import AsyncOpenAI

from .models import CadRunRequest, ModelInspection
from .prompts import CAD_SYSTEM_PROMPT, PLANNER_PROMPT
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
    trace: list[dict[str, str]]


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
) -> list[dict[str, str]]:
    return [*state["trace"], {"node": node, "status": status, "detail": detail}]


async def _complete(
    client: AsyncOpenAI,
    state: AgentState,
    messages: list[dict[str, Any]],
    structured: bool = False,
) -> str:
    params: dict[str, Any] = {
        "model": state["model_id"],
        "messages": messages,
        "max_tokens": 8192,
        "extra_body": {"reasoning": {"effort": "high"}},
    }
    if structured and state["supports_structured_outputs"]:
        params["response_format"] = CAD_CODE_RESPONSE_FORMAT

    completion = await client.chat.completions.create(**params)
    return (completion.choices[0].message.content or "").strip()


def create_cad_graph(client: AsyncOpenAI, inspect_code: InspectCode):
    async def plan(state: AgentState) -> dict[str, Any]:
        raw = await _complete(
            client,
            state,
            [
                {"role": "system", "content": PLANNER_PROMPT},
                *_conversation_messages(state),
            ],
        )
        if not raw:
            raise ValueError("The planning model returned an empty response.")
        return {
            "plan": raw,
            "trace": _append_trace(
                state,
                "plan",
                "complete",
                "Translated the request into geometry and manufacturing constraints.",
            ),
        }

    async def generate(state: AgentState) -> dict[str, Any]:
        raw = await _complete(
            client,
            state,
            [
                {"role": "system", "content": CAD_SYSTEM_PROMPT},
                *_conversation_messages(state),
                {
                    "role": "user",
                    "content": f"Implement this approved design plan:\n\n{state['plan']}",
                },
            ],
            structured=True,
        )
        if not raw:
            raise ValueError("The CAD model returned an empty response.")
        return {
            "code": extract_code(raw, state["supports_structured_outputs"]),
            "trace": _append_trace(
                state,
                "generate",
                "complete",
                "Generated parameterized build123d geometry.",
            ),
        }

    async def inspect(state: AgentState) -> dict[str, Any]:
        static_error = validate_code(state["code"])
        if static_error:
            return {
                "validation_error": static_error,
                "inspection": {"valid": False, "error": static_error},
                "trace": _append_trace(
                    state, "inspect", "failed", static_error
                ),
            }

        inspection = await asyncio.to_thread(inspect_code, state["code"])
        error = None if inspection.valid else inspection.error or "Geometry execution failed."
        dimensions = inspection.bounding_box_mm or {}
        detail = (
            f"Built {inspection.solid_count or 0} solid(s); bounds "
            f"{dimensions.get('x', '?')} × {dimensions.get('y', '?')} × "
            f"{dimensions.get('z', '?')} mm."
            if inspection.valid
            else error
        )
        return {
            "inspection": inspection.model_dump(),
            "validation_error": error,
            "trace": _append_trace(
                state,
                "inspect",
                "passed" if inspection.valid else "failed",
                detail,
            ),
        }

    async def repair(state: AgentState) -> dict[str, Any]:
        raw = await _complete(
            client,
            state,
            [
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
            ],
            structured=True,
        )
        if not raw:
            raise ValueError("The repair model returned an empty response.")
        attempt = state["repair_attempts"] + 1
        return {
            "code": extract_code(raw, state["supports_structured_outputs"]),
            "repair_attempts": attempt,
            "trace": _append_trace(
                state,
                "repair",
                "complete",
                f"Repaired geometry after validation failure "
                f"(attempt {attempt}/{MAX_REPAIR_ATTEMPTS}).",
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
    request: CadRunRequest, api_key: str, inspect_code: InspectCode
) -> AgentState:
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    graph = create_cad_graph(client, inspect_code)
    initial_state: AgentState = {
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
    }
    return await graph.ainvoke(initial_state)
