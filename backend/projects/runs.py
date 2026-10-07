"""Background CAD runs.

`POST /cad/runs` records the run and returns immediately; the agent keeps
working after the HTTP request ends. A successful run is saved into the
user's project server-side, so the result survives a closed tab, a dropped
connection or a proxy timeout. A failed run keeps its last attempt.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field

from agent import (
    MAX_REPAIR_ATTEMPTS,
    CadRunRequest,
    CadRunTimeoutError,
    run_cad_agent,
)
from agent.graph import run_timeout_seconds
from execution import inspect_code

from .auth import get_current_user_id
from .meshes import store_mesh_for_code
from .billing import SubscribedUserId
from .models import (
    CadRunRecord,
    CadRunResult,
    ProjectCreate,
    ProjectState,
    RunEvent,
)
from .store import (
    ProjectNotFoundError,
    ProjectStoreProtocol,
    RunNotFoundError,
    get_project_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cad/runs", tags=["cad-runs"])
Store = Annotated[ProjectStoreProtocol, Depends(get_project_store)]
UserId = Annotated[str, Depends(get_current_user_id)]

# A run still "running" this long after its deadline died with its process
# (a redeploy or crash), so it is reported as failed instead of polled forever.
STALE_RUN_GRACE_SECONDS = 120

# Strong references so in-flight runs are not garbage collected mid-await.
_active_runs: set[asyncio.Task] = set()


class CadRunStart(CadRunRequest):
    project_id: str | None = Field(default=None, alias="projectId")


def _prompt_of(request: CadRunRequest) -> str:
    content = request.messages[-1].content
    if isinstance(content, str):
        return content.strip()
    return "\n".join(
        part.get("text", "") for part in content if part.get("type") == "text"
    ).strip()


def _result_of(state: dict[str, Any], revision_number: int | None = None) -> CadRunResult:
    return CadRunResult.model_validate(
        {
            "code": state.get("code") or "",
            "plan": state.get("plan") or "",
            "inspection": state.get("inspection"),
            "trace": state.get("trace") or [],
            "usage": state.get("usage") or {},
            "revisionNumber": revision_number,
        }
    )


def _save_to_project(
    store: ProjectStoreProtocol,
    *,
    run_id: str,
    request: CadRunStart,
    result: CadRunResult,
    user_id: str,
) -> tuple[str, int]:
    assistant = {
        "role": "assistant",
        "content": result.code,
        "agent": {
            "runId": run_id,
            "plan": result.plan,
            "trace": [step.model_dump() for step in result.trace],
            "inspection": result.inspection.model_dump() if result.inspection else None,
            "usage": result.usage.model_dump(),
        },
    }
    state = ProjectState(
        code=result.code,
        messages=[message.model_dump() for message in request.messages] + [assistant],
        model_id=request.model_id,
        selection=None,
        last_run_id=run_id,
    )
    if request.project_id:
        try:
            revision = store.add_revision(request.project_id, state, user_id=user_id)
            return request.project_id, revision.revision_number
        except ProjectNotFoundError:
            # Deleted while the run was in flight: keep the paid result anyway.
            logger.warning(
                "Project %s vanished during run %s; saving as a new project.",
                request.project_id,
                run_id,
            )
    project = store.create_project(
        ProjectCreate(name=_prompt_of(request)[:60] or "Untitled part", state=state),
        user_id=user_id,
    )
    return project.id, 1


async def _execute_run(
    run_id: str,
    request: CadRunStart,
    *,
    user_id: str,
    store: ProjectStoreProtocol,
    api_key: str,
) -> None:
    project_id: str | None = None
    result: CadRunResult | None = None
    error: str | None = None
    sequence = 0

    async def record_event(event: dict[str, Any]) -> None:
        nonlocal sequence
        sequence += 1
        await asyncio.to_thread(
            store.add_run_event,
            run_id,
            RunEvent(
                seq=sequence,
                stage=str(event.get("stage", "")),
                status=str(event.get("status", "")),
                message=str(event.get("message", ""))[:500],
                attempt=event.get("attempt"),
                duration_ms=event.get("duration_ms"),
                created_at=datetime.now(timezone.utc),
            ),
            user_id=user_id,
        )

    try:
        state = await run_cad_agent(
            request, api_key, inspect_code, run_id=run_id, on_event=record_event
        )
    except CadRunTimeoutError as timeout:
        result = _result_of(timeout.state)
        error = str(timeout)
    except Exception as failure:
        logger.error("CAD agent run %s failed: %s", run_id, failure, exc_info=True)
        error = f"CAD agent failed: {failure}"
    else:
        if state["validation_error"]:
            result = _result_of(state)
            error = (
                "The CAD agent could not produce valid geometry after "
                f"{MAX_REPAIR_ATTEMPTS} repairs: {state['validation_error']}"
            )
        else:
            result = _result_of(state)
            try:
                project_id, revision_number = await asyncio.to_thread(
                    _save_to_project,
                    store,
                    run_id=run_id,
                    request=request,
                    result=result,
                    user_id=user_id,
                )
                result.revision_number = revision_number
                # Build the mesh now, so the studio can show the part as soon
                # as the run reports success.
                try:
                    await record_event(
                        {
                            "stage": "mesh",
                            "status": "started",
                            "message": "Preparing the 3D view.",
                        }
                    )
                except Exception:
                    logger.warning("Could not record the mesh event.", exc_info=True)
                await asyncio.to_thread(
                    store_mesh_for_code,
                    store,
                    user_id=user_id,
                    project_id=project_id,
                    code=result.code,
                )
            except Exception as failure:
                logger.error(
                    "Run %s succeeded but saving it failed: %s",
                    run_id,
                    failure,
                    exc_info=True,
                )
                error = f"The part was generated but could not be saved: {failure}"

    try:
        await asyncio.to_thread(
            store.finish_run,
            run_id,
            user_id=user_id,
            status="failed" if error else "succeeded",
            result=result,
            error=error,
            project_id=project_id,
        )
    except RunNotFoundError:
        logger.warning("Run %s was already closed before it finished.", run_id)
    except Exception:
        logger.exception("Could not record the outcome of run %s.", run_id)


def _spawn(coroutine) -> None:
    task = asyncio.create_task(coroutine)
    _active_runs.add(task)
    task.add_done_callback(_active_runs.discard)


@router.post("", response_model=CadRunRecord, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    request: CadRunStart, store: Store, user_id: SubscribedUserId
):
    if not request.messages or request.messages[-1].role != "user":
        raise HTTPException(
            status_code=400,
            detail="A non-empty message list ending with a user message is required.",
        )
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY is not configured on the backend.",
        )
    if request.project_id:
        try:
            await asyncio.to_thread(
                store.get_project, request.project_id, user_id=user_id
            )
        except ProjectNotFoundError as error:
            raise HTTPException(status_code=404, detail="Project not found.") from error

    run_id = str(uuid4())
    record = await asyncio.to_thread(
        store.create_run,
        run_id,
        user_id=user_id,
        project_id=request.project_id,
        prompt=_prompt_of(request)[:2000],
        model_id=request.model_id,
    )
    _spawn(
        _execute_run(run_id, request, user_id=user_id, store=store, api_key=api_key)
    )
    return record


@router.get("/{run_id}", response_model=CadRunRecord)
async def get_run(
    run_id: str,
    store: Store,
    user_id: UserId,
    after: Annotated[int, Query(ge=0)] = 0,
):
    """The run, with the progress events after sequence number ``after``."""
    try:
        record = await asyncio.to_thread(store.get_run, run_id, user_id=user_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="Run not found.") from error

    created_at = record.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    deadline = created_at + timedelta(
        seconds=run_timeout_seconds() + STALE_RUN_GRACE_SECONDS
    )
    if record.status == "running" and datetime.now(timezone.utc) > deadline:
        try:
            record = await asyncio.to_thread(
                store.finish_run,
                run_id,
                user_id=user_id,
                status="failed",
                result=None,
                error="The run was interrupted (the server restarted). Please retry.",
                project_id=None,
            )
        except RunNotFoundError:
            record = await asyncio.to_thread(store.get_run, run_id, user_id=user_id)
    try:
        record.events = await asyncio.to_thread(
            store.list_run_events, run_id, user_id=user_id, after=after
        )
    except Exception:
        # Before the run_events migration is applied, runs still work.
        logger.warning("Could not read events of run %s.", run_id, exc_info=True)
    return record
