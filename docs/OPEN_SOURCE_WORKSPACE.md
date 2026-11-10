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

The agent reads the current design, plans the change, then calls `build_model`.
The CAD tool executes code in Nfinit's sandbox and returns:

- kernel validity, solid count, volume and bounds;
- explicitly authored measurements and any failures;
- top, front and isometric images;
- envelope and volume comparison against an imported STL, where available.

The agent can repair and rebuild up to eight times within the run deadline.
The backend independently rebuilds the final source before accepting it. A
model without authored measurement checks is marked `unverified`; passing those
checks establishes only the quantities checked. They are agent-authored tests,
not an independent mechanical certification. Render failures remain explicit.
Preview rendering samples meshes over 15,000 triangles and is not metrology.

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
