import json
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from agent.graph import run_cad_agent
from agent.models import (
    CadRunRequest,
    ModelInspection,
    ModelUsage,
    TraceStep,
)
from execution import inspect_code

from .models import EvaluationCase, EvaluationResult, ReplayRecord
from .scoring import score_evaluation

InspectCode = Callable[[str], ModelInspection]


def _load_list(path: Path, key: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get(key) if isinstance(payload, dict) else payload
    if not isinstance(values, list):
        raise ValueError(f"{path} must contain a JSON list or a '{key}' list.")
    return values


def load_cases(path: Path) -> list[EvaluationCase]:
    cases = [EvaluationCase.model_validate(value) for value in _load_list(path, "cases")]
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path} contains duplicate evaluation case IDs.")
    return cases


def load_replays(path: Path) -> list[ReplayRecord]:
    records = [
        ReplayRecord.model_validate(value) for value in _load_list(path, "replays")
    ]
    keys = [(record.case_id, record.model_id) for record in records]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{path} contains duplicate case/model replay records.")
    return records


def filter_cases(
    cases: list[EvaluationCase],
    case_ids: set[str] | None = None,
    categories: set[str] | None = None,
) -> list[EvaluationCase]:
    return [
        case
        for case in cases
        if (not case_ids or case.id in case_ids)
        and (not categories or case.category in categories)
    ]


def evaluate_replays(
    cases: list[EvaluationCase],
    records: list[ReplayRecord],
    model_ids: list[str] | None = None,
    inspector: InspectCode = inspect_code,
) -> list[EvaluationResult]:
    record_map = {
        (record.case_id, record.model_id): record for record in records
    }
    selected_models = model_ids or sorted({record.model_id for record in records})
    results = []

    for model_id in selected_models:
        for case in cases:
            record = record_map.get((case.id, model_id))
            if record is None:
                results.append(
                    score_evaluation(
                        case,
                        model_id,
                        "",
                        ModelInspection(
                            valid=False,
                            error="Replay record is missing.",
                        ),
                        [],
                        ModelUsage(),
                        error="Replay record is missing.",
                    )
                )
                continue

            inspection = inspector(record.code)
            results.append(
                score_evaluation(
                    case,
                    model_id,
                    record.code,
                    inspection,
                    record.trace,
                    record.usage,
                )
            )
    return results


async def evaluate_live(
    cases: list[EvaluationCase],
    model_ids: list[str],
    api_key: str,
    inspector: InspectCode = inspect_code,
    structured_output_support: dict[str, bool] | None = None,
) -> list[EvaluationResult]:
    results = []
    structured_output_support = structured_output_support or {}
    for model_id in model_ids:
        # "plan+code" runs the plan step on a separate (cheaper) model.
        plan_model, _, code_model = model_id.rpartition("+")
        for case in cases:
            run_id = str(uuid4())
            request = CadRunRequest(
                messages=case.messages,
                code=case.current_code,
                modelId=code_model,
                planModelId=plan_model or None,
                supportsStructuredOutputs=structured_output_support.get(
                    model_id, True
                ),
                selection=case.selection,
            )
            try:
                state = await run_cad_agent(
                    request, api_key, inspector, run_id=run_id
                )
                inspection = ModelInspection.model_validate(
                    state["inspection"]
                    or {"valid": False, "error": "Inspection result is missing."}
                )
                trace = [
                    TraceStep.model_validate(step) for step in state["trace"]
                ]
                usage = ModelUsage.model_validate(state["usage"])
                results.append(
                    score_evaluation(
                        case,
                        model_id,
                        state["code"],
                        inspection,
                        trace,
                        usage,
                        error=state["validation_error"],
                        run_id=run_id,
                    )
                )
            except Exception as error:
                results.append(
                    score_evaluation(
                        case,
                        model_id,
                        "",
                        ModelInspection(valid=False, error=str(error)),
                        [],
                        ModelUsage(),
                        error=f"{type(error).__name__}: {str(error)}",
                        run_id=run_id,
                    )
                )
    return results


async def evaluate_local(
    cases: list[EvaluationCase],
    agent_ids: list[str],
    inspector: InspectCode = inspect_code,
) -> list[EvaluationResult]:
    """Run each case through an installed Claude Code or Codex CLI.

    This uses the developer's own CLI login and usage allowance, so it never
    runs in CI.
    """
    from agent.local import run_local_agent

    results = []
    for agent_id in agent_ids:
        for case in cases:
            run_id = str(uuid4())
            request = CadRunRequest(
                messages=case.messages,
                code=case.current_code,
                modelId=agent_id,
                selection=case.selection,
            )
            try:
                state = await run_local_agent(request, inspector, run_id=run_id)
                results.append(_score_state(case, agent_id, state, run_id))
            except Exception as error:
                state = getattr(error, "state", None)
                if state and state.get("inspection"):
                    results.append(
                        _score_state(
                            case, agent_id, state, run_id,
                            error=f"{type(error).__name__}: {error}",
                        )
                    )
                    continue
                results.append(
                    score_evaluation(
                        case,
                        agent_id,
                        "",
                        ModelInspection(valid=False, error=str(error)),
                        [],
                        ModelUsage(),
                        error=f"{type(error).__name__}: {str(error)}",
                        run_id=run_id,
                    )
                )
    return results


def _score_state(
    case: EvaluationCase,
    model_id: str,
    state: dict,
    run_id: str,
    error: str | None = None,
) -> EvaluationResult:
    inspection = ModelInspection.model_validate(
        state["inspection"]
        or {"valid": False, "error": "Inspection result is missing."}
    )
    return score_evaluation(
        case,
        model_id,
        state["code"],
        inspection,
        [TraceStep.model_validate(step) for step in state["trace"]],
        ModelUsage.model_validate(state["usage"]),
        error=error or state["validation_error"],
        run_id=run_id,
    )
