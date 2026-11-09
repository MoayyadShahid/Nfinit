"""Who is making a request.

Nfinit runs on the user's own machine for one person, so every request
belongs to the one local user. The local launcher binds the API to loopback
and sets NFNIT_ALLOW_LOCAL_AUTH_BYPASS; without it the API refuses to serve,
so a backend started some other way never accepts anonymous requests.
"""

from dataclasses import dataclass

from fastapi import HTTPException, status

from .config import local_auth_bypass_enabled
from .store import LEGACY_LOCAL_USER_ID

LOCAL_USER_ID = LEGACY_LOCAL_USER_ID


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None = None


def get_current_user() -> CurrentUser:
    if not local_auth_bypass_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Start Nfinit with npm run local.",
        )
    return CurrentUser(LOCAL_USER_ID)


def get_current_user_id() -> str:
    return get_current_user().id
