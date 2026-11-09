# Demo parts

Six example builds, served as static files from `frontend/public/demos/`
(27 MB; the studio downloads only the versions a visitor opens):

| Demo | Versions |
| --- | --- |
| 5-inch FPV drone frame | bottom plate → motor mounts → stack, standoff and strap holes → arm weight relief → standoffs and top plate → camera cage |
| Robot gripper | base plate → micro servo → spur gears → cranks and idler links → fingers |
| Miniature glider | fuselage → main wing → horizontal stabilizer → vertical fin → nose pocket and launch hook |
| Model rocket | body tube → nose cone → fin can → launch lug → motor mount and retainer |
| Desk catapult | ladder frame → A-frame uprights → axle and throwing arm → bucket → stop bar → wheels |
| Electronics enclosure | shell → board standoffs → USB-C and button openings → vent slots → lid → screw bosses and lid holes |

**Where they come from.** Each demo is a design file in
`backend/demos/designs/<slug>.cad`: build123d code with comment markers
that split it into steps, each with the request, the reply and the code it
adds (`backend/demos/authored.py` documents the format). The code of a
version is the complete script of steps 1 to N, so every version is a real,
runnable script, and the next version only adds to it. The demos are written
by hand, not recorded agent runs, so `demo.json` says `"source": "example"`
and the studio labels them "Example build". The progress steps in a replay
show the plan and the real build result, without timings.

Each folder has `demo.json` (for every version: the request, the reply,
the trace, the code, the finished GLB and the previews of the features that
version adds) and the GLB files. `index.json` lists the demos in order.
The GLB files are stored gzipped (`.glb.gz`, about 30% of their size), and
`next.config.ts` serves them with `Content-Encoding: gzip`, so the browser
decodes them; Vercel does not compress GLB files itself.

**The public website.** Any Vercel build (or one with `NFNIT_DEMO_ONLY=true`)
is a read-only demo with no backend: `/studio` opens the first demo part,
`/parts` lists the demos, and the chat input, export and saving are replaced by
a link to run Nfinit locally. `frontend/src/lib/site.ts` holds the flag.

**Replay as a version history.** The replay panel shows a timeline with one
point per version, named after the features it adds. "Build next version"
plays the next version like a live run: the request appears in the chat, the
progress steps play, the new features grow in the viewport (new faces
highlighted), and then the finished part appears. Clicking a point on the
timeline, or a reply in the chat history, shows that version at once; later
turns stay in the chat, dimmed, like the rest of a CAD timeline. "Replay this
version" plays the shown version again, and "Watch again" plays the whole
story from version 1. Replays make no backend calls.

**Who sees what.**

- Everyone sees "See how it's built" cards under the prompt box on the
  welcome screen, and `/studio?demo=<slug>` opens a demo directly.
- Every account's Parts gallery (`/parts`, "Your parts") lists the six demo
  parts after the user's own parts, each with a picture of its last version
  and a "Demo part" badge; search covers them too. With no parts of their own,
  a "Make your first part" card comes first. Demos are shown, not copied into
  a user's projects: they use none of the account's storage, and stay up to
  date when the demos change.
- A prompt sent from a demo builds on the shown version as a new project, and
  export works as for any part.

**Rebuild.** From `backend/` (no model calls, so no key and no cost):

```bash
poetry run python -m demos.build [--only fpv-drone]
```

The script runs every version of each design through the CAD sandbox, writes
the GLBs, the previews and `demo.json`, and removes demo folders that are no
longer listed. A demo with a step that does not build is left out. The tests
in `backend/tests/test_demos.py` check that the shipped code is exactly the
design's code for each version and that every version builds on the one
before it.

Then, from `frontend/`, render the gallery pictures (`thumbnail.webp` in each
demo folder) from each demo's last version, with the studio viewer's colours,
lights and camera:

```bash
PLAYWRIGHT_PATH=$(npm root -g)/playwright node scripts/render-demo-thumbnails.mjs
```

The demo build keeps an existing `thumbnail.webp`, so render the pictures
again after a design changes.

**Next: version history for projects.** Projects should get the same
behaviour: each assistant turn in a project's chat is a revision, and
clicking it opens that revision. `ChatPane` already takes a `versions` prop
for this, and the studio already loads revisions (`loadRevision`), so the
remaining work is to map each assistant message to its revision number.
