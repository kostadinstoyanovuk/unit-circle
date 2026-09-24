"""AR(2) estimators and companion-root conventions fixed by the programme.

No estimator constrains a fit to the stationary region. Undefined period,
half-life or stationary spectrum diagnostics are represented by None.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class RootSummary:
    roots: tuple[complex, complex]
    modulus: float
    discriminant: float
    stable: bool
    complex_pair: bool
    period: float | None
    half_life: float | None
    spectral_peak: bool | None
    peak_frequency: float | None


@dataclass(frozen=True)
class ARFit:
    method: str
    coefficients: tuple[float, float]
    intercept: float
    n_observations: int
    n_regression_rows: int
    residuals: tuple[float, ...]
    diagnostics: RootSummary


def _real_vector(values, *, length: int | None = None, minimum: int = 0) -> np.ndarray:
    array = np.asarray(values)
    if np.iscomplexobj(array):
        raise ValueError("Expected real observations or coefficients, not complex values")
    try:
        array = np.asarray(array, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError("Expected numeric real values") from error
    if array.ndim != 1 or (length is not None and array.size != length) or array.size < minimum:
        raise ValueError("Invalid one-dimensional input length")
    if not np.isfinite(array).all():
        raise ValueError("Non-finite values are not accepted; no implicit deletion or filling")
    return array


def in_triangle(phi1: float, phi2: float) -> bool:
    """Strict open stability triangle; floating-point classification, no tolerance."""
    a, b = _real_vector([phi1, phi2], length=2)
    return bool(a + b < 1 and b - a < 1 and b > -1)


def root_summary(coefficients) -> RootSummary:
    """Companion roots of z^2-phi1*z-phi2, not lag-polynomial reciprocals.

    Period and half-life are in sampling intervals. A negative real root may
    alternate in sign, but receives no complex-pair period. Zero memory has
    half-life 0 by the limiting convention. No decay half-life is assigned to
    unit or explosive roots. Spectrum diagnostics require strict stability.
    """
    a, b = map(float, _real_vector(coefficients, length=2))
    discriminant = a * a + 4 * b
    if not math.isfinite(discriminant):
        raise ValueError("Coefficient magnitude overflows root calculations")
    complex_pair = discriminant < 0
    if complex_pair:
        radius = math.sqrt(-b)
        theta = math.atan2(math.sqrt(-discriminant), a)
        roots = (complex(a / 2, math.sqrt(-discriminant) / 2),
                 complex(a / 2, -math.sqrt(-discriminant) / 2))
        period = 2 * math.pi / theta
    else:
        # Use the product for the smaller root to avoid subtractive cancellation.
        large = (a + math.copysign(math.sqrt(discriminant), a)) / 2
        small = -b / large if large != 0 else 0.0
        roots = (complex(large), complex(small))
        radius = max(abs(large), abs(small))
        period = None
    stable = in_triangle(a, b)
    half_life = (0.0 if radius == 0 else math.log(2) / -math.log(radius)) if 0 <= radius < 1 else None
    if stable:
        has_peak = b < 0 and abs(a) * (1 - b) < -4 * b
        frequency = math.acos(max(-1.0, min(1.0, a * (b - 1) / (4 * b)))) if has_peak else None
    else:
        has_peak, frequency = None, None
    return RootSummary(roots, radius, discriminant, stable, complex_pair,
                       period, half_life, has_peak, frequency)


def _fit_result(method: str, x: np.ndarray, phi: np.ndarray, intercept: float) -> ARFit:
    if not np.isfinite(phi).all() or not math.isfinite(intercept):
        raise ValueError("Non-finite fit; inspect input scale and conditioning")
    residuals = x[2:] - intercept - phi[0] * x[1:-1] - phi[1] * x[:-2]
    if not np.isfinite(residuals).all():
        raise ValueError("Non-finite residuals")
    coefficients = tuple(map(float, phi))
    return ARFit(method, coefficients, float(intercept), len(x), len(x) - 2,
                 tuple(map(float, residuals)), root_summary(coefficients))


def fit_ols(values) -> ARFit:
    """Intercept-inclusive least squares, with the first two values used as lags.

    Center and scale lag columns before solving; recover the intercept from
    means. This is the same least-squares objective, not a different estimator.
    Rank-deficient series raise ValueError; unstable coefficients are retained.
    """
    x = _real_vector(values, minimum=5)
    lags = np.column_stack((x[1:-1], x[:-2]))
    lag_means = lags.mean(axis=0)
    y_mean = float(x[2:].mean())
    centered = lags - lag_means
    scales = np.sqrt(np.mean(centered**2, axis=0))
    if not np.isfinite(scales).all() or np.any(scales == 0):
        raise ValueError("Constant or non-finite lag columns: AR(2) is not identifiable")
    solution, _, rank, _ = np.linalg.lstsq(centered / scales, x[2:] - y_mean, rcond=None)
    if rank != 2:
        raise ValueError("Rank-deficient lag matrix: AR(2) is not identifiable")
    phi = solution / scales
    return _fit_result("ols", x, phi, y_mean - float(lag_means @ phi))


def fit_yw(values) -> ARFit:
    """Demeaned Yule-Walker with one common full-sample denominator.

    Intercept is mean(x)*(1-sum(phi)); returned residuals are conditional on
    the first two observations and need not have zero mean for this estimator.
    """
    x = _real_vector(values, minimum=5)
    mean = float(x.mean())
    centered = x - mean
    scale = float(np.max(np.abs(centered)))
    if scale == 0 or not math.isfinite(scale):
        raise ValueError("Yule-Walker requires finite nonconstant observations")
    centered = centered / scale
    energy = float(centered @ centered)
    r1 = float(centered[1:] @ centered[:-1]) / energy
    r2 = float(centered[2:] @ centered[:-2]) / energy
    denominator = 1 - r1 * r1
    if denominator <= 0:
        raise ValueError("Singular Yule-Walker system")
    phi = np.array([(r1 - r1 * r2) / denominator, (r2 - r1 * r1) / denominator])
    return _fit_result("yw", x, phi, mean * (1 - float(phi.sum())))
