# E3 official synthetic checks (X.3): record

Recorded on 29 September 2026. This directory keeps the outputs, logs and independent verification of the official X.3 prerequisite, size and power checks for E3, the registered addendum `prereg/E3.md` (OSF [rhzsm](https://doi.org/10.17605/OSF.IO/RHZSM); section 11 and Annex B step 3). The checks use artificial series only. No E3 statistic has been computed on UK data.

## Outcome

The prerequisites passed, and the size and power checks ran once and in full. The registered pass conditions are met.

| Check | Result | Registered condition |
|---|---|---|
| Prerequisites | F2 and AT-11, the r = 0 fixture and the agreement test of the batched filter all passed (below) | Each prerequisite met |
| Size | 11 rejections in 200 series: rate 0.055 (Wilson 95% interval 0.0310 to 0.0958); all 200 replicates valid | Rate between 0.02 and 0.09 inclusive, all 200 valid: met |
| Power, validity | 200 of 200 replicates valid in each of the four cells | Every cell complete and valid: met |
| Power, adjacent differences | +0.0650, +0.0300 and +0.1950: all three are increases, so no decrease exceeds its 1.96-SE threshold | No flagged decrease: met |
| D80 | Undefined: no kappa up to 1.6 reaches 0.80 (the highest rate is 0.340) | Reported |

Power cells (200 series each):

| kappa | Rejections | Rate | Wilson 95% interval | Mean S (standard error) | Difference from previous cell | 1.96 x standard error | Decrease flag |
|---:|---:|---:|---|---|---:|---:|---|
| 1.0 | 10 | 0.050 | 0.0274 to 0.0896 | 0.00089975 (0.00223881) | n/a | n/a | n/a |
| 1.2 | 23 | 0.115 | 0.0779 to 0.1666 | 0.00973824 (0.00210793) | +0.0650 | 0.05355 | no |
| 1.4 | 29 | 0.145 | 0.1029 to 0.2005 | 0.01665182 (0.00231781) | +0.0300 | 0.06585 | no |
| 1.6 | 68 | 0.340 | 0.2779 to 0.4081 | 0.03616202 (0.00265316) | +0.1950 | 0.08180 | no |

In the size cell the mean S is 0.00035830 (standard error 0.00145273), and the Monte Carlo standard error of the rejection rate is 0.0161206.

D80 is undefined because no cell up to kappa = 1.6 reaches a rejection rate of 0.80. As for the H1 validation run, the inconclusive branch of section 11 will therefore carry no Branch B diagnostic. The design is unchanged.

## Registered conditions applied

These are quoted from the registered files.

- Size, `prereg/E3.md` section 11: "Pass: rejection rate between **0.02 and 0.09** inclusive, with all 200 valid."
- Power reporting and D80, section 11: "As H1 §9, including the 1.96-SE decrease flag and the first-raw-crossing D80."
- Cell validity and the decrease rule, `prereg/H1.md` section 9 (Cell reporting), which E3 keeps ("Every H1 rule applies unchanged unless replaced here", `prereg/E3.md`, opening): "A cell is complete and valid only when all 200 provide finite S and valid p." and "If any cell is invalid/incomplete or a decrease exceeds this threshold, AT-16 does not pass and G2 remains pending."
- Prerequisites, section 11: "F2 (plan p. 7) and AT-11 on the implementation used." "With r1 = r2 = 0 and the §6 prior, the final filtered state equals the full-sample OLS estimate to 1e−6 on one base synthetic series, generated from stream 5320, cell 1, replicate 0." "The §6 agreement test for any batched filter."
- Batched filter, section 6: "A batched or re-implemented filter may be used only if, on every X.3 fixture of §11 and on AT-11's fixture, it agrees with that reference to **1e−8** in every filtered state and **1e−6** in l(r)."
- Annex B step 3: "Implement §§6–10 on synthetic data, pass the prerequisites, run the §11 cells, commit and freeze the code."

The two readings adopted for E1 (D-037) apply here in the same way: the power pass condition is H1 section 9's AT-16 condition, carried into E3 by the sentence quoted above, and a replicate is valid when its status is ok and S and p are finite. Neither changes the outcome on the alternative reading. The two E3 readings adopted before the checks (D-035) are recorded in every output: a filter failure at a single grid point discards that grid value (`grid_point_failure: discard`), and every fit is retained (`retention: all_fits`).

## What was run

| Item | Record |
|---|---|
| Code | Research repository commit `6ea02456244efa7c58ac8cb1be682a2b206597c5` (D-036). Code identity SHA-256 `c42cbbf35734eb4f8c12aff22384371aa4fad107ae283f6d2f5f6f93c12feef7`, the same as for the E1 checks. |
| Place | The same separate clone pinned at that commit, working tree clean before and after (D-036). |
| Registration | OSF `rhzsm`; annotated tag `prereg-E3` (tag object `8963e4ac871c0730ae271f28277c4c87216fb004`, commit `5a26bfc8b4af3486cb17e758102f7efc59301379`); protocol SHA-256 `9b891fe691b21a9098f3a0fe811c3d0eae3e615dd6d59f7dc290e908a51a22ae`; registration record SHA-256 `72450300a0b9a39ea40ceeb4da471e5c5ac8d3a7a6493096b925b89807b31007`. |
| Design | Registered mode; master seed 1927; streams 5320 and 5321 (size), 5330 and 5331 (power), and stream 5320 cell 1 replicate 0 for the r = 0 fixture; 200 series per cell; B = 1,000 attempted surrogate draws per series, each re-estimated; kappa = 1.0, 1.2, 1.4, 1.6. Settings recorded in every record: batched engine, agreement check on, grid-point failures discarded, all fits retained. |
| Execution | The prerequisite record first (04:58:35 to 04:58:45 UTC), then `tests/test_foundations.py` again (04:58:45 to 04:58:48), then sixteen parts: eight size parts of 25 series and eight power parts of 100 series (four cells, two halves each), each run once, on eight processes in parallel, with no interruption and no resumption. The summaries were written at 16:00:22 and 16:00:43 and the output hashes listed at 16:00:48. |
| Environment | Python 3.12.14; NumPy 2.5.3; the research lock (`requirements.lock`); Windows 10 (build 19045). |
| Outputs | 1,019 files, 2,539,364,513 bytes, kept outside the repository: sixteen part files, two summaries, the prerequisite record and 1,000 retained-fit files (one per record). Each file's SHA-256 is in `E3/OUTPUT_SHA256.json` and `E3/OUTPUT_SHA256.txt`. The E3 checks followed the E1 checks in one driver run that began at 03:38:46 UTC and finished at 16:00:48 UTC. |

## Prerequisites (section 11)

The prerequisite record is `E3/x3_prerequisite.jsonl` (SHA-256 `d7768a7e0925281b7accd32d27b49ce85134aa59e76c01af470d1f7e834a7a83`); every output names it.

- **r = 0 fixture.** With r1 = r2 = 0 and the section 6 prior, on the base series from stream 5320, cell 1, replicate 0, the final filtered state differs from the full-sample least-squares estimate by at most 1.04e-10 (tolerance 1e-6): passed.
- **Agreement of the batched filter.** On 256 grid points of the prerequisite series, the largest difference from the reference filter is 2.59e-11 in a filtered state and 1.28e-11 in l(r); on the AT-11 fixture it is 5.91e-10 and 3.32e-10 (tolerances 1e-8 and 1e-6); no failure mismatched. In every one of the 1,000 records, the record's own agreement check on 256 grid points stays within the tolerances: largest state difference 2.51e-09, largest l(r) difference 2.84e-10, no mismatched failure.
- **AT-11 on the implementation used.** The fixture is the yearly sunspot numbers 1749-1924 (176 values) bundled with the locked statsmodels. With r = 0 and the section 6 prior, the final filtered state differs from the least-squares estimate by at most 2.29e-09 for the reference filter and 2.29e-09 for the batched filter (tolerance 1e-6): passed.
- **F2 (plan p. 7).** `tests/test_foundations.py` at the run commit: 10 passed in the preflight record (`../e1_x3/preflight/`), and again after the prerequisite record (`stages/E3_F2.json`; exit status 0).

## Surrogate accounting

All 1,000 records have status ok. Across them 1,000,000 surrogate draws were attempted and 999,990 were retained. Ten draws, in seven size-cell records (the smallest retained count is 996), had no eligible episode and were dropped and counted, as section 9 requires ("Drop and count draws with no eligible episode."). No draw failed.

## Independent verification

The verifier `tools/verify_e_x3.py` (version 1.1; see `../e1_x3/README.md`) was run read-only on the stored outputs, twice: once in its standard mode and once with `--deep-fits`, which also decompresses every retained-fit file. Both reports and printed outputs are in `verification/`. Both report:

- 16 part files and 1,000 records; every coordinate of the design present once, none missing, duplicated or outside it; each part written by a single uninterrupted run.
- The p-value recomputed from the stored surrogate statistics for all 1,000 records; the observed S recomputed from the stored input series by the tool's own Kalman filter at the stored variances (largest difference 1.48e-10); the fitted null recomputed (largest difference 2.66e-15); l(r) at the accepted estimate recomputed by the tool's own square-root filter (largest difference 2.27e-13); no record with a problem.
- One fingerprint across the sixteen manifests: commit, Python 3.12.14, code identity above, registered mode, seed 1927.
- The size and power cells, Wilson intervals, adjacent differences, flags and D80 recomputed and equal to the runner's (32 and 92 fields compared, none differs).
- All 1,019 output files match their recorded SHA-256 and size, and no file is present but unlisted. All 1,000 retained-fit files are present with the recorded SHA-256; in the deep run all 1,000 also decompressed and were checked (143.9 s).
- 16 of 16 quotations of registered wording found verbatim in the registered files.

Result of both runs: no problem found, and the runner's summaries and the recomputation agree.

Limits. The verifier takes the stored surrogate statistics, the stored fits and the stored input series as data. It does not regenerate them from the registered seed. It does not repeat the maximum-likelihood searches of section 6 (the grid and the refinement), for the series or for any surrogate: it recomputes the observed S and the log-likelihood at the accepted estimates with its own filter. It therefore does not by itself test random-number generation, series construction, surrogate resampling or the optimiser. The runner's summary step re-verifies every saved record before combining the parts (D-036). A replay from the seed in the manner of the H1 validation review (`audit/G2_REVIEW.md`) remains possible; none has been done for these checks.

## Contents of this directory

- `E3/`: the runner's size and power summaries, the prerequisite record and the SHA-256 listing of the 1,019 output files.
- `stages/`: the stage markers written for E3 (`E3_F2.json`, `E3_parts.json`, `E3_summaries.json`, `E3_hashes.json`).
- `logs/`: the standard output and error of each E3 step, and the driver's complete log `run_log.jsonl` for the E1 and E3 checks. The snapshot in `../e1_x3/logs/` (22,785 bytes) is a byte-for-byte prefix of it.
- `verification/`: the reports and printed outputs of the two verification runs.
- The preflight record for both extensions is in `../e1_x3/preflight/`.
- `MANIFEST_SHA256.txt`: the SHA-256 of every file in this directory except this README and the manifest itself. Files here are stored byte for byte (`.gitattributes`: `audit/e3_x3/** -text`), so these hashes hold for the committed files.

## Consequences

- The code identity above is the identity that the real E3 run (X.4) must present. The registered analysis code is not to be changed before X.4.
- The 1,019 output files stay outside git. No archive location for them is recorded yet.
- E3 X.2 (re-verification of the H1 file's hash and a manifest note; no download) has not begun, and no E3 statistic has been computed on UK data.
- The size cell and the four power cells are checks of the implementation and the surrogate procedure on artificial series. They are not evidence about UK GDP.
