import pytest
from fastapi import HTTPException

from projects.auth import LOCAL_USER_ID, get_current_user_id
from projects.config import validate_project_configuration


def test_every_request_is_the_local_user():
    assert get_current_user_id() == LOCAL_USER_ID


def test_api_refuses_to_serve_outside_the_local_workspace(monkeypatch):
    monkeypatch.delenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS")

    with pytest.raises(HTTPException) as refused:
        get_current_user_id()
    assert refused.value.status_code == 503

    with pytest.raises(RuntimeError, match="npm run local"):
        validate_project_configuration()
