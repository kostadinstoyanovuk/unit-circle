# M1c.2 completion report

Date: 2026-09-24. **M1c.2a and the M1c.2b methodological draft are complete. Local infrastructure and the prior-data declaration are complete. M1 closure awaits verification of the current public repositories and hosted checks under G0.**

## Methods delivered

- Window sensitivities at 32/48, fixed observed onsets and wild signs use explicit independent streams.
- Kendall tau-b trend and the signed lag-one comparator use the same generated primary paths, with separate eligibility, failure counts and retained denominators.
- The conditional 90% episode interval uses 10,000 resamples in the final protocol, with explicit zero/single-episode outcomes and saved random states.
- The joint reporting layer preserves computable comparisons when another observed/surrogate statistic fails. Null failure, no eligible episode and numerical failure remain distinct.
- An external fixed-date interface implements the planted-signal proxy without substituting data-derived recession dates.
- The single constants module fixes streams; synthetic-design helpers implement the stationary initial pair, planted dates, Wilson precision intervals and first-crossing D80 arithmetic.

The research suite has **204 passing tests**: 113 existing, 62 secondary utility tests, 21 integration tests and 8 synthetic-design arithmetic tests. The bounded end-to-end fixture uses 140 artificial observations, 12 attempted draws per comparison mode and 1,000 episode resamples. Its primary results and final generator state exactly match the M1c.1 reference. No numerical failure occurred. Full evidence is in `m1c2_verification.json`; reproduce with `.venv/Scripts/python.exe tools/verify_m1c2.py`.

Method review found and repaired an observed-failure isolation error: a failed primary rolling fit could previously discard a still-computable lag-one result. A regression test now uses an initially linear synthetic segment to demonstrate the distinction. Another exactness check ensures kappa1 uses the base intercept 1.5 at every time step. No real outcome influenced either correction.

These tests do not pass AT5, AT15 or AT16. The large registered validation cells have not run, and no raw UK data was acquired or analysed. Small development fixtures and constructed power-summary tables are not scientific power estimates.

## Protocol and source preparation

`prereg/H1.md` is a standalone, unregistered protocol draft. It fixes the primary/secondary definitions, data release-selection and sample-validation rules, seed mapping, synthetic generation and initialization, outcome wording, D80 interpolation, incomplete-cell handling, extension-family adjustment and retained records. D-013 through D-015 record clarifications and prior-work scope. `H1_SOURCE_METADATA.md` distinguishes verified ONS methodology from the unopened series page and future release-specific file verification.

No methodological H1 placeholder is intentionally left open. The declaration dated 2026-09-24 records no inspection/download of UK GDP data or UK recession analysis before this project. No earlier registration is known; its absence has not been independently established. Final registration details, release-route metadata and external evidence remain to be verified before submission. A manifest fingerprints the current draft; it is not a registration receipt.

## Local infrastructure delivered

The research repository now has a pinned CI recipe. The separate `unitcircle` development package was built and installed, with 3 passing installed-package tests. The separate `schur-cohn` repository has pinned Lean/mathlib, a successful local build and inspected axiom lists for two setup examples. Those examples are not the programme's formal theorem. Detailed versions, hashes, logs and the sibling commit identifiers are in `M1_INFRASTRUCTURE.md` and `.json`.

## M1 closure and subsequent registration

G0 requires the current research, package and Lean repositories to be public, with successful hosted checks at their published commits. Verification of the revised publication is pending. `GITHUB_PUBLICATION.json` records the publication evidence; local build results do not establish current hosted success.

M1 can close once G0 is verified. Public OSF registration and the matching pushed `prereg-H1` tag belong to M2/G1. That tag must identify the registered protocol, not this draft. No UK observations may be acquired before G1, and no preregistration is claimed by this report.
