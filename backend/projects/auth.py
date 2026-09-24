import os
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from .config import local_auth_bypass_enabled
from .store import LEGACY_LOCAL_USER_ID

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Authentication required.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Production project authentication is not configured.",
    )


@lru_cache(maxsize=4)
def _jwks_client(supabase_url: str) -> PyJWKClient:
    return PyJWKClient(
        f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json",
        cache_keys=True,
    )


def _decode_access_token(token: str) -> dict:
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "").strip()
    issuer = f"{supabase_url}/auth/v1" if supabase_url else None

    try:
        algorithm = jwt.get_unverified_header(token).get("alg")
        decode_options = {
            "algorithms": [algorithm],
            "audience": "authenticated",
        }
        if issuer:
            decode_options["issuer"] = issuer

        if algorithm == "HS256":
            if not jwt_secret:
                raise _unauthorized("Legacy Supabase JWT secret is not configured.")
            return jwt.decode(token, jwt_secret, **decode_options)

        if algorithm not in {"RS256", "ES256"} or not supabase_url:
            raise _unauthorized("Unsupported Supabase access token.")
        signing_key = _jwks_client(supabase_url).get_signing_key_from_jwt(token)
        return jwt.decode(token, signing_key.key, **decode_options)
    except HTTPException:
        raise
    except (PyJWTError, ValueError) as error:
        raise _unauthorized("Invalid or expired Supabase access token.") from error


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    auth_configured = bool(
        os.getenv("SUPABASE_URL", "").strip()
        or os.getenv("SUPABASE_JWT_SECRET", "").strip()
    )
    if not auth_configured:
        if local_auth_bypass_enabled():
            return LEGACY_LOCAL_USER_ID
        raise _unavailable()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    payload = _decode_access_token(credentials.credentials)
    subject = payload.get("sub")
    try:
        return str(UUID(subject))
    except (TypeError, ValueError, AttributeError) as error:
        raise _unauthorized("Supabase access token has no valid subject.") from error
