# Open-source local CAD workspace

Nfinit is free to run locally under MIT. The user supplies an installed,
authenticated Claude Code or Codex CLI. Model usage consumes that account's
allowance or its configured API credits. CAD computation and project storage run
on the user's machine; prompts and reference images still reach the model provider.

## Start

1. Install Node.js 20.9+, Python 3.11/3.12 and Poetry. macOS/Linux are supported;
   use WSL2 on Windows.
2. Run `npm ci` at the repository root and `poetry install` inside `backend/`.
3. Install Claude Code or Codex using its official instructions, and sign in in
   the terminal. Update older CLIs if they reject the integration flags.
4. Run `npm run local` at the root. Open `http://127.0.0.1:3000/studio`.

`NFNIT_PYTHON=/path/to/python npm run local` selects an existing backend Python
environment. No cloud accounts or API keys are required. Local pattern search
and run diagnostics also require no cloud service accounts. The
launcher binds both services to loopback and uses SQLite. Existing local
projects remain available. Ports 3000 and 8000 must be free.

## Agent connection and loop

The local launcher creates a random token shared only by the Next.js proxy and
backend. A local-agent run requires that token, a loopback peer and explicit
local mode. The API refuses to serve at all unless the launcher started it.
Provider credentials remain with the official CLI.

Each run launches the unmodified CLI in a fresh temporary workspace. Claude
Code uses structured streaming input/output and only the Nfinit MCP tools.
Codex uses `exec --json`, a read-only sandbox and the Nfinit MCP server. This
initial adapter is a bounded job, not a remote-control connection to an already
open app window. Durable Nfinit conversation history is supplied on each run;
native CLI sessions are not resumed across runs. Superseded assistant code is
omitted from native-agent context; the current model is available through the
CAD tool, alongside user requests and reference images.

The agent's prompt (`local_agent_prompt` in `backend/agent/prompts.py`) gives
it a numbered procedure, the rules for reading stacked dimensions ("a 3 mm base
with 12 mm walls" is 15 mm tall), build123d pitfalls that build without an
error, and rules for reviewing a build: never read a dimension off an image,
turn visual doubts into measurements, and never drop a requested feature to make
a build pass. Each pitfall is reproduced by a test in
`backend/tests/test_prompt_pitfalls.py`.

The agent reads the current design and plans the change. Before its first
build it must call `declare_requirements` with the overall size, the expected
number of solids, one requirement per requested number, count or feature, and
its assumptions; `build_model` refuses to run until it has. Numbers in the
request that no requirement covers come back as a warning.

The agent then calls `build_model`. The CAD tool executes code in Nfinit's
sandbox and returns:

- kernel validity, solid count, volume and bounds;
- each solid's volume and bounds. An inside-out solid (negative volume) or an
  open one makes the build invalid. Closedness uses the kernel's free-boundary
  analysis, because build123d's `is_manifold` rejects plain spheres, cones and
  filleted boxes;
- a census of holes, bosses and rounded edges counted from the faces, and how
  many faces each registered feature owns;
- warnings for parts that built but are probably wrong: extra solids (a
  feature that does not touch the part) and registered features that own no
  faces of the final part;
- explicitly authored measurements and any failures;
- two shaded views from opposite corners, which together show every side,
  drawn in the same sandbox run as the inspection;
- envelope and volume comparison against an imported STL, where available;
- an acceptance table: each declared requirement as passed, failed,
  unverified or judged from images. A requirement passes only through a
  `check_measurement` named with its id that measures built geometry; a check
  that compares an input with itself is rejected. A wrong overall size or
  solid count makes the build an error.

Between builds the agent can call `inspect_model` to ask about the current
part without rebuilding it or using a build: its faces (filtered by surface,
feature, direction or area), one face and its edges, its edges, the distance
between two faces, edges, features or points, and the area and loops of a
plane section. Face ids are the ones the studio's selection uses, so for an
edit with a selected face the agent first looks up exactly what was picked.
It has 20 questions per run.

`view_model` draws up to four more views per call, 12 per run: any preset
(iso, front, top, ...) or azimuth and elevation, in shaded, hidden-line or
x-ray mode, with an optional section cut (cut faces drawn red), a face or
feature to focus on, and faces or features to highlight. The renderer in
`backend/execution/render.py` runs inside the sandbox: it shades the part's
own tessellation and draws exact edges from the kernel's hidden-line removal,
with a scale bar and an axis triad. Images show arrangement only; dimensions
come from measurements.

For an edit, the bridge measures the starting design once and compares every
build with it: bounds and volume deltas, features added, removed and
modified, constraints no longer met, and changes in the counts of holes,
bosses and rounded edges. A removed feature, a broken constraint or a lost
hole, boss or rounded edge is flagged, and the acceptance table gains a row
that needs review until the agent fixes it or confirms the user asked for it.

Parts are assumed to be 3D printed. Before its summary the agent calls
`check_printability` (three times per run at most), and the backend checks the
saved part once more. The check measures, inside the sandbox:

- bed fit, including a 90 degree turn;
- wall thickness, from 2,000 inward rays at fixed sample points;
- overhangs steeper than the profile's limit, excluding faces on the bed, with
  the largest areas located;
- an upper bound on support volume;
- the six axis-aligned orientations ranked by overhang area;
- holes below the minimum size, and sealed cavities.

Findings compare these with a print profile: conservative FDM defaults (220 ×
220 × 250 mm bed, 1.2 mm walls, 45 degree overhangs, 2 mm holes) that a request
can override with `printProfile`. The defaults come from public design guides
and are starting points, not physics. Bridges, minimum feature size, warping
and strength are reported as not measured.

The agent can repair and rebuild up to eight times within the run deadline.
The backend independently rebuilds the final source before accepting it, and
computes the final acceptance verdict itself: `verified` when every measurable
requirement passed, `partial` when some are unverified, `failed` when any
failed. A
model without authored measurement checks is marked `unverified`; passing those
checks establishes only the quantities checked. They are agent-authored tests,
not an independent mechanical certification. Render failures remain explicit:
a view that cannot be drawn is reported by name. Views are not metrology.

`check_measurement(name, actual, expected, tolerance=0.01)` must measure built
geometry, never repeat the requested parameter. Failed checks make inspection
fail and enter repair. The optional API loop also preserves images through later
turns and repairs and prompts for these checks.

The runtime controls subprocess lifetime and kills its process group at the
deadline. An unavailable agent, invalid login, or exhausted usage allowance is
reported; Nfinit never silently switches to paid API inference.

## Reference pictures

Attach, drop or paste PNG/JPEG/WebP/GIF images into chat. Up to eight images,
10 MB total across a run's conversation, are accepted. Images persist with the
project and remain visible to subsequent agent turns. Include a known dimension
or a dimensioned drawing: an unscaled image cannot establish exact measurements.

## STL imports

Open **References & copies**, choose source units, and import an STL. Every
import creates a separate working project and stores the original bytes in its
revision state. **Download original STL** returns those original bytes, while
normal export returns the current edited design. **Save as a new copy** branches
the project; normal runs append immutable revisions.

- **Preserve mesh:** up to 2,000 triangles in a closed, consistently oriented
  mesh. Reconstructs a faceted B-rep solid. Boolean additions/cuts can build on it,
  and the modified part exports as STEP/STL. This preserves the mesh surface;
  it does not recover analytic curves or the original feature history. Complex
  meshes can exceed the kernel timeout or code size limit and are refused.
- **Reconstruct from reference:** up to 100,000 triangles and 10 MB. Stores
  measured bounds and three reference views. Click **Reconstruct editable copy**
  to ask the selected agent for a new parametric model. This is approximate
  reverse engineering, not a guaranteed conversion. The model may miss hidden
  or ambiguous features; inspect it before use. Local tools compare bounds and
  volume but do not claim surface equivalence.

STL has no standard embedded units, so choose mm or inches explicitly. Invalid,
nonfinite, oversized or degenerate input is rejected. Open meshes are available
as reconstruction references only. Geometry data is bounded numeric data, never
Python, pickle, or an arbitrary filesystem path.

## Review sequence

The implementation is arranged for three review areas (with shared integration
touchpoints in the studio and run API):

1. MIT licensing, local launcher, contributor setup and local-agent access.
2. Native CLI adapters, restricted CAD MCP tools, measured checks and previews.
3. Reference pictures, STL import/reconstruction, original preservation and copies.

Future work includes persistent app-server sessions with approvals in the UI,
independent feature-specific acceptance tests, surface-deviation comparison,
assembly workflows and a signed desktop installer. These are not implied by the
initial local workspace release.

## Upstream inspiration and licensing

The measure/render/repair workflow is informed by earthtojake/text-to-cad's CAD
skill and inspection guidance. This implementation does not vendor its code or
modify its install scripts. See https://github.com/earthtojake/text-to-cad.
Nfinit's own code is MIT; build123d, OpenCASCADE and other dependencies retain
their licenses. The bundled build123d retrieval corpus keeps its Apache-2.0
license and NOTICE under `backend/agent/retrieval/corpus/`.

Provider integrations use their own published interfaces and terms:
- https://code.claude.com/docs/en/headless
- https://code.claude.com/docs/en/legal-and-compliance
- https://developers.openai.com/codex/noninteractive
- https://learn.chatgpt.com/docs/app-server
