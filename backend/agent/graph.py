import asyncio
import json
import logging
import os
import re
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any, Literal, TypedDict
from uuid import uuid4

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from openai import AsyncOpenAI

from .models import CadRunRequest, ModelInspection
from .prompts import CAD_SYSTEM_PROMPT, PLANNER_PROMPT
from .retrieval import (
    PatternRetriever,
    RetrievedPattern,
    format_pattern_context,
    get_pattern_retriever,
    retrieval_limit,
)
from .tracing import RunTracer, summarize_messages, summarize_text
from .validation import extract_code, validate_code

MAX_REPAIR_ATTEMPTS = 3
# Plan + generate + up to three repairs is at most five model calls; the run
# deadline bounds all of them together, and each call has its own ceiling so
# one stalled request cannot eat the whole budget.
DEFAULT_RUN_TIMEOUT_SECONDS = 300.0
DEFAULT_LLM_TIMEOUT_SECONDS = 120.0
logger = logging.getLogger(__name__)


def run_timeout_seconds() -> float:
    return float(
        os.getenv("CAD_RUN_TIMEOUT_SECONDS", str(DEFAULT_RUN_TIMEOUT_SECONDS))
    )


class CadRunTimeoutError(TimeoutError):
    """The run hit its deadline; `state` is the last step that finished."""

    def __init__(self, seconds: float, state: "AgentState"):
        super().__init__(f"The CAD agent did not finish within {seconds:g} seconds.")
        self.state = state

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
    plan_model_id: str | None
    supports_structured_outputs: bool
    selection: dict[str, Any] | None
    patterns: list[dict[str, Any]]
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
# Receives each progress event: {"stage", "status", "message", ...}.
RunEventHandler = Callable[[dict[str, Any]], Awaitable[None]]

def _announce(stage: str, message: str, **extra: Any) -> None:
    """Tell a streaming caller that a step has started."""
    get_stream_writer()(
        {"stage": stage, "status": "started", "message": message, **extra}
    )


def plan_summary(plan: str, limit: int = 160) -> str:
    """The plan's first sentence, without Markdown markers or headings."""
    # Split sentences after a word, not after a list number such as "1.".
    for line in re.split(r"\n|(?<=[a-z)][.!?])\s+", plan):
        if line.lstrip().startswith("#"):
            continue
        text = re.sub(r"^[\s>*_`-]+|[*_`]+", "", line).strip()
        text = re.sub(r"^\d+[.)]\s+", "", text)
        # "Intent: A 250 mm frame." -> "A 250 mm frame."
        text = re.sub(r"^[A-Za-z][\w /-]{0,30}:\s*", "", text)
        if text:
            return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
    return ""


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
        )
        if selection.get("entity_id"):
            selection_text += (
                f"\n- B-rep face ID: {selection['entity_id']}"
                f"\n- surface type: {selection.get('surface_type') or 'unknown'}"
                f"\n- topology version: "
                f"{selection.get('topology_version') or 'unknown'}"
            )
        selection_text += (
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


def _retrieval_query(state: AgentState) -> str:
    content = _text_of(state["messages"][-1]["content"])
    selection = state["selection"]
    if selection:
        content += (
            "\nSelected face editing"
            f"\nSurface type: {selection.get('surface_type') or 'unknown'}"
        )
    return content[:4_000]


def _pattern_message(
    state: AgentState, *, include_code: bool = True
) -> dict[str, str] | None:
    patterns = [
        RetrievedPattern.model_validate(pattern) for pattern in state["patterns"]
    ]
    context = format_pattern_context(patterns, include_code=include_code)
    return {"role": "user", "content": context} if context else None


def _append_trace(
    state: AgentState,
    node: Literal["retrieve", "plan", "generate", "inspect", "repair"],
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


USAGE_KEYS = ("input_tokens", "output_tokens", "total_tokens", "cost_usd")


def _add_usage(state: AgentState, usage: dict[str, Any]) -> dict[str, Any]:
    return {key: state["usage"].get(key, 0) + usage.get(key, 0) for key in USAGE_KEYS}


def _message_text(message: Any) -> str:
    """Collect visible text from an OpenRouter/OpenAI chat message.

    Reasoning models often leave ``content`` empty while filling ``parsed``,
    ``refusal``, or list-shaped content parts.
    """
    parts: list[str] = []
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        parts.append(content.strip())
    elif isinstance(content, list):
        text = _text_of(content).strip()
        if text:
            parts.append(text)

    parsed = getattr(message, "parsed", None)
    if parsed is not None:
        code = getattr(parsed, "code", None)
        if isinstance(code, str) and code.strip():
            parts.append(json.dumps({"code": code.strip()}))
        elif isinstance(parsed, dict) and isinstance(parsed.get("code"), str):
            parts.append(json.dumps({"code": parsed["code"].strip()}))

    refusal = getattr(message, "refusal", None)
    if isinstance(refusal, str) and refusal.strip():
        parts.append(refusal.strip())

    return "\n".join(parts)


def _usage_of(completion: Any) -> dict[str, Any]:
    completion_usage = getattr(completion, "usage", None)
    # OpenRouter adds the call's cost in USD when usage accounting is on.
    cost = getattr(completion_usage, "cost", None)
    if cost is None:
        cost = (getattr(completion_usage, "model_extra", None) or {}).get("cost")
    return {
        "input_tokens": getattr(completion_usage, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(completion_usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(completion_usage, "total_tokens", 0) or 0,
        "cost_usd": float(cost or 0),
    }


def _model_for(state: AgentState, operation: str) -> str:
    if operation == "plan" and state.get("plan_model_id"):
        return state["plan_model_id"]
    return state["model_id"]


# Output room for one call. Only the tokens a call uses are billed.
MAX_OUTPUT_TOKENS = 32_000
# Explicit reasoning budgets for models that take one (Anthropic). With an
# effort level instead, OpenRouter reserves a share of max_tokens for
# reasoning (80% for "high"), which left too little room for the code: the
# call ended with finish_reason="length" and no content, still billed.
REASONING_BUDGETS = {"high": 8_000, "medium": 3_000}


def _completion_attempts(structured: bool) -> list[dict[str, Any]]:
    """First try the quality-first path, then drop structured JSON / high reasoning."""
    attempts: list[dict[str, Any]] = [
        {"structured": structured, "reasoning": "high", "max_tokens": MAX_OUTPUT_TOKENS},
    ]
    if structured:
        attempts.append(
            {"structured": False, "reasoning": "medium", "max_tokens": MAX_OUTPUT_TOKENS}
        )
    attempts.append(
        {"structured": False, "reasoning": None, "max_tokens": MAX_OUTPUT_TOKENS}
    )
    return attempts


def _reasoning_parameter(model: str, effort: str) -> dict[str, Any]:
    """A token budget for Anthropic models, an effort level for the others."""
    if model.startswith("anthropic/"):
        return {"max_tokens": REASONING_BUDGETS[effort]}
    return {"effort": effort}


async def _complete(
    client: AsyncOpenAI,
    state: AgentState,
    messages: list[dict[str, Any]],
    tracer: RunTracer,
    operation: str,
    structured: bool = False,
) -> CompletionResult:
    last_finish = None
    last_usage = {key: 0 for key in USAGE_KEYS}
    model = _model_for(state, operation)

    with tracer.observation(
        f"llm.{operation}",
        as_type="generation",
        input=summarize_messages(messages),
        metadata={"structured_output": structured},
        model=model,
    ) as generation:
        for attempt in _completion_attempts(structured):
            params: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "max_tokens": attempt["max_tokens"],
            }
            extra_body: dict[str, Any] = {"usage": {"include": True}}
            if attempt["reasoning"]:
                extra_body["reasoning"] = _reasoning_parameter(model, attempt["reasoning"])
            if extra_body:
                params["extra_body"] = extra_body
            if (
                attempt["structured"]
                and state["supports_structured_outputs"]
            ):
                params["response_format"] = CAD_CODE_RESPONSE_FORMAT

            completion = await client.chat.completions.create(**params)
            choice = completion.choices[0]
            content = _message_text(choice.message)
            last_finish = getattr(choice, "finish_reason", None)
            last_usage = _add_usage(
                {"usage": last_usage},
                _usage_of(completion),
            )
            if content:
                generation.update(
                    output=summarize_text(content),
                    usage_details={
                        "input": last_usage["input_tokens"],
                        "output": last_usage["output_tokens"],
                        "total": last_usage["total_tokens"],
                    },
                    metadata={
                        "finish_reason": last_finish,
                        "attempt": attempt,
                    },
                )
                return {"content": content, "usage": last_usage}

            logger.warning(
                "Empty %s completion from %s (finish_reason=%s); retrying without %s.",
                operation,
                state["model_id"],
                last_finish,
                "structured output"
                if attempt["structured"]
                else "high reasoning",
            )

        generation.update(
            output=summarize_text(""),
            level="WARNING",
            status_message="Model returned empty content after retries.",
            metadata={"finish_reason": last_finish},
        )

    raise ValueError(
        f"The {operation} model returned an empty response "
        f"(finish_reason={last_finish!r})."
    )


def create_cad_graph(
    client: AsyncOpenAI,
    inspect_code: InspectCode,
    tracer: RunTracer | None = None,
    pattern_retriever: PatternRetriever | None = None,
):
    tracer = tracer or RunTracer(str(uuid4()))
    pattern_retriever = pattern_retriever or get_pattern_retriever()

    async def retrieve(state: AgentState) -> dict[str, Any]:
        started = perf_counter()
        _announce("retrieve", "Finding build123d patterns for this request.")
        query = _retrieval_query(state)
        limit = retrieval_limit()
        with tracer.observation(
            "node.retrieve",
            as_type="retriever",
            input={"query": summarize_text(query), "limit": limit},
        ) as span:
            patterns = await asyncio.to_thread(
                pattern_retriever.retrieve, query, limit
            )
            span.update(
                output={
                    "count": len(patterns),
                    "pattern_ids": [pattern.id for pattern in patterns],
                    "backend": (
                        patterns[0].backend
                        if patterns
                        else pattern_retriever.backend
                    ),
                }
            )
        backend = (
            patterns[0].backend if patterns else pattern_retriever.backend
        )
        duration_ms = round((perf_counter() - started) * 1000)
        return {
            "patterns": [pattern.model_dump() for pattern in patterns],
            "trace": _append_trace(
                state,
                "retrieve",
                "complete",
                f"Retrieved {len(patterns)} build123d pattern(s) via {backend}.",
                duration_ms,
            ),
        }

    async def plan(state: AgentState) -> dict[str, Any]:
        started = perf_counter()
        _announce("plan", "Planning the dimensions, features and constraints.")
        pattern_message = _pattern_message(state, include_code=False)
        conversation = [
            {"role": "system", "content": PLANNER_PROMPT},
            *([pattern_message] if pattern_message else []),
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
                plan_summary(raw)
                or "Translated the request into geometry and manufacturing constraints.",
                duration_ms,
            ),
        }

    async def generate(state: AgentState) -> dict[str, Any]:
        started = perf_counter()
        _announce("generate", "Writing the build123d code.")
        pattern_message = _pattern_message(state)
        conversation = [
            {"role": "system", "content": CAD_SYSTEM_PROMPT},
            *([pattern_message] if pattern_message else []),
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
        _announce("inspect", "Building the part and checking its geometry.")
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
        _announce(
            "repair",
            "Fixing the error (attempt "
            f"{state['repair_attempts'] + 1} of {MAX_REPAIR_ATTEMPTS}).",
            attempt=state["repair_attempts"] + 1,
        )
        pattern_message = _pattern_message(state)
        conversation = [
            {"role": "system", "content": CAD_SYSTEM_PROMPT},
            *([pattern_message] if pattern_message else []),
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
        .add_node("retrieve", retrieve)
        .add_node("plan", plan)
        .add_node("generate", generate)
        .add_node("inspect", inspect)
        .add_node("repair", repair)
        .add_edge(START, "retrieve")
        .add_edge("retrieve", "plan")
        .add_edge("plan", "generate")
        .add_edge("generate", "inspect")
        .add_conditional_edges("inspect", after_inspection)
        .add_edge("repair", "inspect")
        .compile()
    )


async def _emit(on_event: RunEventHandler | None, event: dict[str, Any]) -> None:
    if on_event is None:
        return
    try:
        await on_event(event)
    except Exception:
        # Progress is a convenience; it must never fail the paid run.
        logger.warning("Could not record a run progress event.", exc_info=True)


async def run_cad_agent(
    request: CadRunRequest,
    api_key: str,
    inspect_code: InspectCode,
    run_id: str | None = None,
    timeout_seconds: float | None = None,
    on_event: RunEventHandler | None = None,
) -> AgentState:
    run_id = run_id or str(uuid4())
    timeout_seconds = timeout_seconds or run_timeout_seconds()
    tracer = RunTracer(run_id)
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=float(
            os.getenv("CAD_LLM_TIMEOUT_SECONDS", str(DEFAULT_LLM_TIMEOUT_SECONDS))
        ),
        max_retries=1,
    )
    graph = create_cad_graph(client, inspect_code, tracer)
    initial_state: AgentState = {
        "run_id": run_id,
        "messages": [message.model_dump() for message in request.messages],
        "current_code": request.code,
        "model_id": request.model_id,
        "plan_model_id": request.plan_model_id,
        "supports_structured_outputs": request.supports_structured_outputs,
        "selection": request.selection.model_dump() if request.selection else None,
        "patterns": [],
        "plan": "",
        "code": "",
        "inspection": None,
        "validation_error": None,
        "repair_attempts": 0,
        "trace": [],
        "usage": {key: 0 for key in USAGE_KEYS},
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
        result = initial_state
        try:
            async with asyncio.timeout(timeout_seconds):
                reported = 0
                async for mode, chunk in graph.astream(
                    initial_state, stream_mode=["values", "custom"]
                ):
                    if mode == "custom":
                        await _emit(on_event, chunk)
                        continue
                    result = chunk
                    # Each finished step appends one trace entry.
                    for step in result["trace"][reported:]:
                        await _emit(
                            on_event,
                            {
                                "stage": step["node"],
                                "status": step["status"],
                                "message": step["detail"],
                                "duration_ms": step.get("duration_ms"),
                            },
                        )
                    reported = len(result["trace"])
        except TimeoutError as error:
            root.update(
                level="ERROR",
                status_message=f"Run exceeded {timeout_seconds:g}s.",
                metadata={"usage": result["usage"]},
            )
            raise CadRunTimeoutError(timeout_seconds, result) from error
        root.update(
            output={
                "valid": not bool(result["validation_error"]),
                "repair_attempts": result["repair_attempts"],
                "inspection": result["inspection"],
            },
            metadata={"usage": result["usage"]},
        )
        return result
