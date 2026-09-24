from copy import deepcopy
from dataclasses import FrozenInstanceError
import math

import numpy as np
import pandas as pd
import pytest
from statsmodels.tsa.stattools import acf

from uc_core.recession import PreOnsetResult, pre_onset_changes
from uc_core.rolling import RollingFitError
from uc_core.secondary import (
    SecondaryStatisticError, episode_percentile_interval, mean_pre_onset_trend,
    rolling_lag1, signed_pre_onset_changes,
)


def test_lag1_hand_calculation_and_negative_values():
    # Centered [1,-1,1,-1] has adjacent-product sum -3 and total energy 4.
    actual = rolling_lag1([2, 0, 2, 0], window=4)
    assert actual.iloc[:3].isna().all()
    assert actual.iloc[3] == -.75
    # A second window [0,2,0,4] centers at 1.5: numerator=-5.25, energy=11.
    assert rolling_lag1([2, 0, 2, 0, 4], window=4).iloc[4] == -5.25 / 11
    assert rolling_lag1([1, 2], window=2).iloc[-1] == -.5


def test_lag1_default_boundaries_index_and_established_acf():
    x = pd.Series(np.random.default_rng(12485).normal(size=65),
                  index=pd.period_range("2000Q1", periods=65, freq="Q"))
    result = rolling_lag1(x)
    assert result.name == "lag1"
    assert result.index.equals(x.index)
    assert result.iloc[:39].isna().all()
    assert result.iloc[39:].notna().all()
    for end in (39, 40, 64):
        expected = acf(x.iloc[end - 39:end + 1], nlags=1, adjusted=False, fft=False)[1]
        assert result.iloc[end] == pytest.approx(expected, abs=1e-15)
    pd.testing.assert_series_equal(rolling_lag1(x.iloc[:55]), result.iloc[:55])
    changed = x.copy()
    changed.iloc[55:] = 100
    pd.testing.assert_series_equal(rolling_lag1(changed).iloc[:55], result.iloc[:55])


def test_lag1_empty_short_and_constant_failure():
    assert rolling_lag1([]).empty
    assert rolling_lag1([1, 1]).isna().all()
    with pytest.raises(RollingFitError, match="position 39.*Zero centered denominator"):
        rolling_lag1(np.ones(40))


@pytest.mark.parametrize("window", [0, 1, True, np.bool_(True), 2.5])
def test_lag1_invalid_window(window):
    with pytest.raises(ValueError):
        rolling_lag1([1, 2, 3], window)


@pytest.mark.parametrize("values", [[1, np.nan], [1, np.inf], [1 + 0j, 2], [[1, 2]]])
def test_lag1_invalid_observations(values):
    with pytest.raises(ValueError):
        rolling_lag1(values)


def test_signed_change_first_eligibility_and_exact_endpoints():
    values = np.full(65, -.4)
    values[:39] = np.nan
    values[[39, 47, 49, 57]] = [-.6, -.2, -.1, -.8]
    result = signed_pre_onset_changes(values, [47, 48, 58])
    assert isinstance(result, PreOnsetResult)
    assert result.eligible_onsets == (48, 58)
    assert result.ineligible_onsets == (47,)
    np.testing.assert_allclose(result.changes, [.4, -.7], atol=1e-15)
    assert result.mean_change == pytest.approx(-.15)
    values[58:] = 999
    assert signed_pre_onset_changes(values, [58]).changes == result.changes[1:]


def test_signed_change_agrees_with_primary_on_nonnegative_path():
    values = np.arange(70, dtype=float) / 100
    values[:39] = np.nan
    assert signed_pre_onset_changes(values, [47, 48, 58]) == pre_onset_changes(values, [47, 48, 58])


def _pair_count_tau_b(segment):
    # Independent direct concordant/discordant counts; ordered time has no ties.
    concordant = discordant = tied = 0
    for i in range(len(segment)):
        for j in range(i + 1, len(segment)):
            if segment[j] > segment[i]:
                concordant += 1
            elif segment[j] < segment[i]:
                discordant += 1
            else:
                tied += 1
    pairs = len(segment) * (len(segment) - 1) // 2
    return (concordant - discordant) / math.sqrt(pairs * (pairs - tied))


def test_trend_ties_and_average_match_independent_pair_counts():
    first = np.array([2, 2, 1, 3, 5, 5, 4, 7, 7, 5, 6, 7, 9, 8, 9, 9])
    second = first[::-1]
    values = np.r_[first, second, 100]
    result = mean_pre_onset_trend(values, [16, 32])
    expected = (_pair_count_tau_b(first), _pair_count_tau_b(second))
    np.testing.assert_allclose(result.trends, expected, atol=1e-15)
    assert result.mean_trend == pytest.approx(sum(expected) / 2, abs=1e-15)
    assert result.eligible_onsets == (16, 32)


def test_trend_warmup_first_eligibility_and_exact_endpoints():
    values = np.arange(70, dtype=float)
    values[:39] = np.nan
    result = mean_pre_onset_trend(values, [54, 55])
    assert result.eligible_onsets == (55,)
    assert result.ineligible_onsets == (54,)
    assert result.mean_trend == pytest.approx(1)
    values[55:] = 0
    assert mean_pre_onset_trend(values, [55]).trends == result.trends
    # The first included point really is onset-16, not onset-15.
    values[39] = 1000
    assert mean_pre_onset_trend(values, [55]).mean_trend == pytest.approx(_pair_count_tau_b(values[39:55]))
    assert mean_pre_onset_trend(values, [55]).mean_trend < 1


def test_constant_eligible_trend_fails_without_dropping_episode():
    values = np.r_[np.arange(16), np.ones(16), 1]
    with pytest.raises(SecondaryStatisticError, match="Constant.*onset 32"):
        mean_pre_onset_trend(values, [16, 32])


@pytest.mark.parametrize("function,attribute", [
    (signed_pre_onset_changes, "mean_change"), (mean_pre_onset_trend, "mean_trend"),
])
def test_empty_eligible_sets_are_distinct_from_failure(function, attribute):
    assert getattr(function([], []), attribute) is None
    result = function(np.full(50, np.nan), [0, 10, 49])
    assert getattr(result, attribute) is None
    assert result.eligible_onsets == ()
    assert result.ineligible_onsets == (0, 10, 49)
    assert getattr(function(np.ones(50), []), attribute) is None


@pytest.mark.parametrize("function", [signed_pre_onset_changes, mean_pre_onset_trend])
@pytest.mark.parametrize("onsets", [[-1], [60], [20, 20], [21, 20], [20.0], [True], None])
def test_invalid_onsets(function, onsets):
    with pytest.raises(ValueError):
        function(np.arange(60.0), onsets)


@pytest.mark.parametrize("function", [signed_pre_onset_changes, mean_pre_onset_trend])
@pytest.mark.parametrize("values", [[1, np.nan, 2], [1, np.inf], [1 + 0j], [[1, 2]]])
def test_invalid_indicator_paths(function, values):
    with pytest.raises(ValueError):
        function(values, [])


def test_trend_rejects_negative_modulus_and_invalid_spans():
    with pytest.raises(ValueError, match="nonnegative"):
        mean_pre_onset_trend([-1, 0, 1], [])
    for span in (1, 0, True, 16.5):
        with pytest.raises(ValueError):
            mean_pre_onset_trend(np.arange(20.0), [16], span=span)
    for lookback in (0, True, 8.5):
        with pytest.raises(ValueError):
            signed_pre_onset_changes(np.arange(20.0), [16], lookback=lookback)


@pytest.mark.parametrize("function", [rolling_lag1, signed_pre_onset_changes, mean_pre_onset_trend])
def test_series_chronology_is_validated(function):
    series = pd.Series(np.arange(60.0), index=pd.period_range("2000Q1", periods=60, freq="Q"))
    for bad in (series.iloc[::-1], series.drop(series.index[30]),
                pd.Series(np.arange(60.0), index=[0] * 60)):
        with pytest.raises(ValueError):
            function(bad) if function is rolling_lag1 else function(bad, [55])


def _linear_percentile(sorted_values, fraction):
    position = (len(sorted_values) - 1) * fraction
    left = math.floor(position)
    right = math.ceil(position)
    return sorted_values[left] + (position - left) * (sorted_values[right] - sorted_values[left])


def test_interval_draw_order_quantiles_and_saved_states_independently():
    values = [-5.0, -1.0, 2.0, 8.0]
    rng = np.random.default_rng(2045)
    other = np.random.default_rng(2045)
    before = deepcopy(rng.bit_generator.state)
    result = episode_percentile_interval(values, rng=rng, B=37)
    indices = other.integers(0, len(values), size=(37, len(values)))
    expected_means = [sum(values[int(i)] for i in row) / len(values) for row in indices]
    expected_sorted = sorted(expected_means)
    expected_interval = tuple(_linear_percentile(expected_sorted, p) for p in (.05, .95))
    assert result.draw_means == tuple(expected_means)
    assert result.interval == pytest.approx(expected_interval, abs=1e-14)
    assert result.rng_before == before
    assert result.rng_after == other.bit_generator.state == rng.bit_generator.state
    assert (result.status, result.requested, result.attempted, result.episode_count) == ("ok", 37, 37, 4)
    # State dictionaries are snapshots, independent of later generator draws.
    saved = deepcopy(result.rng_after)
    rng.normal(size=3)
    assert result.rng_after == saved
    with pytest.raises(FrozenInstanceError):
        result.status = "changed"


def test_interval_empty_consumes_no_randomness():
    rng = np.random.default_rng(43)
    before = deepcopy(rng.bit_generator.state)
    result = episode_percentile_interval([], rng=rng)
    assert result.status == "no_eligible_episode"
    assert result.interval is None
    assert result.draw_means == ()
    assert (result.requested, result.attempted, result.episode_count) == (10_000, 0, 0)
    assert result.rng_before == result.rng_after == before == rng.bit_generator.state


def test_interval_default_count_and_single_episode_flag():
    result = episode_percentile_interval([-.125], rng=np.random.default_rng(9))
    assert result.status == "single_episode"
    assert result.interval == (-.125, -.125)
    assert (result.requested, result.attempted, result.episode_count) == (10_000, 10_000, 1)
    assert result.draw_means == (-.125,) * 10_000


@pytest.mark.parametrize("changes", [[1, np.nan], [np.inf], [[1, 2]], [1 + 0j], 1])
def test_interval_rejects_invalid_changes_without_consuming_rng(changes):
    rng = np.random.default_rng(87)
    before = deepcopy(rng.bit_generator.state)
    with pytest.raises(ValueError):
        episode_percentile_interval(changes, rng=rng)
    assert rng.bit_generator.state == before


@pytest.mark.parametrize("B", [0, -1, True, np.bool_(True), 4.5])
def test_interval_rejects_invalid_counts(B):
    with pytest.raises(ValueError):
        episode_percentile_interval([1, 2], rng=np.random.default_rng(1), B=B)


@pytest.mark.parametrize("rng", [None, 3, np.random, np.random.RandomState(8)])
def test_interval_requires_explicit_generator(rng):
    with pytest.raises(ValueError, match="explicit"):
        episode_percentile_interval([1, 2], rng=rng)
