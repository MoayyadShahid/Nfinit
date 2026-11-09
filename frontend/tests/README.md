# Studio browser checks

These Playwright checks use a local frontend and fixture API responses. They do
not need a backend, an account, or model credits. The script rejects a
non-loopback base URL, intercepts all API requests, and blocks external browser
requests. Monaco CDN paths are fulfilled from the locked local npm package so
the advanced editor can be tested offline. It never creates production data.

From the repository root:

```sh
python3 -m venv /tmp/nfinit-ui-tests
/tmp/nfinit-ui-tests/bin/pip install playwright==1.64.1
/tmp/nfinit-ui-tests/bin/python -m playwright install chromium
npm ci
```

Start the frontend on port 3100:

```sh
NFNIT_ALLOW_LOCAL_AUTH_BYPASS=true \
BACKEND_URL=http://127.0.0.1:8000 \
NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000 \
npm run dev -w frontend -- --hostname 127.0.0.1 --port 3100
```

In a second terminal:

```sh
/tmp/nfinit-ui-tests/bin/python frontend/tests/studio_controls.py
```

Use `--channel chrome` to use an already installed Google Chrome. Screenshots
are written to `/tmp/nfinit-ui-checks`. The frontend workflow runs the suite on
pull requests and main alongside typechecking, lint, and a production build.

Coverage includes model allowlisting and request wiring; keyboard navigation,
focus restoration, search, and unsaved-change confirmation; revision switching;
camera fitting without regeneration; progress/retry/error events; literal
rendering of HTML-like input; busy controls; mobile drawer dismissal and export;
reduced motion; and local-agent selection
with unavailable agents disabled and reference controls preserved.
