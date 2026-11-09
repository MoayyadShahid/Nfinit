# Changelog

All notable changes to Nfinit are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Local workspace: `npm run local` starts the backend and the studio on your computer, with your own Claude Code or Codex CLI as the agent.
- Demo website: the public site shows the landing page and read-only studio demos, with no backend.
- Demo build gate: each demo step must build, and its main part must be one solid.
- Issue templates, a code of conduct, and this changelog.

### Changed
- License is MIT.
- API models through OpenRouter are optional. Local agents need no key.

### Removed
- The hosted service: sign-in, accounts, Supabase, Postgres, Railway and Docker deployment, billing, telemetry, and the Terms and Privacy pages.
