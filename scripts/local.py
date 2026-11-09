"""Start the free local workspace. Uses installed dependencies and agent logins."""
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    python = os.environ.get("NFNIT_PYTHON")
    if not python:
        if not shutil.which("poetry"):
            raise SystemExit("Install Poetry and run poetry install in backend/, or set NFNIT_PYTHON.")
        python = subprocess.check_output(
            ["poetry", "env", "info", "--executable"], cwd=ROOT / "backend", text=True
        ).strip()
    env = {**os.environ, "NFNIT_LOCAL_AGENTS": "true",
           "NFNIT_LOCAL_TOKEN": secrets.token_urlsafe(32),
           "NFNIT_ALLOW_LOCAL_AUTH_BYPASS": "true", "NFNIT_ALLOW_FREE_ACCESS": "true",
           "BACKEND_URL": "http://127.0.0.1:8000",
           "NEXT_PUBLIC_BACKEND_URL": "http://127.0.0.1:8000",
           "CORS_ORIGINS": "http://127.0.0.1:3000,http://localhost:3000"}
    # Local mode never reads hosted billing or identity configuration from .env.
    for name in ("SUPABASE_URL", "SUPABASE_JWT_SECRET", "NFNIT_DATABASE_URL",
                 "NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY",
                 "STRIPE_SECRET_KEY", "STRIPE_PRICE_ID", "STRIPE_WEBHOOK_SECRET",
                 "RAILWAY_ENVIRONMENT_NAME"):
        env[name] = ""
    children = []
    def stop(*_args):
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        children.append(subprocess.Popen(
            [python, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=ROOT / "backend", env=env, start_new_session=True))
        children.append(subprocess.Popen(
            ["npm", "run", "dev", "-w", "frontend", "--", "--hostname", "127.0.0.1"],
            cwd=ROOT, env=env, start_new_session=True))
        print("Nfinit local workspace: http://127.0.0.1:3000/studio", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
    finally:
        stop()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    main()
