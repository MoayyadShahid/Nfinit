# CAD loop plan: match text-to-cad, then pass it

Status: work packages 0 to 9 done. Work packages 10 and 11 wait for the owner's decisions. Written 2026-11-10 against `main` at `52be5f3`.
Progress and changes to the plan are recorded in section 10.

This is a handoff document. It assumes you have the repository and nothing
else: no earlier conversation, no other notes. Read sections 1 to 5 once, then
do the work packages in section 6 in order. Each work package is one pull
request.

## 1. Goal

Nfinit's local agents (Claude Code and Codex) write build123d code and call a
`build_model` tool that builds and measures it. The loop writes code well but
checks it badly. [text-to-cad](https://github.com/earthtojake/text-to-cad) is a
set of agent skills with a much stronger checking step.

The goal has two parts:

1. **Match it.** Give Nfinit's agents the same ability to look at, measure and
   question a part.
2. **Pass it.** text-to-cad is guidance that an agent may or may not follow.
   Nfinit owns the loop, so it can enforce the checks, run checks the agent did
   not write, and show the evidence to the user.

**Done means:**

- Every work package in section 6 is merged, or explicitly dropped by the owner.
- The `loop20` benchmark (work package 0) passes in replay mode in CI.
- A live run of `loop20` with a local agent scores higher after the work than
  the baseline recorded in work package 0. Both numbers are in
  `docs/evaluations/`.
- Existing behaviour still works: all backend tests pass, the CAD50 gate passes,
  the frontend builds, and the studio controls test passes.

**Out of scope:** circuit boards, robot simulation, sheet metal, photoreal
renders, stress analysis and engineering drawings. text-to-cad has these.
Nfinit should win at one correct, printable part first.

## 2. How the loop works today

Paths are relative to the repository root.

| Piece | File | What it does |
| --- | --- | --- |
| Launcher | `scripts/local.py` | Starts the backend and the studio on loopback with a shared token. |
| Run entry | `backend/projects/runs.py` (`_execute_run`) | Runs `run_local_agent` for `local/claude` and `local/codex`, otherwise the hosted graph. Saves the result as a revision. |
| Local agent runner | `backend/agent/local.py` | Builds the prompt, starts the CLI in a temporary workspace with one MCP server, waits, then rebuilds the final code itself. |
| MCP bridge | `backend/agent/cad_mcp.py` | A stdio MCP server with two tools: `current_design` and `build_model`. Limit of 8 builds. |
| Prompts | `backend/agent/prompts.py` | `PLANNER_PROMPT` (hosted only) and `CAD_SYSTEM_PROMPT` (both paths). |
| Plan check | `backend/agent/expectations.py` | Parses the planner's `expectations` block and compares bounds and solid count. Hosted only. |
| Hosted graph | `backend/agent/graph.py` | retrieve → plan → generate → inspect → repair, through OpenRouter. Optional path. |
| Sandbox runner | `backend/execution/runner.py` | `inspect_code`, `analyze_code`, `export_code`, `build_mesh`, `inspect_with_snapshots`. One sandbox job per call. |
| Sandbox worker | `backend/execution/worker.py` | Runs the code with a restricted scope. `_inspect`, `_topology`, `_entity_records`, `_feature_tree`, `_surface_key`, GLB export. |
| Code policy | `backend/execution/policy.py` | AST allow and block rules for generated code. |
| Topology models | `backend/execution/topology.py` | Faces, edges, features, constraints, revision comparison models. |
| Revision comparison | `backend/execution/rematching.py` | `compare_analyses`, `compare_code`. Used by the studio, not by the agent loop. |
| Views and STL | `backend/execution/references.py` | `model_views` exports an STL and draws three flat views with Pillow. |
| Result models | `backend/agent/models.py` | `ModelInspection`, `CadRunRequest`, `FaceSelection`. |
| Benchmark | `backend/evaluation/` | Cases, replays, scoring, CI gate. `evaluate_live` only supports the hosted graph. |
| Studio | `frontend/src/components/Studio.tsx`, `ViewportPane.tsx` | Shows the part, the chat and a one-line count of passed checks. |

One local run, step by step:

1. `prepare_input` writes `context.txt` and `model.py` into the workspace and
   builds one prompt: `CAD_SYSTEM_PROMPT` with two `.replace()` edits plus a
   paragraph of instructions.
2. The CLI runs with only the Nfinit MCP tools allowed.
3. Each `build_model` call runs the sandbox **twice**: once for `inspect_code`
   and once more inside `model_views` to export an STL. It returns the
   inspection JSON and three 640×480 images.
4. When the CLI exits, the backend runs the final code again and saves it.

What a build reports (`ModelInspection`): `valid`, `shape_type`, `solid_count`,
`volume_mm3`, `bounding_box_mm`, `checks` (from `check_measurement` calls in
the code), `verification` and `reference_comparison`.

## 3. The gaps

Each gap is confirmed by reading the code. Gaps 3 and 4 were also confirmed by
running the libraries.

| # | Gap | Evidence |
| --- | --- | --- |
| G1 | The agent sees three fixed, flat, low-resolution views with no real edges, and cannot choose a view or cut a section. | `render_views` in `references.py`. |
| G2 | The agent cannot ask about geometry without rebuilding. | Only `check_measurement` exists. |
| G3 | Local agents get no plan check and no dimension-reading rules. | `expectations.py` and the stacked-dimension rules in `PLANNER_PROMPT` are used only by `graph.py`. |
| G4 | Validity is thin. An inside-out solid passes. Extra solids are not flagged. | `_inspect` requires `is_valid` and a finite total volume. A reversed unit box has volume −1 and `is_valid` is true (confirmed). |
| G5 | The prompt has no kernel pitfalls. | `CAD_SYSTEM_PROMPT`. |
| G6 | Review rules are one sentence: "Review its measured checks and rendered images." | `prepare_input`. |
| G7 | No printability checks. | None in the backend. |
| G8 | Two sandbox runs per build. Run deadline of 300 s is shared with the hosted path. | `cad_mcp.py`, `run_timeout_seconds`. |
| G9 | The benchmark only scores bounds, solid count and sometimes volume. A part with a missing fillet passes `finish_fillet_box`. | `backend/evaluation/cases/cad50.json`, `scoring.py`. |
| G10 | The benchmark cannot run a local agent. | `evaluate_live` calls `run_cad_agent` only. |

Where Nfinit is already ahead, and must stay ahead:

- Generated code runs in a sandbox with no network. text-to-cad runs the
  agent's Python with full access to the machine.
- Saved revisions, face picking, registered features and constraints.
- STL import and comparison against the reference mesh.
- A deterministic benchmark gate in CI.

## 4. Environment

### 4.1 Python

The repository needs Python 3.11 or 3.12. Python 3.13 does not work: the
OpenCASCADE wheel (`cadquery-ocp`) does not install, and every sandbox test
fails with `No module named 'OCP'`.

This setup was tested on macOS arm64 with Python 3.12 and gave
**210 passed, 20 skipped in about 6 minutes**:

```sh
cd backend
poetry env use 3.12          # install it first if needed: uv python install 3.12
poetry install --with dev --no-root
NFNIT_ALLOW_LOCAL_AUTH_BYPASS=true poetry run python -m pytest -q
```

If Poetry cannot build the environment, this also works and was the route
actually tested:

```sh
uv venv --python 3.12 .venv-cad
python3 - <<'EOF' > /tmp/req.txt
import tomllib
for p in tomllib.load(open("backend/poetry.lock", "rb"))["package"]:
    print(f'{p["name"]}=={p["version"]}')
EOF
uv pip install --python .venv-cad/bin/python -r /tmp/req.txt
cd backend && NFNIT_ALLOW_LOCAL_AUTH_BYPASS=true ../.venv-cad/bin/python -m pytest -q
```

Install the exact versions from `poetry.lock`. Unpinned installs pull a newer
`ocp-gordon` that breaks `import build123d`.

Locked versions that this plan relies on: build123d 0.10.0, cadquery-ocp
7.8.1.1.post1, numpy 2.2.6, scipy 1.15.3, pillow 12.1.1. numpy and scipy are
already installed as build123d dependencies. **Do not add new dependencies.**
In particular, do not add trimesh: section 6 gives numpy versions of what is
needed.

### 4.2 Checks to run before every pull request

```sh
# Backend
cd backend
NFNIT_ALLOW_LOCAL_AUTH_BYPASS=true poetry run python -m pytest -q
poetry run python -m evaluation.cli --cases evaluation/cases/cad50.json \
  --mode replay --replays evaluation/replays/cad50.json \
  --output evaluation/reports/cad50.json
poetry run python -m evaluation.gate --report evaluation/reports/cad50.json \
  --cases evaluation/cases/cad50.json --policy evaluation/baselines/cad50.json

# Frontend (only when frontend files change)
cd ../frontend
npx tsc --noEmit && npm run lint && npm run build
```

CI runs the same things: `.github/workflows/cad-regression.yml` for `backend/**`
and `.github/workflows/frontend.yml` for the frontend.

Known local traps:

- If `tsc` reports errors in `.next/types`, delete `frontend/.next/types` and
  `frontend/.next/dev/types` and run it again.
- `next dev` sometimes creates `frontend/AGENTS.md`. Delete it. Do not commit it.
- On macOS the sandbox uses spawn mode, so each sandbox job takes a few
  seconds. On Linux it uses a fork server and is much faster.

### 4.3 Library behaviour confirmed for this plan

These were run against the locked versions. Build on them without re-checking.

| Fact | Result |
| --- | --- |
| `shape.project_to_viewport(origin, viewport_up=, look_at=)` | Returns `(visible_edges, hidden_edges)`. Orthographic. About 10 ms for a simple part. |
| Its 2D frame | With `fwd = normalize(look_at − origin)`, `right = normalize(fwd × up)`, `cam_up = right × fwd`, a point `p` maps to `((p − look_at)·right, (p − look_at)·cam_up)`. A tessellated part projected this way has the same 2D bounding box as the returned edges. |
| Cylinder faces | `face.geom_type == GeomType.CYLINDER`, `face.radius`. `BRepAdaptor_Surface(face.wrapped)` gives the axis, and `LastUParameter() − FirstUParameter()` gives the angular span: 360° for a hole or boss, 90° for a fillet on a square corner. `LastVParameter() − FirstVParameter()` gives the length along the axis. |
| Hole or boss | Take a point on the face and its normal. If the normal points toward the axis, the face is concave (a hole). If it points away, it is convex (a boss or a rounded edge). |
| `Hole(radius, depth)` in a `BuildPart` | Drills in −Z from the active location. `Hole(radius)` without a depth cuts through. |
| Distance | `BRepExtrema_DistShapeShape(a.wrapped, b.wrapped).Value()` gives the minimum distance. `shape.distance_to(other)` also exists. |
| Overlap | `(a & b).volume` gives the intersection volume. |
| Inside-out solid | `solid.wrapped.Reverse()` gives volume −1 for a unit box and `is_valid` stays true. |
| Tessellation | `shape.tessellate(0.1, 0.3)` returns `(vertices, triangles)`. Per-face tessellation with `face.tessellate(...)` also works, which lets a triangle be traced back to its face. |
| Default alignment | `Box` and `Cylinder` are centred on all three axes by default. `Box(40, 30, 12)` spans Z −6 to +6. |

One thing that did **not** reproduce: selecting edges, cutting a hole elsewhere,
then filleting the earlier selection worked without error. So do not write
"stale edge selections are silently skipped" into the prompt unless you produce
a failing example first (see the rule in work package 1).

## 5. Rules for all work packages

1. **The sandbox boundary does not move.** Generated code runs only in
   `backend/execution/worker.py`. All geometry work (measuring, rendering,
   printability) also runs in the worker. The MCP bridge never executes
   generated code, never takes a file path from the agent and never gains a
   shell or network tool.
2. **Every new tool input is validated and bounded**: enum values, numeric
   ranges, list lengths, string lengths. Every tool output is capped in size.
3. **New result fields are optional.** `ModelInspection` is stored inside saved
   revisions and in `frontend/src/lib/demos.ts`. Old data must still load.
4. **Do not break the hosted graph.** `backend/agent/graph.py` must keep
   passing its tests. Share code with it where that is free; do not extend it
   unless a work package says so.
5. **Facts, then verdicts.** A measuring function returns numbers and where
   they were measured. A separate step compares them with a requirement or a
   limit. A check that could not run is reported as `unverified`, never as a
   pass.
6. **Write Nfinit's own wording.** text-to-cad is MIT-licensed and is already
   credited in the README. Use its ideas; do not paste its text or code.
7. **Match the surrounding code**: comment density, naming and style. Units are
   millimetres, +Z is up, X is width, Y is depth.
8. **One work package, one pull request**, on a branch named
   `claude/loop-<n>-<slug>`. Do not push to `main`. Merge only when the owner
   says so, after CI passes.
9. **Each pull request updates the docs it makes untrue**:
   `docs/OPEN_SOURCE_WORKSPACE.md` (section "Agent connection and loop"),
   `docs/ARCHITECTURE.md`, `docs/MODEL_EVALUATION.md` and `CHANGELOG.md`
   (under "Unreleased").

## 6. Work packages

Order and dependencies:

| # | Work package | Depends on | Size |
| --- | --- | --- | --- |
| 0 | Benchmark that can see the problems | none | Medium |
| 1 | Prompt: one template, pitfalls, review rules | 0 | Small |
| 2 | Strict validity and feature census | 0 | Medium |
| 3 | Requirements contract and enforced acceptance | 1, 2 | Medium |
| 4 | `inspect_model` tool | 2 | Medium |
| 5 | Renderer and `view_model` tool, one sandbox run per build | 2 | Large |
| 6 | Printability checks | 5 | Large |
| 7 | Edit safety | 2, 3 | Medium |
| 8 | Evidence panel in the studio | 3, 6, 7 | Medium |
| 9 | Speed and budgets | 5 | Medium |
| 10 | Slicing and print profiles (needs owner sign-off) | 6, 8 | Large |
| 11 | Richer pointing in the studio (needs owner sign-off) | 4, 8 | Large |

### Work package 0: a benchmark that can see the problems

**Why first:** without it, nothing later can be shown to help (G9, G10).

**Changes**

1. `backend/evaluation/models.py`: add to `GeometryExpectation`

   ```python
   class FeatureExpectation(BaseModel):
       kind: Literal["hole", "boss", "rounded_edge"]
       diameter_mm: float | None = None      # hole, boss
       radius_mm: float | None = None        # rounded_edge
       count: int | None = None              # exact count when given
       min_count: int | None = None          # at least this many
       tolerance_mm: float = 0.05

   features: list[FeatureExpectation] = Field(default_factory=list)
   max_solids_inverted: int = 0
   ```

   Feature scoring needs the census from work package 2. Until that merges,
   `score_evaluation` scores a case with `features` as failed with the message
   "Feature census is not available." Write the scoring function now against
   the census shape defined in work package 2, and test it with hand-written
   census dictionaries.

2. `backend/evaluation/scoring.py`: add a `features` metric (one score per
   expected feature, named `feature_<index>_<kind>`) and an `inverted_solids`
   metric.

3. New suite `backend/evaluation/cases/loop20.json` with 20 cases, four in each
   of five categories. Each case has full expectations including `features`.

   | Category | What it catches | Example prompt |
   | --- | --- | --- |
   | `silent_finish` | A fillet or chamfer that was skipped | "Create a 40 by 30 by 12 mm box and apply 2 mm fillets to the four vertical edges." Expect 4 rounded edges of radius 2. |
   | `detached` | A feature that floats as a second solid | "A 60 by 40 by 5 mm plate with a 10 mm diameter, 8 mm tall boss centred on top." Expect 1 solid, bounds Z 13, one boss of diameter 10. |
   | `stacked_reading` | Wrong overall height from stacked dimensions | "A tray with a 3 mm base and 12 mm tall walls, 80 by 50 mm outside, 2 mm wall." Expect Z 15. |
   | `hole_pattern` | Wrong count, size or position of holes | "An 80 by 50 by 6 mm plate with four 4 mm through-holes 6 mm from each corner." Expect 4 holes of diameter 4. |
   | `edit_regression` | An edit that damages something else | Start code with a plate, two holes and filleted corners. "Change the plate thickness from 5 to 8 mm." Expect the holes and rounded edges to remain. |

4. `backend/evaluation/replays/loop20.json`: a correct recorded solution for
   every case, so the suite runs in CI without a model.

5. **Negative replays.** In `backend/tests/test_evaluation.py`, add for each
   category one wrong solution that builds (fillet left out, boss offset so it
   floats, tray 12 mm tall, three holes, edit that drops the fillets) and
   assert that scoring fails it. These tests are the proof that the benchmark
   sees each failure. They will only pass after work package 2; mark them
   `xfail(strict=True)` until then and remove the mark in work package 2.

6. Local agents in the benchmark. `backend/evaluation/runner.py`: add
   `evaluate_local(cases, agent_ids, inspector=inspect_code)` that calls
   `agent.local.run_local_agent` and scores the result the same way as
   `evaluate_live`. `backend/evaluation/cli.py`: add
   `--agent local/claude|local/codex` (repeatable), valid only with
   `--mode live`. When `--agent` is given, the CLI sets
   `NFNIT_LOCAL_AGENTS=true`, `NFNIT_ALLOW_LOCAL_AUTH_BYPASS=true` and a random
   `NFNIT_LOCAL_TOKEN` for the process, because `local_agents_enabled()` reads
   them. This mode uses the developer's own CLI login and usage, so it is never
   run in CI.

7. CI: add a `loop20` job to `.github/workflows/cad-regression.yml` that mirrors
   the `cad50` job, with a policy file `backend/evaluation/baselines/loop20.json`.

8. Record the baseline. Run
   `python -m evaluation.cli --cases evaluation/cases/loop20.json --mode live --agent local/claude --output evaluation/reports/loop20-baseline.json`
   and write the pass rate per category to
   `docs/evaluations/loop20-baseline.md`. If you cannot run a local agent, say
   so in the pull request and ask the owner to run this one command.

**Acceptance**

- `loop20` passes in replay mode, locally and in CI.
- The negative-replay tests exist (xfail for now).
- The baseline file exists, or the pull request says who must produce it.

### Work package 1: prompt

**Fixes:** G3 (in part), G5, G6.

**Changes**

1. `backend/agent/prompts.py`: split the prompt into named blocks and stop
   building the local prompt with `.replace()`.

   - `DIMENSION_READING_RULES`: move the "Read stacked dimensions this way"
     paragraph out of `PLANNER_PROMPT` into a constant used by both
     `PLANNER_PROMPT` and the local prompt. The hosted planner's text must not
     change (assert this in a test by comparing with the current string).
   - `CAD_API_REFERENCE`: the existing `<available_api>` and `<examples>` blocks.
   - `KERNEL_PITFALLS`: new, below.
   - `REVIEW_RULES`: new, below.
   - `local_agent_prompt(context: str) -> str`: returns the full prompt for
     Claude Code and Codex. `prepare_input` in `backend/agent/local.py` calls
     it. `CAD_SYSTEM_PROMPT` stays as the hosted prompt and gains
     `KERNEL_PITFALLS`.

2. `KERNEL_PITFALLS`, draft text:

   ```
   <kernel_pitfalls>
   - Primitives are centred on all three axes by default. Box(40, 30, 12)
     spans Z -6 to +6. To sit a feature on a surface, give
     align=(Align.CENTER, Align.CENTER, Align.MIN) and place it at that
     surface's height.
   - Hole(radius, depth) drills downward (-Z) from the active location.
     Place the location on the face being drilled. Hole(radius) with no depth
     cuts through the whole part.
   - A cut that misses the part removes nothing and raises no error. After a
     subtractive feature, check the volume went down or measure the feature.
   - An added feature that does not touch the part becomes a second solid and
     raises no error. Check the number of solids after every additive feature.
   - Fillet and chamfer last, after every Boolean. Select the edges from the
     part as it is at that moment, by position or direction, not by index.
   - A fillet radius must be smaller than half the thinnest wall next to the
     edge, or the kernel fails or returns a damaged solid.
   - A Polygon listed clockwise (seen from +Z) faces down and extrudes
     downward. List points anticlockwise.
   - Two faces that only just touch or coincide can make a Boolean return the
     wrong region. Overlap the tool by a small margin rather than aligning it
     exactly with a face.
   </kernel_pitfalls>
   ```

   **Rule: every pitfall in the prompt must be backed by a test.** For each
   line, add a test in `backend/tests/test_prompt_pitfalls.py` that runs a few
   lines of build123d through `inspect_code` and shows the behaviour (for
   example: `Box(40, 30, 12)` has `bounding_box().min.Z == -6`). If you cannot
   demonstrate a pitfall on the locked versions, delete that line. Lines 1 and
   2 are already confirmed (section 4.3). Lines 3 to 8 are not.

3. `REVIEW_RULES`, draft text:

   ```
   <review_rules>
   - Never read a dimension off an image. Images show arrangement and
     appearance only. Dimensions come from measurements.
   - Turn every visual doubt into a measurement. If a hole pattern looks
     uneven, measure the hole centres. If a boss looks detached, check the
     number of solids and the contact.
   - A check that fails, or that could not run, proves nothing about the
     design. Do not report it as verified.
   - Do not weaken the request to make the build pass. Dropping a fillet,
     shrinking a radius or removing a feature is a different design. If a
     requirement cannot be met, keep the closest correct part and say so.
   - Rebuild only when the code changed. Do not rebuild just to look again.
   - Finish with: what changed, each requirement and its measured value,
     what was not verified, and every assumption.
   </review_rules>
   ```

4. Replace the one-paragraph instruction in `prepare_input` with a numbered
   procedure inside `local_agent_prompt`. Work package 3 adds the requirements
   step; in this work package the procedure is:
   read the design → plan (with the overall size stated first) → build →
   review measurements, then images → repair → final summary.

**Tests**

- `backend/tests/test_local_agents.py`: the local prompt contains the
  dimension rules, the pitfalls and the review rules; it no longer contains
  "Return only executable Python code"; the hosted planner prompt is unchanged.
- `backend/tests/test_prompt_pitfalls.py` as described.

**Acceptance:** tests pass. Run `loop20` live once and add the numbers to the
pull request, next to the baseline.

### Work package 2: strict validity and feature census

**Fixes:** G4, and makes the work package 0 scoring real.

**Changes in `backend/execution/worker.py`**

1. `_inspect(result, checks=None, feature_records=None)` returns these extra
   keys. All are additive.

   ```json
   {
     "solids": [
       {"volume_mm3": 41193.81, "bounding_box_mm": {"x": 80, "y": 50, "z": 20},
        "min_mm": [-40, -25, -5], "manifold": true, "inverted": false}
     ],
     "warnings": ["2 separate solids: the smallest is 0.4% of the total volume."],
     "census": {
       "holes": [{"diameter_mm": 4.0, "count": 4, "axis": [0, 0, 1],
                  "length_mm": 6.0, "centers_mm": [[-34, -19, 0], "..."]}],
       "bosses": [{"diameter_mm": 10.0, "count": 1, "axis": [0, 0, 1],
                   "length_mm": 8.0, "centers_mm": [[0, 0, 9]]}],
       "rounded_edges": [{"radius_mm": 2.0, "count": 4, "surface": "cylinder"}],
       "face_counts": {"plane": 6, "cylinder": 9},
       "features": [{"id": "edge_fillet", "operation": "fillet", "owned_faces": 4}]
     }
   }
   ```

2. Census rules (see section 4.3 for the calls):

   - **Hole:** concave cylindrical faces grouped by axis line and radius whose
     angular spans sum to 360° within 1°. Use `_surface_key(face)` to group: it
     already encodes axis and radius. A kernel may split one hole into two
     180° faces, so sum the spans per key.
   - **Boss:** the same, for convex faces.
   - **Rounded edge:** a convex or concave cylindrical face with a span under
     180°, or a toroidal or spherical face. Group by radius. Report
     `surface` as `cylinder`, `torus` or `sphere`.
   - Group holes and bosses that share diameter, axis direction and length
     into one entry with `count` and `centers_mm`. Round to 3 decimals. Cap
     each list at 50 entries and add `"truncated": true` when cut.
   - `features`: for each registered feature, the number of final faces it
     owns, from `_feature_tree`. This needs `_entity_records(result)`. That
     function compares every face edge against every edge, so skip the
     `features` list (and add the warning "Feature ownership skipped: part has
     N faces.") when the part has more than 400 faces.

3. Validity rules. `valid` becomes false, with a clear `error`, when:

   - any solid has `volume <= 0` (error: "Solid N is inside out (negative
     volume). Build it another way, for example one extruded or revolved
     profile instead of stacked Booleans.");
   - any solid is not manifold;
   - the result has no solids and is not a 2D shape. Keep the existing
     exception: retrieval patterns contain legitimate sketches and wires, so
     only apply the solid rules when `shape_type` is `Part`, `Solid` or
     `Compound` with at least one solid.

   These become **warnings**, not failures, in this work package:

   - more than one solid;
   - a registered feature with operation `additive`, `subtractive`, `pattern`,
     `fillet` or `chamfer` that owns zero faces ("Feature 'edge_fillet' left
     no faces. It may have been skipped or fully removed by a later feature.").

   Work package 3 turns the solid-count warning into a failure when it
   contradicts the declared requirements.

4. `handle_request`: pass `feature_records` to `_inspect` for the `inspect` and
   `glb` operations.

**Changes elsewhere**

- `backend/agent/models.py`: add `solids`, `warnings` and `census` to
  `ModelInspection` with empty defaults.
- `backend/evaluation/scoring.py`: score `features` and `inverted_solids` from
  the census. Remove the `xfail` marks from work package 0.
- `frontend/src/lib/types.ts`: add the optional fields to `ModelInspection`.

**Tests** (`backend/tests/test_sandbox.py` or a new `test_census.py`)

- Plate with four holes → one hole entry, count 4, diameter 4.
- Box with four filleted vertical edges → rounded edges radius 3, count 4.
- Boss placed off the plate → 2 solids and a warning.
- Fillet registered but not applied → zero-face warning.
- A reversed solid cannot be produced by policy-compliant code easily, so test
  `_inspect` directly in a worker-level test with a shape built by
  `Solid.make_box(1, 1, 1)` and `wrapped.Reverse()`.
- All CAD50 replays and all demo builds (`backend/tests/test_demos.py`) still
  pass. If a legitimate recorded part fails a new validity rule, stop and
  report it in the pull request rather than loosening the rule silently.

**Acceptance:** the negative replays from work package 0 now fail scoring for
the right reason, and CAD50 still passes.

### Work package 3: requirements contract and enforced acceptance

**Fixes:** G3. This is the first step past text-to-cad.

**Idea:** before building, the agent must state what the part has to measure.
The bridge then checks every build against that list, rejects fake checks, and
reports which requirements are proven. The agent cannot mark its own work
verified.

**New module `backend/agent/acceptance.py`** (pure Python, no sandbox)

```python
class Requirement(TypedDict):
    id: str            # ^[a-z][a-z0-9_]{0,63}$
    text: str          # <= 200 chars, plain language
    kind: Literal["dimension", "count", "feature", "relation", "visual"]
    expected: float | None
    unit: Literal["mm", "deg", "count", "mm2", "mm3"] | None
    tolerance: float | None
    source: Literal["user", "assumed"]

def parse_requirements(arguments: dict) -> RequirementSet: ...
def stated_numbers(text: str) -> list[float]: ...
def uncovered_numbers(text: str, requirements: RequirementSet) -> list[float]: ...
def self_checks(code: str) -> list[str]: ...
def evaluate(requirements: RequirementSet, inspection: dict) -> Acceptance: ...
```

- `RequirementSet` holds `summary`, `bounding_box_mm` (x, y, z, each a number
  or null), `solid_count`, `requirements` (at most 32) and `assumptions` (at
  most 5). Reuse `PlanExpectations` and `check_geometry` from
  `expectations.py` for the bounds and solid-count comparison.
- `stated_numbers`: every numeric token in the user's latest message.
  `uncovered_numbers`: those that appear in no requirement's `expected` or
  `text` and in no bound. This catches a requirement the agent left out. It is
  a warning, because some numbers are not dimensions.
- `self_checks`: parse the code with `ast`. Collect names assigned from
  expressions made only of numeric literals, arithmetic and other such names.
  A `check_measurement(...)` call whose `actual` argument contains no `Call`
  and no `Attribute` node, only those names and literals, is a self-check.
  Return its names.
- `evaluate` gives each requirement a status:
  - `passed` or `failed`: a `check_measurement` whose name equals the
    requirement id exists, is not a self-check, and passed or failed. Census
    data can also settle a requirement: kind `count` or `feature` with a
    matching census entry.
  - `unverified`: kinds `dimension`, `count`, `feature` and `relation` with no
    such check.
  - `not_measurable`: kind `visual`.
  - Plus two built-in rows, `overall_size` and `solid_count`, from
    `check_geometry`.
  - `Acceptance` = `{rows, passed, failed, unverified, not_measurable, verdict}`
    where `verdict` is `failed` if any row failed, `verified` if every
    measurable row passed, otherwise `partial`.

**MCP bridge (`backend/agent/cad_mcp.py`)**

- New tool `declare_requirements` with the schema above
  (`additionalProperties: false`, bounded lengths). It writes
  `requirements.json` in the workspace and returns the parsed set plus any
  `uncovered_numbers` as a warning. It may be called again to revise; cap at 4
  calls.
- `build_model` refuses with "Call declare_requirements first." until the file
  exists.
- After each build, `build_model` adds an `acceptance` object to the JSON it
  returns, and lists self-checks under `rejected_checks` with the message
  "This check compares an input with itself. Measure the built geometry."
- A solid count that differs from the declared `solid_count` makes the build
  result an error, like a failed check.
- Allow the new tool in `agent_command` in `backend/agent/local.py`: add
  `mcp__nfinit__declare_requirements` to `--allowedTools` for Claude Code and
  an `approval_mode="approve"` line for Codex.

**Runner (`backend/agent/local.py`)**

- After the final rebuild, load `requirements.json`, run
  `acceptance.evaluate` on the final inspection and store it as
  `inspection["acceptance"]`. The backend's own rebuild decides the verdict,
  not the agent's last tool result.
- The trace detail becomes, for example, "Final geometry checked. 6 of 7
  requirements measured and passed, 1 unverified."
- A run whose final part is valid but `partial` still succeeds and is saved.
  A run with a `failed` verdict is handled as failed checks are today. Fix the
  error wording in `_execute_run` in `backend/projects/runs.py` for local
  agents: it currently says "after 3 repairs", which is the hosted limit.

**Prompt:** `local_agent_prompt` procedure becomes: read the design → call
`declare_requirements` (one row per stated number, each stated assumption
marked `assumed`, the overall size first, following the dimension rules) →
build, with one `check_measurement` per measurable requirement, named with the
requirement id → review → repair → summary.

**Models:** add `acceptance: dict | None = None` to `ModelInspection`, and the
matching optional type in `frontend/src/lib/types.ts`. Do not change the
`verification` literal; old data uses it.

**Tests** (`backend/tests/test_acceptance.py`, `test_local_agents.py`)

- `self_checks` flags `check_measurement("w", width, 80)` and
  `check_measurement("w", width * 1, 80)`, and does not flag
  `check_measurement("w", result.bounding_box().size.X, 80)`.
- `uncovered_numbers("a 60 by 40 by 5 mm plate with four 4 mm holes", ...)`.
- `evaluate` for each status and each verdict.
- Bridge: `build_model` before `declare_requirements` is refused; a wrong
  solid count is an error; acceptance appears in the result. Drive `CadTools`
  directly with a temporary workspace, as the existing tests drive
  `prepare_input`.
- `agent_command` allows the new tool for both CLIs.

**Acceptance:** tests pass; `loop20` live shows the `stacked_reading` and
`detached` categories at or above the previous run.

### Work package 4: `inspect_model` tool

**Fixes:** G2.

**Sandbox:** add operation `"query"` to `SandboxOperation` in `runner.py` and
to `handle_request` in `worker.py`. The request carries `code` and a `query`
object. Add `query_code(code, query) -> dict` in `runner.py`, exported from
`execution/__init__.py`. It executes the code, then answers from
`_entity_records` and `_feature_tree`, so face and edge ids are the same ids
the studio uses (`FaceSelection.entityId`).

**Queries**

| `query.kind` | Input | Output |
| --- | --- | --- |
| `summary` | none | The inspection with census and per-feature face counts. |
| `faces` | optional `surface_type`, `feature_id`, `normal` (unit vector, 5° tolerance), `min_area_mm2`, `limit` (max 50) | Faces: id, surface type, area, centre, normal, bounds, radius where defined, owning feature id. Sorted by area, largest first. |
| `face` | `face_id` | The same facts plus its edges: id, curve type, length, radius where defined, end points. |
| `edges` | optional `curve_type`, `feature_id`, `limit` | Edges with the same facts. |
| `distance` | `a`, `b`: each a face id, edge id, feature id or `[x, y, z]` point | Minimum distance and the two witness points. A feature id means the compound of its owned faces. |
| `section` | `axis` (`x`, `y` or `z`), `at` (mm) | Area of the cross-section, its 2D bounds, and the number of closed loops. |

Unknown ids return an error that lists up to five near matches by surface type.
Cap any response at 20 KB.

**Bridge:** new tool `inspect_model` with `{"query": {...}}`. It runs against
the code of the last successful build in the workspace. It does not use the
build budget. Limit of 20 calls per run. Allow it in `agent_command`.

**Prompt:** add to the procedure: "To learn about a face, an edge or a
distance, call inspect_model. Do not rebuild to measure." When the request
has a selected face, tell the agent to call `inspect_model` with
`{"kind": "face", "face_id": <entityId>}` first.

**Tests:** each query kind on a plate-with-holes part; id stability between
`analyze_code` and `query_code`; limits and size caps; unknown id error.

**Acceptance:** tests pass. In a manual local run with a selected face, the
agent's tool trace shows an `inspect_model` call.

### Work package 5: renderer, `view_model` tool, one sandbox run per build

**Fixes:** G1 and the first half of G8.

**Renderer: new module `backend/execution/render.py`, imported by the worker**

It takes a build123d shape and a list of view requests and writes PNG files
into the sandbox work directory. No new dependencies: tessellation and
hidden-line removal come from the kernel, drawing uses Pillow.

1. Tessellate per face (`face.tessellate(tolerance, 0.3)`) so each triangle
   knows its face id. Tolerance: 0.25% of the bounding-box diagonal, with a
   floor of 0.02 mm. If the result has more than 60,000 triangles, double the
   tolerance and try again.
2. Camera, orthographic. `look_at` is the bounding-box centre, or the centre
   of the focused face or feature. `origin = look_at + D·(cos el·cos az,
   cos el·sin az, sin el)` with `D` = 4 × diagonal. `up` is +Z, or +Y when
   looking straight down or up. Then use the frame from section 4.3.
   Presets: `iso` (az −45, el 35.264), `iso_back` (az 135, el −35.264),
   `front` (az −90, el 0), `back` (90, 0), `right` (0, 0), `left` (180, 0),
   `top` (el 90), `bottom` (el −90).
3. Fill: cull back faces, sort the rest far to near, draw each triangle with
   Lambert shading from a light fixed to the camera (up and to the left).
   Base colour neutral grey; highlighted faces in an accent colour.
4. Edges: `shape.project_to_viewport(origin, viewport_up=up, look_at=look_at)`.
   Sample each returned edge into a polyline and draw visible edges as dark
   1.5 px lines. This gives exact silhouettes and feature edges.
5. Modes: `shaded` (fill plus visible edges), `hidden_line` (white fill,
   visible edges solid, hidden edges light and dashed), `xray` (fill at 35%
   opacity, both edge sets).
6. Section: `{"axis": "x"|"y"|"z", "at": mm, "keep": "below"|"above"}`. Cut
   the shape with a half-space box before tessellating, and colour faces lying
   on the cut plane with a hatch colour.
7. Overlays on every image: the view name, the mode, a scale bar with a round
   length in mm, and a small XYZ triad. Add the line "Reference view. Measure
   geometry for dimensions."
8. Sizes: 800×600 by default, 1200×900 on request.

If a view fails, the others are still returned and the failure is named.

**Sandbox:** add operation `"review"`: execute once, then return the
inspection (with census) and render the default views. `review_code(code,
views=None)` in `runner.py` returns the inspection and the PNG bytes. Add
operation `"render"` for extra views: `render_code(code, views)`.

**Bridge**

- `build_model` calls `review_code` once instead of `inspect_code` plus
  `model_views`. Default views: `iso` and `iso_back`, both `shaded`. Together
  they show all six sides.
- New tool `view_model`:

  ```json
  {"views": [{"camera": "top" | {"azimuth": 30, "elevation": 20},
              "mode": "shaded" | "hidden_line" | "xray",
              "section": {"axis": "z", "at": 3.0, "keep": "below"},
              "focus": "<face id or feature id>",
              "highlight": ["<face id>", "..."],
              "size": "normal" | "large"}]}
  ```

  At most 4 views per call and 12 images per run. Allow it in `agent_command`.
- Keep `model_views` and `render_views` in `references.py`: the STL reference
  import still uses `render_views` for meshes.

**Prompt:** add: "The two default views show every side. Ask view_model for
another view only to answer a specific question: a top view for a hole
pattern, a section for a bore, pocket or wall, a focused view of the changed
feature."

**Tests**

- Renderer unit tests run in the worker environment: a box gives a non-blank
  image of the right size; a plate with a hole seen from the top has dark
  pixels on the hole's circle (project the known centre and radius and sample
  there); a section at mid-height of a tube shows the hatch colour.
- `review_code` returns an inspection and two images from one sandbox job
  (assert `_run_worker` is called once, with a monkeypatch).
- Sandbox isolation tests still pass, including
  `backend/tests/test_sandbox_root.py` in CI. Pillow now runs inside the
  sandboxed worker and writes PNGs to the work directory. If the Linux
  seccomp filter blocks it, fall back to returning projected triangles and
  polylines as JSON and drawing them in the bridge process; keep geometry in
  the worker either way.
- On Linux the fork server refuses to start if warm-up leaves more than one
  thread (`serve` in `worker.py`). Do not import the renderer or Pillow in
  `_warm_up` unless the thread count stays at 1; import them inside the job.

**Acceptance:** tests pass. Attach four sample images to the pull request
(shaded iso, hidden-line top, x-ray, section). `loop20` live is not worse.

### Work package 6: printability checks

**Fixes:** G7.

**New module `backend/execution/printability.py`, run in the worker**

Input: the shape, and a profile. Output: facts with locations and face ids.
Use the per-face tessellation from work package 5 as numpy arrays.

| Fact | How |
| --- | --- |
| `bed_fit` | Bounding box against the profile's bed size, also trying a 90° turn about Z. |
| `overhangs` | For each triangle with a downward normal, angle from horizontal = `acos(−n_z)` in degrees (0° for a flat ceiling, 90° for a vertical wall). A triangle needs support when that angle is below the profile's limit and it does not rest on the bed (its lowest point is more than 0.05 mm above the part's lowest Z). Report total area, share of surface, and the 10 largest regions grouped by face id with centroid and area. |
| `wall_thickness` | Sample 2,000 surface points, area-weighted, with a fixed seed. From each, cast a ray inward along the negative normal and take the first triangle hit whose normal is at least 120° from the start normal. Report min, 5th percentile, median, and the 10 thinnest samples with location and face id. Use a vectorised Möller–Trumbore test in numpy, in chunks of 200 rays. |
| `support_volume` | Sum over overhanging triangles of projected area × height above the bed. An upper bound; label it as one. |
| `orientations` | Repeat overhang area and build height for the six axis-aligned orientations. |
| `small_holes` | Holes from the census with a diameter under the profile's minimum. |
| `sealed_voids` | Solids with inner shells. |

Not measured, and always reported as `unverified`: bridges, minimum positive
feature size, warping, strength.

**Profile**

```python
DEFAULT_PROFILE = {
    "process": "fdm", "bed_mm": [220, 220, 250], "nozzle_mm": 0.4,
    "min_wall_mm": 1.2, "overhang_limit_deg": 45,
    "min_hole_mm": 2.0, "max_support_ratio": 0.30,
}
```

These limits follow the conservative FDM defaults in text-to-cad's printing
reference, which cites public design guides. They are defaults, not physics.
Say so wherever they are shown. Add an optional `print_profile` field (alias
`printProfile`) to `CadRunRequest` in `backend/agent/models.py`, validated and
bounded, that overrides the defaults.

**Findings:** a separate function compares facts with the profile and returns
rows `{rule, measured, limit, status, where, face_ids, suggestion}` with
status `pass`, `fail`, `review` or `unverified`. A thin 5th percentile is a
`fail`; a thin minimum alone is a `review` that names the location.

**Wiring**

- Sandbox operation `"printability"` and `printability_code(code, profile)`.
- Bridge tool `check_printability` (no input beyond an optional orientation),
  limit 3 calls per run.
- The backend runs it once on the final code in `run_local_agent` and stores
  the result as `inspection["printability"]`. A printability `fail` does not
  fail the run.
- Prompt: "Parts are 3D printed unless the user says otherwise. Before the
  final summary, call check_printability once. Fix a failure when the fix does
  not change a stated requirement; otherwise report it with the suggested
  change."

**Tests:** a 0.6 mm wall is found and located; a 10 mm cube has no overhang
findings; a T-shape has an overhang and a better orientation; a 300 mm part
fails `bed_fit`; a part with a 1 mm hole lists it; results are identical on
two runs (fixed seed).

**Acceptance:** tests pass. Timing for a 20,000-triangle part is under 10 s on
CI; if not, lower the sample count and say so.

### Work package 7: edit safety

**Goal:** when the user edits an existing part, catch changes they did not
ask for.

**Changes**

- `prepare_input` (`backend/agent/local.py`): when `request.code` is not
  empty, run `analyze_code` and `inspect_code` on it once and save
  `previous.json` (topology and inspection) in the workspace.
- New function `change_report(previous, current) -> dict` in
  `backend/agent/acceptance.py`, built on `compare_analyses` from
  `backend/execution/rematching.py`:

  ```json
  {"bounds_delta_mm": {"x": 0, "y": 0, "z": 3},
   "volume_delta_mm3": 7200.0,
   "features": {"added": [], "removed": ["edge_fillet"], "modified": ["base_plate"]},
   "constraints_violated": ["hole_spacing"],
   "census_delta": {"holes": "2 → 2", "rounded_edges": "4 → 0"},
   "flags": ["Feature 'edge_fillet' was removed.", "Rounded edges went from 4 to 0."]}
  ```

  A flag is raised for: a removed feature, a violated constraint, and any
  census count that went down.
- `build_model` returns `changes` on every build of an edit. The prompt says:
  "For an edit, every flag must be either something the user asked for or
  fixed. List the rest under 'Other changes' in the summary."
- `acceptance.evaluate` adds a row `no_unrequested_changes`: `passed` when
  there are no flags, otherwise `review` (extend the status set) with the
  flags as detail. It cannot be `failed` automatically, because the bridge
  does not know what the user intended.
- The backend stores the final report as `inspection["changes"]`.

**Tests:** the `edit_regression` negative replay from work package 0 produces
the fillet flag; a pure thickness change produces no flags; the previous
analysis runs once per run, not once per build.

**Acceptance:** tests pass; the `edit_regression` category in `loop20` live is
at or above the previous run.

### Work package 8: evidence panel in the studio

**Goal:** the user sees what was proven, not a claim.

**Changes**

- `frontend/src/lib/types.ts`: optional `acceptance`, `warnings`, `census`,
  `printability` and `changes` on `ModelInspection`.
- New component `frontend/src/components/VerificationPanel.tsx`. It replaces
  the line in `Studio.tsx` that reads "N/M geometry measurements passed"
  (search for `geometry measurements passed`). Sections, each hidden when
  empty:
  1. Verdict: Verified, Partly verified, or Failed, with counts.
  2. Requirements table: text, expected, measured, status. Assumed rows are
     marked "assumed".
  3. Warnings.
  4. Printability: findings with status, and a "Show on part" control.
  5. Changes since the previous revision, with flags.
- "Show on part": pass the finding's `face_ids` to `ViewportPane.tsx`. Meshes
  already carry `userData.faceId`, and the pane already highlights a set of
  face ids for a hovered feature (`featureFaceIds`). Reuse that mechanism with
  a warning colour.
- Use the existing design tokens and `ui/` components. Match the studio's
  current look in light and dark themes.
- `frontend/src/components/DesignInspector.tsx` is not imported anywhere. Do
  not build on it.
- Demos (`frontend/src/lib/demos.ts`) must still type-check and render; the
  panel must handle an inspection with none of the new fields.

**Tests:** extend `frontend/tests/studio_controls.py` with a fixture
inspection that has every section and assert each renders; `tsc`, lint and
build pass.

**Acceptance:** screenshots of the panel in light and dark themes in the pull
request.

### Work package 9: speed and budgets

**Fixes:** the rest of G8.

1. **Separate deadline for local agents.** Add
   `CAD_LOCAL_RUN_TIMEOUT_SECONDS` (default 900). Make
   `run_timeout_seconds(model_id: str | None = None)` return it for local
   models. Update every caller: `backend/agent/local.py`,
   `backend/projects/runs.py` (two places) and `backend/projects/limits.py`.
   The stale-run check must use the longer value. Update the wait in
   `frontend/src/lib/runs.ts` (its comment says "The backend gives a run
   300s") and `backend/.env.example`.
2. **One budget table** in `cad_mcp.py`, returned to the agent in every tool
   result as `budget_left`: builds 8, requirement declarations 4, inspections
   20, images 12, printability checks 3.
3. **Build once, query many.** After a successful `review`, the worker also
   writes `model.brep` and `topology.json` to the work directory, and the
   bridge keeps them in the agent workspace. The `query`, `render` and
   `printability` operations accept that pair instead of code, and the worker
   loads the B-rep with the kernel's reader instead of executing code again.
   The bridge copies the two files into each new sandbox work directory; the
   worker never reads a path chosen by the agent. Measure before and after and
   keep this only if it saves at least 30% on a typical part.
4. Report timings (`build_ms`, `render_ms`, `query_ms`) in tool results and in
   the run trace.

**Tests:** timeout selection by model id; budgets exhausted return a clear
error and do not kill the run; a B-rep-backed query returns the same answer as
a code-backed one.

### Work package 10: slicing and print profiles

**Needs the owner's decision before starting**, because it runs an external
program and the choice of supported printers is a product decision.

Outline: detect an installed OrcaSlicer; let the user pick a printer, process
and filament preset from their own presets; slice the exported STL or 3MF on
the user's machine; show print time and filament use in the evidence panel.
Never contact a printer and never start a print. Add optional hole and fit
compensation to the profile from work package 6. text-to-cad's `print3d`
skill is the reference for the slicer's command line.

Questions for the owner: which printers to offer first; whether slicing runs
automatically or on a button; whether to add 3MF export.

### Work package 11: richer pointing in the studio

**Needs the owner's decision before starting.**

Outline: a measure tool in the viewport (two picks give a distance, backed by
the `distance` query from work package 4); multi-face selection; drawing on
the current view, with each stroke resolved to the faces under it and sent to
the agent as selections plus the view's camera, so the agent can ask
`view_model` for the same view.

## 7. Where to read text-to-cad

Clone `https://github.com/earthtojake/text-to-cad`. This plan was written
against commit `ed3713e` (2026-11-10).

| Topic | File in their repository |
| --- | --- |
| The loop and the check rules | `skills/cad/SKILL.md` |
| Inspecting and measuring | `skills/cad/references/inspection-and-validation.md` |
| Views, sections, display modes | `skills/cad/references/snapshot-review.md` |
| build123d pitfalls | `skills/cad/references/build123d-modeling.md` |
| Printing limits and how to read them | `skills/cad/references/manufacturing-printing.md` |
| Printing measurements (uses trimesh) | `packages/cad/src/cad/trimesh/_printing.py` |
| Distance, overlap, diagnostics | `packages/cad/src/cad/build123d/_geometry.py` |
| Slicing | `skills/print3d/SKILL.md` |

Their model is different in ways that do not carry over: models are Python
functions with a `@model` decorator, a long-lived server replays builds, and
the agent runs shell commands. Nfinit's agents have no shell and one script
per part. Take the checks, not the architecture.

## 8. Risks and how to handle them

| Risk | Handling |
| --- | --- |
| A stricter validity rule fails a recorded CAD50 part or a demo. | Stop, report the case in the pull request, and let the owner decide. Do not loosen the rule quietly. |
| More tools mean longer runs and more usage on the user's account. | Budgets in work package 9. Report tool-call counts and run time for `loop20` in every pull request from work package 3 on. |
| More images cost tokens. | Two default views, not three. Extra views only on request, capped at 12. |
| The census misreads a shape (a slot end read as a rounded edge, a split cylinder). | It reports raw faces grouped by rule. Benchmarks cover the common cases. Requirements use it only when a matching entry exists; otherwise the row is `unverified`. |
| The agent games acceptance by declaring few requirements. | `uncovered_numbers` warns about every stated number that no requirement covers, and the panel shows the user the full table. |
| A prompt pitfall is wrong for the locked library version. | The rule in work package 1: no pitfall without a test. |
| Pillow or numpy code is blocked by the Linux sandbox filter. | The fallback in work package 5: geometry in the worker, drawing in the bridge. CI runs the root sandbox tests on Linux. |
| Live benchmark numbers are noisy. | Run each `loop20` live comparison three times and report the mean and the range. Treat a difference inside the range as no change. |

## 9. Reporting back

For each work package, the pull request description must contain:

1. What changed, in two or three sentences.
2. The exact test commands run and their results.
3. CAD50 and `loop20` replay results.
4. From work package 1 on: `loop20` live pass rate per category, next to the
   baseline and the previous work package, or a statement that it was not run
   and why.
5. Anything in this plan that turned out to be wrong, and what was done
   instead.

## 10. Progress and changes to this plan

| # | Pull request | Notes |
| --- | --- | --- |
| 0 | Benchmark that can see the problems | The feature census moved here from work package 2: the benchmark cannot score features without it, so the negative replays pass now instead of being marked `xfail`. The census is left out of `build_model`'s output until a prompt explains it, so the baseline measures the old loop. `max_solids_inverted` moves to work package 2, which adds per-solid volumes. |
| 1 | Prompt: one template, pitfalls, review rules | Two draft pitfalls did not reproduce and were dropped (stale edge selections, coincident faces); one became "parts that touch only along an edge stay separate solids". The `Hole` pitfall was corrected: a hole cuts its depth below its location and the same distance above it. The runner now passes on Claude Code's own error text when a run stops. Results are in `docs/evaluations/loop20-results.md`. |
| 2 | Strict validity and feature census | The census itself shipped in work package 0. build123d's `is_manifold` rejects plain spheres, cones and filleted boxes (three CAD50 parts failed with it), so closedness uses the kernel's free-boundary analysis instead; a stricter edge count also failed the mini-glider demo on a 0.4 mm edge that the kernel joins within tolerance. All demo steps and CAD50 parts pass. The census and warnings are now shown to the agent. Live results for work packages 2 to 7 were measured together on the combined branch; see `docs/evaluations/loop20-results.md`. |
| 3 | Requirements contract and enforced acceptance | A failed verdict does not fail the run or discard the part, matching how the hosted path treats a size mismatch after its repairs; the verdict is stored and shown. Census entries do not settle requirements: a requirement says nothing about whether a count is of holes or bosses, so only a named check does. |
| 4 | `inspect_model` tool | The starting design is available to `inspect_model` before the first build, so the agent can look up a selected face before changing anything (the plan said after the first build, which would have answered about the wrong part). |
| 5 | Renderer, `view_model`, one sandbox run per build | The renderer and printability modules sit next to the worker and are loaded by file path, because the worker runs as a script; reads are not restricted by the Linux sandbox, so this works there. Highlighting is skipped inside section views (the cut changes the faces). |
| 6 | Printability checks | `check_printability` takes no orientation input: every report already ranks the six orientations. The kernel keeps a face's first, finer mesh, so coarsening clears it before retrying; rays are only tested against triangles facing roughly against them. A 14,000-triangle plate with 196 holes takes about 5 s on an Apple silicon Mac. |
| 7 | Edit safety | The starting design is measured by the bridge on the first build, in the same review run that draws views (`review_code(..., topology=True)`), not in `prepare_input`. A live loop20 run of work packages 2 to 7 together passed 20 of 20 but used about 87,000 tokens per case, twice work package 1, because tool results grew; work package 9 shortens them before the full measurement. |
| 9 | Speed and budgets | Done before work package 8, because tool-result size drove the token cost. Rebuilding the part is about 1% of a sandbox query on macOS (process start-up is the rest), so the B-rep cache in item 3 was not built: it could not save the 30% the plan required. Tool results were shortened (`agent/feedback.py`), which the plan did not list. |
| 8 | Evidence panel in the studio | The studio's `inspection` comes from the saved mesh, which has no acceptance or printability, so the panel reads the inspection of the assistant message whose code is on screen. It shows in the card over the viewport, where it is visible without opening the chat history, and under each agent reply. |
