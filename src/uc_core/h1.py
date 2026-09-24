"""H1 methods assembled without data acquisition or registration side effects."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import math
import numpy as np

from . import surrogate as s
from .constants import SURROGATE_ATTEMPTS, EPISODE_RESAMPLES, analysis_rng
from .recession import episodes, pre_onset_changes
from .rolling import _observations_and_index, max_modulus
from .secondary import rolling_lag1, signed_pre_onset_changes, mean_pre_onset_trend, episode_percentile_interval


@dataclass(frozen=True)
class Observation:
    status: str
    value: float | None
    components: tuple[float, ...] = ()
    eligible_onsets: tuple[int, ...] = ()
    ineligible_onsets: tuple[int, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class MetricComparison:
    name: str
    status: str
    observed: Observation
    p_value: float | None
    requested: int
    attempted: int
    retained: int
    no_episode: int
    failed: int
    exceedances: int | None
    p_grid_spacing: float | None
    attempts: tuple[s.Attempt, ...]


@dataclass(frozen=True)
class JointComparison:
    primary: MetricComparison
    trend: MetricComparison
    lag1: MetricComparison
    null_model: s.NullModel | None
    rng_before: dict
    rng_after: dict
    generated_attempts: int
    null_error: str | None = None


def _observation(result, trend=False):
    value = result.mean_trend if trend else result.mean_change
    components = result.trends if trend else result.changes
    if value is not None and not math.isfinite(value):
        raise FloatingPointError("Non-finite statistic")
    return Observation("ok" if value is not None else "no_eligible_episode", value,
                       components, result.eligible_onsets, result.ineligible_onsets)


def _failed(error):
    return Observation("failed", None, error=f"{type(error).__name__}: {error}")


def _measure(values, *, window, lookback, merge, span):
    onsets = tuple(e.onset for e in episodes(values, merge=merge))
    output = {name: Observation("no_eligible_episode", None, ineligible_onsets=onsets)
              for name in ("primary", "trend", "lag1")}
    primary_eligible = any(t >= window + lookback for t in onsets)
    trend_eligible = any(t >= window + span - 1 for t in onsets)
    modulus, modulus_error = None, None
    if primary_eligible or trend_eligible:
        try:
            modulus = max_modulus(values, window)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
            modulus_error = error
    for name, eligible in (("primary", primary_eligible), ("trend", trend_eligible)):
        if not eligible:
            continue
        if modulus_error is not None:
            output[name] = _failed(modulus_error)
            continue
        try:
            result = (mean_pre_onset_trend(modulus, onsets, span=span) if name == "trend"
                      else pre_onset_changes(modulus, onsets, lookback=lookback))
            output[name] = _observation(result, trend=name == "trend")
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
            output[name] = _failed(error)
    if primary_eligible:
        try:
            output["lag1"] = _observation(signed_pre_onset_changes(
                rolling_lag1(values, window), onsets, lookback=lookback))
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
            output["lag1"] = _failed(error)
    return output


def _comparison(name, observed, records, requested):
    if observed.status != "ok":
        return MetricComparison(name, "observed_not_estimable" if observed.status == "no_eligible_episode"
                                else "observed_statistic_failed", observed, None, requested,
                                0, 0, 0, 0, None, None, ())
    kept = [r.statistic for r in records if r.status == "retained"]
    failed = sum(r.status == "failed" for r in records)
    empty = sum(r.status == "no_eligible_episode" for r in records)
    status = "invalid_surrogate_failure" if failed else ("ok" if kept else "no_retained_surrogates")
    return MetricComparison(name, status, observed,
                            None if failed else s.monte_carlo_pvalue(observed.value, kept),
                            requested, len(records), len(kept), empty, failed,
                            sum(v >= observed.value for v in kept) if kept else None,
                            1/(len(kept)+1) if kept else None, tuple(records))


def primary_with_comparators(values, *, B, rng, window=40, lookback=8, merge=8, trend_span=16):
    """One set of primary residual paths; three separate retention denominators."""
    B = s._integer(B, "B")
    window = s._integer(window, "window", 5)
    lookback = s._integer(lookback, "lookback")
    merge = s._integer(merge, "merge", 0)
    trend_span = s._integer(trend_span, "trend_span", 2)
    s._generator(rng)
    x, _ = _observations_and_index(values)
    before = deepcopy(rng.bit_generator.state)
    observed = _measure(x, window=window, lookback=lookback, merge=merge, span=trend_span)
    model = None
    null_error = None
    records = {name: [] for name in observed}
    generated = 0
    if any(o.status == "ok" for o in observed.values()):
        try:
            model = s.prepare_null(x)
        except s.NullModelError as error:
            null_error = str(error)
    if model is not None:
        for number in range(B):
            generated += 1
            try:
                path = s.draw_surrogate(model, rng)
                measures = _measure(path, window=window, lookback=lookback, merge=merge, span=trend_span)
            except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
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


def fixed_date_test(values, onsets, *, B, rng, window=40, lookback=8):
    """Explicit external dates for the registered power proxy; no run detection."""
    B = s._integer(B, "B")
    window = s._integer(window, "window", 5)
    lookback = s._integer(lookback, "lookback")
    s._generator(rng)
    x, _ = _observations_and_index(values)
    before = deepcopy(rng.bit_generator.state)
    # This also validates supplied dates even when the series is too short to fit.
    from .secondary import signed_pre_onset_changes
    checked = signed_pre_onset_changes(np.full(len(x), np.nan), onsets, lookback=lookback)
    dates = checked.ineligible_onsets
    observed = s._statistic(x, window=window, lookback=lookback, merge=8, fixed_onsets=dates)
    if observed.mean_change is None:
        return s.Comparison("observed_not_estimable", observed, None, B, 0, 0, 0, 0,
                            None, None, (), None, window, lookback, 8, "external_fixed", "residual",
                            before, deepcopy(rng.bit_generator.state))
    model = s.prepare_null(x)
    records = []
    for number in range(B):
        try:
            path = s.draw_surrogate(model, rng)
            result = s._statistic(path, window=window, lookback=lookback, merge=8,
                                  fixed_onsets=observed.eligible_onsets)
            if result.mean_change is None or not math.isfinite(result.mean_change):
                raise FloatingPointError("Fixed dates lost their estimable statistic")
            records.append(s.Attempt(number, "retained", result.mean_change,
                                     result.eligible_onsets, result.changes))
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
            records.append(s.Attempt(number, "failed", None, error=f"{type(error).__name__}: {error}"))
    comparison = _comparison("primary", _observation(observed), records, B)
    return s.Comparison(comparison.status, observed, comparison.p_value, B, B,
                        comparison.retained, comparison.no_episode, comparison.failed,
                        comparison.exceedances, comparison.p_grid_spacing, tuple(records), model,
                        window, lookback, 8, "external_fixed", "residual", before,
                        deepcopy(rng.bit_generator.state))


def analyze_h1(values, *, B=SURROGATE_ATTEMPTS, interval_B=EPISODE_RESAMPLES):
    """In-memory protocol assembly. Registration/data gates belong to the runner."""
    B = s._integer(B, "B")
    interval_B = s._integer(interval_B, "interval_B")
    joint = primary_with_comparators(values, B=B, rng=analysis_rng("primary"))
    def sensitivity(name, **kwargs):
        try:
            return s.csd_test(values, B=B, rng=analysis_rng(name), **kwargs)
        except s.NullModelError as error:
            observed = s._statistic(values, window=kwargs.get("window",40), lookback=8, merge=8)
            return {"status":"null_model_failed", "p_value":None, "observed":observed,
                    "requested":B, "attempted":0, "error":str(error)}
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
            return {"status": "observed_statistic_failed", "p_value": None,
                    "requested":B, "attempted":0,
                    "error": f"{type(error).__name__}: {error}"}
    return {
        "joint": joint,
        "window32": sensitivity("window32", window=32),
        "window48": sensitivity("window48", window=48),
        "fixed": sensitivity("fixed", onset_mode="fixed"),
        "wild": sensitivity("wild", innovation_mode="wild"),
        "episode_interval": ({"status":"observed_statistic_failed", "interval":None,
                              "error":joint.primary.observed.error}
                             if joint.primary.observed.status == "failed" else
                             episode_percentile_interval(joint.primary.observed.components,
                                                         B=interval_B, rng=analysis_rng("interval"))),
    }
