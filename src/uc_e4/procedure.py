"""E4 sections 8 and 9 (with the shared paths of section 10): the fixed-date per-vintage comparison.

Each episode j is a vintage series of n_v growth values. The observed statistic is
Delta_rt[j] = M_v(n_v - 1) - M_v(n_v - 9) and S_rt is the mean over the episodes given. The null of each
episode is fitted to its own series (uc_core.surrogate.prepare_null: intercept-inclusive OLS, strict
stability, centred residuals) and draws come from the episode's own generator. Rolling fits, the modulus,
the lag-one path and Kendall's tau-b are the uc_core functions, called as H1 calls them; the onset of an
episode is position n_v, one past the last position, so the paths are padded by one throwaway value
that no registered function reads (tested), which lets the registered functions be reused unchanged.

Nothing here reads a file. The seed, the streams, B and the window are arguments.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math

import numpy as np

from uc_core import surrogate as s
from uc_core.recession import pre_onset_changes
from uc_core.rolling import max_modulus
from uc_core.secondary import mean_pre_onset_trend, rolling_lag1, signed_pre_onset_changes
from uc_core.validation_design import wilson_interval

LOOKBACK = 8
TREND_SPAN = 16
NUMERIC_ERRORS = (ValueError, FloatingPointError, np.linalg.LinAlgError)
RAW_P_LABEL = "raw, not family-adjusted"


@dataclass(frozen=True)
class EpisodeInput:
    """One E4-eligible episode: its index j (never renumbered) and its vintage growth series."""
    j: int
    growth: np.ndarray


@dataclass(frozen=True)
class Observed:
    """Observed statistic of one comparison. `components` are the per-episode Delta (or tau-b, or lag-one
    change) in the order of `eligible_onsets`, which holds the episode indices j (E4's onsets are per vintage)."""
    status: str                      # 'ok', 'no_eligible_episode' or 'failed'
    value: float | None
    components: tuple = ()
    eligible_onsets: tuple = ()
    ineligible_onsets: tuple = ()
    error: str | None = None

    @property
    def mean_change(self):
        return self.value


@dataclass(frozen=True)
class MetricComparison:
    name: str
    status: str                      # ok, observed_not_estimable, observed_statistic_failed, null_model_failed,
    observed: Observed               # invalid_surrogate_failure, no_retained_surrogates
    p_value: float | None
    requested: int
    attempted: int
    retained: int
    no_episode: int
    failed: int
    exceedances: int | None
    p_grid_spacing: float | None
    q: float | None
    q_wilson: tuple | None
    attempts: tuple
    p_label: str = RAW_P_LABEL


@dataclass(frozen=True)
class JointComparison:
    window: int
    kind: str
    primary: MetricComparison
    trend: MetricComparison | None
    lag1: MetricComparison | None
    null_models: dict                # j -> uc_core NullModel
    null_error: str | None
    rng_before: dict                 # j -> bit generator state before any draw
    rng_after: dict
    generated_attempts: int


def _padded(values):
    values = np.asarray(values, dtype=float)
    return np.append(values, values[-1])


def _failed(error):
    return Observed("failed", None, error=f"{type(error).__name__}: {error}")


def measure(growth, *, window, comparators=False, lookback=LOOKBACK, span=TREND_SPAN):
    """Observed pieces of ONE vintage series: dict name -> ('ok', value) or ('failed', Observed) or
    ('ineligible', None), for 'primary' and, with comparators, 'trend' and 'lag1'.

    The rolling path is computed over every window of the series: a failed window, or a non-finite modulus at
    a position the statistic needs, is a failure of the statistic and never a dropped window (H1 sections 4-5).
    """
    growth = np.asarray(growth, dtype=float)
    n_v = len(growth)
    onset = [n_v]
    out = {}
    try:
        modulus = max_modulus(growth, window).to_numpy()
        error = None
    except NUMERIC_ERRORS as exc:
        modulus, error = None, exc
    names = ("primary", "trend") if comparators else ("primary",)
    for name in names:
        if error is not None:
            out[name] = ("failed", _failed(error))
            continue
        try:
            if name == "primary":
                result = pre_onset_changes(_padded(modulus), onset, lookback=lookback)
                value, eligible = result.mean_change, bool(result.eligible_onsets)
            else:
                result = mean_pre_onset_trend(_padded(modulus), onset, span=span)
                value, eligible = result.mean_trend, bool(result.eligible_onsets)
            if not eligible:
                out[name] = ("ineligible", None)
            elif not math.isfinite(value):
                raise FloatingPointError("Non-finite statistic")
            else:
                out[name] = ("ok", float(value))
        except NUMERIC_ERRORS as exc:
            out[name] = ("failed", _failed(exc))
    if comparators:
        try:
            path = rolling_lag1(growth, window).to_numpy()
            result = signed_pre_onset_changes(_padded(path), onset, lookback=lookback)
            if not result.eligible_onsets:
                out["lag1"] = ("ineligible", None)
            elif not math.isfinite(result.mean_change):
                raise FloatingPointError("Non-finite statistic")
            else:
                out["lag1"] = ("ok", float(result.mean_change))
        except NUMERIC_ERRORS as exc:
            out["lag1"] = ("failed", _failed(exc))
    return out


def _aggregate(name, per_episode, episodes):
    """Observed statistic of one comparison from the per-episode pieces (mean over the episodes, in j order)."""
    ok = [(e.j, v[1]) for e, v in zip(episodes, per_episode) if v[0] == "ok"]
    failed = [(e.j, v[1]) for e, v in zip(episodes, per_episode) if v[0] == "failed"]
    ineligible = tuple(e.j for e, v in zip(episodes, per_episode) if v[0] == "ineligible")
    if failed:
        j, obs = failed[0]
        return Observed("failed", None, ineligible_onsets=ineligible, error=f"episode {j}: {obs.error}")
    if not ok:
        return Observed("no_eligible_episode", None, ineligible_onsets=ineligible)
    values = [v for _, v in ok]
    return Observed("ok", float(np.mean(values)), tuple(values), tuple(j for j, _ in ok), ineligible)


def _metric(name, observed, records, requested):
    if observed.status != "ok":
        status = "observed_not_estimable" if observed.status == "no_eligible_episode" else "observed_statistic_failed"
        return MetricComparison(name, status, observed, None, requested, 0, 0, 0, 0, None, None, None, None, ())
    kept = [r.statistic for r in records if r.status == "retained"]
    failed = sum(r.status == "failed" for r in records)
    empty = sum(r.status == "no_eligible_episode" for r in records)
    status = "invalid_surrogate_failure" if failed else ("ok" if kept else "no_retained_surrogates")
    exceed = sum(v >= observed.value for v in kept) if kept else None
    return MetricComparison(
        name, status, observed, None if failed else s.monte_carlo_pvalue(observed.value, kept), requested,
        len(records), len(kept), empty, failed, exceed, 1 / (len(kept) + 1) if kept else None,
        exceed / len(kept) if kept else None, wilson_interval(exceed, len(kept)) if kept else None, tuple(records))


def _null_failed(metric, message):
    if metric is None or metric.observed.status != "ok":
        return metric
    from dataclasses import replace
    return replace(metric, status="null_model_failed")


def compare(episodes, rngs, *, window=40, B, kind="residual", comparators=False,
            lookback=LOOKBACK, span=TREND_SPAN) -> JointComparison:
    """Sections 8-9 for the episodes given (E4-eligible, in j order); `rngs` maps j -> that episode's Generator.

    Attempt b draws, for every episode j in order, one integers call of size n_v - 2 (or the wild-sign call)
    from rngs[j] before its recursion, so a failure in one episode neither shifts its own later draws nor any
    other episode's. S_b is the mean of the episodes' Delta_b; a failure in any episode invalidates the
    attempt, and any failed attempt invalidates p (H1 section 6). With comparators=True the same paths also
    supply Kendall's tau-b (episodes with n_v >= window + 15) and the lag-one comparator, each with its own
    accounting (H1 section 7). A null that fails for any episode fails the comparison before any draw.
    """
    B = s._integer(B, "B")
    window = s._integer(window, "window", 5)
    if kind not in ("residual", "wild"):
        raise ValueError("kind must be 'residual' or 'wild'")
    episodes = tuple(episodes)
    if [e.j for e in episodes] != sorted({e.j for e in episodes}):
        raise ValueError("episodes must be given once each, in increasing j")
    for e in episodes:
        if len(e.growth) < window + lookback:
            raise ValueError(f"episode {e.j}: n_v = {len(e.growth)} is below the eligibility threshold "
                             f"{window + lookback}; only E4-eligible episodes are compared")
        if e.j not in rngs or not isinstance(rngs[e.j], np.random.Generator):
            raise ValueError(f"episode {e.j} needs its own numpy Generator")
    before = {e.j: deepcopy(rngs[e.j].bit_generator.state) for e in episodes}
    names = ("primary", "trend", "lag1") if comparators else ("primary",)
    per_episode = [measure(e.growth, window=window, comparators=comparators, lookback=lookback, span=span)
                   for e in episodes]
    observed = {n: _aggregate(n, [p[n] for p in per_episode], episodes) for n in names}
    records = {n: [] for n in names}
    models, null_error, generated = {}, None, 0
    if episodes and any(o.status == "ok" for o in observed.values()):
        try:
            models = {e.j: s.prepare_null(e.growth) for e in episodes}
        except s.NullModelError as error:
            models, null_error = {}, str(error)
    if models:
        for number in range(B):
            generated += 1
            drawn, generation_error = {}, None
            for e in episodes:                       # every episode consumes its own draws whatever happens elsewhere
                try:
                    drawn[e.j] = s.draw_surrogate(models[e.j], rngs[e.j], kind=kind)
                except NUMERIC_ERRORS as error:
                    generation_error = generation_error or error
            pieces = {}
            if generation_error is None:
                pieces = {e.j: measure(drawn[e.j], window=window, comparators=comparators,
                                       lookback=lookback, span=span) for e in episodes}
            for n in names:
                if observed[n].status != "ok":
                    continue
                if generation_error is not None:
                    records[n].append(s.Attempt(number, "failed", None,
                                                error=f"{type(generation_error).__name__}: {generation_error}"))
                    continue
                parts = [pieces[e.j][n] for e in episodes]
                agg = _aggregate(n, parts, episodes)
                # every attempt is structurally eligible: the observed eligible episodes are eligible here too
                if agg.status == "ok" and set(agg.eligible_onsets) == set(observed[n].eligible_onsets):
                    records[n].append(s.Attempt(number, "retained", agg.value, agg.eligible_onsets, agg.components))
                elif agg.status == "failed":
                    records[n].append(s.Attempt(number, "failed", None, error=agg.error))
                else:
                    records[n].append(s.Attempt(number, "failed", None,
                                                error="surrogate eligibility differs from the observed eligibility"))
    metrics = {n: _metric(n, observed[n], records[n], B) for n in names}
    if null_error:
        metrics = {n: _null_failed(m, null_error) for n, m in metrics.items()}
    return JointComparison(window, kind, metrics["primary"], metrics.get("trend"), metrics.get("lag1"), models,
                           null_error, before, {e.j: deepcopy(rngs[e.j].bit_generator.state) for e in episodes},
                           generated)
