# E2: OSF submission responses

Prepared on 29 September 2026 and revised on 30 September and 1 October 2026 for OSF's **Secondary Data Preregistration** template, the template used for H1 (`wcnbz`), E1 (`mjg9w`), E3 (`rhzsm`) and E4 (`dpxqf`). Status: **unregistered submission candidate**. The responses follow the structure of `prereg/H1_OSF_responses.md` and summarise `prereg/E2.md`. The complete attached addendum supplies the exact definitions, random streams and failure rules; where a response and the addendum differ, the addendum governs, and the difference must be resolved before submission.

Field keys in brackets (for example [72-2]) are those recorded for this template in the H1 registration evidence (`audit/registration-evidence/2026-09-27/osf-schema-responses.json`). Their presence in the live form must be checked at submission. Entries marked *[to be completed at submission]* need facts that exist only at submission.

## Registration metadata

**Title:** E2: Did UK recessions give warning in the joint dynamics of output and unemployment? A registered extension of OSF wcnbz with a VAR(2) of GDP growth and the change in the unemployment rate, 1971-2019

**Description:** This registration is extension E2 of the registered H1 protocol, OSF wcnbz (DOI 10.17605/OSF.IO/WCNBZ), and a member of its extension family E1-E4 (with E1, OSF mjg9w; E3, OSF rhzsm; and E4, OSF dpxqf). It tests whether the mean change, before UK recession onsets, in the spectral radius of a rolling VAR(2) of quarterly GDP growth and the change in the unemployment rate is unusually large relative to a prespecified fitted constant-parameter VAR(2) surrogate procedure that resamples residual vectors jointly. It uses the ABMI file already registered and analysed under H1 and the ONS unemployment rate MGSX (dataset LMS), 1971Q1-2019Q4, a 40-quarter primary window and 1,000 attempted surrogates. Recession onsets come from GDP growth, as in H1; the two eligible onsets, 1990Q3 and 2008Q2, are listed in the addendum by a rule fixed before H1 was run. The attached addendum states only its replacements of the H1 rules; every other H1 rule applies unchanged. The decision uses Holm-adjusted p-values within E1-E4. Registration precedes acquisition of the unemployment data; the results of H1 and E3 are known at registration. The study does not claim causal tipping, real-time forecasting or established novelty.

**Contributor:** Kostadin Stoyanov

**License selection:** Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/ , as for H1, E1 and E3. The licence applies to this registration and its attached files. Referenced third-party material and data retain their existing terms.

**Subject selections:** Economics; Statistics and Probability, as for H1.

**Tags:** autoregression; persistence; unit circle; UK GDP; unemployment; vector autoregression; recession; surrogate testing; preregistration

**Link to H1:** cited in the description (a separate registration per research-repo D-023, G-6, as for E1 and E3).

## Study information

### Research questions [72-2]

Before UK recession onsets from 1983Q2 to 2019Q4, is the mean pre-onset change in the spectral radius of the 4x4 companion matrix of a rolling VAR(2), fitted to quarterly UK real GDP growth and the quarterly change in the unemployment rate, unusually large relative to the specified fitted constant-parameter VAR(2) surrogate procedure? The prespecified sensitivity analyses assess dependence on window length, onset selection, innovation resampling and indicator choice; they do not create additional primary hypotheses. This is extension E2 of H1 (OSF wcnbz). See E2 sections 2 and 5-10.

### Hypotheses [72-4]

E2 is directional and upper-tailed. For the primary window W=40, compare the observed mean signed pre-onset change S over the eligible episodes with the registered distribution from 1,000 attempted joint residual-vector surrogates. E2 rejects only when its Holm-adjusted p<=0.05 within the extension family E1-E4, computed at family closure; its raw p is reported when E2 is frozen and labelled as not family-adjusted. This is a model-conditional comparison; rejection alone does not establish an absolute positive rise in persistence. See E2 sections 2, 9, 10 and 11.

## Data description

### Datasets used [72-7]

(1) ONS ABMI, seasonally adjusted quarterly UK GDP in chained volume measures: the file registered and acquired under H1 (QNA, released 30 June 2026; SHA-256 b97f9b0f5d9c94aa711804a43752f83d3d2f0fcf7062f2eff8dbd6f236221262), with no further GDP download. Select the 196 levels 1971Q1-2019Q4. (2) ONS MGSX, "Unemployment rate (aged 16 and over, seasonally adjusted): %", in the dataset Labour market statistics time series (LMS): the 196 quarterly values 1971Q1-2019Q4. Select the latest LMS publication released strictly before the verified public-registration timestamp of this addendum (the registry's recorded approval) and the MGSX file that belongs to it, verified by the file's own release-date record. The actual release is determined by that rule, not by inspecting unemployment values. These give 195 observations of growth and the change in the unemployment rate, 1971Q2-2019Q4. See E2 section 4.

### Data availability [72-9]

The dataset is publicly available

### Data access [72-14]

The ABMI file was acquired under H1 and is held, with its hash, in the research repository. The MGSX observations will be acquired only after verified public registration of this addendum and the pushed prereg-E2 tag, and after the official synthetic checks of section 11 (X.3) have passed and are recorded. The selected LMS publication is identified from ONS release-calendar metadata only, without opening any page or file that shows unemployment values; the calendar gives release times in UK local time, and they are converted to UTC before they are compared with the registration timestamp. Before any value is read, the file's header and row labels are checked: series MGSX, dataset LMS, the release date of the selected publication, and the quarterly labels 1971 Q1-2019 Q4. If release identity or file availability cannot be established, stop and document the issue under the addendum's amendment rule. See E2 section 4 and Annex B.

### Data identifiers [72-16]

Series MGSX; dataset LMS. Archive metadata: https://www.ons.gov.uk/employmentandlabourmarket/peoplenotinwork/unemployment/timeseries/mgsx/lms/previous . Series ABMI; publication family QNA; the H1-registered file is data/raw/ABMI_QNA.csv in https://github.com/kostadinstoyanovuk/unit-circle , recorded in DATA_MANIFEST.csv. The exact LMS release and MGSX file identifiers will be recorded after the registration timestamp determines the selection. An archive's supersession date is not its original release date.

### Access date [72-18]

MGSX: not yet accessed or downloaded. Metadata pages were read during preparation on 28 September 2026 (prereg/E_SOURCE_METADATA.md). ABMI: downloaded once under H1 on 28 September 2026 at 22:20:50 UTC. The MGSX download UTC timestamp and SHA-256 will be recorded in the data manifest after registration.

### Data collection procedures [72-20]

This is secondary analysis of official national accounts and Labour Force Survey statistics, not new participant recruitment. ONS documentation states that UK unemployment rates are available from 1971, that the Labour Force Survey was biennial from 1973 to 1983 and annual from 1984 to 1991, and that quarterly sampling has run since spring 1992. Quarterly unemployment values before 1992 therefore cannot all be direct quarterly survey estimates; how ONS constructed them is not established and is disclosed as a limitation, and the file's construction notes will be copied into the manifest. Both windows of the 1990Q3 episode lie wholly before 1992, so that episode's change rests entirely on the values whose construction is unverified; both windows of the 2008Q2 episode lie after quarterly sampling began (E2 section 4). The sample is a fixed historical time series, not a random sample of recessions. Few eligible episodes (two), revisions and overlapping estimation windows limit interpretation. See E2 sections 4 and 7.

### Data collection procedures documentation [72-22]

A file field, left empty for H1. Use prereg/E_SOURCE_METADATA.md (attached under 72-26), which records the ONS documentation pages read and quoted, including the Labour Force Survey methodology page and the guide to labour market statistics. No observations are attached.

### Codebook [72-24]

MGSX is the seasonally adjusted unemployment rate of people aged 16 and over, in per cent, in the LMS dataset (from the ONS series archive and dataset pages; not checked against a data file). ABMI is seasonally adjusted GDP in chained volume measures, in GBP millions. The addendum defines the quarterly index, the growth and change transformations and all derived variables. The file's structure, its quarterly rows and the sample's completeness will be verified at the permitted acquisition stage, without interpolation or splicing. See E2 sections 4-8 and prereg/E_SOURCE_METADATA.md.

### Codebook documentation [72-26]

A file field. As for E1 and E3, attach E2.md (the addendum) and E_SOURCE_METADATA.md (the source metadata record, byte-identical to the file attached to E1 and E3; SHA-256 44625af43da8aa8d709a172655a749f1c75972b2c4db9d0356dee906a3e4dc08).

## Variables

### Manipulated variables [72-29]

None in the observational UK study. The separate, prespecified synthetic validation design generates a VAR(2) made of two copies of H1's AR(2) with innovation correlation -0.5 and changes its generating coefficients at the two fixed positions of the eligible onsets; it is fully defined in E2 section 11 and supplies no claim about an empirical intervention.

### Manipulated variables documentation [72-31]

A file field, left empty for H1. E2 section 11 specifies the synthetic generating process, its initialisation, the coefficient multipliers, the fixed positions and the random streams.

### Measured variables [72-33]

Inputs are quarterly real GDP Y and the quarterly unemployment rate u. Growth is g[t]=400*(ln(Y[t])-ln(Y[t-1])) and du[t]=u[t]-u[t-1], giving X[t]=(g[t],du[t]) for 1971Q2-2019Q4. In each 40-observation window, fit an intercept-inclusive VAR(2) by OLS using its final 38 observations as responses. M(t) is the spectral radius of the 4x4 companion matrix. Detect qualifying runs of at least two negative-growth quarters in g and merge nearby runs by the H1 rule. For each eligible onset r, Delta[r]=M(r-1)-M(r-9). S is the mean of the eligible signed Delta values. There are no additional covariates. Secondary variables are defined exactly in E2 section 10.

### Missing data [72-35]

The unemployment observations have not been acquired, so their missingness has not been measured. Require all 196 GDP levels positive and finite and all 196 quarterly unemployment values finite and in [0,100], correctly ordered and contiguous, 1971Q1-2019Q4. Stop on missing, duplicate, invalid or ambiguous records. A quarterly row is one whose label is a four-digit year, a space, Q and a digit from 1 to 4; other rows are ignored. A value is present when its field is a number in decimal notation; an empty field or a field without a digit is missing, and a field with a digit that is not such a number stops the analysis for an amendment. No filling, interpolation, splicing or sample substitution is allowed. See E2 section 4.

### Unit of analysis [72-37]

The source unit is a calendar quarter. Rolling fits use windows of observation vectors; the primary summary averages eligible merged recession episodes. The episodes are determined by GDP alone, and applying the registered rule to the H1-registered file gives m=2 eligible episodes, with onsets 1990Q3 and 2008Q2; a non-finite modulus at either onset fails the comparison rather than removing the episode. See E2 sections 5-8.

### Statistical outliers [72-39]

Do not remove, trim, winsorise or select observations or episode changes by magnitude. Retain all signs and rolling estimates outside the stable region. Invalid records and unidentified fits invoke explicit failure rules rather than outlier deletion. See E2 sections 4, 6 and 9.

### Sampling weights [72-41]

No additional sampling weights. Use unweighted OLS and an equally weighted mean of eligible episode changes.

## Knowledge of data

### Prior publication/dissemination [72-44]

The GDP series and the H1 analysis of it are public in the project repository (https://github.com/kostadinstoyanovuk/unit-circle): H1 was run once on 28 September 2026 and frozen (tag h1-frozen) with an inconclusive result, S=-0.0933 over four eligible episodes, raw p=0.928. The E2 eligible onsets, 1990Q3 and 2008Q2, are H1 episodes, and H1's AR(2) changes at them are public (-0.2034 and +0.0662). Because the lag-one comparator of E2 depends on GDP alone and uses H1's windows at those onsets, its observed value is determined by public H1 data; it has not been computed. E3 was run once on the same file and frozen on 29 September 2026 (D-042; tag e3-frozen): inconclusive, raw p=0.524, not family-adjusted; its changes at the two E2 onsets (+0.0020 and -0.0011) are public and are E3 quantities. E1 was run once and frozen on 30 September 2026 (D-049; tag e1-frozen): inconclusive, raw p=0.1349, not family-adjusted. The E1 workbook, which holds UK employment and unemployment series, was acquired once on 29 September 2026; apart from the year cells and the levels of one real-GDP column that E1's registered extraction and run read on 30 September 2026, it has not been read beyond sheet names, titles and header text. E4 was registered on 30 September 2026 (OSF dpxqf); its official synthetic checks are recorded (D-057) and it has not been run on real data. No analysis of the unemployment series and no VAR analysis of UK data exists in the programme. No earlier registration of E2 is known.

### Prior knowledge [72-46]

Every E2 choice was adopted on 28 September 2026 (research-repo DECISIONS.md D-023), before the ABMI file was acquired and before H1 was run; after H1 was frozen, only the list of eligible onsets and the power positions were added, by the rule fixed then. The H1 result is known at registration, as stated above. No MGSX observation has been acquired, opened or previewed in the programme, and no file or page that shows an MGSX value has been opened. The one acquired file that holds UK employment and unemployment series is the Bank of England workbook acquired for E1 on 29 September 2026 (SHA-256 4c23dd392a498691eac92659aec283fb43f28118bd80511dc87fc595974195eb; DATA_MANIFEST.csv; kept out of git); apart from the year cells and the levels of one real-GDP column that E1's registered extraction and run read on 30 September 2026, nothing in it has been read beyond sheet names, titles and header text (E2 section 0). E1 was run once and frozen on 30 September 2026 (D-049; tag e1-frozen): inconclusive, raw p=0.1349, not family-adjusted. E3 was run once and frozen on 29 September 2026 (D-042): inconclusive, raw p=0.524, not family-adjusted. ONS metadata pages about the series and the Labour Force Survey were read, and the series page that displays the latest value was deliberately not opened. General knowledge of UK economic and labour-market history is not ignorance of the data. Investigator's declaration, 1 October 2026: Kostadin Stoyanov has no recollection of downloading, opening or analysing any UK labour-market data other than the workbook described next, and in particular none of the ONS labour-market series this addendum uses. The one file in the programme that contains UK employment and unemployment series is the Bank of England workbook acquired once on 29 September 2026 for E1, for its GDP series; it was hashed and, apart from the year cells and the levels of one real-GDP column that E1's registered extraction and run read on 30 September 2026, read only as text (sheet names, titles and header cells), and no numeric cell of its employment or unemployment sheets has been read or printed. A file-name search of his user folders (desktop, documents, downloads, synchronised cloud documents, and his reference-manager and project folders) on 1 October 2026 found no file or folder whose name refers to unemployment, employment statistics, the labour market, the Labour Force Survey or MGSX; outside the programme's own records the only name matches were three notes on quantitative-finance employers and unrelated technical files. See E2 section 0.

## Analyses

### Statistical models [72-49]

Use the OLS VAR(2), companion spectral radius and episode definitions in E2 sections 6-7. Fit a strictly stable intercept-inclusive VAR(2) to all 195 observations (193 regression rows) for null generation. Centre its 193x2 matrix of residual vectors by column; keep the first two observed vectors fixed and generate 1,000 attempted paths that resample whole residual rows jointly. Refit the rolling models and repeat endogenous episode selection on the surrogate GDP growth. Drop only paths without eligible episodes; numerical or fit failures invalidate the affected comparison. For B' retained paths and K exceedances including ties, the raw p=(1+K)/(B'+1). Master seed 1927 with stream ids 5200-5231. See E2 sections 6-9 and Annex A.

### Effect size [72-51]

Report S, each signed Delta, m and the number of positive changes. No economically defined minimum important effect is asserted. The registered fixed-date power study produces D80 only under its explicit validity and first-crossing rules; it is a detectability diagnostic, not an equivalence margin. See E2 section 11.

### Statistical power [72-53]

Official power results do not yet exist. After registration and before any unemployment value is read, run the exact size and power cells in E2 section 11: 200 size replicates and 200 replicates at each of four fixed power multipliers, each with 1,000 attempted surrogates, with the signals planted at the two eligible onset positions. With two onsets, power may be low and D80 undefined (unverified expectation; H1's five-onset design reached 0.235 at the largest multiplier, and the official checks of E1 and E3 reached 0.115 and 0.340). That outcome is recorded, not corrected. Preserve every failure and incomplete replicate. Do not tune the sample, seeds or design after seeing results.

### Inference criteria [72-55]

One upper-tailed confirmatory comparison at W=40. E2 rejects only when its Holm-adjusted p<=0.05 within the family E1-E4 at family closure; a registered extension never run or failed enters with Holm input 1. Report the raw p at freeze, labelled as not family-adjusted, and the signed statistic and limitations even after rejection. An adjusted p>0.05 is inconclusive, with the H1 Branch B diagnostic reported as a labelled diagnostic or as unavailable; an undefined p is a failed or not-estimable outcome. The 90% episode-resampling interval rests on two episodes and is not asserted to have calibrated coverage. Secondary p-values are prespecified sensitivity evidence. See E2 sections 9-11.

### Assumption violation/model non-convergence [72-57]

Stop on invalid input, unverified release identity, rank-deficient or non-finite fits or an unstable generating null; do not project coefficients or silently drop affected windows. Preserve all attempted-draw and per-statistic failure accounting. A failed synthetic check prevents the real-data run until the response is documented and any methodological change is registered before data. Preserve original outcomes and log deviations. See E2 sections 4, 6, 9, 11 and 13.

### Reliability and robustness testing [72-59]

Report all registered sensitivities: W=32 and W=48; fixed observed onset dates; ordered wild signs applied to whole residual vectors; Kendall tau-b trend of the spectral radius; and the lag-one autocorrelation comparator of GDP growth. Primary, trend and lag-one statistics share the primary generated paths but have separate eligibility, failure and retention accounting. Report, as descriptions only, H1's AR(2) change at each eligible onset and the AR(2) change computed on the unemployment change alone. Use the prescribed 10,000-resample episode interval, deterministic random streams, software lock and retained reproducibility records. See E2 section 10 and Annex B.

### Exploratory analysis [72-61]

No additional exploratory test is specified for the confirmatory conclusion. Any unplanned analysis must be labelled exploratory and recorded as such. Quarters after 2019Q4 are not used. E2 is a separate registered extension of H1, not an undisclosed alternative to it, and H1 remains the single primary test.

## Template source

The template is OSF Registries' Secondary Data Preregistration, as used for H1, E1, E3 and E4. The H1 responses record how it was obtained, through the official OSF registration guide, on 25 September 2026. Field availability, field keys and contributor identity must be checked in the live submission before public registration.
