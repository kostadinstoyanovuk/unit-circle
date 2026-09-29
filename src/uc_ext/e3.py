"""E3 (prereg/E3.md, fixed at research commit 5a26bfc): time-varying AR(2) with filtered root moduli.

State alpha[s] = (c, phi1_s, phi2_s)' for s = 2..258 follows a random walk with variance
sigma2*diag(0, r1, r2); observation noise sigma2; diffuse start N(0, sigma2*1e8*I3). The variances
are estimated by maximum likelihood (prediction-error decomposition, sigma2 concentrated out, first
d = 3 terms excluded), by a fixed 16 x 16 grid in (r1, r2) followed by L-BFGS-B refinement in log10.
M(t) is H1's companion-root modulus of the FILTERED state a(t|t), available for t >= 39.
Recessions, Delta = M(r-1) - M(r-9), eligibility, the fitted constant AR(2) null, surrogate draws
and p-values are H1's (uc_core), imported unchanged; the same ML procedure is applied to every
surrogate (primary) or the observed variances are held fixed (secondary).

The reference filter is uc_core.statespace.kalman_filter (square-root, version 2). `batched_filter`
evaluates many (r1, r2) points or series at once with the same operations and the same LAPACK QR per
matrix; section 6 permits it only where it agrees with the reference to 1e-8 in every filtered
state and 1e-6 in l(r) (`filter_agreement`, run on every X.3 fixture by the check runners and, with
AT-11 on both filters, on AT-11's fixture by `at11_checks` inside the prerequisite step).

Synthetic-only blind build: no function reads or downloads data. The one exception is AT-11's test
fixture (`at11_fixture`), the yearly sunspot series 1749-1924 bundled with the locked statsmodels, which
the research repository already uses for AT-11; it is loaded from the installed package, never downloaded.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import math

import numpy as np
from scipy.optimize import minimize

from uc_core import surrogate as s
from uc_core.ar import fit_ols, root_summary
from uc_core.constants import MASTER_SEED, POWER_KAPPAS, POWER_ONSETS
from uc_core.h1 import Observation, _comparison, _failed, _observation
from uc_core.recession import PreOnsetResult, episodes, pre_onset_changes
from uc_core.rolling import _observations_and_index
from uc_core.secondary import episode_percentile_interval, mean_pre_onset_trend
from uc_core.statespace import _factor, kalman_filter, regression_at11
from uc_core.validation_design import h1_design_series

from . import common as c

# Sections 5-6.
N_GROWTH = 259
M_STATE = 3
DIFFUSE = 1e8
EXCLUDED = 3                                   # d: one term per diffuse state element (s = 2, 3, 4)
N_STAR = N_GROWTH - 2 - EXCLUDED               # 254
GRID_EXPONENTS = (None, *range(-16, -1))       # 0, then 10^(k/2) for k = -16..-2
LOG10_BOUNDS = (-10., 0.)
MAXITER = 200
FIRST_INDICATOR = 39                           # a 40-quarter warm-up, as H1's W = 40
# Section 7-8 and 10: H1's episode rules; Kendall over 16 quarters.
LOOKBACK = 8
MERGE = 8
MINIMUM_RUN = 2
TREND_SPAN = 16
FIRST_ELIGIBLE = FIRST_INDICATOR + LOOKBACK + 1      # 48
SURROGATE_ATTEMPTS = 1000
EPISODE_RESAMPLES = 10000
# Annex A.
STREAM_IDS = dict(primary=5300, fixed=5303, wild=5304, interval=5305, size_generation=5320, size_null=5321,
                  power_generation=5330, power_null=5331)
PREREQUISITE_FIXTURE = dict(stream="size_generation", cell=1, replicate=0)
# Section 11.
SERIES_PER_CELL = 200
SIZE_BOUNDS = (.02, .09)
KAPPAS = POWER_KAPPAS
# S6 (owner's ruling pending; decision-note.md). Section 6 says both "a non-positive or non-finite F[s],
# or a non-finite state, is a failure" and "non-finite grid values are discarded". GRID_POINT_FAILURE fixes
# what a filter failure AT A GRID POINT does: "discard" (the M4b reading and the default: the point's
# value is non-finite and is discarded; the fit fails only if all 256 are, or at the accepted estimate or
# in the indicator run) or "fail" (any grid-point filter failure fails the whole fit). The value in force
# is recorded in every MLFit and in every X.3 manifest and record.
GRID_POINT_FAILURE_OPTIONS = ("discard", "fail")
GRID_POINT_FAILURE = "discard"
# S7 (owner's ruling pending; decision-note.md). What the X.3 replicates retain of each ML fit:
# "all_fits" keeps the full likelihood grid, refinement record and boundary flags of the base series and
# of every surrogate (Annex B's list; the check runner stores the surrogate fits compressed), "base_fits"
# keeps only each base series' fit. Default: all_fits under the registered seed, because a registered run
# without retention cannot be repaired except by recomputation; base_fits in development runs.
X3_RETENTION_OPTIONS = ("all_fits", "base_fits")
X3_RETENTION = dict(registered="all_fits", development="base_fits")
AGREEMENT_STATE_TOL = 1e-8
AGREEMENT_LOGLIK_TOL = 1e-6
AT11_TOL = 1e-6
# AT-11's fixture (plan p. 21; sections 6 and 11): the yearly sunspot numbers 1749-1924 bundled with
# statsmodels, selected exactly as the research repository's AT-11 test does (tests/test_foundations.py,
# sunspots_1749_1924). The hash of the (year, value) array is the one the research repository recorded for
# this interval (audit/baseline_results.json, intervals/1749-1924/year_value_array_sha256).
AT11_YEARS = (1749, 1924)
AT11_YEAR_VALUE_SHA256 = "b6f242da36c8894a60c24f03b3601a5dca2ab46c6de1f05e28779f34eb3e2c95"


def grid_value(exponent):
    return 0. if exponent is None else 10. ** (exponent / 2)


GRID = tuple(grid_value(k) for k in GRID_EXPONENTS)


class FitFailure(ValueError):
    """The section 6 fit failed (all grid values non-finite, or a failure at the chosen estimate)."""


# ------------------------------------------------------------------------------------ filtering

def state_space(values):
    """y[s] = g[s] and z[s] = (1, g[s-1], g[s-2]) for s = 2..n-1."""
    x, _ = _observations_and_index(values)
    return x[2:], np.column_stack((np.ones(len(x) - 2), x[1:-1], x[:-2]))


def reference_filter(values, r1, r2, sigma2=1.0):
    """uc_core.statespace.kalman_filter at (sigma2, r1, r2) with the section 6 prior."""
    y, Z = state_space(values)
    return kalman_filter(y, Z, np.eye(M_STATE), sigma2 * np.diag([0., r1, r2]), sigma2,
                         np.zeros(M_STATE), sigma2 * DIFFUSE * np.eye(M_STATE))


def concentrated_loglik(errors, variances):
    """Section 6 steps 2-4. Returns (l, sigma2_hat); non-finite F, v or sigma2 gives (nan, nan)."""
    v = np.asarray(errors, dtype=float)
    F = np.asarray(variances, dtype=float)
    if not (np.isfinite(v).all() and np.isfinite(F).all() and (F > 0).all()):
        return math.nan, math.nan
    v, F = v[EXCLUDED:], F[EXCLUDED:]
    n_star = len(v)
    sigma2 = float(np.sum(v * v / F)) / n_star
    if not (math.isfinite(sigma2) and sigma2 > 0):
        return math.nan, math.nan
    loglik = -(n_star / 2) * (math.log(2 * math.pi) + 1 + math.log(sigma2)) - .5 * float(np.sum(np.log(F)))
    return (loglik, sigma2) if math.isfinite(loglik) else (math.nan, math.nan)


def reference_loglik(values, r1, r2):
    """l(r) by the reference filter at sigma2 = 1; a filter failure is a non-finite value."""
    try:
        result = reference_filter(values, r1, r2)
    except (ValueError, FloatingPointError, np.linalg.LinAlgError):
        return math.nan, math.nan, None
    if not np.isfinite(result.filtered_states).all():
        return math.nan, math.nan, result
    loglik, sigma2 = concentrated_loglik(result.prediction_errors, result.prediction_variances)
    return loglik, sigma2, result


def filter_failed(result):
    """Section 6 failure of one reference-filter run: it raised (result None), or some F[s] is non-positive
    or non-finite, or some filtered state is non-finite. A non-finite l for another reason is not one."""
    if result is None:
        return True
    F = np.asarray(result.prediction_variances, dtype=float)
    return not (np.isfinite(result.filtered_states).all() and np.isfinite(F).all() and (F > 0).all())


@dataclass(frozen=True)
class BatchResult:
    loglik: np.ndarray
    sigma2: np.ndarray
    failed: np.ndarray                   # l is not usable (a filter failure or a non-finite value)
    filtered_states: np.ndarray | None
    filter_failed: np.ndarray | None = None   # the section 6 filter failures among them (S6)


def batched_filter(y, Z, points, *, store_states=False):
    """The reference square-root filter at sigma2 = 1, vectorised over a batch.

    y has shape (n,) or (G, n); Z (n, 3) or (G, n, 3); points is a (G, 2) array of (r1, r2).
    Each step performs the reference's operations with T = I3 (multiplying by the identity is
    exact, so it is omitted) and the same LAPACK QR for every batch member. A non-positive or
    non-finite F, or a non-finite state, marks that member as a filter failure (`filter_failed`); it and a
    non-finite l or sigma2_hat mark the member as failed (l = nan).
    """
    points = np.atleast_2d(np.asarray(points, dtype=float))
    G = points.shape[0]
    y = np.broadcast_to(np.asarray(y, dtype=float), (G, np.shape(y)[-1]))
    Z = np.broadcast_to(np.asarray(Z, dtype=float), (G, *np.shape(Z)[-2:]))
    n, m = Z.shape[1], Z.shape[2]
    if m != M_STATE or y.shape[1] != n or not np.isfinite(y).all() or not np.isfinite(Z).all():
        raise ValueError("Expected finite observations with a three-column loading matrix")
    root_Q = np.stack([_factor(np.diag([0., r1, r2])) for r1, r2 in points])
    S = np.broadcast_to(_factor(DIFFUSE * np.eye(m)), (G, m, m)).copy()
    a = np.zeros((G, m))
    states = np.empty((G, n, m)) if store_states else None
    broken = np.zeros(G, dtype=bool)
    sum_ratio = np.zeros(G)
    sum_log = np.zeros(G)
    pre = np.zeros((G, m + 1, m + 1))
    pre[:, 0, 0] = 1.0                                   # sqrt(H) with H = 1
    with np.errstate(all="ignore"):
        for t in range(n):
            z = Z[:, t, :]
            v = y[:, t] - np.einsum("gi,gi->g", z, a)
            pre[:, 0, 1:] = np.einsum("gi,gij->gj", z, S)
            pre[:, 1:, 1:] = S
            post = np.swapaxes(np.linalg.qr(np.swapaxes(pre, 1, 2), mode="r"), 1, 2)
            flip = post[:, 0, 0] < 0
            post[flip, :, 0] = -post[flip, :, 0]
            root_F = post[:, 0, 0]
            F = root_F * root_F
            broken |= ~(F > 0) | ~np.isfinite(F)
            a = a + post[:, 1:, 0] * (v / root_F)[:, None]
            S = post[:, 1:, 1:]
            broken |= ~np.isfinite(a).all(axis=1)
            if store_states:
                states[:, t] = a
            if t >= EXCLUDED:
                sum_ratio += v * v / F
                sum_log += np.log(F)
            stacked = np.concatenate((S, root_Q), axis=2)
            S = np.swapaxes(np.linalg.qr(np.swapaxes(stacked, 1, 2), mode="r"), 1, 2)[:, :, :m]
        n_star = n - EXCLUDED
        sigma2 = sum_ratio / n_star
        loglik = -(n_star / 2) * (math.log(2 * math.pi) + 1 + np.log(sigma2)) - .5 * sum_log
    failed = broken | ~np.isfinite(loglik) | ~(sigma2 > 0)
    loglik = np.where(failed, np.nan, loglik)
    sigma2 = np.where(failed, np.nan, sigma2)
    return BatchResult(loglik, sigma2, failed, states, filter_failed=broken)


def filter_agreement(values, points=None):
    """Section 6 agreement test of batched_filter against the reference at the given points.

    Default points: the full 16 x 16 grid. Returns maxima over points of the filtered-state and
    l(r) differences and whether they meet 1e-8 and 1e-6.
    """
    points = grid_points() if points is None else np.atleast_2d(np.asarray(points, dtype=float))
    y, Z = state_space(values)
    batch = batched_filter(y, Z, points, store_states=True)
    state_error, loglik_error, mismatched_failures = 0., 0., 0
    for index, (r1, r2) in enumerate(points):
        loglik, _, reference = reference_loglik(values, r1, r2)
        if reference is None or not math.isfinite(loglik) or batch.failed[index]:
            mismatched_failures += int((reference is None or not math.isfinite(loglik)) != bool(batch.failed[index]))
            continue
        state_error = max(state_error, float(np.max(np.abs(batch.filtered_states[index] - reference.filtered_states))))
        loglik_error = max(loglik_error, abs(float(batch.loglik[index]) - loglik))
    passed = (state_error <= AGREEMENT_STATE_TOL and loglik_error <= AGREEMENT_LOGLIK_TOL
              and mismatched_failures == 0)
    return dict(points=len(points), max_state_difference=state_error, max_loglik_difference=loglik_error,
                mismatched_failures=mismatched_failures, passed=passed)


def grid_points():
    return np.array([(r1, r2) for r1 in GRID for r2 in GRID])


# ----------------------------------------------------------------------------- maximum likelihood

@dataclass(frozen=True)
class MLFit:
    status: str
    r1: float | None
    r2: float | None
    loglik: float | None
    sigma2: float | None
    q1: float | None
    q2: float | None
    grid_loglik: tuple                      # 16 x 16, rows r1, columns r2; None for non-finite
    grid_max: dict
    refinement: dict | None
    accepted: str | None
    at_zero: tuple
    at_upper: tuple
    loglik_at_zero: float | None
    error: str | None = None
    grid_filter_failures: tuple = ()        # (i, j) of grid points whose filter failed (S6)
    grid_point_failure: str | None = None   # the S6 reading in force for this fit
    at_lower_bound: tuple = ()              # C5: a refined coordinate at the lower bound 1e-10 (log10 = -10)


def _grid_choice(values_grid):
    """Maximum, ties broken by smaller r1 + r2, then smaller r1 (section 6 step 1)."""
    best = None
    for i, r1 in enumerate(GRID):
        for j, r2 in enumerate(GRID):
            value = values_grid[i, j]
            if not math.isfinite(value):
                continue
            key = (-value, r1 + r2, r1)
            if best is None or key < best[0]:
                best = (key, i, j)
    return None if best is None else (best[1], best[2])


# C1: inside one comparison or one X.3 replicate the series analysed first (the observed or base series)
# is fitted once. A reuse scope remembers the first fit made inside it and returns that same MLFit when the
# same series is fitted again with the same engine and S6 reading; every other fit is computed as usual.
# The fit is deterministic, so reuse changes no result (tested); it only avoids recomputing it.
_REUSE_SCOPES = []


@contextmanager
def _reusing_first_fit(values=None, engine=None, fit=None):
    """A C1 reuse scope, optionally seeded with a fit already made of `values`."""
    scope = {}
    if fit is not None and fit.grid_point_failure is not None:
        scope[(engine, fit.grid_point_failure, np.asarray(values, dtype=float).tobytes())] = fit
    _REUSE_SCOPES.append(scope)
    try:
        yield
    finally:
        _REUSE_SCOPES.pop()


def fit_ml(values, *, engine="batched", grid_failure=None):
    """Section 6 maximisation: grid, L-BFGS-B refinement in log10 on [-10, 0], acceptance, record.

    engine='batched' evaluates the grid with batched_filter; engine='reference' evaluates every point
    with uc_core's filter. The refinement, the acceptance comparison and the accepted estimate's l,
    sigma2_hat and q_hat always use the reference filter (grid_max records both values of the grid maximum).
    grid_failure (S6) is 'discard' or 'fail'; None means the module setting GRID_POINT_FAILURE.
    """
    if engine not in ("batched", "reference"):
        raise ValueError("engine must be 'batched' or 'reference'")
    reading = GRID_POINT_FAILURE if grid_failure is None else grid_failure
    if reading not in GRID_POINT_FAILURE_OPTIONS:
        raise ValueError(f"grid_failure must be one of {GRID_POINT_FAILURE_OPTIONS}")
    if not _REUSE_SCOPES:
        return _fit_ml(values, engine, reading)
    scope, key = _REUSE_SCOPES[-1], (engine, reading, np.asarray(values, dtype=float).tobytes())
    if key in scope:
        return scope[key]
    fit = _fit_ml(values, engine, reading)
    if not scope:
        scope[key] = fit
    return fit


def _lower_bound_flags(accepted, free, refinement):
    """C5: which coordinates of an accepted refined point lie at the lower bound log10 r = -10."""
    flags = [False, False]
    if accepted == "refined":
        for position, k in enumerate(free):
            flags[k] = refinement["log10"][position] == LOG10_BOUNDS[0]
    return tuple(flags)


def _fit_ml(values, engine, reading):
    points = grid_points()
    shape = (len(GRID), len(GRID))
    if engine == "batched":
        y, Z = state_space(values)
        batch = batched_filter(y, Z, points)
        grid, broken = batch.loglik.reshape(shape), batch.filter_failed.reshape(shape)
    else:
        evaluations = [reference_loglik(values, r1, r2) for r1, r2 in points]
        grid = np.array([e[0] for e in evaluations]).reshape(shape)
        broken = np.array([filter_failed(e[2]) for e in evaluations]).reshape(shape)
    grid_record = tuple(tuple(float(v) if math.isfinite(v) else None for v in row) for row in grid)
    zero_loglik = float(grid[0, 0]) if math.isfinite(grid[0, 0]) else None
    failures = tuple((int(i), int(j)) for i, j in zip(*np.nonzero(broken)))
    recorded = dict(grid_filter_failures=failures, grid_point_failure=reading)
    if failures and reading == "fail":
        return MLFit("failed", None, None, None, None, None, None, grid_record, {}, None, None, (), (),
                     zero_loglik, f"Filter failure at {len(failures)} grid point(s) (S6 reading 'fail')",
                     **recorded)
    choice = _grid_choice(grid)
    if choice is None:
        return MLFit("failed", None, None, None, None, None, None, grid_record, {}, None, None, (), (),
                     zero_loglik, "All 256 grid values are non-finite", **recorded)
    i, j = choice
    exponents = (GRID_EXPONENTS[i], GRID_EXPONENTS[j])
    grid_r = (GRID[i], GRID[j])
    grid_l = float(grid[i, j])
    free = [k for k in (0, 1) if exponents[k] is not None]
    refinement, accepted, r_hat = None, "grid", grid_r
    grid_reference = None
    if free:
        def unpack(x):
            r = [0., 0.]
            for position, k in enumerate(free):
                r[k] = 10. ** x[position]
            return r

        def objective(x):
            value = reference_loglik(values, *unpack(x))[0]
            return -value if math.isfinite(value) else math.inf

        x0 = np.array([exponents[k] / 2 for k in free])
        with np.errstate(all="ignore"):
            result = minimize(objective, x0, method="L-BFGS-B", bounds=[LOG10_BOUNDS] * len(free),
                              options=dict(maxiter=MAXITER))
        refined_r = tuple(unpack(result.x))
        refined_l = reference_loglik(values, *refined_r)[0]
        refinement = dict(start_log10=x0.tolist(), log10=np.asarray(result.x).tolist(), r=refined_r,
                          loglik=refined_l if math.isfinite(refined_l) else None, success=bool(result.success),
                          status=int(result.status), message=str(result.message), nit=int(result.nit),
                          nfev=int(result.nfev))
        # Step 3 compares the refined point with the grid maximum, both evaluated by the reference filter.
        grid_reference = reference_loglik(values, *grid_r)[0]
        if math.isfinite(refined_l) and (not math.isfinite(grid_reference) or refined_l >= grid_reference):
            accepted, r_hat = "refined", refined_r
    loglik, sigma2, result = reference_loglik(values, *r_hat)
    grid_max = dict(r=grid_r, loglik=grid_l, index=(i, j),
                    loglik_reference=(float(loglik) if accepted == "grid" and math.isfinite(loglik) else
                                      float(grid_reference) if grid_reference is not None
                                      and math.isfinite(grid_reference) else None))
    if result is None or not math.isfinite(loglik):
        return MLFit("failed", *r_hat, None, None, None, None, grid_record, grid_max, refinement, accepted,
                     (), (), zero_loglik, "Filter failure at the accepted estimate", **recorded)
    return MLFit("ok", r_hat[0], r_hat[1], float(loglik), float(sigma2), float(sigma2 * r_hat[0]),
                 float(sigma2 * r_hat[1]), grid_record, grid_max,
                 refinement, accepted, (r_hat[0] == 0., r_hat[1] == 0.), (r_hat[0] == 1., r_hat[1] == 1.),
                 zero_loglik, **recorded, at_lower_bound=_lower_bound_flags(accepted, free, refinement))


def filtered_modulus(values, sigma2, r1, r2):
    """Section 6 indicator: filter at (sigma2, r1, r2); M(t) from a(t|t) for t >= 39, NaN before.

    Returns (M, filtered states for t = 2..n-1). A filter failure or non-finite state raises FitFailure.
    """
    x, _ = _observations_and_index(values)
    try:
        result = reference_filter(x, r1, r2, sigma2)
    except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise FitFailure(f"Indicator filter failed: {error}") from error
    states = result.filtered_states
    if not np.isfinite(states).all():
        raise FitFailure("Non-finite filtered state")
    modulus = np.full(len(x), np.nan)
    for t in range(FIRST_INDICATOR, len(x)):
        modulus[t] = root_summary(states[t - 2, 1:]).modulus
    return modulus, states


def estimate(values, *, engine="batched", fit_log=None):
    """ML fit then filtered M. Raises FitFailure on a failed fit. fit_log (a list) receives the MLFit."""
    fit = fit_ml(values, engine=engine)
    if fit_log is not None:
        fit_log.append(fit)
    if fit.status != "ok":
        raise FitFailure(fit.error)
    modulus, states = filtered_modulus(values, fit.sigma2, fit.r1, fit.r2)
    return fit, modulus, states


# ------------------------------------------------------------------------------ statistics

def onsets_of(values):
    return tuple(e.onset for e in episodes(values, minimum_run=MINIMUM_RUN, merge=MERGE))


def statistic(values, *, fixed_onsets=None, variances=None, engine="batched", fit_log=None):
    """S from the filtered M. variances=None re-estimates by section 6; else (sigma2, r1, r2) held fixed.

    Mirrors uc_core.surrogate._statistic: eligibility (onset >= 48) is settled before any fit.
    """
    onsets = onsets_of(values) if fixed_onsets is None else tuple(fixed_onsets)
    if not any(t >= FIRST_ELIGIBLE for t in onsets):
        return PreOnsetResult(None, (), (), onsets)
    if variances is None:
        _, modulus, _ = estimate(values, engine=engine, fit_log=fit_log)
    else:
        modulus, _ = filtered_modulus(values, *variances)
    return pre_onset_changes(modulus, onsets, lookback=LOOKBACK)


METRICS = ("primary", "held_fixed", "trend")


def _measure(values, *, variances, engine, fit_log=None):
    """Primary (re-estimated), held-fixed and Kendall observations on one path (section 10)."""
    onsets = onsets_of(values)
    output = {name: Observation("no_eligible_episode", None, ineligible_onsets=onsets) for name in METRICS}
    primary_eligible = any(t >= FIRST_ELIGIBLE for t in onsets)
    trend_eligible = any(t >= FIRST_INDICATOR + TREND_SPAN for t in onsets)
    re_estimated, error = None, None
    if primary_eligible or trend_eligible:
        try:
            re_estimated = estimate(values, engine=engine, fit_log=fit_log)[1]
        except c.NUMERIC_ERRORS as caught:
            error = caught
    for name, eligible in (("primary", primary_eligible), ("trend", trend_eligible)):
        if not eligible:
            continue
        if error is not None:
            output[name] = _failed(error)
            continue
        try:
            result = (mean_pre_onset_trend(re_estimated, onsets, span=TREND_SPAN) if name == "trend"
                      else pre_onset_changes(re_estimated, onsets, lookback=LOOKBACK))
            output[name] = _observation(result, trend=name == "trend")
        except c.NUMERIC_ERRORS as caught:
            output[name] = _failed(caught)
    if primary_eligible and variances is not None:
        try:
            held = filtered_modulus(values, *variances)[0]
            output["held_fixed"] = _observation(pre_onset_changes(held, onsets, lookback=LOOKBACK))
        except c.NUMERIC_ERRORS as caught:
            output["held_fixed"] = _failed(caught)
    return output


@dataclass(frozen=True)
class JointComparison:
    primary: object
    held_fixed: object
    trend: object
    observed_fit: MLFit | None
    null_model: s.NullModel | None
    rng_before: dict
    rng_after: dict
    generated_attempts: int
    null_error: str | None = None
    fit_error: str | None = None


def primary_with_comparators(values, *, B, rng, engine="batched", fits=None):
    """Stream 5300: one set of residual paths for the primary, held-fixed and Kendall comparisons.

    fits (a dict) receives each surrogate attempt's serialised MLFit (None when no fit was needed).
    """
    with _reusing_first_fit():
        return _primary_with_comparators(values, B=B, rng=rng, engine=engine, fits=fits)


def _primary_with_comparators(values, *, B, rng, engine, fits):
    B = s._integer(B, "B")
    s._generator(rng)
    x, _ = _observations_and_index(values)
    before = deepcopy(rng.bit_generator.state)
    observed_fit, fit_error, variances = None, None, None
    try:
        observed_fit = fit_ml(x, engine=engine)
        if observed_fit.status == "ok":
            variances = (observed_fit.sigma2, observed_fit.r1, observed_fit.r2)
        else:
            fit_error = observed_fit.error
    except c.NUMERIC_ERRORS as error:
        fit_error = f"{type(error).__name__}: {error}"
    observed = _measure(x, variances=variances, engine=engine)
    # S8: without observed variances the held-fixed statistic failed whenever it was due (an eligible
    # episode exists); H1 section 8 keeps that distinct from an empty eligible set.
    if variances is None and any(t >= FIRST_ELIGIBLE for t in onsets_of(x)):
        observed["held_fixed"] = Observation("failed", None, error=f"Observed fit failed: {fit_error}")
    model, null_error = None, None
    records = {name: [] for name in METRICS}
    generated = 0
    if any(o.status == "ok" for o in observed.values()):
        try:
            model = s.prepare_null(x)
        except s.NullModelError as error:
            null_error = str(error)
    if model is not None:
        for number in range(B):
            generated += 1
            log = []                     # S9: reset before the draw, so a failed draw records no fit
            try:
                path = s.draw_surrogate(model, rng)
                measures = _measure(path, variances=variances, engine=engine, fit_log=log)
            except c.NUMERIC_ERRORS as error:
                measures = {name: _failed(error) for name in METRICS}
            if fits is not None:
                fits[number] = c.serial(log[0]) if log else None
            for name in METRICS:
                if observed[name].status != "ok":
                    continue
                value = measures[name]
                records[name].append(s.Attempt(number, "retained" if value.status == "ok" else value.status,
                                               value.value, value.eligible_onsets, value.components, value.error))
    comparisons = {name: _comparison(name, observed[name], records[name], B) for name in METRICS}
    if null_error:
        comparisons = {name: (type(result)(**{**result.__dict__, "status": "null_model_failed"})
                              if observed[name].status == "ok" else result)
                       for name, result in comparisons.items()}
    return JointComparison(**comparisons, observed_fit=observed_fit, null_model=model, rng_before=before,
                           rng_after=deepcopy(rng.bit_generator.state), generated_attempts=generated,
                           null_error=null_error, fit_error=fit_error)


def csd_test(values, *, B, rng, onset_mode="endogenous", innovation_mode="residual", engine="batched",
             fits=None):
    """uc_core.surrogate.csd_test with the E3 statistic; every surrogate is re-estimated by section 6.

    onset_mode 'fixed' uses the observed eligible onsets (stream 5303); 'wild' innovations (5304).
    """
    B = s._integer(B, "B")
    s._generator(rng)
    if onset_mode not in ("endogenous", "fixed") or innovation_mode not in ("residual", "wild"):
        raise ValueError("Unsupported onset or innovation mode")
    x, _ = _observations_and_index(values)
    before = deepcopy(rng.bit_generator.state)
    observed = statistic(x, engine=engine)
    if observed.mean_change is None:
        return s.Comparison("observed_not_estimable", observed, None, B, 0, 0, 0, 0, None, None, (), None,
                            FIRST_INDICATOR + 1, LOOKBACK, MERGE, onset_mode, innovation_mode,
                            before, deepcopy(rng.bit_generator.state))
    model = s.prepare_null(x)
    fixed = observed.eligible_onsets if onset_mode == "fixed" else None
    return _surrogate_loop(x, observed, model, B, rng, before, fixed, onset_mode, innovation_mode, engine, fits)


# C2: every s.Comparison built here carries FIRST_INDICATOR + 1 = 40 in its `window` field. E3 has no rolling
# window; 40 is the warm-up length, kept so that E3 records have H1's record shape (and E3 reduces to H1
# exactly when H1's rolling M is substituted, tests and review check 04). The reporting rows set window None.
def _surrogate_loop(x, observed, model, B, rng, before, fixed, onset_mode, innovation_mode, engine, fits):
    records = []
    for number in range(B):
        log = []
        try:
            simulated = s.draw_surrogate(model, rng, kind=innovation_mode)
            result = statistic(simulated, fixed_onsets=fixed, engine=engine, fit_log=log)
            if result.mean_change is None:
                if fixed is not None:
                    raise FloatingPointError("Fixed dates lost their estimable statistic")
                records.append(s.Attempt(number, "no_eligible_episode", None))
            else:
                if not math.isfinite(result.mean_change):
                    raise FloatingPointError("Non-finite surrogate statistic")
                records.append(s.Attempt(number, "retained", result.mean_change,
                                         result.eligible_onsets, result.changes))
        except c.NUMERIC_ERRORS as error:
            records.append(s.Attempt(number, "failed", None, error=f"{type(error).__name__}: {error}"))
        if fits is not None:
            fits[number] = c.serial(log[0]) if log else None
    kept = [r.statistic for r in records if r.status == "retained"]
    empty = sum(r.status == "no_eligible_episode" for r in records)
    failed = sum(r.status == "failed" for r in records)
    p = None if failed else s.monte_carlo_pvalue(observed.mean_change, kept)
    status = "invalid_surrogate_failure" if failed else ("no_retained_surrogates" if not kept else "ok")
    exceedances = sum(v >= observed.mean_change for v in kept) if kept else None
    return s.Comparison(status, observed, p, B, len(records), len(kept), empty, failed, exceedances,
                        1 / (len(kept) + 1) if kept else None, tuple(records), model, FIRST_INDICATOR + 1,
                        LOOKBACK, MERGE, onset_mode, innovation_mode, before, deepcopy(rng.bit_generator.state))


def fixed_date_test(values, onsets, *, B, rng, engine="batched", fits=None):
    """Power proxy (section 11): S at externally imposed onsets; every surrogate re-estimated.

    Mirrors uc_core.h1.fixed_date_test (validation of dates before any draw, no run detection).
    """
    B = s._integer(B, "B")
    s._generator(rng)
    x, _ = _observations_and_index(values)
    before = deepcopy(rng.bit_generator.state)
    from uc_core.secondary import signed_pre_onset_changes
    dates = signed_pre_onset_changes(np.full(len(x), np.nan), onsets, lookback=LOOKBACK).ineligible_onsets
    observed = statistic(x, fixed_onsets=dates, engine=engine)
    if observed.mean_change is None:
        return s.Comparison("observed_not_estimable", observed, None, B, 0, 0, 0, 0, None, None, (), None,
                            FIRST_INDICATOR + 1, LOOKBACK, MERGE, "external_fixed", "residual",
                            before, deepcopy(rng.bit_generator.state))
    model = s.prepare_null(x)
    return _surrogate_loop(x, observed, model, B, rng, before, observed.eligible_onsets, "external_fixed",
                           "residual", engine, fits)


def analyze(values, *, master_seed=MASTER_SEED, allow_registered=False, B=SURROGATE_ATTEMPTS,
            interval_B=EPISODE_RESAMPLES, engine="batched"):
    """The single E3 run (X.4) in memory: primary, held-fixed, Kendall, fixed dates, wild, interval, descriptives."""
    master_seed = c.check_seed(master_seed, allow_registered)
    B = s._integer(B, "B")
    interval_B = s._integer(interval_B, "interval_B")
    x, _ = _observations_and_index(values)
    if len(x) != N_GROWTH:
        raise ValueError(f"E3 uses exactly {N_GROWTH} growth values (1955Q2-2019Q4)")

    def rng(name):
        return c.stream_rng(master_seed, STREAM_IDS[name])

    fits = dict(primary={}, fixed={}, wild={})
    joint = primary_with_comparators(x, B=B, rng=rng("primary"), engine=engine, fits=fits["primary"])

    def secondary(name, **kwargs):
        try:
            with _reusing_first_fit(x, engine, joint.observed_fit):      # C1: the observed fit is reused
                return csd_test(x, B=B, rng=rng(name), engine=engine, fits=fits[name], **kwargs)
        except s.NullModelError as error:
            return dict(status="null_model_failed", p_value=None, requested=B, attempted=0, error=str(error))
        except c.NUMERIC_ERRORS as error:
            return dict(status="observed_statistic_failed", p_value=None, requested=B, attempted=0,
                        error=f"{type(error).__name__}: {error}")

    fit = joint.observed_fit
    descriptive = None
    if fit is not None and fit.status == "ok":
        modulus, states = filtered_modulus(x, fit.sigma2, fit.r1, fit.r2)
        at_zero = reference_loglik(x, 0., 0.)[0]
        descriptive = dict(sigma2=fit.sigma2, r1=fit.r1, r2=fit.r2, q1=fit.q1, q2=fit.q2,
                           at_zero=fit.at_zero, at_upper=fit.at_upper, at_lower_bound=fit.at_lower_bound,
                           loglik=fit.loglik,
                           loglik_at_zero=at_zero if math.isfinite(at_zero) else None,
                           loglik_minus_loglik_at_zero=fit.loglik - at_zero if math.isfinite(at_zero) else None,
                           filtered_modulus=modulus.tolist(), filtered_states=states.tolist())
    result = dict(
        master_seed=master_seed, input_sha256=c.sha256_values(x), engine=engine, joint=joint,
        descriptive=descriptive, surrogate_fits=fits,
        fixed=secondary("fixed", onset_mode="fixed"),
        wild=secondary("wild", innovation_mode="wild"),
        episode_interval=(dict(status="observed_statistic_failed", interval=None, error=joint.primary.observed.error)
                          if joint.primary.observed.status == "failed" else
                          episode_percentile_interval(joint.primary.observed.components, B=interval_B,
                                                      rng=rng("interval"))),
    )
    result["report"] = report(result)
    return result


def report(result):
    """S10: sections 8-9 reporting quantities for every comparison of analyze(): m, k = count(Delta > 0),
    K, B', q = K/B' with its Wilson interval, and the raw p labelled "raw, not family-adjusted".

    E3 has no rolling window, so `window` is None in every row (C2: the Comparison records' own `window`
    field holds 40, the warm-up length FIRST_INDICATOR + 1, to keep H1's record shape).
    """
    sources = [("primary", result["joint"].primary), ("held_fixed", result["joint"].held_fixed),
               ("fixed", result["fixed"]), ("wild", result["wild"]), ("trend", result["joint"].trend)]
    return dict(p_label=c.RAW_P_LABEL, decision="DR-E3 uses the Holm-adjusted p at family closure (section 10)",
                first_indicator=FIRST_INDICATOR,
                rows=[c.comparison_row(name, source, None) for name, source in sources])


# ------------------------------------------------------------------ X.3 prerequisites and checks

def prerequisite_r0(values):
    """r1 = r2 = 0 with the section 6 prior: final filtered state equals full-sample OLS to 1e-6.

    With sigma2 = 1 this is exactly uc_core.statespace.regression_at11 (AT-11's check).
    """
    return regression_at11(values, observation_variance=1.0, prior_variance=DIFFUSE)


def at11_fixture():
    """AT-11's fixture: statsmodels' bundled yearly sunspot numbers, 1749-1924 (176 values).

    A test fixture already in the research repository, loaded from the locked statsmodels package;
    nothing is downloaded. Raises ValueError unless the years are contiguous and the (year, value)
    array has the hash the research repository recorded.
    """
    import statsmodels.api as sm
    data = sm.datasets.sunspots.load_pandas().data
    rows = data[["YEAR", "SUNACTIVITY"]].to_numpy(dtype=float)
    rows = rows[(rows[:, 0] >= AT11_YEARS[0]) & (rows[:, 0] <= AT11_YEARS[1])]
    if not np.array_equal(rows[:, 0], np.arange(AT11_YEARS[0], AT11_YEARS[1] + 1)):
        raise ValueError("AT-11 fixture: the years 1749-1924 are not contiguous")
    if hashlib.sha256(np.asarray(rows, dtype="<f8").tobytes(order="C")).hexdigest() != AT11_YEAR_VALUE_SHA256:
        raise ValueError("AT-11 fixture differs from the 1749-1924 series recorded by the research repository")
    return rows[:, 1].copy()


def batched_at11(values):
    """AT-11 through batched_filter: r1 = r2 = 0, sigma2 = 1 and the diffuse start 1e8*I3.

    The final filtered state must equal intercept-inclusive least squares to 1e-6, the target of
    uc_core.statespace.regression_at11 (which runs the reference filter).
    """
    y, Z = state_space(values)
    batch = batched_filter(y, Z, [(0., 0.)], store_states=True)
    ols = fit_ols(values)
    target = np.array([ols.intercept, *ols.coefficients])
    final = batch.filtered_states[0, -1]
    difference = float(np.max(np.abs(final - target)))
    return dict(final_state=final.tolist(), least_squares=target.tolist(), max_abs_difference=difference,
                filter_failed=bool(batch.failed[0]), tolerance=AT11_TOL,
                passed=bool(not batch.failed[0] and difference <= AT11_TOL))


def at11_checks():
    """B1 (sections 6 and 11) on AT-11's fixture: AT-11 on the reference filter, AT-11 on the batched
    filter at r = 0, and the section 6 agreement test of the batched filter over the 256 grid points."""
    try:
        values = at11_fixture()
    except (ValueError, ImportError, OSError, KeyError) as error:
        return dict(fixture=None, reference_at11=None, batched_at11=None, agreement=None,
                    error=f"{type(error).__name__}: {error}", passed=False)
    fixture = dict(source="statsmodels.datasets.sunspots (bundled with the locked statsmodels), 1749-1924",
                   n=len(values), year_value_sha256=AT11_YEAR_VALUE_SHA256, values_sha256=c.sha256_values(values))
    reference = regression_at11(values, observation_variance=1.0, prior_variance=DIFFUSE)
    batched = batched_at11(values)
    agreement = filter_agreement(values)
    return dict(fixture=fixture, reference_at11=reference, batched_at11=batched, agreement=agreement, error=None,
                passed=bool(reference["passed"] and batched["passed"] and agreement["passed"]))


def prerequisite_fixture(*, master_seed, allow_registered=False):
    """The section 11 prerequisites: the r = 0 check and the agreement test on the registered prerequisite
    series (stream 5320, cell 1, replicate 0; H1 section 9 design), and AT-11 and the agreement test on
    AT-11's fixture (at11_checks). `passed` is true only when every one of them passes."""
    master_seed = c.check_seed(master_seed, allow_registered)
    values = h1_design_series(c.stream_rng(master_seed, STREAM_IDS["size_generation"],
                                           PREREQUISITE_FIXTURE["cell"], PREREQUISITE_FIXTURE["replicate"]))
    r0, agreement, at11 = prerequisite_r0(values), filter_agreement(values), at11_checks()
    return dict(input_sha256=c.sha256_values(values), r0=r0, agreement=agreement, at11=at11,
                passed=bool(r0["passed"] and agreement["passed"] and at11["passed"]))


def _replicate(cell_name, cell_index, replicate, *, master_seed, generation_stream, analysis_stream, kappa,
               B, fixed_onsets, engine, check_agreement, retain_fits):
    generation_rng = c.stream_rng(master_seed, generation_stream, cell_index, replicate)
    analysis_rng = c.stream_rng(master_seed, analysis_stream, cell_index, replicate)
    agreement = {}
    observed_log = []
    fits = {} if retain_fits else None

    def generate(g):
        values = h1_design_series(g, kappa=kappa)
        if check_agreement:
            agreement.update(filter_agreement(values))
        return values

    if fixed_onsets is None:
        observe = lambda v: statistic(v, engine=engine, fit_log=observed_log)
        compare = lambda v, g: csd_test(v, B=B, rng=g, engine=engine, fits=fits)
    else:
        observe = lambda v: statistic(v, fixed_onsets=fixed_onsets, engine=engine, fit_log=observed_log)
        compare = lambda v, g: fixed_date_test(v, fixed_onsets, B=B, rng=g, engine=engine, fits=fits)
    with _reusing_first_fit():           # C1: the base series is fitted once, for observe and compare
        record = c.compute_record(cell_name=cell_name, cell_index=cell_index, replicate=replicate,
                                  generation_rng=generation_rng, analysis_rng=analysis_rng, generate=generate,
                                  observe=observe, compare=compare, requested=B)
    record.update(kappa=kappa, engine=engine, filter_agreement=agreement or None,
                  observed_fit=c.serial(observed_log[0]) if observed_log else None,
                  surrogate_fits=fits, settings=x3_settings(engine=engine, check_agreement=check_agreement,
                                                            retain_fits=retain_fits))
    if check_agreement and agreement and not agreement["passed"] and engine == "batched":
        record.update(status="filter_agreement_failed", p_value=None)
    return record


def default_retention(master_seed):
    """S7: the X3_RETENTION setting for this master seed (registered or development)."""
    return X3_RETENTION["registered" if master_seed == MASTER_SEED else "development"] == "all_fits"


def size_replicate(replicate, *, master_seed, B=SURROGATE_ATTEMPTS, engine="batched", check_agreement=True,
                   retain_fits=None, allow_registered=False):
    """AT-15 analogue replicate: stream 5320 generation, 5321 surrogates, E3 primary mode.

    retain_fits=None applies the S7 setting (X3_RETENTION) for the master seed.
    """
    master_seed = c.check_seed(master_seed, allow_registered)
    retain_fits = default_retention(master_seed) if retain_fits is None else bool(retain_fits)
    return _replicate("size", 0, replicate, master_seed=master_seed,
                      generation_stream=STREAM_IDS["size_generation"], analysis_stream=STREAM_IDS["size_null"],
                      kappa=1., B=B, fixed_onsets=None, engine=engine, check_agreement=check_agreement,
                      retain_fits=retain_fits)


def power_replicate(cell, replicate, *, master_seed, B=SURROGATE_ATTEMPTS, kappas=KAPPAS, engine="batched",
                    check_agreement=True, retain_fits=None, allow_registered=False):
    """AT-16 analogue replicate: stream 5330 generation, 5331 fixed-onset re-estimated surrogates.

    retain_fits=None applies the S7 setting (X3_RETENTION) for the master seed.
    """
    master_seed = c.check_seed(master_seed, allow_registered)
    retain_fits = default_retention(master_seed) if retain_fits is None else bool(retain_fits)
    return _replicate(f"power_{cell}", cell, replicate, master_seed=master_seed,
                      generation_stream=STREAM_IDS["power_generation"], analysis_stream=STREAM_IDS["power_null"],
                      kappa=kappas[cell], B=B, fixed_onsets=POWER_ONSETS, engine=engine,
                      check_agreement=check_agreement, retain_fits=retain_fits)


def x3_input(check, cell, replicate, *, master_seed, kappas=KAPPAS, allow_registered=False):
    """The generated series of one X.3 replicate, rebuilt from its seed coordinates alone (resume checks)."""
    master_seed = c.check_seed(master_seed, allow_registered)
    if check == "size" and cell == 0:
        return h1_design_series(c.stream_rng(master_seed, STREAM_IDS["size_generation"], 0, replicate), kappa=1.)
    if check == "power":
        return h1_design_series(c.stream_rng(master_seed, STREAM_IDS["power_generation"], cell, replicate),
                                kappa=kappas[cell])
    raise ValueError("Unknown X.3 check or cell")


def x3_settings(*, master_seed=None, engine="batched", check_agreement=True, retain_fits=None, **_):
    """The run-time settings of the E3 X.3 replicates, recorded in every manifest and record: the grid
    engine, the per-series agreement test, the S6 reading and the S7 retention."""
    if retain_fits is None:
        retain_fits = default_retention(master_seed)
    return dict(engine=engine, check_agreement=bool(check_agreement), grid_point_failure=GRID_POINT_FAILURE,
                retention="all_fits" if retain_fits else "base_fits")


def x3_arguments(settings):
    """The size_replicate/power_replicate keyword arguments that realise x3_settings(...) (the S6 reading
    is the module setting GRID_POINT_FAILURE, which the record checks)."""
    if settings["grid_point_failure"] != GRID_POINT_FAILURE:
        raise ValueError("The S6 reading is the module setting GRID_POINT_FAILURE")
    return dict(engine=settings["engine"], check_agreement=settings["check_agreement"],
                retain_fits=settings["retention"] == "all_fits")


def _registered(master_seed, n_series, B, kappas=KAPPAS):
    return master_seed == MASTER_SEED and n_series == SERIES_PER_CELL and B == SURROGATE_ATTEMPTS and tuple(kappas) == KAPPAS


def run_size_check(*, master_seed=c.DEVELOPMENT_MASTER_SEED, n_series=SERIES_PER_CELL, B=SURROGATE_ATTEMPTS,
                   replicates=None, engine="batched", check_agreement=True, retain_fits=None,
                   allow_registered=False, progress=None):
    master_seed = c.check_seed(master_seed, allow_registered)
    n_series = s._integer(n_series, "n_series")
    records = []
    for replicate in (range(n_series) if replicates is None else replicates):
        records.append(size_replicate(replicate, master_seed=master_seed, B=B, engine=engine,
                                      check_agreement=check_agreement, retain_fits=retain_fits,
                                      allow_registered=allow_registered))
        if progress:
            progress(records[-1])
    summary = (c.summarize_size(records, requested=n_series, bounds=SIZE_BOUNDS,
                                registered=_registered(master_seed, n_series, B))
               if replicates is None else None)
    return dict(master_seed=master_seed, n_series=n_series, B=B, engine=engine, records=records, summary=summary)


def run_power_check(*, master_seed=c.DEVELOPMENT_MASTER_SEED, n_series=SERIES_PER_CELL, B=SURROGATE_ATTEMPTS,
                    kappas=KAPPAS, cells=None, replicates=None, engine="batched", check_agreement=True,
                    retain_fits=None, allow_registered=False, progress=None):
    master_seed = c.check_seed(master_seed, allow_registered)
    n_series = s._integer(n_series, "n_series")
    kappas = tuple(float(k) for k in kappas)
    records = []
    for cell in (range(len(kappas)) if cells is None else cells):
        for replicate in (range(n_series) if replicates is None else replicates):
            records.append(power_replicate(cell, replicate, master_seed=master_seed, B=B, kappas=kappas,
                                           engine=engine, check_agreement=check_agreement,
                                           retain_fits=retain_fits, allow_registered=allow_registered))
            if progress:
                progress(records[-1])
    summary = None
    if cells is None and replicates is None:
        cell_summaries = [c.summarize_cell([r for r in records if r["cell_index"] == i], n_series)
                          for i in range(len(kappas))]
        summary = c.summarize_power_cells(cell_summaries, kappas,
                                          registered=_registered(master_seed, n_series, B, kappas))
    return dict(master_seed=master_seed, n_series=n_series, B=B, kappas=kappas, engine=engine,
                records=records, summary=summary)
