# loop20 results by work package

Each row is three live runs of `loop20` through Claude Code (`--agent
local/claude`), on an Apple silicon Mac, after the work package merged. The
method is the one in `loop20-baseline.md`. Raw reports are in this folder,
named `loop20-claude-<stage>-run<n>.json`.

| Stage | Passed (runs 1, 2, 3) | Mean passed | Mean time per case | Mean tokens per case |
| --- | --- | ---: | ---: | ---: |
| Baseline | 19, 19, 20 | 19.3 | 31.0 s | 29,019 |
| 1: prompt | 20, 20, 20 | 20.0 | 36.6 s | 39,662 |
| 2 to 7: checks and tools | 20 (one run) | 20.0 | 44.7 s | 86,930 |
| 9: short tool results | 20, 20, 20 | 20.0 | 44.1 s | 78,550 |

## Notes

- **Work package 1.** The only baseline failure, a tray whose walls were read
  as its overall height, did not recur: `stacked_reading` passed 4 of 4 in all
  three runs. The longer prompt costs about 37% more tokens and 18% more time
  per case. In run 2, two cases stopped when Claude Code hit a temporary usage
  limit; they were run again on their own and both passed. The run 2 report
  holds the rerun results.
- **Work packages 2 to 7.** One run of all six together, then stopped to save
  usage: every part passed, but tokens per case more than doubled. Output
  tokens barely moved (3,548 against 3,187); input tokens went from about
  37,000 to 83,000. Each turn of the CLI rereads the conversation, and the new
  tools add turns (declaring requirements, checking printability) and longer
  results.
- **Work package 9.** Shorter tool results brought tokens down about 10%, to
  78,550 per case; output stayed at about 3,300. Most of the rest is input the
  CLI rereads on each turn. In every run the backend's own verdict was
  `verified` for 19 of 20 parts. The 20th, `edit_hole_size_keeps_corners`,
  was flagged "Holes of 6 mm went from 2 to 0" although the user asked for
  that resize. Edit safety now flags only a drop in the total number of a kind
  of feature, so that edit passes.
- **Against the baseline.** All 60 parts across the last three runs were right,
  against 58 of 60 before, and the backend now proves each one from
  measurements instead of trusting the agent. The cost is about 2.7 times the
  tokens and 1.4 times the time per part. loop20 is too easy to show much more
  than that: a harder suite should come next.
