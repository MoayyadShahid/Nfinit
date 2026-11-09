"""Limits that keep one account from running up the model and server bill.

Every run calls a paid model up to five times, and every sandbox call uses a
CPU for up to a minute and a half. The backend is reachable directly with a
valid access token, so the limits are enforced here, not in the browser:

- runs may use only the models the studio offers;
- a run request has a bounded size, and images must be inline pictures;
- each user has a cap on concurrent runs and on runs per hour and per day;
- each user has a cap on sandbox calls per minute.
"""

import base64
import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated, Iterator
from uuid import uuid4

from fastapi import Depends, HTTPException, status

from agent.models import CadRunRequest

from agent.graph import run_timeout_seconds

from .billing import require_subscription
from .store import (
    ProjectStoreProtocol,
    RunQuotaExceededError,
    get_project_store,
)

DEFAULT_ALLOWED_MODELS = ("anthropic/claude-sonnet-5.5", "anthropic/claude-opus-5.5")

MAX_MESSAGES = 200
MAX_TEXT_CHARS = 400_000
MAX_CODE_CHARS = 200_000
MAX_IMAGES = 8
MAX_IMAGE_BYTES = 10 * 1024 * 1024
# The transport cap is 20 MiB.  Ten MiB of decoded images expands to about
# 13.4 MiB in base64, leaving room for the bounded code, text and JSON syntax.
MAX_TOTAL_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_DATA_URL = re.compile(r"^data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=\s]+)$")


def _int_setting(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def allowed_models() -> frozenset[str]:
    from agent.local_access import LOCAL_MODELS, local_agents_enabled
    configured = os.getenv("CAD_ALLOWED_MODELS", "").strip()
    models = frozenset(model.strip() for model in configured.split(",") if model.strip()) if configured else frozenset(DEFAULT_ALLOWED_MODELS)
    return models | (frozenset(LOCAL_MODELS) if local_agents_enabled() else frozenset())


def _too_large(detail: str) -> HTTPException:
    return HTTPException(status_code=413, detail=detail)


def validate_run_request(request: CadRunRequest) -> None:
    """Reject a run that asks for another model or is larger than any real one."""
    models = allowed_models()
    for model in (request.model_id, request.plan_model_id):
        if model is not None and model not in models:
            raise HTTPException(status_code=400, detail="This model is not available.")

    if len(request.messages) > MAX_MESSAGES:
        raise _too_large("This conversation is too long. Start a new part.")
    if len(request.code) > MAX_CODE_CHARS:
        raise _too_large("The current code is too long.")

    text_chars = 0
    images = 0
    image_bytes = 0
    for message in request.messages:
        if isinstance(message.content, str):
            text_chars += len(message.content)
            continue
        for part in message.content:
            kind = part.get("type")
            if kind == "text":
                text = part.get("text")
                if not isinstance(text, str):
                    raise HTTPException(status_code=400, detail="Invalid message text.")
                text_chars += len(text)
            elif kind == "image_url":
                images += 1
                image = part.get("image_url")
                url = image.get("url") if isinstance(image, dict) else None
                image_bytes += _check_image(url)
            else:
                raise HTTPException(status_code=400, detail="Unsupported message content.")
    if text_chars > MAX_TEXT_CHARS:
        raise _too_large("This conversation is too long. Start a new part.")
    if images > MAX_IMAGES:
        raise _too_large(f"Attach at most {MAX_IMAGES} images to one part.")
    if image_bytes > MAX_TOTAL_IMAGE_BYTES:
        raise _too_large("Attached images may total at most 10 MB.")


def _check_image(url: object) -> int:
    # Inline pictures only: a web address would make the model provider fetch
    # whatever the user names.
    match = IMAGE_DATA_URL.match(url) if isinstance(url, str) else None
    if match is None:
        raise HTTPException(
            status_code=400, detail="Images must be PNG, JPEG, GIF or WebP files."
        )
    encoded = re.sub(r"\s", "", match.group(2))
    decoded_size = len(encoded.rstrip("=")) * 3 // 4
    if decoded_size > MAX_IMAGE_BYTES:
        raise _too_large("Each image must be 10 MB or smaller.")
    try:
        base64.b64decode(encoded[:64] + "=" * (-len(encoded[:64]) % 4), validate=True)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="An image is not valid.") from error
    return decoded_size


def create_run_under_quota(
    store: ProjectStoreProtocol,
    *,
    run_id: str,
    user_id: str,
    project_id: str | None,
    prompt: str,
    model_id: str,
):
    """Atomically reserve a run in the shared store.

    The store holds a database-level lock while it counts and inserts, so the
    cap remains exact across threads, processes and Railway replicas.
    """
    concurrent = _int_setting("CAD_MAX_CONCURRENT_RUNS", 2)
    hourly = _int_setting("CAD_MAX_RUNS_PER_HOUR", 30)
    daily = _int_setting("CAD_MAX_RUNS_PER_DAY", 150)
    now = datetime.now(timezone.utc)
    # A run still "running" past its deadline died with its server.
    running_since = now - timedelta(seconds=run_timeout_seconds() + 120)

    try:
        return store.create_run_with_quota(
            run_id,
            user_id=user_id,
            project_id=project_id,
            prompt=prompt,
            model_id=model_id,
            now=now,
            running_since=running_since,
            max_concurrent=concurrent,
            max_hourly=hourly,
            max_daily=daily,
        )
    except RunQuotaExceededError as error:
        if error.reason == "concurrent":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"You already have {error.running} parts building. "
                    "Wait for one to finish."
                ),
            ) from error
        if error.reason == "daily":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="You reached today's limit of runs. Please try again tomorrow.",
            ) from error
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You reached the hourly limit of runs. Please try again later.",
            headers={"Retry-After": "600"},
        ) from error


def check_sandbox_rate(store: ProjectStoreProtocol, user_id: str) -> None:
    """Consume one sandbox call in the shared database-backed window."""
    wait = store.hit_sandbox_rate(
        user_id=user_id,
        now=datetime.now(timezone.utc),
        limit=_int_setting("CAD_SANDBOX_CALLS_PER_MINUTE", 60),
        window_seconds=60,
    )
    if wait is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down.",
            headers={"Retry-After": str(max(1, int(wait) + 1))},
        )


@contextmanager
def sandbox_execution_slot(
    store: ProjectStoreProtocol, user_id: str
) -> Iterator[None]:
    """Hold one cross-replica execution slot for this user.

    Leases expire if a process dies before the dependency's finally block. The
    default covers two sequential 90-second builds (revision comparison) plus
    queue/response overhead.
    """
    lease_id = str(uuid4())
    now = datetime.now(timezone.utc)
    lease_seconds = max(1, _int_setting("CAD_SANDBOX_LEASE_SECONDS", 240))
    acquired = store.acquire_concurrency_lease(
        lease_id=lease_id,
        user_id=user_id,
        kind="sandbox",
        now=now,
        expires_at=now + timedelta(seconds=lease_seconds),
        limit=_int_setting("CAD_SANDBOX_MAX_CONCURRENT_PER_USER", 2),
    )
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You already have too many CAD operations running.",
            headers={"Retry-After": "5"},
        )
    try:
        yield
    finally:
        store.release_concurrency_lease(lease_id=lease_id, user_id=user_id)


def limit_sandbox_calls(
    user_id: Annotated[str, Depends(require_subscription)],
    store: Annotated[ProjectStoreProtocol, Depends(get_project_store)],
) -> Iterator[str]:
    """A subscribed user's id, if they are under their sandbox call limit."""
    with sandbox_execution_slot(store, user_id):
        check_sandbox_rate(store, user_id)
        yield user_id


SandboxUserId = Annotated[str, Depends(limit_sandbox_calls)]
