# 2023 prompt search

This implements the agreed **2,920-call planned maximum** (before failures or extra evaluations):
140 baseline selection + 250 development + 10 optimizer + 2,100 candidate selection + 420 final.
Uses the exact-deduplicated 466-row historical pool (2018, 2019, 2021, 2022; no 2020 file).
No paid calls occur during preparation or mock execution.

## Prepare

From the repository root:

```powershell
python -m residue_experiment.prompt_search prepare
```

Freezes the configuration, source rows, P0, optimizer instructions, seed, 326 development rows,
140 selection rows, five disjoint 50-row batches, and 70 test rows in `plan.json`.
CSV exports make the partition reviewable. Uses deterministic proportional year/label allocation.
76 development rows remain unused. Semantic near-duplicates are **not** detected or grouped;
review the exported split before live execution. Exact historical/test input overlap is recorded
in the plan; no test outcomes influence search. Modified configuration requires a new plan/output.

## Offline smoke run

```powershell
python -m residue_experiment.prompt_search search --mode mock
python -m residue_experiment.prompt_search final --mode mock
```

Mock and live records are physically separate. Mock accuracy is arbitrary and is not scientific evidence.

## Paid execution (explicit)

Configure `OPENROUTER_API_KEY` in the environment or `.env`. Requires the optional API dependencies.

```powershell
python -m residue_experiment.prompt_search search --mode live --through-round 1 --max-calls 612
python -m residue_experiment.prompt_search search --mode live --max-calls 2500
python -m residue_experiment.prompt_search final --mode live --max-calls 2920
```

The cap is cumulative per mode/output directory, not per invocation. It limits requests, not dollars.
No automatic retries. Usage returned by the API is stored per attempt; no currency price is assumed.
First command budgets the baseline and one full round. Continuing recomputes decisions from cached
responses and does not repeat completed calls. Search never issues test requests. Final evaluation is
a separate command and requires a frozen winner after all five rounds.

## Search rules

The current winner solves 50 development problems. All batch cases (wrong and correct) go to the
optimizer. Analysis then generation produces three complete prompts, with a fixed Yes/No output guard.
Each candidate solves all 140 selection problems once. Accuracy wins; equal accuracy retains the
incumbent. Among new tied candidates use macro-F1 then shorter prompt. Prior selection calls are cached.
No-error development batches skip optimization and retain the incumbent (actual calls can be lower).
Candidates and analysis are saved for inspection. There is no automated scientific validity review.
Generation/label format errors stop rather than being silently excluded or regenerated.

Five rounds are one optimizer run, not five independent replications. Repeated selection can overfit.
2023 was inspected in previous work and must not be described as a pristine prospective test.
Final P0/winner each run three times. Reports contain accuracy, macro-F1, confusion counts, prediction
rows, per-item correction/new-error counts and mean metrics. No significance claim is generated.

## Recovery and audit

Each request is written as `started` before sending, then `success` or `error`, with exact prompts,
model/settings, response, usage and request ID. A crash after dispatch can leave an uncertain charge.
Such records block automatic resend. Inspect them before deciding on a separate retry procedure;
do not delete records casually. Malformed successful output similarly blocks the workflow for review.
An exclusive mode lock prevents concurrent CLI runs; after a forced process termination verify no
process remains before removing a stale lock. Completed final results can be regenerated from cache.
