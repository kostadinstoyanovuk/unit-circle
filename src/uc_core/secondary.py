"""Fixed secondary statistics and the conditional episode diagnostic interval."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

from .ar import _real_vector
from .recession import PreOnsetResult
from .rolling import RollingFitError, _observations_and_index, _validate_index


class SecondaryStatisticError(ValueError):
    """An eligible secondary statistic is undefined; its episode is not dropped."""


@dataclass(frozen=True)
class TrendResult:
    mean_trend: float | None
    trends: tuple[float, ...]
    eligible_onsets: tuple[int, ...]
    ineligible_onsets: tuple[int, ...]


@dataclass(frozen=True)
class EpisodeInterval:
    status: str
    interval: tuple[float, float] | None
    requested: int
    attempted: int
    episode_count: int
    draw_means: tuple[float, ...]
    rng_before: dict
    rng_after: dict


def _integer(value, name, minimum=1):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _path_and_onsets(path, onsets, *, nonnegative=False):
    if isinstance(path, pd.Series):
        _validate_index(path.index)
    values = np.asarray(path)
    if np.iscomplexobj(values):
        raise ValueError("Indicator must be real")
    try:
        values = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("Indicator must contain numeric real values") from error
    if values.ndim != 1 or np.isinf(values).any():
        raise ValueError("Indicator must be one-dimensional and finite after warm-up")
    if nonnegative and np.any(values[np.isfinite(values)] < 0):
        raise ValueError("Modulus must be nonnegative")
    available = np.flatnonzero(np.isfinite(values))
    if len(available) and not np.isfinite(values[available[0]:]).all():
        raise ValueError("Missing indicator inside fitted region; do not silently exclude episodes")
    try:
        supplied = list(onsets)
    except TypeError as error:
        raise ValueError("Onsets must be an iterable of integer positions") from error
    if any(isinstance(t, (bool, np.bool_)) or not isinstance(t, (int, np.integer)) for t in supplied):
        raise ValueError("Onsets must be integer positions")
    supplied = [int(t) for t in supplied]
    if any(t < 0 or t >= len(values) for t in supplied) or any(b <= a for a, b in zip(supplied, supplied[1:])):
        raise ValueError("Onsets must be unique, increasing positions inside the observed series")
    return values, supplied


def rolling_lag1(values, window: int = 40) -> pd.Series:
    """Demeaned sample ACF(1), with the full window's energy as denominator.

    Preserve the index and mark only the first window-1 observations as NaN.
    Negative correlations are valid. A constant or numerically invalid fitted
    window raises with its endpoint, matching rolling AR fit failure handling.
    """
    window = _integer(window, "window", 2)
    x, index = _observations_and_index(values)
    result = np.full(len(x), np.nan)
    for end in range(window - 1, len(x)):
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                segment = x[end - window + 1:end + 1]
                centered = segment - segment.mean()
                denominator = float(np.sum(centered * centered))
                if denominator == 0:
                    raise ValueError("Zero centered denominator: lag-one correlation is undefined")
                statistic = float(np.sum(centered[1:] * centered[:-1]) / denominator)
            if not math.isfinite(statistic):
                raise ValueError("Non-finite lag-one correlation")
            result[end] = statistic
        except (ValueError, FloatingPointError) as error:
            raise RollingFitError(f"Lag-one window ending at position {end}, label {index[end]!r}: {error}") from error
    return pd.Series(result, index=index, name="lag1")


def signed_pre_onset_changes(indicator, onsets, *, lookback: int = 8) -> PreOnsetResult:
    """Apply the primary change/eligibility rule to any real signed indicator.

    Delta=indicator[onset-1]-indicator[onset-lookback-1]. Only a contiguous
    leading NaN warm-up is accepted; negative inputs and changes are retained.
    Empty eligible sets return None, not zero.
    """
    lookback = _integer(lookback, "lookback")
    values, supplied = _path_and_onsets(indicator, onsets)
    eligible, ineligible, changes = [], [], []
    with np.errstate(over="raise", invalid="raise"):
        for onset in supplied:
            earlier = onset - lookback - 1
            if earlier < 0 or not np.isfinite(values[earlier]):
                ineligible.append(onset)
                continue
            eligible.append(onset)
            changes.append(float(values[onset - 1] - values[earlier]))
        mean = float(np.mean(changes)) if changes else None
    return PreOnsetResult(mean, tuple(changes), tuple(eligible), tuple(ineligible))


def mean_pre_onset_trend(modulus, onsets, *, span: int = 16) -> TrendResult:
    """Mean Kendall tau-b on positions 0,...,span-1 before eligible onsets.

    The fixed-contract default uses M[onset-16:onset]; with W=40 the first
    eligible onset is 55. An eligible constant segment fails the statistic,
    while an empty eligible set has mean_trend=None. No p-value is used here.
    """
    span = _integer(span, "span", 2)
    values, supplied = _path_and_onsets(modulus, onsets, nonnegative=True)
    eligible, ineligible, trends = [], [], []
    positions = np.arange(span)
    for onset in supplied:
        first = onset - span
        if first < 0 or not np.isfinite(values[first]):
            ineligible.append(onset)
            continue
        segment = values[first:onset]
        if np.all(segment == segment[0]):
            raise SecondaryStatisticError(f"Constant modulus segment before onset {onset}: Kendall tau-b is undefined")
        statistic = float(kendalltau(positions, segment, variant="b").statistic)
        if not math.isfinite(statistic):
            raise SecondaryStatisticError(f"Non-finite Kendall tau-b before onset {onset}")
        eligible.append(onset)
        trends.append(statistic)
    return TrendResult(float(np.mean(trends)) if trends else None,
                       tuple(trends), tuple(eligible), tuple(ineligible))


def episode_percentile_interval(changes, *, rng: np.random.Generator,
                                B: int = 10_000) -> EpisodeInterval:
    """Conditional 90% diagnostic interval from episode resampling.

    Draw exactly B sets of m indices in one integers(0,m,size=(B,m)) call.
    Use fixed 5th/95th percentiles and NumPy's linear quantile method. Empty
    input consumes no randomness; a single episode is explicitly flagged.
    This diagnostic carries no equivalence or calibrated absence claim.
    """
    B = _integer(B, "B")
    if not isinstance(rng, np.random.Generator):
        raise ValueError("Supply an explicit numpy.random.Generator")
    values = _real_vector(changes)
    before = deepcopy(rng.bit_generator.state)
    m = len(values)
    if m == 0:
        return EpisodeInterval("no_eligible_episode", None, B, 0, 0, (), before,
                               deepcopy(rng.bit_generator.state))
    indices = rng.integers(0, m, size=(B, m))
    with np.errstate(over="raise", invalid="raise"):
        means = values[indices].mean(axis=1)
        endpoints = np.quantile(means, [.05, .95], method="linear")
    if not np.isfinite(means).all() or not np.isfinite(endpoints).all():
        raise SecondaryStatisticError("Non-finite episode resampling result")
    return EpisodeInterval("single_episode" if m == 1 else "ok",
                           tuple(map(float, endpoints)), B, B, m,
                           tuple(map(float, means)), before,
                           deepcopy(rng.bit_generator.state))
