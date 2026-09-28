# M0 baseline acceptance-target audit

Completed 2026-09-24. **AT-1, AT-2, AT-3, AT-4 and AT-6 pass at the original plan's tolerances.** The covariance and delta-method expressions, the repeated-root boundary variance, and the strict distinction between complex roots and an interior spectral peak have also been checked by exact symbolic algebra. These algebra checks do not pass AT-9, AT-10 or AT-17, which require additional numerical experiments.

The authoritative targets are Appendix A, pp. 21-22, with the algebra on pp. 13-14 and 22, of the preserved `../Unit_Circle_Programme_Plan.pdf`. Its SHA-256 matches `85a594b0baf6d7b5a72d3ca1ec856f0df06b1106aaf3319e48f5b3967854dde7`.

## Reproduce

From the `unit-circle` directory in PowerShell:

```powershell
& .venv/Scripts/python.exe tools/audit_baseline.py
```

This writes `audit/baseline_results.json` and exits nonzero if a present original PDF has the wrong hash, or if specified acceptance checks or symbolic identities fail. A clone without the parent PDF can reproduce the numerical checks, but records source verification as unavailable and never claims a hash match. The JSON records full floating-point results, every stated target and tolerance, errors, input hashes, package versions and the audit script hash. It has no timestamp, so a repeat in the same environment produces identical evidence.

Run the focused tests separately:

```powershell
& .venv/Scripts/python.exe -m pytest tests/test_audit_baseline.py -q
```

Initial run: **10 passed in 2.15 seconds**. The final suite includes two further source-provenance tests, making 12 tests; the final run is recorded in `m0_verification.json`. Run time is an observation, not a performance promise.

## Data and sample conventions

Only `statsmodels.datasets.sunspots` bundled with the installed package is loaded. No network request is made. No UK GDP, unemployment or vintage observations are loaded, and no Monte Carlo or Paper II registered simulation cell is run.

- The full bundled series covers 1700-2008, 309 annual observations. The audit is a reproduction of the specified statsmodels targets, not an independent reconstruction of Yule's historical input series.
- AT-1 and AT-2 select 1749-1924 inclusively, 176 values. Least squares uses outcomes in 1751-1924: 174 regression rows. The first two selected observations supply lags only.
- AT-3 selects 1925-2008 inclusively, 84 values, and uses outcomes in 1927-2008: 82 regression rows. It does not import lag observations from 1923-1924.
- Least squares includes an intercept and fits `x[2:]` against columns `1`, `x[1:-1]`, `x[:-2]`.
- Yule-Walker removes the full selected sample mean and divides every lag cross-product sum by the same full sum of centered squares. A lag-adjusted denominator estimates a different quantity and does not reproduce this convention.
- Roots solve `lambda^2 - phi1*lambda - phi2 = 0`. They are the companion eigenvalues, not their reciprocals. Period is `2*pi/theta` for the complex pair, with theta in radians; half-life is `ln(2)/(-ln(M))` when `0 < M < 1`.

The array digest encoding is fixed as little-endian IEEE-754 float64, row-major bytes, with each row containing year then activity. SHA-256 values:

| Input | SHA-256 |
|---|---|
| Full 1700-2008 year/value array | `8079d305fa3cb6b7bb916342bf69900a2cd9df93634e3db3153f8e4a9d72964a` |
| 1749-1924 year/value array | `b6f242da36c8894a60c24f03b3601a5dca2ab46c6de1f05e28779f34eb3e2c95` |
| 1925-2008 year/value array | `4025f6848f2c67269cf0ff5e5c2a334b081b464da0c7b21cf0b73e150414abf7` |
| Bundled sunspots CSV file | `df04b629a69bc68611a4d1d1a8cf7a3a9b10d43a003693c22d7baac56a17bc46` |

## Numerical findings

Values below are rounded for reading; the JSON retains full precision. Plan tolerances are absolute: 0.001 for coefficients/moduli, 0.01 years for periods, and 0.1 years for half-lives.

| Acceptance test | Computed | Plan target | Result |
|---|---|---|---|
| AT-1, OLS 1749-1924 | phi=(1.3359496152, -0.6498534686); M=0.8061348948; period=10.5747503750 y; half-life=3.2163977391 y | (1.336, -0.650); 0.806; 10.57 y; 3.2 y | Pass |
| AT-2, Yule-Walker 1749-1924 | phi=(1.3262603368, -0.6418867558); M=0.8011783545; period=10.5455985790 y | (1.326, -0.642); 0.801; 10.55 y | Pass |
| AT-3, OLS 1925-2008 | phi=(1.4138646331, -0.7623731048); M=0.8731397968; period=10.0170163383 y | (1.414, -0.762); 0.873; 10.02 y | Pass |
| AT-4, OLS on x/0.6+5 | absolute coefficient changes=(2.22e-16, 1.11e-16) | Both no greater than 1e-6 | Pass |
| AT-6, complex-pair modulus | sqrt(-phi2)=0.8061348948 | 0.806 | Pass |

An extra AT-6 audit check compares the formula to independently computed polynomial roots at tolerance 1e-12; the absolute difference is 1.11e-16. This extra tolerance is identified as an audit check rather than a change to the plan.

## Exact algebra findings

For stationary AR(2), write rho1=phi1/(1-phi2), rho2=phi1*rho1+phi2, and gamma0=innovation_variance/(1-phi1*rho1-phi2*rho2). Let the lag covariance matrix be gamma0 times the 2-by-2 matrix with diagonal 1 and off-diagonal rho1. Symbolic inversion verifies that innovation variance times its inverse equals the plan's Sigma. This checks the covariance identity given the Yule-Walker relations; it does not prove the probabilistic limiting theorem or its assumptions.

For D=phi1^2+4*phi2, the gradient is (2*phi1,4). The exact residual between its quadratic form with Sigma and the plan's expression

`4*(1+phi2)*(4*(1-phi2)-phi1^2*(3+phi2))`

is zero. Substituting the repeated-root boundary phi2=-phi1^2/4 gives `(4-phi1^2)^3/4` exactly. The stationary part of this boundary has `abs(phi1)<2`.

| phi1 | Exact boundary variance | Decimal | Plan display |
|---|---|---|---|
| 0 | 16 | 16.0 | 16.0 |
| 4/5 | 148176/15625 | 9.483264 | 9.48 |
| 7/5 | 132651/62500 | 2.122416 | 2.12 |

The algebra also verifies

`-4*phi2 - (4*phi2/(1-phi2))^2 = -4*phi2*(1+phi2)^2/(1-phi2)^2`.

For phi2<0 the right side is nonnegative. Thus the strict spectral-peak inequality implies the complex-root inequality. At the plan's stationary example (phi1,phi2)=(1,-3/10), D=-1/5 while the spectral-peak margin is -1/10. Its stability-triangle margins are 3/10, 23/10 and 7/10, all positive. It has complex roots and no interior spectral peak, establishing strict inclusion within the stationary domain. This is exact algebra with an explicit sign argument, not a random numerical proof or a machine-checked Lean theorem.

## Verification scope and remaining work

The tests independently cross-check least squares against statsmodels AutoReg and Yule-Walker against statsmodels' common-denominator method. They also check known real/complex roots, sign and reciprocal conventions, sample sizes, affine invariance including the intercept transformation, and rejection of invalid/nonidentifiable inputs. A status test prevents the current audit from silently relabelling incomplete Monte Carlo checks as passed.

The first test run found an obsolete `old_names` argument in the test's AutoReg cross-check against statsmodels 0.15.0. The unnecessary argument was removed. Yule-Walker's explicit return-format option was added to remove its future-change warning. The audit estimates themselves were unchanged; the second test run passed without warnings.

AT-9, AT-10 and AT-17 are **partial: algebra only**. AT-5, AT-7, AT-8, AT-11 through AT-16, and AT-18 through AT-21 are **not run**. The prescribed Monte Carlo sample sizes, spectral grid, bootstrap checks, general-degree polynomial checks, Kalman/VAR checks and empirical pipeline checks remain separate work. None of G0-G7 is passed by this audit.

Update, 28 September 2026: AT-9 and AT-17 have passed, and AT-18 has passed for n >= 250 ([C3.T acceptance record](C3T_ACCEPTANCE.md); DECISIONS.md D-029). AT-8, AT-11 and AT-12 are recorded in [FOUNDATIONS_REPORT.md](FOUNDATIONS_REPORT.md) and AT-13 in [S1_TABLE.md](S1_TABLE.md). AT-5, AT-15 and AT-16 are the registered validation experiments, which are running.

Recorded environment: Python 3.12.14; NumPy 2.5.3; SciPy 1.18.1; pandas 3.0.6; statsmodels 0.15.0; SymPy 1.14.0; pytest 9.1.1. The repository's environment lock is the installation record; this JSON is the runtime record.
