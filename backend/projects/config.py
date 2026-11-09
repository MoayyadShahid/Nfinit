import ipaddress
import os
from urllib.parse import urlsplit


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def local_auth_bypass_enabled() -> bool:
    return _enabled(os.getenv("NFNIT_ALLOW_LOCAL_AUTH_BYPASS"))


def is_production() -> bool:
    """Postgres storage or a Railway production environment means real users."""
    return bool(os.getenv("NFNIT_DATABASE_URL", "").strip()) or (
        os.getenv("RAILWAY_ENVIRONMENT_NAME", "").strip().lower() == "production"
    )


def _valid_production_origin(value: str) -> bool:
    if not value or "*" in value:
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        # WHATWG URL parsers accept historical IPv4 spellings such as 127.1,
        # 2130706433 and 0x7f000001 even though ipaddress deliberately does
        # not. Do not let those spellings smuggle a loopback CORS origin into
        # production configuration.
        noncanonical_number = address is None and (
            all(character in "0123456789." for character in host)
            or any(label.startswith("0x") for label in host.split("."))
        )
        return (
            parsed.scheme == "https"
            and bool(host)
            and host != "localhost"
            and not host.endswith(".localhost")
            and not (address and (address.is_loopback or address.is_unspecified))
            and not noncanonical_number
            and parsed.username is None
            and parsed.password is None
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


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

    required = ["NFNIT_MESH_URL_SECRET", "CORS_ORIGINS"]
    unset = [name for name in required if not os.getenv(name, "").strip()]
    if unset:
        raise RuntimeError(
            "Required production settings are missing: " + ", ".join(unset)
        )

    signing_secret = os.environ["NFNIT_MESH_URL_SECRET"].strip().encode()
    if len(signing_secret) < 32:
        raise RuntimeError(
            "NFNIT_MESH_URL_SECRET must contain at least 32 bytes in production."
        )

    origins = [item.strip() for item in os.environ["CORS_ORIGINS"].split(",")]
    invalid_origins = [origin for origin in origins if not _valid_production_origin(origin)]
    if invalid_origins:
        raise RuntimeError(
            "CORS_ORIGINS must contain only exact HTTPS production origins; "
            "wildcards, paths and localhost are not allowed."
        )
