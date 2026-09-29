# E1 official synthetic checks (X.3): record

Recorded on 29 September 2026. This directory keeps the outputs, logs and independent verification of the official X.3 size and power checks for E1, the registered addendum `prereg/E1.md` (OSF [mjg9w](https://doi.org/10.17605/OSF.IO/MJG9W); section 11 and Annex B step 3). The checks use artificial series only. No E1 observation had been acquired when they ran, and none has been acquired since.

## Outcome

The checks ran once and in full. The registered pass conditions are met.

| Check | Result | Registered condition |
|---|---|---|
| Size | 13 rejections in 200 series: rate 0.065 (Wilson 95% interval 0.0384 to 0.1080); all 200 replicates valid | Rate between 0.02 and 0.09 inclusive, all 200 valid: met |
| Power, validity | 200 of 200 replicates valid in each of the four cells | Every cell complete and valid: met |
| Power, adjacent differences | +0.025, +0.010 and +0.035: all three are increases, so no decrease exceeds its 1.96-SE threshold | No flagged decrease: met |
| D80 | Undefined: no kappa up to 1.6 reaches 0.80 | Reported; anticipated in section 11 (below) |

Power cells (200 series each; the planted largest modulus is 0.5, 0.6, 0.7 and 0.8):

| kappa | Rejections | Rate | Wilson 95% interval | Mean S (standard error) | Difference from previous cell | 1.96 x standard error | Decrease flag |
|---:|---:|---:|---|---|---:|---:|---|
| 1.0 | 9 | 0.045 | 0.0239 to 0.0833 | -0.00075506 (0.00282982) | n/a | n/a | n/a |
| 1.2 | 14 | 0.070 | 0.0422 to 0.1141 | 0.00347735 (0.00326552) | +0.0250 | 0.04556 | no |
| 1.4 | 16 | 0.080 | 0.0498 to 0.1260 | 0.00816908 (0.00272928) | +0.0100 | 0.05162 | no |
| 1.6 | 23 | 0.115 | 0.0779 to 0.1666 | 0.01702273 (0.00316282) | +0.0350 | 0.05804 | no |

In the size cell the mean S is -0.00473256 (standard error 0.00129028), and the Monte Carlo standard error of the rejection rate is 0.017432.

D80 is undefined because no cell up to kappa = 1.6 reaches a rejection rate of 0.80 (the highest is 0.115). Section 11 anticipated this: "Only 2 of the 30 observations in the M(r−1) window carry the planted signal, against 8 of 40 in H1, so power at κ ≤ 1.6 may be low and D80 may be undefined. If so, the Branch B diagnostic is unavailable. This follows from the plan's two-year horizon and is not a reason to change the design after seeing X.3 results (D-023, E1-5)." The design is unchanged, and the inconclusive branch of section 11 will carry no Branch B diagnostic.

## Registered conditions applied

These are quoted from the registered files.

- Size, `prereg/E1.md` section 11: "Pass: an empirical rejection rate (raw p ≤ 0.05) between **0.02 and 0.09 inclusive**, with all 200 replicates valid. Failure accounting and uncertainty reporting follow H1 §9."
- Power, `prereg/E1.md` section 11: "Report every cell as H1 §9: rates, Wilson intervals, adjacent differences with the 1.96-SE decrease flag, mean S and its standard error."
- Cell validity and the decrease rule, `prereg/H1.md` section 9 (Cell reporting), which E1 keeps: "Every H1 rule applies unchanged unless this addendum states a replacement" (`prereg/E1.md`, opening). "A cell is complete and valid only when all 200 provide finite S and valid p." and "If any cell is invalid/incomplete or a decrease exceeds this threshold, AT-16 does not pass and G2 remains pending."
- D80, `prereg/E1.md` section 11: "As H1 §9: the first raw crossing of 0.80, interpolated linearly in κ; undefined if any cell is invalid or no κ ≤ 1.6 reaches 0.80."
- Annex B step 3: "Run and record the §11 size and power cells, commit, and do not touch the code again before X.4."

Two readings were adopted to apply them. (1) The power pass condition is H1 section 9's AT-16 condition, carried into E1 by the sentence quoted above. On the literal alternative, that section 11 asks only that each power cell be reported, the outcome is the same. (2) A replicate is valid when its status is ok and S and p are finite. The stricter reading, which also requires every per-record consistency check to hold, gives the same counts.

## What was run

| Item | Record |
|---|---|
| Code | Research repository commit `6ea02456244efa7c58ac8cb1be682a2b206597c5` (D-036). Code identity SHA-256 `c42cbbf35734eb4f8c12aff22384371aa4fad107ae283f6d2f5f6f93c12feef7`, computed by `tools/run_e_checks.py` over every source file of `uc_ext` and `uc_core`, the runner itself and the environment identity. |
| Place | A separate clone pinned at that commit, working tree clean before and after (D-036). |
| Registration | OSF `mjg9w`; annotated tag `prereg-E1` (tag object `bac7d28339ae1624e2c83ccb3bfcf6bfa61bb6b6`, commit `5a26bfc8b4af3486cb17e758102f7efc59301379`); protocol SHA-256 `d0d7b0859593b301a0af8bd9b5d48f92bcd3aef27082d9d7b6c4cf2d4e26e4fd`; registration record SHA-256 `030841c5dd31efd622c7550bd3733a87e4d64c4c186fa008868cfd9d4e93301f`. |
| Design | Registered mode; master seed 1927; streams 5120 and 5121 (size) and 5130 and 5131 (power); 200 series per cell; B = 1,000 attempted surrogate draws per series; kappa = 1.0, 1.2, 1.4, 1.6. |
| Execution | Sixteen parts: eight size parts of 25 series and eight power parts of 100 series (four cells, two halves each). Each part ran once, on eight processes in parallel, with no interruption and no resumption. |
| Environment | Python 3.12.14; NumPy 2.5.3; the research lock (`requirements.lock`); Windows 10 (build 19045). |
| Times (UTC, 29 September 2026) | Start 03:38:46; all parts finished 04:58:18; summaries written 04:58:34; output hashes listed 04:58:35. |
| Outputs | Eighteen files (sixteen part files and two summaries), 449,403,073 bytes, kept outside the repository. Each file's SHA-256 is in `E1/OUTPUT_SHA256.json` and `E1/OUTPUT_SHA256.txt`. |

## Prerequisites (Annex B step 3)

The three prerequisites were run on the same commit before the size and power cells (03:35 to 03:38 UTC; record in `preflight/PREFLIGHT.json`).

- **F1 (plan p. 7).** `audit/FOUNDATIONS_REPORT.md` records F1 as "Passed ([M1A_REPORT.md](M1A_REPORT.md)); hand derivations of the AR(2) autocorrelation and spectral density are not recorded in this repository". That caveat stands.
- **AT-1 to AT-4 through `uc_core.ar`: passed.** AT-1, least squares 1749-1924: phi (1.336, -0.650), M 0.806, period 10.57 years, half-life 3.2 years. AT-2, Yule-Walker 1749-1924: (1.326, -0.642), M 0.801, period 10.55 years. AT-3, least squares 1925-2008: (1.414, -0.762), M 0.873, period 10.02 years. AT-4, least squares on x/0.6 + 5: identical phi to the 1e-6 tolerance (largest difference 4.4e-16). In addition, E1's indicator path `uc_core.rolling.max_modulus` equals `fit_ols` on one full window (M = 0.8061348947801175 in both).
- **Section 7 unit test.** The four E test files (`tests/test_e_common.py`, `tests/test_e1.py`, `tests/test_e3.py`, `tests/test_e_runner.py`), which include the section 7 unit test on constructed runs, passed: 99 passed in 147.61 s.
- Also recorded there, for the E3 checks: `tests/test_foundations.py` (F2), 10 passed; `tests/test_audit_baseline.py`, 12 passed; the environment identity under the research lock; and the output-location check with this platform's paths.

## Independent verification

`tools/verify_e_x3.py` (version 1.1, SHA-256 `e58c4f98ad08f60d22f1558815751efce6100c5c24af1faefaa08836d1936fe3`) is a second implementation. It uses the standard library and NumPy only and imports nothing from the programme's own packages. Its own tests are in `tests/test_verify_e_x3.py` (26 passed). It was run read-only on the stored outputs; its report and printed output are in `verification/`. It reports:

- 16 part files and 1,000 records; every coordinate of the design present once, none missing, duplicated or outside it; each part written by a single uninterrupted run.
- The p-value recomputed from the stored surrogate statistics for all 1,000 records; the observed S recomputed from the stored input series (largest difference 7.2e-15); the fitted null recomputed (largest difference 2.4e-15); no record with a problem; 1,000 retained draws in every record.
- One fingerprint across the sixteen manifests: commit, Python 3.12.14, code identity above, registered mode, seed 1927.
- The size and power cells, Wilson intervals, adjacent differences, flags and D80 recomputed and equal to the runner's (32 and 92 fields compared, none differs).
- All 18 output files match their recorded SHA-256 and size; no file is present but unlisted.
- 16 of 16 quotations of registered wording found verbatim in the registered files.

Result: no problem found, and the runner's summaries and the recomputation agree.

Limits. The verifier takes the stored surrogate statistics and stored input series as data. It does not regenerate them from the registered seed, so it does not by itself test random-number generation, series construction or surrogate resampling. The runner's summary step re-verifies every saved record before combining the parts (D-036), and a replay from the seed in the manner of the H1 validation review (`audit/G2_REVIEW.md`) remains possible; none has been done for these checks.

## Contents of this directory

- `E1/`: the runner's size and power summaries and the SHA-256 listing of the eighteen output files.
- `preflight/`: the prerequisite record (`PREFLIGHT.json`), the test logs and the gate output for both extensions.
- `stages/`: the stage markers written for E1 (`E1_parts.json`, `E1_summaries.json`, `E1_hashes.json`).
- `logs/`: the standard output and error of each E1 step, and a snapshot of the driver's log `run_log.jsonl` taken at 2026-09-29T11:36:27Z (it also holds the early events of the E3 checks, which were then running).
- `verification/`: the independent verification report and its printed output.
- `MANIFEST_SHA256.txt`: the SHA-256 of every file in this directory except this README and the manifest itself. Files here are stored byte for byte (`.gitattributes`: `audit/e1_x3/** -text`), so these hashes hold for the committed files.

## Consequences

- The code identity above is the identity that the real E1 run (X.4) must present. The registered analysis code is not to be changed before X.4.
- The eighteen output files stay outside git. No archive location for them is recorded yet.
- E1 X.2 (acquisition of the millennium workbook) has not begun, and no E1 value has been read.
- The size cell and the four power cells are checks of the implementation and the surrogate procedure on artificial series. They are not evidence about UK GDP.
