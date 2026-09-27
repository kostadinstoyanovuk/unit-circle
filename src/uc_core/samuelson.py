"""S2: the Samuelson reading of an AR(2) fitted to detrended output, a check and not a result (D-021).

Three detrending filters of 100 ln Y: a linear trend, the Hodrick-Prescott
filter with lambda = 1600 and Hamilton's regression filter (h = 8, p = 4).
An intercept-inclusive AR(2) fitted to each cycle gives the implied
multiplier-accelerator parameters c = phi1 + phi2 and v = -phi2 / (phi1 + phi2),
with oscillation when c > 0 and c (1 + v)^2 < 4 v.
"""
from __future__ import annotations

import math

import numpy as np

from .ar import _real_vector, fit_ols

HP_LAMBDA = 1600
HAMILTON_H, HAMILTON_P = 8, 4
FILTERS = ('linear trend', 'Hodrick-Prescott (lambda = 1600)', 'Hamilton regression (h = 8, p = 4)')


def linear_cycle(y) -> np.ndarray:
    y = _real_vector(y, minimum=3)
    t = np.arange(len(y), dtype=float)
    design = np.column_stack((np.ones_like(t), t))
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    return y - design @ coefficients


def hp_cycle(y, lamb: float = HP_LAMBDA) -> np.ndarray:
    from statsmodels.tsa.filters.hp_filter import hpfilter
    cycle, trend = hpfilter(_real_vector(y, minimum=5), lamb=lamb)
    return np.asarray(cycle, dtype=float)


def hamilton_cycle(y, h: int = HAMILTON_H, p: int = HAMILTON_P) -> np.ndarray:
    """Residuals of y[t+h] on (1, y[t], ..., y[t-p+1]); the first p+h-1 positions have no cycle."""
    y = _real_vector(y, minimum=h + p + 2)
    rows = range(p - 1, len(y) - h)
    design = np.array([[1.0, *y[t - np.arange(p)]] for t in rows])
    response = np.array([y[t + h] for t in rows])
    coefficients, _, rank, _ = np.linalg.lstsq(design, response, rcond=None)
    if rank != p + 1:
        raise ValueError('Hamilton regression is rank deficient')
    return response - design @ coefficients


def samuelson(phi1: float, phi2: float) -> dict:
    """Implied marginal propensity c, accelerator v and whether the cycle oscillates."""
    c = phi1 + phi2
    if not c > 0:
        return dict(c=c, v=None, oscillates=None, note='c <= 0: outside the multiplier-accelerator reading')
    v = -phi2 / c
    return dict(c=c, v=v, oscillates=bool(c * (1 + v) ** 2 < 4 * v), note=None)


def s2_rows(levels) -> list[dict]:
    """One row per filter for 100 ln Y of the given positive levels."""
    levels = _real_vector(levels, minimum=20)
    if (levels <= 0).any():
        raise ValueError('Levels must be positive')
    y = 100 * np.log(levels)
    rows = []
    for name, cycle in zip(FILTERS, (linear_cycle(y), hp_cycle(y), hamilton_cycle(y))):
        fit = fit_ols(cycle)
        d = fit.diagnostics
        reading = samuelson(*fit.coefficients)
        rows.append(dict(filter=name, cycle_observations=len(cycle), phi1=fit.coefficients[0], phi2=fit.coefficients[1],
                         modulus=d.modulus, complex_roots=d.complex_pair,
                         period_quarters=d.period, **reading))
    return rows
