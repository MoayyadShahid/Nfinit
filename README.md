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
  --model anthropic/claude-opus-5 \
  --model openai/gpt-6-astra-pro \
  --output evaluation/reports/live.json
```

Reports compare pass rate, geometry accuracy, policy compliance, repair count,
latency, and token usage by model. A nonzero exit code indicates a regression.

## Usage

1. Start the backend on port 8000
2. Start the frontend on port 3000
3. Open http://localhost:3000
4. Select a quality-first model (Claude Opus 5 or GPT-6 Astra Pro)
5. Type a prompt (e.g. "a 10mm cube with a 3mm hole through the center")
6. Press Generate or Cmd+Enter

The AI generates build123d Python code, which is executed by the backend to produce a GLB mesh displayed in the 3D viewport.
