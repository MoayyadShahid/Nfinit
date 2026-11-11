# Demo rehearsal, 2026-11-10

Four parts of the kind the demo video will show, each run five times through
Claude Code (`--agent local/claude`) on `main` after live progress, exports and
the measure tool merged. Cases: `backend/evaluation/cases/demo.json`, with
reference solutions in `backend/evaluation/replays/demo.json`. Raw reports:
`demo-claude-run1.json` to `run5.json` in this folder.

| Part | Correct | Verified by the backend | Mean time (range) | Mean tokens |
| --- | ---: | ---: | --- | ---: |
| Board enclosure with four standoffs | 5/5 | 5/5 | 51 s (41 to 58) | 88,847 |
| 40 mm fan mount | 5/5 | 5/5 | 33 s (31 to 35) | 66,443 |
| Fan mount edit: thicker, with a tab | 5/5 | 5/5 | 48 s (39 to 62) | 79,109 |
| Phone stand with a 70 degree back | 5/5 | 5/5 | 70 s (60 to 95) | 105,932 |

## Notes

- The fan mount edit first scored 0 of 5 on the overall length. Every run built
  the tab 20 mm out from the edge and 10 mm wide along it, for a 60 mm part;
  the case expected the opposite reading of "a 10 mm wide, 20 mm long tab
  sticking out". The agent's reading is the natural one, so the case was
  corrected, and all five runs pass against it. Every run kept the 38 mm fan
  hole, the four 3.4 mm screw holes and the rounded corners, added one 4 mm
  hole, and raised no edit-safety flags.
- The phone stand is the slowest and most variable part (up to 95 s), because
  the angled back needs more building and checking.
- For the video, the fan mount and its edit are the quickest to show live; the
  enclosure shows the most features being checked.

## Run it again

From `backend/`, with Claude Code signed in:

```sh
python -m evaluation.cli --cases evaluation/cases/demo.json \
  --mode live --agent local/claude --output evaluation/reports/demo.json
```
