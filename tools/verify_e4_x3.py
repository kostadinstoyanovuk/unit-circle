#!/usr/bin/env python3
"""verify_e4_x3.py - a second implementation of the E4 procedure and an independent check of its X.3 outputs.

Written from the registered texts alone: prereg/E4.md (OSF dpxqf, SHA-256 df7e2745...c7b9) sections 5 to 9
and 11 and Annex A; prereg/H1.md sections 4 to 9 and 12, which E4 incorporates ("Every H1 rule applies
unchanged unless replaced here"); and the readings adopted where E4 is silent (docs/E4_READINGS.md, decision
D-050), each treated as part of the specification. It imports nothing from the research packages: Python's
standard library and NumPy only, so that it does not rest on the code it checks.

    python -B tools/verify_e4_x3.py <part files or directories> [--report out.json]
                                    [--all | --sample N] [--workers k] [--development] [--partial]

The computational core, a small library in this file:
  * growth from levels, g[t] = 400*(ln Y[t] - ln Y[t-1]) (E4 section 5);
  * the rolling intercept-inclusive OLS AR(2) (H1 section 4) fitted to every window of one or many series at
    once by closed-form centred normal equations, the companion-root modulus M(t) by the H1 section 4
    formulas, and Delta = M(n_v - 1) - M(n_v - 9) (E4 section 8); every window of a series must be fitted,
    otherwise the statistic of that series fails (reading R-9.2);
  * the per-episode null (E4 section 9): OLS on all n_v values with n_v - 2 rows, strict stability as H1
    section 6 (the triangle and the root check must both hold), centred residuals;
  * the surrogate draws: for attempts b = 0, 1, ... one integers(0, n_v - 2, size=n_v - 2) call per attempt
    from the episode's own Generator(PCG64(SeedSequence([seed, stream, cell, replicate]))), regeneration from
    the first two observed values with the fitted null, all attempts of one episode regenerated and refitted
    at once; S_b = mean over episodes of Delta_b; K = count(S_b >= S), B', p = (1 + K)/(B' + 1), q = K/B' and
    the Wilson interval (H1 section 6);
  * the X.3 synthetic design (E4 section 11): five truncations of one 259-value series (n_v = 49, 99, 149,
    199, 249), surrogate cells j (size) and 10*kappa index + j (power), a rejection being a valid raw
    p <= 0.05, the size band 0.02-0.09 with all 200 valid, cell summaries, adjacent differences with the
    1.96-SE decrease flag and D80 by the first raw crossing (H1 section 9);
  * the H1 section 9 generator of the 259-value series, used to check that each stored input is the series its
    generation coordinates give (see REGENERATION below for what the text fixes and what it leaves open).

The check of X.3 output files (JSON Lines: a manifest line, then run-start lines of record type "session",
then one "replicate" line per series): the design (every coordinate once, none outside, sizes), one code
identity, mode and seed across all manifests and records, each stored input against its SHA-256, and an
independent recomputation from the stored input alone of the five vintage series, the observed Delta and S,
the fitted nulls, the random-number states, every surrogate attempt and so every S_b, K, B', p, q and the
Wilson interval; then the size and power summaries, flags and D80 from the recomputed p-values, compared with
the runner's summaries where they are present. Counts are compared exactly; floats agree when
|a - b| <= 1e-12 + 1e-9*|b|. A surrogate statistic within 1e-9 of the observed S is reported as a near tie.

Exit status: 0 everything checked agrees and nothing is missing; 1 a problem or a disagreement; 2 a usage or
input error. The registered pass or fail of the cells is reported, not encoded in the exit status.
"""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import multiprocessing
from pathlib import Path
import platform
import sys
import time

import numpy as np

VERSION = "1.0 (30 September 2026)"
E4_SHA256 = "df7e2745b9f30dc9d9ed53526214f8d4f464f175f3180fcff3e1a92e4d03c7b9"
E1_FROZEN_CODE_SHA256 = "c42cbbf35734eb4f8c12aff22384371aa4fad107ae283f6d2f5f6f93c12feef7"
Z_WILSON = 1.959963984540054              # H1 section 6
DECREASE_Z = Fraction(196, 100)           # H1 section 9: "exceeds 1.96 times that standard error"
ALPHA = Fraction(5, 100)                  # a rejection is a valid raw p <= 0.05
BAND = (Fraction(2, 100), Fraction(9, 100))
TARGET = Fraction(80, 100)                # D80: first raw crossing of 0.80
KAPPAS = (1.0, 1.2, 1.4, 1.6)
REGISTERED_SEED = 1927
N_SERIES = 200
B_ATTEMPTS = 1000
WINDOW = 40                               # E4 section 6, H1 section 4
LOOKBACK = 8                              # Delta = M(n_v - 1) - M(n_v - 9)
N_GROWTH = 259                            # H1 section 9: 259 observations
VINTAGES = (49, 99, 149, 199, 249)        # E4 section 11: n_v = r for the five imposed onsets
# Annex A. The X.3 coordinates: size generation 5420 (cell 0, replicate i), size surrogates 5421 (cell j,
# replicate i); power generation 5430 (cell = kappa index, replicate i), power surrogates 5431 (cell =
# 10 * kappa index + j, replicate i). The study's streams are listed so that a manifest can be checked.
REGISTERED_STREAMS = dict(primary=5400, window32=5401, window48=5402, wild=5404, interval=5405,
                          size_generation=5420, size_null=5421, power_generation=5430, power_null=5431)
# Registered or planned stream ids of the programme (never used by a development run; reading R-G.1).
RESERVED_STREAMS = frozenset(list(range(100, 106)) + [200, 201, 300, 301, 400, 401, 1001, 1013, 2008, 2012]
                             + list(range(5100, 5432)))
DEVELOPMENT_STREAM_FLOOR = 9000
# H1 section 9 generating process
BASE_A, BASE_B, BASE_C, SIGMA = 0.3, 0.1, 1.5, 3.5
# Agreement. Counts are exact. A float recomputed here by another numerical route (closed-form centred normal
# equations; the fitted null regenerated through the recursion) differs from a scaled-lstsq computation by
# rounding only, of order 1e-15 relative; the tolerance sits far above that and far below any difference of
# substance. The absolute floor serves values at or near zero.
FLOAT_REL, FLOAT_ABS = 1e-9, 1e-12
NEAR_TIE = 1e-9                           # |S_b - S| <= 1e-9 is reported as a near tie, not silently classified
# Lag columns whose squared correlation exceeds 1 - 1e-4 make the closed form lose more than about 1e-12 of
# relative precision; such fits are made by the H1 section 4 lstsq recipe instead (never met on random data).
ILL_CONDITIONED = 1e-4
P_LABEL = "raw, not family-adjusted"

SIZE_CLAUSE = ("prereg/E4.md", "section 11, Size (AT-15 adapted)",
               "Pass: rejection rate between **0.02 and 0.09** inclusive, with all 200 valid. A rejection in the "
               "cells is a valid raw p ≤ 0.05, as in H1 §9.")
POWER_CLAUSE = ("prereg/E4.md", "section 11, Reporting and D80",
                "**Reporting and D80.** As H1 §9, including the 1.96-SE decrease flag and the first-raw-crossing D80.")
AT16_CLAUSE = ("prereg/H1.md", "section 9, Cell reporting",
               "If any cell is invalid/incomplete or a decrease exceeds this threshold, AT-16 does not pass and G2 "
               "remains pending.")
VALID_CELL_CLAUSE = ("prereg/H1.md", "section 9, Cell reporting",
                     "A cell is complete and valid only when all 200 provide finite S and valid p.")


class NullFailure(Exception):
    """The per-episode null cannot be used (E4 section 9: an unstable or failed null fails the comparison)."""


class UsageError(Exception):
    pass


# ------------------------------------------------------------------------------------------ arithmetic

def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def finite(value):
    return is_number(value) and math.isfinite(value)


def close(a, b, rel=FLOAT_REL, abs_tol=FLOAT_ABS):
    if a is None or b is None:
        return a is None and b is None
    if not (is_number(a) and is_number(b)):
        return False
    a, b = float(a), float(b)
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return abs(a - b) <= abs_tol + rel * abs(b)


def max_abs_difference(a, b):
    """Largest |a - b| over the finite pairs, and whether every pair agrees within the tolerance (NaN only
    against NaN)."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.shape != b.shape:
        return None, False
    nan_a, nan_b = np.isnan(a), np.isnan(b)
    if np.any(nan_a != nan_b):
        return None, False
    both = ~nan_a
    if not np.any(both):
        return 0.0, True
    diff = np.abs(a[both] - b[both])
    ok = bool(np.all(diff <= FLOAT_ABS + FLOAT_REL * np.abs(b[both])))
    return float(diff.max()), ok


def wilson(successes, total, z=Z_WILSON):
    """H1 section 6: centre (q + z^2/(2n))/(1 + z^2/n), half-width z*sqrt(q(1-q)/n + z^2/(4n^2))/(1 + z^2/n)."""
    q = successes / total
    d = 1 + z * z / total
    centre = (q + z * z / (2 * total)) / d
    half = z * math.sqrt(q * (1 - q) / total + z * z / (4 * total * total)) / d
    return [max(0.0, centre - half), min(1.0, centre + half)]


# ------------------------------------------------------------------ the kernel (E4 sections 5-9, H1 4-6)

def growth_from_levels(levels):
    """E4 section 5: g[t] = 400*(ln(Y[t]) - ln(Y[t-1])). A non-positive or non-finite level in the run makes
    the episode unavailable; nothing is interpolated."""
    y = np.asarray(levels, dtype=float)
    if y.ndim != 1 or len(y) < 2:
        raise ValueError("at least two levels are needed")
    if not np.all(np.isfinite(y)) or np.any(y <= 0):
        raise ValueError("a level in the run is non-positive or non-finite")
    return 400.0 * (np.log(y[1:]) - np.log(y[:-1]))


def companion_modulus(phi1, phi2):
    """H1 section 4: the roots of lambda^2 - phi1*lambda - phi2 = 0. For D = phi1^2 + 4*phi2 < 0, M =
    sqrt(-phi2); otherwise the larger-magnitude real root (phi1 + copysign(sqrt(D), phi1))/2 and the other by
    the root product -phi2 divided by it, zero when both vanish. No clipping."""
    phi1 = np.asarray(phi1, dtype=float)
    phi2 = np.asarray(phi2, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        d = phi1 * phi1 + 4.0 * phi2
        complex_pair = d < 0
        m_complex = np.sqrt(np.where(complex_pair, -phi2, 0.0))
        big = (phi1 + np.copysign(np.sqrt(np.where(complex_pair, 0.0, d)), phi1)) / 2.0
        nonzero = big != 0
        small = np.where(nonzero, -phi2 / np.where(nonzero, big, 1.0), 0.0)
        m_real = np.maximum(np.abs(big), np.abs(small))
        out = np.where(complex_pair, m_complex, m_real)
        out = np.where(np.isfinite(d), out, np.nan)
    return out


def h1_lstsq_slopes(values):
    """The H1 section 4 recipe for one fit, used where the closed form is ill-conditioned: centre each lag
    column, divide by its root mean square centred magnitude, solve the two-column problem with
    lstsq(rcond=None), require rank two and finite values, undo the scaling. Returns (phi1, phi2), NaN on a
    failure."""
    w = np.asarray(values, dtype=float)
    y, l1, l2 = w[2:], w[1:-1], w[:-2]
    c1, c2 = l1 - l1.mean(), l2 - l2.mean()
    scale1, scale2 = math.sqrt(float(np.mean(c1 * c1))), math.sqrt(float(np.mean(c2 * c2)))
    if not (scale1 > 0 and scale2 > 0 and math.isfinite(scale1) and math.isfinite(scale2)):
        return math.nan, math.nan
    beta, _, rank, _ = np.linalg.lstsq(np.column_stack([c1 / scale1, c2 / scale2]), y - y.mean(), rcond=None)
    if rank < 2 or not np.all(np.isfinite(beta)):
        return math.nan, math.nan
    return float(beta[0] / scale1), float(beta[1] / scale2)


def rolling_fit(x, window=WINDOW):
    """H1 section 4 for every window of the last axis at once. Each window of W values is fitted by OLS with an
    intercept, the last W - 2 values as responses and the window's own first two values only as lags, by the
    closed-form solution of the centred 2 x 2 normal equations (the intercept follows from the means).
    Returns (phi1, phi2, modulus, ok), of shape (..., n - W + 1); entry k is the window ending at position
    k + W - 1. A window fails (ok False, modulus NaN) when a lag column has zero centred scale, the centred
    cross-product matrix is not positive definite (rank below two), or a coefficient or the modulus is not
    finite; a non-finite value in a window propagates to a failure. A window whose lag columns are nearly
    collinear (squared correlation above 1 - ILL_CONDITIONED) is refitted by the H1 section 4 lstsq recipe,
    whose rank decision then applies."""
    x = np.asarray(x, dtype=float)
    n = x.shape[-1]
    if n < window:
        shape = x.shape[:-1] + (0,)
        return np.empty(shape), np.empty(shape), np.empty(shape), np.zeros(shape, dtype=bool)
    view = np.lib.stride_tricks.sliding_window_view(x, window, axis=-1)
    y, l1, l2 = view[..., 2:], view[..., 1:-1], view[..., :-2]
    with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        yc = y - y.mean(axis=-1, keepdims=True)
        c1 = l1 - l1.mean(axis=-1, keepdims=True)
        c2 = l2 - l2.mean(axis=-1, keepdims=True)
        s11 = np.einsum("...i,...i->...", c1, c1)
        s22 = np.einsum("...i,...i->...", c2, c2)
        s12 = np.einsum("...i,...i->...", c1, c2)
        s1y = np.einsum("...i,...i->...", c1, yc)
        s2y = np.einsum("...i,...i->...", c2, yc)
        det = s11 * s22 - s12 * s12
        phi1 = (s22 * s1y - s12 * s2y) / det
        phi2 = (s11 * s2y - s12 * s1y) / det
        modulus = companion_modulus(phi1, phi2)
        ok = ((s11 > 0) & (s22 > 0) & (det > 0) & np.isfinite(det) & np.isfinite(phi1) & np.isfinite(phi2)
              & np.isfinite(modulus))
        r2 = (s12 * s12) / (s11 * s22)
        ill = (s11 > 0) & (s22 > 0) & np.isfinite(r2) & (r2 > 1.0 - ILL_CONDITIONED)
    if np.any(ill):
        # The normal equations square the condition number; H1 section 4 decides rank and coefficients by
        # lstsq(rcond=None) on the scaled centred columns, so such windows are refitted by that recipe.
        for index in zip(*np.nonzero(ill)):
            p1, p2 = h1_lstsq_slopes(view[index])
            m = float(companion_modulus(p1, p2))
            phi1[index], phi2[index], modulus[index] = p1, p2, m
            ok[index] = math.isfinite(p1) and math.isfinite(p2) and math.isfinite(m)
    return phi1, phi2, np.where(ok, modulus, np.nan), ok


def rolling_modulus(x, window=WINDOW, chunk=64):
    """M(t) for every window of one series (1-D) or of each row of a 2-D array, in chunks of rows to bound
    memory. Returns (modulus, ok) with the window axis last."""
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        _, _, modulus, ok = rolling_fit(x, window)
        return modulus, ok
    width = max(x.shape[-1] - window + 1, 0)
    modulus = np.empty((x.shape[0], width))
    ok = np.empty((x.shape[0], width), dtype=bool)
    for start in range(0, x.shape[0], chunk):
        _, _, m, k = rolling_fit(x[start:start + chunk], window)
        modulus[start:start + chunk], ok[start:start + chunk] = m, k
    return modulus, ok


def delta_from_modulus(modulus, ok, lookback=LOOKBACK):
    """Delta = M(n - 1) - M(n - 1 - lookback) along the last axis, with its availability: M(n - 1 - lookback)
    must exist, every window of the series must have been fitted (reading R-9.2: a window that cannot be
    fitted anywhere in the series fails the statistic) and both moduli must be finite."""
    modulus = np.asarray(modulus, dtype=float)
    ok = np.asarray(ok, dtype=bool)
    if modulus.shape[-1] < lookback + 1:
        shape = modulus.shape[:-1]
        return np.full(shape, np.nan), np.zeros(shape, dtype=bool)
    with np.errstate(invalid="ignore"):
        delta = modulus[..., -1] - modulus[..., -1 - lookback]
    good = ok.all(axis=-1) & np.isfinite(delta)
    return np.where(good, delta, np.nan), good


def series_delta(series, window=WINDOW, lookback=LOOKBACK):
    """(Delta, reason) of one vintage series; Delta is None with a reason when the statistic fails or the
    series is too short (n_v < W + lookback, E4 section 7 step 3)."""
    x = np.asarray(series, dtype=float)
    if len(x) < window + lookback:
        return None, "n_v = %d < %d" % (len(x), window + lookback)
    modulus, ok = rolling_modulus(x, window)
    delta, good = delta_from_modulus(modulus, ok, lookback)
    if not bool(good):
        bad = [int(k) + window - 1 for k in np.flatnonzero(~ok)[:5]]
        return None, "rolling fit failed at positions %s" % bad if bad else "non-finite modulus"
    return float(delta), None


def fit_null(series):
    """E4 section 9 per episode: the intercept-inclusive OLS AR(2) on all n_v values with n_v - 2 rows (closed
    form on centred columns, the intercept from the means), strict stability as H1 section 6 - phi1 + phi2 < 1,
    phi2 - phi1 < 1, phi2 > -1 and a finite computed M < 1, all of them - and the residuals in position order
    with their arithmetic mean subtracted explicitly."""
    x = np.asarray(series, dtype=float)
    n = len(x)
    if x.ndim != 1 or n < 5:
        raise NullFailure("fewer than three regression rows")
    if not np.all(np.isfinite(x)):
        raise NullFailure("non-finite growth value")
    y, l1, l2 = x[2:], x[1:-1], x[:-2]
    my, m1, m2 = y.mean(), l1.mean(), l2.mean()
    yc, c1, c2 = y - my, l1 - m1, l2 - m2
    s11, s22, s12 = float(c1 @ c1), float(c2 @ c2), float(c1 @ c2)
    s1y, s2y = float(c1 @ yc), float(c2 @ yc)
    det = s11 * s22 - s12 * s12
    if s11 > 0 and s22 > 0 and math.isfinite(det) and s12 * s12 / (s11 * s22) > 1.0 - ILL_CONDITIONED:
        phi1, phi2 = h1_lstsq_slopes(x)              # ill-conditioned: the H1 section 4 recipe decides
        if not (math.isfinite(phi1) and math.isfinite(phi2)):
            raise NullFailure("the full-sample fit is not identified (rank below two)")
    elif not (math.isfinite(det) and s11 > 0 and s22 > 0 and det > 0):
        raise NullFailure("the full-sample fit is not identified (rank below two)")
    else:
        phi1 = (s22 * s1y - s12 * s2y) / det
        phi2 = (s11 * s2y - s12 * s1y) / det
    intercept = my - phi1 * m1 - phi2 * m2
    residuals = y - intercept - phi1 * l1 - phi2 * l2
    if not (math.isfinite(phi1) and math.isfinite(phi2) and math.isfinite(intercept)
            and np.all(np.isfinite(residuals))):
        raise NullFailure("non-finite estimate or residual")
    modulus = float(companion_modulus(phi1, phi2))
    triangle = phi1 + phi2 < 1 and phi2 - phi1 < 1 and phi2 > -1
    by_root = math.isfinite(modulus) and modulus < 1
    if not (triangle and by_root):
        raise NullFailure("not strictly stable (phi1 %.6g, phi2 %.6g, M %.6g)%s" % (
            phi1, phi2, modulus, "" if triangle == by_root else "; the triangle and root checks disagree"))
    return dict(phi1=phi1, phi2=phi2, intercept=intercept, modulus=modulus, n=n,
                initial=(float(x[0]), float(x[1])), residuals=residuals - residuals.mean(),
                residual_mean_removed=float(residuals.mean()))


def generator(seed, stream, cell, replicate):
    """H1 section 8, E4 Annex A: NumPy Generator with PCG64 from SeedSequence([seed, stream, cell, replicate])."""
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, stream, cell, replicate])))


def draw_indices(gen, n, attempts):
    """E4 section 9: for attempts b = 0, 1, ... in order, one integers(0, n_v - 2, size=n_v - 2) call each."""
    rows = np.empty((attempts, n - 2), dtype=np.int64)
    for b in range(attempts):
        rows[b] = gen.integers(0, n - 2, size=n - 2)
    return rows


def regenerate(null, indices):
    """Regenerate the vintage series from its first two observed values with the fitted null and the selected
    centred residuals in draw order: x[t] = c + phi1*x[t-1] + phi2*x[t-2] + e[idx[t-2]], t = 2..n_v-1, for
    every attempt (row of indices) at once."""
    indices = np.asarray(indices)
    n = null["n"]
    innovations = null["residuals"][indices]
    out = np.empty((indices.shape[0], n))
    out[:, 0], out[:, 1] = null["initial"]
    c, a, b = null["intercept"], null["phi1"], null["phi2"]
    with np.errstate(over="ignore", invalid="ignore"):
        for t in range(2, n):
            out[:, t] = c + a * out[:, t - 1] + b * out[:, t - 2] + innovations[:, t - 2]
    return out


def e4_comparison(series_list, seed, stream, cells, replicate, attempts, window=WINDOW, lookback=LOOKBACK,
                  surrogates=True):
    """E4 sections 8-9 over the episodes given as growth series (in X.3, the five synthetic vintages).
    Episode j uses the generator of (seed, stream, cells[j], replicate). The observed statistic is computed
    first; if it fails, no null is fitted and nothing is drawn (reading R-9.2); every null is fitted before any
    draw, and one failed null fails the comparison with zero draws and no generator advanced (R-9.3). With
    surrogates=False the draws are made (so that the generator states can be checked) but no path is
    regenerated."""
    m = len(series_list)
    out = dict(status=None, components=[], reasons=[], S=None, nulls=None, null_error=None, rng_before={},
               rng_after={}, indices=None, statistics=None, changes=None, attempt_failed=None, K=None,
               retained=None, failed=None, p=None, q=None, wilson=None, grid=None, near_ties=[],
               regenerated=bool(surrogates))
    for s in series_list:
        delta, reason = series_delta(s, window, lookback)
        out["components"].append(delta)
        out["reasons"].append(reason)
    if any(d is None for d in out["components"]):
        out["status"] = "observed_statistic_failed"
        return out
    S = float(np.mean(np.asarray(out["components"], dtype=float)))
    out["S"] = S
    try:
        out["nulls"] = [fit_null(s) for s in series_list]
    except NullFailure as error:
        out["status"], out["null_error"] = "null_model_failed", str(error)
        return out
    gens = [generator(seed, stream, cell, replicate) for cell in cells]
    out["rng_before"] = {str(j): g.bit_generator.state for j, g in enumerate(gens)}
    out["indices"] = [draw_indices(g, len(s), attempts) for g, s in zip(gens, series_list)]
    out["rng_after"] = {str(j): g.bit_generator.state for j, g in enumerate(gens)}
    if not surrogates:
        out["status"] = "not_regenerated"
        return out
    changes = np.full((attempts, m), np.nan)
    failed = np.zeros(attempts, dtype=bool)
    for j, (null, idx) in enumerate(zip(out["nulls"], out["indices"])):
        paths = regenerate(null, idx)
        modulus, ok = rolling_modulus(paths, window)
        delta, good = delta_from_modulus(modulus, ok, lookback)
        changes[:, j] = delta
        failed |= ~good
    statistics = np.where(failed, np.nan, changes.mean(axis=1) if m else np.nan)
    retained = int(attempts - failed.sum())
    K = int(np.sum(statistics[~failed] >= S))
    out.update(statistics=statistics, changes=changes, attempt_failed=failed, K=K, retained=retained,
               failed=int(failed.sum()))
    out["near_ties"] = [dict(attempt=int(b), statistic=float(statistics[b]), difference=float(statistics[b] - S))
                        for b in np.flatnonzero(~failed & (np.abs(statistics - S) <= NEAR_TIE))]
    if failed.any():
        out["status"] = "invalid_surrogate_failure"
    elif retained == 0:
        out["status"] = "no_retained_surrogates"
    else:
        out["status"] = "ok"
        out["p"] = (1 + K) / (retained + 1)
        out["q"] = K / retained
        out["wilson"] = wilson(K, retained)
        out["grid"] = 1 / (retained + 1)
    return out


# ------------------------------------------------------------------------ the X.3 design (E4 section 11)

def synthetic_vintages(x):
    """E4 section 11: vintage r is positions 0..r-1 of the same series, n_v = r (R-11.1: growth-like values)."""
    x = np.asarray(x, dtype=float)
    return [x[:r] for r in VINTAGES]


def surrogate_cells(check, cell_index):
    """Annex A: size surrogates cell = j (the synthetic vintage 0-4); power surrogates cell = 10*kappa index + j."""
    return [j if check == "size" else 10 * cell_index + j for j in range(len(VINTAGES))]


def h1_series(seed, stream, cell, replicate, kappa=None, n=N_GROWTH, onsets=VINTAGES):
    """The H1 section 9 generator: 259 observations, a = 0.3, b = 0.1, c = 1.5, s.d. 3.5, no burn-in; one
    standard_normal(2) call for the stationary initial pair, x[0] = mu + sqrt(v) z0, x[1] = mu + (h/sqrt(v)) z0 +
    sqrt(v - h*h/v) z1 with mu = c/(1-a-b), v = 3.5^2 (1-b)/((1+b)((1-b)^2 - a^2)), h = a v/(1-b); then one
    normal(0, 3.5, size=257) call and the recursion for x[2..258] in order. With kappa, positions r-8..r-1
    before each imposed onset r use (kappa*0.3, kappa^2*0.1) and the intercept 2.5*(1 - kappa*0.3 -
    kappa^2*0.1); every other position, the onsets included, uses the base values. Returns (series, state
    before, state after)."""
    gen = generator(seed, stream, cell, replicate)
    before = gen.bit_generator.state
    a, b, c = BASE_A, BASE_B, BASE_C
    mu = c / (1 - a - b)
    v = SIGMA ** 2 * (1 - b) / ((1 + b) * ((1 - b) ** 2 - a ** 2))
    h = a * v / (1 - b)
    z = gen.standard_normal(2)
    innovations = gen.normal(0, SIGMA, size=n - 2)
    after = gen.bit_generator.state
    coef_a = np.full(n, a)
    coef_b = np.full(n, b)
    coef_c = np.full(n, c)
    if kappa is not None:
        for r in onsets:
            coef_a[r - 8:r] = kappa * 0.3
            coef_b[r - 8:r] = kappa ** 2 * 0.1
            coef_c[r - 8:r] = 2.5 * (1 - kappa * 0.3 - kappa ** 2 * 0.1)
    x = np.empty(n)
    x[0] = mu + math.sqrt(v) * z[0]
    x[1] = mu + (h / math.sqrt(v)) * z[0] + math.sqrt(v - h * h / v) * z[1]
    for t in range(2, n):
        x[t] = coef_c[t] + coef_a[t] * x[t - 1] + coef_b[t] * x[t - 2] + innovations[t - 2]
    return x, before, after


def input_sha256(values):
    """SHA-256 of the float64 little-endian bytes of the stored input."""
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


def build_record(x, *, seed, streams, check, cell_index, replicate, attempts, kappa=None, mode="development",
                 code_sha256="0" * 64, settings=None):
    """A replicate record in the layout of the X.3 output files, made by this implementation (used by the tests
    and the cross-check: constructed inputs, development seeds)."""
    x = np.asarray(x, dtype=float)
    stream = streams["size_null" if check == "size" else "power_null"]
    result = e4_comparison(synthetic_vintages(x), seed, stream, surrogate_cells(check, cell_index), replicate,
                           attempts)
    observed = dict(status="ok" if result["S"] is not None else "failed", value=result["S"],
                    components=result["components"], eligible_onsets=list(range(len(VINTAGES))),
                    ineligible_onsets=[], error=None)
    attempts_out = []
    if result["statistics"] is not None:
        for b in range(attempts):
            bad = bool(result["attempt_failed"][b])
            attempts_out.append(dict(number=b, status="failed" if bad else "retained",
                                     statistic=None if bad else float(result["statistics"][b]),
                                     eligible_onsets=list(range(len(VINTAGES))),
                                     changes=[None if math.isnan(v) else float(v) for v in result["changes"][b]],
                                     error="surrogate statistic failed" if bad else None))
    counts = dict(requested=attempts, attempted=len(attempts_out), retained=result["retained"] or 0,
                  no_episode=0, failed=result["failed"] or 0, exceedances=result["K"] or 0)
    comparison = dict(name="primary", status=result["status"], observed=observed, p_value=result["p"], **counts,
                      p_grid_spacing=result["grid"], q=result["q"], q_wilson=result["wilson"],
                      attempts=attempts_out, p_label=P_LABEL)
    record = dict(cell="size" if check == "size" else "power_%d" % cell_index, cell_index=cell_index,
                  replicate=replicate, status=result["status"], input=[float(v) for v in x],
                  input_sha256=input_sha256(x), kappa=1.0 if kappa is None else kappa, S=result["S"],
                  p_value=result["p"], observed=observed, comparison=comparison, error=None)
    for key in ("requested", "attempted", "retained", "no_episode", "failed", "exceedances"):
        record["surrogate_" + key] = counts[key]
    record["surrogate_exceedance_rate"] = result["q"]
    record["surrogate_exceedance_wilson"] = result["wilson"]
    record["analysis_rng_before"] = result["rng_before"]
    record["analysis_rng_after"] = result["rng_after"]
    record["null_models"] = {j: dict(coefficients=[nl["phi1"], nl["phi2"]], intercept=nl["intercept"],
                                     initial=list(nl["initial"]), residuals=[float(r) for r in nl["residuals"]],
                                     residual_mean_removed=nl["residual_mean_removed"], modulus=nl["modulus"])
                             for j, nl in enumerate(result["nulls"] or [])} or None
    record.update(record_type="replicate", registered=mode == "registered", mode=mode, master_seed=seed,
                  B=attempts, settings=settings or {}, code_sha256=code_sha256)
    return record


# ------------------------------------------------------------------------------- cell summaries (H1 9)

def cell_figures(entries, requested, kappa=None):
    """H1 section 9 accounting for one cell; entries: one dict per record present (replicate, status, valid,
    rejected, S). Rates use the nominal denominator."""
    valid = [e for e in entries if e["valid"]]
    rejected = sum(1 for e in valid if e["rejected"])
    missing = requested - len(valid)
    failures = {}
    for e in entries:
        if not e["valid"]:
            failures[str(e["status"])] = failures.get(str(e["status"]), 0) + 1
    complete = missing == 0 and len(entries) == requested
    out = dict(kappa=kappa, requested=requested, attempted=len(entries), valid=len(valid), rejected=rejected,
               unfinished=requested - len(entries), failures=failures,
               accounting_bounds=[rejected / requested, (rejected + missing) / requested] if requested else None,
               valid_only_rate=(rejected / len(valid)) if valid else None, complete=complete, rate=None,
               rate_se=None, rate_wilson=None, mean_S=None, mean_S_se=None)
    if complete and requested:
        values = [e["S"] for e in sorted(valid, key=lambda e: e["replicate"])]
        mean = math.fsum(values) / requested
        rate = rejected / requested
        out.update(rate=rate, rate_se=math.sqrt(rate * (1 - rate) / requested),
                   rate_wilson=wilson(rejected, requested), mean_S=mean,
                   mean_S_se=(math.sqrt(math.fsum((s - mean) ** 2 for s in values) / (requested - 1))
                              / math.sqrt(requested)) if requested > 1 else None)
    return out


def decrease_flag(r_prev, r_cur, n):
    """H1 section 9: flag a decrease p_prev - p_cur whose magnitude exceeds 1.96 * sqrt(p_prev(1-p_prev)/n +
    p_cur(1-p_cur)/n); decided in exact rationals ("exceeds" is strict)."""
    p1, p2 = Fraction(r_prev, n), Fraction(r_cur, n)
    m = p1 - p2
    variance = (p1 * (1 - p1) + p2 * (1 - p2)) / n
    return bool(m > 0 and m * m > DECREASE_Z * DECREASE_Z * variance)


def power_figures(cells):
    """Adjacent differences, decrease flags and D80 by the first raw crossing (H1 section 9)."""
    out = dict(adjacent=[], decrease_flags=[], D80=None, kappa80=None, crossing=None, d80_status=None,
               all_valid=bool(cells) and all(c["complete"] for c in cells))
    if not out["all_valid"]:
        out["d80_status"] = "undefined: a cell is invalid or incomplete"
        return out
    for prev, cur in zip(cells, cells[1:]):
        n = cur["requested"]
        f1, f2 = prev["rejected"] / n, cur["rejected"] / n
        se = math.sqrt(f2 * (1 - f2) / n + f1 * (1 - f1) / n)
        flag = decrease_flag(prev["rejected"], cur["rejected"], n)
        out["adjacent"].append(dict(left_kappa=prev["kappa"], right_kappa=cur["kappa"], difference=f2 - f1,
                                    standard_error=se, threshold=1.96 * se, decrease_flag=flag))
        out["decrease_flags"].append(flag)
    for index, cell in enumerate(cells):
        rate = Fraction(cell["rejected"], cell["requested"])
        if rate < TARGET:
            continue
        if index == 0:
            out.update(D80=cell["mean_S"], kappa80=cell["kappa"], crossing=dict(left=0, right=0, weight=0.0))
        else:
            left = cells[index - 1]
            left_rate = Fraction(left["rejected"], left["requested"])
            w = float((TARGET - left_rate) / (rate - left_rate))
            out.update(D80=left["mean_S"] + w * (cell["mean_S"] - left["mean_S"]),
                       kappa80=left["kappa"] + w * (cell["kappa"] - left["kappa"]),
                       crossing=dict(left=index - 1, right=index, weight=w))
        out["d80_status"] = "defined"
        break
    else:
        out["d80_status"] = "undefined: no kappa <= 1.6 reaches 0.80"
    return out


def size_rule(cell, n):
    """E4 section 11: the rate R/n within [0.02, 0.09] inclusive (exact rationals) with all n valid."""
    band = bool(cell["complete"] and n and BAND[0] <= Fraction(cell["rejected"], n) <= BAND[1])
    all_valid = bool(cell["valid"] == n and cell["attempted"] == n)
    return dict(band=band, all_valid=all_valid, passed=band and all_valid)


# ------------------------------------------------------------------------ checking one record numerically

def _states_equal(stored, mine):
    return json.loads(json.dumps(stored)) == json.loads(json.dumps(mine))


def check_numeric(job):
    """Every numerical check of one record from its stored input alone (run in a worker process when
    --workers > 1). Returns the findings; never raises for a problem of the data."""
    issues, notes = [], []
    res = dict(key=job["key"], where=job["where"], issues=issues, notes=notes, full=job["full"], S=None,
               p=None, K=None, retained=None, status=None, stored_status=job["stored"]["status"], valid=False,
               rejected=False, basis=None,
               max_diff=dict(components=0.0, S=0.0, statistics=0.0, changes=0.0, nulls=None, regeneration=None),
               near_ties=[], stored_near_ties=[], regeneration_identical=None)
    x = job["x"]
    if x is None:
        issues.append("no usable stored input: nothing can be recomputed")
        res["status"] = "no_input"
        return res
    # (a) the stored input against the H1 section 9 generator at its generation coordinates
    if job["generation"] is not None:
        seed, stream, cell, replicate, kappa = job["generation"]
        series, before, after = h1_series(seed, stream, cell, replicate, kappa)
        diff, agree = max_abs_difference(x, series)
        res["max_diff"]["regeneration"] = diff
        res["regeneration_identical"] = bool(np.array_equal(x, series))
        if not agree:
            issues.append("the stored input is not the series its generation coordinates give (max |difference| "
                          "%s)" % ("shape" if diff is None else "%.3g" % diff))
        for label, stored, mine in (("generation_rng_before", job["generation_rng_before"], before),
                                    ("generation_rng_after", job["generation_rng_after"], after)):
            if stored is None:
                notes.append("%s not stored" % label)
            elif not _states_equal(stored, mine):
                issues.append("%s differs from the state of the recomputed generation draws" % label)
    # (b) observed statistic, nulls, draws and (if full) every surrogate attempt
    result = e4_comparison(synthetic_vintages(x), job["seed"], job["stream"], job["cells"], job["replicate"],
                           job["B"], surrogates=job["full"])
    res["status"] = result["status"]
    res["S"] = result["S"]
    stored = job["stored"]
    if result["S"] is None:
        issues.append("recomputed observed statistic failed: %s" % [r for r in result["reasons"] if r])
    else:
        diff, agree = max_abs_difference(stored["components"], result["components"]) \
            if stored["components"] is not None else (None, False)
        res["max_diff"]["components"] = diff
        if not agree:
            issues.append("observed Delta per vintage %s, recomputed %s" % (stored["components"],
                                                                           result["components"]))
        if not close(stored["S"], result["S"]):
            issues.append("observed S %r, recomputed %r" % (stored["S"], result["S"]))
        elif stored["S"] is not None:
            res["max_diff"]["S"] = abs(stored["S"] - result["S"])
    if result["null_error"]:
        issues.append("recomputed null failed: %s" % result["null_error"])
    if result["nulls"] is not None:
        res["nulls"] = [dict(phi1=nl["phi1"], phi2=nl["phi2"], intercept=nl["intercept"], modulus=nl["modulus"])
                        for nl in result["nulls"]]
        largest = None
        for j, (theirs, mine, fit) in enumerate(zip(stored.get("nulls") or [], res["nulls"], result["nulls"])):
            for field in ("phi1", "phi2", "intercept", "modulus"):
                if theirs.get(field) is None:
                    continue
                if not close(theirs[field], mine[field]):
                    issues.append("vintage %d fitted null %s %r, recomputed %r" % (j, field, theirs[field],
                                                                                  mine[field]))
                else:
                    largest = max(largest or 0.0, abs(float(theirs[field]) - float(mine[field])))
            if theirs.get("residual_mean_removed") is not None:
                if not close(theirs["residual_mean_removed"], fit["residual_mean_removed"]):
                    issues.append("vintage %d mean removed from the residuals %r, recomputed %r" % (
                        j, theirs["residual_mean_removed"], fit["residual_mean_removed"]))
            for field in ("initial", "residuals"):
                if theirs.get(field) is None:
                    continue
                try:
                    diff, agree = max_abs_difference(theirs[field], fit[field])
                except (TypeError, ValueError):
                    diff, agree = None, False
                if not agree:
                    issues.append("vintage %d fitted null %s differ from the recomputed values (max |difference| %s)"
                                  % (j, field, "shape or value" if diff is None else "%.3g" % diff))
                elif diff is not None:
                    largest = max(largest or 0.0, diff)
        res["max_diff"]["nulls"] = largest
    for label, stored_states, mine in (("analysis_rng_before", job["analysis_rng_before"], result["rng_before"]),
                                       ("analysis_rng_after", job["analysis_rng_after"], result["rng_after"])):
        if not mine:
            continue
        if stored_states is None:
            notes.append("%s not stored" % label)
        elif not isinstance(stored_states, dict) or set(map(str, stored_states)) != set(mine):
            issues.append("%s does not hold one state per synthetic vintage" % label)
        elif any(not _states_equal(stored_states[str(j)], mine[str(j)]) for j in mine):
            bad = [j for j in sorted(mine) if not _states_equal(stored_states[str(j)], mine[str(j)])]
            issues.append("%s differs from the recomputed draws for vintages %s" % (label, bad))
    # (c) p from the stored surrogate statistics against the recomputed observed S (every record)
    stat = stored["statistics"]
    failed_stored = stored["failed_mask"]
    if result["S"] is not None and stat is not None:
        keep = ~failed_stored
        k_cheap = int(np.sum(stat[keep] >= result["S"]))
        res["stored_near_ties"] = [int(b) for b in np.flatnonzero(keep & (np.abs(stat - result["S"]) <= NEAR_TIE))]
        if stored["K"] is not None and k_cheap != stored["K"]:
            issues.append("exceedances %r, but %d stored surrogate statistics are >= the recomputed S%s" % (
                stored["K"], k_cheap, " (near ties at attempts %s)" % res["stored_near_ties"]
                if res["stored_near_ties"] else ""))
        cheap_valid = bool(len(stat) == job["B"] and not failed_stored.any() and result["nulls"] is not None
                           and job["B"] > 0)
        if not job["full"]:
            res.update(K=k_cheap, retained=int(keep.sum()), basis="stored surrogate statistics")
            if cheap_valid:
                res["p"] = (1 + k_cheap) / (int(keep.sum()) + 1)
                res["valid"] = True
                res["rejected"] = Fraction(1 + k_cheap, int(keep.sum()) + 1) <= ALPHA
    # (d) full regeneration of every attempt
    if job["full"] and result["statistics"] is not None:
        res["basis"] = "every attempt regenerated"
        res.update(K=result["K"], retained=result["retained"], near_ties=result["near_ties"])
        mine_failed = result["attempt_failed"]
        if stat is None or len(stat) != job["B"]:
            issues.append("stored attempts %s, recomputed %d" % (None if stat is None else len(stat), job["B"]))
        else:
            if np.any(mine_failed != failed_stored):
                issues.append("attempt statuses differ at attempts %s" % (
                    np.flatnonzero(mine_failed != failed_stored)[:10].tolist()))
            diff, agree = max_abs_difference(stat, result["statistics"])
            res["max_diff"]["statistics"] = diff
            if not agree:
                gap = np.abs(stat - result["statistics"])
                gap[np.isnan(stat) != np.isnan(result["statistics"])] = np.inf
                worst = int(np.argmax(np.nan_to_num(gap, nan=-1.0)))
                issues.append("surrogate statistics S_b differ from the recomputation (largest at attempt %d: "
                              "stored %r, recomputed %r)" % (worst, float(stat[worst]),
                                                             float(result["statistics"][worst])))
            diff, agree = max_abs_difference(stored["changes"], result["changes"])
            res["max_diff"]["changes"] = diff
            if not agree:
                issues.append("per-vintage surrogate Delta_b differ from the recomputation")
        if stored["K"] is not None and stored["K"] != result["K"]:
            issues.append("exceedances %r, recomputed K = %d%s" % (stored["K"], result["K"], (
                " (recomputed near ties at attempts %s)" % [t["attempt"] for t in result["near_ties"]])
                if result["near_ties"] else ""))
        if stored["retained"] is not None and stored["retained"] != result["retained"]:
            issues.append("retained %r, recomputed B' = %d" % (stored["retained"], result["retained"]))
        if result["status"] == "ok":
            res["p"] = result["p"]
            res["valid"] = True
            res["rejected"] = Fraction(1 + result["K"], result["retained"] + 1) <= ALPHA
            if not close(stored["p"], result["p"]):
                issues.append("p %r, recomputed (1 + K)/(B' + 1) = %d/%d" % (stored["p"], 1 + result["K"],
                                                                             result["retained"] + 1))
            if not close(stored["q"], result["q"]):
                issues.append("q %r, recomputed K/B' = %r" % (stored["q"], result["q"]))
            if stored["wilson"] is None or len(stored["wilson"]) != 2 or not all(
                    close(a, b) for a, b in zip(stored["wilson"], result["wilson"])):
                issues.append("Wilson interval %r, recomputed %r" % (stored["wilson"], result["wilson"]))
            if stored["grid"] is not None and not close(stored["grid"], result["grid"]):
                issues.append("grid spacing %r, recomputed 1/(B' + 1)" % stored["grid"])
        elif stored["p"] is not None:
            issues.append("p %r stored, but the recomputed comparison is %s" % (stored["p"], result["status"]))
    if job["full"] and result["status"] != job["stored"]["status"]:
        issues.append("status %r, recomputed %r" % (job["stored"]["status"], result["status"]))
    elif not job["full"] and result["status"] in ("observed_statistic_failed", "null_model_failed") \
            and job["stored"]["status"] == "ok":
        issues.append("status 'ok', but the recomputed comparison is %s" % result["status"])
    if res["near_ties"]:
        notes.append("near ties (|S_b - S| <= %g) at attempts %s" % (
            NEAR_TIE, [t["attempt"] for t in res["near_ties"]]))
    return res


# ------------------------------------------------------------------------------------ reading the files

class Report:
    def __init__(self, max_print=25, quiet=False):
        self.problems = []
        self.notes = []
        self.missing_fields = {}
        self.max_print = max_print
        self.lines = []
        self.quiet = quiet

    def problem(self, where, message):
        self.problems.append(dict(where=where, message=message))

    def missing(self, field):
        self.missing_fields[field] = self.missing_fields.get(field, 0) + 1

    def say(self, text=""):
        self.lines.append(text)
        if not self.quiet:
            print(text, flush=True)


def fingerprint(manifest):
    identity = manifest.get("identity") or {}
    return dict(schema=manifest.get("schema"), extension=manifest.get("extension"), mode=manifest.get("mode"),
                master_seed=manifest.get("master_seed"), n_series=manifest.get("n_series"), B=manifest.get("B"),
                settings=manifest.get("settings"), code_sha256=manifest.get("code_sha256"),
                e1_code_sha256=manifest.get("e1_code_sha256"), commit=identity.get("commit"),
                python=identity.get("python"), packages=identity.get("packages"), streams=manifest.get("streams"),
                lock=(manifest.get("lock") or {}).get("satisfied"), gate=manifest.get("gate"))


class Context:
    def __init__(self, args, report):
        self.args = args
        self.development = args.development
        self.report = report
        self.manifests = {}
        self.coordinates = {}
        self.jobs = []
        self.entries = {}
        self.files = []
        self.expected_n = None if args.development else N_SERIES
        self.expected_B = None if args.development else B_ATTEMPTS


def check_manifest(ctx, name, manifest):
    rep = ctx.report
    where = name + " manifest"
    for field in ("extension", "check", "mode", "master_seed", "n_series", "B", "code_sha256", "streams",
                  "identity", "lock", "gate", "e1_code_sha256"):
        if field not in manifest:
            rep.missing("manifest." + field)
    if manifest.get("extension") != "e4":
        rep.problem(where, "extension %r, expected 'e4'" % manifest.get("extension"))
    if manifest.get("check") not in ("size", "power"):
        rep.problem(where, "check %r is neither size nor power" % manifest.get("check"))
    streams = manifest.get("streams")
    if ctx.development:
        if manifest.get("mode") != "development" or manifest.get("master_seed") == REGISTERED_SEED:
            rep.problem(where, "a development verification needs a development manifest (not master seed 1927)")
        if isinstance(streams, dict):
            bad = {k: s for k, s in streams.items() if not (type(s) is int and s >= DEVELOPMENT_STREAM_FLOOR
                                                            and s not in RESERVED_STREAMS)}
            if bad:
                rep.problem(where, "development run uses registered or low stream ids: %r" % bad)
        for key, value in (("n_series", manifest.get("n_series")), ("B", manifest.get("B"))):
            if not (type(value) is int and value > 0):
                rep.problem(where, "%s is %r" % (key, value))
    else:
        expected = dict(mode="registered", master_seed=REGISTERED_SEED, n_series=N_SERIES, B=B_ATTEMPTS,
                        kappas=list(KAPPAS) if manifest.get("check") == "power" else None)
        for key, value in expected.items():
            if manifest.get(key) != value:
                rep.problem(where, "%s is %r, the registered design needs %r" % (key, manifest.get(key), value))
        if isinstance(streams, dict):
            for key, value in streams.items():
                if key in REGISTERED_STREAMS and value != REGISTERED_STREAMS[key]:
                    rep.problem(where, "stream %s = %r, Annex A gives %d" % (key, value, REGISTERED_STREAMS[key]))
        identity = manifest.get("identity") or {}
        if identity.get("python") != "3.12.14":
            rep.problem(where, "interpreter %r; registered results need Python 3.12.14 under the lock"
                        % identity.get("python"))
        if (manifest.get("lock") or {}).get("satisfied") is not True:
            rep.problem(where, "the lock is not recorded as satisfied")
        gate = manifest.get("gate")
        if not isinstance(gate, dict):
            rep.problem(where, "no gate record")
        else:
            for key, value in (("tag", "prereg-E4"), ("registration_id", "dpxqf")):
                if key not in gate:
                    rep.missing("manifest.gate." + key)
                elif gate.get(key) != value:
                    rep.problem(where, "gate %s is %r, expected %r" % (key, gate.get(key), value))
    code = manifest.get("code_sha256")
    if not (isinstance(code, str) and len(code) == 64 and all(ch in "0123456789abcdef" for ch in code)):
        rep.problem(where, "code_sha256 %r is not a SHA-256" % code)


def stream_plan(ctx, manifest, check):
    """(generation stream, surrogate stream): Annex A in a registered verification; the manifest's development
    plan otherwise."""
    if not ctx.development:
        return REGISTERED_STREAMS[check + "_generation"], REGISTERED_STREAMS[check + "_null"]
    streams = manifest.get("streams") or {}
    return streams.get(check + "_generation"), streams.get(check + "_null")


def _float_list(values, length=None):
    if not isinstance(values, list) or (length is not None and len(values) != length):
        return None
    out = []
    for v in values:
        if v is None:
            out.append(np.nan)
        elif is_number(v):
            out.append(float(v))
        else:
            return None
    return out


def stored_nulls(record, comparison):
    """The fitted nulls of the five vintages if the record stores them (the layout of the E4 runner's records:
    `null_models`, a dict keyed 0..4, each with coefficients, intercept, initial values, residuals, the mean
    removed from them and the modulus; read defensively, also a list or the keys nulls and null_model, and
    phi1/phi2 in place of coefficients); None when absent."""
    m = len(VINTAGES)
    for holder in (comparison, record):
        for key in ("null_models", "nulls", "null_model"):
            value = holder.get(key)
            if isinstance(value, dict) and all(str(j) in value for j in range(m)):
                value = [value[str(j)] for j in range(m)]
            if not (isinstance(value, list) and len(value) == m and all(isinstance(v, dict) for v in value)):
                continue
            out = []
            for item in value:
                coefficients = item.get("coefficients")
                pair = coefficients if isinstance(coefficients, list) and len(coefficients) == 2 else [None, None]
                out.append(dict(phi1=item.get("phi1", pair[0]), phi2=item.get("phi2", pair[1]),
                                intercept=item.get("intercept"), modulus=item.get("modulus"),
                                residual_mean_removed=item.get("residual_mean_removed"),
                                initial=item.get("initial"), residuals=item.get("residuals")))
            return out
    return None


def check_replicate(ctx, name, manifest, record, line_number):
    """Structural checks of one record and the compact job for its numerical checks."""
    rep = ctx.report
    check = manifest.get("check")
    cell, replicate = record.get("cell_index"), record.get("replicate")
    where = "%s line %d (%s cell %r, replicate %r)" % (name, line_number, check, cell, replicate)
    issues = []
    n_series = ctx.expected_n if ctx.expected_n is not None else manifest.get("n_series")
    B = ctx.expected_B if ctx.expected_B is not None else manifest.get("B")
    m = len(VINTAGES)
    if type(cell) is not int or type(replicate) is not int:
        issues.append("coordinates are not integers")
    else:
        expected_name = "size" if check == "size" else "power_%d" % cell
        if record.get("cell") != expected_name:
            issues.append("cell name %r, expected %r" % (record.get("cell"), expected_name))
    for field in ("mode", "master_seed", "B", "settings", "code_sha256"):
        if field not in record:
            rep.missing("replicate." + field)
            issues.append("no %s field" % field)
        elif record.get(field) != manifest.get(field):
            issues.append("%s %r differs from the file's manifest (%r)" % (field, record.get(field),
                                                                          manifest.get(field)))
    if "registered" in record and record.get("registered") is not (manifest.get("mode") == "registered"):
        issues.append("registered flag %r in a %r file" % (record.get("registered"), manifest.get("mode")))
    kappas = manifest.get("kappas") or list(KAPPAS)
    kappa = None
    if check == "power" and type(cell) is int:
        if 0 <= cell < len(KAPPAS):
            kappa = KAPPAS[cell] if not ctx.development else (kappas[cell] if cell < len(kappas) else None)
            if record.get("kappa") != kappa:
                issues.append("kappa %r does not belong to cell %d" % (record.get("kappa"), cell))
    elif check == "size" and record.get("kappa") not in (None, 1.0):
        issues.append("kappa %r in the size cell" % record.get("kappa"))
    # input and its hash
    x = None
    values = record.get("input")
    if values is None:
        rep.missing("replicate.input")
        issues.append("no stored input")
    else:
        floats = _float_list(values)
        if floats is None or len(floats) != N_GROWTH or not np.all(np.isfinite(floats)):
            issues.append("input is not %d finite numbers" % N_GROWTH)
        else:
            x = np.asarray(floats, dtype=float)
            if input_sha256(x) != record.get("input_sha256"):
                issues.append("stored input does not match input_sha256")
    # observed and comparison fields
    comparison = record.get("comparison")
    if not isinstance(comparison, dict):
        rep.missing("replicate.comparison")
        issues.append("no comparison")
        comparison = {}
    observed = record.get("observed") if isinstance(record.get("observed"), dict) else comparison.get("observed")
    if not isinstance(observed, dict):
        rep.missing("replicate.observed")
        observed = {}
    if isinstance(record.get("observed"), dict) and isinstance(comparison.get("observed"), dict) \
            and record["observed"] != comparison["observed"]:
        issues.append("record observed differs from comparison observed")
    components = _float_list(observed.get("components"), m)
    if observed.get("status") == "ok":
        if components is None:
            issues.append("observed components are not %d numbers" % m)
        if list(observed.get("eligible_onsets") or []) != list(range(m)) or list(
                observed.get("ineligible_onsets") or []) != []:
            issues.append("observed eligible vintages %r, expected all five" % observed.get("eligible_onsets"))
        if record.get("S") != observed.get("value"):
            issues.append("record S differs from the observed value")
    status = record.get("status")
    if comparison and status != comparison.get("status"):
        issues.append("record status %r differs from comparison status %r" % (status, comparison.get("status")))
    if comparison and record.get("p_value") != comparison.get("p_value"):
        issues.append("record p_value differs from the comparison's")
    attempts = comparison.get("attempts")
    stat = changes = failed_mask = None
    if attempts is None:
        if comparison:
            rep.missing("replicate.comparison.attempts")
        if status == "ok":
            issues.append("status ok without stored attempts")
    elif not isinstance(attempts, list):
        issues.append("attempts is not a list")
    else:
        if type(B) is int and len(attempts) != B:
            issues.append("%d attempts stored, the design needs B = %s" % (len(attempts), B))
        if [a.get("number") if isinstance(a, dict) else None for a in attempts] != list(range(len(attempts))):
            issues.append("attempt numbers are not 0..%d in order" % (len(attempts) - 1))
        stat = np.full(len(attempts), np.nan)
        changes = np.full((len(attempts), m), np.nan)
        failed_mask = np.zeros(len(attempts), dtype=bool)
        bad_mean, bad_status, bad_shape = [], [], []
        for i, a in enumerate(attempts):
            if not isinstance(a, dict):
                bad_shape.append(i)
                continue
            st = a.get("status")
            if st == "failed":
                failed_mask[i] = True
                if a.get("statistic") is not None:
                    bad_status.append(i)
                continue
            if st != "retained":
                bad_status.append(i)
                failed_mask[i] = True
                continue
            parts = _float_list(a.get("changes"), m)
            s_b = a.get("statistic")
            if parts is None or not finite(s_b) or list(a.get("eligible_onsets") or []) != list(range(m)):
                bad_shape.append(i)
                continue
            stat[i], changes[i] = s_b, parts
            if not close(math.fsum(parts) / m, s_b):
                bad_mean.append(i)
        if bad_status:
            issues.append("attempts with an unknown status or a failed attempt with a statistic: %s" % bad_status[:10])
        if bad_shape:
            issues.append("retained attempts without five changes, their vintages or a finite statistic: %s"
                          % bad_shape[:10])
        if bad_mean:
            issues.append("attempt statistics that are not the mean of their five changes: %s" % bad_mean[:10])
        counts = dict(requested=B, attempted=len(attempts), retained=int((~failed_mask).sum()),
                      no_episode=0, failed=int(failed_mask.sum()))
        for key, value in counts.items():
            if key not in comparison:
                rep.missing("replicate.comparison." + key)
            elif comparison.get(key) != value:
                issues.append("%s %r, the stored attempts give %r" % (key, comparison.get(key), value))
        for key in ("requested", "attempted", "retained", "no_episode", "failed", "exceedances"):
            if "surrogate_" + key in record and record["surrogate_" + key] != comparison.get(key):
                issues.append("surrogate_%s differs from the comparison" % key)
        s_stored = observed.get("value")
        if finite(s_stored) and comparison.get("exceedances") is not None:
            k_stored = int(np.sum(stat[~failed_mask] >= s_stored))
            if k_stored != comparison.get("exceedances"):
                issues.append("exceedances %r, but %d stored statistics are >= the stored S" % (
                    comparison.get("exceedances"), k_stored))
            retained = int((~failed_mask).sum())
            if status == "ok" and retained and not failed_mask.any():
                p_exact = Fraction(1 + comparison["exceedances"], retained + 1)
                if not close(comparison.get("p_value"), float(p_exact)):
                    issues.append("p %r is not (1 + K)/(B' + 1) = %d/%d of the stored counts" % (
                        comparison.get("p_value"), p_exact.numerator, p_exact.denominator))
            if failed_mask.any() and comparison.get("p_value") is not None:
                issues.append("a surrogate failure did not invalidate p")
        if record.get("surrogate_exceedance_rate") is not None and comparison.get("q") is not None and \
                not close(record.get("surrogate_exceedance_rate"), comparison.get("q")):
            issues.append("surrogate_exceedance_rate differs from q")
    if comparison.get("p_label") not in (None, P_LABEL):
        issues.append("p label %r" % comparison.get("p_label"))
    for issue in issues:
        rep.problem(where, issue)
    # the job for the numerical checks
    gen_stream, sur_stream = stream_plan(ctx, manifest, check)
    seed = manifest.get("master_seed")
    job = None
    if type(cell) is int and type(replicate) is int and type(seed) is int and type(B) is int and \
            type(sur_stream) is int:
        generation = None
        if type(gen_stream) is int:
            generation = (seed, gen_stream, cell if check == "power" else 0, replicate,
                          kappa if check == "power" else None)
        job = dict(key=(check, cell, replicate), where=where, x=x, seed=seed, stream=sur_stream,
                   cells=surrogate_cells(check, cell), replicate=replicate, B=B, full=False,
                   generation=generation,
                   generation_rng_before=record.get("generation_rng_before"),
                   generation_rng_after=record.get("generation_rng_after"),
                   analysis_rng_before=record.get("analysis_rng_before"),
                   analysis_rng_after=record.get("analysis_rng_after"),
                   stored=dict(status=status, S=observed.get("value") if finite(observed.get("value")) else None,
                               components=components, statistics=stat, changes=changes,
                               failed_mask=failed_mask if failed_mask is not None else np.zeros(0, dtype=bool),
                               K=comparison.get("exceedances"), retained=comparison.get("retained"),
                               p=comparison.get("p_value"), q=comparison.get("q"),
                               wilson=comparison.get("q_wilson"), grid=comparison.get("p_grid_spacing"),
                               nulls=stored_nulls(record, comparison)))
        if job["stored"]["nulls"] is None:
            rep.missing("replicate.null_models")
        if record.get("generation_rng_before") is None:
            rep.missing("replicate.generation_rng_before")
        if record.get("analysis_rng_after") is None:
            rep.missing("replicate.analysis_rng_after")
    else:
        rep.problem(where, "coordinates, seed, B or the surrogate stream are unknown: no recomputation")
    return job, len(issues)


def parse_file(ctx, path):
    rep = ctx.report
    name = path.name
    row = dict(file=str(path), bytes=0, lines=0, manifest=False, run_starts=0, replicates=0, problems=0,
               truncated=False, sha256=None, check=None)
    before = len(rep.problems)
    digest = hashlib.sha256()
    manifest = None
    with open(path, "rb") as handle:
        number = 0
        for raw in handle:
            number += 1
            digest.update(raw)
            row["bytes"] += len(raw)
            complete = raw.endswith(b"\n")
            if not raw.strip():
                rep.problem("%s line %d" % (name, number), "blank line")
                continue
            try:
                obj = json.loads(raw)
            except ValueError as error:
                row["truncated"] = row["truncated"] or not complete
                rep.problem("%s line %d" % (name, number), "truncated last line" if not complete else
                            "not valid JSON: %s" % str(error)[:100])
                continue
            if not complete:
                row["truncated"] = True
                rep.problem("%s line %d" % (name, number), "last line has no trailing newline")
            if not isinstance(obj, dict):
                rep.problem("%s line %d" % (name, number), "line is not a JSON object")
                continue
            kind = obj.get("record_type")
            if number == 1:
                if kind != "manifest":
                    rep.problem(name, "does not start with a manifest line")
                    continue
                manifest = obj
                row["manifest"], row["check"] = True, obj.get("check")
                ctx.manifests[str(path)] = manifest
                check_manifest(ctx, name, manifest)
                continue
            if kind == "session":
                row["run_starts"] += 1
                if row["replicates"]:
                    rep.notes.append("%s line %d: a run-start line after replicate lines (a resumed run)" % (
                        name, number))
                continue
            if kind == "manifest":
                rep.problem("%s line %d" % (name, number), "a second manifest line")
                continue
            if kind != "replicate":
                rep.problem("%s line %d" % (name, number), "unexpected record type %r" % kind)
                continue
            if manifest is None:
                rep.problem("%s line %d" % (name, number), "replicate line before any manifest")
                continue
            row["replicates"] += 1
            job, n_issues = check_replicate(ctx, name, manifest, obj, number)
            key = (manifest.get("check"), obj.get("cell_index"), obj.get("replicate"))
            ctx.coordinates.setdefault(key, []).append("%s:%d" % (name, number))
            if job is not None and key not in ctx.entries:
                ctx.jobs.append(job)
                ctx.entries[key] = dict(structural_issues=n_issues)
    row["lines"] = number
    row["sha256"] = digest.hexdigest()
    if manifest is None:
        rep.problem(name, "no manifest")
    row["problems"] = len(rep.problems) - before
    ctx.files.append(row)
    return row


def coverage(ctx, partial):
    rep = ctx.report
    checks = sorted({m.get("check") for m in ctx.manifests.values() if m.get("check") in ("size", "power")})
    n = ctx.expected_n
    if n is None:
        values = {m.get("n_series") for m in ctx.manifests.values()}
        n = values.pop() if len(values) == 1 else None
        if n is None:
            rep.problem("design", "manifests disagree on n_series: %r" % sorted(values, key=str))
            n = 0
    expected = set()
    if "size" in checks:
        expected |= {("size", 0, r) for r in range(n)}
    if "power" in checks:
        expected |= {("power", c, r) for c in range(len(KAPPAS)) for r in range(n)}
    present = set(ctx.coordinates)
    duplicates = sorted((k for k, v in ctx.coordinates.items() if len(v) > 1), key=str)
    missing = sorted(expected - present, key=str)
    outside = sorted(present - expected, key=str)
    for key in duplicates:
        rep.problem("design", "%s cell %s replicate %s appears %d times (%s)" % (
            key[0], key[1], key[2], len(ctx.coordinates[key]), ", ".join(ctx.coordinates[key])))
    if outside:
        rep.problem("design", "%d records outside the design, first %s" % (len(outside), outside[:5]))
    if missing and not partial:
        rep.problem("design", "%d coordinates missing, first %s" % (len(missing), missing[:5]))
    return dict(checks=checks, n_series=n, expected=len(expected), present=len(present), missing=len(missing),
                duplicates=len(duplicates), outside=len(outside))


def compare_manifests(ctx):
    rep = ctx.report
    reference = None
    for name, manifest in ctx.manifests.items():
        fp = fingerprint(manifest)
        if reference is None:
            reference = (name, fp)
            continue
        differing = sorted(k for k in fp if fp[k] != reference[1][k])
        if differing:
            rep.problem(Path(name).name, "manifest differs from %s in %s" % (Path(reference[0]).name,
                                                                           ", ".join(differing)))
    return reference[1] if reference else None


def run_jobs(jobs, workers):
    if workers <= 1 or len(jobs) <= 1:
        return [check_numeric(job) for job in jobs]
    with multiprocessing.Pool(workers) as pool:
        return list(pool.imap(check_numeric, jobs, chunksize=1))


def compare_runner(ctx, path, check, cells, power):
    """Every figure of a runner summary (the E1/E3 layout: summary.cell or summary.cells, adjacent comparisons,
    decrease flags, D80) against the recomputation; fields absent from the file are listed, not guessed."""
    rep = ctx.report
    out = dict(file=str(path), compared=0, differences=[], absent=[])
    with open(path, "rb") as handle:
        data = json.loads(handle.read())
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else data

    def same(label, theirs, ours, exact):
        if theirs is None and ours is not None:
            out["absent"].append(label)
            return
        out["compared"] += 1
        if exact:
            ok = theirs == ours
        elif isinstance(theirs, (list, tuple)) or isinstance(ours, (list, tuple)):
            ok = (isinstance(theirs, (list, tuple)) and isinstance(ours, (list, tuple)) and len(theirs) == len(ours)
                  and all(close(a, b) for a, b in zip(theirs, ours)))
        else:
            ok = close(theirs, ours)
        if not ok:
            out["differences"].append(dict(field=label, runner=theirs, verifier=ours))
            rep.problem(Path(path).name, "%s: runner %r, recomputed %r" % (label, theirs, ours))

    theirs_cells = [summary.get("cell") or {}] if check == "size" else list(summary.get("cells") or [])
    if len(theirs_cells) != len(cells):
        rep.problem(Path(path).name, "%d cells, recomputed %d" % (len(theirs_cells), len(cells)))
    for index, (theirs, ours) in enumerate(zip(theirs_cells, cells)):
        label = "cell" if check == "size" else "cells[%d]" % index
        for field in ("requested", "attempted", "valid", "rejected", "unfinished"):
            same("%s.%s" % (label, field), theirs.get(field), ours[field], True)
        for field in ("accounting_bounds", "valid_only_rate", "rate", "rate_se", "rate_wilson", "mean_S",
                      "mean_S_se"):
            same("%s.%s" % (label, field), theirs.get(field), ours[field], False)
        if check == "power":
            same("%s.kappa" % label, theirs.get("kappa"), ours["kappa"], True)
    if check == "power" and power is not None:
        adjacent = summary.get("adjacent_comparisons") or []
        for index, (theirs, ours) in enumerate(zip(adjacent, power["adjacent"])):
            for field in ("difference", "standard_error"):
                same("adjacent[%d].%s" % (index, field), theirs.get(field), ours[field], False)
            same("adjacent[%d].decrease_flag" % index, theirs.get("decrease_flag"), ours["decrease_flag"], True)
        if len(adjacent) != len(power["adjacent"]):
            rep.problem(Path(path).name, "%d adjacent comparisons, recomputed %d" % (len(adjacent),
                                                                                    len(power["adjacent"])))
        same("decrease_flags", summary.get("decrease_flags"), power["decrease_flags"], True)
        if power["D80"] is not None or summary.get("D80") is not None:
            same("D80", summary.get("D80"), power["D80"], False)
            same("kappa80", summary.get("kappa80"), power["kappa80"], False)
    return out


def select_sample(jobs, count, seed):
    """Indices of `count` jobs drawn without replacement, in coordinate order, from SeedSequence(seed)."""
    order = sorted(range(len(jobs)), key=lambda i: str(jobs[i]["key"]))
    count = min(count, len(jobs))
    gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))
    chosen = gen.choice(len(order), size=count, replace=False) if count else []
    return sorted(order[i] for i in chosen)


def check_prereg(report):
    """If the research clone's prereg/E4.md is beside this script, its SHA-256 and the quoted clauses."""
    path = Path(__file__).resolve().parent.parent / "prereg" / "E4.md"
    h1 = path.parent / "H1.md"
    if not path.is_file():
        return dict(present=False)
    with open(path, "rb") as handle:
        content = handle.read()
    out = dict(present=True, sha256=hashlib.sha256(content).hexdigest())
    out["registered"] = out["sha256"] == E4_SHA256
    text = content.decode("utf-8")
    h1_text = h1.read_bytes().decode("utf-8") if h1.is_file() else ""
    out["quotes_verbatim"] = bool(SIZE_CLAUSE[2] in text and POWER_CLAUSE[2] in text
                                  and AT16_CLAUSE[2] in h1_text and VALID_CELL_CLAUSE[2] in h1_text)
    if not out["registered"]:
        report.problem("prereg/E4.md", "SHA-256 %s differs from the registered %s" % (out["sha256"], E4_SHA256))
    if not out["quotes_verbatim"]:
        report.problem("prereg", "a clause quoted here is not found verbatim")
    return out


def fmt(value, digits=6):
    if value is None:
        return "undefined"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return ("%." + str(digits) + "g") % value
    return str(value)


def fmt_interval(interval):
    return "undefined" if interval is None else "[%.4f, %.4f]" % (interval[0], interval[1])


# ------------------------------------------------------------------------------------------ main

def parse_arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", help="X.3 part files (.jsonl) or directories holding them")
    parser.add_argument("--report", help="write the JSON report here")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="regenerate every surrogate attempt of every record "
                                                          "(the default)")
    group.add_argument("--sample", type=int, metavar="N",
                       help="regenerate the surrogate attempts of N records drawn with --sample-seed; every "
                            "record still has its design, hashes, observed S, nulls, draws and p checked")
    parser.add_argument("--sample-seed", type=int, default=20260930,
                        help="seed of the record selection for --sample (recorded in the report)")
    parser.add_argument("--workers", type=int, default=1, help="processes for the recomputation (default 1)")
    parser.add_argument("--development", action="store_true",
                        help="verify a development run: sizes and stream ids from its manifests; seed 1927 and "
                             "registered stream ids are refused")
    parser.add_argument("--partial", action="store_true",
                        help="check the records present without requiring the complete design (interim use)")
    parser.add_argument("--summary", action="append", default=[],
                        help="a runner summary JSON (x3_size_summary.json or x3_power_summary.json) to compare; "
                             "such files inside a given directory are found automatically")
    parser.add_argument("--max-print", type=int, default=25, help="problems printed in full (all go to --report)")
    parser.add_argument("--quiet", action="store_true", help="print nothing (the JSON report still holds all)")
    args = parser.parse_args(argv)
    if args.sample is not None and args.sample < 0:
        raise UsageError("--sample needs N >= 0")
    if args.sample_seed == REGISTERED_SEED:
        raise UsageError("--sample-seed 1927 is refused: it is the registered master seed")
    if args.workers < 1:
        raise UsageError("--workers needs k >= 1")
    return args


def collect_paths(args):
    files, summaries = [], [Path(p) for p in args.summary]
    for raw in args.paths:
        path = Path(raw)
        if path.is_dir():
            files += sorted(p for p in path.iterdir() if p.is_file() and p.suffix == ".jsonl"
                            and p.name.startswith("x3_") and "prerequisite" not in p.name)
            summaries += sorted(p for p in path.iterdir() if p.name in ("x3_size_summary.json",
                                                                         "x3_power_summary.json"))
        elif path.is_file():
            files.append(path)
        else:
            raise UsageError("no such file or directory: %s" % path)
    if not files:
        raise UsageError("no X.3 part files found")
    return files, summaries


def verify(argv=None):
    """Run every check, print the report and return the JSON payload (also written to --report)."""
    args = parse_arguments(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # quoted clauses hold non-ASCII signs
    except (AttributeError, ValueError):
        pass
    started = time.time()
    rep = Report(args.max_print, args.quiet)
    ctx = Context(args, rep)
    files, summaries = collect_paths(args)
    rep.say("verify_e4_x3.py %s - independent recomputation of the E4 X.3 outputs" % VERSION)
    rep.say("started (UTC) %s; Python %s; NumPy %s; %s" % (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                            platform.python_version(), np.__version__,
                                                            platform.platform()))
    rep.say("mode: %s" % ("development run (sizes and streams from the manifests)" if args.development else
                          "registered design (200 series per cell, B = 1,000, seed 1927, streams of Annex A)"))
    if platform.python_version() != "3.12.14":
        rep.say("note: this interpreter is not the registered environment (Python 3.12.14 under the lock); the "
                "recomputation is exact in its integers and within 1e-9 in its floats on any NumPy 2 platform, "
                "but its own results are development results")
    prereg = check_prereg(rep)
    # 1. files, design and records
    rep.say("")
    rep.say("[1] FILES, DESIGN AND RECORD STRUCTURE")
    for path in files:
        row = parse_file(ctx, path)
        rep.say("  %-34s %s %11d bytes %5d lines %4d records %d run-start line(s) %s%s" % (
            Path(row["file"]).name, row["check"], row["bytes"], row["lines"], row["replicates"], row["run_starts"],
            "OK" if not row["problems"] else "%d PROBLEM(S)" % row["problems"],
            " TRUNCATED" if row["truncated"] else ""))
    reference = compare_manifests(ctx)
    cover = coverage(ctx, args.partial)
    rep.say("  coordinates: expected %d, present %d, missing %d%s, duplicated %d, outside the design %d" % (
        cover["expected"], cover["present"], cover["missing"], " (partial check)" if args.partial else "",
        cover["duplicates"], cover["outside"]))
    if reference:
        rep.say("  manifests: %d; fingerprint: mode %s, master seed %s, code %s..., e1 code %s..., commit %s, "
                "Python %s" % (len(ctx.manifests), reference["mode"], reference["master_seed"],
                               str(reference["code_sha256"])[:12], str(reference["e1_code_sha256"])[:12],
                               reference["commit"], reference["python"]))
        rep.say("  E1 code identity recorded in the manifests equals E1's frozen identity (c42cbbf3...): %s" % (
            reference["e1_code_sha256"] == E1_FROZEN_CODE_SHA256))
    if prereg.get("present"):
        rep.say("  prereg/E4.md beside this script: SHA-256 registered %s; clauses quoted here verbatim %s" % (
            prereg["registered"], prereg["quotes_verbatim"]))
    # 2. recomputation
    if args.sample is not None:
        chosen = select_sample(ctx.jobs, args.sample, args.sample_seed)
    else:
        chosen = list(range(len(ctx.jobs)))
    for index in chosen:
        ctx.jobs[index]["full"] = True
    rep.say("")
    rep.say("[2] RECOMPUTATION FROM THE STORED INPUTS (%d records; every attempt regenerated for %d%s; workers %d)"
            % (len(ctx.jobs), len(chosen), "" if args.sample is None else
               " drawn with SeedSequence(%d)" % args.sample_seed, args.workers))
    t0 = time.time()
    results = run_jobs(ctx.jobs, args.workers)
    compute_seconds = time.time() - t0
    near_ties, stored_near_ties, identical, regen_max = [], [], 0, 0.0
    maxima = dict(components=0.0, S=0.0, statistics=0.0, changes=0.0, nulls=0.0)
    for res in results:
        for issue in res["issues"]:
            rep.problem(res["where"], issue)
        for note in res["notes"]:
            rep.notes.append("%s: %s" % (res["where"], note))
        for key in maxima:
            if res["max_diff"][key] is not None:
                maxima[key] = max(maxima[key], res["max_diff"][key])
        if res["max_diff"]["regeneration"] is not None:
            regen_max = max(regen_max, res["max_diff"]["regeneration"])
        identical += bool(res["regeneration_identical"])
        near_ties += [dict(t, record=list(res["key"])) for t in res["near_ties"]]
        stored_near_ties += [dict(attempt=a, record=list(res["key"])) for a in res["stored_near_ties"]]
        ctx.entries[res["key"]].update(res)
    full = [r for r in results if r["full"]]
    rep.say("  observed Delta and S recomputed for %d records: max |difference| %.3g (Delta), %.3g (S)" % (
        len(results), maxima["components"], maxima["S"]))
    rep.say("  fitted nulls (coefficients, intercept, modulus, initial values, residuals) compared for %d records: "
            "max |difference| %.3g" % (sum(r["max_diff"]["nulls"] is not None for r in results), maxima["nulls"]))
    rep.say("  generator check (H1 section 9): stored input regenerated for %d records, bit-identical %d, max "
            "|difference| %.3g" % (sum(r["max_diff"]["regeneration"] is not None for r in results), identical,
                                   regen_max))
    rep.say("  every surrogate attempt regenerated for %d records: max |difference| %.3g (S_b), %.3g (Delta_b); "
            "near ties (|S_b - S| <= 1e-9): %d recomputed, %d among stored statistics" % (
                len(full), maxima["statistics"], maxima["changes"], len(near_ties), len(stored_near_ties)))
    rep.say("  recomputation time %.1f s" % compute_seconds)
    # 3. cell summaries
    n = cover["n_series"]
    kinds = cover["checks"]
    entries = [dict(check=k[0], cell=k[1], replicate=k[2],
                    status=e.get("status") if e.get("full") else e.get("stored_status"),
                    valid=bool(e.get("valid")), rejected=bool(e.get("rejected")), S=e.get("S"))
               for k, e in ctx.entries.items()]
    size = cell_figures([e for e in entries if e["check"] == "size"], n) if "size" in kinds else None
    power_cells = [cell_figures([e for e in entries if e["check"] == "power" and e["cell"] == c], n, KAPPAS[c])
                   for c in range(len(KAPPAS))] if "power" in kinds else []
    power = power_figures(power_cells) if power_cells else None
    rep.say("")
    rep.say("[3] CELL SUMMARIES FROM THE RECOMPUTED p-VALUES (denominator %d per cell; a rejection is a valid raw "
            "p <= 0.05)%s" % (n, " - partial: incomplete cells are expected" if args.partial else ""))
    if size is not None:
        rep.say("  size: R = %d of %d; valid %d; rate %s; Wilson 95%% %s; MC s.e. %s; mean S %s (s.e. %s); "
                "accounting bounds %s" % (size["rejected"], n, size["valid"], fmt(size["rate"]),
                                          fmt_interval(size["rate_wilson"]), fmt(size["rate_se"]),
                                          fmt(size["mean_S"], 8), fmt(size["mean_S_se"]),
                                          size["accounting_bounds"]))
    for cell in power_cells:
        rep.say("  power kappa %.1f: R = %d of %d; valid %d; rate %s; Wilson 95%% %s; mean S %s (s.e. %s)" % (
            cell["kappa"], cell["rejected"], n, cell["valid"], fmt(cell["rate"]), fmt_interval(cell["rate_wilson"]),
            fmt(cell["mean_S"], 8), fmt(cell["mean_S_se"])))
    if power is not None:
        for adj in power["adjacent"]:
            rep.say("  kappa %.1f -> %.1f: difference %+.4f; s.e. %.5f; 1.96 s.e. %.5f; decrease flag %s" % (
                adj["left_kappa"], adj["right_kappa"], adj["difference"], adj["standard_error"], adj["threshold"],
                adj["decrease_flag"]))
        rep.say("  D80: %s%s" % (power["d80_status"], "" if power["D80"] is None else " = %s at kappa80 = %s (%s)" % (
            fmt(power["D80"], 8), fmt(power["kappa80"]), power["crossing"])))
    # 4. registered rule
    registered_design = bool(not args.development and reference and reference["mode"] == "registered"
                             and reference["master_seed"] == REGISTERED_SEED)
    rep.say("")
    rep.say("[4] THE REGISTERED RULE ON THESE NUMBERS")
    rep.say("  precondition: registered design in every manifest (mode registered, seed 1927, 200 series, "
            "B = 1,000): %s" % ("yes" if registered_design else "no (development run or a mismatch)"))
    verdicts = {}
    if size is not None:
        rule = size_rule(size, n)
        verdicts["size"] = dict(rule, registered=registered_design,
                                passed=bool(registered_design and rule["passed"]))
        rep.say("  SIZE (%s, %s): %s - rate in band %s, all valid %s" % (
            SIZE_CLAUSE[0], SIZE_CLAUSE[1], "PASS" if verdicts["size"]["passed"] else "FAIL", rule["band"],
            rule["all_valid"]))
        rep.say("    registered: \"%s\"" % SIZE_CLAUSE[2])
    if power is not None:
        no_flag = bool(power["all_valid"] and not any(power["decrease_flags"]))
        verdicts["power"] = dict(cells_valid=power["all_valid"], no_flag=no_flag, registered=registered_design,
                                 passed=bool(registered_design and no_flag), D80=power["D80"])
        rep.say("  POWER (%s, %s): %s - every cell complete and valid %s, no flagged decrease %s; D80 %s" % (
            POWER_CLAUSE[0], POWER_CLAUSE[1], "PASS" if verdicts["power"]["passed"] else "FAIL",
            power["all_valid"], no_flag, fmt(power["D80"], 8)))
        rep.say("    registered: \"%s\" and (%s, %s) \"%s\"" % (POWER_CLAUSE[2], AT16_CLAUSE[0], AT16_CLAUSE[1],
                                                                AT16_CLAUSE[2]))
    # 5. runner summaries
    rep.say("")
    rep.say("[5] COMPARISON WITH THE RUNNER'S SUMMARIES")
    runner = []
    for path in summaries:
        check = "power" if "power" in path.name else "size"
        if check == "size" and size is None or check == "power" and power is None:
            rep.problem(path.name, "a %s summary without %s records" % (check, check))
            continue
        item = compare_runner(ctx, path, check, [size] if check == "size" else power_cells, power)
        runner.append(item)
        rep.say("  %s: %d fields compared, %d differ; absent fields %s" % (path.name, item["compared"],
                                                                         len(item["differences"]),
                                                                         item["absent"] or "none"))
    if not runner:
        rep.say("  no runner summary given or found: not compared")
    # 6. result
    rep.say("")
    rep.say("[6] RESULT")
    if rep.missing_fields:
        rep.say("  fields needed but not found (count of lines): %s" % json.dumps(rep.missing_fields, sort_keys=True))
    rep.say("  notes: %d (in the JSON report)" % len(rep.notes))
    rep.say("  problems and disagreements: %d" % len(rep.problems))
    for item in rep.problems[:args.max_print]:
        rep.say("    - %s: %s" % (item["where"], item["message"]))
    if len(rep.problems) > args.max_print:
        rep.say("    ... %d more in the JSON report" % (len(rep.problems) - args.max_print))
    status = 0 if not rep.problems else 1
    rep.say("  exit status %d (%s)" % (status, "everything checked agrees" if status == 0 else
                                        "a problem or disagreement"))
    elapsed = time.time() - started
    rep.say("  finished in %.1f s" % elapsed)
    payload = dict(program="verify_e4_x3.py", version=VERSION, python=platform.python_version(),
                   numpy=np.__version__, platform=platform.platform(), elapsed_seconds=elapsed,
                   compute_seconds=compute_seconds, arguments=vars(args), files=ctx.files, coverage=cover,
                   fingerprint=reference, prereg=prereg,
                   sample=None if args.sample is None else dict(
                       seed=args.sample_seed, requested=args.sample,
                       records=[list(ctx.jobs[i]["key"]) for i in chosen]),
                   per_record=[dict(record=list(r["key"]), status=r["status"], basis=r["basis"], S=r["S"],
                                    p=r["p"], K=r["K"], retained=r["retained"], valid=r["valid"],
                                    rejected=bool(r["rejected"]), max_diff=r["max_diff"],
                                    regeneration_identical=r["regeneration_identical"],
                                    problems=len(r["issues"])) for r in results],
                   maxima=dict(maxima, regeneration=regen_max), near_ties=near_ties,
                   stored_near_ties=stored_near_ties, size=size, power_cells=power_cells, power=power,
                   verdicts=verdicts, runner=runner, missing_fields=rep.missing_fields, notes=rep.notes,
                   problems=rep.problems, exit_status=status)
    if args.report:
        with open(args.report, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=1, default=str)
            handle.write("\n")
    return payload


def main(argv=None):
    try:
        payload = verify(argv)
    except UsageError as error:
        print(str(error), file=sys.stderr)
        return 2
    return payload["exit_status"]


if __name__ == "__main__":
    sys.exit(main())
