import os


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_production_environment() -> bool:
    return bool(
        os.getenv("RAILWAY_ENVIRONMENT", "").strip()
        or os.getenv("NFNIT_ENV", "").strip().lower() == "production"
    )


def local_auth_bypass_enabled() -> bool:
    explicit = os.getenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS")
    if explicit is not None:
        return _enabled(explicit)
    return not is_production_environment()


def validate_project_configuration() -> None:
    database_url = os.getenv("NFNIT_DATABASE_URL", "").strip()
    supabase_url = os.getenv("SUPABASE_URL", "").strip()

    if database_url and not supabase_url:
        raise RuntimeError(
            "SUPABASE_URL is required when NFNIT_DATABASE_URL is configured."
        )
    if not local_auth_bypass_enabled():
        missing = [
            name
            for name, value in (
                ("NFNIT_DATABASE_URL", database_url),
                ("SUPABASE_URL", supabase_url),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Production project storage is not configured: "
                + ", ".join(missing)
            )
