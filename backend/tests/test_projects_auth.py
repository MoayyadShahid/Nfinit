from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from projects.auth import get_current_user_id
from projects.config import validate_project_configuration
from projects.store import LEGACY_LOCAL_USER_ID

SUPABASE_URL = "https://example.supabase.co"
JWT_SECRET = "a-test-secret-that-is-long-enough-for-hs256"
USER_ID = "00000000-0000-4000-8000-000000000010"


@pytest.fixture(autouse=True)
def clean_project_environment(monkeypatch):
    for name in (
        "NFNIT_ALLOW_LOCAL_AUTH_BYPASS",
        "NFNIT_DATABASE_URL",
        "NFNIT_ENV",
        "RAILWAY_ENVIRONMENT",
        "SUPABASE_JWT_SECRET",
        "SUPABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def _credentials(subject: str = USER_ID) -> HTTPAuthorizationCredentials:
    token = jwt.encode(
        {
            "sub": subject,
            "aud": "authenticated",
            "iss": f"{SUPABASE_URL}/auth/v1",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_project_auth_uses_local_identity_without_supabase(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)

    assert get_current_user_id(None) == LEGACY_LOCAL_USER_ID


def test_project_auth_requires_token_when_supabase_is_configured(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)

    with pytest.raises(HTTPException) as error:
        get_current_user_id(None)

    assert error.value.status_code == 401


def test_project_auth_accepts_valid_supabase_token(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)

    assert get_current_user_id(_credentials()) == USER_ID


def test_project_auth_rejects_invalid_subject(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)

    with pytest.raises(HTTPException) as error:
        get_current_user_id(_credentials("not-a-uuid"))

    assert error.value.status_code == 401


def test_production_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="NFNIT_DATABASE_URL, SUPABASE_URL"):
        validate_project_configuration()
    with pytest.raises(HTTPException) as error:
        get_current_user_id(None)

    assert error.value.status_code == 503


def test_production_configuration_requires_auth_for_postgres(monkeypatch):
    monkeypatch.setenv("NFNIT_DATABASE_URL", "postgresql://example")

    with pytest.raises(RuntimeError, match="SUPABASE_URL is required"):
        validate_project_configuration()
