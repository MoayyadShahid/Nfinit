# loop20 results by work package

Each row is three live runs of `loop20` through Claude Code (`--agent
local/claude`), on an Apple silicon Mac, after the work package merged. The
method is the one in `loop20-baseline.md`. Raw reports are in this folder,
named `loop20-claude-<stage>-run<n>.json`.

| Stage | Passed (runs 1, 2, 3) | Mean passed | Mean time per case | Mean tokens per case |
| --- | --- | ---: | ---: | ---: |
| Baseline | 19, 19, 20 | 19.3 | 31.0 s | 29,019 |
| 1: prompt | 20, 20, 20 | 20.0 | 36.6 s | 39,662 |

## Notes

- **Work package 1.** The only baseline failure, a tray whose walls were read
  as its overall height, did not recur: `stacked_reading` passed 4 of 4 in all
  three runs. The longer prompt costs about 37% more tokens and 18% more time
  per case. In run 2, two cases stopped when Claude Code hit a temporary usage
  limit; they were run again on their own and both passed. The run 2 report
  holds the rerun results.
