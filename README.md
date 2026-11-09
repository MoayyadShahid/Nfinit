# Nfinit

An open-source visual CAD workspace for Claude Code and Codex. Describe a part,
attach reference pictures or an STL, and your agent writes parametric
[build123d](https://github.com/gumyr/build123d) code that Nfinit builds, measures
and shows in a 3D viewer. Refine it in chat or by clicking a face, keep every
revision, and export STEP or STL.

Everything runs on your machine. Model usage goes through your own agent
account and its usage limits; Nfinit needs no API keys or cloud accounts.

<img width="1470" height="761" alt="The Nfinit studio: chat on the left, a 3D part in the viewport" src="https://github.com/user-attachments/assets/88c0ec7a-4c47-4efb-925f-0d5ef71f04ea" />

## Requirements

- macOS or Linux (on Windows, use WSL2)
- Node.js 20.9 or later
- Python 3.11 or 3.12, and [Poetry](https://python-poetry.org/)
- [Claude Code](https://code.claude.com) or [Codex](https://developers.openai.com/codex),
  installed and signed in through its own terminal login
- Ports 3000 and 8000 free

## Quick start

```sh
npm ci
cd backend && poetry install && cd ..
npm run local
```

Open **http://127.0.0.1:3000/studio** and pick your agent.

To use a Python environment you already have (for example a conda env with
OpenCASCADE, if `poetry install` cannot find a VTK wheel for your platform):

```sh
NFNIT_PYTHON=/path/to/python npm run local
```

## Using the studio

- **Describe a part** in the chat, e.g. "a 60 × 40 × 5 mm mounting plate with
  four 4 mm holes 5 mm from each corner". Include real dimensions.
- **Refine it** with follow-up messages, or click a face in the viewport to
  target it ("add a 10 mm boss on this face").
- **Attach pictures** by attaching, dropping or pasting PNG, JPEG, WebP or GIF
  images. Include a known dimension: an unscaled picture can't fix exact sizes.
- **Import an STL** under **References & copies**, either as a faceted solid
  you can add to and cut from, or as a reference for an approximate parametric
  rebuild. The original file stays downloadable.
- **Revisions**: every run saves a new revision; open any earlier one from the
  version rail, or save a branch as a new copy.
- **Export** the current part as STEP or STL.
- **Advanced** opens the generated code in an editor.

Demo parts in the studio and on **Your parts** show how example builds come
together step by step.

## How it works

1. The launcher (`scripts/local.py`) starts the FastAPI backend and the Next.js
   frontend on loopback only, with a random token shared between them.
2. Each run starts your agent CLI in a fresh temporary workspace, connected
   only to Nfinit's CAD tools (MCP).
3. The agent plans the change and calls `build_model`. Nfinit runs the code in
   a sandbox and returns validity, volume, bounds, measurement checks and
   rendered views, and the agent repairs and rebuilds as needed.
4. The backend rebuilds the final code itself before accepting it, then saves
   the revision to a local SQLite database (`backend/data/nfinit.db`).

Generated code never runs in the server process. It runs in an isolated worker
with an AST policy, restricted built-ins, no network, and CPU, memory, time and
file limits.

AI-generated parts can be wrong. Check every dimension, fit and strength
requirement before you make or use a part.

## Configuration

The defaults work without any configuration. Optional settings go in
`backend/.env` (see [`backend/.env.example`](backend/.env.example)):

| Variable | Purpose |
| --- | --- |
| `NFNIT_PYTHON` | Python interpreter the launcher uses for the backend |
| `NFNIT_DATABASE_PATH` | Where the SQLite database lives |
| `CAD_SANDBOX_*` | Sandbox time, memory and concurrency limits |
| `PATTERN_RAG_ENABLED` | Turn the bundled build123d pattern search on or off |

## Project layout

```
backend/    FastAPI API, agent adapters, CAD sandbox, evaluations (Python)
frontend/   Next.js studio and landing page (TypeScript)
scripts/    Local launcher
docs/       Architecture, local workspace, demos and security notes
```

## Development

```sh
cd backend && poetry run python -m pytest -q
cd frontend && npx tsc --noEmit && npm run lint
```

Replay the CAD benchmark (free and deterministic, no model calls) from
`backend/`:

```sh
poetry run python -m evaluation.cli \
  --cases evaluation/cases/cad50.json --mode replay \
  --replays evaluation/replays/cad50.json \
  --output evaluation/reports/cad50.json
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR.

## Documentation

- [Local workspace](docs/OPEN_SOURCE_WORKSPACE.md): agent connection, limits,
  reference pictures and STL import
- [Architecture](docs/ARCHITECTURE.md): sandbox, semantic topology, persistence,
  pattern search and evaluations
- [Demo parts](docs/DEMOS.md): how the example builds are made and rebuilt
- [Security](docs/SECURITY.md)

## License

[MIT](LICENSE). build123d, OpenCASCADE and other dependencies keep their own
licenses; the bundled build123d pattern corpus is Apache-2.0 (see
`backend/agent/retrieval/corpus/`).
