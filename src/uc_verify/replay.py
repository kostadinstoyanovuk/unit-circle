"""An independent second implementation of the registered H1 computations, for review only.

Written from the text of prereg/H1.md, sections 4-6 and 9, using NumPy alone; it imports
nothing from uc_core. It regenerates the registered synthetic series from their stream
coordinates, refits every rolling window, re-detects recessions, redraws every residual
surrogate and recomputes S, p and the cell summaries, so that the G2 review does not rest
on the implementation it is checking. Least squares is solved in closed form on centred
columns, a different numerical route from the frozen code, so agreement is to rounding.
"""
import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

MASTER_SEED = 1927
Z = 1.959963984540054
POWER_ONSETS = (49, 99, 149, 199, 249)  # one-based quarters 50, 100, ..., 250
BASE = (0.3, 0.1, 1.5)                   # a, b, c of the registered generating recursion
INNOVATION_SD = 3.5
LENGTH = 259


def generator(stream, cell, replicate, master_seed=MASTER_SEED):
    """PCG64 from SeedSequence([master seed, stream, cell, replicate]) (section 3 of the protocol)."""
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([master_seed, stream, cell, replicate])))


def design_series(rng, kappa, planted_onsets):
    """Section 9: stationary initial pair, 257 Gaussian innovations, eight planted quarters per onset."""
    a, b, c = BASE
    mu = c / (1 - a - b)
    v = INNOVATION_SD ** 2 * (1 - b) / ((1 + b) * ((1 - b) ** 2 - a ** 2))
    h = a * v / (1 - b)
    z0, z1 = rng.standard_normal(2)
    x = np.empty(LENGTH)
    x[0] = mu + math.sqrt(v) * z0
    x[1] = mu + (h / math.sqrt(v)) * z0 + math.sqrt(v - h * h / v) * z1
    innovations = rng.normal(0, INNOVATION_SD, size=LENGTH - 2)
    planted = {t for r in planted_onsets for t in range(r - 8, r)}
    ak, bk = kappa * a, kappa ** 2 * b
    ck = mu * (1 - ak - bk)
    for t in range(2, LENGTH):
        if t in planted:
            x[t] = ck + ak * x[t - 1] + bk * x[t - 2] + innovations[t - 2]
        else:
            x[t] = c + a * x[t - 1] + b * x[t - 2] + innovations[t - 2]
    return x


def ols_ar2(windows):
    """Intercept-inclusive AR(2) by closed-form least squares on centred columns.

    windows has shape (..., n); responses are positions 2..n-1. Returns phi1, phi2, intercept.
    """
    y, l1, l2 = windows[..., 2:], windows[..., 1:-1], windows[..., :-2]
    my, m1, m2 = y.mean(-1), l1.mean(-1), l2.mean(-1)
    yc, c1, c2 = y - my[..., None], l1 - m1[..., None], l2 - m2[..., None]
    s11, s22, s12 = (c1 * c1).sum(-1), (c2 * c2).sum(-1), (c1 * c2).sum(-1)
    s1y, s2y = (c1 * yc).sum(-1), (c2 * yc).sum(-1)
    det = s11 * s22 - s12 * s12
    phi1 = (s22 * s1y - s12 * s2y) / det
    phi2 = (s11 * s2y - s12 * s1y) / det
    return phi1, phi2, my - phi1 * m1 - phi2 * m2


def modulus(phi1, phi2):
    """Largest companion-root modulus, section 4."""
    phi1, phi2 = np.asarray(phi1, float), np.asarray(phi2, float)
    d = phi1 * phi1 + 4 * phi2
    with np.errstate(invalid='ignore', divide='ignore'):
        big = (phi1 + np.copysign(np.sqrt(np.where(d >= 0, d, 0.)), phi1)) / 2
        small = np.where(big != 0, -phi2 / np.where(big != 0, big, 1.), 0.)
        real = np.maximum(np.abs(big), np.abs(small))
        return np.where(d < 0, np.sqrt(np.where(d < 0, -phi2, 0.)), real)


def rolling_modulus(series, window=40):
    """M(t) for each window ending at t = W-1, ..., n-1 (index 0 of the result is t = W-1)."""
    phi1, phi2, _ = ols_ar2(sliding_window_view(np.asarray(series, float), window, axis=-1))
    return modulus(phi1, phi2)


def episodes(growth, merge=8):
    """Qualifying runs of two or more negative quarters, merged when onset - previous end <= merge."""
    negative = np.asarray(growth) < 0
    runs, t, n = [], 0, len(negative)
    while t < n:
        if negative[t]:
            start = t
            while t + 1 < n and negative[t + 1]:
                t += 1
            if t > start:
                runs.append((start, t))
        t += 1
    merged = []
    for start, end in runs:
        if merged and start - merged[-1][1] <= merge:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return [tuple(e) for e in merged]


def statistic(moduli, onsets, window=40, lookback=8):
    """S over eligible onsets; moduli[k] is M(W-1+k). Returns (S or None, eligible onsets, changes)."""
    eligible = [r for r in onsets if r - lookback - 1 >= window - 1]
    if not eligible:
        return None, [], []
    changes = [float(moduli[r - 1 - (window - 1)] - moduli[r - lookback - 1 - (window - 1)]) for r in eligible]
    return float(np.mean(changes)), eligible, changes


def fitted_null(series):
    """Full-sample OLS AR(2), strict stability check and centred residuals (section 6)."""
    x = np.asarray(series, float)
    phi1, phi2, c = (float(v) for v in ols_ar2(x))
    stable = phi1 + phi2 < 1 and phi2 - phi1 < 1 and phi2 > -1 and float(modulus(phi1, phi2)) < 1
    residuals = x[2:] - c - phi1 * x[1:-1] - phi2 * x[:-2]
    return dict(phi1=phi1, phi2=phi2, intercept=c, stable=stable, residuals=residuals - residuals.mean())


def surrogates(series, null, rng, B=1000):
    """B residual surrogates; one integers(0, 257, size=257) call per draw, in draw order."""
    x = np.asarray(series, float)
    n = len(x)
    draws = np.stack([rng.integers(0, n - 2, size=n - 2) for _ in range(B)])
    out = np.empty((B, n))
    out[:, 0], out[:, 1] = x[0], x[1]
    e = null['residuals'][draws]
    for t in range(2, n):
        out[:, t] = null['intercept'] + null['phi1'] * out[:, t - 1] + null['phi2'] * out[:, t - 2] + e[:, t - 2]
    return out


def comparison(series, rng, *, fixed_onsets=None, B=1000, window=40, lookback=8, chunk=250):
    """Observed S, fitted null and every surrogate statistic; p = (1+K)/(B'+1)."""
    x = np.asarray(series, float)
    onsets = list(fixed_onsets) if fixed_onsets is not None else [e[0] for e in episodes(x)]
    S, eligible, changes = statistic(rolling_modulus(x, window), onsets, window, lookback)
    result = dict(S=S, eligible_onsets=eligible, changes=changes, attempts=[], p_value=None, retained=0,
                  no_episode=0, exceedances=None, stable=None, null=None)
    if S is None:
        return result
    null = fitted_null(x)
    result['stable'] = null['stable']
    result['null'] = [null['phi1'], null['phi2'], null['intercept']]
    if not null['stable']:
        return result
    paths = surrogates(x, null, rng, B)
    for first in range(0, B, chunk):
        block = paths[first:first + chunk]
        moduli = rolling_modulus(block, window)
        for offset, path in enumerate(block):
            dates = list(fixed_onsets) if fixed_onsets is not None else [e[0] for e in episodes(path)]
            value, dates_used, _ = statistic(moduli[offset], dates, window, lookback)
            result['attempts'].append(dict(number=first + offset, statistic=value, eligible_onsets=dates_used,
                                           status='retained' if value is not None else 'no_episode'))
    kept = [a['statistic'] for a in result['attempts'] if a['statistic'] is not None]
    result['retained'], result['no_episode'] = len(kept), B - len(kept)
    if kept:
        result['exceedances'] = int(sum(value >= S for value in kept))
        result['p_value'] = (1 + result['exceedances']) / (len(kept) + 1)
    return result


def wilson(count, n):
    q = count / n
    centre = (q + Z * Z / (2 * n)) / (1 + Z * Z / n)
    half = Z * math.sqrt(q * (1 - q) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return [centre - half, centre + half]


def cell_summary(outcomes, requested):
    """outcomes: one (valid, positive, S) triple per attempted replicate."""
    valid = sum(1 for v, _, _ in outcomes if v)
    positive = sum(1 for v, p, _ in outcomes if v and p)
    complete = valid == requested == len(outcomes)
    values = [s for v, _, s in outcomes if v and s is not None]
    return dict(requested=requested, attempted=len(outcomes), valid=valid, positive=positive,
                rate=positive / requested if complete else None,
                rate_se=math.sqrt((positive / requested) * (1 - positive / requested) / requested) if complete else None,
                rate_wilson=wilson(positive, requested) if complete else None,
                mean_S=float(np.mean(values)) if complete and values else None,
                mean_S_se=float(np.std(values, ddof=1) / math.sqrt(requested)) if complete and len(values) > 1 else None)


def power_summary(cells, kappas=(1.0, 1.2, 1.4, 1.6), n=200):
    """Adjacent-difference flags and D80 by the first raw crossing (section 9)."""
    rates = [c['rate'] for c in cells]
    means = [c['mean_S'] for c in cells]
    valid = all(r is not None for r in rates)
    adjacent, flags = [], []
    if valid:
        for j in range(1, len(cells)):
            difference = rates[j] - rates[j - 1]
            se = math.sqrt(rates[j] * (1 - rates[j]) / n + rates[j - 1] * (1 - rates[j - 1]) / n)
            flagged = difference < 0 and abs(difference) > 1.96 * se
            adjacent.append(dict(from_kappa=kappas[j - 1], to_kappa=kappas[j], difference=difference, se=se,
                                 flagged_decrease=flagged))
            flags.extend([j] if flagged else [])
    D80 = kappa80 = crossing = None
    if valid:
        hits = [j for j, r in enumerate(rates) if r >= 0.80]
        if hits:
            j = hits[0]
            if j == 0:
                D80, kappa80, crossing = means[0], kappas[0], dict(cells=[0], weight=None)
            else:
                w = (0.80 - rates[j - 1]) / (rates[j] - rates[j - 1])
                kappa80 = kappas[j - 1] + w * (kappas[j] - kappas[j - 1])
                D80 = means[j - 1] + w * (means[j] - means[j - 1])
                crossing = dict(cells=[j - 1, j], weight=w)
    return dict(valid=valid, adjacent=adjacent, decrease_flags=flags, D80=D80, kappa80=kappa80, crossing=crossing,
                AT16_passed=valid and not flags)
