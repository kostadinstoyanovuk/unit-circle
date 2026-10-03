# E2 official synthetic checks (X.3): record

Recorded on 3 October 2026. This directory keeps the summaries, logs and independent verification of the official X.3 prerequisite, size and power checks for E2, the registered addendum `prereg/E2.md` (OSF [4ncz2](https://doi.org/10.17605/OSF.IO/4NCZ2); section 11 and Annex B step 3). The checks use artificial series only. No unemployment value has been read: no MGSX file has been acquired, opened or previewed, and no E2 statistic has been computed on UK data.

## Outcome

The prerequisites, the size check and the power check ran once and in full. The registered pass conditions are met.

| Check | Result | Registered condition |
|---|---|---|
| Prerequisites | F4 as the repository records it, AT-12 through the E2 spectral-radius function, the reduction of the VAR code to H1's rolling M(t), and the unit tests of the section 4 and section 7 rules passed before the first part (below) | Annex B step 3 |
| Size | 12 rejections in 200 series: rate 0.060 (Wilson 95% interval 0.0347 to 0.1019); all 200 replicates valid | Rate between 0.02 and 0.09 inclusive, with all 200 valid: met |
| Power, validity | 200 of 200 replicates valid in each of the four cells | Every cell complete and valid: met |
| Power, adjacent differences | +0.0700, -0.0100 and +0.1950: the one fall (-0.0100) is smaller than its 1.96-SE threshold (0.0613), so no decrease is flagged | No flagged decrease: met |
| D80 | Undefined: no kappa up to 1.6 reaches 0.80 (the highest rate is 0.300) | Reported |

Power cells (200 series each, the two onsets at positions 77 and 148 of section 7):

| kappa | Rejections | Rate | Wilson 95% interval | Mean S (standard error) | Difference from previous cell | 1.96 x standard error | Decrease flag |
|---:|---:|---:|---|---|---:|---:|---|
| 1.0 | 9 | 0.045 | 0.0239 to 0.0833 | -0.00868319 (0.00557436) | n/a | n/a | n/a |
| 1.2 | 23 | 0.115 | 0.0779 to 0.1666 | 0.02255213 (0.00565755) | +0.0700 | 0.05273 | no |
| 1.4 | 21 | 0.105 | 0.0697 to 0.1552 | 0.02315428 (0.00626974) | -0.0100 | 0.06132 | no |
| 1.6 | 60 | 0.300 | 0.2407 to 0.3668 | 0.06705535 (0.00675968) | +0.1950 | 0.07641 | no |

In the size cell the mean S is -0.00130001 (standard error 0.00358006), and the Monte Carlo standard error of the rejection rate is 0.0167929.

D80 is undefined because no cell up to kappa = 1.6 reaches a rejection rate of 0.80. Section 11 anticipated this: "H1's registered power cells, with five planted onsets, reached a rejection rate of 0.235 at κ = 1.6, so H1's D80 is undefined (D-032). The official checks of E1 and E3 reached 0.115 and 0.340 at κ = 1.6, and their D80 is also undefined (D-037, D-038). With two onsets, E2's power may be lower and its D80 undefined. The Branch B diagnostic would then be unavailable. This follows from the eligible onsets and is recorded, not corrected." The Branch B diagnostic of the inconclusive branch will therefore be reported as unavailable if E2 is inconclusive, as for H1, E1, E3 and E4. The design is unchanged.

## Registered conditions applied

These are quoted from the registered files.

- Size, `prereg/E2.md` section 11: "Pass: an empirical rejection rate (raw p ≤ 0.05) between **0.02 and 0.09** inclusive, with all 200 replicates valid. Failure accounting and uncertainty reporting follow H1 §9."
- Power reporting and D80, section 11: "Cell reporting, the 1.96-SE decrease flag and **D80** (first raw crossing, linear in κ) follow H1 §9."
- Power pass, section 11: "**Pass:** all four cells valid (all 200 replicates with finite S and a valid p) and no adjacent decrease flagged (H1 §9, AT-16). D80 need not be defined."
- Cell validity and the decrease rule, `prereg/H1.md` section 9 (Cell reporting), which E2 keeps ("Every H1 rule applies unchanged unless this addendum states a replacement.", `prereg/E2.md`, opening): "A cell is complete and valid only when all 200 provide finite S and valid p." and "If any cell is invalid/incomplete or a decrease exceeds this threshold, AT-16 does not pass and G2 remains pending."
- Surrogate counting and the p-value, section 9: "Drop and count a draw only when it has no eligible episode. Failures are recorded and invalidate the comparison exactly as H1 §6. The identity attempted = retained + no_eligible + failed holds." and "Raw p-value: `p = (1+K)/(B'+1)`, with K = count(S_b ≥ S) counting ties and B′ the number of retained draws."
- Annex B step 3, the prerequisites: "AT-12 through the E2 spectral-radius function"; "a unit test that the VAR code, restricted to an AR(2) in companion form, reproduces H1's rolling M(t) to 1e−10 on a synthetic series"; "unit tests of the §4 rules on constructed files"; "unit tests of the §7 rules on constructed growth paths"; and F4 (plan p. 7). Then: "Run and record the §11 size and power cells, commit, and do not change the code again before X.4."

The sixteen readings of `docs/E2_READINGS.md`, which the owner adopted as they stand before X.3 (D-060), apply here. The power pass condition is the one that section 11 states in the quotation above, and a replicate is valid when its status is ok and S and p are finite. No replicate failed, so every fitted null was strictly stable (R4) and no window failed (R16) in any of the 1,000 records; no record depends on how either would have been read in a failure. The power onsets were read from `audit/E2_ONSETS.json` (R1: positions 77 and 148). The verifier recomputed validity under the same reading and found all 200 replicates valid in each of the five cells.

## What was run

| Item | Record |
|---|---|
| Code | Research repository commit `2a752bbf76751f37190d396afde275ae2d6bbfbf` (D-060). Code identity SHA-256 `db442259d47b6b46edf887a05633d35d23f19fd447ed23367b18d02fa55da35f` (identity option e1-superset, D-051): every source of E1's identity plus `src/uc_e2/*.py` and `tools/run_e2_checks.py`. E1's own identity, recorded in every manifest, is `c42cbbf35734eb4f8c12aff22384371aa4fad107ae283f6d2f5f6f93c12feef7`, the same as in the manifests of the E1, E3 and E4 checks. |
| Place | A separate clone created from origin and pinned at that commit, on the machine that ran H1, E1, E3 and E4, with the working tree clean before and after (the procedure of D-055). |
| Registration | OSF `4ncz2`; annotated tag `prereg-E2` (tag object `45a06e5127d65d6f08fc0d03d7cb3aa812e53836`, commit `46174d12c716d2c9ef0bfb4e7e8ed958f259e7c6`); protocol SHA-256 `7b103bb2cc314977cb30446a924d8d975850369f01ebc4819eb6da24f1e08786`; registration record SHA-256 `20bc5451b2ee9e9288708717e2c51e8c6fdddfcc27afbf64936b0ac63b32df4f`. |
| Design | Registered mode; master seed 1927; the streams of Annex A (size: generation 5220, surrogates 5221; power: generation 5230, surrogates 5231; AT-12: 2012); 200 series of 195 observations per cell; B = 1,000 surrogate attempts per series, each a joint resampling of the 193 residual vectors of the fitted VAR(2) null; W = 40; kappa = 1.0, 1.2, 1.4, 1.6, planted in the eight positions before each of the onsets at positions 77 and 148. |
| Execution | The prerequisites first (the preflight, 16:48:18 to 16:57:28 UTC), then, at the start of the driver, the prerequisite record and the data-rule tests (finished 16:58:05 UTC), then the 40 parts: eight size parts of 25 series and, for each of the four power cells, eight parts of 25 series, each run once, on eight processes in parallel (one thread each, below-normal priority), with no interruption and no resumption. The driver began at 16:57:53 UTC on 2 October 2026 and finished at 17:49:06 UTC; each part took 602 to 622 s. The summaries were written at 17:48:57 and 17:49:05 UTC and the output hashes listed at 17:49:06 UTC. |
| Environment | Python 3.12.14; NumPy 2.5.3; the research lock (`requirements.lock`); Windows 10 (build 19045). |
| Outputs | 45 files, 248,168,072 bytes, kept outside the repository: forty part files, the prerequisite record, two summaries, the plan and the log of the data-rule tests. Each file's SHA-256 is in `E2/OUTPUT_SHA256.json` and `E2/OUTPUT_SHA256.txt`. Every part holds, for each series, the input, the fitted null with its residuals, the window fits and the statistic of every surrogate attempt (Annex B). |

## Prerequisites (Annex B step 3)

They ran in the pinned clone before the first part: the preflight from 16:48:18 to 16:57:28 UTC, with the working tree clean before and after, and the prerequisite record and the data-rule tests at the start of the driver. They are kept in `preflight/` (`PREFLIGHT.json` is the record) and in `E2/x3_prerequisite.jsonl`.

- **F4 (plan p. 7).** As the repository records it (`DECISIONS.md` D-019 and `STATUS.md`; `preflight/f4_status.txt`): "Passed: diagonal VAR(1) exact (error 0); AR(2) companion against root modulus, largest error 4.9e-15." It is not run again here (R15).
- **AT-12 through the E2 spectral-radius function.** 100,000 draws of each kind with AT-12's own seed and stream (1927, 2012): the diagonal VAR(1) is exact (largest error 0.0) and the AR(2) companion agrees with the root modulus to 4.88e-15; 0 draws skipped.
- **Reduction to H1's rolling M(t).** The VAR code, restricted to an AR(2) in companion form, reproduces H1's rolling M(t) at W = 32, 40 and 48 on the H1-design series of stream 5220, cell 1, replicate 0 (a coordinate that the size check does not use), in 228, 220 and 212 fitted windows: largest difference 2.22e-16 against the tolerance 1e-10.
- **Unit tests of the section 4 and section 7 rules** on constructed inputs: `tests/test_e2_data_rules.py` (28 passed; `E2/x3_data_rules_tests.txt`) and, with `tests/test_e2_onsets.py`, 30 passed in the preflight.
- **Onsets record.** `audit/E2_ONSETS.json` is committed, unchanged and lists positions 77 and 148 (m_E2 = 2).
- **Registered invocation.** `tools/run_e2_checks.py e2 summarize --registered` passes the code-location, gate and lock checks and stops at a missing file, as intended.
- **Output locations.** `git check-ignore` on this platform accepts all 45 planned paths (the 40 parts, the prerequisite record, the two summaries, the plan and the test log) and refuses a tracked path.
- **Whole test suite** at the pinned commit: 1348 passed, 1 skipped in 529.77s (0:08:49).
- No E2 output file existed before the prerequisite step and the parts started.

## Surrogate accounting

All 1,000 records have status ok. Across them 1,000,000 surrogate attempts were made and 999,831 retained; none failed. In the size check, 200,000 attempts gave 199,831 retained draws and 169 dropped because the surrogate g had no eligible episode (section 9: "Drop and count a draw only when it has no eligible episode. Failures are recorded and invalidate the comparison exactly as H1 §6. The identity attempted = retained + no_eligible + failed holds."), in 58 of the 200 series (the smallest B′ is 984). In the power check all 800,000 attempts were retained, because the surrogate statistic is taken at the two imposed positions, which are structurally eligible (section 11). Every p-value is (1 + K)/(B′ + 1) with B′ the number retained.

## Independent verification

The verifier `tools/verify_e2_x3.py` (version 1.0; `docs/E2_X3_VERIFICATION.md`) is a second implementation of the E2 procedure, written from the registered texts, that uses the standard library and NumPy only and imports none of the programme's code. It was run in full (`--all`, 12 worker processes, 259.5 s) on the stored outputs, from the committed copy in the registered clone, after the 40 parts, the summaries and the hash list were complete and before anything was recorded. Its report and printed output are in `verification/`. An earlier full run of the same program, made before it was committed, reported no problem and the same figures; it is not part of this record. The full run reports:

- 40 part files and 1,000 records; every coordinate of the design present once (1,000 of 1,000; 0 missing, 0 duplicated, 0 outside it).
- One fingerprint across the 40 manifests: registered mode, master seed 1927, code identity `db442259d47b...`, E1's code identity `c42cbbf35734...` (equal to E1's frozen identity), commit `2a752bb`, Python 3.12.14.
- From each stored 195 x 2 input alone: the rolling VAR(2) fit of each of the 156 windows and its spectral radius, which the record retains (largest difference 4.96e-14); the pre-onset change at each eligible onset and the statistic S (largest differences 1.55e-14 and 4.11e-15); the fitted null with its residuals (largest difference 3.02e-14); and every one of the 1,000,000 surrogate attempts, regenerated from its seed coordinates (largest differences 5.12e-13 in S_b and 1.03e-12 in Delta_b). Surrogate statistics within 1e-9 of the observed S (near ties): 1 among the recomputed statistics and 1 among the stored ones. The one near tie is in power cell 0 (kappa 1.0), replicate 108, attempt 917, where the surrogate statistic exceeds the observed S by 7.50e-10. Both implementations count it, since K counts S_b at or above S, and agree on K; the gap is about 1,500 times the largest difference between the two implementations in any surrogate statistic (5.12e-13), so the classification is not a matter of rounding. In that replicate K = 482 and p = 0.4825; the replicate's rejection status would be the same if this attempt were not counted, so no cell count depends on it.
- The stored input of each series regenerated by the section 11 generator at its generation coordinates: largest difference 0.00e+00; bit-identical in all 1,000 records, with the generator states before and after the draws equal.
- Every p-value and rejection, the size and power cells with their Wilson intervals, the adjacent differences with the 1.96-SE flag and D80, recomputed from these and compared with the runner's two summaries field by field: 164 fields compared, 0 differ.
- The prerequisite record: AT-12 recomputed through the spectral-radius function (the draws and the skip rule of `uc_core.linalg.at12` written out again; largest errors 0.0 and 4.88e-15) and the reduction to H1's AR(2) recomputed on the regenerated fixture series (largest difference 1.33e-15); both pass. F4 and the unit tests that the record cites are taken from the research record and are not run again.
- The registered rule applied to the recomputed numbers: size and power both pass.
- Every record internally consistent (counts, S_b as the mean of its changes at the eligible onsets, p as (1 + K)/(B′ + 1)) and every input equal to its SHA-256; the part files it read have the SHA-256 of the list in `E2/OUTPUT_SHA256.json`.
- `prereg/E2.md` and `prereg/H1.md` as read beside the verifier have SHA-256 `7b103bb2cc314977cb30446a924d8d975850369f01ebc4819eb6da24f1e08786` and `be447b725317c3b857eb1888dbcedd127d057cd5e0e586a0b2de87e24b182ba4`, the registered values, and the clauses it quotes are verbatim.

Result: no problem found (one note, the near tie), and the runner's summaries and the recomputation agree.

Limits. The section 11 generator fixes the random draws and the formulas but not the floating-point order of evaluation, so a regenerated input can differ from the stored one in the last bits; the verifier compares with a float tolerance (1e-12 + 1e-9 |b|) and compares the generator states before and after the draws exactly. The draws of AT-12 are those of `uc_core.linalg.at12`, which Annex B names and does not print, written out again from that rule. The data stages (X.2 and X.4) are not checked here. The verifier is an additional check, not part of the registered pass rule, and is not among the sources of the code identity. Both implementations were written inside the programme; neither is an external replication.

## Contents of this directory

- `E2/`: the runner's size and power summaries, the prerequisite record, the plan, the log of the data-rule tests and the SHA-256 listing of the 45 output files.
- `stages/`: the stage markers written by the driver (`E2_prerequisite.json`, `E2_parts.json`, `E2_summaries.json`, `E2_hashes.json`).
- `logs/`: the standard output and error of each step and part, and the driver's complete log `run_log.jsonl`.
- `preflight/`: the preflight record and the logs of the prerequisites (F4 status, the unit tests, the registered invocation, the whole test suite at the pinned commit), and `test_full_suite.txt`, the whole-suite run made before the E2 code was published (D-060).
- `verification/`: the verifier's report and printed output.
- `MANIFEST_SHA256.txt`: the SHA-256 of every file in this directory except this README and the manifest itself. Files here are stored byte for byte (`.gitattributes`: `audit/e2_x3/** -text`), so these hashes hold for the committed files.

## Consequences

- The code identity above is the identity that the real E2 run (X.4) must present. The registered analysis code is not to be changed before X.4 (Annex B: "do not change the code again before X.4"): no file in the identity (`src/uc_core/*.py`, `src/uc_ext/*.py`, `tools/run_e_checks.py`, `src/uc_e2/*.py`, `tools/run_e2_checks.py` and the environment files `tools/run_validation.py`, `tools/verify_validation_runner.py`, `prereg/H1.md` and `requirements.lock`) may change, nor the lock or the interpreter (`docs/E2_X3.md`).
- The 45 output files (248 MB) stay outside git.
- No MGSX value has been read. The gate record `audit/E2_X3.json` is made from these outputs and committed before the MGSX file is downloaded (Annex B: "X.3 comes before the download of X.2").
- The size cell and the four power cells are checks of the implementation and of the procedure on artificial series. They are not evidence about UK output or unemployment, and section 11 states a limit of the size cells: "The size cells are analysed with the episodes each synthetic series has, not a fixed two, so they say little about the calibration of a two-episode statistic."
