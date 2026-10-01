"""Independent derivations for the review tests of the E4 analysis code (constructed data only).

Every quantity here is recomputed from the registered text by a short derivation that does not call the
code under test or the uc_core functions it reuses: the rolling fit is an unscaled least-squares solve with
an explicit intercept column (H1 section 4), the modulus is the largest absolute root of
lambda^2 - phi1*lambda - phi2 found by numpy.roots, the generators are built from
SeedSequence([seed, stream, cell, replicate]) directly (H1 section 8, E4 Annex A), and the p-value and the
Wilson interval follow the formulas of H1 section 6. Agreement with the code is expected to rounding
error only, because the code solves the same least-squares problem after centring and scaling.
"""
import math

import numpy as np

Z = 1.959963984540054                      # H1 section 6
DEV_SEED = 20260930                        # development master seed (never 1927)


def generator(seed, stream, cell, replicate):
    """PCG64 from SeedSequence([seed, stream, cell, replicate]), built without the package's own generator function."""
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, stream, cell, replicate])))


def constructed_growth(n, replicate, *, stream=9991):
    """An arbitrary stationary AR(2) growth-like series (development stream 9991, not a registered id)."""
    rng = generator(DEV_SEED, stream, 0, replicate)
    e = rng.normal(0.0, 3.0, size=n + 50)
    x = np.zeros(n + 50)
    x[0] = x[1] = 2.0
    for t in range(2, n + 50):
        x[t] = 1.2 + 0.35 * x[t - 1] + 0.15 * x[t - 2] + e[t]
    return x[50:]


def ols_ar2(values):
    """Intercept-inclusive OLS AR(2): responses values[2:], lags values[1:-1] and values[:-2]."""
    x = np.asarray(values, dtype=float)
    design = np.column_stack((np.ones(len(x) - 2), x[1:-1], x[:-2]))
    beta = np.linalg.lstsq(design, x[2:], rcond=None)[0]
    residuals = x[2:] - design @ beta
    return float(beta[0]), float(beta[1]), float(beta[2]), residuals


def modulus(phi1, phi2):
    """Largest absolute companion root of lambda^2 - phi1*lambda - phi2 = 0."""
    return float(np.max(np.abs(np.roots([1.0, -phi1, -phi2]))))


def rolling_modulus(values, window):
    """M(t) for t >= window - 1 from the window values[t-window+1..t]; NaN before (warm-up)."""
    x = np.asarray(values, dtype=float)
    out = np.full(len(x), np.nan)
    for t in range(window - 1, len(x)):
        _, p1, p2, _ = ols_ar2(x[t - window + 1:t + 1])
        out[t] = modulus(p1, p2)
    return out


def delta(values, window=40, lookback=8):
    """Delta = M(n - 1) - M(n - 1 - lookback) with the onset at position n = len(values)."""
    m = rolling_modulus(values, window)
    n = len(values)
    return float(m[n - 1] - m[n - 1 - lookback])


def lag_one(values, window, t):
    """A(t) of H1 section 7: demeaned window, full-window energy as the denominator."""
    v = np.asarray(values[t - window + 1:t + 1], dtype=float)
    v = v - v.mean()
    return float(np.sum(v[1:] * v[:-1]) / np.sum(v * v))


def kendall_tau_b(y):
    """tau-b of y against positions 0..len(y)-1 (distinct positions): (C - D) / sqrt(n0 * (n0 - T))."""
    n = len(y)
    concordant = discordant = ties = 0
    for i in range(n):
        for k in range(i + 1, n):
            if y[k] > y[i]:
                concordant += 1
            elif y[k] < y[i]:
                discordant += 1
            else:
                ties += 1
    n0 = n * (n - 1) // 2
    return (concordant - discordant) / math.sqrt(n0 * (n0 - ties))


def surrogate_statistics(series, seed, stream, B, *, window=40, kind="residual"):
    """S_b for b = 0..B-1 of the fixed-date per-vintage null (E4 section 9), derived independently.

    Per episode j (in the order given, with cell = j): OLS AR(2) with intercept on all n_v values, residuals
    centred; attempt b draws n_v - 2 indices in one integers(0, n_v - 2, size=n_v - 2) call (or one
    integers(0, 2, size=n_v - 2) sign call for the wild scheme), regenerates from the first two observed
    values, and Delta_b = M(n_v - 1) - M(n_v - 9). S_b is the mean over episodes.
    """
    fits = []
    for j, g in enumerate(series):
        c, p1, p2, residuals = ols_ar2(g)
        fits.append((np.asarray(g, dtype=float), c, p1, p2, residuals - residuals.mean(), generator(seed, stream, j, 0)))
    out = []
    for _ in range(B):
        deltas = []
        for g, c, p1, p2, res, rng in fits:
            n = len(g)
            if kind == "residual":
                innovations = res[rng.integers(0, n - 2, size=n - 2)]
            else:
                innovations = res * (2 * rng.integers(0, 2, size=n - 2) - 1)
            x = np.empty(n)
            x[:2] = g[:2]
            for t in range(2, n):
                x[t] = c + p1 * x[t - 1] + p2 * x[t - 2] + innovations[t - 2]
            deltas.append(delta(x, window))
        out.append(float(np.mean(deltas)))
    return out


ONSETS = ((1973, 3), (1980, 1), (1990, 3), (2008, 2))
VINTAGE_ENDS = {0: (1972, 4), 1: (1979, 3), 2: (1990, 1), 3: (2007, 4), 4: (2010, 4), 5: (2010, 4)}


def constructed_tables(n_vs=(45, 52, 60, 90)):
    """Constructed workbook (arbitrary numbers) for the four registered onsets.

    Rows 1955Q1 to 2010Q4; six vintages "Jan 2016" to "Jun 2016"; vintage k holds levels up to
    VINTAGE_ENDS[k], so the first vintage holding q_j - 1 is j + 1 and the vintage before it has no level for
    q_j - 1. In vintage j + 1 an empty cell at q_j - 1 - n_vs[j] - 1 makes the run of episode j exactly n_vs[j]
    growth values long. Levels are 100 * exp(cumulated constructed growth / 400) times a small factor that
    differs between vintages.
    """
    from uc_e4.table import RawPart, build_tables, quarter_from_index, quarter_index
    first, last = quarter_index((1955, 1)), quarter_index((2010, 4))
    rows = [quarter_from_index(i) for i in range(first, last + 1)]
    g = constructed_growth(len(rows), replicate=5)
    log_level = np.concatenate([[0.0], np.cumsum(g[1:]) / 400.0])
    gaps = {j + 1: quarter_from_index(quarter_index(o) - 1 - n - 1) for j, (o, n) in enumerate(zip(ONSETS, n_vs))}
    cells = []
    for i, q in enumerate(rows):
        row = []
        for k in range(6):
            if quarter_index(q) > quarter_index(VINTAGE_ENDS[k]) or gaps.get(k) == q:
                row.append(None)
            else:
                row.append(100.0 * math.exp(log_level[i]) * (1 + 0.0005 * k * math.sin(0.9 * i)))
        cells.append(tuple(row))
    labels = ("Jan 2016", "Feb 2016", "Mar 2016", "Apr 2016", "May 2016", "Jun 2016")
    return build_tables([RawPart("T", labels, tuple(f"{y} Q{qq}" for y, qq in rows), tuple(cells))])


def p_value(observed, statistics):
    """H1 section 6: p = (1 + K) / (B' + 1), K = count(S_b >= S), ties counted."""
    k = sum(1 for s in statistics if s >= observed)
    return (1 + k) / (len(statistics) + 1), k


def wilson(k, n):
    """H1 section 6 Wilson interval for q = K / B' (centre and half-width as written there)."""
    q = k / n
    centre = (q + Z * Z / (2 * n)) / (1 + Z * Z / n)
    half = Z * math.sqrt(q * (1 - q) / n + Z * Z / (4 * n * n)) / (1 + Z * Z / n)
    return centre - half, centre + half
