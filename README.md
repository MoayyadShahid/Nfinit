# Nfinit

AI-native CAD IDE for comparing how different LLMs handle 3D geometry code.

<img width="1470" height="761" alt="Screenshot 2026-02-17 at 6 27 44 PM" src="https://github.com/user-attachments/assets/88c0ec7a-4c47-4efb-925f-0d5ef71f04ea" />

The current product scope is intentionally narrow: describe one part, preview
it, refine it through chat or face selection, save revisions, and export STL or
STEP. See [`docs/SIMPLE_LOVABLE_MVP.md`](docs/SIMPLE_LOVABLE_MVP.md) for the
requirements and explicitly deferred work.


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

# Optional: activates Supabase OAuth and protects /studio
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-publishable-anon-key
```

When the Supabase values are absent, authentication intentionally runs in
local bypass mode: `/login` redirects directly to `/studio`. To activate OAuth,
create Google and/or GitHub providers in Supabase and add these redirect URLs:

```
http://localhost:3000/auth/callback
https://your-production-domain.com/auth/callback
```

The landing page login action uses `/login?next=/studio`. Configured
deployments exchange the OAuth code in `/auth/callback`, store the Supabase
session in secure cookies, protect `/studio`, and expose sign-out in the studio
toolbar.

**Backend:** Copy `backend/.env.example` to `backend/.env` and configure:

```
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

## Agent workflow

The FastAPI backend owns the LangGraph workflow; Next.js only proxies requests:

1. **Retrieve** — find relevant build123d implementation patterns.
2. **Plan** — translate the product request into dimensions, constraints,
   features, and manufacturing intent.
3. **Generate** — produce parameterized build123d code from that plan.
4. **Inspect** — execute the code and measure its solids, volume, and bounding
   box.
5. **Repair** — feed execution failures back to the model, retrying up to three
   times.

Clicking a model face adds its local point and normal to the next request, so prompts such as “add a mounting hole on this face” can target the selected geometry.

### build123d pattern RAG

Retrieval works without external credentials: a compact curated corpus is
ranked locally with deterministic lexical scoring. When Pinecone is configured,
the same graph node uses an integrated-embedding index and falls back to the
local corpus on service errors. Only the latest text request and selected
surface type are used as the search query. LangFuse receives a hash and length,
not the query or retrieved source.

Set `PINECONE_API_KEY` and either `PINECONE_INDEX_HOST` (preferred) or
`PINECONE_INDEX_NAME`. The index must use integrated embedding with its text
field mapped to `chunk_text`. Use a versioned namespace such as
`build123d-patterns-v1`.

The ingestion CLI extracts content-addressed snippets from a pinned checkout of
the official build123d examples and docs. It verifies the upstream Apache-2.0
license, retains only syntax-valid snippets accepted by the CAD policy, removes
overlapping windows, and preserves source URLs and license metadata. CAD50
replays and the curated local corpus can be included as validated seeds:

```bash
git clone https://github.com/gumyr/build123d.git /tmp/build123d
cd /tmp/build123d
REVISION=$(git rev-parse HEAD)
cd /path/to/Nfinit/backend
poetry run python -m agent.retrieval.ingest \
  --source-root /tmp/build123d \
  --revision "$REVISION" \
  --replays evaluation/replays/cad50.json \
  --seed-corpus agent/retrieval/patterns.json \
  --output agent/retrieval/generated/build123d.jsonl \
  --pinecone
```

The default quality gate requires at least 100 unique patterns. The checked
source revision, source counts, and final deduplicated count are printed by the
command; use those measured values rather than assuming a corpus size.

Keep the upstream `LICENSE` and `NOTICE` with any exported or redistributed
corpus. Set `PATTERN_RAG_ENABLED=false` to disable retrieval entirely.

### Semantic topology

`POST /analyze-model` executes CAD code in the sandbox and returns a deterministic
index of B-rep faces and edges. Entity IDs are content-addressed from geometric
properties and adjacency, so repeated analysis of identical geometry returns the
same IDs. A supplied point and outward normal resolves a viewport click to the
exact face ID, surface type, distance, normal alignment, and confidence. The IDE
adds that identity to subsequent agent prompts.

These IDs identify one exact B-rep version; geometry-changing edits may replace
them. Cross-edit feature identity uses the explicit semantic feature tree built
on this topology layer rather than pretending OpenCASCADE solves the
topological naming problem automatically.

Generated scripts declare that semantic history explicitly after each major
operation:

```python
register_feature(
    "mounting_holes",
    "Mounting hole pattern",
    "pattern",
    part.part,
    parent_id="base_plate",
    parameters={"count": 4, "spacing": 30.0},
)
```

Feature IDs are authored names that remain stable through parameter edits. The
sandbox snapshots topology at each declaration, then `/analyze-model` attributes
surviving final faces to the feature that introduced them. Legacy scripts remain
valid: they return an empty feature tree and list their faces as unassigned
instead of receiving guessed history. Scripts may declare up to 64 features.
`ownedFaceIds` are recomputed for each B-rep version; the authored feature ID,
not a face ID, is the cross-edit semantic handle.

Generated scripts can also declare stable, revision-aware design intent after
the referenced features exist:

```python
register_constraint(
    "plate_thickness",
    "thickness",
    ["base_plate"],
    parameters={"parameter": "thickness", "value": thickness, "unit": "mm"},
)
```

Constraints support dimensional kinds (`distance`, `angle`, `radius`,
`diameter`, `thickness`, and `count`) and relational kinds such as
`concentric`, `parallel`, and `symmetry`. They are validated, stored in topology
analysis, and preserved by the editing prompt. Numeric declarations that name an
authored feature parameter are reported as `satisfied` or `violated`.
Relationships requiring geometric reasoning are explicitly `unevaluated`.
These records do not claim to be a general geometric constraint solver.

`POST /compare-models` analyzes `previousCode` and `currentCode`, then reports:

- exact feature and constraint matches by stable authored ID, including changed
  fields and added or removed IDs
- exact face matches when content-addressed B-rep IDs survive
- conservative geometric face matches within the same authored feature, or
  among unassigned legacy faces
- unmatched faces when repeated or symmetric geometry is ambiguous

Pass an optional `previousFaceId` to receive `selectionRemap`. Persisted project
comparison automatically uses the previous revision's selected face. A remap is
reported as `matched`, `ambiguous`, `unmatched`, or `stale`; ambiguous matches
are never silently resolved.

Feature-ID matches have confidence 1 because identity is explicit. Geometric
face confidence is descriptor-based and never used to silently rename authored
features.

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

## Project persistence

The backend stores projects in SQLite at `backend/data/nfinit.db` by default.
Set `NFNIT_DATABASE_PATH` to place the database elsewhere. Each project begins
with revision 1, and every save appends an immutable snapshot containing code,
chat messages, model selection, selected-face context, and the latest agent run
ID. Loading an older revision never overwrites history; save it again to create
a new revision.

Project APIs:

- `POST /projects` and `GET /projects`
- `GET`, `PATCH`, and `DELETE /projects/{project_id}`
- `POST` and `GET /projects/{project_id}/revisions`
- `GET /projects/{project_id}/revisions/{revision_number}`
- `GET /projects/{project_id}/compare?previousRevision=1&currentRevision=2`

SQLite WAL mode and transactional revision numbering keep concurrent saves
consistent. Database files are excluded from Git.

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
