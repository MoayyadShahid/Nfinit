# Contributing to Nfinit

Nfinit is an MIT-licensed visual CAD workspace. Contributions should make it
easier to create, inspect, edit and export a correct design with an installed agent.

Use Python 3.11 or 3.12, Poetry, and Node.js 20.9 or later. Install with `npm ci`
at the root and `poetry install` in `backend/`. Run `npm run local`; sign in to
Claude Code or Codex through that tool's own terminal login before using it.
The current CAD sandbox supports macOS and Linux. Windows requires WSL2.

Before submitting changes:

```sh
cd backend
poetry run python -m pytest -q
cd ../frontend
npx tsc --noEmit
npm run lint
```

Test CAD behavior with measured geometry. Include a reproducing model for
geometry bugs, and a regression check for the specific requirement that failed.
Do not treat a valid solid, rendered image, or matching volume as proof of a
correct design. Keep held-out evaluation solutions out of retrieval corpora.

Keep generated code inside the execution sandbox. Never make the backend or a
developer's local agent account reachable from another machine, bypass CLI
permissions, or collect
provider credentials in the Nfinit frontend. Do not include keys, private model
files, local databases or conversation traces in a PR.

Open issues for workflow gaps and narrowly scoped PRs for changes. The public
website is a read-only demo build (see `docs/DEMOS.md`); keep it free of API
calls. See `docs/OPEN_SOURCE_WORKSPACE.md` for the architecture and limits.

By contributing, you agree your contribution is licensed under the MIT license.
Third-party components retain their own licenses and attribution.
