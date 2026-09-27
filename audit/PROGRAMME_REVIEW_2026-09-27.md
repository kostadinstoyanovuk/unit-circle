# Programme review: 27 September 2026

## Scope and conclusion

This review compares the adopted roadmap, milestone evidence and outstanding gates with the original 23-page `Unit_Circle_Programme_Plan.pdf`. Its verified SHA-256 is `85a594b0baf6d7b5a72d3ca1ec856f0df06b1106aaf3319e48f5b3967854dde7`. Page references below refer to that original document, which remains unchanged. Adopted clarifications are recorded in [DECISIONS.md](../DECISIONS.md) and [SPECIFICATION_AUDIT.md](SPECIFICATION_AUDIT.md).

Progress follows the adopted milestone sequence: M0 and M1 are complete, M2 is in progress, G0 is passed and G1-G7 remain pending. The documentary record distinguishes implementation checks from registered calibration, empirical findings, formal proofs and external review. No material inconsistency was identified in those milestone and gate claims. This is a review of the plan and retained evidence, not a new statistical experiment, an exhaustive proof review or a claim that the remaining research will succeed.

The original plan explicitly supplies no calendar: its hours describe scope and its ordering follows dependencies (p. 1; dependency diagram and component budget on p. 6). Consequently this review makes no claim that the programme is ahead of, behind or on a calendar schedule.

## What the completed work establishes

- [GITHUB_PUBLICATION.json](GITHUB_PUBLICATION.json) records public repositories, exact commits and successful hosted checks for all three components. These support G0's infrastructure requirement (original pp. 4-5).
- The completed M1 milestone covers the tested early mathematical and computational methods, synthetic workflow, protocol preparation, exposure declaration and public infrastructure described in [MILESTONES.md](../MILESTONES.md).
- [M2_RUNNER_REPORT.md](M2_RUNNER_REPORT.md) records 236 research tests and an 18-record development fixture whose interrupted and resumed scientific payloads match uninterrupted execution exactly. This supports execution and recovery behaviour; it does not establish AT-5, AT-15 or AT-16 calibration.
- The reporting checkpoint is verified separately in [M2_REPORTING_REPORT.md](M2_REPORTING_REPORT.md). Its artificial-data checks do not constitute calibration or an empirical finding.

The [programme completion measure](../STATUS.md#programme-completion-measure), **2 of 9 milestones (22.2%)**, is an equal milestone count. It is not an estimate of time, cost, effort or scientific work completed. Partial M2 progress does not make M2 complete.

The adapted M1 milestone must also be distinguished from the original C1 component. Original C1 includes later requirements such as Kalman-filter verification and a fitted local-level model, broader theoretical derivations, further acceptance checks and Lemma A proved in Lean (pp. 6-7). Foundations are intended to run alongside the components that need them (p. 7). Completion of M1 therefore does not imply completion of every original C1 requirement.

## Open dependencies

### G1: public registration, timestamp and source identity

H1 was submitted to [OSF wcnbz](https://osf.io/wcnbz/) with the five prepared attachments. The latest anonymous registration API check returned HTTP 401 at **2026-09-27T04:32:45.4692644Z**. That response does not verify public availability. The signed-in registration page was also refreshed on 27 September and still displayed **Pending approval** and no DOI. Public immutable registration remains unverified.

The original G1 requires a public, timestamped registration and a pushed annotated `prereg-H1` tag (pp. 5, 8). The adopted receipt checks additionally require archived attachment bytes to match the submitted hashes. Names, sizes and a displayed registration date are insufficient to establish those facts. See [H1_REGISTRATION.json](H1_REGISTRATION.json) and [the execution checklist](../docs/M2_VALIDATION_EXECUTION.md).

[H1 section 3](../prereg/H1.md) selects the latest completed QNA publication released strictly before the verified public registration timestamp. The meaning of that timestamp must be resolved from documented registry evidence before selecting the release. Submission time and the time of the first successful public check must not silently be substituted for the required public registration time.

The selected vintage's publication identity and release-specific file availability also remain unverified. D-016 correctly distinguishes archive supersession labels from publication dates and aligns retrieval with the QNA family. An advertised archive route does not establish that the ultimately selected file is available. If its identity or availability cannot be verified, the registered stop-and-amend rule applies before values are inspected; there is no unverified latest-file fallback.

### G2: registered validation can fail

The original G2 requires the estimator checks AT-1-AT-4 and synthetic checks AT-5, AT-15 and AT-16 (pp. 5, 9-10, 21). The registered designs and acceptance decisions remain unexecuted official work. Development tests and a recovery fixture cannot substitute for them.

The submitted protocol requires all requested replications to be accounted for and all required comparisons to be valid before acceptance. A valid-only rejection rate does not establish a pass when invalid or unfinished outcomes remain. AT-15 also requires its rejection rate to lie from 0.02 through 0.09 inclusive; AT-16 retains the disclosed adjacent-decrease check. D80 may legitimately remain undefined if the power grid never reaches 0.80; that possibility is present in the original plan (pp. 10, 21).

These checks are substantive constraints, not administrative steps guaranteed to pass. A failed acceptance check keeps G2 pending. Preserve the original failures, seeds, denominators and outcomes; document the response and register any methodological change before data access. The adopted H1 protocol requires both G1 and G2 before UK acquisition. See [H1 sections 8, 9 and 12](../prereg/H1.md) and [the validation execution checklist](../docs/M2_VALIDATION_EXECUTION.md).

### M5 and G6: exact blueprint and external coordination

The original formal blueprint package requires exact statements, a complete dependency graph and recorded external coordination answers (p. 16). [FORMAL_FEASIBILITY.md](FORMAL_FEASIBILITY.md) preserves this requirement: G6 remains open until that evidence exists or an explicit, justified gate revision is adopted.

D-008's decision to write independent proof code does not itself waive the coordination requirement. A pinned Lean setup or compiled setup example is also distinct from the programme theorem, its intended meaning and its axiom audit. The technical proof and external contribution outcomes remain separate deliverables (original pp. 5-6, 16).

## Remaining M2 and programme scope

M2 must not close solely because a runner, reporting layer or H1 result exists. The original core includes the Yule transcription and sunspot-version comparison, bootstrap bands and figures (p. 9), the three-filter Samuelson check, the frozen H1 analysis and a reproducible six-to-eight-page note rebuilt from a clean clone (p. 10). The required `h1-frozen` and `core-v1` tags and complete supporting evidence remain part of that closure. These are planned remaining deliverables, not evidence of a current failure.

Subsequent milestones still require registered extensions, Paper II theory and simulations, the formal proof, the reusable library, manuscripts and replication archives, and external review and maintenance. Journal decisions, coordination answers, contribution outcomes and replication evidence cannot be inferred from passing software tests. The original finish line permits negative findings and rejected contributions with the required retained evidence (p. 6); it does not require a preferred scientific result.

## Next review boundary

After preserving the reporting checkpoint, verify G1 using actual public evidence and archived bytes. Freeze the applicable code and environment before bounded official validation. Review every required acceptance result before G2 and before UK acquisition. Keep the timestamp, vintage-availability and later formal-coordination dependencies explicit throughout; none is closed by this review.
