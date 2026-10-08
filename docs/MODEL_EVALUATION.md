# Model evaluation, 2026-10-08

This report compares the studio's model setups on the full CAD50 benchmark. It
was used to choose the default model.

## Method

- **Benchmark:** CAD50, 50 cases in 10 categories (primitives, subtractive
  features, patterns, sketch profiles, edge finishing, mechanical parts,
  iterative edits, selected-face edits, failure recovery, manufacturing).
- **Agent:** the production LangGraph agent from `main`, with the 367-pattern
  corpus from #32 and high reasoning effort.
- **Mode:** live, through OpenRouter. Each setup ran in its own process with
  its own sandbox, 7 processes at once.
- **Cost:** the billed cost that OpenRouter reported for each call, reasoning
  tokens included.
- **Setups:** "A + B" means model A writes the plan and model B writes and
  repairs the code.
- **Interruption:** the OpenRouter key reached its spending limit during the
  first pass. The runs refused with "Key limit exceeded" were run again after
  the limit was raised. Every setup has exactly one result for each of the 50
  cases, and no result in the report comes from a refused call.

Raw reports: `docs/evaluations/cad50-live-2026-10-08.json` (CAD50) and
`docs/evaluations/smoke-live-2026-10-08.json` (smoke, 3 cases).

## Results

| Setup | Passed | Repair rate | Mean time | p95 time | Cost per run | Cost for 50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GPT-5.6 Luna + Claude Opus 5.5 | 49/50 | 42% | 37.7 s | 65.0 s | $0.072 | $3.59 |
| **Claude Sonnet 5.5** | **48/50** | 36% | **19.9 s** | **31.6 s** | $0.044 | $2.20 |
| Claude Haiku 5.5 + Claude Sonnet 5.5 | 47/50 | 32% | 22.1 s | 38.6 s | $0.033 | $1.66 |
| Claude Opus 5.5 | 47/50 | 42% | 46.3 s | 85.9 s | $0.116 | $5.82 |
| GPT-5.6 Luna | 44/50 | 94% | 61.1 s | 127.2 s | $0.009 | $0.44 |
| GPT-5.6 Sol | 42/50 | 80% | 51.3 s | 115.6 s | $0.053 | $2.67 |
| GPT-5.6 Terra | 41/50 | 62% | 27.8 s | 51.8 s | $0.046 | $2.28 |

Total cost: $18.65 for CAD50 and $0.77 for the smoke run.

The repair rate is the share of runs that needed at least one repair after the
first code failed. The times are for the whole run (plan, code, check and
repairs), measured with 7 setups running at once.

## Failures

- **Claude Sonnet 5.5:** `manufacturing_sheet_tray`, `manufacturing_phone_cradle`.
- **Claude Opus 5.5:** `manufacturing_printable_bracket`,
  `manufacturing_sheet_tray`, `manufacturing_phone_cradle`.
- **GPT-5.6 Luna + Claude Opus 5.5:** `manufacturing_sheet_tray`.
- **GPT-5.6 Sol:** 8 cases in 5 categories, including simple subtractive and
  pattern cases (`subtract_plate_center_hole`, `pattern_four_top_bosses`).

All failures of the Claude setups are manufacturing cases, which are the
hardest category. In every listed failure the code built, but the geometry
failed a check.

## Decision

**The default model is Claude Sonnet 5.5.** Compared with Claude Opus 5.5,
the previous default, it:

- passed 1 more case (48 against 47);
- was 2.3 times faster on average (19.9 s against 46.3 s) and 2.7 times faster
  at p95 (31.6 s against 85.9 s);
- cost 2.6 times less per run ($0.044 against $0.116);
- needed a repair less often (36% against 42%).

GPT-5.6 Luna + Claude Opus 5.5 passed 1 more case than Sonnet 5.5. One case
in 50 is within noise, and that setup is 1.9 times slower and 1.6 times more
expensive. A cheaper plan model did not improve either strong code model
enough to be worth the extra step, so the studio keeps one model per run. The
`planModelId` option remains available for later evaluations.

The model menu offers Claude Sonnet 5.5 (default) and Claude Opus 5.5. The
GPT-5.6 models were removed from the menu after this comparison; a project
saved with one opens with the default model.

## Limits

- 50 cases per setup. A difference of 1 or 2 cases is not significant.
- One run per case. Model output varies between runs, so a repeat can change
  a result.
- The times include contention from 7 processes at once and OpenRouter's
  provider routing on that day.

## Repeat the evaluation

From `backend/`, with `OPENROUTER_API_KEY` set:

```bash
CAD_SANDBOX_MODE=fork poetry run python -m evaluation.cli \
  --cases evaluation/cases/cad50.json \
  --mode live \
  --config evaluation/config/live_models.json \
  --output evaluation/reports/cad50-live.json
```

To run one setup, use `--model` instead of `--config`. To give the plan step
its own model, write the setup as `plan-model+code-model`. Use an OpenRouter
key with its own spending limit, so that an evaluation cannot use up the
production key.
