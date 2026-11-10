# Architecture

How Nfinit's backend builds, inspects, stores and evaluates CAD parts. For the
local agent connection, reference pictures and STL import, see
[OPEN_SOURCE_WORKSPACE.md](OPEN_SOURCE_WORKSPACE.md).

## API agent workflow (optional)

Runs with Claude Code or Codex use your own CLI; see
[OPEN_SOURCE_WORKSPACE.md](OPEN_SOURCE_WORKSPACE.md). The optional API path
(OpenRouter models, enabled only when `OPENROUTER_API_KEY` is set) runs a
LangGraph workflow in the FastAPI backend; Next.js only proxies requests. The
live CAD50 evaluation also uses this path.

1. **Retrieve** — find relevant build123d implementation patterns.
2. **Plan** — translate the product request into dimensions, constraints,
   features, and manufacturing intent.
3. **Generate** — produce parameterized build123d code from that plan.
4. **Inspect** — execute the code, measure its solids, volume, and bounding
   box, and compare them with the plan's expectations.
5. **Repair** — feed execution failures and geometry mismatches back to the
   model, retrying up to three times.

### Plan expectations

The plan ends with a fenced `expectations` block: the overall bounding box
(an axis is `null` when the plan does not fix it), the solid count, and any
assumption about how the request was read. The block is removed from the plan
that the studio shows. Assumptions become the plan's first line, so the chat
summary says how an ambiguous request was read.

The planner reads a stacked dimension from the surface the feature rises
from: "a 3 mm base with 12 mm tall walls" is 15 mm overall. Words such as
"overall" or "total" give the full size instead.

A part that builds but differs from the expectations by more than 0.1 mm (or
0.1%) goes to repair with the measured and expected values. A part that still
differs after three repairs is returned with the difference in its trace. When
the last repair does not build, the previous part that did build is kept, so a
repair cannot turn a usable part into an error. Plans without the block are
checked for execution only, as before.

Each step records a progress event when it starts and when it finishes
(`run_events`). `GET /cad/runs/{id}?after=<seq>` returns the run with the
events after that sequence number. The studio shows them as a live step
list, and the current model stays on screen while the next one builds.

The studio first follows the run as server-sent events. It asks for
`POST /cad/runs/{id}/stream` through the Next.js proxy and opens the returned
signed link (`GET /cad/runs/{id}/events?token=…`) directly on the backend,
because the proxy cannot hold a response open for a whole run. The stream
sends each event as soon as the run records it, a heartbeat every 15 seconds
(so proxies do not close an idle connection), and a final `done` event.
A reconnect resumes after the browser's `Last-Event-ID`. When the stream is
unavailable, the studio polls the status endpoint every second instead.

While the check step builds the part, the sandbox also writes a coarse
preview after each `register_feature` call (at most 16), tagging the faces
that feature added. Each preview becomes a `snapshot` progress event, and
`GET /cad/runs/{id}/snapshots/{seq}` serves its GLB to the run's owner.
Previews are kept in memory only while a run is watched. The studio plays them
at least half a second apart, so the part visibly grows feature by feature,
then replaces them with the finished part.

Clicking a model face adds its local point and normal to the next request, so prompts such as “add a mounting hole on this face” can target the selected geometry.

### build123d pattern RAG

Retrieval works without external credentials. The default local corpus,
`backend/agent/retrieval/corpus/build123d-v0.10.0.jsonl`, is ranked with
deterministic lexical scoring (common words such as "with" and "the" are
ignored). Only the latest text request and selected surface type are used as
the search query. Search runs against the bundled files; no embeddings API,
vector database, or external search service is required.

The shipped corpus has 367 unique patterns, all from build123d 0.10.0 (the
version in `poetry.lock`, tag commit `fa8e936`):

| Source | Patterns |
| --- | ---: |
| Official examples and docs (code windows around each CAD call) | 82 |
| Official unit tests that build in the sandbox | 217 |
| CAD50 reference solutions | 50 |
| Curated patterns (`patterns.json`) | 18 |

Each unit test becomes one runnable pattern: its assertions become
`# check:` comments that state the result the test verifies, expected
failures (`assertRaises`) are dropped, and a `result = ...` line names the
built shape. A test is kept only when it passes the CAD code policy and builds
valid geometry in the sandbox; 217 of the 342 policy-valid tests do. Rebuild the
corpus when `poetry.lock` moves to a new build123d release, from that release:

```bash
curl -sL -o /tmp/build123d.tgz \
  https://github.com/gumyr/build123d/archive/refs/tags/v0.10.0.tar.gz
mkdir -p /tmp/build123d && tar -xzf /tmp/build123d.tgz -C /tmp/build123d --strip-components 1
cd /path/to/Nfinit/backend
CAD_SANDBOX_MODE=fork poetry run python -m agent.retrieval.ingest \
  --source-root /tmp/build123d \
  --revision "$(gh api repos/gumyr/build123d/commits/v0.10.0 --jq .sha)" \
  --replays evaluation/replays/cad50.json \
  --seed-corpus agent/retrieval/patterns.json \
  --output agent/retrieval/corpus/build123d-v0.10.0.jsonl
```

Use `--no-tests` to leave out the unit tests, or `--skip-sandbox` to keep
policy-valid tests without building them. The command prints the source revision
and each source's count. The default quality gate requires at least 100 unique patterns.

CadQuery's tests are not included: CadQuery runs on the same OpenCASCADE
kernel but has a different API (`cq.Workplane(...)`), so its snippets would
teach calls that the build123d sandbox does not have.

Set `PATTERN_RAG_ENABLED=false` to disable retrieval, or
`PATTERN_RAG_LOCAL_CORPUS` to use another corpus file.

build123d is Apache-2.0. Its `LICENSE` and `NOTICE` ship next to the corpus
(`LICENSE-build123d`, `NOTICE-build123d`); keep them with any exported or
redistributed copy, and each pattern keeps its source URL and license.

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
sandbox snapshots topology at each declaration, then `/analyze-model` gives
each final face to the feature that first created it: the first snapshot with
a face on the same surface (plane, cylinder, cone, sphere or torus). A face
whose outline a later feature reshapes, such as a plate side rounded by a
fillet or a top face cut by a hole, stays with the feature that made it.
Faces on other surfaces fall back to the last feature that produced exactly
that face. Legacy scripts remain valid: they return an empty feature tree and
list their faces as unassigned instead of receiving guessed history. Scripts may declare up to 64 features.
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

Importing OpenCASCADE takes seconds, while most parts build in milliseconds.
On Linux the backend therefore starts one fork server at startup that imports
build123d once. Each job runs in a fresh child forked from that clean process
and serves only that job, so nothing carries over between jobs. The child
applies the limits above, and a job past its deadline is killed. The fork
server refuses to start if OpenCASCADE has started threads, and the backend
falls back to one-shot workers whenever the fork server is unavailable. Set
`CAD_SANDBOX_MODE=spawn` to always use one-shot workers.
`CAD_SANDBOX_MAX_CONCURRENCY` (default 4) limits how many jobs run at once.

The limits can be tuned with the `CAD_SANDBOX_*` variables documented in
`backend/.env.example`.

## Tracing

Every CAD run receives a UUID that is returned as `runId`. Node latency and
OpenRouter token usage are included in the API response and shown in the chat.
Progress events and evaluation reports stay in Nfinit. Optional Python debug
logging records run IDs, node names, status and timing, without prompt, code
or image payloads. No telemetry service or cloud tracing account is needed.

## Project persistence

The backend stores projects in SQLite at `backend/data/nfinit.db` by default.
Set `NFNIT_DATABASE_PATH` to place the database elsewhere. Each project begins
with revision 1, and every save appends an immutable snapshot containing code,
chat messages, model selection, selected-face context, and the latest agent run
ID. Loading an older revision never overwrites history; save it again to create
a new revision.

The studio's GLB holds one glTF node per B-rep face, named and tagged with
its content-addressed face ID, surface type and owning feature, plus one line
node with the part's edges (seams left out). The scene's extras carry the
topology version and the feature list. The viewer draws the edges over the
faces, highlights the face under the pointer, and takes a clicked face's ID
straight from the mesh, so selecting a face needs no backend call.

Each project keeps its latest built mesh (GLB) and geometry facts. The studio
asks for `GET /projects/{project_id}/revisions/{n}/mesh` through the Next.js
proxy and receives a signed link that expires after five minutes. The browser
downloads the GLB directly from the backend with that link, so mesh size is
not limited by the proxy. Viewing another revision rebuilds its mesh on the
warm sandbox and stores it in place of the previous one. Set
`NFNIT_MESH_URL_SECRET` in production so links survive restarts.

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
  It requires `OPENROUTER_API_KEY` and writes the same local JSON reports.
  With `--agent local/claude` or `--agent local/codex` instead of a model, it
  runs each case through your installed Claude Code or Codex CLI, the same path
  the local studio uses. That uses your own CLI login and usage, so it never
  runs in CI.

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

The quality-first matrix pins Claude Sonnet 5.5 and Claude Opus 5.5, the models the
studio ships, so comparisons
remain reproducible even when OpenRouter's `*-latest` aliases change.
Reports include overall and per-metric results, repairs, latency, and token costs.

The **Live CAD model evaluation** GitHub workflow runs both models on demand.
Choose `smoke` for six paid agent runs or `cad50` for the complete 110-run
comparison. Configure the `OPENROUTER_API_KEY` repository secret before running it.

The weekly smoke schedule is skipped unless the repository variable
`ENABLE_SCHEDULED_PAID_EVALS` is exactly `true`. Reports are retained as workflow
artifacts for 90 days.

Reports compare pass rate, geometry accuracy, policy compliance, repair count,
latency, and token usage by model. A nonzero exit code indicates a regression.

The `cad50.json` benchmark contains 55 balanced cases across primitives,
subtractive features, patterns, sketch profiles, edge finishing, mechanical
parts, iterative edits, selected-face edits, failure recovery,
manufacturing-oriented products, and dimension reading (stacked and overall
heights). The file keeps its `cad50` name so earlier reports stay comparable.
Validate all canonical outputs locally with:

```bash
python -m evaluation.cli \
  --cases evaluation/cases/cad50.json \
  --mode replay \
  --replays evaluation/replays/cad50.json \
  --output evaluation/reports/cad50.json
```

Pull requests that change the backend run this benchmark in GitHub Actions.
`evaluation/baselines/cad50.json` requires all 55 case IDs, five cases in each
category, complete metric coverage, and a 100% canonical replay pass rate. The
JSON report is uploaded as a 30-day workflow artifact. Validate a report against
the same policy locally with:

```bash
python -m evaluation.gate \
  --report evaluation/reports/cad50.json \
  --cases evaluation/cases/cad50.json \
  --policy evaluation/baselines/cad50.json
```

### loop20: failures that still build

`loop20.json` has 20 cases, four in each of five categories, for parts that
build without an error but are still wrong:

| Category | Catches |
| --- | --- |
| `silent_finish` | A fillet or chamfer that was left out |
| `detached` | A boss, standoff or gusset that floats as a second solid |
| `stacked_reading` | A wall or stem height read as the overall height |
| `hole_pattern` | The wrong number, size or spacing of holes |
| `edit_regression` | An edit that loses holes or rounded edges it was not asked to change |

Besides bounds, solid count and volume, a case can list `features`: holes,
bosses or rounded edges of a given size, with an exact or minimum count and the
extent of their centres (`center_span_mm`, which does not depend on where the
origin is). They are scored from the inspection's `census`, which the sandbox
counts from the part's faces: a full cylindrical face pointing at its axis is a
hole, one pointing away is a boss, and a cylindrical face under half a turn, a
torus or a sphere is a rounded edge.

`tests/test_loop20.py` holds wrong solutions for each category and asserts that
scoring fails them. Run the suite and its gate like CAD50:

```bash
python -m evaluation.cli \
  --cases evaluation/cases/loop20.json \
  --mode replay \
  --replays evaluation/replays/loop20.json \
  --output evaluation/reports/loop20.json
python -m evaluation.gate \
  --report evaluation/reports/loop20.json \
  --cases evaluation/cases/loop20.json \
  --policy evaluation/baselines/loop20.json
```

Measure a change to the agent loop with a live run through a local agent:

```bash
python -m evaluation.cli \
  --cases evaluation/cases/loop20.json \
  --mode live --agent local/claude \
  --output evaluation/reports/loop20-live.json
```

Live results vary from run to run, so compare the mean of three runs. The
baseline before the loop work is in `docs/evaluations/loop20-baseline.md`.
