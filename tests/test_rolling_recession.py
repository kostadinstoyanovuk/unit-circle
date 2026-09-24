import numpy as np
import pandas as pd
import pytest

from uc_core import fit_ols
from uc_core.rolling import max_modulus, rolling_ar2, RollingFitError
from uc_core.recession import episodes, pre_onset_changes


@pytest.fixture
def series():
    # Synthetic engineering fixture, not an inferential simulation cell.
    return pd.Series(np.random.default_rng(192740).normal(size=90),
                     index=pd.period_range("2000Q1", periods=90, freq="Q"))


def test_rolling_window_and_sample_boundaries(series):
    result = rolling_ar2(series)
    assert result.index.equals(series.index)
    assert (result.status.iloc[:39] == "warmup").all()
    assert result.modulus.iloc[:39].isna().all()
    first = fit_ols(series.iloc[:40])
    last = fit_ols(series.iloc[-40:])
    np.testing.assert_allclose(result.iloc[39][["phi1", "phi2"]].astype(float), first.coefficients, rtol=0, atol=1e-14)
    assert result.modulus.iloc[-1] == pytest.approx(last.diagnostics.modulus, abs=1e-14)
    assert first.n_regression_rows == 38


def test_prefix_invariance_and_future_perturbation(series):
    full = max_modulus(series)
    prefix = max_modulus(series.iloc[:65])
    pd.testing.assert_series_equal(full.iloc[:65], prefix)
    altered = series.copy()
    altered.iloc[65:] = altered.iloc[65:] * 100 + 50
    pd.testing.assert_series_equal(max_modulus(altered).iloc[:65], full.iloc[:65])


@pytest.mark.parametrize("window", [True, 4, 40.5, 0])
def test_invalid_window(series, window):
    with pytest.raises(ValueError):
        max_modulus(series, window)


def test_short_sample_has_only_warmup(series):
    result = rolling_ar2(series.iloc[:20])
    assert result.modulus.isna().all()
    assert (result.status == "warmup").all()


def test_fit_failure_is_not_warmup_or_silently_dropped():
    with pytest.raises(RollingFitError, match="position 39"):
        rolling_ar2(np.ones(60))


def test_bad_chronology_missing_period_and_nonfinite_values(series):
    for bad in (series.iloc[::-1], series.drop(series.index[30]),
                pd.Series(series.to_numpy(), index=[0] * len(series))):
        with pytest.raises(ValueError):
            rolling_ar2(bad)
        with pytest.raises(ValueError):
            episodes(bad)
    bad = series.copy()
    bad.iloc[50] = np.nan
    with pytest.raises(ValueError):
        max_modulus(bad)


def path(length, runs):
    values = np.ones(length)
    for start, stop in runs:
        values[start:stop+1] = -1
    return values


def test_runs_strict_negativity_singletons_and_terminal_run():
    result = episodes([0, -1, 0, -1, -1, 0, -1, -1], merge=0)
    assert [(e.onset, e.end) for e in result] == [(3, 4), (6, 7)]
    assert episodes([1, 0, -1, 0, 1]) == ()
    assert [(e.onset, e.end) for e in episodes([-1, -1])] == [(0, 1)]


def test_merge_eight_inclusive_and_nine_exclusive():
    merged = episodes(path(24, [(2, 3), (11, 12)]))
    assert [(e.onset, e.end) for e in merged] == [(2, 12)]
    separate = episodes(path(24, [(2, 3), (12, 13)]))
    assert [(e.onset, e.end) for e in separate] == [(2, 3), (12, 13)]


def test_chain_merge_uses_latest_run_end_and_singleton_does_not_reset():
    chain = episodes(path(32, [(2, 3), (11, 12), (20, 21)]))
    assert [(e.onset, e.end) for e in chain] == [(2, 21)]
    assert len(chain[0].runs) == 3
    separate = episodes(path(30, [(2, 3), (10, 10), (18, 19)]))
    assert [(e.onset, e.end) for e in separate] == [(2, 3), (18, 19)]


def test_first_eligible_onset_and_exact_eight_quarter_change():
    m = np.arange(80, dtype=float) / 100
    m[:39] = np.nan
    result = pre_onset_changes(m, [47, 48, 60])
    assert result.eligible_onsets == (48, 60)
    assert result.ineligible_onsets == (47,)
    np.testing.assert_allclose(result.changes, [.08, .08], rtol=0, atol=1e-15)
    assert result.mean_change == pytest.approx(.08)
    # An arbitrary onset-quarter jump must never enter Delta.
    m[60] = 100
    assert pre_onset_changes(m, [60]).changes == result.changes[1:]


def test_no_eligible_episode_is_none_not_zero():
    assert pre_onset_changes(np.full(40, np.nan), [10, 30]).mean_change is None
    assert pre_onset_changes(np.arange(50.0), []).mean_change is None


@pytest.mark.parametrize("onsets", [[10, 10], [20, 10], [-1], [50], [10.5], [True]])
def test_invalid_onsets_rejected(onsets):
    with pytest.raises(ValueError):
        pre_onset_changes(np.arange(50.0), onsets)


def test_internal_missing_modulus_is_an_error():
    values = np.arange(80, dtype=float)
    values[:39] = np.nan
    values[50] = np.nan
    with pytest.raises(ValueError):
        pre_onset_changes(values, [60])


def test_merged_later_run_cannot_replace_ineligible_first_onset():
    runs = episodes(path(70, [(47, 48), (56, 57)]))
    assert [(e.onset, e.end) for e in runs] == [(47, 57)]
    m = np.arange(70, dtype=float) / 100
    m[:39] = np.nan
    result = pre_onset_changes(m, [e.onset for e in runs])
    assert result.eligible_onsets == () and result.ineligible_onsets == (47,)
    assert result.mean_change is None


def test_signed_changes_are_preserved_in_mean():
    m = np.full(70, .4)
    m[:39] = np.nan
    m[[39, 47, 49, 57]] = [.40, .46, .50, .48]
    result = pre_onset_changes(m, [48, 58])
    np.testing.assert_allclose(result.changes, [.06, -.02], rtol=0, atol=1e-15)
    assert result.mean_change == pytest.approx(.02)


def test_modulus_index_cannot_reverse_chronology():
    with pytest.raises(ValueError):
        pre_onset_changes(pd.Series(np.arange(60.0), index=np.arange(60)[::-1]), [48])


def test_empty_growth_and_trailing_singleton():
    assert episodes([]) == ()
    assert episodes(path(60, [(59, 59)])) == ()


def test_rolling_and_episode_inputs_share_quarter_labels(series):
    growth = series.abs() + 1
    growth.iloc[48:50] = [-1, -.5]
    result = episodes(growth)
    assert result[0].onset == 48
    assert growth.index[result[0].onset] == pd.Period("2012Q1", freq="Q")
    m = max_modulus(growth)
    delta = pre_onset_changes(m, [result[0].onset])
    assert delta.changes[0] == pytest.approx(m.iloc[47] - m.iloc[39])
