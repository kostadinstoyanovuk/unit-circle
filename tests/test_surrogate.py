from copy import deepcopy
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from uc_core import fit_ols
from uc_core.recession import episodes, pre_onset_changes
from uc_core.rolling import max_modulus
from uc_core import surrogate as s


def generator(seed=192741):
    return np.random.Generator(np.random.PCG64(seed))


@pytest.fixture
def growth():
    values = generator().uniform(1, 3, size=90)
    values[48:50] = [-1, -.6]
    values[60:62] = [-1, -.6]
    return values


def test_recursion_initial_order_intercept_and_innovation_alignment():
    actual = s.simulate_ar2((.3, .1), 1.5, (2, 3), (1, -2, 0))
    np.testing.assert_allclose(actual, [2, 3, 3.6, .88, 2.124], rtol=0, atol=1e-14)
    np.testing.assert_array_equal(s.simulate_ar2((.3, .1), 1.5, (2, 3), []), [2, 3])


@pytest.mark.parametrize("kind", ["residual", "wild"])
def test_resampler_matches_independent_innovations_and_loop(kind):
    model = s.NullModel((.3, .1), 1.5, (2., 3.), (-2., -1., 1., 2.), 0., .5)
    reference_rng = generator()
    residuals = np.array(model.residuals)
    if kind == "residual":
        innovations = residuals[reference_rng.integers(0, 4, size=4)]
    else:
        innovations = residuals * (2*reference_rng.integers(0, 2, size=4)-1)
    expected = [2., 3.]
    for noise in innovations:
        expected.append(1.5 + .3*expected[-1] + .1*expected[-2] + noise)
    actual_rng = generator()
    actual = s.draw_surrogate(model, actual_rng, kind=kind)
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-14)
    assert actual_rng.bit_generator.state == reference_rng.bit_generator.state


def test_null_uses_full_fit_and_centered_unscaled_residuals(growth):
    model = s.prepare_null(growth)
    fit = fit_ols(growth)
    assert model.coefficients == fit.coefficients
    assert model.intercept == fit.intercept
    assert model.initial == tuple(growth[:2])
    assert len(model.residuals) == len(growth)-2
    expected = np.array(fit.residuals)
    assert model.residual_mean_removed == expected.mean()
    np.testing.assert_array_equal(model.residuals, expected-expected.mean())
    assert abs(np.mean(model.residuals)) < 1e-14
    assert model.modulus < 1


def test_unstable_and_rank_deficient_nulls_fail_without_projection():
    explosive = s.simulate_ar2((1.2, -.1), .5, (1, 2), generator().normal(size=78))
    with pytest.raises(s.NullModelError, match="strictly stable"):
        s.prepare_null(explosive)
    with pytest.raises(s.NullModelError, match="null fit failed"):
        s.prepare_null(np.ones(60))


@pytest.mark.parametrize("modulus,stable,accepted", [(.999, True, True), (1., False, False),
                                                    (1.001, False, False), (1., True, False)])
def test_null_boundary_policy(growth, monkeypatch, modulus, stable, accepted):
    # Isolate the fitted-null policy; root computations are separately tested.
    fit = fit_ols(growth)
    fit = replace(fit, diagnostics=replace(fit.diagnostics, modulus=modulus, stable=stable))
    monkeypatch.setattr(s, "fit_ols", lambda values: fit)
    if accepted:
        assert s.prepare_null(growth).modulus == modulus
    else:
        with pytest.raises(s.NullModelError):
            s.prepare_null(growth)


@pytest.mark.parametrize("observed,draws,expected", [(2., [2., 2., 2.], 1.),
                                                  (2., [0., 1., 1.5], .25),
                                                  (2., [3., 4., 5.], 1.),
                                                  (-2., [-3., -2., -1.], .75),
                                                  (2., [], None)])
def test_pvalue_ties_tail_plus_one_and_empty(observed, draws, expected):
    assert s.monte_carlo_pvalue(observed, draws) == expected


@pytest.mark.parametrize("observed,draws", [(np.nan, [1]), (1, [np.inf]), (1, [[1, 2]])])
def test_pvalue_invalid_inputs(observed, draws):
    with pytest.raises(ValueError):
        s.monte_carlo_pvalue(observed, draws)


def test_observed_statistic_matches_separate_rolling_and_episode_calculation(growth):
    expected = pre_onset_changes(max_modulus(growth), [e.onset for e in episodes(growth)])
    result = s.csd_test(growth, B=3, rng=generator())
    assert result.observed == expected
    assert result.observed.eligible_onsets == (48, 60)
    assert result.requested == result.attempted == 3
    assert result.attempted == result.retained + result.no_episode + result.failed
    assert result.failed == 0


@pytest.mark.parametrize("kind", ["residual", "wild"])
def test_reproducible_seed_and_stream_advancement(growth, kind):
    rng = generator()
    first = s.csd_test(growth, B=3, rng=rng, innovation_mode=kind)
    repeat = s.csd_test(growth, B=3, rng=generator(), innovation_mode=kind)
    assert first == repeat
    assert first.rng_before != first.rng_after
    assert rng.bit_generator.state == first.rng_after
    second = s.csd_test(growth, B=3, rng=rng, innovation_mode=kind)
    assert second.rng_before == first.rng_after
    assert second.rng_after != first.rng_after


def test_observed_no_eligible_episode_consumes_no_randomness():
    values = generator().uniform(1, 3, size=90)
    values[30:32] = [-1, -.6]  # A real run, but before the first eligible onset.
    rng = generator()
    before = deepcopy(rng.bit_generator.state)
    result = s.csd_test(values, B=5, rng=rng)
    assert result.status == "observed_not_estimable"
    assert result.observed.ineligible_onsets == (30,)
    assert result.observed.mean_change is result.p_value is None
    assert result.attempted == result.retained == result.no_episode == result.failed == 0
    assert result.null_model is None and result.attempts == ()
    assert result.rng_before == result.rng_after == before == rng.bit_generator.state


def test_mixed_empty_surrogates_drop_without_replacement(growth, monkeypatch):
    supplied = iter([np.abs(growth), growth.copy(), np.abs(growth), growth.copy()])
    monkeypatch.setattr(s, "draw_surrogate", lambda *args, **kwargs: next(supplied))
    result = s.csd_test(growth, B=4, rng=generator())
    assert result.status == "ok"
    assert (result.attempted, result.retained, result.no_episode, result.failed) == (4, 2, 2, 0)
    assert [r.number for r in result.attempts] == [0, 1, 2, 3]
    assert result.exceedances == 2 and result.p_value == 1
    assert result.p_grid_spacing == 1/3
    with pytest.raises(StopIteration):
        next(supplied)


def test_no_retained_surrogates_means_no_pvalue(growth, monkeypatch):
    monkeypatch.setattr(s, "draw_surrogate", lambda *args, **kwargs: np.abs(growth))
    result = s.csd_test(growth, B=3, rng=generator())
    assert result.status == "no_retained_surrogates"
    assert (result.attempted, result.retained, result.no_episode, result.failed) == (3, 0, 3, 0)
    assert result.p_value is result.p_grid_spacing is result.exceedances is None


def test_fixed_onsets_do_not_require_surrogate_recessions(growth, monkeypatch):
    positive = np.abs(growth)
    assert episodes(positive) == ()
    monkeypatch.setattr(s, "draw_surrogate", lambda *args, **kwargs: positive)
    result = s.csd_test(growth, B=3, rng=generator(), onset_mode="fixed")
    expected = pre_onset_changes(max_modulus(positive), [48, 60])
    assert result.status == "ok"
    assert (result.attempted, result.retained, result.no_episode, result.failed) == (3, 3, 0, 0)
    assert all(r.eligible_onsets == (48, 60) and r.changes == expected.changes for r in result.attempts)


@pytest.mark.parametrize("bad", ["generation", "rolling"])
def test_failure_invalidates_pvalue_and_remaining_attempts_continue(growth, monkeypatch, bad):
    supplied = iter(["bad", "empty", "good", "good"])

    def draw(*args, **kwargs):
        item = next(supplied)
        if item == "bad":
            if bad == "generation":
                raise FloatingPointError("deliberate test failure")
            rank_deficient = np.ones(90)
            rank_deficient[48:50] = -1
            return rank_deficient
        return np.abs(growth) if item == "empty" else growth.copy()

    monkeypatch.setattr(s, "draw_surrogate", draw)
    result = s.csd_test(growth, B=4, rng=generator())
    assert result.status == "invalid_surrogate_failure" and result.p_value is None
    assert (result.attempted, result.retained, result.no_episode, result.failed) == (4, 2, 1, 1)
    assert result.attempts[0].error
    assert result.attempts[-1].status == "retained"


def test_null_fit_failure_happens_before_any_random_draw(growth, monkeypatch):
    def fail(values):
        raise s.NullModelError("deliberate null failure")
    monkeypatch.setattr(s, "prepare_null", fail)
    rng = generator()
    before = deepcopy(rng.bit_generator.state)
    with pytest.raises(s.NullModelError):
        s.csd_test(growth, B=3, rng=rng)
    assert rng.bit_generator.state == before


@pytest.mark.parametrize("options", [{"B": 0}, {"B": True}, {"window": 4}, {"lookback": 0},
                                     {"merge": -1}, {"onset_mode": "unknown"},
                                     {"innovation_mode": "unknown"}, {"rng": None}])
def test_bad_parameters_rejected_before_rng_consumption(growth, options):
    rng = generator()
    before = deepcopy(rng.bit_generator.state)
    kwargs = dict(B=3, rng=rng)
    kwargs.update(options)
    with pytest.raises(ValueError):
        s.csd_test(growth, **kwargs)
    assert rng.bit_generator.state == before


def test_input_chronology_and_nonfinite_values_are_rejected(growth):
    bad = growth.copy()
    bad[3] = np.nan
    series = pd.Series(growth, index=pd.period_range("2000Q1", periods=90, freq="Q"))
    for values in (bad, series.iloc[::-1], series.drop(series.index[10])):
        with pytest.raises(ValueError):
            s.csd_test(values, B=3, rng=generator())


def test_generator_does_not_touch_global_random_state(growth):
    before = np.random.get_state()
    s.csd_test(growth, B=3, rng=generator())
    after = np.random.get_state()
    assert before[0] == after[0]
    np.testing.assert_array_equal(before[1], after[1])
    assert before[2:] == after[2:]


def test_nonfinite_recursion_fails_explicitly():
    with pytest.raises(FloatingPointError):
        s.simulate_ar2((1e308, 0), 0, (1, 1e308), [0])
