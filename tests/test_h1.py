from copy import deepcopy

import numpy as np
import pytest

from uc_core import h1, surrogate as s
from uc_core.constants import analysis_rng, STREAM_IDS
from uc_core.recession import pre_onset_changes
from uc_core.rolling import max_modulus
from uc_core.secondary import SecondaryStatisticError


@pytest.fixture
def growth():
    values = np.random.default_rng(719274).uniform(1, 3, size=100)
    values[48:50] = [-1, -.6]
    values[60:62] = [-1, -.6]
    return values


def test_shared_paths_preserve_primary_results_and_rng_exactly(growth):
    baseline = s.csd_test(growth, B=12, rng=np.random.default_rng(2917))
    joint = h1.primary_with_comparators(growth, B=12, rng=np.random.default_rng(2917))
    for field in ("p_value", "attempted", "retained", "no_episode", "failed", "exceedances", "attempts"):
        assert getattr(joint.primary, field) == getattr(baseline, field)
    assert joint.primary.observed.value == baseline.observed.mean_change
    assert joint.rng_before == baseline.rng_before and joint.rng_after == baseline.rng_after
    assert joint.null_model == baseline.null_model


def test_secondary_eligibility_uses_same_paths_and_separate_denominators(growth, monkeypatch):
    early = np.abs(growth)
    early[48:50] = [-1, -.6]
    supplied = iter([early, growth.copy(), growth.copy()])
    monkeypatch.setattr(s, "draw_surrogate", lambda *args, **kwargs: next(supplied))
    joint = h1.primary_with_comparators(growth, B=3, rng=np.random.default_rng(99))
    assert joint.generated_attempts == 3
    assert joint.primary.retained == joint.lag1.retained == 3
    assert joint.trend.retained == 2 and joint.trend.no_episode == 1
    assert joint.trend.observed.eligible_onsets == (60,)
    assert joint.primary.observed.eligible_onsets == (48, 60)
    assert joint.trend.p_grid_spacing == 1/3
    assert joint.primary.p_grid_spacing == 1/4


def test_surrogate_trend_failure_does_not_invalidate_primary(growth, monkeypatch):
    original = h1.mean_pre_onset_trend
    calls = 0
    def trend(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SecondaryStatisticError("test undefined trend")
        return original(*args, **kwargs)
    monkeypatch.setattr(h1, "mean_pre_onset_trend", trend)
    monkeypatch.setattr(s, "draw_surrogate", lambda *args, **kwargs: growth.copy())
    joint = h1.primary_with_comparators(growth, B=3, rng=np.random.default_rng(99))
    assert joint.trend.failed == 1 and joint.trend.p_value is None
    assert joint.trend.attempted == 3
    assert joint.primary.p_value == joint.lag1.p_value == 1
    assert joint.primary.failed == joint.lag1.failed == 0


def test_generation_failure_invalidates_all_estimable_statistics(growth, monkeypatch):
    def fail(*args, **kwargs):
        raise FloatingPointError("test generation failure")
    monkeypatch.setattr(s, "draw_surrogate", fail)
    joint = h1.primary_with_comparators(growth, B=3, rng=np.random.default_rng(99))
    for result in (joint.primary, joint.trend, joint.lag1):
        assert result.failed == result.attempted == 3
        assert result.status == "invalid_surrogate_failure" and result.p_value is None


def test_unobserved_trend_has_zero_statistic_attempts(growth, monkeypatch):
    growth[60:62] = 2
    monkeypatch.setattr(s, "draw_surrogate", lambda *args, **kwargs: growth.copy())
    joint = h1.primary_with_comparators(growth, B=3, rng=np.random.default_rng(99))
    assert joint.primary.retained == 3
    assert joint.trend.status == "observed_not_estimable"
    assert joint.trend.attempted == 0 and joint.trend.p_value is None


def test_empty_observed_series_consumes_no_rng(growth):
    rng = np.random.default_rng(99)
    before = deepcopy(rng.bit_generator.state)
    joint = h1.primary_with_comparators(np.abs(growth), B=3, rng=rng)
    assert joint.generated_attempts == 0 and joint.null_model is None
    assert joint.rng_before == joint.rng_after == before
    assert all(r.status == "observed_not_estimable" for r in (joint.primary, joint.trend, joint.lag1))


def test_external_fixed_dates_need_no_recessions(growth):
    growth = np.abs(growth)
    expected = pre_onset_changes(max_modulus(growth), [48, 60])
    result = h1.fixed_date_test(growth, [48, 60], B=4, rng=np.random.default_rng(71))
    assert result.observed == expected
    assert result.retained == result.attempted == 4
    assert result.no_episode == result.failed == 0
    assert all(a.eligible_onsets == (48, 60) for a in result.attempts)


@pytest.mark.parametrize("dates", [[-1], [48, 48], [60, 48], [100], [48.0], [True], None])
def test_external_dates_validation_before_rng(growth, dates):
    rng = np.random.default_rng(99)
    before = deepcopy(rng.bit_generator.state)
    with pytest.raises(ValueError):
        h1.fixed_date_test(growth, dates, B=3, rng=rng)
    assert before == rng.bit_generator.state


def test_external_dates_all_ineligible_no_draws(growth):
    result = h1.fixed_date_test(growth, [40], B=3, rng=np.random.default_rng(71))
    assert result.status == "observed_not_estimable" and result.attempted == 0
    assert result.rng_before == result.rng_after


def test_registered_stream_coordinates_are_reproducible_and_distinct():
    states = [repr(analysis_rng(name).bit_generator.state) for name in STREAM_IDS]
    assert len(set(states)) == len(STREAM_IDS)
    for cell, replicate in [(0, 0), (1, 0), (0, 1)]:
        actual = analysis_rng("primary", cell=cell, replicate=replicate)
        expected = np.random.Generator(np.random.PCG64(np.random.SeedSequence([1927, 100, cell, replicate])))
        np.testing.assert_array_equal(actual.integers(0, 10000, 12), expected.integers(0, 10000, 12))
    assert analysis_rng("primary", cell=1).bit_generator.state != analysis_rng("primary", replicate=1).bit_generator.state
    with pytest.raises(ValueError):
        analysis_rng("typo")
    for coordinate in [-1, True, .5]:
        with pytest.raises(ValueError):
            analysis_rng("primary", cell=coordinate)


def test_full_in_memory_assembly_has_every_prespecified_output(growth):
    result = h1.analyze_h1(growth, B=2, interval_B=20)
    assert set(result) == {"input_sha256", "joint", "window32", "window48", "fixed", "wild", "episode_interval"}
    assert result["episode_interval"].episode_count == 2
    assert result["episode_interval"].attempted == 20
    for name in ["window32", "window48", "fixed", "wild"]:
        assert result[name].attempted == 2


def test_secondary_observed_failure_remains_a_reported_result(growth, monkeypatch):
    original = s.csd_test
    def maybe_fail(*args, **kwargs):
        if kwargs.get("window") == 32:
            raise ValueError("test sensitivity failure")
        return original(*args, **kwargs)
    monkeypatch.setattr(s, "csd_test", maybe_fail)
    result = h1.analyze_h1(growth, B=2, interval_B=20)
    assert result["window32"]["status"] == "observed_statistic_failed"
    assert result["window32"]["p_value"] is None
    assert result["wild"].attempted == 2


def test_failed_observed_primary_does_not_hide_computable_comparator(growth):
    growth[:40] = np.linspace(1,3,40)
    result = h1.analyze_h1(growth, B=2, interval_B=20)
    assert result["joint"].primary.status == "observed_statistic_failed"
    assert result["joint"].primary.attempted == 0
    assert result["joint"].lag1.observed.status == "ok"
    assert result["joint"].lag1.attempted == 2
    assert result["episode_interval"]["status"] == "observed_statistic_failed"


def test_failed_null_keeps_observed_statistics_without_drawing(growth, monkeypatch):
    def fail(*args, **kwargs):
        raise s.NullModelError("deliberate unusable null")
    monkeypatch.setattr(s,"prepare_null",fail)
    result = h1.primary_with_comparators(growth,B=3,rng=np.random.default_rng(11))
    assert result.primary.observed.value is not None
    assert result.primary.status == "null_model_failed"
    assert result.null_error == "deliberate unusable null"
    assert result.generated_attempts == 0 and result.rng_before == result.rng_after


def test_sensitivity_null_failure_preserves_observed_value_and_cause(growth, monkeypatch):
    original = s.csd_test
    def fail_fixed(*args, **kwargs):
        if kwargs.get("onset_mode") == "fixed":
            raise s.NullModelError("test sensitivity null failure")
        return original(*args, **kwargs)
    monkeypatch.setattr(s,"csd_test",fail_fixed)
    result = h1.analyze_h1(growth,B=2,interval_B=20)
    assert result["fixed"]["status"] == "null_model_failed"
    assert result["fixed"]["observed"].mean_change == result["joint"].primary.observed.value
    assert result["fixed"]["attempted"] == 0 and result["fixed"]["requested"] == 2
