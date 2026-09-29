"""E3 unit tests on synthetic fixtures with development seeds only (never 1927, never full sizes), plus
AT-11's sunspot fixture (1749-1924), which the research repository already uses (B1)."""
import json
import math

import numpy as np
import pytest

from uc_core import h1, surrogate as s
from uc_core.ar import fit_ols
from uc_core.constants import POWER_ONSETS
from uc_core.recession import episodes
from uc_core.rolling import max_modulus
from uc_core.statespace import kalman_filter, regression_at11
from uc_core.validation_design import h1_design_series
from uc_core.validation_runner import serial
from uc_ext import common as c, e3

DEV = c.DEVELOPMENT_MASTER_SEED


def rng(stream, cell=0, replicate=0):
    return c.stream_rng(DEV, stream, cell, replicate)


@pytest.fixture(scope="module")
def series():
    return h1_design_series(rng(9300))


@pytest.fixture(scope="module")
def fitted(series):
    return e3.fit_ml(series)


# ----------------------------------------------------------------------------- registered constants

def test_constants_follow_the_addendum():
    assert len(e3.GRID) == 16 and e3.GRID[0] == 0. and e3.GRID[1] == 1e-8 and e3.GRID[-1] == 1e-1
    assert e3.GRID[2] == pytest.approx(10 ** -7.5, rel=1e-15)
    assert all(a < b for a, b in zip(e3.GRID, e3.GRID[1:]))
    assert (e3.N_GROWTH, e3.EXCLUDED, e3.N_STAR, e3.DIFFUSE) == (259, 3, 254, 1e8)
    assert (e3.FIRST_INDICATOR, e3.FIRST_ELIGIBLE, e3.FIRST_INDICATOR + e3.TREND_SPAN) == (39, 48, 55)
    assert (e3.LOG10_BOUNDS, e3.MAXITER) == ((-10., 0.), 200)
    assert e3.STREAM_IDS == dict(primary=5300, fixed=5303, wild=5304, interval=5305, size_generation=5320,
                                 size_null=5321, power_generation=5330, power_null=5331)
    assert e3.PREREQUISITE_FIXTURE == dict(stream="size_generation", cell=1, replicate=0)
    assert (e3.SERIES_PER_CELL, e3.SURROGATE_ATTEMPTS, e3.SIZE_BOUNDS) == (200, 1000, (.02, .09))
    assert POWER_ONSETS == (49, 99, 149, 199, 249)


# ------------------------------------------------------------------------------ likelihood and filter

@pytest.mark.parametrize("r1,r2", [(0., 0.), (1e-4, 0.), (0., 3e-3), (1e-2, 1e-5)])
def test_concentrated_loglik_equals_exact_loglik_at_sigma2_hat(series, r1, r2):
    loglik, sigma2, _ = e3.reference_loglik(series, r1, r2)
    y, Z = e3.state_space(series)
    exact = kalman_filter(y, Z, np.eye(3), sigma2 * np.diag([0., r1, r2]), sigma2, np.zeros(3),
                          sigma2 * 1e8 * np.eye(3), burn=3).loglik
    assert loglik == pytest.approx(exact, abs=1e-8)


def test_batched_filter_agrees_with_reference_on_grid_and_off_grid(series):
    grid = e3.filter_agreement(series)
    assert grid["passed"] and grid["points"] == 256 and grid["mismatched_failures"] == 0
    off = e3.filter_agreement(series, [(3.3e-5, 7.1e-3), (1., 1.), (1e-10, 0.)])
    assert off["passed"]


def test_batch_member_does_not_depend_on_batch_composition(series):
    y, Z = e3.state_space(series)
    points = e3.grid_points()
    full = e3.batched_filter(y, Z, points)
    for index in (0, 17, 255):
        alone = e3.batched_filter(y, Z, points[index:index + 1])
        assert alone.loglik[0] == full.loglik[index]


def test_batched_filter_marks_failures():
    y = np.zeros(10)
    Z = np.zeros((10, 3))
    result = e3.batched_filter(y, Z, [(0., 0.)])
    # All-zero observations give sigma2_hat = 0: a non-finite likelihood, never a silent value.
    assert result.failed[0] and math.isnan(result.loglik[0])


# ------------------------------------------------------------------------------ maximum likelihood

def test_grid_tie_breaking():
    grid = np.full((16, 16), -np.inf)
    grid[3, 5] = grid[5, 3] = grid[4, 4] = -1.0
    assert e3._grid_choice(grid) in ((3, 5), (5, 3), (4, 4))
    # Ties go to the smaller r1 + r2, then the smaller r1.
    sums = {k: e3.GRID[k[0]] + e3.GRID[k[1]] for k in ((3, 5), (5, 3), (4, 4))}
    best = min(sums, key=lambda k: (sums[k], e3.GRID[k[0]]))
    assert e3._grid_choice(grid) == best
    grid = np.full((16, 16), -np.inf)
    grid[2, 7] = grid[7, 2] = -1.0
    assert e3._grid_choice(grid) == (2, 7)
    assert e3._grid_choice(np.full((16, 16), np.nan)) is None


def test_fit_record_and_acceptance(fitted):
    assert fitted.status == "ok"
    assert len(fitted.grid_loglik) == 16 and all(len(row) == 16 for row in fitted.grid_loglik)
    assert fitted.loglik >= fitted.grid_max["loglik_reference"]
    assert abs(fitted.grid_max["loglik"] - fitted.grid_max["loglik_reference"]) <= 1e-6
    if fitted.accepted == "grid":
        assert (fitted.r1, fitted.r2) == fitted.grid_max["r"]
    i, j = fitted.grid_max["index"]
    for k, index in enumerate((i, j)):
        if index == 0:   # a zero coordinate at the grid maximum is held at 0
            assert (fitted.r1, fitted.r2)[k] == 0. and fitted.at_zero[k]
    assert fitted.q1 == pytest.approx(fitted.sigma2 * fitted.r1) and fitted.q2 == pytest.approx(fitted.sigma2 * fitted.r2)
    assert fitted.loglik_at_zero == fitted.grid_loglik[0][0]


@pytest.mark.parametrize("replicate", range(3))
def test_batched_and_reference_engines_reach_the_same_estimate(replicate):
    values = h1_design_series(rng(9301, 0, replicate))
    batched = e3.fit_ml(values, engine="batched")
    reference = e3.fit_ml(values, engine="reference")
    assert (batched.r1, batched.r2, batched.accepted) == (reference.r1, reference.r2, reference.accepted)
    assert batched.loglik == reference.loglik


def test_drifting_coefficient_is_picked_up_by_the_estimator():
    generator = rng(9302)
    noise = generator.normal(0, 1, 259)
    x = np.zeros(259)
    phi1 = np.r_[np.full(130, -.5), np.full(129, .8)]
    for t in range(2, 259):
        x[t] = 1 + phi1[t] * x[t - 1] + noise[t]
    fit = e3.fit_ml(x)
    assert fit.r1 > 0 and fit.loglik > fit.loglik_at_zero + 5


def test_refinement_keeps_bounds_and_records_optimizer(series):
    x = series.copy()
    x[130:] += np.sin(np.arange(129)) * 4      # a fixture pushing the variances off zero
    fit = e3.fit_ml(x)
    if fit.refinement is not None:
        assert all(-10 <= v <= 0 for v in fit.refinement["log10"])
        assert {"success", "status", "message", "nit", "nfev"} <= set(fit.refinement)
    assert all(0 <= r <= 1 for r in (fit.r1, fit.r2))


# ----------------------------------------------------------------------------- indicator

def test_filtered_not_smoothed_modulus(series, fitted):
    modulus, states = e3.filtered_modulus(series, fitted.sigma2, fitted.r1, fitted.r2)
    assert np.isnan(modulus[:39]).all() and np.isfinite(modulus[39:]).all()
    assert states.shape == (257, 3)
    changed = series.copy()
    changed[150:] = changed[150:] * 3 - 7
    later, _ = e3.filtered_modulus(changed, fitted.sigma2, fitted.r1, fitted.r2)
    assert np.array_equal(later[:150], modulus[:150], equal_nan=True)   # M(t) uses g[0..t] only
    assert not np.array_equal(later[150:], modulus[150:])


def test_zero_state_noise_reduces_to_expanding_least_squares(series):
    """Agreement with H1's estimator: r = 0 filtered states are OLS on g[0..t]; the last is full-sample OLS."""
    prerequisite = e3.prerequisite_r0(series)
    assert prerequisite["passed"] and prerequisite["max_abs_difference"] <= 1e-6
    modulus, states = e3.filtered_modulus(series, 1.0, 0., 0.)
    for t in (39, 100, 258):
        ols = fit_ols(series[:t + 1])
        assert np.max(np.abs(states[t - 2] - [ols.intercept, *ols.coefficients])) <= 1e-6
        assert modulus[t] == pytest.approx(ols.diagnostics.modulus, abs=1e-6)


def test_prerequisite_fixture_uses_stream_5320_cell_1():
    record = e3.prerequisite_fixture(master_seed=DEV)
    expected = h1_design_series(c.stream_rng(DEV, 5320, 1, 0))
    assert record["input_sha256"] == c.sha256_values(expected)
    assert record["r0"]["passed"] and record["agreement"]["passed"]
    # B1: the prerequisite step also runs and records AT-11 and the agreement test on AT-11's fixture.
    assert record["at11"]["passed"] and record["at11"]["agreement"]["points"] == 256
    assert record["passed"] is True


# ------------------------------------------------- B1: AT-11's fixture (sections 6 and 11)

def sunspots_1749_1924():
    """The research repository's AT-11 fixture, selected as its tests/test_foundations.py does."""
    import statsmodels.api as sm
    data = sm.datasets.sunspots.load_pandas().data
    return data.SUNACTIVITY[(data.YEAR >= 1749) & (data.YEAR <= 1924)].to_numpy()


def test_at11_fixture_is_the_research_repositorys_fixture():
    values = e3.at11_fixture()
    assert len(values) == 176 and np.array_equal(values, sunspots_1749_1924())


def test_batched_filter_agrees_with_reference_on_at11_fixture_over_the_grid():
    result = e3.filter_agreement(sunspots_1749_1924())
    assert result["points"] == 256 and result["mismatched_failures"] == 0 and result["passed"]
    assert result["max_state_difference"] <= 1e-8 and result["max_loglik_difference"] <= 1e-6


def test_at11_through_the_batched_filter_at_r0():
    values = sunspots_1749_1924()
    batched = e3.batched_at11(values)
    reference = regression_at11(values)
    assert batched["passed"] and batched["max_abs_difference"] <= 1e-6 and not batched["filter_failed"]
    assert reference["passed"] and batched["least_squares"] == reference["least_squares"]
    assert np.max(np.abs(np.subtract(batched["final_state"], reference["final_state"]))) <= 1e-8


def test_at11_checks_fail_closed_on_a_different_fixture(monkeypatch):
    monkeypatch.setattr(e3, "AT11_YEAR_VALUE_SHA256", "0" * 64)
    result = e3.at11_checks()
    assert result["passed"] is False and "differs" in result["error"]
    record = e3.prerequisite_fixture(master_seed=DEV)
    assert record["passed"] is False and record["r0"]["passed"] and record["agreement"]["passed"]


# ------------------------------------------------------- agreement of the test layer with H1 code

@pytest.fixture
def rolling_indicator(monkeypatch):
    """Replace only the E3 indicator by H1's rolling M; the rest must then be H1's procedure."""
    def estimate(values, *, engine="batched", fit_log=None):
        return None, max_modulus(values, 40).to_numpy(), None
    monkeypatch.setattr(e3, "estimate", estimate)


def test_episode_rules_are_h1s(series):
    assert e3.onsets_of(series) == tuple(e.onset for e in episodes(series, merge=8))


@pytest.mark.parametrize("onset_mode,innovation_mode", [("endogenous", "residual"), ("fixed", "residual"),
                                                        ("endogenous", "wild")])
def test_surrogate_layer_reduces_to_h1_csd_test(series, rolling_indicator, onset_mode, innovation_mode):
    ours = e3.csd_test(series, B=6, rng=rng(9303), onset_mode=onset_mode, innovation_mode=innovation_mode)
    theirs = s.csd_test(series, B=6, rng=rng(9303), onset_mode=onset_mode, innovation_mode=innovation_mode)
    assert serial(ours) == serial(theirs)


def test_fixed_date_layer_reduces_to_h1(series, rolling_indicator):
    ours = e3.fixed_date_test(series, POWER_ONSETS, B=5, rng=rng(9304))
    theirs = h1.fixed_date_test(series, POWER_ONSETS, B=5, rng=rng(9304))
    assert serial(ours) == serial(theirs)


def test_joint_primary_and_trend_reduce_to_h1(series, rolling_indicator):
    ours = e3.primary_with_comparators(series, B=5, rng=rng(9305))
    theirs = h1.primary_with_comparators(series, B=5, rng=rng(9305))
    assert serial(ours.primary) == serial(theirs.primary)
    assert serial(ours.trend) == serial(theirs.trend)
    assert ours.rng_after == theirs.rng_after and ours.generated_attempts == theirs.generated_attempts
    assert ours.held_fixed.attempted == 5


# ------------------------------------------------------------------- assembled run and X.3 (dev)

def test_registered_seed_is_refused_without_gate(series):
    with pytest.raises(c.RegisteredRunRefused):
        e3.run_size_check(master_seed=1927, n_series=1, B=1)
    with pytest.raises(c.RegisteredRunRefused):
        e3.prerequisite_fixture(master_seed=1927)
    with pytest.raises(c.RegisteredRunRefused):
        e3.analyze(series)


def test_analyze_produces_every_output_and_retains_fits(series):
    result = e3.analyze(series, master_seed=DEV, B=2, interval_B=20)
    assert set(result) == {"master_seed", "input_sha256", "engine", "joint", "descriptive", "surrogate_fits",
                           "fixed", "wild", "episode_interval", "report"}
    joint = result["joint"]
    assert joint.observed_fit.status == "ok" and joint.generated_attempts == 2
    for name in ("primary", "held_fixed", "trend"):
        assert getattr(joint, name).requested == 2
    assert result["fixed"].onset_mode == "fixed" and result["wild"].innovation_mode == "wild"
    assert set(result["surrogate_fits"]["primary"]) == {0, 1}
    retained = [f for f in result["surrogate_fits"]["primary"].values() if f is not None]
    assert all(len(f["grid_loglik"]) == 16 for f in retained)
    assert result["descriptive"]["loglik_minus_loglik_at_zero"] >= 0
    assert len(result["descriptive"]["filtered_states"]) == 257


def test_replicates_are_seed_reproducible_and_distinct():
    first = e3.size_replicate(0, master_seed=DEV, B=2, check_agreement=False)
    assert e3.size_replicate(0, master_seed=DEV, B=2, check_agreement=False) == first
    assert e3.size_replicate(1, master_seed=DEV, B=2, check_agreement=False)["input_sha256"] != first["input_sha256"]
    power = e3.power_replicate(1, 0, master_seed=DEV, B=2, check_agreement=False, retain_fits=True)
    assert power["kappa"] == 1.2 and power["observed"]["eligible_onsets"] == list(POWER_ONSETS)
    assert power["comparison"]["onset_mode"] == "external_fixed" and len(power["surrogate_fits"]) == 2


@pytest.mark.slow
def test_development_size_and_power_checks_run_end_to_end():
    size = e3.run_size_check(master_seed=DEV, n_series=1, B=2)
    assert size["summary"]["cell"]["attempted"] == 1 and size["summary"]["passed"] is False
    assert size["records"][0]["filter_agreement"]["passed"]
    power = e3.run_power_check(master_seed=DEV, n_series=1, B=2, check_agreement=False)
    assert [cell["attempted"] for cell in power["summary"]["cells"]] == [1, 1, 1, 1]
    assert power["summary"]["passed"] is False and power["summary"]["registered_design"] is False


@pytest.mark.slow
def test_planted_signal_is_detected_at_development_size():
    """Development-only plant kappa = 3 in the eight quarters before H1's onsets; not a registered cell."""
    for replicate in range(3):
        planted = c.design_series(rng(9310, 0, replicate), kappa=3., n=259, onsets=POWER_ONSETS, signal_length=8)
        result = e3.fixed_date_test(planted, POWER_ONSETS, B=19, rng=rng(9311, 0, replicate))
        assert result.status == "ok" and result.p_value <= .05


# ------------------------------------------------ S8 and S9: failure handling of the joint comparison

@pytest.fixture(scope="module")
def recession_series():
    """A development series shifted down so that eligible recession episodes exist."""
    x = h1_design_series(rng(9320)) - 2.0
    assert any(t >= e3.FIRST_ELIGIBLE for t in e3.onsets_of(x))
    return x


def forced_fit_failure(values, *, engine="batched"):
    return e3.MLFit("failed", None, None, None, None, None, None, (), {}, None, None, (), (), None,
                    "forced failure for the test")


def test_s8_observed_fit_failure_fails_held_fixed_instead_of_emptying_it(monkeypatch, recession_series):
    monkeypatch.setattr(e3, "fit_ml", forced_fit_failure)
    joint = e3.primary_with_comparators(recession_series, B=2, rng=rng(9321))
    assert joint.fit_error == "forced failure for the test"
    for name in ("primary", "held_fixed"):
        comparison = getattr(joint, name)
        assert comparison.observed.status == "failed" and comparison.status == "observed_statistic_failed"
        assert comparison.attempted == 0 and comparison.p_value is None
    assert "Observed fit failed" in joint.held_fixed.observed.error and joint.generated_attempts == 0
    result = e3.analyze(recession_series, master_seed=DEV, B=2, interval_B=10)
    assert result["joint"].held_fixed.status == "observed_statistic_failed" and result["descriptive"] is None
    assert result["episode_interval"]["status"] == "observed_statistic_failed"
    assert result["fixed"]["status"] == result["wild"]["status"] == "observed_statistic_failed"


def test_s8_without_an_eligible_episode_held_fixed_stays_not_estimable(monkeypatch):
    calm = h1_design_series(rng(9323)) + 30.0          # no negative quarter, so no episode at all
    assert e3.onsets_of(calm) == ()
    monkeypatch.setattr(e3, "fit_ml", forced_fit_failure)
    joint = e3.primary_with_comparators(calm, B=2, rng=rng(9324))
    assert joint.held_fixed.status == joint.primary.status == "observed_not_estimable"


@pytest.mark.parametrize("failing", [0, 1])
def test_s9_generation_failure_records_no_fit_and_does_not_abort(monkeypatch, recession_series, failing):
    original = s.draw_surrogate
    calls = dict(n=0)

    def draw(model, generator, *, kind="residual"):
        number = calls["n"]
        calls["n"] += 1
        if number == failing:
            generator.integers(0, 257, size=257)
            raise FloatingPointError("forced generation failure for the test")
        return original(model, generator, kind=kind)

    monkeypatch.setattr(s, "draw_surrogate", draw)
    fits = {}
    joint = e3.primary_with_comparators(recession_series, B=3, rng=rng(9322), fits=fits)
    statuses = [a.status for a in joint.primary.attempts]
    assert statuses[failing] == "failed" and fits[failing] is None and set(fits) == {0, 1, 2}
    assert all(fits[k] is not None for k in range(3) if statuses[k] == "retained")
    assert "forced generation failure" in joint.primary.attempts[failing].error
    assert joint.primary.status == joint.held_fixed.status == "invalid_surrogate_failure"
    assert joint.primary.p_value is None and joint.generated_attempts == 3


def test_s10_analyze_reports_k_q_wilson_and_the_raw_label(recession_series):
    """S10: k = count(Delta > 0), q = K/B' with its Wilson interval, and the raw-p label (sections 8-9)."""
    from uc_core.validation_design import wilson_interval
    result = e3.analyze(recession_series, master_seed=DEV, B=3, interval_B=20)
    report = result["report"]
    assert report["p_label"] == "raw, not family-adjusted" and report["first_indicator"] == 39
    rows = {row["analysis"]: row for row in report["rows"]}
    assert list(rows) == ["primary", "held_fixed", "fixed", "wild", "trend"]
    joint = result["joint"]
    deltas = joint.primary.observed.components
    assert rows["primary"]["m"] == len(deltas) >= 1 and rows["primary"]["k"] == sum(d > 0 for d in deltas)
    assert rows["held_fixed"]["k"] == rows["primary"]["k"]          # same observed statistic (E3-O7)
    for name, row in rows.items():
        assert row["p_label"] == "raw, not family-adjusted" and row["status"] != "report_failed", name
        assert row["window"] is None
        if row["status"] == "ok":
            assert row["q"] == row["exceedances"] / row["B_prime"]
            assert row["q_wilson"] == wilson_interval(row["exceedances"], row["B_prime"])
        else:
            assert row["q"] is None and row["p_value"] is None



# ------------------------------------------------ S6 and S7: the two owner rulings as recorded settings

FORCED_POINT = 16 * 3 + 7          # grid index (3, 7), r1 = 10^-7, r2 = 10^-5


def force_grid_filter_failure(monkeypatch, skip=0):
    """Mark grid point (3, 7) as a filter failure in every 256-point grid after the first `skip` grids."""
    original = e3.batched_filter
    grids = dict(seen=0)

    def forced(y, Z, points, *, store_states=False):
        result = original(y, Z, points, store_states=store_states)
        if len(np.atleast_2d(points)) != 256:
            return result
        grids["seen"] += 1
        if grids["seen"] <= skip:
            return result
        loglik, failed, broken = result.loglik.copy(), result.failed.copy(), result.filter_failed.copy()
        loglik[FORCED_POINT], failed[FORCED_POINT], broken[FORCED_POINT] = np.nan, True, True
        return e3.BatchResult(loglik, result.sigma2, failed, result.filtered_states, filter_failed=broken)
    monkeypatch.setattr(e3, "batched_filter", forced)


def test_s6_default_reading_discards_a_failed_grid_point(monkeypatch, series, fitted):
    assert e3.GRID_POINT_FAILURE == "discard" and fitted.grid_point_failure == "discard"
    assert fitted.grid_filter_failures == ()
    force_grid_filter_failure(monkeypatch)
    fit = e3.fit_ml(series)
    assert fit.status == "ok" and fit.grid_filter_failures == ((3, 7),) and fit.grid_loglik[3][7] is None
    if fitted.grid_max["index"] != (3, 7):
        assert (fit.r1, fit.r2, fit.loglik) == (fitted.r1, fitted.r2, fitted.loglik)


def test_s6_fail_reading_fails_the_fit_and_the_surrogate(monkeypatch, series):
    force_grid_filter_failure(monkeypatch)
    fit = e3.fit_ml(series, grid_failure="fail")
    assert fit.status == "failed" and "S6" in fit.error and fit.grid_filter_failures == ((3, 7),)
    monkeypatch.setattr(e3, "GRID_POINT_FAILURE", "fail")      # the module setting drives every fit
    assert e3.fit_ml(series).status == "failed"
    with pytest.raises(e3.FitFailure):
        e3.estimate(series)
    record = e3.size_replicate(0, master_seed=DEV, B=1, check_agreement=False)
    assert record["settings"]["grid_point_failure"] == "fail" and record["status"] == "observed_statistic_failed"
    with pytest.raises(ValueError):
        e3.fit_ml(series, grid_failure="ignore")


@pytest.mark.parametrize("reading,expected", [("discard", "ok"), ("fail", "invalid_surrogate_failure")])
def test_s6_reading_decides_a_surrogate_grid_failure(monkeypatch, recession_series, reading, expected):
    """The observed fit is clean; every surrogate fit has one failed grid point (fixed dates, so every
    surrogate is fitted). 'discard' keeps the surrogates, 'fail' makes each a failed attempt, invalidating p."""
    force_grid_filter_failure(monkeypatch, skip=1)
    monkeypatch.setattr(e3, "GRID_POINT_FAILURE", reading)
    fits = {}
    result = e3.fixed_date_test(recession_series, POWER_ONSETS, B=2, rng=rng(9331), fits=fits)
    assert result.status == expected and result.attempted == 2
    assert all(fit["grid_filter_failures"] == [[3, 7]] and fit["grid_point_failure"] == reading
               for fit in fits.values())


def test_s6_reference_engine_flags_filter_failures(monkeypatch, series):
    original = e3.reference_loglik

    def forced(values, r1, r2):
        if (r1, r2) == (e3.GRID[3], e3.GRID[7]):
            return math.nan, math.nan, None           # the reference filter raised
        return original(values, r1, r2)
    monkeypatch.setattr(e3, "reference_loglik", forced)
    assert e3.fit_ml(series, engine="reference").grid_filter_failures == ((3, 7),)
    assert e3.fit_ml(series, engine="reference", grid_failure="fail").status == "failed"
    assert e3.filter_failed(None) and not e3.filter_failed(e3.reference_filter(series, 0., 0.))


def test_s7_retention_setting_defaults_to_all_fits_under_the_registered_seed():
    assert e3.X3_RETENTION == dict(registered="all_fits", development="base_fits")
    assert e3.default_retention(1927) is True and e3.default_retention(DEV) is False
    assert e3.x3_settings(master_seed=1927)["retention"] == "all_fits"       # no computation, no draws
    assert e3.x3_settings(master_seed=DEV) == dict(engine="batched", check_agreement=True,
                                                   grid_point_failure="discard", retention="base_fits")
    assert e3.x3_arguments(e3.x3_settings(master_seed=1927))["retain_fits"] is True
    base = e3.size_replicate(0, master_seed=DEV, B=2, check_agreement=False)
    assert base["surrogate_fits"] is None and base["settings"]["retention"] == "base_fits"
    assert base["observed_fit"]["grid_loglik"]
    kept = e3.size_replicate(0, master_seed=DEV, B=2, check_agreement=False, retain_fits=True)
    assert set(kept["surrogate_fits"]) == {0, 1} and kept["settings"]["retention"] == "all_fits"



# -------------------------------------------------------------------------- C1 and C5

def test_c1_the_observed_series_is_fitted_once_and_nothing_changes(monkeypatch, recession_series):
    import contextlib
    calls = []
    original = e3._fit_ml

    def counting(values, engine, reading):
        calls.append(np.asarray(values, dtype=float).tobytes())
        return original(values, engine, reading)

    monkeypatch.setattr(e3, "_fit_ml", counting)
    observed = np.asarray(recession_series, dtype=float).tobytes()
    reused = e3.primary_with_comparators(recession_series, B=2, rng=rng(9340))
    assert calls.count(observed) == 1
    replicate = next(r for r in range(10) if e3.size_replicate(r, master_seed=DEV, B=1, check_agreement=False)["S"])
    calls.clear()
    record = e3.size_replicate(replicate, master_seed=DEV, B=2, check_agreement=False)
    assert calls.count(np.asarray(record["input"], dtype=float).tobytes()) == 1
    calls.clear()
    analyzed = e3.analyze(recession_series, master_seed=DEV, B=1, interval_B=10)
    assert calls.count(observed) == 1
    monkeypatch.setattr(e3, "_reusing_first_fit", lambda *args, **kwargs: contextlib.nullcontext())
    calls.clear()
    assert serial(e3.primary_with_comparators(recession_series, B=2, rng=rng(9340))) == serial(reused)
    assert calls.count(observed) == 2                          # without reuse: fitted twice, as in M4b
    assert e3.size_replicate(replicate, master_seed=DEV, B=2, check_agreement=False) == record
    again = e3.analyze(recession_series, master_seed=DEV, B=1, interval_B=10)
    as_json = lambda result: json.dumps(serial(result), sort_keys=True, default=str)   # NaN-safe comparison
    assert as_json(again) == as_json(analyzed)


def test_c5_lower_bound_flag(fitted):
    assert e3._lower_bound_flags("refined", [0, 1], dict(log10=[-10.0, -3.2])) == (True, False)
    assert e3._lower_bound_flags("refined", [1], dict(log10=[-10.0])) == (False, True)
    assert e3._lower_bound_flags("grid", [0, 1], dict(log10=[-10.0, -10.0])) == (False, False)
    assert fitted.at_lower_bound == (False, False) and fitted.at_upper == (False, False)
