# 2023 prompt search

## v3: development feedback instead of a memory gate

`config.prompt-search-v3.json` enables `development_feedback` and disables
`require_memory_gate`. v2's default gate behavior is preserved. v3 logs all candidates'
paired development-memory corrections/regressions, exact instruction diffs, declared changes
and risks, then supplies the history to the next round's analysis and generation requests.
No selection scores, selection cases, or test cases enter this history. Response changes are
observational, not causal evidence about an individual clause. History includes non-adopted
candidates, so unsuccessful edits can inform later revisions.

Memory is still evaluated (up to 50 cases) and logged, but does **not** disqualify a candidate.
Selection uses the same 140-case accuracy criterion, macro-F1/length candidate tie-breaking,
and incumbent retention on accuracy ties. Maximum five rounds and patience two are retained.
Same split and P0 start; existing one-rule-edit guidance remains. No label-specific veto.

```powershell
python -m residue_experiment.prompt_search prepare --config config.prompt-search-v3.json --output results/prompt-search-2023-v3
python -m residue_experiment.prompt_search search --output results/prompt-search-2023-v3 --mode live --max-calls 2950
if ($LASTEXITCODE -eq 0) {
    python -m residue_experiment.prompt_search final --output results/prompt-search-2023-v3 --mode live --max-calls 3370
}
```

Use `--mode mock` for offline checks. Planned maximum remains 3,370 requests (no retries);
larger history increases input tokens and therefore potential cost. Existing results are not reused
across versions. `round-XX/development_feedback.json` records each round's observations;
`optimizer_feedback_input.json` records the exact analysis input including prior history.
`memory_gate_applied: false` in selection records confirms memory is diagnostic only.

## Follow-up v2: cumulative validation and early stopping

Use a **new output directory**. Old v1 plans/results stay unchanged.

```powershell
python -m residue_experiment.prompt_search prepare --config config.prompt-search-v2.json --output results/prompt-search-2023-v2
python -m residue_experiment.prompt_search search --output results/prompt-search-2023-v2 --mode mock
python -m residue_experiment.prompt_search final --output results/prompt-search-2023-v2 --mode mock
```

Paid execution, only when intended:

```powershell
python -m residue_experiment.prompt_search search --output results/prompt-search-2023-v2 --mode live --max-calls 2950
if ($LASTEXITCODE -eq 0) {
    python -m residue_experiment.prompt_search final --output results/prompt-search-2023-v2 --mode live --max-calls 3370
}
```

v2 preserves the exact v1 split/batches and P0 start. Each batch contributes up to 10 development
cases: up to six errors first, then correct examples alternating labels, then remaining errors if
space remains. This is a deterministic sampling heuristic, **not** expert semantic counterexample
selection. Selection/test cases never enter memory. Cumulative memory is re-evaluated per candidate;
the incumbent's already available outputs are reused by prompt hash/item ID.

The optimizer sees current development cases and accumulated development evidence. Instructions
request one-rule edits, application limits and evidence gaps; this is prompting guidance, not a
formal guarantee that a candidate changes only one rule. Candidate eligibility requires correction
of at least one selected current error AND no drop in total cumulative correct count versus the
incumbent. This permits individual regressions offset by repairs; all fixed/broken IDs are saved.
Among eligible candidates, accuracy/macro-F1/length selection is unchanged; ties retain incumbent.
No-error rounds also count as no improvement. Two consecutive non-adoptions stop search early.
Partial `--through-round` runs do not finalize unless a real stop condition is reached.

Maximum planned requests: 2,920 + 3*(10+20+30+40+50) = **3,370**, assuming five full rounds,
valid responses and no retries. Search alone is 2,950. Identical candidates/cache reuse, no-error
rounds or early stopping can reduce usage. Dollar cost is not bounded by this call cap; optimizer
inputs grow. Optional multi-run selection confirmation is NOT enabled and is not in this budget.

Reports and audit: `python scripts/audit_prompt_search.py` reads v1 local files and creates
`analysis/reports/prompt_search_audit/report.html` and `audit.json` without API calls.
v2 remains exploratory: neither cumulative development gates nor early stopping eliminate adaptive
selection overfitting. Development/selection substance overlap and the already-inspected 2023 set
remain limitations. No grouping changes were silently made to the 466-row pool.

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
