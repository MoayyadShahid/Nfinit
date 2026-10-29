"""Limits that keep one account from running up the model and server bill.

Every run calls a paid model up to five times, and every sandbox call uses a
CPU for up to a minute and a half. The backend is reachable directly with a
valid access token, so the limits are enforced here, not in the browser:

- runs may use only the models the studio offers;
- a run request has a bounded size, and images must be inline pictures;
- each user has a cap on concurrent runs and on runs per hour and per day;
- each user has a cap on sandbox calls per minute.
"""

import asyncio
import base64
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status

from agent.models import CadRunRequest

from agent.graph import run_timeout_seconds

from .billing import require_subscription
from .store import ProjectStoreProtocol

DEFAULT_ALLOWED_MODELS = ("anthropic/claude-sonnet-5.5", "anthropic/claude-opus-5.5")

MAX_MESSAGES = 200
MAX_TEXT_CHARS = 400_000
MAX_CODE_CHARS = 200_000
MAX_IMAGES = 8
MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_DATA_URL = re.compile(r"^data:image/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/=\s]+)$")


def _int_setting(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def allowed_models() -> frozenset[str]:
    configured = os.getenv("CAD_ALLOWED_MODELS", "").strip()
    if not configured:
        return frozenset(DEFAULT_ALLOWED_MODELS)
    return frozenset(model.strip() for model in configured.split(",") if model.strip())


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
                _check_image(url)
            else:
                raise HTTPException(status_code=400, detail="Unsupported message content.")
    if text_chars > MAX_TEXT_CHARS:
        raise _too_large("This conversation is too long. Start a new part.")
    if images > MAX_IMAGES:
        raise _too_large(f"Attach at most {MAX_IMAGES} images to one part.")


def _check_image(url: object) -> None:
    # Inline pictures only: a web address would make the model provider fetch
    # whatever the user names.
    match = IMAGE_DATA_URL.match(url) if isinstance(url, str) else None
    if match is None:
        raise HTTPException(
            status_code=400, detail="Images must be PNG, JPEG, GIF or WebP files."
        )
    encoded = re.sub(r"\s", "", match.group(2))
    if len(encoded) * 3 // 4 > MAX_IMAGE_BYTES:
        raise _too_large("Each image must be 10 MB or smaller.")
    try:
        base64.b64decode(encoded[:64] + "=" * (-len(encoded[:64]) % 4), validate=True)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="An image is not valid.") from error


# Checking the quota and recording the run are one step per user, so two
# requests sent at once cannot both pass a full quota.
_run_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def run_lock(user_id: str) -> asyncio.Lock:
    return _run_locks[user_id]


def check_run_quota(store: ProjectStoreProtocol, user_id: str) -> None:
    concurrent = _int_setting("CAD_MAX_CONCURRENT_RUNS", 2)
    hourly = _int_setting("CAD_MAX_RUNS_PER_HOUR", 30)
    daily = _int_setting("CAD_MAX_RUNS_PER_DAY", 150)
    now = datetime.now(timezone.utc)
    # A run still "running" past its deadline died with its server.
    running_since = now - timedelta(seconds=run_timeout_seconds() + 120)

    running, last_day = store.count_runs(
        user_id=user_id, since=now - timedelta(days=1), running_since=running_since
    )
    if running >= concurrent:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You already have {running} parts building. Wait for one to finish.",
        )
    if last_day >= daily:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You reached today's limit of runs. Please try again tomorrow.",
        )
    _, last_hour = store.count_runs(
        user_id=user_id, since=now - timedelta(hours=1), running_since=running_since
    )
    if last_hour >= hourly:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You reached the hourly limit of runs. Please try again later.",
            headers={"Retry-After": "600"},
        )


class SlidingWindowLimiter:
    """At most ``limit`` calls per key in any ``window`` seconds (in memory)."""

    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self._calls: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> float | None:
        """Record a call; return seconds to wait if the key is over its limit."""
        now = time.monotonic()
        with self._lock:
            calls = self._calls[key]
            while calls and calls[0] <= now - self.window:
                calls.popleft()
            if len(calls) >= self.limit:
                return calls[0] + self.window - now
            calls.append(now)
            return None


_sandbox_limiter = SlidingWindowLimiter(_int_setting("CAD_SANDBOX_CALLS_PER_MINUTE", 60), 60.0)


def check_sandbox_rate(user_id: str) -> None:
    """Count one sandbox call for the user; raise 429 when over the limit."""
    wait = _sandbox_limiter.hit(user_id)
    if wait is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down.",
            headers={"Retry-After": str(max(1, int(wait) + 1))},
        )


def limit_sandbox_calls(user_id: Annotated[str, Depends(require_subscription)]) -> str:
    """A subscribed user's id, if they are under their sandbox call limit."""
    check_sandbox_rate(user_id)
    return user_id


SandboxUserId = Annotated[str, Depends(limit_sandbox_calls)]
