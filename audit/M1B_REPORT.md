# M1b - causal windows and recession bookkeeping

Completed 2026-09-24. This report records the M1b checkpoint; subsequent progress is recorded in `M1_READINESS.md`.

## Delivered and verified

- `src/uc_core/rolling.py`: within-window intercept-inclusive AR(2), preserved pandas index, explicit warm-up and fit errors; no future values enter earlier fits.
- `src/uc_core/recession.py`: qualifying negative runs, inclusive eight-quarter episode merging, retained first onset, exact pre-onset differences and explicit empty eligibility.
- `docs/M1B_CONVENTIONS.md`: positional/date mapping, calendar checks, window endpoints and failure behaviour.
- 26 additional tests, for **75 passing tests** in the full suite.
- `tools/verify_m1b.py` and `audit/m1b_verification.json`: seeded synthetic input hash, end-to-end results, prefix-invariance check, runtime and source/test hashes.

Hand-worked fixtures provide reference values. The implementation tests confirm: exactly-eight merges but nine does not; chained runs merge against the latest run end; isolated negatives do not reset the clock; zeros interrupt runs; a terminal pair qualifies; W=40 first yields M at position 39 and first eligible onset at 48; merging into an earlier ineligible onset does not make it eligible; signed changes [.06, -.02] average to .02.

The recorded synthetic end-to-end fixture contains deliberately inserted negative pairs at positions 48, 60 and 100. It detects exactly those episodes and retains identical earlier estimates when future observations are withheld. Its numerical S is merely a software check, not an empirical finding or a power estimate.

## Limits

The reference rolling implementation has not yet been optimized for tens of millions of regressions. It provides the comparison standard for a later vectorized implementation. No surrogate model, bootstrap p-value, confirmatory size/power run or real UK dataset was used. General datetime indices are checked for order/uniqueness; the eventual data ingestion must verify actual quarterly frequency. PeriodIndex gaps are rejected directly.

The subsequent M1c reports cover synthetic surrogate mechanics, the failure policy, the H1 registration draft and infrastructure verification. Data acquisition remains subject to G1.
