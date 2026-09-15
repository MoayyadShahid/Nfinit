import hashlib
import logging
import os
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from langfuse import Langfuse

logger = logging.getLogger(__name__)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def summarize_text(value: str) -> dict[str, Any]:
    return {
        "characters": len(value),
        "sha256": _fingerprint(value),
    }


def summarize_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
    text_parts: list[str] = []
    image_count = 0
    roles: list[str] = []
    for message in messages:
        roles.append(str(message.get("role", "unknown")))
        content = message.get("content", "")
        if isinstance(content, str):
            text_parts.append(content)
            continue
        for part in content:
            if part.get("type") == "text":
                text_parts.append(str(part.get("text", "")))
            elif part.get("type") == "image_url":
                image_count += 1

    combined = "\n".join(text_parts)
    return {
        "message_count": len(messages),
        "roles": roles,
        "text": summarize_text(combined),
        "image_count": image_count,
        "images_redacted": image_count > 0,
    }


class NullObservation:
    def update(self, **_kwargs):
        return self


@lru_cache(maxsize=1)
def get_langfuse_client() -> Langfuse | None:
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return None

    return Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        base_url=os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
        environment=os.getenv("LANGFUSE_ENVIRONMENT", "development"),
        release=os.getenv("LANGFUSE_RELEASE"),
        tracing_enabled=True,
    )


class RunTracer:
    def __init__(self, run_id: str, client: Langfuse | None = None):
        self.run_id = run_id
        self.client = client if client is not None else get_langfuse_client()

    @property
    def enabled(self) -> bool:
        return self.client is not None

    @contextmanager
    def observation(
        self,
        name: str,
        *,
        as_type: str = "span",
        input: Any = None,
        metadata: dict[str, Any] | None = None,
        model: str | None = None,
        root: bool = False,
    ):
        if self.client is None:
            yield NullObservation()
            return

        kwargs: dict[str, Any] = {
            "name": name,
            "as_type": as_type,
            "input": input,
            "metadata": {"run_id": self.run_id, **(metadata or {})},
        }
        if model:
            kwargs["model"] = model
        if root:
            kwargs["trace_context"] = {"trace_id": self.run_id.replace("-", "")}

        with self.client.start_as_current_observation(**kwargs) as observation:
            yield observation


def flush_tracing():
    client = get_langfuse_client()
    if client is not None:
        try:
            client.flush()
        except Exception:
            logger.warning("Failed to flush LangFuse traces", exc_info=True)
