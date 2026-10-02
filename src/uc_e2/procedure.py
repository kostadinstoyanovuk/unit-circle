"""E2 sections 7 to 10: episodes of g, the statistic S, the fitted VAR(2) null and the surrogate comparisons.

Episodes, pre-onset changes, eligibility, p-values and the Kendall and lag-one statistics are the registered
uc_core functions, imported unchanged; the control flow is that of uc_core.surrogate and uc_core.h1 with the
VAR statistic and null, so that with k = 1 it reproduces H1's procedure.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import math

import numpy as np

from uc_core import surrogate as s
from uc_core.h1 import JointComparison, Observation, _comparison, _failed, _observation
from uc_core.recession import PreOnsetResult, episodes, pre_onset_changes
from uc_core.secondary import mean_pre_onset_trend, rolling_lag1, signed_pre_onset_changes
from uc_ext import common as c

from .constants import LOOKBACK, MERGE, MINIMUM_RUN, TREND_SPAN, WINDOW
from .var import _observations, _window, fit_var2, max_modulus


# ---------------------------------------------------------------- sections 7-8: episodes and statistic

def onsets_of(values):
    """Section 7: merged negative-growth episodes of g (the first variable), H1's rules unchanged."""
    x = _observations(values)
    return tuple(e.onset for e in episodes(x[:, 0], minimum_run=MINIMUM_RUN, merge=MERGE))


def statistic(values, *, window=WINDOW, fixed_onsets=None) -> PreOnsetResult:
    """S over eligible episodes of g (or supplied fixed onsets); mirrors uc_core.surrogate._statistic."""
    window = _window(window)
    x = _observations(values)
    onsets = onsets_of(x) if fixed_onsets is None else tuple(fixed_onsets)
    if not any(t >= window + LOOKBACK for t in onsets):          # the first M is at W - 1
        return PreOnsetResult(None, (), (), onsets)
    return pre_onset_changes(max_modulus(x, window), onsets, lookback=LOOKBACK)


# ------------------------------------------------------------------- section 9: fitted null and draws

@dataclass(frozen=True)
class VARNullModel:
    intercept: tuple[float, ...]
    coefficients: tuple[tuple[tuple[float, ...], ...], ...]
    initial: tuple[tuple[float, ...], ...]                        # X[0], X[1]
    residuals: tuple[tuple[float, ...], ...]                      # centred, (n - 2) x k
    residual_mean_removed: tuple[float, ...]
    modulus: float


def prepare_null(values) -> VARNullModel:
    """Section 9: the full-sample VAR(2); strictly stable (finite spectral radius < 1) or NullModelError.

    R4: stability is judged by the companion spectral radius from numpy.linalg.eigvals alone (the section 9
    wording); no projection. Residual vectors are centred column by column and not standardised.
    """
    x = _observations(values)
    try:
        fit = fit_var2(x)
    except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise s.NullModelError(f"Full-sample null fit failed: {error}") from error
    if not math.isfinite(fit.modulus) or not fit.modulus < 1:
        raise s.NullModelError("Full-sample null must be strictly stable; coefficients were not projected")
    residuals = np.asarray(fit.residuals, dtype=float)
    mean = residuals.mean(axis=0)
    residuals = residuals - mean
    return VARNullModel(fit.intercept, fit.coefficients, (tuple(map(float, x[0])), tuple(map(float, x[1]))),
                        tuple(map(tuple, residuals.tolist())), tuple(map(float, mean)), fit.modulus)


def simulate_var2(intercept, coefficients, initial, innovations) -> np.ndarray:
    """Generate len(innovations) + 2 vectors from exactly the supplied X[0], X[1]; in-order recursion.

    X[t] = c + A1 X[t-1] + A2 X[t-2] + e[t]; with k = 1 the arithmetic is uc_core.surrogate.simulate_ar2's.
    """
    innovations = _observations(innovations)
    k = innovations.shape[1]
    c_vector = np.asarray(intercept, dtype=float).reshape(k)
    a1, a2 = (np.asarray(m, dtype=float).reshape(k, k) for m in coefficients)
    start = np.asarray(initial, dtype=float).reshape(2, k)
    if not (np.isfinite(c_vector).all() and np.isfinite(a1).all() and np.isfinite(a2).all()
            and np.isfinite(start).all()):
        raise ValueError("Generating parameters and initial values must be finite")
    x = np.empty((len(innovations) + 2, k))
    x[:2] = start
    with np.errstate(over="raise", invalid="raise"):
        for position, noise in enumerate(innovations, start=2):
            x[position] = c_vector + a1 @ x[position - 1] + a2 @ x[position - 2] + noise
    if not np.isfinite(x).all():
        raise FloatingPointError("Non-finite generated series")
    return x


def draw_surrogate(model: VARNullModel, rng: np.random.Generator, *, kind="residual") -> np.ndarray:
    """One surrogate path: joint residual-vector resampling (one integers(0, n, size=n) call) or wild signs
    (one integers(0, 2, size=n) call, 0 -> -1 and 1 -> +1, one sign per residual vector)."""
    s._generator(rng)
    residuals = np.asarray(model.residuals, dtype=float)
    if kind == "residual":
        innovations = residuals[rng.integers(0, len(residuals), size=len(residuals))]
    elif kind == "wild":
        signs = 2 * rng.integers(0, 2, size=len(residuals)) - 1
        innovations = residuals * signs[:, None]
    else:
        raise ValueError("kind must be 'residual' or 'wild'")
    return simulate_var2(model.intercept, model.coefficients, model.initial, innovations)


def csd_test(values, *, B, rng, window=WINDOW, onset_mode="endogenous", innovation_mode="residual"):
    """uc_core.surrogate.csd_test with the VAR statistic and null (section 9; the section 10 sensitivities).

    Exactly B attempts; only draws without an eligible episode are dropped; failures invalidate p.
    onset_mode='fixed' reuses the observed eligible onsets in every surrogate (stream 5203 analysis).
    """
    B = s._integer(B, "B")
    window = _window(window)
    s._generator(rng)
    if onset_mode not in ("endogenous", "fixed") or innovation_mode not in ("residual", "wild"):
        raise ValueError("Unsupported onset or innovation mode")
    x = _observations(values)
    before = deepcopy(rng.bit_generator.state)
    observed = statistic(x, window=window)
    if observed.mean_change is None:
        return s.Comparison("observed_not_estimable", observed, None, B, 0, 0, 0, 0, None, None, (), None,
                            window, LOOKBACK, MERGE, onset_mode, innovation_mode, before,
                            deepcopy(rng.bit_generator.state))
    model = prepare_null(x)
    fixed = observed.eligible_onsets if onset_mode == "fixed" else None
    records = []
    for number in range(B):
        try:
            simulated = draw_surrogate(model, rng, kind=innovation_mode)
            result = statistic(simulated, window=window, fixed_onsets=fixed)
            if result.mean_change is None:
                records.append(s.Attempt(number, "no_eligible_episode", None))
            else:
                if not math.isfinite(result.mean_change):
                    raise FloatingPointError("Non-finite surrogate statistic")
                records.append(s.Attempt(number, "retained", result.mean_change,
                                         result.eligible_onsets, result.changes))
        except c.NUMERIC_ERRORS as error:
            records.append(s.Attempt(number, "failed", None, error=f"{type(error).__name__}: {error}"))
    kept = [r.statistic for r in records if r.status == "retained"]
    empty = sum(r.status == "no_eligible_episode" for r in records)
    failed = sum(r.status == "failed" for r in records)
    p = None if failed else s.monte_carlo_pvalue(observed.mean_change, kept)
    status = "invalid_surrogate_failure" if failed else ("no_retained_surrogates" if not kept else "ok")
    exceedances = sum(v >= observed.mean_change for v in kept) if kept else None
    return s.Comparison(status, observed, p, B, len(records), len(kept), empty, failed, exceedances,
                        1 / (len(kept) + 1) if kept else None, tuple(records), model, window, LOOKBACK, MERGE,
                        onset_mode, innovation_mode, before, deepcopy(rng.bit_generator.state))


def _measure(values, window=WINDOW):
    """uc_core.h1._measure with the VAR modulus; episodes and the lag-one statistic use g (column 0)."""
    x = _observations(values)
    growth = x[:, 0]
    onsets = onsets_of(x)
    output = {name: Observation("no_eligible_episode", None, ineligible_onsets=onsets)
              for name in ("primary", "trend", "lag1")}
    primary_eligible = any(t >= window + LOOKBACK for t in onsets)
    trend_eligible = any(t >= window + TREND_SPAN - 1 for t in onsets)
    modulus, modulus_error = None, None
    if primary_eligible or trend_eligible:
        try:
            modulus = max_modulus(x, window)
        except c.NUMERIC_ERRORS as error:
            modulus_error = error
    for name, eligible in (("primary", primary_eligible), ("trend", trend_eligible)):
        if not eligible:
            continue
        if modulus_error is not None:
            output[name] = _failed(modulus_error)
            continue
        try:
            result = (mean_pre_onset_trend(modulus, onsets, span=TREND_SPAN) if name == "trend"
                      else pre_onset_changes(modulus, onsets, lookback=LOOKBACK))
            output[name] = _observation(result, trend=name == "trend")
        except c.NUMERIC_ERRORS as error:
            output[name] = _failed(error)
    if primary_eligible:
        try:
            output["lag1"] = _observation(signed_pre_onset_changes(
                rolling_lag1(growth, window), onsets, lookback=LOOKBACK))
        except c.NUMERIC_ERRORS as error:
            output["lag1"] = _failed(error)
    return output


def primary_with_comparators(values, *, B, rng, window=WINDOW):
    """Stream 5200 design: one set of VAR paths for the primary, Kendall and lag-one comparisons (section 10).

    Same control flow as uc_core.h1.primary_with_comparators; with k = 1 it reproduces it. The lag-one
    comparator uses the first component (g) of each path.
    """
    B = s._integer(B, "B")
    window = _window(window)
    s._generator(rng)
    x = _observations(values)
    before = deepcopy(rng.bit_generator.state)
    observed = _measure(x, window)
    model, null_error = None, None
    records = {name: [] for name in observed}
    generated = 0
    if any(o.status == "ok" for o in observed.values()):
        try:
            model = prepare_null(x)
        except s.NullModelError as error:
            null_error = str(error)
    if model is not None:
        for number in range(B):
            generated += 1
            try:
                path = draw_surrogate(model, rng)
                measures = _measure(path, window)
            except c.NUMERIC_ERRORS as error:
                measures = {name: _failed(error) for name in observed}
            for name in observed:
                if observed[name].status != "ok":
                    continue
                value = measures[name]
                records[name].append(s.Attempt(number, "retained" if value.status == "ok" else value.status,
                                               value.value, value.eligible_onsets, value.components, value.error))
    comparisons = {name: _comparison(name, observed[name], records[name], B) for name in observed}
    if null_error:
        comparisons = {name: replace(result, status="null_model_failed") if observed[name].status == "ok"
                       else result for name, result in comparisons.items()}
    return JointComparison(**comparisons, null_model=model, rng_before=before,
                           rng_after=deepcopy(rng.bit_generator.state), generated_attempts=generated,
                           null_error=null_error)


def fixed_date_test(values, onsets, *, B, rng, window=WINDOW):
    """uc_core.h1.fixed_date_test with the VAR statistic: external dates, no run detection (section 11 power)."""
    B = s._integer(B, "B")
    window = _window(window)
    s._generator(rng)
    x = _observations(values)
    before = deepcopy(rng.bit_generator.state)
    # This also validates supplied dates even when the series is too short to fit.
    dates = signed_pre_onset_changes(np.full(len(x), np.nan), onsets, lookback=LOOKBACK).ineligible_onsets
    observed = statistic(x, window=window, fixed_onsets=dates)
    if observed.mean_change is None:
        return s.Comparison("observed_not_estimable", observed, None, B, 0, 0, 0, 0, None, None, (), None,
                            window, LOOKBACK, MERGE, "external_fixed", "residual", before,
                            deepcopy(rng.bit_generator.state))
    model = prepare_null(x)
    records = []
    for number in range(B):
        try:
            path = draw_surrogate(model, rng)
            result = statistic(path, window=window, fixed_onsets=observed.eligible_onsets)
            if result.mean_change is None or not math.isfinite(result.mean_change):
                raise FloatingPointError("Fixed dates lost their estimable statistic")
            records.append(s.Attempt(number, "retained", result.mean_change, result.eligible_onsets, result.changes))
        except c.NUMERIC_ERRORS as error:
            records.append(s.Attempt(number, "failed", None, error=f"{type(error).__name__}: {error}"))
    comparison = _comparison("primary", _observation(observed), records, B)
    return s.Comparison(comparison.status, observed, comparison.p_value, B, B, comparison.retained,
                        comparison.no_episode, comparison.failed, comparison.exceedances, comparison.p_grid_spacing,
                        tuple(records), model, window, LOOKBACK, MERGE, "external_fixed", "residual", before,
                        deepcopy(rng.bit_generator.state))
