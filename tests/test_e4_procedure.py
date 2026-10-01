"""prereg/E4.md sections 8 and 9: Delta_rt, the per-episode null, the draws, S_b, p, q and the Wilson interval.
Development runs on constructed data only: seed 20260930, stream ids from 9000, small B; not a registered result."""
import math

import numpy as np
import pytest

import uc_core.surrogate as core_surrogate
from e4_artificial import DEV_SEED, growth_series
from uc_core.recession import pre_onset_changes
from uc_core.rolling import max_modulus
from uc_core.validation_design import wilson_interval
from uc_e4 import procedure as P
from uc_e4.procedure import EpisodeInput, compare, measure
from uc_e4.streams import (DEVELOPMENT_STREAMS as DS, REGISTERED_STREAMS, RegisteredRunRefused, check_run,
                           stream_rng)

B = 12


def eps(sizes=(60, 75, 90)):
    return [EpisodeInput(j, growth_series(n, replicate=j)) for j, n in enumerate(sizes)]


def rngs_for(episodes, stream=DS.primary, seed=DEV_SEED):
    return {e.j: stream_rng(seed, stream, e.j, 0) for e in episodes}


def test_delta_agrees_with_uc_core_rolling_modulus_and_pre_onset_changes():
    x = growth_series(120)
    n_v = 70
    vintage = x[:n_v]
    m_vintage = max_modulus(vintage, 40).to_numpy()
    m_long = max_modulus(x, 40).to_numpy()
    assert np.array_equal(m_vintage[39:], m_long[39:n_v])          # causal: later data do not enter a fit
    core = pre_onset_changes(m_long, [n_v], lookback=8)             # onset inside the longer series
    assert core.changes[0] == m_vintage[n_v - 1] - m_vintage[n_v - 9]
    kind, value = measure(vintage, window=40)["primary"]
    assert kind == "ok" and value == core.changes[0]


def test_the_padding_value_is_never_read():
    v = growth_series(70)
    a = P._padded(max_modulus(v, 40).to_numpy())
    b = a.copy()
    b[-1] = 123.0
    assert pre_onset_changes(a, [70]).changes == pre_onset_changes(b, [70]).changes


def test_observed_statistic_is_the_mean_of_the_signed_deltas_and_k_counts_positive():
    e = eps()
    out = compare(e, rngs_for(e), B=B)
    deltas = [measure(x.growth, window=40)["primary"][1] for x in e]
    o = out.primary.observed
    assert o.status == "ok" and o.components == tuple(deltas) and o.eligible_onsets == (0, 1, 2)
    assert o.value == float(np.mean(deltas))
    assert sum(d > 0 for d in deltas) == sum(c > 0 for c in o.components)


def by_hand(e, seed, stream, B, kind="residual"):
    """An independent reconstruction of every attempt, from SeedSequence([seed, stream, j, 0])."""
    rows = []
    fits = {}
    for x in e:
        fit = core_surrogate.fit_ols(x.growth)
        res = np.asarray(fit.residuals) - np.mean(fit.residuals)
        fits[x.j] = (fit, res, stream_rng(seed, stream, x.j, 0))
    for b in range(B):
        deltas = []
        for x in e:
            fit, res, rng = fits[x.j]
            n_v = len(x.growth)
            if kind == "residual":
                innov = res[rng.integers(0, n_v - 2, size=n_v - 2)]
            else:
                innov = res * (2 * rng.integers(0, 2, size=n_v - 2) - 1)
            path = core_surrogate.simulate_ar2(fit.coefficients, fit.intercept, (x.growth[0], x.growth[1]), innov)
            m = max_modulus(path, 40).to_numpy()
            deltas.append(m[n_v - 1] - m[n_v - 9])
        rows.append(deltas)
    return rows


def test_draws_follow_annex_a_and_section_9_exactly():
    e = eps()
    out = compare(e, rngs_for(e), B=B)
    rows = by_hand(e, DEV_SEED, DS.primary, B)
    for b, attempt in enumerate(out.primary.attempts):
        assert attempt.status == "retained" and attempt.number == b
        assert list(attempt.changes) == rows[b]
        assert attempt.statistic == float(np.mean(rows[b]))


def test_wild_signs_follow_section_10_exactly():
    e = eps((60, 75))
    out = compare(e, rngs_for(e, DS.wild), B=B, kind="wild")
    rows = by_hand(e, DEV_SEED, DS.wild, B, kind="wild")
    assert [list(a.changes) for a in out.primary.attempts] == rows


def test_p_q_wilson_arithmetic():
    e = eps()
    out = compare(e, rngs_for(e), B=B).primary
    kept = [a.statistic for a in out.attempts]
    k = sum(v >= out.observed.value for v in kept)
    assert out.exceedances == k and out.retained == B and out.attempted == B and out.failed == 0
    assert out.p_value == (1 + k) / (B + 1) and out.p_grid_spacing == 1 / (B + 1)
    assert out.q == k / B and out.q_wilson == wilson_interval(k, B)
    assert out.p_label == "raw, not family-adjusted"
    assert out.status == "ok" and out.attempted == out.retained + out.no_episode + out.failed


def test_ties_count_as_exceedances():
    # an observed statistic equal to a surrogate statistic is counted (S_b >= S_rt)
    e = eps((60,))
    first = compare(e, rngs_for(e), B=B).primary
    assert core_surrogate.monte_carlo_pvalue(first.attempts[3].statistic, [a.statistic for a in first.attempts]) \
        == (1 + sum(a.statistic >= first.attempts[3].statistic for a in first.attempts)) / (B + 1)


def test_determinism_and_dependence_on_the_seed():
    e = eps()
    a = compare(e, rngs_for(e), B=B)
    b = compare(e, rngs_for(e), B=B)
    assert a.primary.p_value == b.primary.p_value
    assert [x.statistic for x in a.primary.attempts] == [x.statistic for x in b.primary.attempts]
    assert a.rng_after == b.rng_after
    c = compare(e, rngs_for(e, seed=DEV_SEED + 1), B=B)
    assert [x.statistic for x in c.primary.attempts] != [x.statistic for x in a.primary.attempts]


def test_one_episodes_draws_do_not_depend_on_another_episodes_data():
    e = eps((60, 75, 90))
    other = [e[0], EpisodeInput(1, growth_series(101, replicate=41)), e[2]]      # different data and length for j = 1
    a = compare(e, rngs_for(e), B=B)
    b = compare(other, rngs_for(other), B=B)
    for j in (0, 2):
        assert [x.changes[j] for x in a.primary.attempts] == [x.changes[j] for x in b.primary.attempts]
        assert a.rng_after[j] == b.rng_after[j]
    assert [x.changes[1] for x in a.primary.attempts] != [x.changes[1] for x in b.primary.attempts]
    # dropping an episode (unavailable) does not shift the others' generators either
    c = compare([e[0], e[2]], rngs_for(e), B=B)
    assert [x.changes[0] for x in a.primary.attempts] == [x.changes[0] for x in c.primary.attempts]
    assert [x.changes[1] for x in c.primary.attempts] == [x.changes[2] for x in a.primary.attempts]


def test_one_episodes_generation_failure_cannot_shift_another_episodes_draws(monkeypatch):
    e = eps((60, 75))
    clean = compare(e, rngs_for(e), B=B)
    real = core_surrogate.simulate_ar2
    calls = {"n": 0}

    def flaky(coefficients, intercept, initial, innovations):
        if len(innovations) == 73:              # episode 1 only (n_v - 2)
            calls["n"] += 1
            if calls["n"] == 4:
                raise FloatingPointError("forced")
        return real(coefficients, intercept, initial, innovations)
    monkeypatch.setattr(core_surrogate, "simulate_ar2", flaky)
    broken = compare(e, rngs_for(e), B=B)
    p = broken.primary
    assert p.status == "invalid_surrogate_failure" and p.p_value is None and p.failed == 1
    assert p.attempted == B and p.retained == B - 1 and p.attempts[3].status == "failed"
    assert p.attempted == p.retained + p.no_episode + p.failed
    assert broken.rng_after == clean.rng_after                                   # every draw was still consumed
    keep = [a.changes[0] for i, a in enumerate(clean.primary.attempts) if i != 3]
    assert [a.changes[0] for i, a in enumerate(p.attempts) if i != 3] == keep


def test_failed_observed_statistic_fails_the_comparison_and_draws_nothing(monkeypatch):
    e = eps((60, 75))
    x = e[1].growth.copy()
    x[5:47] = 1.5                                            # a constant window: the rolling AR(2) fit is not identifiable
    e2 = [e[0], EpisodeInput(1, x)]
    rngs = rngs_for(e2)
    before = {j: r.bit_generator.state for j, r in rngs.items()}
    out = compare(e2, rngs, B=B)
    assert out.primary.status == "observed_statistic_failed" and out.primary.p_value is None
    assert out.primary.observed.status == "failed" and "episode 1" in out.primary.observed.error
    assert out.generated_attempts == 0 and out.primary.attempted == 0
    assert {j: r.bit_generator.state for j, r in rngs.items()} == before
    # a non-finite modulus at a position Delta_rt requires is a failure too, not an unavailable episode
    def nan_modulus(values, window):
        import pandas as pd
        m = max_modulus(values, window).copy()
        m.iloc[len(values) - 1] = np.nan
        return m
    monkeypatch.setattr(P, "max_modulus", nan_modulus)
    out = compare(e, rngs_for(e), B=B)
    assert out.primary.status == "observed_statistic_failed" and out.primary.observed.eligible_onsets == ()


def test_unstable_or_failed_null_of_any_episode_fails_before_any_draw():
    e = eps((60, 75))
    rng = np.random.default_rng(1)
    z = rng.normal(size=70)
    bad = np.empty(70)
    bad[0], bad[1] = 1.0, 2.0
    for t in range(2, 70):
        bad[t] = 1.1 * bad[t - 1] + 0.02 * bad[t - 2] + 0.05 * z[t]
    with pytest.raises(core_surrogate.NullModelError):
        core_surrogate.prepare_null(bad)
    e2 = [e[0], EpisodeInput(1, bad)]
    rngs = rngs_for(e2)
    before = {j: r.bit_generator.state for j, r in rngs.items()}
    out = compare(e2, rngs, B=B)
    assert out.primary.status == "null_model_failed" and out.primary.p_value is None
    assert out.null_error and out.generated_attempts == 0
    assert {j: r.bit_generator.state for j, r in rngs.items()} == before


def test_no_eligible_episode_is_not_estimable():
    out = compare([], {}, B=B)
    assert out.primary.status == "observed_not_estimable" and out.primary.p_value is None
    assert out.primary.observed.status == "no_eligible_episode" and out.generated_attempts == 0


def test_below_the_eligibility_threshold_is_refused():
    e = [EpisodeInput(0, growth_series(47))]
    with pytest.raises(ValueError):
        compare(e, rngs_for(e), B=B)
    e = [EpisodeInput(0, growth_series(48))]
    assert compare(e, rngs_for(e), B=3).primary.status == "ok"


def test_generators_must_be_explicit_and_per_episode():
    e = eps((60,))
    with pytest.raises(ValueError):
        compare(e, {}, B=B)
    with pytest.raises(ValueError):
        compare(e, {0: None}, B=B)


def test_kendall_and_lag_one_share_the_primary_paths_with_their_own_denominators():
    e = eps((54, 55, 90))                                    # n_v = 54 is below Kendall's 55; 55 and 90 are not
    out = compare(e, rngs_for(e), B=B, comparators=True)
    assert out.primary.observed.eligible_onsets == (0, 1, 2)
    assert out.trend.observed.eligible_onsets == (1, 2) and out.trend.observed.ineligible_onsets == (0,)
    assert out.lag1.observed.eligible_onsets == (0, 1, 2)
    paths = [a.changes for a in out.primary.attempts]
    assert len(paths) == B and out.trend.attempted == B and out.lag1.attempted == B
    assert out.trend.status == "ok" and out.lag1.status == "ok"
    # the primary attempts are the same as without comparators (same paths, same draws)
    plain = compare(e, rngs_for(e), B=B)
    assert [a.statistic for a in plain.primary.attempts] == [a.statistic for a in out.primary.attempts]
    # by hand: tau-b of M(n_v-16..n_v-1) against 0..15, and A(n_v-1) - A(n_v-9), on the observed vintages
    from scipy.stats import kendalltau
    taus = []
    for x in e[1:]:
        m = max_modulus(x.growth, 40).to_numpy()
        taus.append(float(kendalltau(np.arange(16), m[len(x.growth) - 16:], variant="b").statistic))
    assert out.trend.observed.components == tuple(taus) and out.trend.observed.value == float(np.mean(taus))
    a_changes = []
    for x in e:
        g = x.growth
        def A(t):
            v = g[t - 39:t + 1] - g[t - 39:t + 1].mean()
            return float(np.sum(v[1:] * v[:-1]) / np.sum(v * v))
        a_changes.append(A(len(g) - 1) - A(len(g) - 9))
    assert out.lag1.observed.components == tuple(a_changes)


def test_kendall_not_estimable_when_no_episode_reaches_55():
    e = eps((50, 54))
    out = compare(e, rngs_for(e), B=4, comparators=True)
    assert out.trend.status == "observed_not_estimable" and out.trend.attempted == 0
    assert out.primary.status == "ok" and out.lag1.status == "ok"


@pytest.mark.parametrize("window,n_ok,n_bad", [(32, 40, 39), (40, 48, 47), (48, 56, 55)])
def test_window_specific_eligibility_threshold(window, n_ok, n_bad):
    good = [EpisodeInput(0, growth_series(n_ok))]
    assert compare(good, rngs_for(good), window=window, B=2).primary.status == "ok"
    with pytest.raises(ValueError):
        compare([EpisodeInput(0, growth_series(n_bad))], rngs_for(good), window=window, B=2)


def test_streams_guard():
    assert check_run(DEV_SEED, DS) is False
    with pytest.raises(RegisteredRunRefused):
        check_run(1927, REGISTERED_STREAMS)                 # registered seed without the gate flag
    assert check_run(1927, REGISTERED_STREAMS, allow_registered=True) is True
    with pytest.raises(RegisteredRunRefused):
        check_run(1927, DS, allow_registered=True)          # registered seed with other ids
    with pytest.raises(RegisteredRunRefused):
        check_run(DEV_SEED, REGISTERED_STREAMS)             # development seed on registered ids
    with pytest.raises(ValueError):
        check_run(-1, DS)
