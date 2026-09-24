# M0 specification audit

Date: 2026-09-24. Source: the original 23-page Unit Circle Programme execution plan, SHA-256 `85a594b0baf6d7b5a72d3ca1ec856f0df06b1106aaf3319e48f5b3967854dde7`.

## Assessment

Retain all six components and the programme's connection between exact stability regions and uncertain empirical inference. The implementation is feasible as staged work. Research findings, formal proof builds and external review require distinct evidence.

M0 verifies a baseline and specifies necessary repairs before registration. It does not certify the full mathematical/statistical programme, exhaustive novelty, any OSF registration, or any of G0-G7. The original PDF remains unchanged.

## Changes adopted before registration

| ID | Original location | Finding | Adopted handling |
|---|---|---|---|
| A01 | p3 P5, roles; p20 statement interface | Completion claims must be supported by the corresponding evidence | Keep implementation, mathematical verification, empirical findings and external review distinct. A completed file does not establish every programme outcome. |
| A02 | pp8,11 H1 and Branch A | An upper-tail surrogate result is relative to its null benchmark; the observed S can still be negative | Report observed S, its sign, p and the benchmark separately. Count of positive episode changes is descriptive, not a count of individually significant warnings. No causal mechanism or operational forecasting claim follows solely from H1. |
| A03 | pp10-11 Branch B | D80 is based on fixed-date planted signals; primary onset selection is endogenous. The few-episode interval is not an established equivalence guarantee | Preserve the numeric comparison as a labelled scenario-specific diagnostic. Withhold the strong 'no sizeable rise' conclusion. A nonsignificant primary result is inconclusive unless a separately justified and registered absence/equivalence procedure is established before data. |
| A04 | p14 C3.TEST; p22 formula sheet | sigma_D denotes the limiting SD of sqrt(n)(Dhat-D); the printed Wald ratio omits its sample-size scaling | Define the Wald statistic as sqrt(n) Dhat / sigmahat_D, equivalently Dhat divided by a consistently defined finite-sample SE. Record exactly what n counts. Derive the spectral version separately, including its kink. |
| A05 | p14 DR-3 and candidates | Passing a finite calibration grid is not universal size control; projection onto a boundary is not by itself proof of a least-favourable null | Call this finite-grid calibration unless stronger theory is proved. Freeze projection, selection and independent validation rules. If no candidate passes, report that outcome; do not force a recommendation or relabel failure as success. Original package obligations remain open until an explicitly justified resolution. |
| A06 | p17 time-series bridge | Existing IsStationary is a root predicate; a stochastic-process theorem would require additional definitions and assumptions | Formal C4 scope is the complex polynomial theorem, executable rational checker and root-predicate corollaries. Explain the causal time-series interpretation in prose. A full stochastic-process formalisation is an optional separately scoped extension, not silently added. |
| A07 | pp15-17 upstream comparison | Named upstream work must be pinned and accurately attributed; reuse terms must be checked | Use independently written proof code by default. Preserve comparison and attribution. Do not copy/relicense upstream source without clear permission. |
| A08 | pp4-6 tools and gates | Original setup commands require platform-specific tools and external services | Use portable build commands and a tested pinned environment. Local success is distinct from hosted CI and public repositories. Keep gates pending until actual evidence exists. |
| A09 | H1 surrogate edge cases; resolved in M1c.1 | Initial values, residual centering, unusable full-sample nulls and numerical failures need exact rules | Adopt D-012 and docs/M1C1_SURROGATE_CONTRACT.md: stable fitted null only, no projection; fixed initial pair; centered unscaled residuals; exact attempted-draw accounting; failures invalidate p. Carry these additions into registration. |

These decisions preserve the research questions and outputs; they do not choose a preferred empirical answer. Detailed reasoning and primary-source records are in STATISTICAL_DESIGN.md and FORMAL_FEASIBILITY.md.

M1c.2 closes the remaining H1 methodological choices in D-013/D-014 and prereg/H1.md: exact secondary statistics/undefined cases, interval quantiles, stream mapping, synthetic initialization and date indexing, D80 interpolation and failure accounting, release-specific selection and missing-data stop rules. These are explicit preregistration additions; they do not execute acceptance simulations or pass G0/G1. The prior-data declaration is recorded below. Public infrastructure, final registration details and the actual frozen registration require separate verification.

## Further choices requiring design work, not observed results

The M0 audit identified additional choices concerning source release rules, previous exposure, unavailable data, singular or unstable fitted nulls, missing/empty episodes, synthetic initialization, random-stream allocation, projection metrics and result-selection validation. H1's choices are now fixed in the draft; later components remain subject to the checks in PREREGISTRATION_READINESS.md. Resolve outstanding choices through theory, source metadata and recorded synthetic engineering work before the applicable registration. Never silently alter registered choices after real-data inspection.

E4 must distinguish the quarter described by data from their publication date. E3 must distinguish causal filtering conditional on fitted hyperparameters from an entirely real-time estimation procedure. Paper I's retrospective question remains useful without claiming deployable warning performance.

For statistical tests, a null-model rejection is evidence about the registered statistic under that null; it is not evidence uniquely identifying critical slowing down. For formal proofs, an accepted proof of a weakened or mis-specified theorem would not meet the intended goal. Both layers need review of meaning as well as computation.

## Baseline evidence and limits

The M0 numerical audit uses the sunspot dataset bundled with statsmodels; no UK observations are required. It independently checks the original estimator, sample and root conventions rather than importing a future production implementation. BASELINE_CHECKS.md and baseline_results.json contain full-precision values, tolerances, input digests and package versions. Symbolic delta-method identities are labelled algebra checks, not completed Monte Carlo acceptance tests. Production code must later reproduce these independently.

The complete AT-1-AT-21 suite is not being claimed. In particular large Monte Carlo checks, H1 size/power checks, a state-space implementation and Lean validation await their proper milestones. Nor is the plan's assertion that its own starred checks were run accepted as evidence of a run in this workspace.

## Prior-work status

The primary Rye and Jackson article was opened and its abstract and methodological description checked. It studies lag-one autocorrelation and variance across historical GDP datasets, emphasizing multi-decadal variability. This supports the plan's use of it as related work; it does not establish that H1 is novel or that no closer paper exists. Full contribution searches for C2, C3 and C4 remain required. [Rye and Jackson (2020)](https://www.nature.com/articles/s41598-020-66996-6), accessed 2026-09-24.

The formal source audit verifies the exact named repository and inspected theorem scope at a commit. It does not certify every theorem in that repository or the absence of related work throughout mathlib and other proof libraries. Consult FORMAL_SOURCES.json for verified URLs and explicit gaps.

## Data-access and provenance record

No raw UK GDP, unemployment or vintage series has been acquired or analysed during preparation. Related published literature was inspected, including discussion of historical UK dynamics. A source-metadata search returned unsolicited post-2019 GDP headline snippets; those snippets were not used for design choices, and no source dataset or primary-sample observations were opened. This incidental exposure is recorded in STATISTICAL_SOURCES.json. The declaration dated 2026-09-24 records no inspection/download of UK GDP data or UK recession analysis before this project. The preregistration must preserve the distinction between prior-data access and literature or incidental headline exposure.

## Delivery and review constraints

Journal decisions, maintainer responses and third-party replication are external outcomes requiring direct evidence. The original plan allows rejection and closed pull requests with recorded reasons. If an external gate cannot be satisfied, retain its status explicitly; other independent work can proceed within the remaining gates.

## Completion criterion for M0

The audit reports exist, the baseline independently reproduces its declared targets, the dependency lock matches the tested environment, the test suite passes, records accurately distinguish completed from pending work, and a local Git checkpoint preserves the evidence. `python tools/verify_m0.py` checks the repeatable local part and writes `audit/m0_verification.json`. It does not perform scientific peer review or pass G0-G7.
