# M1c.1 - surrogate mechanics

Completed 2026-09-24. This report records the M1c.1 checkpoint; subsequent progress is recorded in `M1_READINESS.md`.

## Delivered and checked

`src/uc_core/surrogate.py` implements the full-sample fitted null, conditional AR(2) generation, centered-residual and wild-sign draws, primary endogenous episodes, secondary fixed observed onsets, and the upper-tail plus-one calculation. The result preserves observed signed changes, per-attempt outcomes, counts, fitted null and random-generator states. Numerical failures invalidate the p-value; they are never counted as empty recession results or silently replaced.

The specification was written before implementation in `docs/M1C1_SURROGATE_CONTRACT.md`; its review clarified calibration limits, draw order and failure accounting. D-012 and audit item A09 record the stable-full-sample-null policy and other preregistration additions. These rules must appear in the final registration.

All **113 tests passed**, including **38 new surrogate tests**. They check hand-calculated recursion, both innovation schemes, unchanged initial values, residual centering, null boundary handling, fixed-onset routing without surrogate recessions, empty observed/reference outcomes, exact attempted counts, failure continuation, seed reproducibility and unchanged global randomness. AT-14's formula is verified, including ties, zero exceedances and the retained denominator. This does not establish AT-15 size or AT-16 power.

`tools/verify_m1c1.py` saves full machine-readable evidence in `audit/m1c1_verification.json`: input hash, development seeds, generator states, source hashes, environment versions, test output and individual outcomes. Its 140-observation synthetic fixture has deliberately planted negative pairs at positions 48, 60 and 100. Each mode attempted 24 draws:

| Mode | Retained | No eligible episode | Failed |
|---|---:|---:|---:|
| Residual, endogenous onsets | 3 | 21 | 0 |
| Residual, fixed observed onsets | 24 | 0 | 0 |
| Wild, endogenous onsets | 19 | 5 | 0 |

The small retained count in the first mode illustrates why B requested and B retained must be reported separately. With three retained draws its p grid has spacing 1/4. This fixture was designed to test mechanics; its p-values have no empirical interpretation and cannot estimate size or power. No replacements or tuning followed these results.

## Subsequent work and evidence limits

M1c.2 records the secondary trend/lag-1/interval definitions and implementations, registration seed allocation, source-release metadata and missing-data rules, power-study specification and full H1 draft. The declaration dated 2026-09-24 records no prior inspection/download of UK GDP data or UK recession analysis before the project. Literature and incidental headline exposure during preparation are recorded separately in `STATISTICAL_SOURCES.json`. Real UK values remain inaccessible until G1; official size/power cells require the frozen registered design. The reference rolling implementation remains the correctness standard; optimization requires a separate benchmark and equivalence check.

Reproduce this checkpoint from the repository root with `.venv/Scripts/python.exe tools/verify_m1c1.py`. No new dependencies or network access are required for verification. These development checks do not constitute external peer review.
