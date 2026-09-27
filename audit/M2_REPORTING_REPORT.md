# M2 reporting preparation

27 September 2026. **The development reporting checkpoint is complete. M2, G1 and G2 remain open.** No official validation cells or UK observations informed this work.

## Outputs and integrity

The reporting layer exports all seven prespecified comparisons, episode and run tables, the complete artificial input and rolling path, and every attempted primary surrogate. It produces two figures in PNG and SVG, complete numerical JSON, a development note and a checksum manifest. The [reporting contract](../docs/H1_REPORTING.md) defines reproduction and scope.

Review identified and corrected two integrity gaps before publication. Analysis results now carry a hash of the complete numerical input, so changing observations after the final onset cannot pair stale inference with a new series. The reporter also reconciles every attempt's number, status and statistic with the aggregate counts, exceedances, grid spacing and p-value. A changed or failed attempt cannot silently retain a successful summary.

The interpretation preserves signed changes independently of surrogate rejection. All failed or unavailable rows remain present without inferential p-values. Conditional episode intervals and the strict Branch B condition do not establish absence or equivalence. A failed rolling path is explicitly unavailable, not filled or set to zero.

## Verification

The full research suite passes **273 tests**, including **37 reporting tests**. Tests cover altered inputs, including changes after the final onset, missing input identity, unavailable/failed analyses, corrupted attempt records, correct failure accounting, signed interpretations, strict diagnostic boundaries, all seven rows, episode merging, complete labelled exports, checksums and refusal to overwrite an existing output directory.

Three additional bounded artificial fixtures compare the current H1 assembly with the actual H1 source retained in the submitted supporting ZIP: ordinary comparisons, no eligible episodes and a rolling-fit failure. All scientific outputs and recorded random states match exactly after excluding the newly added input hash. The seven scientific dependencies used by that module remain byte-identical to the submitted snapshot. These checks support the limited record-integrity change; they do not claim universal equivalence or statistical calibration.

The separate length-259 development fixture uses generation seed 2026092601, 24 surrogate attempts per mode and 256 episode resamples. All seven comparison rows, 259 input rows, 24 primary attempt rows and twelve output checksums were verified. Both PNG figures were visually checked for legible labels, complete content and visible artificial-data identification. [h1_reporting_verification.json](h1_reporting_verification.json) records source, environment, method-comparison and output identities. Artifact metadata and output hashes are preserved with the checkpoint; the reproduction command creates a new bundle.

## Scope retained

The analysis adds input-identity metadata; its estimators, episode rules, random streams and scientific calculations are unchanged. The five submitted files and protocol remain unchanged and separately identified. No registered method or acceptance criterion was relaxed.

The current command exports development fixtures only. The empirical workflow still requires verified public registration, completed acceptance checks, verified source and calendar identities, full registered counts, official calibration integration, the remaining core-study checks and a reproducible final note. The [programme review](PROGRAMME_REVIEW_2026-09-27.md) records those remaining obligations. This checkpoint closes reporting preparation, not M2 or any research gate.
