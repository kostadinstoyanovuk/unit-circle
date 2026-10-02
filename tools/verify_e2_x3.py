#!/usr/bin/env python3
"""verify_e2_x3.py - a second implementation of the E2 procedure and an independent check of its X.3 outputs.

Written from the registered texts alone: prereg/E2.md (OSF 4ncz2, SHA-256 7b103bb2...1e08786) sections 4 to 11
and Annex A; prereg/H1.md sections 4 to 9, which E2 incorporates ("Every H1 rule applies unchanged unless this
addendum states a replacement"); and the readings adopted where E2 is silent (docs/E2_READINGS.md, decision
D-060), each treated as part of the specification. It imports nothing from the research packages: Python's
standard library and NumPy only, so that it does not rest on the code it checks.

    python -B tools/verify_e2_x3.py <part files or directories> [--report out.json]
                                    [--all | --sample N] [--workers k] [--development] [--partial]
                                    [--prerequisite FILE] [--summary FILE]

The computational core, a small library in this file:
  * the intercept-inclusive OLS VAR(2) of every window of one or many series at once (E2 section 6): each
    window's lag columns centred and divided by their root-mean-square magnitude, the normal equations of the
    scaled columns solved in closed form, the intercepts from the means; a window whose lag block is nearly
    collinear is fitted by the section 6 recipe itself (`lstsq(rcond=None)`), whose rank decision then applies;
    the spectral radius M(t) is the largest modulus of the four eigenvalues of [[A1, A2], [I, 0]];
  * the episodes of g (section 7): runs of two or more quarters with g < 0, merged when onset - previous end
    <= 8 (chained, the first onset kept), an onset being eligible when M(r - 9) exists (r >= 48 at W = 40);
    S = the mean of M(r - 1) - M(r - 9) over the eligible episodes (section 8); a window that cannot be fitted
    anywhere in a series fails that series' M path and with it the statistic (reading R16);
  * the fitted null (section 9): the full-sample VAR(2) (n - 2 = 193 rows), strictly stable (a finite spectral
    radius below 1, reading R4, no projection), the conditional residual vectors centred column by column;
  * the surrogate draws: for attempts b = 0, 1, ... one integers(0, 193, size=193) call per attempt from the
    comparison's own Generator(PCG64(SeedSequence([seed, stream, cell, replicate]))), joint resampling of
    residual rows, regeneration from the first two observed vectors, all attempts of one record at once;
    primary mode detects the episodes of each surrogate g, fixed-date mode (power) uses the observed eligible
    onsets; a draw without an eligible episode is dropped and counted, a failure invalidates p;
    K = count(S_b >= S), B', p = (1 + K)/(B' + 1), q = K/B' and the Wilson interval (H1 section 6);
  * the X.3 synthetic design (section 11): the generating VAR (two copies of H1's AR(2), innovation correlation
    -0.5, stationary start through the Cholesky factor of [[1, 1/3], [1/3, 1]] kron (100/88) Sigma, innovations
    `standard_normal((193, 2)) @ L.T`), the planted persistence at positions r - 8, ..., r - 1 before the imposed
    onsets 77 and 148 (kappa*A1, kappa^2*A2 and the mean-preserving intercept; base values at kappa = 1);
    size cells (stream 5220, surrogates 5221), power cells (5230, fixed-date surrogates 5231), a rejection being
    a valid raw p <= 0.05, the size band 0.02-0.09 with all 200 valid, cell summaries, adjacent differences
    with the 1.96-SE decrease flag and D80 by the first raw crossing (H1 section 9).

The check of the X.3 output files (JSON Lines: a manifest line, then run-start lines of record type "session",
then one "replicate" line per series): the design (every coordinate once, none outside, sizes), one code
identity, mode, seed, prerequisite and gate across all manifests and records, each stored input against its
SHA-256 and against the series its generation coordinates give, and an independent recomputation from the stored
input alone of the window fits of the series, the episodes, the observed S, the fitted null, the random-number
states, every surrogate attempt (status, eligible onsets, changes, S_b) and so K, B', p, q and the Wilson
interval; then the size and power summaries, flags and D80 from the recomputed p-values, compared with the
runner's summaries where they are present, and the prerequisite record (AT-12 through the spectral-radius
function and the reduction to H1's AR(2), recomputed). Counts are compared exactly; floats agree when
|a - b| <= 1e-12 + 1e-9*|b|. A surrogate statistic within 1e-9 of the observed S is reported as a near tie.

Exit status: 0 everything checked agrees and nothing is missing; 1 a problem or a disagreement; 2 a usage or
input error. The registered pass or fail of the cells is reported, not encoded in the exit status.
"""
import argparse
import copy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
import sys
import time

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")      # the work is split over processes; one BLAS thread each

import numpy as np

VERSION = "1.0 (2 October 2026)"
E2_SHA256 = "7b103bb2cc314977cb30446a924d8d975850369f01ebc4819eb6da24f1e08786"
E2_GATE = dict(tag="prereg-E2", registration_id="4ncz2", doi="10.17605/OSF.IO/4NCZ2",
               tag_commit="46174d12c716d2c9ef0bfb4e7e8ed958f259e7c6", protocol_sha256=E2_SHA256)
E1_FROZEN_CODE_SHA256 = "c42cbbf35734eb4f8c12aff22384371aa4fad107ae283f6d2f5f6f93c12feef7"
IDENTITY_OPTION = "e1-superset"
Z_WILSON = 1.959963984540054              # H1 section 6
DECREASE_Z = Fraction(196, 100)           # H1 section 9: "exceeds 1.96 times that standard error"
ALPHA = Fraction(5, 100)                  # a rejection is a valid raw p <= 0.05
BAND = (Fraction(2, 100), Fraction(9, 100))
TARGET = Fraction(80, 100)                # D80: first raw crossing of 0.80
KAPPAS = (1.0, 1.2, 1.4, 1.6)
REGISTERED_SEED = 1927
N_SERIES = 200
B_ATTEMPTS = 1000
K = 2                                     # X = (g, du)
N_OBS = 195                               # section 5: 195 observations, positions 0..194
N_ROWS = N_OBS - 2                        # 193 regression rows of the null, 193 x 2 residual matrix
WINDOW = 40                               # section 6
LOOKBACK = 8                              # Delta = M(r - 1) - M(r - 9)
MINIMUM_RUN = 2
MERGE = 8
FIRST = WINDOW - 1                        # the first window ends at position W - 1 = 39
ELIGIBLE_FROM = WINDOW + LOOKBACK         # onset r is eligible iff M(r - 9) exists: r - 9 >= W - 1
SIGNAL_LENGTH = 8                         # planted positions r - 8, ..., r - 1
POWER_ONSETS = (77, 148)                  # section 7 list, section 11 imposed onsets
# Annex A
REGISTERED_STREAMS = dict(primary=5200, window32=5201, window48=5202, fixed=5203, wild=5204, interval=5205,
                          size_generation=5220, size_null=5221, power_generation=5230, power_null=5231,
                          at12=2012)
# Registered or planned stream ids of the programme (never used by a development run).
RESERVED_STREAMS = frozenset(list(range(100, 106)) + [200, 201, 300, 301, 400, 401, 1001, 1013, 2008, 2012]
                             + list(range(5100, 5432)))
DEVELOPMENT_STREAM_FLOOR = 9000
# Section 11 generating VAR: A1 = 0.3 I, A2 = 0.1 I, mu = (2.5, 0), c = (I - A1 - A2) mu = (1.5, 0)
PHI1, PHI2 = 0.3, 0.1
BASE_INTERCEPT = (1.5, 0.0)
MU = (2.5, 0.0)
SIGMA = ((3.5 ** 2, -0.5 * 3.5 * 1.0), (-0.5 * 3.5 * 1.0, 1.0 ** 2))
SIGMA_FACTOR = ((3.5, 0.0), (-0.5, 0.8660254037844386))      # printed in section 11
TIME_CORRELATION = ((1.0, 1 / 3), (1 / 3, 1.0))              # [[1, 1/3], [1/3, 1]]
DESIGN_SCALE = 100 / 88
# H1 section 9 generator of the prerequisite fixture (reduction test): 259 values
H1_N = 259
H1_A, H1_B, H1_C, H1_SIGMA = 0.3, 0.1, 1.5, 3.5
AT12_DRAWS = dict(registered=100_000)
REDUCTION_WINDOWS = (32, 40, 48)
REDUCTION_TOLERANCE = 1e-10
# Agreement. Counts are exact. Floats recomputed here by another numerical route (closed-form normal equations
# on scaled columns, a recursion regenerated for all attempts at once) differ from the stored values by rounding
# only, of order 1e-14; the tolerance sits far above that and far below any difference of substance.
FLOAT_REL, FLOAT_ABS = 1e-9, 1e-12
NEAR_TIE = 1e-9                           # |S_b - S| <= 1e-9 is reported as a near tie, not silently classified
# A window whose scaled lag-block correlation matrix has a determinant below this is fitted by the section 6
# lstsq recipe itself (never met on random data); the closed form is used above it.
ILL_DET = 1e-6
P_LABEL = "raw, not family-adjusted"
STATUSES = ("ok", "observed_not_estimable", "observed_statistic_failed", "null_model_failed",
            "invalid_surrogate_failure", "no_retained_surrogates", "generation_failed", "comparison_failed")

SIZE_CLAUSE = ("prereg/E2.md", "section 11, Size (AT-15 adapted)",
               "Pass: an empirical rejection rate (raw p ≤ 0.05) between **0.02 and 0.09** inclusive, with all 200 "
               "replicates valid. Failure accounting and uncertainty reporting follow H1 §9.")
POWER_CLAUSE = ("prereg/E2.md", "section 11, Power (AT-16 adapted)",
                "**Pass:** all four cells valid (all 200 replicates with finite S and a valid p) and no adjacent "
                "decrease flagged (H1 §9, AT-16). D80 need not be defined.")
AT16_CLAUSE = ("prereg/H1.md", "section 9, Cell reporting",
               "If any cell is invalid/incomplete or a decrease exceeds this threshold, AT-16 does not pass and G2 "
               "remains pending.")
VALID_CELL_CLAUSE = ("prereg/H1.md", "section 9, Cell reporting",
                     "A cell is complete and valid only when all 200 provide finite S and valid p.")


class NullFailure(Exception):
    """The fitted null cannot be used (section 9: an unstable or unidentified null fails the comparison)."""


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
    against NaN). Shapes must agree; otherwise (None, False)."""
    try:
        a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    except (TypeError, ValueError):
        return None, False
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


def input_sha256(values):
    """SHA-256 of the float64 little-endian bytes of the stored input (row-major, 195 x 2)."""
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


# ------------------------------------------------------------------------ the kernel (E2 sections 6-9)

def radius_of(a1, a2):
    """Spectral radius of the companion matrix [[A1, A2], [I, 0]] for stacks of finite (k, k) matrices (section
    6): the largest modulus of the 2k eigenvalues from numpy.linalg.eigvals; NaN where the solver fails."""
    a1, a2 = np.asarray(a1, dtype=float), np.asarray(a2, dtype=float)
    k = a1.shape[-1]
    shape = a1.shape[:-2]
    if int(np.prod(shape, dtype=np.int64)) == 0:
        return np.empty(shape)
    companion = np.zeros(shape + (2 * k, 2 * k))
    companion[..., :k, :k] = a1
    companion[..., :k, k:] = a2
    companion[..., k:, :k] = np.eye(k)
    try:
        return np.abs(np.linalg.eigvals(companion)).max(axis=-1)
    except np.linalg.LinAlgError:
        out = np.full(shape, np.nan)
        for index in np.ndindex(*shape):
            try:
                out[index] = np.abs(np.linalg.eigvals(companion[index])).max()
            except np.linalg.LinAlgError:
                pass
        return out


def lstsq_fit(window_values):
    """The section 6 recipe for one window, used where the closed form is ill-conditioned: centre each lag
    column, divide it by its root mean square centred magnitude, solve both responses with lstsq(rcond=None),
    require rank 2k and finite values, undo the scaling, recover the intercepts from the means. Returns
    (intercept, A1, A2), None on a failure."""
    w = np.asarray(window_values, dtype=float)
    k = w.shape[1]
    response = w[2:]
    lags = np.hstack((w[1:-1], w[:-2]))
    lag_mean, response_mean = lags.mean(axis=0), response.mean(axis=0)
    centred = lags - lag_mean
    scale = np.sqrt(np.mean(centred ** 2, axis=0))
    if not np.isfinite(scale).all() or np.any(scale == 0):
        return None
    solution, _, rank, _ = np.linalg.lstsq(centred / scale, response - response_mean, rcond=None)
    if rank != 2 * k:
        return None
    beta = solution / scale[:, None]
    intercept = response_mean - lag_mean @ beta
    if not (np.isfinite(beta).all() and np.isfinite(intercept).all()):
        return None
    return intercept, beta[:k].T, beta[k:].T


def _fit_chunk(x, window):
    """Fits of every window of each series of x (p, n, k): arrays ok (p, nw), intercept (p, nw, k), a1 and a2
    (p, nw, k, k) and the number of windows fitted by the lstsq recipe."""
    p, n, k = x.shape
    nw = n - window + 1
    rows = window - 2
    view = np.lib.stride_tricks.sliding_window_view(x, window, axis=1)           # (p, nw, k, window)
    response = view[..., 2:]
    lags = np.concatenate((view[..., 1:-1], view[..., :-2]), axis=2)             # (p, nw, 2k, rows): lag 1, lag 2
    with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        lag_mean = lags.mean(axis=-1)
        response_mean = response.mean(axis=-1)
        centred = lags - lag_mean[..., None]
        scale = np.sqrt((centred * centred).mean(axis=-1))                      # root-mean-square magnitude
        scaled = centred / scale[..., None]
        response_centred = response - response_mean[..., None]
        gram = np.einsum("pwir,pwjr->pwij", scaled, scaled)                      # rows x correlation matrix
        cross = np.einsum("pwir,pwjr->pwij", scaled, response_centred)
        det = np.linalg.det(gram)
        usable = np.isfinite(scale).all(axis=-1) & (scale > 0).all(axis=-1)
        good = usable & np.isfinite(det) & (det > ILL_DET * float(rows) ** (2 * k))
        safe = np.where(good[..., None, None], gram, np.eye(2 * k))
        beta_scaled = np.linalg.solve(safe, np.where(good[..., None, None], cross, 0.0))
        beta = beta_scaled / scale[..., :, None]
        intercept = response_mean - np.einsum("pwi,pwij->pwj", lag_mean, beta)
        a1 = np.swapaxes(beta[..., :k, :], -1, -2).copy()
        a2 = np.swapaxes(beta[..., k:, :], -1, -2).copy()
        ok = good & np.isfinite(beta).all(axis=(-1, -2)) & np.isfinite(intercept).all(axis=-1)
    fallbacks = 0
    for index in zip(*np.nonzero(usable & ~good)):
        fallbacks += 1
        fit = lstsq_fit(view[index].T)
        if fit is None:
            ok[index] = False
            intercept[index], a1[index], a2[index] = np.nan, np.nan, np.nan
        else:
            ok[index] = True
            intercept[index], a1[index], a2[index] = fit
    return ok, intercept, a1, a2, fallbacks


def fit_windows(x, window=WINDOW, chunk=64):
    """Section 6 for every window of every series: x has shape (n, k) or (p, n, k). Window w of a series is
    the one that ends at position w + window - 1; its first two vectors serve only as lags, so it has
    window - 2 regression rows. Returns dict(ok, intercept, a1, a2, fallbacks) with the window axis second.
    A window fails (ok False) when a lag column has zero or non-finite scale, the lag block has rank below 2k
    or a coefficient is not finite; a non-finite value in a window propagates to a failure."""
    x = np.asarray(x, dtype=float)
    if x.ndim == 2:
        x = x[None]
    p, n, k = x.shape
    nw = max(n - window + 1, 0)
    out = dict(ok=np.zeros((p, nw), dtype=bool), intercept=np.full((p, nw, k), np.nan),
               a1=np.full((p, nw, k, k), np.nan), a2=np.full((p, nw, k, k), np.nan), fallbacks=0)
    if nw == 0:
        return out
    for start in range(0, p, chunk):
        stop = min(start + chunk, p)
        ok, intercept, a1, a2, fallbacks = _fit_chunk(x[start:stop], window)
        out["ok"][start:stop], out["intercept"][start:stop] = ok, intercept
        out["a1"][start:stop], out["a2"][start:stop] = a1, a2
        out["fallbacks"] += fallbacks
    return out


def rolling_modulus(x, window=WINDOW, need=None, chunk=64):
    """(M, ok, fits): M(t) at every window of every series (NaN where the window failed), or only where the
    boolean array `need` (p, nw) is set; ok is the fit status of every window."""
    fits = fit_windows(x, window, chunk)
    modulus = np.full(fits["ok"].shape, np.nan)
    select = fits["ok"] if need is None else fits["ok"] & np.asarray(need, dtype=bool)
    if select.any():
        index = np.nonzero(select)
        modulus[index] = radius_of(fits["a1"][index], fits["a2"][index])
    return modulus, fits["ok"], fits


def negative_runs(g, minimum=MINIMUM_RUN):
    """Section 7: maximal runs of consecutive quarters with g < 0 that last at least `minimum` quarters, as
    (first position, last position)."""
    runs, start = [], None
    for position, value in enumerate(g):
        if value < 0:
            if start is None:
                start = position
        elif start is not None:
            if position - start >= minimum:
                runs.append((start, position - 1))
            start = None
    if start is not None and len(g) - start >= minimum:
        runs.append((start, len(g) - 1))
    return runs


def merged_episodes(g, merge=MERGE):
    """Section 7: qualifying runs merge when onset - previous end <= 8, with chained merges; the episode keeps
    its first onset and takes the last run's end. Returns [(onset, end), ...]."""
    episodes = []
    for start, end in negative_runs(g):
        if episodes and start - episodes[-1][1] <= merge:
            episodes[-1] = (episodes[-1][0], end)
        else:
            episodes.append((start, end))
    return episodes


def pre_onset_values(modulus_row, onsets):
    """Section 8 for one M path (window axis, entry w for the window ending at position w + 39): for each onset
    r, M(r - 9) must exist (r - 9 >= 39); Delta = M(r - 1) - M(r - 9). Returns (eligible, ineligible,
    changes) in onset order."""
    eligible, ineligible, changes = [], [], []
    for r in onsets:
        earlier, later = r - LOOKBACK - 1, r - 1
        if earlier < FIRST:
            ineligible.append(r)
            continue
        eligible.append(r)
        changes.append(float(modulus_row[later - FIRST] - modulus_row[earlier - FIRST]))
    return eligible, ineligible, changes


def mean_of(values):
    return math.fsum(values) / len(values)


def observed_result(x, fixed=None, fits=None):
    """Sections 7-8 on one 195 x 2 series: the onsets (the merged episodes of g, or the supplied fixed dates),
    the eligible ones, Delta for each and S. status: ok, observed_not_estimable (no onset reaches 48: nothing is
    fitted, as the statistic then needs no M) or observed_statistic_failed (a window fit failed anywhere in the
    series, or S is not finite). `fits` may carry the (modulus, ok, fits) of all windows already computed."""
    onsets = list(fixed) if fixed is not None else [start for start, _ in merged_episodes(x[:, 0])]
    out = dict(status=None, S=None, changes=[], eligible=[], ineligible=list(onsets), onsets=onsets, error=None)
    if not any(r >= ELIGIBLE_FROM for r in onsets):
        out["status"] = "observed_not_estimable"
        return out
    modulus, ok, _ = fits if fits is not None else rolling_modulus(x[None], WINDOW)
    if not ok.all():
        out["status"] = "observed_statistic_failed"
        out["error"] = "window fit failed at positions %s" % [int(w) + FIRST for w in np.flatnonzero(~ok[0])[:5]]
        return out
    eligible, ineligible, changes = pre_onset_values(modulus[0], onsets)
    value = mean_of(changes) if changes else None
    if value is None or not all(math.isfinite(c) for c in changes):
        out["status"] = "observed_statistic_failed"
        out["error"] = "a pre-onset change is not finite"
        return out
    out.update(status="ok", S=value, changes=changes, eligible=eligible, ineligible=ineligible)
    return out


def fit_null(x):
    """Section 9: the intercept-inclusive OLS VAR(2) on all n vectors (n - 2 rows, section 6 numerics), strictly
    stable (a finite spectral radius below 1; reading R4: that and nothing else, no projection), the n - 2 x 2
    conditional residual vectors with each column's arithmetic mean subtracted explicitly."""
    x = np.asarray(x, dtype=float)
    if x.ndim != 2 or len(x) < 2 * x.shape[1] + 3:
        raise NullFailure("too few regression rows")
    if not np.isfinite(x).all():
        raise NullFailure("non-finite value in the series")
    fits = fit_windows(x, window=len(x))
    if not bool(fits["ok"][0, 0]):
        raise NullFailure("the full-sample fit is not identified (rank below four or a non-finite value)")
    intercept, a1, a2 = fits["intercept"][0, 0], fits["a1"][0, 0], fits["a2"][0, 0]
    radius = float(radius_of(a1, a2))
    residuals = x[2:] - intercept - x[1:-1] @ a1.T - x[:-2] @ a2.T
    if not (np.isfinite(residuals).all() and math.isfinite(radius)):
        raise NullFailure("non-finite residual or spectral radius")
    if not radius < 1:
        raise NullFailure("not strictly stable (spectral radius %.6g)" % radius)
    mean = residuals.mean(axis=0)
    return dict(intercept=intercept, a1=a1, a2=a2, modulus=radius, n=len(x), initial=(x[0].copy(), x[1].copy()),
                residuals=residuals - mean, residual_mean_removed=mean)


def generator(seed, stream, cell, replicate):
    """Annex A: NumPy Generator with PCG64 from SeedSequence([seed, stream, cell, replicate])."""
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, stream, cell, replicate])))


def draw_indices(gen, rows, attempts):
    """Section 9: for attempts b = 0, 1, ... in order, one integers(0, rows, size=rows) call each."""
    indices = np.empty((attempts, rows), dtype=np.int64)
    for b in range(attempts):
        indices[b] = gen.integers(0, rows, size=rows)
    return indices


def regenerate(null, indices):
    """Section 9: positions 2, ..., n - 1 from the observed X[0], X[1] with the fitted intercept and matrices
    and the selected residual rows (both components together): X[t] = c + A1 X[t-1] + A2 X[t-2] + e, in order,
    for every attempt (row of indices) at once. Returns paths (attempts, n, k)."""
    indices = np.asarray(indices)
    n, k = null["n"], len(null["intercept"])
    innovations = null["residuals"][indices]                                      # (attempts, n - 2, k)
    paths = np.empty((indices.shape[0], n, k))
    paths[:, 0, :], paths[:, 1, :] = null["initial"]
    c, a1t, a2t = null["intercept"], null["a1"].T, null["a2"].T
    with np.errstate(over="ignore", invalid="ignore"):
        for t in range(2, n):
            paths[:, t, :] = c + paths[:, t - 1, :] @ a1t + paths[:, t - 2, :] @ a2t + innovations[:, t - 2, :]
    return paths


def attempt_results(paths, mode, fixed=None, chunk=64):
    """Sections 7-9 for each surrogate path: status retained / no_eligible_episode / failed, S_b, the eligible
    onsets and the changes. A path with a non-finite value, a window that fails anywhere (only evaluated when
    the path has an eligible onset: reading R16) or a non-finite statistic fails; primary mode detects the
    episodes of the path's g, fixed mode uses the supplied dates."""
    attempts = paths.shape[0]
    nw = paths.shape[1] - WINDOW + 1
    status = ["retained"] * attempts
    statistic = np.full(attempts, np.nan)
    eligible = [()] * attempts
    changes = [()] * attempts
    onsets = [None] * attempts
    needing = []
    for b in range(attempts):
        if not np.isfinite(paths[b]).all():
            status[b] = "failed"
            continue
        onsets[b] = list(fixed) if mode == "fixed" else [s for s, _ in merged_episodes(paths[b, :, 0])]
        if any(r >= ELIGIBLE_FROM for r in onsets[b]):
            needing.append(b)
        else:
            status[b] = "no_eligible_episode"
    for start in range(0, len(needing), chunk):
        rows = needing[start:start + chunk]
        need = np.zeros((len(rows), nw), dtype=bool)
        for i, b in enumerate(rows):
            for r in onsets[b]:
                if r - LOOKBACK - 1 >= FIRST:
                    need[i, r - 1 - FIRST] = need[i, r - LOOKBACK - 1 - FIRST] = True
        modulus, ok, _ = rolling_modulus(paths[rows], WINDOW, need)
        for i, b in enumerate(rows):
            if not ok[i].all() or not np.isfinite(modulus[i][need[i]]).all():
                status[b] = "failed"
                continue
            e, _, c = pre_onset_values(modulus[i], onsets[b])
            value = mean_of(c)
            if not math.isfinite(value):
                status[b] = "failed"
                continue
            statistic[b], eligible[b], changes[b] = value, tuple(e), tuple(c)
    return dict(status=status, statistic=statistic, eligible=eligible, changes=changes)


def e2_comparison(x, *, mode, fixed, seed, stream, cell, replicate, attempts, surrogates=True, fits=None):
    """Sections 7-9 on one series. mode "primary" (size) detects the episodes of g in the series and in every
    surrogate; mode "fixed" (power) uses the supplied dates, the observed eligible ones in every surrogate.
    The observed statistic comes first; if it cannot be formed no null is fitted and nothing is drawn; a failed
    null fails the comparison before any draw. With surrogates=False the draws are made (so that the generator
    states can be checked) but no path is regenerated."""
    out = dict(status=None, observed=None, null=None, null_error=None, rng_fresh=None, rng_before=None,
               rng_after=None, indices=None, attempt_status=None, statistics=None, eligible=None, changes=None,
               K=None, retained=None, no_episode=None, failed=None, attempted=None, p=None, q=None, wilson=None,
               grid=None, near_ties=[], regenerated=bool(surrogates))
    gen = generator(seed, stream, cell, replicate)
    out["rng_fresh"] = copy.deepcopy(gen.bit_generator.state)
    observed = observed_result(x, fixed if mode == "fixed" else None, fits)
    out["observed"] = observed
    if observed["status"] != "ok":
        out["status"] = observed["status"]
        return out
    try:
        out["null"] = fit_null(x)
    except NullFailure as error:
        out["status"], out["null_error"] = "null_model_failed", str(error)
        return out
    out["rng_before"] = copy.deepcopy(gen.bit_generator.state)
    out["indices"] = draw_indices(gen, len(x) - 2, attempts)
    out["rng_after"] = copy.deepcopy(gen.bit_generator.state)
    if not surrogates:
        out["status"] = "not_regenerated"
        return out
    results = attempt_results(regenerate(out["null"], out["indices"]), mode,
                              observed["eligible"] if mode == "fixed" else None)
    status, statistic = results["status"], results["statistic"]
    retained_mask = np.array([s == "retained" for s in status])
    failed = sum(s == "failed" for s in status)
    empty = sum(s == "no_eligible_episode" for s in status)
    retained = int(retained_mask.sum())
    S = observed["S"]
    count = int(np.sum(statistic[retained_mask] >= S)) if retained else None
    out.update(attempt_status=status, statistics=statistic, eligible=results["eligible"],
               changes=results["changes"], K=count, retained=retained, no_episode=empty, failed=failed,
               attempted=len(status))
    out["near_ties"] = [dict(attempt=int(b), statistic=float(statistic[b]), difference=float(statistic[b] - S))
                        for b in np.flatnonzero(retained_mask & (np.abs(statistic - S) <= NEAR_TIE))]
    if failed:
        out["status"] = "invalid_surrogate_failure"
    elif not retained:
        out["status"] = "no_retained_surrogates"
    else:
        out["status"] = "ok"
        out["p"] = (1 + count) / (retained + 1)
        out["q"] = count / retained
        out["wilson"] = wilson(count, retained)
    if retained:
        out["grid"] = 1 / (retained + 1)
    return out


# --------------------------------------------------------------------- the X.3 synthetic design (section 11)

def design_series(seed, stream, cell, replicate, kappa=1.0, onsets=(), n=N_OBS):
    """Section 11, the generating VAR: A1 = 0.3 I, A2 = 0.1 I, mu = (2.5, 0), c = (1.5, 0), innovation
    covariance Sigma with correlation -0.5, no burn-in. One standard_normal(4) call gives the stationary start
    (2.5, 0, 2.5, 0) + C z, C the lower Cholesky factor (numpy.linalg.cholesky) of [[1, 1/3], [1/3, 1]] kron
    (100/88) Sigma; one standard_normal((n - 2, 2)) call, `z @ L.T` with L = [[3.5, 0], [-0.5, 0.866...]], gives
    the innovation vector of position i + 2 in row i; then the recursion in order. In the eight positions r - 8,
    ..., r - 1 before each imposed onset r the coefficients are kappa*A1, kappa^2*A2 and the intercept
    (I - kappa*A1 - kappa^2*A2) mu; everywhere else, and at kappa = 1, the base values (reading R7).
    Returns (series, generator state before the draws, state after them)."""
    gen = generator(seed, stream, cell, replicate)
    before = copy.deepcopy(gen.bit_generator.state)
    initial_factor = np.linalg.cholesky(np.kron(np.array(TIME_CORRELATION), DESIGN_SCALE * np.array(SIGMA)))
    start = np.array([MU[0], MU[1], MU[0], MU[1]]) + initial_factor @ gen.standard_normal(2 * K)
    noise = gen.standard_normal((n - 2, K)) @ np.array(SIGMA_FACTOR).T
    after = copy.deepcopy(gen.bit_generator.state)
    kappa = float(kappa)
    planted = np.zeros(n, dtype=bool)
    for r in onsets:
        planted[r - SIGNAL_LENGTH:r] = True
    planted_a, planted_b = kappa * PHI1, kappa ** 2 * PHI2
    planted_c = (((1.0 - planted_a) - planted_b) * MU[0], 0.0)
    x = np.empty((n, K))
    x[0], x[1] = start[:K], start[K:]
    for t in range(2, n):
        if planted[t] and kappa != 1.0:
            c, a, b = planted_c, planted_a, planted_b
        else:
            c, a, b = BASE_INTERCEPT, PHI1, PHI2
        for j in range(K):
            x[t, j] = ((c[j] + a * x[t - 1, j]) + b * x[t - 2, j]) + noise[t - 2, j]
    return x, before, after


def h1_series(seed, stream, cell, replicate, form="text", n=H1_N):
    """The H1 section 9 generator (259 observations, a = 0.3, b = 0.1, c = 1.5, s.d. 3.5, no burn-in), used for
    the reduction test of the prerequisite: one standard_normal(2) call for the stationary initial pair, then
    one normal(0, 3.5, size=257) call. x[0] = mu + sqrt(v) z0, x[1] = mu + (h/sqrt(v)) z0 + sqrt(v - h^2/v) z1.
    form "text": mu = c/(1 - a - b), v = 3.5^2 (1 - b)/((1 + b)((1 - b)^2 - a^2)), h = a v/(1 - b); form "closed":
    mu = 2.5, v = 1225/88, h = v/3, the same numbers written as constants (they may differ in the last bit)."""
    gen = generator(seed, stream, cell, replicate)
    if form == "text":
        mu = H1_C / (1 - H1_A - H1_B)
        v = H1_SIGMA ** 2 * (1 - H1_B) / ((1 + H1_B) * ((1 - H1_B) ** 2 - H1_A ** 2))
        h = H1_A * v / (1 - H1_B)
    else:
        mu, v = 2.5, 1225 / 88
        h = v / 3
    z = gen.standard_normal(2)
    innovations = gen.normal(0, H1_SIGMA, size=n - 2)
    x = np.empty(n)
    x[0] = mu + math.sqrt(v) * z[0]
    x[1] = mu + (h / math.sqrt(v)) * z[0] + math.sqrt(v - h * h / v) * z[1]
    for t in range(2, n):
        x[t] = H1_C + H1_A * x[t - 1] + H1_B * x[t - 2] + innovations[t - 2]
    return x


def _lists(array):
    return np.asarray(array, dtype=float).tolist()


def build_record(x, *, seed, streams, check, cell_index, replicate, attempts, kappa=None, onsets=POWER_ONSETS,
                 mode="development", code_sha256="0" * 64, settings=None, prerequisite_sha256=None,
                 generation_states=None):
    """A replicate record in the layout of the X.3 output files, made by this implementation (used by the tests
    and the cross-check: constructed inputs, development seeds)."""
    x = np.asarray(x, dtype=float)
    stream = streams["size_null" if check == "size" else "power_null"]
    kernel_mode = "primary" if check == "size" else "fixed"
    all_fits = rolling_modulus(x[None], WINDOW)
    result = e2_comparison(x, mode=kernel_mode, fixed=onsets, seed=seed, stream=stream, cell=cell_index,
                           replicate=replicate, attempts=attempts, fits=all_fits)
    obs = result["observed"]
    observed = None
    if obs["status"] in ("ok", "observed_not_estimable"):
        observed = dict(mean_change=obs["S"], changes=list(obs["changes"]), eligible_onsets=list(obs["eligible"]),
                        ineligible_onsets=list(obs["ineligible"]))
    status = result["status"]
    attempts_out, null_model = None, None
    if result["attempt_status"] is not None:
        attempts_out = []
        for b in range(attempts):
            kind = result["attempt_status"][b]
            attempts_out.append(dict(number=b, status=kind, statistic=(float(result["statistics"][b])
                                                                      if kind == "retained" else None),
                                     eligible_onsets=list(result["eligible"][b]), changes=list(result["changes"][b]),
                                     error="FloatingPointError: constructed" if kind == "failed" else None))
    elif status == "observed_not_estimable":
        attempts_out = []
    if result["null"] is not None:
        nl = result["null"]
        null_model = dict(intercept=_lists(nl["intercept"]), coefficients=[_lists(nl["a1"]), _lists(nl["a2"])],
                          initial=[_lists(nl["initial"][0]), _lists(nl["initial"][1])],
                          residuals=_lists(nl["residuals"]), residual_mean_removed=_lists(nl["residual_mean_removed"]),
                          modulus=nl["modulus"])
    comparison = None
    counts = dict(requested=attempts, attempted=0, retained=0, no_episode=0, failed=0, exceedances=None)
    if status in ("ok", "invalid_surrogate_failure", "no_retained_surrogates", "observed_not_estimable"):
        if status != "observed_not_estimable":
            counts = dict(requested=attempts, attempted=result["attempted"], retained=result["retained"],
                          no_episode=result["no_episode"], failed=result["failed"], exceedances=result["K"])
        rng_before = result["rng_before"] if result["rng_before"] is not None else result["rng_fresh"]
        rng_after = result["rng_after"] if result["rng_after"] is not None else result["rng_fresh"]
        comparison = dict(status=status, observed=observed, p_value=result["p"], **counts,
                          p_grid_spacing=result["grid"], attempts=attempts_out, null_model=null_model, window=WINDOW,
                          lookback=LOOKBACK, merge=MERGE,
                          onset_mode="endogenous" if check == "size" else "external_fixed",
                          innovation_mode="residual", rng_before=rng_before, rng_after=rng_after)
    fits = all_fits[2]
    if bool(all_fits[1].all()):
        window_fits = dict(window=WINDOW, first_position=FIRST, error=None, modulus=_lists(all_fits[0][0]),
                           intercept=_lists(fits["intercept"][0]), A1=_lists(fits["a1"][0]), A2=_lists(fits["a2"][0]))
    else:
        window_fits = dict(window=WINDOW, first_position=FIRST, error="ValueError: constructed")
    record = dict(cell="size" if check == "size" else "power_%d" % cell_index, cell_index=cell_index,
                  replicate=replicate, status=status, input=[[float(a), float(b)] for a, b in x],
                  input_sha256=input_sha256(x),
                  generation_rng_before=(generation_states or (None, None))[0],
                  analysis_rng_before=result["rng_fresh"], S=obs["S"], p_value=result["p"], observed=observed,
                  comparison=comparison, error=obs["error"] if status == "observed_statistic_failed" else
                  (result["null_error"] if status == "null_model_failed" else None),
                  surrogate_requested=attempts, surrogate_attempted=counts["attempted"],
                  surrogate_retained=counts["retained"], surrogate_no_episode=counts["no_episode"],
                  surrogate_failed=counts["failed"], surrogate_exceedances=counts["exceedances"],
                  surrogate_exceedance_rate=result["q"], surrogate_exceedance_wilson=result["wilson"],
                  generation_rng_after=(generation_states or (None, None))[1],
                  analysis_rng_after=result["rng_after"] if result["rng_after"] is not None else result["rng_fresh"],
                  settings=settings or {}, window_fits=window_fits)
    record.update(record_type="replicate", registered=mode == "registered", mode=mode, master_seed=seed,
                  B=attempts, code_sha256=code_sha256)
    if check == "power":
        record["kappa"] = float(KAPPAS[cell_index] if kappa is None else kappa)
    if prerequisite_sha256:
        record["prerequisite_sha256"] = prerequisite_sha256
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
    """Section 11: the rate R/n within [0.02, 0.09] inclusive (exact rationals) with all n valid."""
    band = bool(cell["complete"] and n and BAND[0] <= Fraction(cell["rejected"], n) <= BAND[1])
    all_valid = bool(cell["valid"] == n and cell["attempted"] == n)
    return dict(band=band, all_valid=all_valid, passed=band and all_valid)


# ------------------------------------------------------------------------ checking one record numerically

def _states_equal(stored, mine):
    return json.loads(json.dumps(stored)) == json.loads(json.dumps(mine))


def _compare_state(issues, notes, label, stored, mine):
    if mine is None:
        return
    if stored is None:
        notes.append("%s not stored" % label)
    elif not _states_equal(stored, mine):
        issues.append("%s differs from the state of the recomputed draws" % label)


def _compare_changes(stored_lists, mine_lists):
    """(max |difference|, agree) of two lists of per-attempt change tuples."""
    if [len(a) for a in stored_lists] != [len(b) for b in mine_lists]:
        return None, False
    flat_a = np.fromiter((v for row in stored_lists for v in row), dtype=float)
    flat_b = np.fromiter((v for row in mine_lists for v in row), dtype=float)
    return max_abs_difference(flat_a, flat_b)


def check_numeric(job):
    """Every numerical check of one record from its stored input alone (run in a worker process when
    --workers > 1). Returns the findings; never raises for a problem of the data."""
    issues, notes = [], []
    stored = job["stored"]
    res = dict(key=job["key"], where=job["where"], issues=issues, notes=notes, full=job["full"], S=None, p=None,
               K=None, retained=None, status=None, stored_status=stored["status"], valid=False, rejected=False,
               basis=None, fallbacks=0,
               max_diff=dict(fits=0.0, S=0.0, components=0.0, nulls=None, statistics=0.0, changes=0.0,
                             regeneration=None),
               near_ties=[], stored_near_ties=[], regeneration_identical=None)
    x = job["x"]
    if x is None:
        issues.append("no usable stored input: nothing can be recomputed")
        res["status"] = "no_input"
        return res
    # (a) the stored input against the section 11 generator at its generation coordinates
    if job["generation"] is not None:
        seed, stream, cell, replicate, kappa, onsets = job["generation"]
        series, before, after = design_series(seed, stream, cell, replicate, kappa, onsets)
        diff, agree = max_abs_difference(x, series)
        res["max_diff"]["regeneration"] = diff
        res["regeneration_identical"] = bool(np.array_equal(x, series))
        if not agree:
            issues.append("the stored input is not the series its generation coordinates give (max |difference| "
                          "%s)" % ("shape" if diff is None else "%.3g" % diff))
        _compare_state(issues, notes, "generation_rng_before", job["generation_rng_before"], before)
        _compare_state(issues, notes, "generation_rng_after", job["generation_rng_after"], after)
    # (b) the window fits of the series, then the observed statistic, null, draws and (if full) every attempt
    all_fits = rolling_modulus(x[None], WINDOW)
    res["fallbacks"] = all_fits[2]["fallbacks"]
    stored_fits = stored["window_fits"]
    if stored_fits is None:
        notes.append("window_fits not stored")
    elif stored_fits["error"] is not None:
        if bool(all_fits[1].all()):
            issues.append("window_fits records an error (%s), but every window can be fitted" % stored_fits["error"])
    elif not bool(all_fits[1].all()):
        issues.append("window_fits stored, but %d windows cannot be fitted" % int((~all_fits[1]).sum()))
    else:
        mine = dict(modulus=all_fits[0][0], intercept=all_fits[2]["intercept"][0], A1=all_fits[2]["a1"][0],
                    A2=all_fits[2]["a2"][0])
        largest = 0.0
        for field in ("modulus", "intercept", "A1", "A2"):
            diff, agree = max_abs_difference(stored_fits[field], mine[field])
            if not agree:
                issues.append("window_fits %s differ from the recomputed fits (max |difference| %s)" % (
                    field, "shape or value" if diff is None else "%.3g" % diff))
            elif diff is not None:
                largest = max(largest, diff)
        res["max_diff"]["fits"] = largest
        if (stored_fits.get("window"), stored_fits.get("first_position")) != (WINDOW, FIRST):
            issues.append("window_fits window %r, first position %r; expected %d and %d" % (
                stored_fits.get("window"), stored_fits.get("first_position"), WINDOW, FIRST))
    result = e2_comparison(x, mode=job["mode"], fixed=job["fixed"], seed=job["seed"], stream=job["stream"],
                           cell=job["cell"], replicate=job["replicate"], attempts=job["B"], surrogates=job["full"],
                           fits=all_fits)
    res["status"] = result["status"]
    obs = result["observed"]
    res["S"] = obs["S"]
    # the observed statistic
    stored_obs = stored["observed"]
    if obs["status"] == "ok":
        if stored_obs is None or stored_obs.get("mean_change") is None:
            issues.append("no observed statistic stored; recomputed S %r" % obs["S"])
        else:
            diff, agree = max_abs_difference(stored_obs["changes"], obs["changes"])
            res["max_diff"]["components"] = diff
            if not agree:
                issues.append("observed Delta per episode %s, recomputed %s" % (stored_obs["changes"], obs["changes"]))
            if not close(stored_obs["mean_change"], obs["S"]):
                issues.append("observed S %r, recomputed %r" % (stored_obs["mean_change"], obs["S"]))
            else:
                res["max_diff"]["S"] = abs(stored_obs["mean_change"] - obs["S"])
            if list(stored_obs["eligible_onsets"]) != obs["eligible"]:
                issues.append("eligible onsets %s, recomputed %s" % (stored_obs["eligible_onsets"], obs["eligible"]))
            if list(stored_obs["ineligible_onsets"]) != obs["ineligible"]:
                issues.append("ineligible onsets %s, recomputed %s" % (stored_obs["ineligible_onsets"],
                                                                       obs["ineligible"]))
        if not close(stored["S"], obs["S"]):
            issues.append("record S %r, recomputed %r" % (stored["S"], obs["S"]))
    elif obs["status"] == "observed_not_estimable":
        if stored_obs is None or stored_obs.get("mean_change") is not None or list(stored_obs.get("changes") or []):
            issues.append("recomputed: no episode reaches onset 48 (observed_not_estimable), but a statistic is stored")
        elif list(stored_obs.get("ineligible_onsets") or []) != obs["ineligible"]:
            issues.append("ineligible onsets %s, recomputed %s" % (stored_obs.get("ineligible_onsets"),
                                                                   obs["ineligible"]))
        if stored["S"] is not None:
            issues.append("record S %r, but the recomputed statistic is not estimable" % stored["S"])
    else:
        issues.append("recomputed observed statistic failed: %s" % obs["error"])
    # the fitted null
    if result["null_error"]:
        issues.append("recomputed null failed: %s" % result["null_error"])
    if result["null"] is not None:
        fit = result["null"]
        theirs = stored["null"]
        if theirs is None:
            notes.append("null_model not stored")
        else:
            largest = None
            for field in ("intercept", "a1", "a2", "initial0", "initial1", "residuals", "residual_mean_removed"):
                mine_value = (fit["initial"][0] if field == "initial0" else fit["initial"][1]
                              if field == "initial1" else fit[field])
                if theirs.get(field) is None:
                    issues.append("fitted null %s not stored" % field)
                    continue
                diff, agree = max_abs_difference(theirs[field], mine_value)
                if not agree:
                    issues.append("fitted null %s differ from the recomputed values (max |difference| %s)" % (
                        field, "shape or value" if diff is None else "%.3g" % diff))
                elif diff is not None:
                    largest = max(largest or 0.0, diff)
            if theirs.get("modulus") is None or not close(theirs["modulus"], fit["modulus"]):
                issues.append("fitted null modulus %r, recomputed %r" % (theirs.get("modulus"), fit["modulus"]))
            else:
                largest = max(largest or 0.0, abs(theirs["modulus"] - fit["modulus"]))
            res["max_diff"]["nulls"] = largest
    # the random-number states of the analysis
    after = result["rng_after"] if result["rng_after"] is not None else result["rng_fresh"]
    before = result["rng_before"] if result["rng_before"] is not None else result["rng_fresh"]
    _compare_state(issues, notes, "analysis_rng_before", job["analysis_rng_before"], result["rng_fresh"])
    _compare_state(issues, notes, "analysis_rng_after", job["analysis_rng_after"], after)
    if job["comparison_rng"] is not None:
        _compare_state(issues, notes, "comparison rng_before", job["comparison_rng"][0], before)
        _compare_state(issues, notes, "comparison rng_after", job["comparison_rng"][1], after)
    # (c) p from the stored surrogate statistics against the recomputed observed S (every record)
    attempts = stored["attempts"]
    if obs["status"] == "ok" and attempts is not None and len(attempts["status"]) and result["null"] is not None:
        stat = attempts["statistic"]
        retained_stored = np.array([s == "retained" for s in attempts["status"]])
        failed_stored = np.array([s == "failed" for s in attempts["status"]])
        k_cheap = int(np.sum(stat[retained_stored] >= obs["S"]))
        res["stored_near_ties"] = [int(b) for b in np.flatnonzero(retained_stored & (np.abs(stat - obs["S"]) <= NEAR_TIE))]
        if stored["K"] is not None and retained_stored.any() and k_cheap != stored["K"]:
            issues.append("exceedances %r, but %d stored surrogate statistics are >= the recomputed S%s" % (
                stored["K"], k_cheap, " (near ties at attempts %s)" % res["stored_near_ties"]
                if res["stored_near_ties"] else ""))
        if not job["full"]:
            res.update(K=k_cheap, retained=int(retained_stored.sum()), basis="stored surrogate statistics")
            if len(stat) == job["B"] and not failed_stored.any() and retained_stored.any():
                res["p"] = (1 + k_cheap) / (int(retained_stored.sum()) + 1)
                res["valid"] = True
                res["rejected"] = Fraction(1 + k_cheap, int(retained_stored.sum()) + 1) <= ALPHA
    # (d) full regeneration of every attempt
    if job["full"] and result["attempt_status"] is not None:
        res["basis"] = "every attempt regenerated"
        res.update(K=result["K"], retained=result["retained"], near_ties=result["near_ties"])
        if attempts is None or len(attempts["status"]) != job["B"]:
            issues.append("stored attempts %s, recomputed %d" % (None if attempts is None else len(attempts["status"]),
                                                                 job["B"]))
        else:
            bad = [b for b in range(job["B"]) if attempts["status"][b] != result["attempt_status"][b]]
            if bad:
                issues.append("attempt statuses differ at attempts %s (stored %s, recomputed %s)" % (
                    bad[:10], [attempts["status"][b] for b in bad[:3]], [result["attempt_status"][b] for b in bad[:3]]))
            bad = [b for b in range(job["B"]) if tuple(attempts["eligible"][b]) != tuple(result["eligible"][b])]
            if bad:
                issues.append("eligible onsets of attempts differ at attempts %s" % bad[:10])
            diff, agree = max_abs_difference(attempts["statistic"], result["statistics"])
            res["max_diff"]["statistics"] = diff
            if not agree:
                gap = np.abs(attempts["statistic"] - result["statistics"])
                gap[np.isnan(attempts["statistic"]) != np.isnan(result["statistics"])] = np.inf
                worst = int(np.argmax(np.nan_to_num(gap, nan=-1.0)))
                issues.append("surrogate statistics S_b differ from the recomputation (largest at attempt %d: stored "
                              "%r, recomputed %r)" % (worst, float(attempts["statistic"][worst]),
                                                      float(result["statistics"][worst])))
            diff, agree = _compare_changes(attempts["changes"], result["changes"])
            res["max_diff"]["changes"] = diff
            if not agree:
                issues.append("per-episode surrogate Delta_b differ from the recomputation")
        for field, mine_value in (("K", result["K"]), ("retained", result["retained"]),
                                  ("no_episode", result["no_episode"]), ("failed", result["failed"]),
                                  ("attempted", result["attempted"])):
            if stored[field] is not None and stored[field] != mine_value:
                issues.append("%s %r, recomputed %r%s" % (field, stored[field], mine_value, (
                    " (recomputed near ties at attempts %s)" % [t["attempt"] for t in result["near_ties"]])
                    if field == "K" and result["near_ties"] else ""))
        if result["status"] == "ok":
            res["p"], res["valid"] = result["p"], True
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
    elif job["full"] and obs["status"] == "ok" and result["null"] is not None:
        pass
    if job["full"]:
        if result["status"] != stored["status"]:
            issues.append("status %r, recomputed %r" % (stored["status"], result["status"]))
        if result["status"] in ("observed_not_estimable", "observed_statistic_failed", "null_model_failed"):
            res["valid"] = False
            if stored["p"] is not None:
                issues.append("p %r stored, but the recomputed comparison is %s" % (stored["p"], result["status"]))
    elif result["status"] in ("observed_not_estimable", "observed_statistic_failed", "null_model_failed") \
            and stored["status"] == "ok":
        issues.append("status 'ok', but the recomputed comparison is %s" % result["status"])
    if res["near_ties"]:
        notes.append("near ties (|S_b - S| <= %g) at attempts %s" % (NEAR_TIE, [t["attempt"] for t in res["near_ties"]]))
    return res


# ----------------------------------------------------------------------------- the files: reading and structure

H1_SHA256 = "be447b725317c3b857eb1888dbcedd127d057cd5e0e586a0b2de87e24b182ba4"     # prereg/H1.md as registered


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
    """The manifest fields that every part file of one run (size and power alike) must share exactly."""
    identity = manifest.get("identity") or {}
    imported = manifest.get("imported") or {}
    return dict(schema=manifest.get("schema"), extension=manifest.get("extension"), mode=manifest.get("mode"),
                master_seed=manifest.get("master_seed"), n_series=manifest.get("n_series"), B=manifest.get("B"),
                settings=manifest.get("settings"), streams=manifest.get("streams"),
                code_sha256=manifest.get("code_sha256"), e1_code_sha256=manifest.get("e1_code_sha256"),
                identity_option=manifest.get("identity_option"), commit=identity.get("commit"),
                dirty=identity.get("dirty"), ext_commit=imported.get("ext_commit"), python=identity.get("python"),
                packages=identity.get("packages"), lock=(manifest.get("lock") or {}).get("satisfied"),
                gate=manifest.get("gate"), prerequisite=manifest.get("prerequisite"))


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
        self.manifest_problems = 0
        self.expected_n = None if args.development else N_SERIES
        self.expected_B = None if args.development else B_ATTEMPTS


def _is_hex(value, length):
    return isinstance(value, str) and len(value) == length and all(ch in "0123456789abcdef" for ch in value)


def check_manifest(ctx, name, manifest):
    """The manifest of one part file: a registered verification accepts only the registered design, identity and
    gate; a development verification accepts only development seeds and stream ids."""
    rep = ctx.report
    where = name + " manifest"
    before = len(rep.problems)
    for field in ("schema", "extension", "check", "mode", "master_seed", "n_series", "B", "kappas", "settings",
                  "streams", "code_sha256", "e1_code_sha256", "identity_option", "identity", "imported", "lock",
                  "gate", "prerequisite"):
        if field not in manifest:
            rep.missing("manifest." + field)
    if manifest.get("schema") != 2:
        rep.problem(where, "schema %r, expected 2" % manifest.get("schema"))
    if manifest.get("extension") != "e2":
        rep.problem(where, "extension %r, expected 'e2'" % manifest.get("extension"))
    check = manifest.get("check")
    if check not in ("size", "power"):
        rep.problem(where, "check %r is neither size nor power" % check)
    kappas = manifest.get("kappas")
    if check == "power" and kappas != list(KAPPAS):
        rep.problem(where, "kappas %r, the design needs %r" % (kappas, list(KAPPAS)))
    if check == "size" and kappas is not None:
        rep.problem(where, "kappas %r in a size file" % (kappas,))
    settings = manifest.get("settings")
    onsets = settings.get("power_onsets") if isinstance(settings, dict) else None
    if not (isinstance(onsets, list) and onsets and all(type(o) is int for o in onsets)
            and all(b - a >= 10 for a, b in zip(onsets, onsets[1:])) and onsets[0] - SIGNAL_LENGTH >= 2
            and onsets[-1] < N_OBS):
        rep.problem(where, "settings.power_onsets %r is not an increasing list of onsets at least 10 apart" % (onsets,))
    streams = manifest.get("streams")
    code = manifest.get("code_sha256")
    if not _is_hex(code, 64):
        rep.problem(where, "code_sha256 %r is not a SHA-256" % code)
    if ctx.development:
        if manifest.get("mode") != "development" or manifest.get("master_seed") == REGISTERED_SEED:
            rep.problem(where, "a development verification needs a development manifest (not master seed 1927)")
        if isinstance(streams, dict):
            bad = {k: s for k, s in streams.items() if not (type(s) is int and s >= DEVELOPMENT_STREAM_FLOOR
                                                            and s not in RESERVED_STREAMS)}
            if bad:
                rep.problem(where, "development run uses registered or low stream ids: %r" % bad)
        else:
            rep.problem(where, "no stream plan")
        for key in ("n_series", "B"):
            if not (type(manifest.get(key)) is int and manifest.get(key) > 0):
                rep.problem(where, "%s is %r" % (key, manifest.get(key)))
    else:
        expected = dict(mode="registered", master_seed=REGISTERED_SEED, n_series=N_SERIES, B=B_ATTEMPTS)
        for key, value in expected.items():
            if manifest.get(key) != value:
                rep.problem(where, "%s is %r, the registered design needs %r" % (key, manifest.get(key), value))
        if settings != dict(power_onsets=list(POWER_ONSETS), power_onset_source="registered_onsets_record",
                            retain_window_fits=True):
            rep.problem(where, "settings %r, the registered design needs onsets %s from the onsets record and "
                               "window-fit retention" % (settings, list(POWER_ONSETS)))
        if isinstance(streams, dict):
            for key, value in REGISTERED_STREAMS.items():
                if streams.get(key) != value:
                    rep.problem(where, "stream %s = %r, Annex A gives %d" % (key, streams.get(key), value))
        else:
            rep.problem(where, "no stream plan")
        identity = manifest.get("identity") or {}
        if identity.get("python") != "3.12.14":
            rep.problem(where, "interpreter %r; registered results need Python 3.12.14 under the lock"
                        % identity.get("python"))
        if identity.get("dirty") is not False or (manifest.get("imported") or {}).get("ext_dirty") is not False:
            rep.problem(where, "the research tree was not clean (dirty %r, imported sources dirty %r)" % (
                identity.get("dirty"), (manifest.get("imported") or {}).get("ext_dirty")))
        if not _is_hex(identity.get("commit"), 40):
            rep.problem(where, "no 40-digit commit in the identity: %r" % identity.get("commit"))
        if (manifest.get("lock") or {}).get("satisfied") is not True:
            rep.problem(where, "the lock is not recorded as satisfied")
        if manifest.get("e1_code_sha256") != E1_FROZEN_CODE_SHA256:
            rep.problem(where, "e1_code_sha256 %r is not E1's frozen identity %s" % (
                manifest.get("e1_code_sha256"), E1_FROZEN_CODE_SHA256))
        if manifest.get("identity_option") != IDENTITY_OPTION:
            rep.problem(where, "identity option %r, expected %r" % (manifest.get("identity_option"),
                                                                      IDENTITY_OPTION))
        gate = manifest.get("gate")
        if not isinstance(gate, dict):
            rep.problem(where, "no gate record")
        else:
            for key, value in E2_GATE.items():
                if gate.get(key) != value:
                    rep.problem(where, "gate %s is %r, expected %r" % (key, gate.get(key), value))
            for key in ("tag_object", "registration_file_sha256"):
                if not gate.get(key):
                    rep.missing("manifest.gate." + key)
        prerequisite = manifest.get("prerequisite")
        if not (isinstance(prerequisite, dict) and prerequisite.get("passed") is True
                and _is_hex(prerequisite.get("sha256"), 64)):
            rep.problem(where, "no passed prerequisite record is named in the manifest")
    ctx.manifest_problems += len(rep.problems) - before


def stream_plan(ctx, manifest, check):
    """(generation stream, surrogate stream): Annex A in a registered verification; the manifest's development
    plan otherwise."""
    if not ctx.development:
        return REGISTERED_STREAMS[check + "_generation"], REGISTERED_STREAMS[check + "_null"]
    streams = manifest.get("streams") or {}
    return streams.get(check + "_generation"), streams.get(check + "_null")


def _matrix(values, rows, cols):
    """`values` as a (rows, cols) float array, or None unless it is exactly that shape of numbers."""
    if not isinstance(values, list) or len(values) != rows:
        return None
    out = np.empty((rows, cols))
    for i, row in enumerate(values):
        if not isinstance(row, list) or len(row) != cols:
            return None
        for j, v in enumerate(row):
            if not is_number(v):
                return None
            out[i, j] = v
    return out


def parse_attempts(attempts, expected, mode, observed_eligible, issues):
    """The stored surrogate attempts as lists and an array (NaN where no statistic is stored); structural
    findings are appended to `issues`. None when `attempts` is not a list."""
    if not isinstance(attempts, list):
        issues.append("attempts is not a list")
        return None
    if type(expected) is int and len(attempts) != expected:
        issues.append("%d attempts stored, the design needs %d" % (len(attempts), expected))
    status, eligible, changes = [], [], []
    statistic = np.full(len(attempts), np.nan)
    bad_number, bad_status, bad_shape, bad_mean, bad_fixed = [], [], [], [], []
    for i, a in enumerate(attempts):
        if not isinstance(a, dict):
            bad_shape.append(i)
            status.append("malformed")
            eligible.append(())
            changes.append(())
            continue
        if a.get("number") != i:
            bad_number.append(i)
        kind = a.get("status")
        if kind not in ("retained", "no_eligible_episode", "failed"):
            bad_status.append(i)
            status.append(str(kind))
            eligible.append(())
            changes.append(())
            continue
        status.append(kind)
        value, onsets, parts = a.get("statistic"), a.get("eligible_onsets"), a.get("changes")
        if kind == "retained":
            good = (finite(value) and isinstance(onsets, list) and isinstance(parts, list) and len(parts) > 0
                    and len(onsets) == len(parts) and all(type(o) is int for o in onsets)
                    and all(finite(v) for v in parts))
            if not good:
                bad_shape.append(i)
                eligible.append(())
                changes.append(())
                continue
            statistic[i] = value
            eligible.append(tuple(onsets))
            changes.append(tuple(float(v) for v in parts))
            if not close(math.fsum(parts) / len(parts), value):
                bad_mean.append(i)
            if mode == "fixed" and list(onsets) != list(observed_eligible or []):
                bad_fixed.append(i)
        else:
            if value is not None or onsets or parts:
                bad_shape.append(i)
            eligible.append(())
            changes.append(())
            if kind == "no_eligible_episode" and mode == "fixed":
                bad_fixed.append(i)
    if bad_number:
        issues.append("attempt numbers are not 0..%d in order (first wrong: %s)" % (len(attempts) - 1, bad_number[:5]))
    if bad_status:
        issues.append("attempts with an unknown status: %s" % bad_status[:10])
    if bad_shape:
        issues.append("attempts whose statistic, onsets or changes are malformed: %s" % bad_shape[:10])
    if bad_mean:
        issues.append("attempt statistics that are not the mean of their changes: %s" % bad_mean[:10])
    if bad_fixed:
        issues.append("fixed-date attempts whose onsets are not the observed eligible onsets: %s" % bad_fixed[:10])
    return dict(status=status, statistic=statistic, eligible=eligible, changes=changes)


def parse_null(null_model, issues):
    """The stored fitted null in the field names check_numeric compares (None when there is none)."""
    if null_model is None:
        return None
    if not isinstance(null_model, dict):
        issues.append("null_model is not an object")
        return None
    coefficients, initial = null_model.get("coefficients"), null_model.get("initial")
    pair = coefficients if isinstance(coefficients, list) and len(coefficients) == 2 else [None, None]
    start = initial if isinstance(initial, list) and len(initial) == 2 else [None, None]
    return dict(intercept=null_model.get("intercept"), a1=pair[0], a2=pair[1], initial0=start[0], initial1=start[1],
                residuals=null_model.get("residuals"), residual_mean_removed=null_model.get("residual_mean_removed"),
                modulus=null_model.get("modulus"))


def check_replicate(ctx, name, manifest, record, line_number):
    """Structural checks of one record and the compact job for its numerical checks."""
    rep = ctx.report
    check = manifest.get("check")
    cell, replicate = record.get("cell_index"), record.get("replicate")
    where = "%s line %d (%s cell %r, replicate %r)" % (name, line_number, check, cell, replicate)
    issues = []
    B = ctx.expected_B if ctx.expected_B is not None else manifest.get("B")
    mode = "primary" if check == "size" else "fixed"
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
    if "registered" not in record:
        rep.missing("replicate.registered")
    elif record.get("registered") is not (manifest.get("mode") == "registered"):
        issues.append("registered flag %r in a %r file" % (record.get("registered"), manifest.get("mode")))
    prerequisite = manifest.get("prerequisite")
    if isinstance(prerequisite, dict) and record.get("prerequisite_sha256") != prerequisite.get("sha256"):
        issues.append("prerequisite_sha256 %r differs from the prerequisite the manifest names" %
                      record.get("prerequisite_sha256"))
    kappa = None
    if check == "power" and type(cell) is int:
        if 0 <= cell < len(KAPPAS):
            kappa = KAPPAS[cell]
            if record.get("kappa") != kappa:
                issues.append("kappa %r does not belong to cell %d" % (record.get("kappa"), cell))
        else:
            issues.append("cell %d is not a power cell" % cell)
    elif check == "size" and record.get("kappa") not in (None, 1.0):
        issues.append("kappa %r in the size cell" % record.get("kappa"))
    # the stored input and its hash
    x = None
    if record.get("input") is None:
        rep.missing("replicate.input")
        issues.append("no stored input (status %r)" % record.get("status"))
    else:
        matrix = _matrix(record["input"], N_OBS, K)
        if matrix is None or not np.isfinite(matrix).all():
            issues.append("input is not %d x %d finite numbers" % (N_OBS, K))
        else:
            x = matrix
            if input_sha256(x) != record.get("input_sha256"):
                issues.append("stored input does not match input_sha256")
    # observed and comparison
    status = record.get("status")
    comparison = record.get("comparison")
    if comparison is not None and not isinstance(comparison, dict):
        issues.append("comparison is not an object")
        comparison = None
    has_comparison = comparison is not None
    comparison = comparison or {}
    if status in ("ok", "invalid_surrogate_failure", "no_retained_surrogates", "observed_not_estimable") \
            and not has_comparison:
        rep.missing("replicate.comparison")
        issues.append("status %r without a comparison" % status)
    observed = record.get("observed") if isinstance(record.get("observed"), dict) else comparison.get("observed")
    observed = observed if isinstance(observed, dict) else None
    if isinstance(record.get("observed"), dict) and isinstance(comparison.get("observed"), dict) \
            and record["observed"] != comparison["observed"]:
        issues.append("record observed differs from comparison observed")
    if has_comparison and status != comparison.get("status"):
        issues.append("record status %r differs from comparison status %r" % (status, comparison.get("status")))
    if has_comparison and record.get("p_value") != comparison.get("p_value"):
        issues.append("record p_value differs from the comparison's")
    if status == "ok":
        if observed is None or not finite(observed.get("mean_change")):
            issues.append("status ok without a finite observed statistic")
        elif record.get("S") != observed.get("mean_change"):
            issues.append("record S differs from the observed mean_change")
        elif not (isinstance(observed.get("changes"), list) and observed["changes"]
                  and len(observed["changes"]) == len(observed.get("eligible_onsets") or [])
                  and all(finite(v) for v in observed["changes"])
                  and close(math.fsum(observed["changes"]) / len(observed["changes"]), observed["mean_change"])):
            issues.append("observed mean_change is not the mean of its changes, one per eligible onset")
    if status == "observed_not_estimable":
        if observed is None or observed.get("mean_change") is not None or record.get("S") is not None \
                or record.get("p_value") is not None:
            issues.append("observed_not_estimable with a statistic or a p stored")
    if mode == "fixed" and observed is not None and status in ("ok", "observed_not_estimable"):
        planned = manifest.get("settings", {}).get("power_onsets") if isinstance(manifest.get("settings"), dict) \
            else None
        both = list(observed.get("eligible_onsets") or []) + list(observed.get("ineligible_onsets") or [])
        if planned is not None and sorted(both) != list(planned):
            issues.append("observed onsets %s, the power design plants %s" % (sorted(both), planned))
    # the stored attempts, their counts, K and p
    attempts = comparison.get("attempts")
    parsed = None
    if has_comparison and status != "observed_not_estimable" or (status == "observed_not_estimable" and attempts):
        if attempts is None:
            rep.missing("replicate.comparison.attempts")
            issues.append("no stored attempts")
        else:
            parsed = parse_attempts(attempts, B, mode, (observed or {}).get("eligible_onsets"), issues)
    elif status == "observed_not_estimable" and attempts not in (None, []):
        issues.append("attempts stored for an observed_not_estimable record")
    if parsed is not None:
        kinds = parsed["status"]
        counts = dict(requested=B, attempted=len(kinds), retained=kinds.count("retained"),
                      no_episode=kinds.count("no_eligible_episode"), failed=kinds.count("failed"))
        for key, value in counts.items():
            if key not in comparison:
                rep.missing("replicate.comparison." + key)
            elif comparison.get(key) != value:
                issues.append("%s %r, the stored attempts give %r" % (key, comparison.get(key), value))
        retained_mask = np.array([k == "retained" for k in kinds])
        s_stored = observed.get("mean_change") if observed else None
        if finite(s_stored) and comparison.get("exceedances") is not None:
            k_stored = int(np.sum(parsed["statistic"][retained_mask] >= s_stored))
            if k_stored != comparison.get("exceedances"):
                issues.append("exceedances %r, but %d stored statistics are >= the stored S" % (
                    comparison.get("exceedances"), k_stored))
            retained = int(retained_mask.sum())
            if status == "ok" and retained and counts["failed"] == 0:
                exact = Fraction(1 + comparison["exceedances"], retained + 1)
                if not close(comparison.get("p_value"), float(exact)):
                    issues.append("p %r is not (1 + K)/(B' + 1) = %d/%d of the stored counts" % (
                        comparison.get("p_value"), exact.numerator, exact.denominator))
        if counts["failed"] and comparison.get("p_value") is not None:
            issues.append("a surrogate failure did not invalidate p")
    if has_comparison:
        for key in ("requested", "attempted", "retained", "no_episode", "failed", "exceedances"):
            if "surrogate_" + key in record and record["surrogate_" + key] != comparison.get(key):
                issues.append("surrogate_%s differs from the comparison" % key)
        if comparison.get("exceedances") is not None and comparison.get("retained") \
                and not close(record.get("surrogate_exceedance_rate"),
                              comparison["exceedances"] / comparison["retained"]):
            issues.append("surrogate_exceedance_rate is not K/B'")
        for key, expected_value in (("window", WINDOW), ("lookback", LOOKBACK), ("merge", MERGE),
                                    ("onset_mode", "endogenous" if mode == "primary" else "external_fixed"),
                                    ("innovation_mode", "residual")):
            if comparison.get(key) != expected_value:
                issues.append("comparison %s is %r, expected %r" % (key, comparison.get(key), expected_value))
    if status not in STATUSES:
        issues.append("unknown status %r" % status)
    for issue in issues:
        rep.problem(where, issue)
    # the job for the numerical checks
    gen_stream, sur_stream = stream_plan(ctx, manifest, check)
    seed = manifest.get("master_seed")
    job = None
    if type(cell) is int and type(replicate) is int and type(seed) is int and type(B) is int \
            and type(sur_stream) is int:
        settings = manifest.get("settings") if isinstance(manifest.get("settings"), dict) else {}
        planted = tuple(settings.get("power_onsets") or ())
        generation = None
        if type(gen_stream) is int and (check == "size" or kappa is not None):
            generation = (seed, gen_stream, cell, replicate, 1.0 if check == "size" else kappa,
                          () if check == "size" else planted)
        stored_status = status if isinstance(status, str) else None
        job = dict(key=(check, cell, replicate), where=where, x=x, generation=generation,
                   generation_rng_before=record.get("generation_rng_before"),
                   generation_rng_after=record.get("generation_rng_after"),
                   analysis_rng_before=record.get("analysis_rng_before"),
                   analysis_rng_after=record.get("analysis_rng_after"),
                   comparison_rng=((comparison.get("rng_before"), comparison.get("rng_after"))
                                   if has_comparison and comparison.get("rng_before") is not None else None),
                   mode=mode, fixed=planted if mode == "fixed" else None, seed=seed, stream=sur_stream, cell=cell,
                   replicate=replicate, B=B, full=False,
                   stored=dict(status=stored_status, S=record.get("S") if finite(record.get("S")) else None,
                               observed=observed, window_fits=record.get("window_fits"),
                               null=parse_null(comparison.get("null_model"), []), attempts=parsed,
                               K=comparison.get("exceedances"), retained=comparison.get("retained"),
                               no_episode=comparison.get("no_episode"), failed=comparison.get("failed"),
                               attempted=comparison.get("attempted"), p=comparison.get("p_value"),
                               q=record.get("surrogate_exceedance_rate"),
                               wilson=record.get("surrogate_exceedance_wilson"),
                               grid=comparison.get("p_grid_spacing")))
        if record.get("window_fits") is None:
            rep.missing("replicate.window_fits")
        if has_comparison and status in ("ok", "invalid_surrogate_failure", "no_retained_surrogates") \
                and comparison.get("null_model") is None:
            rep.missing("replicate.comparison.null_model")
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
    number = 0
    with open(path, "rb") as handle:
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


def select_sample(jobs, count, seed):
    """Indices of `count` jobs drawn without replacement, in coordinate order, from SeedSequence(seed)."""
    order = sorted(range(len(jobs)), key=lambda i: str(jobs[i]["key"]))
    count = min(count, len(jobs))
    gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))
    chosen = gen.choice(len(order), size=count, replace=False) if count else []
    return sorted(order[i] for i in chosen)


def compare_runner(ctx, path, check, cells, power, registered_design, verdict):
    """Every figure of a runner summary (E2 layout: summary.cell or summary.cells, adjacent comparisons, decrease
    flags, D80, registered_design, passed; inputs with each file's SHA-256 and record count) against the
    recomputation and the verified files; fields absent from the file are listed, not guessed."""
    rep = ctx.report
    name = Path(path).name
    out = dict(file=str(path), compared=0, differences=[], absent=[])
    try:
        with open(path, "rb") as handle:
            data = json.loads(handle.read())
    except ValueError as error:
        rep.problem(name, "not valid JSON: %s" % str(error)[:100])
        return out
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
            rep.problem(name, "%s: runner %r, recomputed %r" % (label, theirs, ours))

    # the files the summary was made from
    listed = data.get("inputs")
    mine = {Path(row["file"]).name: row for row in ctx.files if row.get("check") == check}
    if isinstance(listed, list):
        seen = set()
        for item in listed:
            file_name = Path(str(item.get("path"))).name
            seen.add(file_name)
            row = mine.get(file_name)
            if row is None:
                rep.problem(name, "the summary lists %s, which is not among the verified %s files" % (
                    file_name, check))
                continue
            same("inputs[%s].sha256" % file_name, item.get("sha256"), row["sha256"], True)
            same("inputs[%s].records" % file_name, item.get("records"), row["replicates"], True)
        for file_name in sorted(set(mine) - seen):
            rep.problem(name, "verified file %s is not listed among the summary's inputs" % file_name)
    else:
        out["absent"].append("inputs")
    # the figures
    theirs_cells = [summary.get("cell") or {}] if check == "size" else list(summary.get("cells") or [])
    if len(theirs_cells) != len(cells):
        rep.problem(name, "%d cells, recomputed %d" % (len(theirs_cells), len(cells)))
    for index, (theirs, ours) in enumerate(zip(theirs_cells, cells)):
        label = "cell" if check == "size" else "cells[%d]" % index
        for field in ("requested", "attempted", "valid", "rejected", "unfinished", "failures"):
            same("%s.%s" % (label, field), theirs.get(field), ours[field], True)
        for field in ("accounting_bounds", "valid_only_rate", "rate", "rate_se", "rate_wilson", "mean_S",
                      "mean_S_se"):
            same("%s.%s" % (label, field), theirs.get(field), ours[field], False)
        if check == "power":
            same("%s.kappa" % label, theirs.get("kappa"), ours["kappa"], True)
    if check == "size":
        same("bounds", summary.get("bounds"), [float(BAND[0]), float(BAND[1])], False)
    same("registered_design", summary.get("registered_design"), registered_design, True)
    same("passed", summary.get("passed"), verdict, True)
    if check == "power" and power is not None:
        adjacent = summary.get("adjacent_comparisons") or []
        for index, (theirs, ours) in enumerate(zip(adjacent, power["adjacent"])):
            for field in ("difference", "standard_error"):
                same("adjacent[%d].%s" % (index, field), theirs.get(field), ours[field], False)
            same("adjacent[%d].decrease_flag" % index, theirs.get("decrease_flag"), ours["decrease_flag"], True)
        if len(adjacent) != len(power["adjacent"]):
            rep.problem(name, "%d adjacent comparisons, recomputed %d" % (len(adjacent), len(power["adjacent"])))
        same("decrease_flags", summary.get("decrease_flags"), power["decrease_flags"], True)
        if power["D80"] is not None or summary.get("D80") is not None:
            same("D80", summary.get("D80"), power["D80"], False)
            same("kappa80", summary.get("kappa80"), power["kappa80"], False)
    return out


def check_prereg(report):
    """If the research clone's prereg files are beside this script: their SHA-256 and the quoted clauses."""
    base = Path(__file__).resolve().parent.parent / "prereg"
    path, h1 = base / "E2.md", base / "H1.md"
    if not path.is_file():
        return dict(present=False)
    content = path.read_bytes()
    out = dict(present=True, sha256=hashlib.sha256(content).hexdigest())
    out["registered"] = out["sha256"] == E2_SHA256
    text = content.decode("utf-8")
    h1_content = h1.read_bytes() if h1.is_file() else b""
    h1_text = h1_content.decode("utf-8")
    out["h1_sha256"] = hashlib.sha256(h1_content).hexdigest() if h1_content else None
    out["h1_registered"] = out["h1_sha256"] == H1_SHA256
    out["quotes_verbatim"] = bool(SIZE_CLAUSE[2] in text and POWER_CLAUSE[2] in text
                                  and AT16_CLAUSE[2] in h1_text and VALID_CELL_CLAUSE[2] in h1_text)
    if not out["registered"]:
        report.problem("prereg/E2.md", "SHA-256 %s differs from the registered %s" % (out["sha256"], E2_SHA256))
    if h1_content and not out["h1_registered"]:
        report.problem("prereg/H1.md", "SHA-256 %s differs from the registered %s" % (out["h1_sha256"], H1_SHA256))
    if not out["quotes_verbatim"]:
        report.problem("prereg", "a clause quoted here is not found verbatim")
    return out


# ----------------------------------------------------------------------------- the prerequisite record

def ar2_closed_modulus(phi1, phi2):
    """The largest modulus of the roots of z^2 - phi1 z - phi2 (the eigenvalues of the AR(2) companion matrix) in
    closed form: (|phi1| + sqrt(d))/2 for d = phi1^2 + 4 phi2 >= 0, sqrt(-phi2) for d < 0."""
    phi1, phi2 = np.asarray(phi1, dtype=float), np.asarray(phi2, dtype=float)
    disc = phi1 * phi1 + 4 * phi2
    real = (np.abs(phi1) + np.sqrt(np.where(disc >= 0, disc, 0.0))) / 2
    pair = np.sqrt(np.where(disc < 0, -phi2, 0.0))
    return np.where(disc >= 0, real, pair)


def ar2_rolling_closed(x, window):
    """H1's AR(2) with intercept on every window of one series by the closed-form normal equations of the centred
    lag columns (no scaling, no lstsq): the comparator of the reduction test. NaN where a window is singular."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x) - window + 1, np.nan)
    for w in range(len(out)):
        seg = x[w:w + window]
        y, l1, l2 = seg[2:], seg[1:-1], seg[:-2]
        c1, c2, cy = l1 - l1.mean(), l2 - l2.mean(), y - y.mean()
        s11, s22, s12 = float(c1 @ c1), float(c2 @ c2), float(c1 @ c2)
        s1y, s2y = float(c1 @ cy), float(c2 @ cy)
        det = s11 * s22 - s12 * s12
        if not det > 0:
            continue
        out[w] = float(ar2_closed_modulus((s1y * s22 - s2y * s12) / det, (s2y * s11 - s1y * s12) / det))
    return out


def at12_recompute(seed, stream, draws):
    """AT-12 through the companion spectral radius of this file: the diagonal VAR(1) against max(|a|, |b|) and the
    k = 1 companion against the closed-form AR(2) root modulus, with AT-12's own draws (SeedSequence([seed, stream,
    0]) and [seed, stream, 1]) and its skip rule |phi1^2 + 4 phi2| < 1e-8."""
    def pcg(word):
        return np.random.Generator(np.random.PCG64(np.random.SeedSequence([int(seed), int(stream), word])))
    ab = pcg(0).uniform(-2, 2, size=(draws, 2))
    a1 = np.zeros((draws, 2, 2))
    a1[:, 0, 0], a1[:, 1, 1] = ab[:, 0], ab[:, 1]
    diagonal_error = float(np.max(np.abs(radius_of(a1, np.zeros_like(a1)) - np.max(np.abs(ab), axis=1))))
    gen = pcg(1)
    phi1 = gen.uniform(-3, 3, draws)
    phi2 = gen.uniform(-2, 2, draws)
    keep = ~(np.abs(phi1 * phi1 + 4 * phi2) < 1e-8)
    modulus = radius_of(phi1[keep].reshape(-1, 1, 1), phi2[keep].reshape(-1, 1, 1))
    ar_error = float(np.max(np.abs(modulus - ar2_closed_modulus(phi1[keep], phi2[keep]))))
    return dict(draws=draws, skipped=int((~keep).sum()), diagonal_error=diagonal_error, ar2_error=ar_error,
                diagonal_passed=diagonal_error <= 1e-12, ar2_passed=ar_error <= 1e-9)


def reduction_recompute(values, windows=REDUCTION_WINDOWS):
    """The VAR code of this file with one variable against the closed-form AR(2) of H1 on every window of one
    series (Annex B): per window the number of fitted windows, whether the warm-up positions agree and the
    largest |difference|."""
    x = np.asarray(values, dtype=float)
    rows = []
    for window in windows:
        var_path = rolling_modulus(x.reshape(1, -1, 1), window)[0][0]
        h1_path = ar2_rolling_closed(x, window)
        fitted = ~np.isnan(h1_path)
        same_shape = bool(np.array_equal(np.isnan(var_path), np.isnan(h1_path)))
        both = fitted & ~np.isnan(var_path)
        difference = float(np.max(np.abs(var_path[both] - h1_path[both]))) if both.any() else None
        rows.append(dict(window=window, fitted=int(fitted.sum()), max_abs_difference=difference,
                         warmup_same=same_shape,
                         passed=bool(same_shape and difference is not None and difference <= REDUCTION_TOLERANCE)))
    return rows


def check_prerequisite(ctx, path, reference):
    """The prerequisite record the X.3 parts name: its structure, its identity against the parts', AT-12 and the
    reduction test recomputed here, and its overall verdict."""
    rep = ctx.report
    name = Path(path).name
    out = dict(file=str(path), sha256=None, structure=False, recomputed=None, passed_recorded=None,
               passed_recomputed=None, fixture_form=None)
    raw = Path(path).read_bytes()
    out["sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        lines = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    except ValueError as error:
        rep.problem(name, "not valid JSON Lines: %s" % str(error)[:100])
        return out
    if not raw.endswith(b"\n"):
        rep.problem(name, "last line has no trailing newline")
    if len(lines) != 2 or lines[0].get("record_type") != "manifest" or lines[1].get("record_type") != "prerequisite":
        rep.problem(name, "must hold exactly a manifest line and one prerequisite record (found %s)" % (
            [line.get("record_type") for line in lines],))
        return out
    manifest, record = lines
    out["structure"] = True
    registered = not ctx.development
    where = name
    if manifest.get("extension") != "e2" or manifest.get("check") != "prerequisite":
        rep.problem(where, "manifest extension %r, check %r; expected e2 and prerequisite" % (
            manifest.get("extension"), manifest.get("check")))
    if manifest.get("mode") != ("registered" if registered else "development") or \
            record.get("mode") != manifest.get("mode") or record.get("master_seed") != manifest.get("master_seed") \
            or record.get("registered") is not registered or record.get("code_sha256") != manifest.get("code_sha256"):
        rep.problem(where, "the record's mode, master seed, registered flag or code hash differs from its manifest")
    if reference is not None:
        mine = fingerprint(manifest)
        for key in ("schema", "extension", "mode", "master_seed", "n_series", "B", "streams", "code_sha256",
                    "e1_code_sha256", "identity_option", "commit", "dirty", "ext_commit", "python", "packages",
                    "lock", "gate"):
            if mine[key] != reference[key]:
                rep.problem(where, "manifest %s differs from the X.3 parts' (%r against %r)" % (
                    key, mine[key], reference[key]))
        named = (reference.get("prerequisite") or {}).get("sha256")
        if named is not None and named != out["sha256"]:
            rep.problem(where, "the SHA-256 of this file, %s, is not the one the parts' manifests name, %s" % (
                out["sha256"], named))
        if named is None and registered:
            rep.problem(where, "the parts' manifests name no prerequisite file")
    seed, streams = manifest.get("master_seed"), manifest.get("streams") or {}
    at12 = record.get("at12") or {}
    diagonal, ar2 = at12.get("diagonal") or {}, at12.get("ar2") or {}
    draws = AT12_DRAWS["registered"] if registered else diagonal.get("draws")
    at12_stream = streams.get("at12")
    problems = []
    if not (type(draws) is int and draws > 0 and type(seed) is int and type(at12_stream) is int):
        rep.problem(where, "no usable AT-12 coordinates (draws %r, seed %r, stream %r)" % (draws, seed, at12_stream))
        return out
    if diagonal.get("draws") != draws or ar2.get("draws") != draws:
        problems.append("AT-12 draws %r and %r, expected %d" % (diagonal.get("draws"), ar2.get("draws"), draws))
    if at12.get("seed") != [seed, at12_stream]:
        problems.append("AT-12 seed %r, expected %r" % (at12.get("seed"), [seed, at12_stream]))
    mine12 = at12_recompute(seed, at12_stream, draws)
    if ar2.get("skipped") != mine12["skipped"]:
        problems.append("AT-12 skipped draws %r, recomputed %d" % (ar2.get("skipped"), mine12["skipped"]))
    for label, recorded, error, passed, limit in (
            ("diagonal", diagonal, mine12["diagonal_error"], mine12["diagonal_passed"], 1e-12),
            ("AR(2)", ar2, mine12["ar2_error"], mine12["ar2_passed"], 1e-9)):
        if recorded.get("passed") is not True:
            problems.append("AT-12 %s part recorded as not passed" % label)
        if not passed:
            problems.append("AT-12 %s part: recomputed max error %.3g exceeds %.0e" % (label, error, limit))
        if not finite(recorded.get("max_abs_error")) or recorded["max_abs_error"] > limit:
            problems.append("AT-12 %s part: recorded max error %r exceeds %.0e" % (label, recorded.get("max_abs_error"),
                                                                                  limit))
    # the reduction test on the fixture series (stream size_generation, cell 1, replicate 0)
    reduction = record.get("reduction") or {}
    fixture, mine_rows = None, None
    for form in ("closed", "text"):
        candidate = h1_series(seed, streams.get("size_generation"), 1, 0, form=form)
        if input_sha256(candidate) == record.get("input_sha256"):
            fixture, out["fixture_form"] = candidate, form
            break
    if reduction.get("input_sha256") != record.get("input_sha256"):
        problems.append("the reduction's input hash differs from the record's")
    if fixture is None:
        problems.append("the fixture series of the reduction test is not reproduced from its generation coordinates "
                        "(stored hash %s)" % record.get("input_sha256"))
    else:
        mine_rows = reduction_recompute(fixture)
        theirs = reduction.get("windows") or []
        if [row.get("window") for row in theirs] != list(REDUCTION_WINDOWS):
            problems.append("reduction windows %r, expected %r" % ([row.get("window") for row in theirs],
                                                                   list(REDUCTION_WINDOWS)))
        for row, mine_row in zip(theirs, mine_rows):
            if row.get("fitted") != mine_row["fitted"]:
                problems.append("reduction W = %s: fitted windows %r, recomputed %d" % (
                    row.get("window"), row.get("fitted"), mine_row["fitted"]))
            if row.get("warmup_same") is not True or row.get("passed") is not True or not mine_row["passed"]:
                problems.append("reduction W = %s: recorded passed %r, warm-up same %r; recomputed passed %r "
                                "(max |difference| %r)" % (row.get("window"), row.get("passed"),
                                                           row.get("warmup_same"), mine_row["passed"],
                                                           mine_row["max_abs_difference"]))
            if not finite(row.get("max_abs_difference")) or row["max_abs_difference"] > REDUCTION_TOLERANCE:
                problems.append("reduction W = %s: recorded max |difference| %r exceeds %.0e" % (
                    row.get("window"), row.get("max_abs_difference"), REDUCTION_TOLERANCE))
    f4 = record.get("f4") or {}
    if f4.get("passed") is not True:
        problems.append("F4 is not recorded as passed")
    recomputed_pass = bool(mine12["diagonal_passed"] and mine12["ar2_passed"] and mine_rows is not None
                           and all(row["passed"] for row in mine_rows) and f4.get("passed") is True)
    out.update(passed_recorded=record.get("passed"), passed_recomputed=recomputed_pass, f4=f4,
               unit_tests=record.get("unit_tests"),
               recomputed=dict(at12=mine12, reduction=mine_rows, recorded_at12=dict(
                   diagonal=diagonal.get("max_abs_error"), ar2=ar2.get("max_abs_error"), skipped=ar2.get("skipped")),
                   recorded_reduction=[row.get("max_abs_difference") for row in (reduction.get("windows") or [])]))
    if record.get("passed") is not recomputed_pass:
        problems.append("the record's verdict %r differs from the recomputed %r" % (record.get("passed"),
                                                                                    recomputed_pass))
    for message in problems:
        rep.problem(where, message)
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
                            "record still has its design, hashes, window fits, observed S, null, draws and p "
                            "checked from its stored statistics")
    parser.add_argument("--sample-seed", type=int, default=20260930,
                        help="seed of the record selection for --sample (recorded in the report)")
    parser.add_argument("--workers", type=int, default=1, help="processes for the recomputation (default 1)")
    parser.add_argument("--development", action="store_true",
                        help="verify a development run: sizes and stream ids from its manifests; seed 1927 and "
                             "registered stream ids are refused")
    parser.add_argument("--partial", action="store_true",
                        help="check the records present without requiring the complete design (interim use)")
    parser.add_argument("--prerequisite", help="the prerequisite record the parts name (x3_prerequisite.jsonl in a "
                                               "given directory is found automatically)")
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
    prerequisite = Path(args.prerequisite) if args.prerequisite else None
    for raw in args.paths:
        path = Path(raw)
        if path.is_dir():
            files += sorted(p for p in path.iterdir() if p.is_file() and p.suffix == ".jsonl"
                            and p.name.startswith("x3_") and "prerequisite" not in p.name)
            summaries += sorted(p for p in path.iterdir() if p.name in ("x3_size_summary.json",
                                                                         "x3_power_summary.json")
                                and p not in summaries)
            candidate = path / "x3_prerequisite.jsonl"
            if prerequisite is None and candidate.is_file():
                prerequisite = candidate
        elif path.is_file():
            files.append(path)
        else:
            raise UsageError("no such file or directory: %s" % path)
    if not files:
        raise UsageError("no X.3 part files found")
    if prerequisite is not None and not prerequisite.is_file():
        raise UsageError("no such prerequisite file: %s" % prerequisite)
    return files, summaries, prerequisite


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
    files, summaries, prerequisite = collect_paths(args)
    rep.say("verify_e2_x3.py %s - independent recomputation of the E2 X.3 outputs" % VERSION)
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
        rep.say("  manifests: %d; fingerprint: mode %s, master seed %s, code %s..., e1 code %s..., identity option "
                "%s, commit %s, Python %s" % (len(ctx.manifests), reference["mode"], reference["master_seed"],
                                               str(reference["code_sha256"])[:12],
                                               str(reference["e1_code_sha256"])[:12], reference["identity_option"],
                                               reference["commit"], reference["python"]))
        rep.say("  E1 code identity recorded in the manifests equals E1's frozen identity (c42cbbf3...): %s" % (
            reference["e1_code_sha256"] == E1_FROZEN_CODE_SHA256))
    if prereg.get("present"):
        rep.say("  prereg/E2.md beside this script: SHA-256 registered %s; prereg/H1.md registered %s; clauses "
                "quoted here verbatim %s" % (prereg["registered"], prereg["h1_registered"],
                                              prereg["quotes_verbatim"]))
    # 2. the prerequisite record
    rep.say("")
    rep.say("[2] PREREQUISITE RECORD (AT-12 AND THE REDUCTION TEST, RECOMPUTED)")
    prereq = None
    if prerequisite is not None:
        t0 = time.time()
        prereq = check_prerequisite(ctx, prerequisite, reference)
        rec = prereq.get("recomputed")
        rep.say("  %s: SHA-256 %s" % (prerequisite.name, prereq["sha256"]))
        if rec:
            a = rec["at12"]
            rep.say("  AT-12 (%d draws): diagonal max error %.3g recomputed, %s recorded (limit 1e-12); AR(2) max "
                    "error %.3g recomputed, %s recorded (limit 1e-9); skipped draws %d recomputed, %s recorded" % (
                        a["draws"], a["diagonal_error"], fmt(rec["recorded_at12"]["diagonal"], 3), a["ar2_error"],
                        fmt(rec["recorded_at12"]["ar2"], 3), a["skipped"], rec["recorded_at12"]["skipped"]))
            if rec["reduction"] is not None:
                rep.say("  reduction test on the fixture series (reproduced from its generation coordinates by the "
                        "'%s' form of H1's generator):" % prereq["fixture_form"])
                for row, recorded in zip(rec["reduction"], rec["recorded_reduction"]):
                    rep.say("    W = %d: %d windows fitted; max |difference| %s recomputed, %s recorded (limit "
                            "1e-10); warm-up positions agree %s" % (row["window"], row["fitted"],
                                                                     fmt(row["max_abs_difference"], 3),
                                                                     fmt(recorded, 3), row["warmup_same"]))
            else:
                rep.say("  reduction test: the fixture series could not be reproduced; not recomputed")
            rep.say("  F4 (taken from the research record, not re-run): %s; unit tests cited: %s" % (
                prereq["f4"].get("passed"), prereq["unit_tests"]))
            rep.say("  verdict: recorded %s, recomputed %s (%.1f s)" % (prereq["passed_recorded"],
                                                                      prereq["passed_recomputed"],
                                                                      time.time() - t0))
    elif not args.development and not args.partial:
        rep.problem("prerequisite", "a registered verification needs the prerequisite record the parts name (give "
                                    "--prerequisite FILE or a directory holding x3_prerequisite.jsonl)")
        rep.say("  no prerequisite record given: PROBLEM")
    else:
        rep.say("  no prerequisite record given: not checked")
    # 3. recomputation
    if args.sample is not None:
        chosen = select_sample(ctx.jobs, args.sample, args.sample_seed)
    else:
        chosen = list(range(len(ctx.jobs)))
    for index in chosen:
        ctx.jobs[index]["full"] = True
    rep.say("")
    rep.say("[3] RECOMPUTATION FROM THE STORED INPUTS (%d records; every attempt regenerated for %d%s; workers %d)"
            % (len(ctx.jobs), len(chosen), "" if args.sample is None else
               " drawn with SeedSequence(%d)" % args.sample_seed, args.workers))
    t0 = time.time()
    results = run_jobs(ctx.jobs, args.workers)
    compute_seconds = time.time() - t0
    near_ties, stored_near_ties, identical, regen_max, fallbacks = [], [], 0, 0.0, 0
    maxima = dict(fits=0.0, components=0.0, S=0.0, statistics=0.0, changes=0.0, nulls=0.0)
    counted = dict(fits=0, nulls=0, generation=0)
    for res in results:
        for issue in res["issues"]:
            rep.problem(res["where"], issue)
        for note in res["notes"]:
            rep.notes.append("%s: %s" % (res["where"], note))
        for key in maxima:
            value = res["max_diff"].get(key)
            if value is not None:
                maxima[key] = max(maxima[key], value)
        counted["fits"] += res["max_diff"].get("fits") is not None and res["status"] != "no_input"
        counted["nulls"] += res["max_diff"].get("nulls") is not None
        if res["max_diff"].get("regeneration") is not None:
            counted["generation"] += 1
            regen_max = max(regen_max, res["max_diff"]["regeneration"])
        identical += bool(res["regeneration_identical"])
        fallbacks += res["fallbacks"]
        near_ties += [dict(t, record=list(res["key"])) for t in res["near_ties"]]
        stored_near_ties += [dict(attempt=a, record=list(res["key"])) for a in res["stored_near_ties"]]
        ctx.entries[res["key"]].update(res)
    full = [r for r in results if r["full"]]
    rep.say("  window fits (intercept, A1, A2, M(t) of every window) recomputed for %d records: max |difference| "
            "%.3g; windows fitted by the lstsq recipe instead of the closed form: %d" % (
                counted["fits"], maxima["fits"], fallbacks))
    rep.say("  observed Delta and S recomputed for %d records: max |difference| %.3g (Delta), %.3g (S)" % (
        len(results), maxima["components"], maxima["S"]))
    rep.say("  fitted nulls (coefficients, intercept, modulus, initial values, residuals) compared for %d records: "
            "max |difference| %.3g" % (counted["nulls"], maxima["nulls"]))
    rep.say("  generator check (section 11): stored input regenerated for %d records, bit-identical %d, max "
            "|difference| %.3g" % (counted["generation"], identical, regen_max))
    rep.say("  every surrogate attempt regenerated for %d records: max |difference| %.3g (S_b), %.3g (Delta_b); "
            "near ties (|S_b - S| <= 1e-9): %d recomputed, %d among stored statistics" % (
                len(full), maxima["statistics"], maxima["changes"], len(near_ties), len(stored_near_ties)))
    rep.say("  recomputation time %.1f s" % compute_seconds)
    # 4. cell summaries
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
    rep.say("[4] CELL SUMMARIES FROM THE RECOMPUTED p-VALUES (denominator %d per cell; a rejection is a valid raw "
            "p <= 0.05)%s" % (n, " - partial: incomplete cells are expected" if args.partial else ""))
    if size is not None:
        rep.say("  size: R = %d of %d; valid %d; rate %s; Wilson 95%% %s; MC s.e. %s; mean S %s (s.e. %s); "
                "accounting bounds %s" % (size["rejected"], n, size["valid"], fmt(size["rate"]),
                                          fmt_interval(size["rate_wilson"]), fmt(size["rate_se"]),
                                          fmt(size["mean_S"], 8), fmt(size["mean_S_se"]), size["accounting_bounds"]))
        if size["failures"]:
            rep.say("    invalid records by status: %s" % json.dumps(size["failures"], sort_keys=True))
    for cell in power_cells:
        rep.say("  power kappa %.1f: R = %d of %d; valid %d; rate %s; Wilson 95%% %s; mean S %s (s.e. %s)" % (
            cell["kappa"], cell["rejected"], n, cell["valid"], fmt(cell["rate"]), fmt_interval(cell["rate_wilson"]),
            fmt(cell["mean_S"], 8), fmt(cell["mean_S_se"])))
        if cell["failures"]:
            rep.say("    invalid records by status: %s" % json.dumps(cell["failures"], sort_keys=True))
    if power is not None:
        for adj in power["adjacent"]:
            rep.say("  kappa %.1f -> %.1f: difference %+.4f; s.e. %.5f; 1.96 s.e. %.5f; decrease flag %s" % (
                adj["left_kappa"], adj["right_kappa"], adj["difference"], adj["standard_error"], adj["threshold"],
                adj["decrease_flag"]))
        rep.say("  D80: %s%s" % (power["d80_status"], "" if power["D80"] is None else " = %s at kappa80 = %s (%s)" % (
            fmt(power["D80"], 8), fmt(power["kappa80"]), power["crossing"])))
    # 5. registered rule
    registered_design = bool(not args.development and reference and reference["mode"] == "registered"
                             and reference["master_seed"] == REGISTERED_SEED and ctx.manifest_problems == 0)
    rep.say("")
    rep.say("[5] THE REGISTERED RULE ON THESE NUMBERS")
    rep.say("  precondition: registered design, identity and gate in every manifest (mode registered, seed 1927, "
            "200 series, B = 1,000, Annex A streams, clean tree, Python 3.12.14, the E2 gate): %s" % (
                "yes" if registered_design else "no (development run or a mismatch)"))
    verdicts = {}
    if size is not None:
        rule = size_rule(size, n)
        verdicts["size"] = dict(rule, registered=registered_design, passed=bool(registered_design and rule["passed"]))
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
    # 6. runner summaries
    rep.say("")
    rep.say("[6] COMPARISON WITH THE RUNNER'S SUMMARIES")
    runner = []
    for path in summaries:
        check = "power" if "power" in path.name else "size"
        if check == "size" and size is None or check == "power" and power is None:
            rep.problem(path.name, "a %s summary without %s records" % (check, check))
            continue
        item = compare_runner(ctx, path, check, [size] if check == "size" else power_cells, power,
                              registered_design, verdicts[check]["passed"])
        runner.append(item)
        rep.say("  %s: %d fields compared, %d differ; absent fields %s" % (path.name, item["compared"],
                                                                         len(item["differences"]),
                                                                         item["absent"] or "none"))
    if not runner:
        rep.say("  no runner summary given or found: not compared")
    # 7. result
    rep.say("")
    rep.say("[7] RESULT")
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
    payload = dict(program="verify_e2_x3.py", version=VERSION, python=platform.python_version(),
                   numpy=np.__version__, platform=platform.platform(), elapsed_seconds=elapsed,
                   compute_seconds=compute_seconds, arguments=vars(args), files=ctx.files, coverage=cover,
                   fingerprint=reference, prereg=prereg, prerequisite=prereq,
                   sample=None if args.sample is None else dict(
                       seed=args.sample_seed, requested=args.sample,
                       records=[list(ctx.jobs[i]["key"]) for i in chosen]),
                   per_record=[dict(record=list(r["key"]), status=r["status"], basis=r["basis"], S=r["S"],
                                    p=r["p"], K=r["K"], retained=r["retained"], valid=r["valid"],
                                    rejected=bool(r["rejected"]), max_diff=r["max_diff"],
                                    regeneration_identical=r["regeneration_identical"],
                                    problems=len(r["issues"])) for r in results],
                   maxima=dict(maxima, regeneration=regen_max), fallbacks=fallbacks, near_ties=near_ties,
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
