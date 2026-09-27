# Programme status

Updated 28 September 2026. **M1 Foundations and Registration Preparation is complete; M2 is in progress.** The mathematical and computational methods, protocol, exposure declaration and public infrastructure meet the M1 checklist. All three repositories have successful hosted checks, satisfying G0. H1 was submitted to OSF on 25 September under CC BY 4.0, approved by the registry at 04:49 UTC on 27 September and verified as public, with all five archived attachments byte-identical to the submission. The supporting annotated `prereg-H1` tag is published, so G1 has passed. No empirical H1 result or completed programme formal theorem is claimed.

| Output | Evidence | Status |
|---|---|---|
| Specification and baseline | audit/SPECIFICATION_AUDIT.md; audit/baseline_results.json | Complete |
| Estimators and root diagnostics | src/uc_core/ar.py; audit/M1A_REPORT.md | Complete |
| Stability triangle | proof/triangle.pdf | Paper proof complete |
| Rolling calculations and episodes | audit/M1B_REPORT.md | Complete |
| Surrogate mechanics | audit/M1C1_REPORT.md | Complete |
| Secondary methods and integrated workflow | audit/M1C2_REPORT.md; 204 research tests | Complete |
| Resumable validation execution | audit/M2_RUNNER_REPORT.md; audit/validation_runner_verification.json; 236 total research tests | Development recovery checks complete; official experiments unrun |
| Reporting preparation | audit/M2_REPORTING_REPORT.md; audit/h1_reporting_verification.json; 273 total research tests | Artificial-data tables and figures verified; empirical report remains outstanding |
| H1 execution tooling (acquire once, run once, freeze) | docs/H1_EXECUTION.md; src/uc_core/abmi.py; src/uc_core/h1_official.py; tools/acquire_abmi.py; tools/run_h1.py; tools/freeze_h1.py; tests/test_h1_official.py | Built and rehearsed end to end on artificial ONS-format data; closed until G2 passes |
| Core note draft (plan W) | paper1/core-note.tex; tools/build_note.py; tests/test_note.py; `make note` | Drafted; registration, S1 and foundations numbers are written from the evidence records; the G2, release, H1 and S2 values are visible placeholders until their records exist; one commit rebuilds one byte-identical PDF |
| S2 Samuelson check (three filters) | DECISIONS.md D-021; src/uc_core/samuelson.py; tools/build_s2.py; tests/test_samuelson.py | Built and tested on artificial series; runs on the registered levels after acquisition |
| H1 methodological protocol | prereg/H1.md; audit/H1_REGISTRATION.json; tag `prereg-H1` | Registered: [OSF wcnbz](https://doi.org/10.17605/OSF.IO/WCNBZ), approved and public |
| H1 registration responses | prereg/H1_OSF_responses.md; audit/PREREGISTRATION_READINESS.md | All five archived attachments match the submitted bytes |
| Registration timestamp | audit/H1_REGISTRATION_TIMESTAMP.md; audit/h1_timestamp_verification.json; 278 total research tests | Approval recorded 2026-09-27T04:49:01Z; QNA release rule invariant over the admissible interval |
| Registered validation (AT-5, AT-15, AT-16) | Frozen checkout at commit da548d9; run manifest SHA-256 3eb8cc1330bf721349f546869ede239d8c70b6998321d814a5de3bcd55d7cbc6; registration receipt SHA-256 5645a0f9082865abe2c77334bd8970e9ee12a8c1d7b485ffeb3681e0a685adee | Running since 27 September, 21:41 UTC; both white-noise cells (160,000 records) complete; size at 140 of 200 records at 23:18 UTC on 27 September; power not yet started; no acceptance decision yet |
| S1 Yule centenary | DECISIONS.md D-018; audit/YULE1927_TRANSCRIPTION.md; audit/S1_TABLE.md; audit/s1_verification.json; audit/yule1927_verification.json; figures/s1_argand.svg; figures/s1_triangle.svg | S1.1-S1.5 complete; Yule's equation (31) and 10.600-year period reproduced from his transcribed data; AT-13 passed |
| Original C1 foundations checks (F2, F4, F5, F6) | audit/FOUNDATIONS_REPORT.md; audit/foundations_verification.json; DECISIONS.md D-019; schur-cohn commit a907f99 | AT-8, AT-12 and the local-level model passed; AT-11 failed in filter version 1 and passed after a recorded correction; Lemma A proved in Lean with no sorry |
| Historical exposure declaration | prereg/H1.md, section 1 | Recorded |
| Python package foundation | unitcircle repository; installed-package checks | Complete development setup |
| Lean foundation | schur-cohn repository; pinned build evidence | Complete setup; programme theorems remain |
| Public infrastructure | audit/GITHUB_PUBLICATION.json | Complete; all three hosted checks passed |

## Research gates

| Gate | Status | Required evidence |
|---|---|---|
| G0 | Passed | audit/GITHUB_PUBLICATION.json: verified public commits and successful hosted checks |
| G1 | Passed | OSF wcnbz approved and public (DOI 10.17605/OSF.IO/WCNBZ); five archived attachments byte-identical; registration timestamp in audit/h1_timestamp_verification.json; annotated `prereg-H1` tag on commit 0dfc025 published |
| G2 | Pending | Complete registered baseline and simulation checks (AT-1-AT-4, AT-5, AT-15, AT-16) |
| G3 | Pending | Frozen H1 analysis and core note |
| G4 | Pending | Registered extension addenda |
| G5 | Pending | Frozen Paper I analyses |
| G6 | Pending | Formal blueprint and coordination requirements |
| G7 | Pending | Programme theorem build and axiom audit |

The [submission evidence record](audit/H1_REGISTRATION.json) retains the five submitted files unchanged. OSF's registry record timestamp, 2026-09-25T15:32:12Z, marks submission: the record and its files were frozen then, pending approval. OSF recorded approval of the registration's original response at 2026-09-27T04:49:01Z; the Internet Archive copy became public at 04:50:09Z, and the first anonymous check at 20:58:15Z returned the approved public record. The [timestamp record](audit/H1_REGISTRATION_TIMESTAMP.md) documents these sources. No ONS quarterly national accounts publication was released between submission and the first anonymous check, so the H1 section 3 release rule selects the same publication for every admissible timestamp ([D-017](DECISIONS.md)). The publication's identity, release-specific ABMI file and availability are resolved only after G2, under the registered stop-and-amend rule.

The annotated `prereg-H1` tag points to commit 0dfc0258459d42092ec4e880ada917b011d9879f, the earliest public commit whose protocol and form responses equal the archived attachments; every repository file in the archived supporting-materials archive also matches that commit. The OSF registration is the primary timestamp; the tag is supporting evidence published on 27 September.

The registered size and power experiments are running from a frozen checkout of commit da548d9, bound to the registration receipt above; UK data acquisition remains ahead. S1 now uses SILSO's frozen Version 1 and current Version 2 yearly files, committed with attribution under CC BY-NC 4.0 and hashed in DATA_MANIFEST.csv. For 1749-1924 both versions and both estimators give complex roots with modulus 0.80-0.81 and period 10.5-10.7 years; Version 2 raises the least-squares period by 0.07 years and the modulus by 0.003 relative to Version 1. The bootstrap bands and point differences are reported without a difference test ([S1 table](audit/S1_TABLE.md)). The S1.1 transcription of Yule (1927) reproduces his serial correlations exactly and his equation (31) to 1e-5; on his own data the programme's least squares gives 10.57 years against his 10.600, so his figure reflects his correlation arithmetic rather than the data version ([transcription record](audit/YULE1927_TRANSCRIPTION.md)). The research suite has 321 tests. The [validation execution checklist](docs/M2_VALIDATION_EXECUTION.md) defines the registered experiments. The [runner](docs/VALIDATION_RUNNER.md) has tested interruption recovery, integrity checks, explicit failure accounting and backup restoration, and its fail-closed registration check now accepts the published receipt. Its 18-record development fixture reproduced uninterrupted execution exactly; this is not calibration evidence. G2-G7 remain pending; M2 is not complete.

The [reporting preparation](docs/H1_REPORTING.md) preserves all seven comparisons, checks full-input identity and individual attempt accounting, and exports labelled artificial-data evidence. Three bounded fixtures reproduced the submitted methods' scientific outputs and random states exactly; the submitted package is unchanged. This establishes reporting behaviour, not a completed H1 study. The [programme review](audit/PROGRAMME_REVIEW_2026-09-27.md) records the remaining core-note obligations, source dependencies, substantive calibration checks and later formal-coordination requirement.

## Programme completion measure

M0 and M1 are complete: **2 of 9 milestones (22.2%)**. Seven milestones are not complete (77.8%), including M2, which is active. This is an equal milestone count, not a time, cost or effort estimate. Partial M2 work, including G1, is recorded above without treating the milestone as finished. The remaining programme includes registered validation and empirical work, extensions, theory and simulations, formal proofs, a reusable library, manuscripts and replication archives, and external review and maintenance.
