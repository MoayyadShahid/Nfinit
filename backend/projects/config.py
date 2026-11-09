import os


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def local_auth_bypass_enabled() -> bool:
    """True when the backend runs as the local single-user workspace."""
    return _enabled(os.getenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS"))


def validate_project_configuration() -> None:
    if not local_auth_bypass_enabled():
        raise RuntimeError(
            "Nfinit runs locally for one user. Start it with npm run local, "
            "which binds the API to this machine and sets "
            "NFNIT_ALLOW_LOCAL_AUTH_BYPASS."
        )
