import hashlib
import logging
from contextlib import contextmanager
from time import perf_counter
from typing import Any

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


class LocalObservation:
    def __init__(self):
        self.level = "DEFAULT"

    def update(self, **kwargs):
        # Never retain prompt, source, image or result payloads in debug logs.
        self.level = kwargs.get("level", self.level)
        return self


class RunTracer:
    """Local timing diagnostics only. No telemetry client or network export."""

    def __init__(self, run_id: str):
        self.run_id = run_id

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
        observation = LocalObservation()
        started = perf_counter()
        try:
            yield observation
        except BaseException:
            observation.level = "ERROR"
            raise
        finally:
            logger.debug("CAD observation run=%s node=%s level=%s duration_ms=%d",
                         self.run_id, name, observation.level, round((perf_counter()-started)*1000))
