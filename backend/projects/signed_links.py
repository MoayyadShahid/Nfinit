"""Short-lived signed links the browser can use without a session.

Some responses go straight from this service to the browser instead of
through the Next.js proxy: meshes (too large for the proxy) and run event
streams (too long-lived). The studio asks for such a link through the proxy,
as the signed-in user, and the link carries who may use it and until when.
Each link has a purpose, so a link for one use is refused for any other.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_fallback_secret = secrets.token_bytes(32)
_warned_about_secret = False


def _secret() -> bytes:
    global _warned_about_secret
    configured = os.getenv("NFNIT_MESH_URL_SECRET", "").strip()
    if configured:
        return configured.encode()
    if not _warned_about_secret:
        _warned_about_secret = True
        logger.warning(
            "NFNIT_MESH_URL_SECRET is unset; signed links use a per-process key "
            "and stop working after a restart or on another replica."
        )
    return _fallback_secret


def _signature(purpose: str, body: str) -> str:
    message = f"{purpose}.{body}".encode()
    return hmac.new(_secret(), message, hashlib.sha256).hexdigest()


def sign_token(purpose: str, payload: dict, *, expires_at: int) -> str:
    raw = json.dumps(
        {**payload, "e": expires_at}, separators=(",", ":"), sort_keys=True
    ).encode()
    body = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return f"{body}.{_signature(purpose, body)}"


def read_token(purpose: str, token: str, *, label: str) -> dict:
    """Return the token's payload, or raise 404 (invalid) or 410 (expired)."""
    not_found = HTTPException(status_code=404, detail=f"{label} not found.")
    body, _, signature = token.partition(".")
    if not body or not hmac.compare_digest(signature, _signature(purpose, body)):
        raise not_found
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        expires_at = int(payload.pop("e"))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise not_found from error
    if expires_at < time.time():
        raise HTTPException(status_code=410, detail=f"{label} has expired.")
    return payload
