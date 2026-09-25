# H1: OSF submission responses

Prepared 25 September 2026 for the **Secondary Data Preregistration** template. Status: **unregistered submission candidate**. These responses summarise `H1.md`; the complete attached protocol supplies the exact definitions, random streams and failure rules. Any discrepancy must be resolved before submission.

## Registration metadata

**Title:** Did UK recessions give warning? A preregistered AR(2) persistence study

**Description:** This retrospective study tests whether the mean change in fitted autoregressive persistence before UK recession onsets is unusually large relative to a prespecified constant-parameter AR(2) surrogate procedure. It uses ONS quarterly real GDP levels for 1955Q1-2019Q4, a fixed 40-quarter primary window and 1,000 attempted residual surrogates. The protocol specifies recession identification, secondary comparisons, random streams, synthetic acceptance experiments, failure handling and reporting. Registration and the required validation precede acquisition of the UK observations. The study does not claim causal tipping, real-time forecasting or established novelty.

**Contributor:** Kostadin Stoyanov

**License selection:** Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/ . The licence applies to this registration and its attached research snapshot, including the methodological source files reproduced as evidence. This is not a software-package release or a repository-wide licensing decision for separate releases. Referenced third-party material and dependencies retain their existing terms.

**Subject selections:** Economics; Statistics and Probability, where available in the live subject taxonomy.

**Tags:** autoregression; persistence; unit circle; UK GDP; recession; surrogate testing; preregistration

## Study information

### Research questions

Is the mean pre-onset change in the largest companion-root modulus of a rolling AR(2) fitted to UK quarterly real GDP growth unusually large relative to the specified fitted constant-parameter AR(2) surrogate procedure? The prespecified sensitivity analyses assess dependence on window length, onset selection, innovation resampling and indicator choice; they do not create additional primary hypotheses. See H1 sections 2, 5-7.

### Hypotheses

H1 is directional and upper-tailed. For the primary window W=40, compare the observed mean signed pre-onset change S with the registered surrogate distribution. Reject at a valid p<=0.05. This is a model-conditional comparison; rejection alone does not establish an absolute positive rise in persistence. See H1 sections 2, 6 and 10.

## Data description

### Datasets used

ONS ABMI: seasonally adjusted quarterly UK GDP in chained volume measures, obtained from the QNA publication family. Select 260 contiguous quarterly levels from 1955Q1 through 2019Q4, yielding 259 growth observations after the prescribed log difference. Select the latest completed QNA publication strictly before the verified public registration timestamp and obtain a verified release-specific file. The actual release is determined by that rule, not by inspecting GDP values. See H1 section 3.

### Data availability

The dataset is publicly available.

### Data access

The observations will be acquired only after verified public registration and completion of the required acceptance checks. Public availability does not establish that the selected vintage is accessible through a verified release-specific route. If release identity or file availability cannot be established, stop and document the issue under the protocol's amendment rule.

### Data identifiers

Series ABMI; publication family QNA. Archive metadata: https://www.ons.gov.uk/economy/grossdomesticproductgdp/timeseries/abmi/qna/previous . Exact release and file identifiers will be recorded after the registration timestamp determines the selection. An archive's supersession date is not its original release date.

### Access date

Not yet accessed or downloaded. Metadata and literature reviews occurred during protocol preparation on 24-25 September 2026. The first permitted raw-file download UTC timestamp and SHA-256 will be recorded in the data manifest after the registration and validation gates pass.

### Data collection procedures

This is secondary analysis of official national accounts, not new participant recruitment. The ONS GDP Quality and Methodology Information document describes compilation, quality and comparability: https://www.ons.gov.uk/economy/grossdomesticproductgdp/methodologies/grossdomesticproductgdpqmi . The planned sample is a fixed historical time series; it is not a random sample of recessions. Revisions, changing economic conditions, few eligible episodes and overlapping estimation windows limit interpretation. See H1 sections 3 and 10.

### Data collection procedures documentation

Use the linked ONS QMI; no observations are attached at registration.

### Codebook

The relevant metadata identifies ABMI as seasonally adjusted GDP in chained volume measures, in GBP millions. The registered protocol defines the quarterly index, growth transformation and all derived variables. The exact file structure and sample completeness will be verified at the permitted acquisition stage, without interpolation or splicing. See H1 sections 3-7 and H1_SOURCE_METADATA.md in the supporting materials.

### Codebook documentation

Use H1 sections 3-7 and `H1_SOURCE_METADATA.md` in the supporting materials.

## Variables

### Manipulated variables

None in the observational UK study. The separate, prespecified synthetic validation design changes generating coefficients at fixed positions; it is fully defined in H1 section 9 and supplies no claim about an empirical intervention.

### Manipulated variables documentation

H1 section 9 specifies synthetic initialization, coefficient multipliers, fixed positions and random streams.

### Measured variables

Input Y is quarterly real GDP. Growth is g[t]=400*(ln(Y[t])-ln(Y[t-1])). In each 40-observation window, fit an intercept-inclusive AR(2) using its final 38 observations as responses. M(t) is the largest modulus of the companion roots. Detect qualifying runs of at least two negative-growth quarters and merge nearby runs using the exact inclusive-end rule. For each eligible onset r, Delta[r]=M(r-1)-M(r-9). S is the mean of all eligible signed Delta values. There are no additional covariates. Secondary variables are defined exactly in H1 section 7.

### Missing data

Missingness has not been measured because the observations have not been acquired. Require all 260 positive, finite, correctly ordered and contiguous quarterly levels. Stop on missing, duplicate, invalid or ambiguous records. No filling, interpolation, splicing or sample substitution is allowed. See H1 section 3.

### Unit of analysis

The source unit is a calendar quarter. Rolling fits use growth windows; the primary summary averages eligible merged recession episodes. The eligible episode count m is unknown before analysis and is determined by the registered rule. If m=0, report not estimable; do not replace it with zero or change the sample. See H1 sections 3-5.

### Statistical outliers

Do not remove, trim, winsorise or select observations or episode changes by magnitude. Retain all signs and rolling estimates outside the stationary region. Invalid records and unidentified fits invoke explicit failure rules rather than outlier deletion. See H1 sections 3-6.

### Sampling weights

No additional sampling weights. Use unweighted OLS and an equally weighted mean of eligible episode changes.

## Knowledge of data

### Prior publication/dissemination

No earlier dataset-based publication has been reported in the preparation record. The project repository at https://github.com/kostadinstoyanovuk/unit-circle contains methods, synthetic engineering checks and a protocol; it does not contain an empirical H1 result. No earlier registration is known, with uncertainty retained. Any earlier work identified before submission must be disclosed.

### Prior knowledge

Kostadin Stoyanov declared on 24 September 2026 that he had not previously inspected or downloaded UK GDP data or run a UK recession analysis. During preparation, related GDP literature and official source metadata were reviewed; earlier metadata searches incidentally displayed post-2019 GDP headline snippets. No raw UK research series was acquired or analysed. Pilot numbers in the original design document are inherited claims to verify. This declaration does not assert complete ignorance of GDP information. See H1 section 1 and the retained source audits.

## Analyses

### Statistical models

Use the OLS AR(2), companion-root and episode definitions in H1 sections 4-5. Fit a strictly stable intercept-inclusive AR(2) to the full 259-observation growth sample for null generation. Center its 257 conditional residuals; keep the first observed pair fixed and generate 1,000 attempted residual-resampled paths. Refit rolling models and repeat endogenous episode selection on each path. Drop only paths without eligible episodes; numerical or fit failures invalidate the affected comparison. For B' retained paths and K exceedances including ties, p=(1+K)/(B'+1). Exact stream allocation and accounting are in sections 6-8.

### Effect size

Report S, each signed Delta, m and the number of positive changes. No economically defined minimum important effect is asserted. The registered fixed-date power study produces D80 only under its explicit validity and first-crossing rules; it is a detectability diagnostic, not an equivalence margin. See H1 sections 9-10.

### Statistical power

Official power results do not yet exist. After registration, run the exact size and power cells in H1 section 9: 200 size replicates and 200 replicates at each of four fixed power multipliers, each with 1,000 attempted surrogates. The fixed-date power proxy is distinct from the primary endogenous-onset procedure. Preserve every failure and incomplete replicate. Do not use development fixtures as registered power evidence or tune the sample, seeds or design after seeing results.

### Inference criteria

One upper-tailed primary comparison at W=40, rejecting only for valid p<=0.05. Report the signed statistic and limitations even after rejection. A valid p>0.05 is inconclusive; undefined p is a failed or not-estimable outcome. The 90% episode-resampling interval is conditional and not asserted to have calibrated coverage. Secondary p-values are prespecified sensitivity evidence. E1-E4 require separate addenda and their own Holm family; H1 and its sensitivities are outside that family. See H1 sections 6-7 and 10-11.

### Assumption violation/model non-convergence

Stop on invalid input, unidentified fits or an unstable generating null; do not project coefficients or silently drop affected windows. Preserve all attempted-draw and per-statistic failure accounting. Failed validation prevents UK acquisition until the response is documented and any methodological change is registered before data. Preserve original outcomes and log deviations. See H1 sections 3-9 and 12.

### Reliability and robustness testing

Report all registered sensitivities: W=32 and W=48; fixed observed onset dates; ordered wild signs; Kendall tau-b trend; and the lag-one autocorrelation comparator. Primary, trend and lag-one statistics share primary generated paths but have separate eligibility, failure and retention accounting. Use the prescribed 10,000-resample episode interval, deterministic random streams, software lock and retained reproducibility records. See H1 sections 7-9 and 12.

### Exploratory analysis

No additional exploratory test is specified for the primary conclusion. Any unplanned analysis must be labelled exploratory and recorded as such. Later post-2019 descriptions cannot enter H1, its fitted null or its primary episode interval. E1-E4 are separate registered extensions, not undisclosed alternatives to H1.

## Template source

The template was obtained through the [official OSF registration guide](https://help.osf.io/article/330-welcome-to-registrations) on 25 September 2026. Its [Secondary Data Preregistration template](https://docs.google.com/document/d/1p6UE2b0D0ON4XEccOCOU1pdaCTiyGLOfP-g-8Ayxylk/edit) supplies the field structure. Field availability and contributor identity must be checked in the live submission before public registration.
