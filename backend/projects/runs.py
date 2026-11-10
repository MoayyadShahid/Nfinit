"""Background CAD runs.

`POST /cad/runs` records the run and returns immediately; the agent keeps
working after the HTTP request ends. A successful run is saved into the
user's project server-side, so the result survives a closed tab, a dropped
connection or a proxy timeout. A failed run keeps its last attempt.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from collections import OrderedDict
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import Field
from starlette.background import BackgroundTask

from agent import (
    MAX_REPAIR_ATTEMPTS,
    CadRunRequest,
    CadRunTimeoutError,
    run_cad_agent,
)
from agent.graph import run_timeout_seconds
from agent.local_access import LOCAL_MODELS, require_local_access
from execution import BuildSnapshot, inspect_with_snapshots

from .auth import get_current_user_id
from .meshes import store_mesh_for_code
from .limits import create_run_under_quota, validate_run_request
from .models import (
    CadRunRecord,
    CadRunResult,
    ProjectCreate,
    ProjectState,
    RunEvent,
    RunStreamLink,
)
from .signed_links import read_token, sign_token
from .store import (
    ProjectNotFoundError,
    ProjectStoreProtocol,
    RunNotFoundError,
    StorageQuotaExceededError,
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

# Event streams check the database at least this often. A run in this process
# also wakes its streams at once, so this only bounds the delay for a run
# that another replica is executing.
STREAM_POLL_SECONDS = 2.0
# Railway closes a connection after 5 minutes without data.
STREAM_HEARTBEAT_SECONDS = 15.0
# Streams waiting on each run in this process.
_run_listeners: dict[str, set[asyncio.Event]] = {}


# Build previews (coarse GLBs of the part after each feature), by run and
# event sequence. They only matter while a run is watched, so they stay in
# memory: a restart or another replica loses them, and the studio skips them.
SNAPSHOT_CACHE_BYTES = 64 * 1024 * 1024
_snapshots: "OrderedDict[tuple[str, int], tuple[str, bytes]]" = OrderedDict()
_snapshot_bytes = 0


def _remember_snapshot(run_id: str, seq: int, user_id: str, glb: bytes) -> None:
    global _snapshot_bytes
    _snapshots[(run_id, seq)] = (user_id, glb)
    _snapshot_bytes += len(glb)
    while _snapshot_bytes > SNAPSHOT_CACHE_BYTES and _snapshots:
        _, (_, evicted) = _snapshots.popitem(last=False)
        _snapshot_bytes -= len(evicted)


def _wake_streams(run_id: str) -> None:
    for listener in _run_listeners.get(run_id, ()):
        listener.set()


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
        mesh_reference=request.mesh_reference,
    )
    if request.project_id:
        try:
            revision = store.add_revision(request.project_id, state, user_id=user_id)
            return request.project_id, revision.revision_number
        except ProjectNotFoundError:
            # The user deleted the project while the run was in flight. Never
            # resurrect data they explicitly removed as a new project.
            logger.warning(
                "Project %s vanished during run %s; discarding the result.",
                request.project_id,
                run_id,
            )
            raise
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

    async def record_event(event: dict[str, Any], glb: bytes | None = None) -> None:
        nonlocal sequence
        sequence += 1
        if glb is not None:
            # Stored before the event exists, so a client never asks too early.
            _remember_snapshot(run_id, sequence, user_id, glb)
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
        _wake_streams(run_id)

    loop = asyncio.get_running_loop()

    def inspect_and_preview(code: str):
        """Inspect in the sandbox thread, then report each build preview."""
        inspection, previews = inspect_with_snapshots(code)
        for preview in previews:
            try:
                asyncio.run_coroutine_threadsafe(
                    _record_snapshot(preview), loop
                ).result(timeout=10)
            except Exception:
                logger.warning("Could not record a build preview.", exc_info=True)
        return inspection

    async def _record_snapshot(preview: BuildSnapshot) -> None:
        await record_event(
            {"stage": "snapshot", "status": "ready", "message": preview.name},
            glb=preview.glb,
        )

    try:
        if request.model_id in LOCAL_MODELS:
            from agent.local import run_local_agent
            state = await run_local_agent(request, inspect_and_preview, run_id=run_id, on_event=record_event)
        else:
            state = await run_cad_agent(
                request, api_key, inspect_and_preview, run_id=run_id, on_event=record_event
            )
    except CadRunTimeoutError as timeout:
        result = _result_of(timeout.state)
        error = str(timeout)
    except Exception as failure:
        logger.error("CAD agent run %s failed: %s", run_id, failure, exc_info=True)
        # The exception text can name internal services; keep it in the log.
        error = (str(failure)[:500] if request.model_id in LOCAL_MODELS and isinstance(failure, ValueError)
                 else "The CAD agent failed unexpectedly. Please try again.")
    else:
        if state["validation_error"]:
            result = _result_of(state)
            attempts = (
                "its builds" if request.model_id in LOCAL_MODELS
                else f"{MAX_REPAIR_ATTEMPTS} repairs"
            )
            error = (
                "The CAD agent could not produce valid geometry after "
                f"{attempts}: {state['validation_error']}"
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
                # The exception can name tables and hosts; it is already logged above.
                error = "The part was generated but could not be saved. Please try again."

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
    except StorageQuotaExceededError:
        # The quota is checked before model spend, but another request can
        # consume the remaining space while this run is executing. Always
        # close the run; omit the large result when it no longer fits.
        logger.warning("Run %s finished after user %s filled storage.", run_id, user_id)
        try:
            await asyncio.to_thread(
                store.finish_run,
                run_id,
                user_id=user_id,
                status="failed",
                result=None,
                # Do not add even a small error string when the hard byte cap
                # is full. The HTTP layer already reports failed status.
                error=None,
                project_id=project_id,
            )
        except Exception:
            logger.exception("Could not close storage-limited run %s.", run_id)
    except RunNotFoundError:
        logger.warning("Run %s was already closed before it finished.", run_id)
    except Exception:
        logger.exception("Could not record the outcome of run %s.", run_id)
    finally:
        _wake_streams(run_id)


def _spawn(coroutine) -> None:
    task = asyncio.create_task(coroutine)
    _active_runs.add(task)
    task.add_done_callback(_active_runs.discard)


@router.post("", response_model=CadRunRecord, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    request: CadRunStart, store: Store, user_id: UserId, http_request: Request
):
    if not request.messages or request.messages[-1].role != "user":
        raise HTTPException(
            status_code=400,
            detail="A non-empty message list ending with a user message is required.",
        )
    validate_run_request(request)
    if request.plan_model_id in LOCAL_MODELS:
        raise HTTPException(400, "Local agents manage their own planning. Select them as the main agent.")
    if request.model_id in LOCAL_MODELS:
        require_local_access(http_request)
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key and request.model_id not in LOCAL_MODELS:
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
        create_run_under_quota,
        store,
        run_id=run_id,
        user_id=user_id,
        project_id=request.project_id,
        prompt=_prompt_of(request)[:2000],
        model_id=request.model_id,
    )
    _spawn(
        _execute_run(run_id, request, user_id=user_id, store=store, api_key=api_key or "")
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


def _stream_deadline_seconds() -> float:
    return run_timeout_seconds() + STALE_RUN_GRACE_SECONDS


@router.post("/{run_id}/stream", response_model=RunStreamLink)
async def create_stream_link(run_id: str, store: Store, user_id: UserId):
    """A signed link the browser opens directly, without the proxy.

    The Next.js proxy cannot hold a response open for a whole run, and the
    browser's EventSource cannot send an Authorization header, so the link
    itself carries who may read the stream. It lasts as long as a run can.
    """
    try:
        await asyncio.to_thread(store.get_run, run_id, user_id=user_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="Run not found.") from error
    expires_at = int(time.time() + _stream_deadline_seconds())
    token = sign_token("run-events", {"u": user_id, "r": run_id}, expires_at=expires_at)
    return RunStreamLink(
        url=f"/cad/runs/{run_id}/events?token={token}",
        expires_at=datetime.fromtimestamp(expires_at, timezone.utc),
    )


def _sse(event: str, data: str, event_id: int | None = None) -> str:
    lines = [f"id: {event_id}"] if event_id is not None else []
    lines += [f"event: {event}", f"data: {data}"]
    return "\n".join(lines) + "\n\n"


async def _event_stream(
    request: Request,
    store: ProjectStoreProtocol,
    *,
    run_id: str,
    user_id: str,
    cursor: int,
):
    wake = asyncio.Event()
    _run_listeners.setdefault(run_id, set()).add(wake)
    deadline = time.monotonic() + _stream_deadline_seconds()
    last_write = time.monotonic()
    try:
        # Reconnect after 2 s; the browser sends the last id it received.
        yield "retry: 2000\n\n"
        while not await request.is_disconnected():
            # Clear before reading, so an event recorded meanwhile is not missed.
            wake.clear()
            events = await asyncio.to_thread(
                store.list_run_events, run_id, user_id=user_id, after=cursor
            )
            for event in events:
                cursor = event.seq
                yield _sse("progress", event.model_dump_json(by_alias=True), event.seq)
                last_write = time.monotonic()
            record = await asyncio.to_thread(store.get_run, run_id, user_id=user_id)
            if record.status != "running" or time.monotonic() > deadline:
                # The client reads the final run through the proxy, which also
                # reports a run that its server lost as failed.
                yield _sse("done", json.dumps({"status": record.status}))
                return
            if time.monotonic() - last_write >= STREAM_HEARTBEAT_SECONDS:
                yield ": ping\n\n"
                last_write = time.monotonic()
            try:
                await asyncio.wait_for(wake.wait(), STREAM_POLL_SECONDS)
            except TimeoutError:
                pass
    finally:
        listeners = _run_listeners.get(run_id)
        if listeners is not None:
            listeners.discard(wake)
            if not listeners:
                _run_listeners.pop(run_id, None)


@router.get("/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    store: Store,
    token: Annotated[str, Query()],
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header()] = None,
):
    """Server-sent progress events of a run, then one "done" event."""
    payload = read_token("run-events", token, label="Event stream")
    if payload.get("r") != run_id or not isinstance(payload.get("u"), str):
        raise HTTPException(status_code=404, detail="Event stream not found.")
    user_id = payload["u"]
    try:
        await asyncio.to_thread(store.get_run, run_id, user_id=user_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="Run not found.") from error
    lease_id = str(uuid4())
    now = datetime.now(timezone.utc)
    acquired = await asyncio.to_thread(
        store.acquire_concurrency_lease,
        lease_id=lease_id,
        user_id=user_id,
        kind="run-stream",
        now=now,
        expires_at=now
        + timedelta(seconds=_stream_deadline_seconds() + STREAM_HEARTBEAT_SECONDS),
        limit=max(1, int(os.getenv("CAD_MAX_EVENT_STREAMS_PER_USER", "4"))),
    )
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many event streams are already open.",
            headers={"Retry-After": "5"},
        )
    if last_event_id and last_event_id.isdigit():
        after = max(after, int(last_event_id))
    return StreamingResponse(
        _event_stream(request, store, run_id=run_id, user_id=user_id, cursor=after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(
            store.release_concurrency_lease,
            lease_id=lease_id,
            user_id=user_id,
        ),
    )


@router.get("/{run_id}/snapshots/{seq}")
async def get_run_snapshot(run_id: str, seq: int, store: Store, user_id: UserId):
    """The build preview recorded as event ``seq`` of the run."""
    try:
        await asyncio.to_thread(store.get_run, run_id, user_id=user_id)
    except RunNotFoundError as error:
        raise HTTPException(status_code=404, detail="Run not found.") from error
    entry = _snapshots.get((run_id, seq))
    if entry is None or entry[0] != user_id:
        raise HTTPException(status_code=404, detail="Preview not available.")
    return Response(
        content=entry[1],
        media_type="model/gltf-binary",
        headers={"Cache-Control": "private, max-age=600"},
    )
