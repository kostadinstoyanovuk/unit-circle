# M1a core conventions

The local `src/uc_core` implementation is research code, not yet the separately released C5 package. It is independent of `tools/audit_baseline.py`, which remains the audit reference. Scope is real AR(2) with an intercept; arbitrary AR order is deferred to the package design.

- Select the full input interval before forming lags. Use its first two observations only as lags. Require at least five finite real values; reject missing, complex, constant or rank-deficient input rather than repairing it silently.
- OLS minimizes the intercept-inclusive sum of squared residuals. Centering/scaling the lag columns improves numerical conditioning without changing that objective. Record both stored observation count and regression-row count. No stationarity projection or coefficient clipping occurs.
- Yule-Walker removes the interval mean, uses a common sum-of-squares denominator for both autocorrelations, solves the two-equation system and returns the implied intercept. Conditional residuals are returned but not automatically centered for resampling; surrogate centering is a later explicit decision.
- Roots solve `z^2 - phi1*z - phi2 = 0`. The stability diagnostic uses the strict open triangle. Eigenvalue and triangle comparisons near floating-point boundaries require separate treatment; this is not an exact arithmetic certificate.
- Period is assigned only to a nonreal conjugate pair, in sampling intervals. Negative real roots can alternate but receive no complex-pair period. A repeated real root receives no period.
- Half-life is the modulus-envelope decay half-life for `0 < M < 1`. At M=0, use the limiting value 0. Unit or explosive roots receive `None`, not a negative decay time.
- A stationary spectral-peak diagnostic is available only for a strictly stable fit. It is `None` otherwise. For stable models, the original strict interior-peak inequality is used; endpoint peaks do not count.
- Returned fits use immutable tuples for coefficients and residuals and a frozen dataclass. Inputs are not mutated. pandas Series are accepted; an estimator's parameter result has no time index. Rolling outputs will preserve the input index in M1b.

The proof in `proof/triangle.md` establishes the mathematical region; it is a paper proof, not Lean verification. A rendered proof and M1a execution record accompany the final checkpoint. No registered simulation cell or real UK dataset is needed for these tests.
