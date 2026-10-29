import os

# Fail-closed production config requires Postgres + Supabase unless this
# flag is set. Tests keep the local SQLite bypass unless they delete it.
os.environ.setdefault("NFNIT_ALLOW_LOCAL_AUTH_BYPASS", "true")

# Billing stays off unless a test turns it on. An empty value also stops
# main.py's load_dotenv from pulling a developer's Stripe keys from .env.
for _name in (
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_ID",
    "APP_URL",
):
    os.environ[_name] = ""


import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _stop_cad_sandbox():
    yield
    from execution import stop_sandbox

    stop_sandbox()

# Older fixtures name models the studio no longer offers; the run allowlist
# itself is tested in test_limits.py.
os.environ.setdefault(
    "CAD_ALLOWED_MODELS",
    "anthropic/claude-sonnet-5.5,anthropic/claude-opus-5.5,"
    "anthropic/claude-opus-5,openai/gpt-6-astra-pro",
)
