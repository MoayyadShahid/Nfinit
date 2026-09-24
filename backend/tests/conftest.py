import pytest


@pytest.fixture(autouse=True)
def enable_local_project_auth(monkeypatch):
    monkeypatch.setenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS", "true")
