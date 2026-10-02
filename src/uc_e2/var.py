"""E2 section 6: the intercept-inclusive OLS VAR(2) of every window and the companion spectral radius M(t).

The companion matrix and the spectral radius are the registered uc_core.linalg functions, imported unchanged.
With one variable (k = 1) the estimator is uc_core.ar.fit_ols and the path is uc_core.rolling.max_modulus.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from uc_core.linalg import spectral_radius as _spectral_radius, var_companion
from uc_core.rolling import RollingFitError

from .constants import WINDOW


# ----------------------------------------------------------------- section 6: estimator and indicator

def _observations(values, *, minimum=1):
    """A finite real (n, k) array; a one-dimensional input is one variable (k = 1)."""
    array = np.asarray(values)
    if np.iscomplexobj(array):
        raise ValueError("Expected real observations, not complex values")
    try:
        array = np.asarray(array, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError("Expected numeric real values") from error
    if array.ndim == 1:
        array = array[:, None]
    if array.ndim != 2 or array.shape[1] < 1 or array.shape[0] < minimum:
        raise ValueError("Expected an (n, k) array of observations")
    if not np.isfinite(array).all():
        raise ValueError("Non-finite values are not accepted; no implicit deletion or filling")
    return array


@dataclass(frozen=True)
class VARFit:
    intercept: tuple[float, ...]
    coefficients: tuple[tuple[tuple[float, ...], ...], ...]      # (A1, A2), each k x k, rows = equations
    n_observations: int
    n_regression_rows: int
    residuals: tuple[tuple[float, ...], ...]                     # (n - 2) x k
    modulus: float


def spectral_radius(coefficients) -> float:
    """Spectral radius of the VAR companion matrix [[A1, A2, ...], [I, 0, ...]] (uc_core.linalg).

    numpy.linalg.eigvals through uc_core.linalg.spectral_radius; nothing is clipped or projected.
    """
    return _spectral_radius(var_companion(coefficients))


def _fit_arrays(x):
    n, k = x.shape
    if n - 2 < 2 * k + 1:
        raise ValueError("Too few regression rows for an intercept-inclusive VAR(2)")
    lags = np.hstack((x[1:-1], x[:-2]))                 # columns: X[s-1] (k), then X[s-2] (k)
    response = x[2:]
    lag_means = lags.mean(axis=0)
    response_means = response.mean(axis=0)
    centered = lags - lag_means
    scales = np.sqrt(np.mean(centered ** 2, axis=0))
    if not np.isfinite(scales).all() or np.any(scales == 0):
        raise ValueError("Constant or non-finite lag columns: VAR(2) is not identifiable")
    solution, _, rank, _ = np.linalg.lstsq(centered / scales, response - response_means, rcond=None)
    if rank != 2 * k:
        raise ValueError(f"Rank-deficient lag matrix (rank {rank} < {2 * k}): VAR(2) is not identifiable")
    beta = solution / scales[:, None]
    intercept = response_means - lag_means @ beta
    a1, a2 = beta[:k].T, beta[k:].T
    if not (np.isfinite(beta).all() and np.isfinite(intercept).all()):
        raise ValueError("Non-finite fit; inspect input scale and conditioning")
    residuals = response - intercept - x[1:-1] @ a1.T - x[:-2] @ a2.T
    if not np.isfinite(residuals).all():
        raise ValueError("Non-finite residuals")
    modulus = spectral_radius([a1, a2])
    if not math.isfinite(modulus):
        raise ValueError("Non-finite companion spectral radius")
    return intercept, a1, a2, residuals, modulus


def fit_var2(values) -> VARFit:
    """Section 6: intercept-inclusive multivariate OLS VAR(2); the first two vectors serve only as lags.

    H1 section 4 numerics for 2k lag columns: centre and root-mean-square-scale each lag column, solve for
    all k responses with one numpy lstsq(rcond=None) call, undo the scaling, recover the intercepts from the
    means. Requires lag-block rank 2k and finite coefficients and residuals; unstable fits are retained.
    With k = 1 this is uc_core.ar.fit_ols (tested).
    """
    x = _observations(values, minimum=3)
    intercept, a1, a2, residuals, modulus = _fit_arrays(x)
    return VARFit(tuple(map(float, intercept)), (tuple(map(tuple, a1.tolist())), tuple(map(tuple, a2.tolist()))),
                  len(x), len(x) - 2, tuple(map(tuple, residuals.tolist())), float(modulus))


def _window(window):
    if isinstance(window, (bool, np.bool_)) or not isinstance(window, (int, np.integer)) or window < 5:
        raise ValueError("window must be an integer of at least five observations")
    return int(window)


def rolling_var2(values, window=WINDOW):
    """One within-window fit ending at each t >= W - 1 (causal). Earlier positions are warm-up (NaN).

    Returns dict(modulus (n,), intercept (n, k), A1 (n, k, k), A2 (n, k, k)). A failed non-warm-up window
    raises RollingFitError with its endpoint; no window is dropped.
    """
    window = _window(window)
    x = _observations(values)
    n, k = x.shape
    modulus = np.full(n, np.nan)
    intercepts = np.full((n, k), np.nan)
    a1s, a2s = np.full((n, k, k), np.nan), np.full((n, k, k), np.nan)
    for end in range(window - 1, n):
        try:
            intercept, a1, a2, _, radius = _fit_arrays(x[end - window + 1:end + 1])
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
            raise RollingFitError(f"VAR(2) window ending at position {end}: {error}") from error
        modulus[end], intercepts[end], a1s[end], a2s[end] = radius, intercept, a1, a2
    return dict(modulus=modulus, intercept=intercepts, A1=a1s, A2=a2s)


def max_modulus(values, window=WINDOW) -> np.ndarray:
    """The causal companion spectral-radius path M(t); NaN before position W - 1."""
    return rolling_var2(values, window)["modulus"]
