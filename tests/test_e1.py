"""E1 unit tests on synthetic fixtures with development seeds only (never 1927, never full sizes)."""
from dataclasses import asdict, replace

import numpy as np
import pytest
from scipy.stats import kendalltau

from uc_core import h1, surrogate as s
from uc_core.ar import fit_ols
from uc_core.constants import POWER_ONSETS as H1_ONSETS
from uc_core.rolling import max_modulus
from uc_core.secondary import mean_pre_onset_trend
from uc_core.validation_design import h1_design_series
from uc_core.validation_runner import serial
from uc_ext import common as c, e1

DEV = c.DEVELOPMENT_MASTER_SEED


def rng(stream, cell=0, replicate=0):
    return c.stream_rng(DEV, stream, cell, replicate)


@pytest.fixture
def series():
    return e1.design_series(rng(9000))


def positive(n):
    return np.full(n, 2.0)


# ----------------------------------------------------------------------------- registered constants

def test_constants_follow_the_addendum():
    assert (e1.N_LEVELS, e1.N_GROWTH, e1.FIRST_GROWTH_YEAR) == (317, 316, 1701)
    assert (e1.WINDOW, e1.SENSITIVITY_WINDOWS, e1.LOOKBACK, e1.MINIMUM_RUN, e1.MERGE) == (30, (25, 35), 2, 1, 2)
    assert e1.STREAM_IDS == dict(primary=5100, window25=5101, window35=5102, fixed=5103, wild=5104,
                                 interval=5105, size_generation=5120, size_null=5121,
                                 power_generation=5130, power_null=5131)
    assert e1.POWER_ONSETS == tuple(t - 1 for t in (35, 75, 115, 155, 195, 235, 275))
    years = [e1.FIRST_GROWTH_YEAR + t for t in e1.POWER_ONSETS]
    assert years == [1735, 1775, 1815, 1855, 1895, 1935, 1975]
    assert not set(years) & e1.EXOGENOUS_YEARS
    # Spacing 40 exceeds the 32 years a W=30 window reaches back from M(r-3); every onset is eligible.
    assert all(b - a > e1.WINDOW + e1.LOOKBACK for a, b in zip(e1.POWER_ONSETS, e1.POWER_ONSETS[1:]))
    assert min(e1.POWER_ONSETS) >= e1.WINDOW + e1.LOOKBACK
    assert (e1.SERIES_PER_CELL, e1.SURROGATE_ATTEMPTS, e1.EPISODE_RESAMPLES, e1.SIZE_BOUNDS) == (200, 1000, 10000, (.02, .09))


def test_design_series_draws_and_planted_positions():
    values = e1.design_series(rng(9001), kappa=1.4)
    draws = rng(9001)
    z = draws.standard_normal(2)
    noise = draws.normal(0, 3.5, size=314)
    assert len(values) == 316
    assert values[0] == 2.5 + np.sqrt(1225 / 88) * z[0]
    for t in range(2, 316):
        planted = any(r - 2 <= t < r for r in e1.POWER_ONSETS)
        a, b = (.3 * 1.4, .1 * 1.4 ** 2) if planted else (.3, .1)
        intercept = 2.5 * (1 - a - b) if planted else 1.5
        assert values[t] == intercept + a * values[t - 1] + b * values[t - 2] + noise[t - 2]


# ------------------------------------------------------------------------ agreement with H1 code

@pytest.mark.parametrize("kappa", [1., 1.2, 1.4, 1.6])
def test_generator_reduces_to_h1_design_bit_for_bit(kappa):
    ours = e1.design_series(rng(9002, 1, 3), kappa=kappa, n=259, onsets=H1_ONSETS, signal_length=8)
    theirs = h1_design_series(rng(9002, 1, 3), kappa=kappa)
    assert np.array_equal(ours, theirs)


def h1_fixture(replicate):
    return h1_design_series(rng(9003, 0, replicate))


@pytest.mark.parametrize("replicate", range(3))
def test_measure_and_statistic_reduce_to_h1(replicate):
    values = h1_fixture(replicate)
    assert e1._measure(values, e1.H1_RULES) == h1._measure(values, window=40, lookback=8, merge=8, span=16)
    assert e1.statistic(values, e1.H1_RULES) == s._statistic(values, window=40, lookback=8, merge=8)


def test_joint_primary_reduces_to_h1_exactly():
    values = h1_fixture(0)
    ours = e1.primary_with_comparators(values, B=6, rng=rng(9004), rules=e1.H1_RULES)
    theirs = h1.primary_with_comparators(values, B=6, rng=rng(9004))
    assert serial(ours) == serial(theirs)


@pytest.mark.parametrize("onset_mode,innovation_mode", [("endogenous", "residual"), ("fixed", "residual"),
                                                        ("endogenous", "wild")])
def test_comparison_reduces_to_h1_csd_test_exactly(onset_mode, innovation_mode):
    values = h1_fixture(1)
    ours = e1.csd_test(values, B=6, rng=rng(9005), rules=e1.H1_RULES, onset_mode=onset_mode,
                       innovation_mode=innovation_mode)
    theirs = s.csd_test(values, B=6, rng=rng(9005), onset_mode=onset_mode, innovation_mode=innovation_mode)
    assert serial(ours) == serial(theirs)


# ----------------------------------------------------------------------------- section 7 rules

def test_single_negative_year_is_a_run_and_zero_ends_a_run():
    g = positive(80)
    g[40] = -1
    g[50:52] = [-1, 0.0]
    g[79] = -.5  # a terminal run qualifies
    endogenous, exogenous = e1.split_episodes(g)
    assert [(e.onset, e.end) for e in endogenous] == [(40, 40), (50, 50), (79, 79)]
    assert exogenous == ()


def test_merge_distance_two_merges_three_does_not_and_chains():
    g = positive(100)
    g[[40, 42, 44]] = -1       # 42-40 = 2 and 44-42 = 2: one chained episode
    g[[60, 63]] = -1           # 63-60 = 3: separate
    endogenous, _ = e1.split_episodes(g)
    assert [(e.onset, e.end, len(e.runs)) for e in endogenous] == [(40, 44, 3), (60, 60, 1), (63, 63, 1)]


def test_exogenous_by_onset_year_after_merging_absorbs_later_run():
    g = positive(316)
    onset_1914 = 1914 - 1701
    g[[onset_1914, onset_1914 + 2]] = -1              # merged into the 1914 episode
    g[1913 - 1701 + 30] = -1                           # 1943: exogenous
    g[1912 - 1701 - 20] = -1                           # 1892: endogenous
    start_1913 = 1913 - 1701 - 50                      # 1863 run, merged with nothing
    g[start_1913] = -1
    endogenous, exogenous = e1.split_episodes(g)
    assert [(e.onset + 1701, e.end + 1701) for e in exogenous] == [(1914, 1916), (1943, 1943)]
    assert [e.onset + 1701 for e in endogenous] == [1863, 1892]
    # An episode starting in 1913 that runs into 1914 is classified by its onset year only.
    g = positive(316)
    g[1913 - 1701:1916 - 1701] = -1
    endogenous, exogenous = e1.split_episodes(g)
    assert [e.onset + 1701 for e in endogenous] == [1913] and exogenous == ()


def test_eligibility_boundaries_by_window():
    g = e1.design_series(rng(9006))
    for window, first in ((30, 32), (25, 27), (35, 37)):
        rules = replace(e1.E1_RULES, window=window)
        result = e1.statistic(g, rules, fixed_onsets=(first - 1, first, first + 50))
        assert result.eligible_onsets == (first, first + 50)
        assert result.ineligible_onsets == (first - 1,)


def test_ineligible_first_onset_stays_ineligible_after_merge():
    g = positive(316)
    g[[20, 22, 24, 26, 28, 30, 32, 34]] = -1  # chained from 20; 34 alone would be eligible
    g += np.random.default_rng(1).normal(0, .1, 316) * (g > 0)
    result = e1.statistic(g)
    assert result.mean_change is None and result.ineligible_onsets == (20,)


def test_exogenous_episodes_never_enter_s(series):
    g = series.copy()
    g[g < 0] = .5
    g[[100, 213, 240]] = -1          # 1801 endogenous, 1914 and 1941 exogenous
    result = e1.statistic(g)
    assert result.eligible_onsets == (100,)
    rows = e1.episode_record(g)
    assert [(r["onset_year"], r["classification"]) for r in rows] == [(1801, "eligible"), (1914, "exogenous"),
                                                                       (1941, "exogenous")]
    assert all(r["delta"] is not None for r in rows)


def test_delta_is_two_year_change_of_rolling_modulus(series):
    result = e1.statistic(series)
    for onset, delta in zip(result.eligible_onsets, result.changes):
        late = fit_ols(series[onset - 30:onset]).diagnostics.modulus            # window r-30..r-1
        early = fit_ols(series[onset - 32:onset - 2]).diagnostics.modulus       # window r-32..r-3
        assert delta == pytest.approx(late - early, abs=1e-13)


def test_kendall_uses_four_years_before_onset(series):
    onsets = tuple(e.onset for e in e1.split_episodes(series)[0])
    modulus = max_modulus(series, 30)
    trend = mean_pre_onset_trend(modulus, onsets, span=4)
    assert min(trend.eligible_onsets) >= 33
    first = trend.eligible_onsets[0]
    expected = kendalltau(np.arange(4), modulus.to_numpy()[first - 4:first], variant="b").statistic
    assert trend.trends[0] == pytest.approx(expected)
    measured = e1._measure(series, e1.E1_RULES)["trend"]
    assert measured.value == pytest.approx(trend.mean_trend)


def test_territory_flags_are_descriptive(series):
    rows = e1.episode_record(series)
    eligible = [r for r in rows if r["classification"] == "eligible"]
    boundary = eligible[1]["onset_year"] - 10
    flags = e1.territory_flags(rows, [(1700, boundary - 1, "A"), (boundary, 2016, "B")])
    assert len(flags) == len(eligible)
    assert flags[1]["crosses_boundary"] and flags[1]["territories"] == ["A", "B"]
    first = flags[0]
    assert first["level_years"] == (first["onset_year"] - 33, first["onset_year"] - 1)


# ---------------------------------------------------------------------------------- section 4

def test_annual_growth_stop_rules():
    years = list(range(1690, 2020))
    levels = [100 * 1.01 ** (y - 1690) for y in years]
    growth_years, growth = e1.annual_growth(years, levels)
    assert len(growth) == 316 and growth_years[0] == 1701 and growth_years[-1] == 2016
    assert growth[0] == pytest.approx(100 * np.log(1.01))
    for bad in ([*years[:20], *years[21:]], [*years, 1800]):
        with pytest.raises(ValueError):
            e1.annual_growth(bad, levels[:len(bad)] + [1.0] * (len(bad) - len(levels)))
    for value in (0.0, -1.0, float("nan"), "n/a", None):
        broken = list(levels)
        broken[50] = value
        with pytest.raises(ValueError):
            e1.annual_growth(years, broken)
    with pytest.raises(ValueError):
        e1.annual_growth(list(range(1700, 2010)), levels[:310])   # ends before 2016: stop and amend
    outside = list(levels)
    outside[0] = "text above the sample"                           # 1690 is not inspected
    assert np.array_equal(e1.annual_growth(years, outside)[1], growth)


# ------------------------------------------------------------ assembled run and X.3 checks (dev)

def test_registered_seed_is_refused_without_gate():
    with pytest.raises(c.RegisteredRunRefused):
        e1.run_size_check(master_seed=1927, n_series=1, B=1)
    with pytest.raises(c.RegisteredRunRefused):
        e1.analyze(np.zeros(316))


def test_analyze_produces_every_output(series):
    result = e1.analyze(series, master_seed=DEV, B=4, interval_B=20)
    assert set(result) == {"master_seed", "input_sha256", "episodes", "joint", "window25", "window35",
                           "fixed", "wild", "episode_interval", "report"}
    assert result["joint"].primary.attempted == 4 and result["joint"].primary.status in ("ok",
                                                                                          "no_retained_surrogates")
    assert result["window25"].window == 25 and result["window35"].window == 35
    assert result["fixed"].onset_mode == "fixed" and result["wild"].innovation_mode == "wild"
    assert result["episode_interval"].requested == 20
    again = e1.analyze(series, master_seed=DEV, B=4, interval_B=20)
    assert serial(again) == serial(result)
    with pytest.raises(ValueError):
        e1.analyze(series[:300], master_seed=DEV, B=4)


def test_replicates_are_seed_reproducible_and_distinct():
    first = e1.size_replicate(0, master_seed=DEV, B=3)
    assert e1.size_replicate(0, master_seed=DEV, B=3) == first
    assert e1.size_replicate(1, master_seed=DEV, B=3)["input_sha256"] != first["input_sha256"]
    power = e1.power_replicate(2, 0, master_seed=DEV, B=3)
    assert e1.power_replicate(2, 0, master_seed=DEV, B=3) == power
    assert power["kappa"] == 1.4 and power["comparison"]["onset_mode"] == "external_fixed"
    assert power["observed"]["eligible_onsets"] == list(e1.POWER_ONSETS)


@pytest.mark.slow
def test_development_size_and_power_checks_run_end_to_end():
    size = e1.run_size_check(master_seed=DEV, n_series=3, B=9)
    assert size["summary"]["cell"]["attempted"] == 3 and size["summary"]["passed"] is False
    power = e1.run_power_check(master_seed=DEV, n_series=2, B=9)
    summary = power["summary"]
    assert [cell["attempted"] for cell in summary["cells"]] == [2, 2, 2, 2]
    assert summary["passed"] is False and summary["registered_design"] is False
    split = e1.run_power_check(master_seed=DEV, n_series=2, B=9, cells=[3], replicates=[1])
    assert split["records"][0] == power["records"][-1]


@pytest.mark.slow
def test_planted_signal_is_detected_at_development_size():
    """Development-only plant kappa = 4 (planted modulus 2.0 for two years), not a registered cell."""
    for replicate in range(4):
        planted = e1.design_series(rng(9010, 0, replicate), kappa=4.)
        result = h1.fixed_date_test(planted, e1.POWER_ONSETS, B=99, rng=rng(9011, 0, replicate),
                                    window=30, lookback=2)
        assert result.status == "ok" and result.p_value <= .05
    base = [s._statistic(e1.design_series(rng(9010, 0, r)), window=30, lookback=2, merge=2,
                         fixed_onsets=e1.POWER_ONSETS).mean_change for r in range(4)]
    strong = [s._statistic(e1.design_series(rng(9010, 0, r), kappa=4.), window=30, lookback=2, merge=2,
                           fixed_onsets=e1.POWER_ONSETS).mean_change for r in range(4)]
    assert np.mean(strong) > np.mean(base) + .1


def test_s10_analyze_reports_k_q_wilson_and_the_raw_label(series):
    """S10: k = count(Delta > 0), q = K/B' with its Wilson interval, and the raw-p label (sections 8-9)."""
    from uc_core.validation_design import wilson_interval
    shifted = series - 1.5                        # more recessions, so several eligible episodes
    result = e1.analyze(shifted, master_seed=DEV, B=6, interval_B=20)
    report = result["report"]
    assert report["p_label"] == "raw, not family-adjusted"
    rows = {row["analysis"]: row for row in report["rows"]}
    assert list(rows) == ["primary", "window25", "window35", "fixed", "wild", "trend", "lag1"]
    assert [rows[k]["window"] for k in rows] == [30, 25, 35, 30, 30, 30, 30]
    primary, observed = rows["primary"], result["joint"].primary
    deltas = observed.observed.components
    assert primary["m"] == len(deltas) >= 1 and primary["k"] == sum(d > 0 for d in deltas)
    assert primary["value"] == observed.observed.value and primary["p_value"] == observed.p_value
    for name, row in rows.items():
        assert row["p_label"] == "raw, not family-adjusted" and row["status"] != "report_failed", name
        if row["status"] == "ok":
            assert row["B_prime"] == row["retained"] >= 1 and row["q"] == row["exceedances"] / row["B_prime"]
            assert row["q_wilson"] == wilson_interval(row["exceedances"], row["B_prime"])
            assert row["p_value"] == (1 + row["exceedances"]) / (1 + row["B_prime"])
        else:
            assert row["q"] is None and row["p_value"] is None
    windowed = result["window25"].observed.changes
    assert rows["window25"]["k"] == sum(d > 0 for d in windowed)


def test_s10_report_keeps_a_row_whose_accounting_fails():
    row = c.comparison_row("primary", dict(status="ok", requested=5, attempted=3, retained=3, no_episode=0,
                                           failed=0, attempts=[], observed=dict(value=.1)), 30)
    assert row["status"] == "report_failed" and "ledger" in row["error"] and row["p_label"] == c.RAW_P_LABEL
