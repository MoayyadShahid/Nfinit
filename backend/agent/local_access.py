"""Local agent accounts must never become a public inference endpoint."""
import hmac
import os
import shutil

from fastapi import HTTPException, Request
from projects.config import is_production, local_auth_bypass_enabled

LOCAL_MODELS = {"local/claude": ("claude", "Claude Code"), "local/codex": ("codex", "Codex")}


def local_agents_enabled() -> bool:
    return (
        os.getenv("NFNIT_LOCAL_AGENTS", "").lower() == "true"
        and local_auth_bypass_enabled()
        and not is_production()
        and not os.getenv("SUPABASE_URL")
        and len(os.getenv("NFNIT_LOCAL_TOKEN", "")) >= 32
    )


def require_local_access(request: Request) -> None:
    token = request.headers.get("x-nfinit-local-token", "")
    if (not local_agents_enabled() or not request.client
            or request.client.host not in {"127.0.0.1", "::1", "testclient"}
            or not hmac.compare_digest(token, os.getenv("NFNIT_LOCAL_TOKEN", ""))):
        raise HTTPException(403, "Local agents are available only through the local Nfinit launcher.")


def agent_inventory() -> list[dict]:
    if not local_agents_enabled():
        return []
    return [{"id": key, "label": label, "installed": bool(shutil.which(command))}
            for key, (command, label) in LOCAL_MODELS.items()]
