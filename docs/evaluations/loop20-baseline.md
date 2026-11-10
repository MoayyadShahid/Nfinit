# loop20 baseline, 2026-11-10

The score of the local agent loop before any of the work in
`docs/CAD_LOOP_PLAN.md`. Later work packages compare against it.

## Method

- **Suite:** `backend/evaluation/cases/loop20.json`, 20 cases.
- **Agent:** Claude Code 2.1.319 through `--agent local/claude`, the same path
  the local studio uses. The loop was the one on `main` at `52be5f3`. The new
  feature census was left out of the agent's tool output, so the agent saw
  exactly what it saw before.
- **Runs:** three, one after another, on an Apple silicon Mac with the sandbox
  in spawn mode.
- **Command:**

  ```sh
  python -m evaluation.cli --cases evaluation/cases/loop20.json \
    --mode live --agent local/claude --output <report>.json
  ```

Raw reports: `loop20-claude-baseline-run1.json` to `run3.json` in this folder.

## Results

| Run | Passed | Mean time per case | Mean tokens per case | Failed |
| --- | ---: | ---: | ---: | --- |
| 1 | 19/20 | 29.5 s | 28,473 | `stacked_tray` |
| 2 | 19/20 | 31.7 s | 29,011 | `stacked_tray` |
| 3 | 20/20 | 31.8 s | 29,572 | none |
| **Mean** | **19.3/20** | **31.0 s** | **29,019** | |

By category, cases passed in runs 1, 2 and 3:

| Category | Run 1 | Run 2 | Run 3 |
| --- | ---: | ---: | ---: |
| `silent_finish` | 4/4 | 4/4 | 4/4 |
| `detached` | 4/4 | 4/4 | 4/4 |
| `stacked_reading` | 3/4 | 3/4 | 4/4 |
| `hole_pattern` | 4/4 | 4/4 | 4/4 |
| `edit_regression` | 4/4 | 4/4 | 4/4 |

## What it shows

- The only repeated failure is a stacked height. Asked for "a 3 mm base and
  12 mm tall walls", the agent built a tray 12 mm tall instead of 15 mm in two
  of three runs. The local agents never receive the dimension-reading rules
  the hosted planner has.
- Claude Code passes almost everything else. loop20 is close to its ceiling
  for this agent, so later gains will show mostly as fewer tokens, less time
  and stable `stacked_reading` results, not a higher pass rate. A harder suite
  is needed to show gains in checking; see the plan's progress table.
