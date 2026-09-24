# M1a - local core mathematics and estimators

Completed 2026-09-24. This report records the M1a checkpoint; subsequent progress is recorded in `M1_READINESS.md`.

## Delivered

- Independent research implementations of intercept-inclusive least squares, the specified Yule-Walker convention, companion roots, strict triangle stability, period, decay half-life and interior spectral-peak diagnostics.
- Immutable fit results, explicit invalid-input errors and retained unstable estimates.
- The elementary two-direction AR(2) triangle proof and Schur-step crosscheck in `proof/triangle.md` and `proof/triangle.tex`, with a one-page `proof/triangle.pdf`.
- `docs/CORE_CONVENTIONS.md`, 37 new scientific-contract tests and `tools/verify_m1a.py` with recorded evidence.

## Verification

The original M1a checkpoint passed 49 tests (12 baseline and 37 core tests). `audit/m1a_verification.json` records the latest verification, full-precision sunspot fits, package versions and file digests; later reruns also include subsequently added tests. OLS and Yule-Walker match the independent baseline and statsmodels references under the specified sampling conventions. Tests exercise scale/offset invariance, wrong-input rejection, unstable fits, real/complex/repeated/zero roots, strict boundaries and the distinction between complex roots and spectral peaks.

AT-7: 100,000 seeded coefficient pairs were checked against companion-matrix eigenvalues; no mismatches occurred. Edge exclusions, random generator and input digest are recorded. This is a numerical acceptance check, not a formal proof.

The PDF was compiled with pdfLaTeX, confirmed to have one page, rendered with Poppler and visually inspected. Equations, title, footer and all proof steps are legible without clipping. Mathematical checks covered necessity, sufficiency and Schur equivalence. This is a paper proof; it is not a Lean certificate or an external referee report.

## Limits and next work

The M1a core supports AR(2) only. Rolling estimation and recession indexing were assigned to M1b, with surrogate generation and protocol completion assigned to M1c. No real UK research data or registered simulation cells were used. Local verification alone does not satisfy external publication or registration gates.

Exact byte-hash evidence uses LF newlines for generated JSON and source files, matching Git's stored text. The initial M0 snapshot was made before this portability correction; the current verifier refreshes it under the documented newline convention.
