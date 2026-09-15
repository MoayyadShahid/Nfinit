# Nfinit

AI-native CAD IDE for comparing how different LLMs handle 3D geometry code.

<img width="1470" height="761" alt="Screenshot 2026-02-17 at 6 27 44 PM" src="https://github.com/user-attachments/assets/88c0ec7a-4c47-4efb-925f-0d5ef71f04ea" />


## Setup

### Backend (FastAPI)

```bash
cd backend
cp .env.example .env
# Add your OPENROUTER_API_KEY to .env
poetry install
poetry run uvicorn main:app --reload --port 8000
```

**Note:** build123d requires OCP (OpenCASCADE) and VTK. If `poetry install` fails (e.g. VTK wheel not found), use conda:

```bash
# Create conda env with OpenCASCADE
conda create -n nfinit python=3.11
conda activate nfinit
conda install -c conda-forge pythonocc-core

# Use conda's Python for Poetry (from Nfinit project root)
cd backend
poetry install
poetry run uvicorn main:app --reload --port 8000
```

### Frontend (Next.js)

```bash
# From project root (uses npm workspaces)
npm install
npm run dev

# Or from frontend directory:
cd frontend
cp .env.local.example .env.local  # or create .env.local
npm install
npm run dev
```

### Environment

**Frontend:** Copy `frontend/.env.local.example` to `frontend/.env.local`:

```
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
BACKEND_URL=http://localhost:8000
```

**Backend:** Copy `backend/.env.example` to `backend/.env` and configure:

```
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

## Agent workflow

The FastAPI backend owns the LangGraph workflow; Next.js only proxies requests:

1. **Plan** — translate the product request into dimensions, constraints, features, and manufacturing intent.
2. **Generate** — produce parameterized build123d code from that plan.
3. **Inspect** — execute the code and measure its solids, volume, and bounding box.
4. **Repair** — feed execution failures back to the model, retrying up to three times.

Clicking a model face adds its local point and normal to the next request, so prompts such as “add a mounting hole on this face” can target the selected geometry.

## Execution sandbox

Generated code never runs inside the FastAPI process. Before execution, an AST
policy rejects imports, introspection, filesystem/network primitives, dynamic
code, and unsafe control flow. Valid code runs in an isolated Python worker with:

- restricted built-ins and no exporter access from generated code
- a scrubbed environment and disabled network sockets
- wall-clock, CPU, memory, file-size, and file-descriptor limits
- a private temporary directory that is deleted after inspection or export

The limits can be tuned with the `CAD_SANDBOX_*` variables documented in
`backend/.env.example`.

## Tracing

Every CAD run receives a UUID that is returned as `runId`. Node latency and
OpenRouter token usage are included in the API response and shown in the chat.
When `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are configured, the backend
also exports nested run, node, and generation observations to LangFuse.

Tracing is disabled automatically when credentials are absent. Prompts, source
code, and image data are never exported: traces contain only counts, hashes,
geometry results, timing, model identifiers, and token usage.

## Evaluations

The backend includes a typed evaluation runner with two modes:

- **Replay** re-executes recorded model code in the real CAD sandbox. It is
  deterministic, free, and suitable for local development or CI.
- **Live** runs selected OpenRouter models through the full LangGraph workflow.
  It requires `OPENROUTER_API_KEY` and sends traces to LangFuse when configured.

Run the included smoke fixtures from `backend/`:

```bash
python -m evaluation.cli \
  --cases evaluation/cases/smoke.json \
  --mode replay \
  --replays evaluation/replays/smoke.json \
  --output evaluation/reports/smoke.json
```

Run selected live models:

```bash
python -m evaluation.cli \
  --cases evaluation/cases/smoke.json \
  --mode live \
  --config evaluation/config/live_quality.json \
  --output evaluation/reports/live.json
```

The quality-first matrix pins Claude Opus 5 and GPT-6 Astra Pro so comparisons
remain reproducible even when OpenRouter's `*-latest` aliases change. Add
`--publish-langfuse` to create privacy-safe dataset items and attach overall,
per-metric, repair, latency, and token scores to each run trace. Prompt text,
generated code, and images remain redacted.

The **Live CAD model evaluation** GitHub workflow runs both models on demand.
Choose `smoke` for six paid agent runs or `cad50` for the complete 100-run
comparison. Configure these repository secrets before running it:

- `OPENROUTER_API_KEY`
- `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` when publishing is enabled

The weekly smoke schedule is skipped unless the repository variable
`ENABLE_SCHEDULED_PAID_EVALS` is exactly `true`. `LANGFUSE_BASE_URL` can
optionally override the default LangFuse Cloud endpoint. Reports are retained as
workflow artifacts for 90 days.

Reports compare pass rate, geometry accuracy, policy compliance, repair count,
latency, and token usage by model. A nonzero exit code indicates a regression.

The `cad50.json` benchmark contains 50 balanced cases across primitives,
subtractive features, patterns, sketch profiles, edge finishing, mechanical
parts, iterative edits, selected-face edits, failure recovery, and
manufacturing-oriented products. Validate all canonical outputs locally with:

```bash
python -m evaluation.cli \
  --cases evaluation/cases/cad50.json \
  --mode replay \
  --replays evaluation/replays/cad50.json \
  --output evaluation/reports/cad50.json
```

Pull requests that change the backend run this benchmark in GitHub Actions.
`evaluation/baselines/cad50.json` requires all 50 case IDs, five cases in each
category, complete metric coverage, and a 100% canonical replay pass rate. The
JSON report is uploaded as a 30-day workflow artifact. Validate a report against
the same policy locally with:

```bash
python -m evaluation.gate \
  --report evaluation/reports/cad50.json \
  --cases evaluation/cases/cad50.json \
  --policy evaluation/baselines/cad50.json
```

## Usage

1. Start the backend on port 8000
2. Start the frontend on port 3000
3. Open http://localhost:3000
4. Select a quality-first model (Claude Opus 5 or GPT-6 Astra Pro)
5. Type a prompt (e.g. "a 10mm cube with a 3mm hole through the center")
6. Press Generate or Cmd+Enter

The AI generates build123d Python code, which is executed by the backend to produce a GLB mesh displayed in the 3D viewport.
