"""S1: the Yule centenary on SILSO Version 1 and Version 2 yearly sunspot numbers.

Conventions are fixed in DECISIONS.md D-018 before any fit was computed:
two SILSO files, two samples per version, the programme's least-squares and
Yule-Walker estimators, and a residual bootstrap of B=4,000 per fit with
explicit PCG64 streams. No UK observation is used.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np

from .ar import ARFit, fit_ols, fit_yw
from .surrogate import simulate_ar2

MASTER_SEED = 1927
BOOTSTRAP_STREAM = 1001
AT13_STREAM = 1013
BOOTSTRAP_B = 4000
EARLY = (1749, 1924)
LATE_START = 1925
VERSIONS = ('V1', 'V2')
METHODS = ('ols', 'yw')
ESTIMATORS = {'ols': fit_ols, 'yw': fit_yw}
LONG_SERIES_LENGTH = 200_000
NUMERIC_ERRORS = (ValueError, FloatingPointError, np.linalg.LinAlgError)


@dataclass(frozen=True)
class YearlySeries:
    version: str
    years: tuple[int, ...]
    values: tuple[float, ...]
    definitive: tuple[bool, ...] | None

    def sample(self, start: int, end: int) -> np.ndarray:
        years = np.asarray(self.years)
        mask = (years >= start) & (years <= end)
        selected = years[mask]
        if selected.size != end - start + 1 or not np.array_equal(selected, np.arange(start, end + 1)):
            raise ValueError(f'{self.version} lacks contiguous years {start}-{end}')
        return np.asarray(self.values, dtype=float)[mask]

    @property
    def last_year(self) -> int:
        return self.years[-1]


def _year(mid_year: str) -> int:
    value = float(mid_year)
    if value - math.floor(value) != 0.5:
        raise ValueError(f'Expected a mid-year time stamp, found {mid_year!r}')
    return int(math.floor(value))


def read_v2(path) -> YearlySeries:
    """SILSO SN_y_tot_V2.0.csv: year.5; mean; std; observations; definitive flag."""
    years, values, definitive = [], [], []
    for line in Path(path).read_text(encoding='ascii').splitlines():
        if not line.strip():
            continue
        fields = [field.strip() for field in line.split(';')]
        if len(fields) != 5:
            raise ValueError(f'Unexpected V2 row: {line!r}')
        years.append(_year(fields[0]))
        values.append(float(fields[1]))
        definitive.append(fields[4] == '1')
    return _checked('V2', years, values, definitive)


def read_v1(path) -> YearlySeries:
    """SILSO archive yearssn.dat (Version 1.0, frozen 2015): year.5 and mean."""
    years, values = [], []
    for line in Path(path).read_text(encoding='ascii').splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 2:
            raise ValueError(f'Unexpected V1 row: {line!r}')
        years.append(_year(fields[0]))
        values.append(float(fields[1]))
    return _checked('V1', years, values, None)


def _checked(version, years, values, definitive):
    if years != list(range(years[0], years[0] + len(years))):
        raise ValueError(f'{version} years are not contiguous')
    array = np.asarray(values)
    if not np.isfinite(array).all() or (array < 0).any():
        raise ValueError(f'{version} contains missing or negative yearly means')
    return YearlySeries(version, tuple(years), tuple(map(float, values)),
                        None if definitive is None else tuple(definitive))


def samples(series: YearlySeries) -> dict[str, tuple[int, int]]:
    """The two S1 samples: Yule's 1749-1924, and 1925 to the version's last complete year."""
    return {'1749-1924': EARLY, f'1925-{series.last_year}': (LATE_START, series.last_year)}


def fit_row(series: YearlySeries, label: str, start: int, end: int, method: str) -> dict:
    x = series.sample(start, end)
    fit = ESTIMATORS[method](x)
    d = fit.diagnostics
    return dict(version=series.version, sample=label, start=start, end=end, n=len(x), method=method,
                phi1=fit.coefficients[0], phi2=fit.coefficients[1], intercept=fit.intercept,
                modulus=d.modulus, period=d.period, half_life=d.half_life,
                complex_pair=d.complex_pair, stable=d.stable)


def fit_plan(v1: YearlySeries, v2: YearlySeries) -> list[tuple[YearlySeries, str, int, int, str]]:
    """Fixed order of the eight fits; fit k uses bootstrap stream (1927, 1001, k)."""
    plan = []
    for series in (v1, v2):
        for label, (start, end) in samples(series).items():
            for method in METHODS:
                plan.append((series, label, start, end, method))
    return plan


def centered_residuals(fit: ARFit) -> np.ndarray:
    residuals = np.asarray(fit.residuals, dtype=float)
    return residuals - residuals.mean()


def residual_bootstrap(x, method: str, rng: np.random.Generator, B: int = BOOTSTRAP_B) -> dict:
    """Resample centred fitted residuals with replacement; rebuild from the first two
    observed values with the fitted coefficients and intercept; refit by the same method."""
    x = np.asarray(x, dtype=float)
    fit = ESTIMATORS[method](x)
    if not fit.diagnostics.stable:
        raise ValueError('Bootstrap requires a strictly stable fit; no projection is applied')
    residuals = centered_residuals(fit)
    draws = np.full((B, 4), np.nan)  # phi1, phi2, modulus, period (nan if real roots)
    complex_pair = np.zeros(B, dtype=bool)
    failed = 0
    for b in range(B):
        innovations = residuals[rng.integers(0, len(residuals), size=len(residuals))]
        try:
            refit = ESTIMATORS[method](simulate_ar2(fit.coefficients, fit.intercept, x[:2], innovations))
        except NUMERIC_ERRORS:
            failed += 1
            continue
        d = refit.diagnostics
        complex_pair[b] = d.complex_pair
        draws[b] = (refit.coefficients[0], refit.coefficients[1], d.modulus,
                    d.period if d.period is not None else np.nan)
    return dict(fit=fit, draws=draws, complex_pair=complex_pair, failed=failed, B=B)


def band(values) -> tuple[float, float] | None:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    low, high = np.percentile(values, [2.5, 97.5])
    return float(low), float(high)


def bootstrap_summary(result: dict) -> dict:
    draws, complex_pair = result['draws'], result['complex_pair']
    valid = np.isfinite(draws[:, 2])
    return dict(B=result['B'], failed=result['failed'], valid=int(valid.sum()),
                complex=int(complex_pair.sum()), real=int((valid & ~complex_pair).sum()),
                modulus_band=band(draws[valid, 2]), period_band=band(draws[complex_pair, 3]))


def stream(k: int, stream_id: int = BOOTSTRAP_STREAM) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([MASTER_SEED, stream_id, k])))


def asymptotic_se(phi1: float, phi2: float, n: int) -> tuple[float, float]:
    """Square roots of the diagonal of Sigma/n for the AR(2) least-squares estimator."""
    variance = (1 - phi2 * phi2) / n
    return math.sqrt(variance), math.sqrt(variance)


def at13(values) -> dict:
    """AT-13 on the statsmodels yearly series, 1749-1924, least squares (D-018 criteria)."""
    x = np.asarray(values, dtype=float)
    result = residual_bootstrap(x, 'ols', stream(0, AT13_STREAM))
    summary = bootstrap_summary(result)
    fit = result['fit']
    rng = stream(1, AT13_STREAM)
    residuals = centered_residuals(fit)
    innovations = residuals[rng.integers(0, len(residuals), size=LONG_SERIES_LENGTH - 2)]
    long_fit = fit_ols(simulate_ar2(fit.coefficients, fit.intercept, x[:2], innovations))
    se = asymptotic_se(*fit.coefficients, LONG_SERIES_LENGTH)
    z = [(long_fit.coefficients[i] - fit.coefficients[i]) / se[i] for i in range(2)]
    period, modulus = summary['period_band'], summary['modulus_band']
    checks = {
        'period_lower_rounds_to_9.3': period is not None and 9.25 <= period[0] < 9.35,
        'period_upper_in_12.2_to_12.3': period is not None and 12.15 <= period[1] < 12.35,
        'modulus_lower_rounds_to_0.72': modulus is not None and 0.715 <= modulus[0] < 0.725,
        'modulus_upper_rounds_to_0.87': modulus is not None and 0.865 <= modulus[1] < 0.875,
        'every_replicate_complex': summary['complex'] == summary['B'] and summary['failed'] == 0,
        'long_series_within_3_se': all(abs(value) <= 3 for value in z),
    }
    return dict(fit=dict(phi1=fit.coefficients[0], phi2=fit.coefficients[1], intercept=fit.intercept,
                         modulus=fit.diagnostics.modulus, period=fit.diagnostics.period),
                bootstrap=summary,
                long_series=dict(length=LONG_SERIES_LENGTH, phi1=long_fit.coefficients[0],
                                 phi2=long_fit.coefficients[1], z=z),
                checks=checks, passed=all(checks.values()))
