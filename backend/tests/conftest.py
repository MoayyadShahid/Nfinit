import os

# Fail-closed production config requires Postgres + Supabase unless this
# flag is set. Tests keep the local SQLite bypass unless they delete it.
os.environ.setdefault("NFNIT_ALLOW_LOCAL_AUTH_BYPASS", "true")
