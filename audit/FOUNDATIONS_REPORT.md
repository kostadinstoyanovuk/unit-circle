# Foundations checks: AT-8, AT-11, AT-12, local level and Lemma A in Lean

27 September 2026. Designs and pass criteria were fixed in [D-019](../DECISIONS.md) and published (commit b2c99f0) before the checks ran. Evidence: [foundations_verification.json](foundations_verification.json) (current) and [foundations_verification_v1.json](foundations_verification_v1.json) (first run, retained). No UK observation is used.

## Results

| Check | Package | Result |
|---|---|---|
| AT-8: Schur-Cohn recursion against computed roots | F5 | Passed: 159,999 random complex polynomials of degree 1-8 compared, no mismatch; 1 skipped (root within 1e-7 of the circle). Stable cases per degree: 10,041, 4,182, 1,714, 602, 222, 88, 37, 11. |
| AT-11: Kalman filter with zero state noise and diffuse start | F2 | Failed in version 1 (5.5e-6); passed in version 2 (2.3e-9). See below. |
| Local-level model by maximum likelihood, Nile 1871-1970 | F2 | Passed: irregular variance 15098.5, level variance 1469.2, within 0.01% of Durbin and Koopman's 15099 and 1469.1. |
| AT-12: companion spectral radius | F4 | Passed: diagonal VAR(1) exact (error 0); AR(2) companion against root modulus, largest error 4.9e-15. |
| Lemma A in Lean | F6 | Proved with no `sorry`; axioms `propext`, `Classical.choice`, `Quot.sound` only ([schur-cohn](https://github.com/kostadinstoyanovuk/schur-cohn) commit a907f99, hosted run 36356528537). |

The random polynomials in AT-8 are mostly unstable at higher degrees, so the stable class is small there (11 cases at degree 8). The check confirms agreement on both classes; it does not measure accuracy near the boundary, which the skip rule excludes.

The statsmodels unobserved-components fit of the same local-level model reports 15078.0 and 1478.8; its likelihood treatment and optimiser differ, and it is shown for reference only.

## AT-11: error in version 1 and its correction

- **What was done.** The first filter propagated the state covariance with the Joseph-form update and was run on the AT-11 design: sunspot AR(2) regression, 1749-1924, zero state noise, unit observation variance, P0 = 1e8 I.
- **What went wrong.** The final filtered state differed from least squares by 5.5e-6 in the intercept, above the 1e-6 target. In exact arithmetic this design differs from least squares only by the prior's ridge term, 2.3e-9. The excess was rounding error: with a 1e8 prior the covariance recursion subtracts nearly equal numbers of order 1e8 to obtain entries of order 1e-4.
- **How it was found.** The acceptance test itself (first run, commit 2a2875d, where the failure is recorded). The pre-specified sensitivity run with the residual variance as observation variance passed at 5.0e-7, but that figure is almost entirely the larger ridge term for that variance (5.5e-7); it is not evidence of accuracy.
- **Fix.** Version 2 propagates a square-root factor of the covariance with orthogonal (QR) array updates, a standard numerically stable form of the same filter. The test design and tolerance are unchanged.
- **What it changed.** AT-11 now agrees with least squares to 2.3e-9, the exact-arithmetic value. On well-conditioned random models the two versions agree to 3e-14 in states and likelihood. The local-level estimates moved by less than 0.01% because the likelihood surface is flat near its optimum; both versions meet the Durbin-Koopman criterion.

## Status of the original C1 packages

| Package | "Done when" in the plan | Evidence |
|---|---|---|
| F1 Time series | Estimators pass AT-1-AT-4 | Passed ([M1A_REPORT.md](M1A_REPORT.md)); hand derivations of the AR(2) autocorrelation and spectral density are not recorded in this repository |
| F2 State space | AT-11; a local-level model fitted by maximum likelihood | Passed (this report) |
| F3 Bootstrap and surrogates | AT-13, AT-14 | AT-13 passed ([S1_TABLE.md](S1_TABLE.md)); the AT-14 p-value convention is implemented and tested ([M1C1_REPORT.md](M1C1_REPORT.md)) |
| F4 Linear algebra | AT-12 | Passed (this report) |
| F5 Complex polynomials | Lemma A on paper; AT-8 | AT-8 passed; the paper proof is the plan's section 14 |
| F6 Lean 4 | Lemma A in Lean with no `sorry` | Passed (schur-cohn) |
| F7 Research craft | Three repositories; CI green | Passed (G0) |

AT-11 in CI and Lemma A in Lean were the remaining items of the plan's C1 finish line. The Kalman filter and local-level code are research implementations; the package versions are later work (C5.4).
