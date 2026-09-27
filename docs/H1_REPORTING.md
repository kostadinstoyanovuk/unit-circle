# H1 reporting preparation

The reporting module assembles existing analysis results into inspectable tables and figures. It acquires no data and draws no new surrogate or interval samples. The available export command is restricted to labelled artificial development fixtures; a gated empirical export and final core note remain outstanding.

## Reporting contract

- Retain all seven prespecified comparison rows: primary, windows 32 and 48, fixed onsets, wild innovations, trend and lag-one autocorrelation. Preserve each statistic's own eligible episodes and surrogate denominator.
- Bind the analysis to the complete ordered numerical input using SHA-256 of little-endian float64 bytes. Verify that identity before assembling a report, including unavailable or failed analyses. The input hash is an integrity record, not a substitute for later source-file and date validation.
- Check individual attempt numbers, statuses, finite retained values and exceedances against summary counts. A numerical failure cannot be presented as a valid p-value; a missing result is not zero or a non-rejection.
- Preserve the observed statistic's sign independently of its upper-tail comparison. A relative rejection with a nonpositive change does not show an absolute rise in persistence.
- Retain the episode interval as a conditional diagnostic. The Branch B condition is strict, requires a valid non-rejection and available D80, and establishes neither absence nor equivalence. Official D80 is unavailable in this development export.
- Preserve merged episodes and their constituent qualifying runs. Record unavailable rolling fits explicitly rather than replacing them with zero or silently filling gaps.

## Reproduce the development output

In the locked research environment, choose a new output directory:

```text
python tools/build_h1_development_report.py --output-directory runs/h1-report-example
```

The command uses one declared artificial length-259 series, generation seed 2026092601, 24 attempted surrogates per mode and 256 episode resamples. It calls the existing H1 engineering interface with shortened counts. It is not an official size, power or white-noise acceptance experiment and cannot pass any research gate.

| Output | Contents |
|---|---|
| `analysis.json` | Complete analysis outputs, input hash and recorded random states |
| `report.json` | Tables and interpretation fields, including unavailable values and errors |
| `comparisons.csv` | All seven comparison rows, counts, p-values and conditional Monte Carlo precision |
| `episodes.csv`, `qualifying-runs.csv` | Merged episodes, contributing runs, eligibility and signed changes |
| `rolling.csv` | Complete artificial input and rolling estimates with status |
| `primary-surrogates.csv` | Every attempted primary surrogate, retained value or failure reason |
| `persistence.png`, `persistence.svg` | Rolling modulus and merged episode shading |
| `surrogates.png`, `surrogates.svg` | Retained primary distribution and signed observed statistic |
| `core-note.md` | Development interpretation and explicit scope limits |
| `manifest.json` | Fixture definition, input hash and checksums of the twelve output files |

Every table and figure identifies the development scope. Existing output directories are refused. The manifest is written last; a partially written directory is not a complete bundle and must not be treated as one. CSV blanks mean unavailable; retain the corresponding status and error fields.

## Remaining empirical requirements

G1 and G2 must pass before acquisition of the verified UK source. The subsequent empirical workflow must retain the exact source and release identity, calendar-quarter labels, validated transformations and full registered counts. It must integrate official calibration and D80 evidence, produce the final note with the remaining original core-study checks, and pass a clean-environment rebuild. This development exporter and its shortened fixture do not satisfy those requirements.
