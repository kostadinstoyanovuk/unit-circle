# H1 validation execution checklist

Prepared 26 September 2026. This checklist implements the submitted H1 protocol; it does not amend the design or report experimental results. Sections 8, 9 and 12 of `prereg/H1.md` remain authoritative. All official cells are unrun.

## 1. Registration receipt: G1

Verify anonymous access to the immutable OSF registration and its public status. Record its identifier, actual registry timestamps, verification time and DOI if assigned. Distinguish submission time from public availability. Resolve which documented public timestamp governs H1 section 3 before selecting a QNA vintage; do not silently substitute a convenient timestamp.

Download the five archived attachments and compare their SHA-256 hashes with `audit/H1_REGISTRATION.json`. A file listing, matching name or size does not establish byte identity. Keep receipt evidence separate from the submitted documents. Publish the annotated `prereg-H1` tag for the exact committed protocol only once these requirements are satisfied. A pending, private or embargoed registration keeps G1 open.

## 2. Resumable execution preparation

Completed development checkpoint: see [runner documentation](VALIDATION_RUNNER.md) and [verification report](../audit/M2_RUNNER_REPORT.md). The requirements below remain applicable to subsequent official runs; completing the runner does not pass G1 or G2.

Implement and review a runner that preserves one immutable record per requested cell and replicate. A restart must verify its saved identity and bytes, reuse the same frozen stream coordinates and account for every requested replicate exactly once. A failed replicate is a retained outcome; it is not retried with a different seed. Detect altered, duplicate, missing and incompatible records before summarising. Retain requested, attempted, failed and unfinished counts explicitly.

Each record must retain input series, generator states, result/status, errors, code and environment identity, and output checksums. For size and power, also retain the full surrogate statistics and attempt statuses required by H1. Save a run manifest and append-only execution log. Write completed records atomically so interrupted writes cannot be counted as results. Save and verify checkpoints between bounded batches.

Test interruption, resumption, accounting, integrity failures and summary arithmetic using constructed records and small development fixtures. Keep development fixtures separate from official cells and stream coordinates. Time only these fixtures before estimating compute and storage; do not report their values as calibration or power evidence. A passing test suite alone does not pass G2.

## 3. Official experiments after G1

| Experiment | Frozen requested work | Acceptance and retained limits |
|---|---|---|
| AT-5, length 30 | 100,000 independent stored Gaussian series; stream 400 | Complex-root proportion 0.630 +/- 0.005 inclusive; every fit valid |
| AT-5, length 1,000 | 60,000 independent stored Gaussian series; stream 401 | Complex-root proportion 0.520 +/- 0.006 inclusive; every fit valid |
| AT-15 size | 200 length-259 base series; streams 200/201; 1,000 requested residual surrogates per comparison | Endogenous onset procedure; valid rejection rate 0.02 to 0.09 inclusive; all 200 comparisons valid |
| AT-16 power | Four kappa cells 1.0, 1.2, 1.4, 1.6; 200 series each; streams 300/301; 1,000 requested surrogates per comparison | Five externally fixed positions; all cells valid; disclosed adjacent decrease checks and first-crossing D80 rule |

These designs request 160,000 white-noise fits and up to 1,000,000 surrogate attempts across size and power. Actual attempts can be lower only under the protocol's explicit pre-draw failures; nominal replicate counts never shrink. Cell and replicate coordinates, initialization and generation order are exactly those in H1. Do not replace the endogenous size test with the fixed-date power proxy.

Report all invalid/unfinished outcomes, accounting bounds, conditional valid-only rates, Monte Carlo uncertainty and the original acceptance decisions. Never increase counts, tune methods, smooth power rates or change seeds to obtain a pass. Any failed acceptance check keeps G2 pending; retain the failure and document the response before considering an amendment.

## 4. G2 review and first empirical acquisition

Combine the registered experiments with all required estimator and baseline checks. Verify their evidence, input/output integrity and method identity before marking G2 passed. Only after G1 and G2 pass may the verified release-specific UK source be acquired. Retain its source identity, first-download time and file hash. If the eligible release or its file cannot be verified, invoke the existing stop-and-amend rule before inspecting observations. No unverified latest-file fallback is allowed.

M2 closes only after these checks, the frozen H1 analysis and its reproducible core note are complete. This checklist is preparatory work and does not close M2.
