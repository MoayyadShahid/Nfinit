import os


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def local_auth_bypass_enabled() -> bool:
    return _enabled(os.getenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS"))


def is_production() -> bool:
    """Postgres storage or a Railway production environment means real users."""
    return bool(os.getenv("NFNIT_DATABASE_URL", "").strip()) or (
        os.getenv("RAILWAY_ENVIRONMENT_NAME", "").strip().lower() == "production"
    )


BILLING_SETTINGS = (
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_ID",
    "APP_URL",
)


def validate_project_configuration() -> None:
    database_url = os.getenv("NFNIT_DATABASE_URL", "").strip()
    supabase_url = os.getenv("SUPABASE_URL", "").strip()

    if database_url and not supabase_url:
        raise RuntimeError(
            "SUPABASE_URL is required when NFNIT_DATABASE_URL is configured."
        )
    if local_auth_bypass_enabled():
        # The bypass signs every caller in as one shared user: never with
        # real users, whatever else is configured.
        if is_production():
            raise RuntimeError(
                "NFNIT_ALLOW_LOCAL_AUTH_BYPASS must not be set in production."
            )
        return

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
            "Production project storage is not configured: " + ", ".join(missing)
        )

    required = ["NFNIT_MESH_URL_SECRET"]
    # Without Stripe the paywall is off and every user gets paid features, so
    # that must be a deliberate choice, not a missing variable.
    if not _enabled(os.getenv("NFNIT_ALLOW_FREE_ACCESS")):
        required += BILLING_SETTINGS
    unset = [name for name in required if not os.getenv(name, "").strip()]
    if unset:
        raise RuntimeError(
            "Required production settings are missing: "
            + ", ".join(unset)
            + ". Set NFNIT_ALLOW_FREE_ACCESS=true to run without billing."
        )
