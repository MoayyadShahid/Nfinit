# Simple Lovable-for-CAD MVP

## Product promise

A user describes one manufacturable part, receives an editable 3D model, refines
it through chat or code, selects a face for a targeted edit, saves immutable
revisions, and downloads STL or STEP.

This is the complete starting product. It is not an assembly, procurement, or
factory-ordering platform.

## Required user journey

1. Open the IDE and describe a single part with useful dimensions.
2. See valid geometry in the viewport without handling Python setup.
3. Refine the part through another prompt.
4. Select a visible face and target the next prompt to that face.
5. Reopen a saved part and load any immutable revision.
6. Edit generated code when needed and save it as another revision.
7. Download STL for printing or STEP for continued CAD work.
8. Receive a clear, recoverable error when generation or geometry fails.

## MVP requirements

### Generate and preview

- The LangGraph CAD agent plans, retrieves patterns, generates build123d code,
  validates it in the sandbox, and repairs failures.
- Successful code is rendered as a GLB preview.
- Chat shows concise progress instead of exposing raw model output.

### Iterate and select

- Every prompt includes the current code and conversation.
- A viewport click resolves to a semantic B-rep face when possible.
- The next prompt includes that selected face.
- Parameterized code, authored feature IDs, and declared constraints are
  preserved across edits.

### Save and restore

- The first successful generation creates a named project automatically.
- Each successful generation appends one immutable revision.
- Manual code, model, or selection changes show an unsaved indicator.
- Users can explicitly save those changes and load previous revisions.
- Loading or replacing dirty work requires confirmation.

### Export

- STL and STEP downloads are available from the primary toolbar.
- Export runs through the same sandbox policy as preview generation.
- BREP may remain available as an expert option, but is not required for the
  core journey.

### Reliability

- Backend regression tests and CAD50 remain green.
- The frontend production build must pass.
- A manual end-to-end walkthrough must prove generate, refine, save/load,
  select, and export behavior before calling the MVP complete.

## Explicitly deferred

These are not requirements for the starting product:

- multi-part assemblies and joints
- BOM generation and component sourcing
- DFM scoring beyond successful solid generation
- supplier matching, quotes, factory ordering, and logistics
- authentication, teams, real-time collaboration, and billing
- electronics, simulation, generative optimization, and mobile clients

Deferred work should only return after direct user evidence shows it blocks the
single-part prompt-to-export journey.

## Completion criteria

The MVP is complete when a new user can create a useful single part, make one
targeted revision, reopen both versions, and export a usable file without
developer assistance. Internal architecture or feature count is not a
completion criterion.
