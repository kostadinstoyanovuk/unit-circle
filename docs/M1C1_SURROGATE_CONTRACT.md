# M1c.1 synthetic surrogate contract

Date: 2026-09-24. Fixed before implementation and synthetic verification. This is a development specification to carry into a future preregistration, not an already registered protocol. No real UK series or official size/power experiment may run at this milestone.

## Null and generation

Fit intercept-inclusive OLS AR(2) to the complete supplied series, using the first two values only as lags. Take its n-2 conditional residuals and explicitly subtract their mean. Do not divide by an estimated degrees-of-freedom correction, standardize their variance, or alter the fitted coefficients. Retain the first two input values as initial conditions for every surrogate; there is no burn-in or stationary initialization in this procedure.

Require a strictly stable fitted full-sample null. If it is unstable, nonidentifiable or nonfinite, return a clear failure rather than project it into the triangle or emit a primary p-value. This is an explicit pre-registration addition resolving an unspecified case in the PDF. It does not constrain individual rolling fits, which remain unconstrained and can be unstable. The complete protocol must retain or explicitly revise this decision before data.

The implementation requires both the strict triangle predicate and a finite computed modulus below one. A boundary or numerical disagreement fails conservatively. `NullModelError` is raised before any random draws when the full-sample fit is unusable. An observed rolling-fit error likewise propagates before draws. These failures differ from an observed series with no structurally eligible onset, which returns an explicit not-estimable result without fitting a null.

Residual mode draws n-2 residual indices independently with replacement. Wild mode preserves the ordered residual sequence and multiplies each entry by an independent equiprobable sign. The same fitted coefficients and intercept drive the recursion in both modes. Wild signs retain the residual magnitude pattern, not a proof that all volatility features of the data-generating process are reproduced.

## Randomness

Each call receives an explicit NumPy Generator. No global random state, hidden seed or automatic reseeding. The caller owns independent streams for separate registered analyses. The result retains the bit-generator name and before/after states. The verification fixture uses explicitly named PCG64 seeds. Final registration must additionally freeze the mapping from analysis names to streams.

For each attempt, residual mode makes one `rng.integers(0, n-2, size=n-2)` call. Wild mode makes one `rng.integers(0, 2, size=n-2)` call and maps zero to -1 and one to +1. Recursion and episode detection consume no additional randomness. Initial values are x[0], x[1] in that order; the intercept is added at every generated step. Attempts are recorded with zero-based numbers.

## Statistic and counts

Observed episodes use the already tested run, merge and eligibility rules. Primary mode repeats that entire procedure for each surrogate. Fixed-onset mode instead evaluates every surrogate at the same observed eligible onset positions, without detecting its negative runs. The pre-onset path and statistic are otherwise identical.

Run exactly B attempted surrogate draws once an observed statistic and valid fitted null exist. Keep a per-attempt outcome record. Only a surrogate with no eligible episode is dropped as prescribed by the original plan; count it separately. Do not regenerate replacements until B successes are obtained. A numerical or fit failure is a different event: record it and invalidate the overall p-value. Continue the remaining attempted draws for an inspectable failure count; do not include partial failed statistics. No retries or alternative algorithms selected from results.

If the observed series has no eligible episode, the result is not estimable: S and p are None, B_attempted=0, and RNG state is unchanged. If B'=0 after otherwise valid draws, p is None. For finite S and B'>0 with zero failed draws, count every retained S_b >= S, including ties, and report p=(1+count)/(B'+1). Keep B_requested, B_attempted, B_retained, no_episode and failed distinct. The retained p-value grid has spacing 1/(B'+1); report it without calling it a confidence interval or an exact calibration guarantee.

The observed S, individual signed changes, eligible/ineligible onsets and p remain separate fields. Rejecting an upper-tail comparison does not assert that S is positive. No episode-bootstrap interval, secondary Kendall statistic, lag-1 comparison or scientific outcome branch is implemented here.

The accounting identity is attempted = retained + no_episode + failed. Fixed-onset comparisons retain the same observed eligible dates even when the surrogate has no negative run. This is a fitted-null bootstrap comparison, not an exact finite-sample randomization test: fitted parameters and endogenous eligibility selection require separate calibration. Dropping empty endogenous results conditions the retained reference distribution on having eligible episodes; the plus-one convention does not remove that issue.

## Completion criterion

Deterministic mechanics and failure accounting pass targeted tests, including explicit-loop recursion, residual/wild innovation reconstruction, fixed and endogenous onset routing, empty data-derived episodes, all ties/no exceedances/all exceedances, numerical failure and unchanged global RNG. A small fixed synthetic verification run saves full per-attempt evidence. No AT-15/AT-16 or substantive H1 claim follows from this milestone.
