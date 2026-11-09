# Security policy

## Reporting a vulnerability

Please report security issues privately. Do not open a public issue.

Email **muayyad.shahid1@gmail.com** with:

- what the issue is and what an attacker could do with it
- steps or a proof of concept to reproduce it
- the commit or version you tested

You'll get a reply within a few days. Once the issue is fixed, we'll credit you
in the release notes unless you'd rather stay anonymous.

## Supported versions

Only the latest `main` branch receives security fixes.

## Scope

Issues we especially want to hear about:

- generated CAD code escaping the execution sandbox
- the local backend or agent tools being reachable from outside your machine
- one project reading or changing another's files or data
- unsafe handling of imported STL files or reference images

Problems in Claude Code, Codex, build123d or OpenCASCADE themselves should go
to those projects.
