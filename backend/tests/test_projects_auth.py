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
    monkeypatch.setenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS", "true")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)

    assert get_current_user_id(None) == LEGACY_LOCAL_USER_ID


def test_local_bypass_allows_sqlite_configuration(monkeypatch):
    monkeypatch.setenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS", "true")
    monkeypatch.delenv("NFNIT_DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    validate_project_configuration()


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
    monkeypatch.delenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS", raising=False)

    with pytest.raises(RuntimeError, match="NFNIT_DATABASE_URL, SUPABASE_URL"):
        validate_project_configuration()
    with pytest.raises(HTTPException) as error:
        get_current_user_id(None)

    assert error.value.status_code == 503


def test_production_configuration_requires_auth_for_postgres(monkeypatch):
    monkeypatch.setenv("NFNIT_DATABASE_URL", "postgresql://example")

    with pytest.raises(RuntimeError, match="SUPABASE_URL is required"):
        validate_project_configuration()


PRODUCTION_SETTINGS = {
    "NFNIT_DATABASE_URL": "postgresql://example",
    "SUPABASE_URL": SUPABASE_URL,
    "NFNIT_MESH_URL_SECRET": "a" * 64,
    "STRIPE_SECRET_KEY": "rk_test_x",
    "STRIPE_WEBHOOK_SECRET": "whsec_x",
    "STRIPE_PRICE_ID": "price_x",
    "APP_URL": "https://nfinit.dev",
    "CORS_ORIGINS": "https://nfinit.dev,https://www.nfinit.dev",
}


def _production(monkeypatch, **overrides):
    monkeypatch.delenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS", raising=False)
    monkeypatch.delenv("NFNIT_ALLOW_FREE_ACCESS", raising=False)
    for name, value in {**PRODUCTION_SETTINGS, **overrides}.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def test_complete_production_configuration_starts(monkeypatch):
    _production(monkeypatch)

    validate_project_configuration()


@pytest.mark.parametrize(
    "origins",
    [
        "*",
        "https://nfinit.dev,http://localhost:3000",
        "https://*.vercel.app",
        "https://nfinit.dev/a/path",
    ],
)
def test_production_configuration_rejects_unsafe_cors(monkeypatch, origins):
    _production(monkeypatch, CORS_ORIGINS=origins)

    with pytest.raises(RuntimeError, match="exact HTTPS production origins"):
        validate_project_configuration()


def test_local_bypass_is_refused_in_production(monkeypatch):
    _production(monkeypatch, NFNIT_ALLOW_LOCAL_AUTH_BYPASS="true")
    with pytest.raises(RuntimeError, match="must not be set in production"):
        validate_project_configuration()

    _production(monkeypatch, NFNIT_DATABASE_URL=None, SUPABASE_URL=None)
    monkeypatch.setenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS", "true")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    with pytest.raises(RuntimeError, match="must not be set in production"):
        validate_project_configuration()


@pytest.mark.parametrize(
    "missing", ["NFNIT_MESH_URL_SECRET", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"]
)
def test_production_refuses_to_start_without_a_required_secret(monkeypatch, missing):
    _production(monkeypatch, **{missing: None})

    with pytest.raises(RuntimeError, match=missing):
        validate_project_configuration()


def test_running_without_billing_must_be_explicit(monkeypatch):
    _production(monkeypatch, STRIPE_SECRET_KEY=None, STRIPE_WEBHOOK_SECRET=None)
    monkeypatch.setenv("NFNIT_ALLOW_FREE_ACCESS", "true")

    validate_project_configuration()
