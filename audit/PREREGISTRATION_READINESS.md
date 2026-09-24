# Preregistration readiness

Status: **methodological draft complete; final submission checks remain**. Date: 2026-09-24. The standalone protocol is prereg/H1.md. The prior-data declaration is complete. G0 awaits verification of the revised public repositories and hosted checks; registration details and release-route metadata remain to be finalized. No OSF registration or confirmatory result is claimed.

## What is preserved

H1 remains the single primary question using the original pre-pandemic sample, 40-quarter causal windows, intercept-inclusive AR(2), companion-root modulus, endogenous recession onsets, episode merging, eight-quarter pre-onset difference, and the specified surrogate comparison. The draft fixes the master seed and random-stream allocation. All prespecified secondary analyses and E1-E4 remain planned. Paper II and the formalisation remain separate research components.

## Must close before G1

| Item | Current position | Evidence required |
|---|---|---|
| Prior data exposure | Declaration dated 2026-09-24: no inspection/download of UK GDP data or UK recession analysis before this project; no raw UK series acquired during preparation | Retain the declaration and distinguish literature/incidental headline exposure from source-data access |
| Prior registration | No earlier registration is known; absence has not been independently established | Retain the uncertainty; identify and disclose any earlier record if found |
| Data release | Fixed QNA-before-registration selection rule and no-fill validation in H1 sections3/12; QMI coverage verified | Release-specific identity and file availability verified before acquisition; no raw values yet |
| Null-generation convention | M1c.1 fixes and tests centering, initial pair, stable fitted null and failure rules; residual resampling retained | Preserve D-012, docs/M1C1_SURROGATE_CONTRACT.md and the fixed random-stream allocation in the registered protocol |
| Onset indexing | Original eligibility/merging retained and tested in M1b | Carry docs/M1B_CONVENTIONS.md and its evidence into protocol |
| Empty outcomes | M1c.1 explicitly tests observed no-episode, B'=0 and exact attempted-count handling | Carry rules into protocol; final stopping/precision rule frozen before data; primary comparison conditions on retained eligible outcomes |
| Secondary statistic eligibility | Fully specified and tested in M1c.2a | H1 section7; shared primary paths with separate denominators and explicit failures |
| Effect interval | Conditional diagnostic implemented and tested | H1 section7; linear quantiles; no equivalence claim |
| Outcome wording | Safer reporting adopted in specification audit | Report S, sign, p, interval, count and benchmark separately; revised Branch B wording |
| Power study | Exact design frozen in draft; helpers tested without official cells | H1 sections8/9; AT5/15/16 execution remains after registration |
| Estimator verification | Production AT1-4 comparisons and secondary engineering checks pass locally | G2 still needs large registered checks; local suite is not calibration evidence |
| Exposure controls | Literature reviewed; no raw UK series acquired | A retained access log; synthetic builds separated from real-data ingestion |
| External evidence | Revised public repositories and hosted checks await verification in GITHUB_PUBLICATION.json | Verified G0, then public frozen OSF record, verified status/date, identical attached protocol hash and pushed supporting tag |

No observed real outcome may decide any of the above. Synthetic development runs must be logged and must not silently become the registered power results. The registered design must identify which synthetic checks occurred before registration and which are subsequently run under the frozen protocol.

## External registration mechanics

The inspected OSF guidance distinguishes a mutable project from a frozen registration. A draft or pending record does not satisfy this plan's public-registration gate. Verify the actual registration, attached file and public status before data acquisition. Public registrations receive a DOI; retaining the URL is also useful. The plan's public visibility requirement is retained even though OSF offers embargoes. [OSF registration guidance](https://help.osf.io/article/330-welcome-to-registrations).

OSF's announced project transition leaves registrations available and supports direct registration without first creating a project. The required evidence is the frozen registration itself, created through the supported workflow at submission time. [OSF transition guidance](https://help.osf.io/article/768-osf-projects-transition-registration-questions-and-use-cases). Accessed 2026-09-24.

## Further registered components

- **E1:** annual-series definition, territorial continuity, exclusions and data coverage must be documented before values are inspected.
- **E2:** unemployment identifier/coverage and joint residual resampling must be exact. Do not enumerate data-derived eligible onsets before registering the rule; distinguish a coverage-based count estimate from an observed count.
- **E3:** specify initialization, likelihood, optimization and per-surrogate re-estimation. Filtered states conditional on variances estimated from the full sample do not by themselves establish real-time availability.
- **E4:** verify release calendars, vintage coverage, usable horizons and source availability. A vintage containing the preceding quarter is not necessarily available before onset. Final-data onset dates remain a retrospective reference unless specified otherwise.
- **C3:** freeze innovations, burn-in/initialization, sample convention, null projection, boundary handling, Monte Carlo uncertainty and no-valid-candidate outcome before cells run. Distinguish development from an independent validation run. Its actual applications wait for G5.

## Next deliverable

The draft, fixtures, report, prior-data declaration and source/coverage inventory are complete. Finalize the registration details, retain uncertainty about earlier registration, verify release-route metadata and establish G0 before submission. G1 requires the actual public registration and an identical protocol attachment; this checklist does not satisfy that gate.
