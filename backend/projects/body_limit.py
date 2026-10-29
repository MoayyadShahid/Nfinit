"""A hard cap on request body size, applied before any route reads a body.

Route-level limits (message counts, image sizes) only run after FastAPI has
parsed the whole body, and the API is reachable without the Next.js proxy, so
without this a client could make the server buffer any amount of data, even
before it is authenticated.
"""

import json
import os

DEFAULT_MAX_BODY_BYTES = 16 * 1024 * 1024


def max_body_bytes() -> int:
    try:
        return max(1024, int(os.getenv("CAD_MAX_REQUEST_BYTES", DEFAULT_MAX_BODY_BYTES)))
    except ValueError:
        return DEFAULT_MAX_BODY_BYTES


class BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Refuse a declared size over the limit, and stop a body that grows past it."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = max_body_bytes()
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = limit + 1
                if declared > limit:
                    await _reject(send)
                    return

        received = 0
        response_started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge()
            return message

        async def tracking_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLarge:
            if not response_started:
                await _reject(send)


async def _reject(send):
    body = json.dumps({"detail": "The request is too large."}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
