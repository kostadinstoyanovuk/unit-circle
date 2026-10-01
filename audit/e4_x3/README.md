# E4 official synthetic checks (X.3): record

Recorded on 1 October 2026. This directory keeps the outputs, logs and independent verification of the official X.3 size and power checks for E4, the registered addendum `prereg/E4.md` (OSF [dpxqf](https://doi.org/10.17605/OSF.IO/DPXQF); section 11 and Annex B step 3). The checks use artificial series only. No real-time level has been read, and no E4 statistic has been computed on UK data. Amendment 1 to the registration (`audit/E4_AMENDMENT_1.json`, D-053) settled how the vintage labels are read and how the parts of the table are joined at the structure mapping (X.2); it does not touch section 11.

## Outcome

The size and power checks ran once and in full. The registered pass conditions are met.

| Check | Result | Registered condition |
|---|---|---|
| Prerequisites | F1 as the repository records it, AT-1 to AT-4 through `uc_core.ar` and the unit tests of sections 4, 5 and 7 (139 passed) passed before the first part (below) | Annex B step 3 |
| Size | 9 rejections in 200 series: rate 0.045 (Wilson 95% interval 0.0239 to 0.0833); all 200 replicates valid | Rate between 0.02 and 0.09 inclusive, with all 200 valid: met |
| Power, validity | 200 of 200 replicates valid in each of the four cells | Every cell complete and valid: met |
| Power, adjacent differences | +0.0000, +0.1100 and +0.0750; no decrease exceeds its 1.96-SE threshold | No flagged decrease: met |
| D80 | Undefined: no kappa up to 1.6 reaches 0.80 (the highest rate is 0.245) | Reported |

Power cells (200 series each):

| kappa | Rejections | Rate | Wilson 95% interval | Mean S (standard error) | Difference from previous cell | 1.96 x standard error | Decrease flag |
|---:|---:|---:|---|---|---:|---:|---|
| 1.0 | 12 | 0.060 | 0.0347 to 0.1019 | -0.00085597 (0.00448259) | n/a | n/a | n/a |
| 1.2 | 12 | 0.060 | 0.0347 to 0.1019 | 0.00364114 (0.00462316) | +0.0000 | 0.04655 | no |
| 1.4 | 34 | 0.170 | 0.1243 to 0.2282 | 0.03902455 (0.00472927) | +0.1100 | 0.06159 | no |
| 1.6 | 49 | 0.245 | 0.1906 to 0.3090 | 0.05434790 (0.00522468) | +0.0750 | 0.07914 | no |

In the size cell the mean S is -0.00679056 (standard error 0.00450388), and the Monte Carlo standard error of the rejection rate is 0.0146586.

D80 is undefined because no cell up to kappa = 1.6 reaches a rejection rate of 0.80. Section 11 anticipated this: "H1's registered power cells reached a rejection rate of 0.235 at κ = 1.6, so H1's D80 is undefined (D-032). E4 has at most four episodes and its cells use five synthetic vintages, so its power on the real vintages may be lower than the cells show, and its D80 may be undefined; the Branch B diagnostic would then be unavailable. This follows from the design and is recorded, not corrected." The Branch B diagnostic of the inconclusive branch will therefore be reported as unavailable, as for E1 and E3. The design is unchanged.

## Registered conditions applied

These are quoted from the registered files.

- Size, `prereg/E4.md` section 11: "Pass: rejection rate between **0.02 and 0.09** inclusive, with all 200 valid. A rejection in the cells is a valid raw p ≤ 0.05, as in H1 §9."
- Power reporting and D80, section 11: "**Reporting and D80.** As H1 §9, including the 1.96-SE decrease flag and the first-raw-crossing D80."
- Cell validity and the decrease rule, `prereg/H1.md` section 9 (Cell reporting), which E4 keeps ("Every H1 rule applies unchanged unless replaced here.", `prereg/E4.md`, opening): "A cell is complete and valid only when all 200 provide finite S and valid p." and "If any cell is invalid/incomplete or a decrease exceeds this threshold, AT-16 does not pass and G2 remains pending."
- No revision noise, section 11: "There is no revision noise. The check measures the per-vintage fixed-date procedure, not the effect of revisions. This limit is disclosed."
- Annex B step 3: "Pass the prerequisites, as in E1: F1 (plan p. 7); AT-1 to AT-4 through the same estimator (research code `uc_core.ar`); and unit tests of §§4, 5 and 7 on constructed workbooks and availability tables", and then "Run the §11 cells, commit and freeze the code."

The two readings adopted for E1 (D-037) and applied to E3 (D-038) apply here in the same way: the power pass condition is H1 section 9's AT-16 condition, carried into E4 by the sentence quoted above, and a replicate is valid when its status is ok and S and p are finite. `docs/E4_READINGS.md` adds R-11.1 (each synthetic vintage is passed to the procedure as a growth series: vintage r is positions 0 to r - 1 of the series, with n_v = 49, 99, 149, 199 and 249) and R-11.2 (the stream coordinates, and the summaries, the 0.02 to 0.09 band, the adjacent-difference flag and D80 computed by the functions that E1 and E3 share). Neither reading changes the outcome on its alternative: the checks also pass on the stricter reading of validity, because the verifier found no inconsistency in any record, and on the weaker literal reading of the power condition, which asks only that each cell be reported.

## What was run

| Item | Record |
|---|---|
| Code | Research repository commit `a63c044af70d00b598f95660cf6f5209e8b62fd1` (D-054, D-055). Code identity SHA-256 `bbd66fdde9cb5cbbaa690eb4c1bb8ba17b11ea1c0c8cd0389502d10aea094bec` (identity option e1-superset, D-051): every source of E1's identity plus `src/uc_e4/*.py` and `tools/run_e4_checks.py`. E1's own identity, recorded in every manifest, is `c42cbbf35734eb4f8c12aff22384371aa4fad107ae283f6d2f5f6f93c12feef7`, the same as for the E1 and E3 checks. |
| Place | A separate clone created from origin and pinned at that commit, on the machine that ran H1, E1 and E3, with the working tree clean before and after (D-055). |
| Registration | OSF `dpxqf`; annotated tag `prereg-E4` (tag object `a119b05be7d427a544e28c20aa05575946458a76`, commit `cc28f421768a55890497c9b2e3d6121c7e05f201`); protocol SHA-256 `df7e2745b9f30dc9d9ed53526214f8d4f464f175f3180fcff3e1a92e4d03c7b9`; registration record SHA-256 `bc4f483ffe84aea9d82b4d86180ad9774b135a9ab8267434c11ab22910089645`. |
| Design | Registered mode; master seed 1927; the streams of Annex A (size: generation 5420, surrogates 5421; power: generation 5430, surrogates 5431); 200 series per cell; B = 1,000 surrogate attempts per series, each drawing a surrogate for each of the five synthetic vintages (onsets at positions 49, 99, 149, 199 and 249); kappa = 1.0, 1.2, 1.4, 1.6. |
| Execution | The prerequisites first (the preflight, 18:18:06 to 18:27:18 UTC), then the 40 parts: eight size parts of 25 series and, for each of the four power cells, eight parts of 25 series, each run once, on eight processes in parallel (one thread each, below-normal priority), with no interruption and no resumption. The driver began at 18:31:22 UTC on 1 October 2026 and finished at 21:10:55 UTC; each part took 1,822 to 1,963 s. The summaries were written at 21:10:46 and 21:10:54 UTC and the output hashes listed at 21:10:55 UTC. |
| Environment | Python 3.12.14; NumPy 2.5.3; the research lock (`requirements.lock`); Windows 10 (build 19045). |
| Outputs | 42 files, 271,003,372 bytes, kept outside the repository: forty part files and two summaries. Each file's SHA-256 is in `E4/OUTPUT_SHA256.json` and `E4/OUTPUT_SHA256.txt`. Every part holds, for each series, the fitted null and residuals of each synthetic vintage and the statistic of every surrogate attempt (Annex B). |

## Prerequisites (Annex B step 3)

They ran in the pinned clone before the first part, from 18:18:06 to 18:27:18 UTC, with the working tree clean before and after, and are kept in `preflight/` (`PREFLIGHT.json` is the record).

- **F1 (plan p. 7).** As `audit/FOUNDATIONS_REPORT.md` records it: "Passed ([M1A_REPORT.md](M1A_REPORT.md)); hand derivations of the AR(2) autocorrelation and spectral density are not recorded in this repository", a caveat that stands (D-037).
- **AT-1 to AT-4 through `uc_core.ar`.** All 5 checks passed: AT-1 least squares 1749-1924: phi (1.336, -0.650), M 0.806, period 10.57 y, half-life 3.2 y; AT-2 Yule-Walker 1749-1924: (1.326, -0.642), M 0.801, period 10.55 y; AT-3 least squares 1925-2008: (1.414, -0.762), M 0.873, period 10.02 y; AT-4 least squares on x/0.6 + 5: identical phi to 1e-6; the indicator path uc_core.rolling.max_modulus equals fit_ols on one full window.
- **Unit tests of sections 4, 5 and 7.** `tests/test_e4_table.py`, `tests/test_e4_vintage.py` and `tests/test_e4_procedure.py` (the last holds the cases of a failed observed statistic and of n_v on each side of 55): 139 passed.
- **Registered invocation.** `tools/run_e4_checks.py e4 summarize --registered` passes the code-location, gate and lock checks and stops at a missing file, as intended.
- **Output locations.** `git check-ignore` on this platform accepts all 42 planned paths (the 40 parts and the two summaries) and refuses a tracked path.
- **Whole test suite** at the pinned commit: 1245 passed, 1 skipped in 540.52s (0:09:00).
- No E4 output file existed before the parts started.

## Surrogate accounting

All 1,000 records have status ok. Across them 1,000,000 surrogate attempts were made and 1,000,000 retained; none was dropped and none failed, because "Every attempt is structurally eligible, so B′ = 1,000 whenever the p-value is valid." (section 9).

## Independent verification

The verifier `tools/verify_e4_x3.py` (version 1.0; `docs/E4_X3_VERIFICATION.md`) is a second implementation of the E4 procedure, written from the registered texts, that uses the standard library and NumPy only and imports none of the programme's code. It was run once, in full (`--all`, 6 worker processes, 151.0 s), on the stored outputs after the 40 parts, the summaries and the hash list were complete and before anything was recorded. Its report and printed output are in `verification/`. Two earlier interim passes with `--partial`, the first on a single finished part and the second on the 24 parts finished at that time (the size check and the first two power cells), found no discrepancy between the recomputed and the stored values; they covered part of the design only, ran while the remaining parts were still being written, and are not part of this record. The full run reports:

- 40 part files and 1,000 records; every coordinate of the design present once (1,000 of 1,000; 0 missing, 0 duplicated, 0 outside it).
- One fingerprint across the 40 manifests: registered mode, master seed 1927, code identity `bbd66fdde9cb...`, E1's code identity `c42cbbf35734...` (equal to E1's frozen identity), commit `a63c044`, Python 3.12.14.
- From each stored 259-value input alone: the five synthetic vintages, the observed change in each and the statistic S (largest differences 3.72e-15 and 7.42e-16), each vintage's fitted null with its residuals (largest difference 7.99e-15), and every one of the 1,000,000 surrogate attempts, regenerated from its seed coordinates (largest differences 7.52e-14 in S_b and 3.77e-13 in Delta_b). Surrogate statistics within 1e-9 of the observed S (near ties): 0 among the recomputed statistics and 0 among the stored ones.
- The stored input of each series regenerated by the H1 section 9 generator at its generation coordinates: largest difference 3.55e-15; bit-identical in 407 of 1,000 records, and equal within the float tolerance in the rest.
- Every p-value and rejection, the size and power cells with their Wilson intervals, the adjacent differences with the 1.96-SE flag and D80, recomputed from these and compared with the runner's two summaries field by field: 74 fields compared, 0 differ.
- The registered rule applied to the recomputed numbers: size and power both pass.
- Every record internally consistent (counts, S_b as the mean of its five changes, p as (1 + K)/(B' + 1)) and every input equal to its SHA-256; the part files it read have the SHA-256 of the list in `E4/OUTPUT_SHA256.json`.
- `prereg/E4.md` as read beside the verifier has SHA-256 `df7e2745b9f30dc9d9ed53526214f8d4f464f175f3180fcff3e1a92e4d03c7b9`, the registered value, and the clauses it quotes are verbatim.

Result: no problem found, and the runner's summaries and the recomputation agree.

Limits. The H1 section 9 generator fixes the random draws and the formulas but not the floating-point order of evaluation, so a regenerated input can differ from the stored one in the last bits; the verifier compares with a float tolerance (1e-12 + 1e-9 |b|) and compares the generator states before and after the draws exactly. The real-time stage (sections 4, 5 and 7: workbook structure, vintage selection, levels) is not checked here: the synthetic vintages are growth series (R-11.1). The verifier is an additional check, not part of the registered pass rule, and does not change the code identity. Both implementations were written inside the programme; neither is an external replication.

## Contents of this directory

- `E4/`: the runner's size and power summaries and the SHA-256 listing of the 42 output files.
- `stages/`: the stage markers written by the driver (`E4_parts.json`, `E4_summaries.json`, `E4_hashes.json`).
- `logs/`: the standard output and error of each part and summary step, and the driver's complete log `run_log.jsonl`.
- `preflight/`: the preflight record and the logs of the prerequisites (F1 status, AT-1 to AT-4, the unit tests, the registered invocation, the whole test suite).
- `verification/`: the verifier's report and printed output.
- `MANIFEST_SHA256.txt`: the SHA-256 of every file in this directory except this README and the manifest itself. Files here are stored byte for byte (`.gitattributes`: `audit/e4_x3/** -text`), so these hashes hold for the committed files.

## Consequences

- The code identity above is the identity that the real E4 run (X.4) must present. The registered analysis code is not to be changed before X.4: no file in the identity (`src/uc_core/*.py`, `src/uc_ext/*.py`, `tools/run_e_checks.py`, `src/uc_e4/*.py`, `tools/run_e4_checks.py` and the environment files `tools/run_validation.py`, `tools/verify_validation_runner.py`, `prereg/H1.md` and `requirements.lock`) may change, nor the lock or the interpreter (`docs/E4_X3.md`, section 5).
- The 42 output files (271 MB) stay outside git. No archive location for them is recorded yet.
- No real-time level has been read. The gate record `audit/E4_X3.json` is made from these outputs and committed before the X.4 run reads any level (section 11).
- The size cell and the four power cells are checks of the implementation and of the per-vintage fixed-date procedure on artificial series. They are not evidence about UK GDP, and with no revision noise they say nothing about the effect of revisions.
