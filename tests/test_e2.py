"""E2 pipeline tests on development fixtures and development seeds only (no data, no registered seed).

Development fixture streams 9600-9699 are ad hoc coordinates under the development master seed; the
registered seed 1927 is never used to draw a random number here.
"""
import math

import numpy as np
import pytest
import scipy.linalg

from uc_core import h1 as h1_module, linalg, surrogate as s
from uc_core.abmi import growth as abmi_growth
from uc_core.ar import fit_ols, root_summary
from uc_core.constants import POWER_ONSETS as H1_POWER_ONSETS, STREAM_IDS as H1_STREAM_IDS
from uc_core.recession import episodes
from uc_core.rolling import RollingFitError, max_modulus as h1_max_modulus
from uc_core.validation_design import h1_design_series

from uc_e2 import analysis, constants, procedure, streams, synthetic, var, variables
from uc_ext import common as c, e1, e3

DEV = streams.DEVELOPMENT_SEED


def rng(stream, cell=0, replicate=0):
    return c.stream_rng(DEV, stream, cell, replicate)


def h1_series(stream, kappa=1.):
    return h1_design_series(rng(stream), kappa=kappa)


def e2_series(stream, kappa=1., onsets=None):
    return synthetic.design_series(rng(stream), kappa=kappa, onsets=onsets)


def assert_attempts_agree(left, right, tol=1e-10):
    assert len(left) == len(right)
    for a, b in zip(left, right):
        assert (a.number, a.status, a.eligible_onsets) == (b.number, b.status, b.eligible_onsets)
        if a.statistic is None:
            assert b.statistic is None
        else:
            assert abs(a.statistic - b.statistic) <= tol
            assert np.allclose(a.changes, b.changes, atol=tol, rtol=0)


def assert_comparisons_agree(mine, reference):
    for name in ("status", "p_value", "requested", "attempted", "retained", "no_episode", "failed", "exceedances",
                 "p_grid_spacing", "window", "lookback", "merge", "onset_mode", "innovation_mode"):
        assert getattr(mine, name) == getattr(reference, name), name
    assert mine.rng_before == reference.rng_before and mine.rng_after == reference.rng_after
    assert mine.observed.eligible_onsets == reference.observed.eligible_onsets
    assert abs(mine.observed.mean_change - reference.observed.mean_change) <= 1e-10
    assert_attempts_agree(mine.attempts, reference.attempts)


# ------------------------------------------------------------------------------------ constants

def test_registered_constants_follow_the_addendum():
    assert (constants.N_LEVELS, constants.N_OBS, constants.K, constants.H1_OFFSET) == (196, 195, 2, 64)
    assert (constants.WINDOW, constants.SENSITIVITY_WINDOWS, constants.LOOKBACK, constants.MINIMUM_RUN, constants.MERGE, constants.TREND_SPAN) == (
        40, (32, 48), 8, 2, 8, 16)
    assert (constants.SURROGATE_ATTEMPTS, constants.EPISODE_RESAMPLES, constants.SERIES_PER_CELL, constants.SIZE_BOUNDS) == (
        1000, 10000, 200, (.02, .09))
    assert constants.KAPPAS == (1., 1.2, 1.4, 1.6)
    assert constants.STREAM_IDS == dict(primary=5200, window32=5201, window48=5202, fixed=5203, wild=5204, interval=5205,
                                 size_generation=5220, size_null=5221, power_generation=5230, power_null=5231)
    ids = set(constants.STREAM_IDS.values())
    assert all(5200 <= i <= 5231 for i in ids) and len(ids) == len(constants.STREAM_IDS)
    for other in (H1_STREAM_IDS.values(), e1.STREAM_IDS.values(), e3.STREAM_IDS.values()):
        assert not ids & set(other)
    assert constants.ONSETS_RECORD == "audit/E2_ONSETS.json" and constants.DEVELOPMENT_POWER_ONSETS == (49, 99, 149)


def test_quarter_positions_match_section_5():
    assert [variables.quarter_label(p) for p in (0, 39, 48, 55, 194)] == ["1971 Q2", "1981 Q1", "1983 Q2", "1985 Q1",
                                                                     "2019 Q4"]


# ------------------------------------------------------------ k = 1: E2 reduces to H1 (Annex B, X.3)

@pytest.mark.parametrize("stream", [9600, 9601, 9602])
def test_one_variable_fit_is_h1s_ols(stream):
    x = h1_series(stream)
    mine, reference = var.fit_var2(x), fit_ols(x)
    assert mine.intercept[0] == pytest.approx(reference.intercept, abs=1e-12)
    assert (mine.coefficients[0][0][0], mine.coefficients[1][0][0]) == pytest.approx(reference.coefficients, abs=1e-12)
    assert np.max(np.abs(np.ravel(mine.residuals) - np.asarray(reference.residuals))) <= 1e-12
    assert abs(mine.modulus - reference.diagnostics.modulus) <= 1e-12
    assert (mine.n_observations, mine.n_regression_rows) == (259, 257)


@pytest.mark.parametrize("stream,kappa", [(9603, 1.), (9604, 1.6), (9605, 1.4)])
def test_rolling_modulus_reproduces_h1_to_1e10(stream, kappa):
    x = h1_series(stream, kappa)
    result = synthetic.reduction_check(x)
    assert result["passed"] and [row["window"] for row in result["windows"]] == [32, 40, 48]
    for window in (32, 40, 48):
        mine, reference = var.max_modulus(x, window), np.asarray(h1_max_modulus(x, window))
        assert np.array_equal(np.isnan(mine), np.isnan(reference)) and np.isnan(mine[:window - 1]).all()
        assert np.nanmax(np.abs(mine - reference)) <= constants.REDUCTION_TOL


def test_one_variable_null_and_draws_are_h1s():
    x = h1_series(9606)
    mine, reference = procedure.prepare_null(x), s.prepare_null(x)
    assert mine.initial == ((reference.initial[0],), (reference.initial[1],))
    assert np.max(np.abs(np.ravel(mine.residuals) - np.asarray(reference.residuals))) <= 1e-12
    assert abs(mine.residual_mean_removed[0] - reference.residual_mean_removed) <= 1e-12
    assert abs(mine.modulus - reference.modulus) <= 1e-12
    for kind in ("residual", "wild"):
        left, right = rng(9607), rng(9607)
        path, reference_path = procedure.draw_surrogate(mine, left, kind=kind), s.draw_surrogate(reference, right, kind=kind)
        assert left.bit_generator.state == right.bit_generator.state
        assert np.max(np.abs(path[:, 0] - reference_path)) <= 1e-9


@pytest.mark.parametrize("kwargs", [dict(), dict(window=32), dict(onset_mode="fixed"), dict(innovation_mode="wild")])
def test_one_variable_csd_test_is_h1s(kwargs):
    x = h1_series(9608)
    mine = procedure.csd_test(x, B=25, rng=rng(9609), **kwargs)
    reference = s.csd_test(x, B=25, rng=rng(9609), **kwargs)
    assert mine.status == "ok"
    assert_comparisons_agree(mine, reference)


def test_one_variable_joint_comparison_is_h1s():
    x = h1_series(9610)
    mine = procedure.primary_with_comparators(x, B=20, rng=rng(9611))
    reference = h1_module.primary_with_comparators(x, B=20, rng=rng(9611))
    assert mine.rng_before == reference.rng_before and mine.rng_after == reference.rng_after
    assert mine.generated_attempts == reference.generated_attempts == 20
    for name in ("primary", "trend", "lag1"):
        a, b = getattr(mine, name), getattr(reference, name)
        assert (a.status, a.p_value, a.retained, a.no_episode, a.failed, a.exceedances) == (
            b.status, b.p_value, b.retained, b.no_episode, b.failed, b.exceedances), name
        assert a.observed.eligible_onsets == b.observed.eligible_onsets
        if b.observed.value is None:
            assert a.observed.value is None
        else:
            assert abs(a.observed.value - b.observed.value) <= 1e-10
        assert_attempts_agree(a.attempts, b.attempts)
    assert mine.primary.status == "ok" and mine.lag1.status == "ok"


def test_one_variable_fixed_date_test_is_h1s():
    x = h1_series(9612, kappa=1.4)
    mine = procedure.fixed_date_test(x, H1_POWER_ONSETS, B=20, rng=rng(9613))
    reference = h1_module.fixed_date_test(x, H1_POWER_ONSETS, B=20, rng=rng(9613))
    assert mine.observed.eligible_onsets == H1_POWER_ONSETS
    assert_comparisons_agree(mine, reference)


def test_at12_through_the_e2_function_is_at12_number_for_number():
    mine, reference = synthetic.at12(3000, DEV), linalg.at12(3000, seed=DEV)
    assert mine["passed"] and reference["passed"]
    assert mine["diagonal"] == reference["diagonal"] and mine["ar2"] == reference["ar2"]
    assert mine["seed"] == [DEV, 2012]


# --------------------------------------------------------------- section 6: the bivariate estimator

def test_multivariate_ols_is_equation_by_equation_ols():
    x = e2_series(9614)
    fit = var.fit_var2(x)
    design = np.column_stack((np.ones(193), x[1:-1], x[:-2]))
    for equation in range(2):
        beta = np.linalg.lstsq(design, x[2:, equation], rcond=None)[0]
        mine = [fit.intercept[equation], *fit.coefficients[0][equation], *fit.coefficients[1][equation]]
        assert np.allclose(mine, beta, atol=1e-9, rtol=0)
    residuals = np.asarray(fit.residuals)
    assert residuals.shape == (193, 2) and np.max(np.abs(design.T @ residuals)) <= 1e-8     # normal equations
    companion = np.block([[np.asarray(fit.coefficients[0]), np.asarray(fit.coefficients[1])],
                          [np.eye(2), np.zeros((2, 2))]])
    assert fit.modulus == np.max(np.abs(np.linalg.eigvals(companion)))


def test_indicator_is_invariant_to_rescaling_and_ordering_the_variables():
    x = e2_series(9615)
    base = var.max_modulus(x)
    assert np.nanmax(np.abs(var.max_modulus(x * [1., 100.]) - base)) <= 1e-10          # section 5
    assert np.nanmax(np.abs(var.max_modulus(x * [.01, 1.]) - base)) <= 1e-10
    assert np.nanmax(np.abs(var.max_modulus(x[:, ::-1]) - base)) <= 1e-10
    assert np.isnan(base[:39]).all() and np.isfinite(base[39:]).all()                     # first M at 1981Q1


def test_window_failures_raise_with_their_endpoint_and_unstable_fits_are_kept():
    x = e2_series(9616)
    collinear = np.column_stack((x[:, 0], x[:, 0]))
    with pytest.raises(RollingFitError, match="position 39"):
        var.max_modulus(collinear)
    with pytest.raises(s.NullModelError):
        procedure.prepare_null(collinear)
    constant = x.copy()
    constant[:, 1] = 3.
    with pytest.raises(RollingFitError):
        var.max_modulus(constant)
    explosive = procedure.simulate_var2((0., 0.), (((1.05, 0.), (0., .5)), ((0., 0.), (0., 0.))), ((1., 0.), (1., 0.)),
                                 rng(9617).standard_normal((193, 2)))
    path = var.max_modulus(explosive)
    assert np.nanmax(path) > 1                                    # retained, not clipped or projected
    with pytest.raises(s.NullModelError, match="strictly stable"):
        procedure.prepare_null(explosive)
    with pytest.raises(ValueError):
        var.fit_var2(np.full((10, 2), np.nan))


# ------------------------------------------------------------------- sections 7-9: episodes and null

def test_episodes_come_from_g_alone():
    x = e2_series(9618)
    changed = x.copy()
    changed[:, 1] = rng(9619).standard_normal(195)
    assert procedure.onsets_of(x) == procedure.onsets_of(changed) == tuple(e.onset for e in episodes(x[:, 0]))
    result = procedure.statistic(x)
    assert all(t >= 48 for t in result.eligible_onsets) and all(t < 48 for t in result.ineligible_onsets
                                                                 if t not in result.eligible_onsets)


def test_residual_vectors_are_resampled_jointly_and_wild_signs_apply_per_vector():
    x = e2_series(9620)
    model = procedure.prepare_null(x)
    residuals = np.asarray(model.residuals)
    assert residuals.shape == (193, 2) and np.max(np.abs(residuals.mean(axis=0))) <= 1e-12
    a1, a2 = (np.asarray(m) for m in model.coefficients)
    c_vector = np.asarray(model.intercept)

    def innovations(path):
        return path[2:] - c_vector - path[1:-1] @ a1.T - path[:-2] @ a2.T

    copy = rng(9621)
    indices = copy.integers(0, 193, size=193)
    path = procedure.draw_surrogate(model, rng(9621))
    assert np.array_equal(path[:2], x[:2])
    assert np.max(np.abs(innovations(path) - residuals[indices])) <= 1e-9       # both components, same row
    signs = 2 * rng(9622).integers(0, 2, size=193) - 1
    wild = procedure.draw_surrogate(model, rng(9622), kind="wild")
    assert np.max(np.abs(innovations(wild) - residuals * signs[:, None])) <= 1e-9


def test_bivariate_comparisons_keep_h1s_accounting():
    x = e2_series(9623)
    comparison = procedure.csd_test(x, B=12, rng=rng(9624))
    assert comparison.status == "ok" and comparison.attempted == 12
    assert comparison.attempted == comparison.retained + comparison.no_episode + comparison.failed
    kept = [a.statistic for a in comparison.attempts if a.status == "retained"]
    assert comparison.p_value == (1 + sum(v >= comparison.observed.mean_change for v in kept)) / (len(kept) + 1)
    assert len(comparison.null_model.residuals) == 193
    joint = procedure.primary_with_comparators(x, B=6, rng=rng(9625))
    assert joint.primary.status == "ok" and joint.lag1.status == "ok" and joint.generated_attempts == 6
    fixed = procedure.fixed_date_test(x, (60, 120, 180), B=5, rng=rng(9626))
    assert fixed.status == "ok" and fixed.observed.eligible_onsets == (60, 120, 180)
    assert all(a.eligible_onsets == (60, 120, 180) for a in fixed.attempts)


def test_failures_are_recorded_not_dropped():
    x = e2_series(9627)
    model = procedure.prepare_null(x)
    huge = procedure.VARNullModel(model.intercept, (((1e155, 0.), (0., 0.)), ((0., 0.), (0., 0.))), model.initial,
                           model.residuals, model.residual_mean_removed, model.modulus)
    with pytest.raises(FloatingPointError):
        procedure.draw_surrogate(huge, rng(9628))
    short = procedure.csd_test(x[:40], B=3, rng=rng(9629))
    assert short.status == "observed_not_estimable" and short.attempted == 0


# ---------------------------------------------------------------------- section 11: synthetic design

def test_design_parameters_and_stationary_start():
    sigma, factor, initial, initial_factor = synthetic.design_covariances()
    assert np.array_equal(np.linalg.cholesky(sigma), factor)
    assert sigma[0, 1] / math.sqrt(sigma[0, 0] * sigma[1, 1]) == -.5
    a1, a2, mu = np.asarray(constants.DESIGN_A1), np.asarray(constants.DESIGN_A2), np.asarray(constants.DESIGN_MEAN)
    assert np.max(np.abs((np.eye(2) - a1 - a2) @ mu - constants.DESIGN_INTERCEPT)) <= 1e-15
    companion = np.block([[a1, a2], [np.eye(2), np.zeros((2, 2))]])
    q = np.zeros((4, 4))
    q[:2, :2] = sigma
    stationary = scipy.linalg.solve_discrete_lyapunov(companion, q)      # covariance of (X[t], X[t-1])
    order = [2, 3, 0, 1]                                                 # -> (X0, X1)
    assert np.max(np.abs(stationary[np.ix_(order, order)] - initial)) <= 1e-12
    assert np.max(np.abs(initial_factor @ initial_factor.T - initial)) <= 1e-12
    assert np.allclose(np.sort(np.linalg.eigvals(companion).real), [-.2, -.2, .5, .5], atol=1e-12)
    for kappa in constants.KAPPAS:
        assert abs(var.spectral_radius([kappa * a1, kappa ** 2 * a2]) - .5 * kappa) <= 1e-12


def test_design_series_draws_exactly_the_stated_calls():
    _, factor, _, initial_factor = synthetic.design_covariances()
    generator = rng(9630)
    start = np.array([2.5, 0., 2.5, 0.]) + initial_factor @ generator.standard_normal(4)
    noise = generator.standard_normal((193, 2)) @ factor.T
    x = e2_series(9630)
    after = rng(9630)
    synthetic.design_series(after)
    assert after.bit_generator.state == generator.bit_generator.state
    assert np.array_equal(x[:2].ravel(), start)
    expected = x[:2].tolist()
    for t in range(2, 195):
        expected.append(np.array([1.5, 0.]) + .3 * np.asarray(expected[t - 1]) + .1 * np.asarray(expected[t - 2])
                        + noise[t - 2])
    assert np.max(np.abs(np.asarray(expected) - x)) <= 1e-12
    assert np.array_equal(e2_series(9631, kappa=1., onsets=(49, 99, 149)), e2_series(9631))


def test_planted_segments_use_scaled_coefficients_only_before_each_onset():
    kappa, onsets = 1.4, (49, 99, 149)
    x = e2_series(9632, kappa=kappa, onsets=onsets)
    _, factor, _, _ = synthetic.design_covariances()
    generator = rng(9632)
    generator.standard_normal(4)
    noise = generator.standard_normal((193, 2)) @ factor.T
    a1, a2, mu = np.asarray(constants.DESIGN_A1), np.asarray(constants.DESIGN_A2), np.asarray(constants.DESIGN_MEAN)
    planted = {t for r in onsets for t in range(r - 8, r)}
    for t in range(2, 195):
        scale = kappa if t in planted else 1.
        intercept = (np.eye(2) - scale * a1 - scale ** 2 * a2) @ mu
        implied = x[t] - intercept - scale * a1 @ x[t - 1] - scale ** 2 * a2 @ x[t - 2]
        assert np.max(np.abs(implied - noise[t - 2])) <= 1e-9, t
    with pytest.raises(ValueError):
        synthetic.design_series(rng(9633), onsets=(49, 55))              # overlapping planted segments


def test_design_innovation_correlation_and_means_in_a_development_sample():
    x = np.concatenate([e2_series(9634 + i) for i in range(40)])
    assert abs(x[:, 0].mean() - 2.5) < 5 * math.sqrt(1225 / 88 / len(x)) * 3      # loose: serial correlation
    assert abs(x[:, 1].mean()) < 5 * math.sqrt(100 / 88 / len(x)) * 3
    _, factor, _, _ = synthetic.design_covariances()
    z = rng(9690).standard_normal((20000, 2)) @ factor.T
    assert abs(np.corrcoef(z.T)[0, 1] + .5) < .02


# ------------------------------------------------------------- R1: power onsets and registered refusal

def test_imposed_onsets_come_from_the_record_under_the_registered_seed():
    assert variables.imposed_onsets(DEV) == (49, 99, 149) and variables.imposed_onsets(DEV, [60, 120]) == (60, 120)
    fixture = dict(power_onsets=[49, 99, 149], power_onset_source="development_fixture", retain_window_fits=True)
    assert synthetic.x3_settings(master_seed=DEV) == fixture == synthetic.x3_settings(master_seed=DEV, power_onsets=(49, 99, 149))
    assert synthetic.x3_settings(master_seed=DEV, power_onsets=(60, 120))["power_onset_source"] == "development_supplied"
    with pytest.raises(c.RegisteredRunRefused, match="E2_ONSETS"):
        variables.imposed_onsets(1927)
    with pytest.raises(c.RegisteredRunRefused):
        synthetic.x3_settings(master_seed=1927)
    assert synthetic.x3_settings(master_seed=1927, power_onsets=(77, 148)) == dict(
        power_onsets=[77, 148], power_onset_source="registered_onsets_record", retain_window_fits=True)
    for other in ((60, 120), (77,), (77, 148, 160), (78, 148)):     # section 7: the record must equal (77, 148)
        with pytest.raises(c.RegisteredRunRefused, match="section 7"):
            synthetic.x3_settings(master_seed=1927, power_onsets=other)
    assert synthetic.x3_arguments(fixture) == synthetic.x3_input_arguments(fixture) == dict(onsets=(49, 99, 149))
    for settings in (dict(fixture, power_onset_source="guess"), dict(fixture, retain_window_fits=False),
                     dict(fixture, power_onsets=[47])):
        with pytest.raises(ValueError):
            synthetic.x3_arguments(settings)
    for bad in [(47,), (48, 57), (100, 195), (), (48.0,), (True,), (60, 50)]:
        with pytest.raises(ValueError):
            variables.check_power_onsets(bad)
    assert variables.check_power_onsets((48, 58, 194)) == (48, 58, 194)
    assert synthetic._registered(1927, 200, 1000) and not synthetic._registered(1927, 200, 999) and not synthetic._registered(DEV, 200, 1000)


def _h1_labels():
    return [f"{y} Q{q}" for y in range(1955, 2020) for q in range(1, 5)][1:]


def test_onset_record_round_trip_and_refusals(tmp_path):
    import json
    growth = h1_series(9660)
    record = variables.onset_record(growth, _h1_labels())
    assert record["m_E2"] >= 1 and tuple(record["power_onsets"]) == variables.onset_table(growth)["power_onsets"]
    assert record["h1_growth_sha256"] == c.sha256_values(growth)
    path = tmp_path / "E2_ONSETS.json"
    path.write_text(json.dumps(record))
    assert variables.read_onsets_record(path) == tuple(record["power_onsets"])
    with pytest.raises(ValueError):
        variables.onset_record(growth, _h1_labels()[1:] + ["2020 Q1"])

    def variant(name, **changes):
        target = tmp_path / name
        target.write_text(json.dumps(json.loads(path.read_text()) | changes))
        return target

    listed = record["power_onsets"]
    for bad in (tmp_path / "missing.json", variant("window.json", window=32), variant("kind.json", record="other"),
                variant("m.json", m_E2=len(listed) + 1), variant("empty.json", m_E2=0, power_onsets=[]),
                variant("shifted.json", power_onsets=[t + 1 for t in listed])):
        with pytest.raises(ValueError):
            variables.read_onsets_record(bad)


def test_registered_seed_is_refused_without_the_gate_flag():
    with pytest.raises(c.RegisteredRunRefused):
        synthetic.size_replicate(0, master_seed=1927)
    with pytest.raises(c.RegisteredRunRefused):
        synthetic.power_replicate(0, 0, master_seed=1927)
    with pytest.raises(c.RegisteredRunRefused):
        analysis.analyze(np.zeros((195, 2)))
    with pytest.raises(c.RegisteredRunRefused):
        synthetic.prerequisite_fixture(master_seed=1927)
    with pytest.raises(c.RegisteredRunRefused):
        synthetic.x3_input("size", 0, 0, master_seed=1927)


# ------------------------------------------------------------------------------- X.3 replicate records

def test_size_and_power_records_are_complete_and_regenerable():
    size = synthetic.size_replicate(0, master_seed=DEV, B=4)
    assert size["status"] == "ok" and size["surrogate_attempted"] == 4 and size["settings"]["power_onsets"] == [49, 99, 149]
    assert size["input_sha256"] == c.sha256_values(synthetic.x3_input("size", 0, 0, master_seed=DEV))
    assert np.asarray(size["input"]).shape == (195, 2)
    assert len(size["comparison"]["null_model"]["residuals"]) == 193
    power = synthetic.power_replicate(3, 1, master_seed=DEV, B=3)
    assert power["kappa"] == 1.6 and power["status"] == "ok"
    assert power["observed"]["eligible_onsets"] == [49, 99, 149]
    assert all(a["eligible_onsets"] == [49, 99, 149] for a in power["comparison"]["attempts"])
    assert power["input_sha256"] == c.sha256_values(synthetic.x3_input("power", 3, 1, master_seed=DEV))
    assert power["generation_rng_before"] == c.stream_rng(DEV, 9230, 3, 1).bit_generator.state
    assert power["analysis_rng_before"] == c.stream_rng(DEV, 9231, 3, 1).bit_generator.state
    assert size["generation_rng_before"] == c.stream_rng(DEV, 9220, 0, 0).bit_generator.state
    assert size["analysis_rng_before"] == c.stream_rng(DEV, 9221, 0, 0).bit_generator.state
    for record in (size, power):                   # R9: the base series' W = 40 window fits
        fits, values = record["window_fits"], np.asarray(record["input"])
        assert (fits["window"], fits["first_position"], fits["error"]) == (40, 39, None)
        assert fits["modulus"] == var.max_modulus(values)[39:].tolist()
        assert np.asarray(fits["A1"]).shape == np.asarray(fits["A2"]).shape == (156, 2, 2)
        assert np.asarray(fits["intercept"]).shape == (156, 2)
    assert synthetic.window_fits(np.zeros((195, 2)))["error"].startswith("RollingFitError")
    supplied = synthetic.power_replicate(1, 0, master_seed=DEV, B=2, onsets=(60, 120, 180))
    assert supplied["observed"]["eligible_onsets"] == [60, 120, 180]
    assert supplied["settings"]["power_onset_source"] == "development_supplied"
    assert supplied["input_sha256"] == c.sha256_values(synthetic.x3_input("power", 1, 0, master_seed=DEV, onsets=(60, 120, 180)))
    assert supplied["input_sha256"] != c.sha256_values(synthetic.x3_input("power", 1, 0, master_seed=DEV))


@pytest.mark.slow
def test_development_size_and_power_checks_summarize_without_passing():
    size = synthetic.run_size_check(n_series=3, B=9)
    assert size["summary"]["cell"]["attempted"] == 3 and size["summary"]["passed"] is False
    power = synthetic.run_power_check(n_series=2, B=5)
    summary = power["summary"]
    assert [row["kappa"] for row in summary["cells"]] == [1., 1.2, 1.4, 1.6]
    assert all(row["attempted"] == 2 for row in summary["cells"]) and summary["passed"] is False


# ------------------------------------------------------------------------------------ prerequisites

def test_development_prerequisite_passes_and_names_its_parts():
    record = synthetic.prerequisite_fixture(master_seed=DEV)
    assert record["passed"] and all(record[name]["passed"] for name in constants.PREREQUISITE_PARTS)
    assert record["at12"]["diagonal"]["draws"] == constants.AT12_DRAWS["development"]
    expected = h1_design_series(c.stream_rng(DEV, 9220, 1, 0))
    assert record["input_sha256"] == c.sha256_values(expected) == record["reduction"]["input_sha256"]
    assert record["f4"] == dict(passed=True, source="DECISIONS.md D-019; STATUS.md, original C1 foundations checks",
                                rerun=False)
    assert record["unit_tests"] == ["tests/test_e2_data_rules.py"]


# ------------------------------------------------------------------- X.4 assembly on a synthetic series

def test_analyze_assembles_every_registered_output_on_a_synthetic_series():
    x = e2_series(9640)
    first = analysis.analyze(x, master_seed=DEV, B=6, interval_B=50)
    report = first["report"]
    assert [row["analysis"] for row in report["rows"]] == ["primary", "window32", "window48", "fixed", "wild",
                                                          "trend", "lag1"]
    assert all(row["p_label"] == "raw, not family-adjusted" for row in report["rows"])
    assert all(row["status"] in ("ok", "observed_not_estimable") for row in report["rows"])
    assert first["joint"].rng_before == c.stream_rng(DEV, 9200).bit_generator.state
    assert first["window32"].rng_before == c.stream_rng(DEV, 9201).bit_generator.state
    assert first["window48"].rng_before == c.stream_rng(DEV, 9202).bit_generator.state
    assert first["fixed"].rng_before == c.stream_rng(DEV, 9203).bit_generator.state
    assert first["wild"].rng_before == c.stream_rng(DEV, 9204).bit_generator.state
    assert first["episode_interval"].rng_before == c.stream_rng(DEV, 9205).bit_generator.state
    assert first["onset_check"] is None
    for window in (32, 40, 48):
        fits = first["rolling_fits"][window]
        assert fits["A1"].shape == (195, 2, 2) and np.isnan(fits["modulus"][:window - 1]).all()
    assert len(first["joint"].null_model.residuals) == 193
    eligible = [row for row in first["episodes"]["rows"] if row["e2_delta"] is not None]
    assert eligible and all(row["h1_frozen_delta"] is None and row["h1_frozen_agrees"] is None for row in eligible)
    recomputed = {row["onset"]: row["ar2_delta_g_recomputed"] for row in eligible}
    for onset, value in recomputed.items():
        reference = np.asarray(h1_max_modulus(x[:, 0], 40))
        assert value == reference[onset - 1] - reference[onset - 9]
    frozen = dict(recomputed)
    frozen[next(iter(frozen))] += 1e-12
    second = analysis.analyze(x, master_seed=DEV, B=6, interval_B=50, h1_frozen_deltas=frozen)
    flags = [row["h1_frozen_agrees"] for row in second["episodes"]["rows"] if row["e2_delta"] is not None]
    assert flags == [False] + [True] * (len(flags) - 1)
    assert second["joint"].primary.p_value == first["joint"].primary.p_value      # deterministic
    observed = first["joint"].primary.observed.eligible_onsets
    check = analysis.analyze(x, master_seed=DEV, B=2, interval_B=10, registered_onsets=observed)["onset_check"]
    assert check == dict(registered=list(observed), observed=list(observed), agrees=True)       # R8
    other = (observed[0] + 1,) if observed[0] + 1 < 195 else (observed[0] - 1,)
    assert analysis.analyze(x, master_seed=DEV, B=2, interval_B=10, registered_onsets=other)["onset_check"]["agrees"] is False
    with pytest.raises(ValueError):
        analysis.analyze(x[:194], master_seed=DEV, B=2)


# ------------------------------------------------------------------ sections 4, 5 and 7: data rules

def _artificial(first_year=1968, last_year=2021, stream=9650):
    """ARTIFICIAL quarterly fixture (labels, levels, rates), not any real series."""
    labels = [f"{y} Q{q}" for y in range(first_year, last_year + 1) for q in range(1, 5)]
    generator = rng(stream)
    levels = 100 * np.exp(np.cumsum(generator.normal(.005, .01, len(labels))))
    rates = generator.uniform(3, 12, len(labels))
    return labels, levels.tolist(), labels, rates.tolist()


def test_variables_select_by_label_and_equal_h1_growth_bit_for_bit():
    gq, levels, uq, rates = _artificial()
    levels[0], rates[-1] = float("nan"), 250.          # outside 1971Q1-2019Q4: never inspected
    quarters, x = variables.variables(gq, levels, uq, rates)
    assert x.shape == (195, 2) and quarters[0] == "1971 Q2" and quarters[-1] == "2019 Q4"
    start = gq.index("1971 Q1")
    assert np.array_equal(x[:, 1], np.diff(np.asarray(rates[start:start + 196])))
    assert np.array_equal(x[:, 0], 400 * np.diff(np.log(np.asarray(levels[start:start + 196]))))


def test_e2_growth_is_h1_growth_for_the_same_quarters():
    gq, levels, uq, rates = _artificial(first_year=1955, last_year=2019, stream=9651)
    h1_labels, h1_growth = abmi_growth(gq, np.asarray(levels))
    _, x = variables.variables(gq, levels, uq, rates)
    assert np.array_equal(x[:, 0], h1_growth[64:]) and np.array_equal(variables.e2_growth_from_h1(h1_growth), x[:, 0])
    assert h1_labels[64] == "1971 Q2"


def test_variables_stop_on_every_section_4_violation():
    gq, levels, uq, rates = _artificial(stream=9652)
    i = gq.index("1990 Q3")
    cases = [
        (gq[:i] + gq[i + 1:], levels[:i] + levels[i + 1:], uq, rates),                 # missing quarter
        (gq + ["1990 Q3"], levels + [100.], uq, rates),                                 # duplicate
        (gq, levels[:i] + [0.] + levels[i + 1:], uq, rates),                            # non-positive level
        (gq, levels[:i] + [float("inf")] + levels[i + 1:], uq, rates),                  # non-finite level
        (gq, levels[:i] + ["1.0"] + levels[i + 1:], uq, rates),                         # non-numeric
        (gq, levels, uq, rates[:i] + [100.5] + rates[i + 1:]),                          # rate above 100
        (gq, levels, uq, rates[:i] + [-.1] + rates[i + 1:]),                            # negative rate
        (gq, levels, uq, rates[:i] + [float("nan")] + rates[i + 1:]),                   # missing rate
        (gq[:i] + ["1990-Q3"] + gq[i + 1:], levels, uq, rates),                         # bad label
        (list(reversed(gq)), list(reversed(levels)), uq, rates),                        # reversed order
        (gq, levels[:-1], uq, rates),                                                   # length mismatch
    ]
    for case in cases:
        with pytest.raises(ValueError):
            variables.variables(*case)


def test_onset_table_applies_section_7_to_h1_growth_positions_64_to_258():
    growth = h1_series(9653)
    growth[60:66] = -1.                       # a run crossing 1971 Q2 (H1 position 64): in E2 it starts at 0
    growth[140:142] = -1.
    table = variables.onset_table(growth)
    e2_growth = growth[64:]
    assert [row["onset"] for row in table["rows"]] == [e.onset for e in episodes(e2_growth)]
    h1_onsets = {e.onset for e in episodes(growth)}
    for row in table["rows"]:
        assert row["eligible"] == {32: row["onset"] >= 40, 40: row["onset"] >= 48, 48: row["onset"] >= 56}
        assert row["also_h1_onset"] == (row["onset"] + 64 in h1_onsets)
        assert row["onset_quarter"] == variables.quarter_label(row["onset"])
    assert table["power_onsets"] == tuple(row["onset"] for row in table["rows"] if row["onset"] >= 48)
    assert table["m_E2"] == len(table["power_onsets"])
    first = table["rows"][0]
    assert first["onset"] == 0 and first["also_h1_onset"] is False      # H1's run starts by 1970 Q2
    with pytest.raises(ValueError):
        variables.onset_table(growth[:258])
