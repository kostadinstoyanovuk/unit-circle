"""prereg/E4.md Annex A and section 10: generator coordinates, the stream of every comparison, and the guard.

Generators in the expected values are built directly from SeedSequence([seed, stream, cell, replicate]) with
PCG64, not with the package's own builder. The registered master seed and stream ids appear only where a test proves
a refusal. Development run on constructed data (seed 20260930, stream ids from 9000, small B).
"""
import dataclasses

import numpy as np
import pytest

import e4_review_support as R
from uc_core.secondary import episode_percentile_interval
from uc_e4.analysis import analyze
from uc_e4.procedure import EpisodeInput, compare
from uc_e4.streams import (DEVELOPMENT_STREAMS as DS, REGISTERED_IDS_TO_AVOID, REGISTERED_STREAMS,
                           RegisteredRunRefused, Streams, check_run, stream_rng)
from uc_e4.vintage import H1Episode

FINAL = (-0.17, -0.06, -0.20, 0.07)            # arbitrary Delta_final values for the descriptive table


@pytest.mark.parametrize("stream,cell,replicate", [(9400, 0, 0), (9400, 3, 0), (9421, 4, 17), (9431, 32, 199)])
def test_generator_coordinates_are_seed_stream_cell_replicate_in_that_order(stream, cell, replicate):
    code = stream_rng(R.DEV_SEED, stream, cell, replicate).integers(0, 2 ** 62, size=6)
    direct = R.generator(R.DEV_SEED, stream, cell, replicate).integers(0, 2 ** 62, size=6)
    assert np.array_equal(code, direct)


def test_cell_and_replicate_are_not_interchangeable():
    a = stream_rng(R.DEV_SEED, 9421, 1, 2).integers(0, 2 ** 62, size=4)
    b = stream_rng(R.DEV_SEED, 9421, 2, 1).integers(0, 2 ** 62, size=4)
    assert not np.array_equal(a, b)


def test_registered_stream_plan_is_annex_a_and_never_uses_5403():
    assert REGISTERED_STREAMS == Streams(primary=5400, window32=5401, window48=5402, wild=5404, interval=5405,
                                         size_generation=5420, size_null=5421, power_generation=5430,
                                         power_null=5431)
    ids = REGISTERED_STREAMS.ids()
    assert len(set(ids)) == len(ids) == 9 and 5403 not in ids
    assert all(i in REGISTERED_IDS_TO_AVOID for i in ids) and 5403 in REGISTERED_IDS_TO_AVOID
    dev = DS.ids()
    assert len(set(dev)) == len(dev) and min(dev) >= 9000 and not set(dev) & set(REGISTERED_IDS_TO_AVOID)


@pytest.mark.parametrize("field", [f.name for f in dataclasses.fields(Streams)])
@pytest.mark.parametrize("registered_id", [100, 105, 401, 1001, 2012, 5100, 5403, 5431])
def test_a_development_run_refuses_any_registered_id_in_any_role(field, registered_id):
    with pytest.raises(RegisteredRunRefused):
        check_run(R.DEV_SEED, dataclasses.replace(DS, **{field: registered_id}))


@pytest.mark.parametrize("flag", [False, 1, "True", np.True_])
def test_the_registered_seed_needs_the_flag_to_be_exactly_true(flag):
    with pytest.raises(RegisteredRunRefused):
        check_run(1927, REGISTERED_STREAMS, allow_registered=flag)
    with pytest.raises(RegisteredRunRefused):
        check_run(np.int64(1927), REGISTERED_STREAMS, allow_registered=flag)


def test_ids_below_9000_are_refused_and_bad_coordinates_are_errors():
    with pytest.raises(RegisteredRunRefused):
        check_run(R.DEV_SEED, dataclasses.replace(DS, wild=8999))
    for seed in (True, -1, 1.5):
        with pytest.raises(ValueError):
            check_run(seed, DS)
    for coordinates in ((R.DEV_SEED, 9400, -1, 0), (R.DEV_SEED, 9400, 0, True), (R.DEV_SEED, 9400.0, 0, 0)):
        with pytest.raises(ValueError):
            stream_rng(*coordinates)


@pytest.mark.parametrize("coordinates", [(1927, 5400, 0, 0), (R.DEV_SEED, 5400, 0, 0), (1927, 9400, 0, 0),
                                         (R.DEV_SEED, 5431, 3, 7), (np.int64(1927), 9400, 0, 0)])
def test_the_generator_builder_refuses_registered_coordinates_without_the_gate_flag(coordinates):
    for flag in (False, None, 1, "yes"):
        with pytest.raises(RegisteredRunRefused):
            stream_rng(*coordinates, allow_registered=flag)       # the flag must be exactly True


def test_the_gate_flag_lets_the_builder_make_the_registered_generators_of_annex_a():
    expected = R.generator(1927, 5400, 3, 0).integers(0, 2 ** 62, size=6)
    assert np.array_equal(stream_rng(1927, 5400, 3, 0, allow_registered=True).integers(0, 2 ** 62, size=6),
                          expected)
    development = R.generator(R.DEV_SEED, 9400, 3, 0).integers(0, 2 ** 62, size=6)
    assert np.array_equal(stream_rng(R.DEV_SEED, 9400, 3, 0).integers(0, 2 ** 62, size=6), development)


def test_the_entry_points_pass_the_verified_gate_on_to_the_builder():
    from uc_core.validation_design import h1_design_series
    from uc_e4 import synthetic as Y
    # Only the generation of the series is made here: no registered analysis is run (stream ids and seed of Annex A).
    for check, cell, stream in (("size", 0, 5420), ("power", 2, 5430)):
        kappas = Y.KAPPAS
        series = Y.x3_input(check, cell, 5, master_seed=1927, streams=REGISTERED_STREAMS, kappas=kappas,
                            allow_registered=True)
        direct = h1_design_series(R.generator(1927, stream, cell, 5), kappa=1.0 if check == "size" else kappas[cell])
        assert np.array_equal(series, direct)
        with pytest.raises(RegisteredRunRefused):
            Y.x3_input(check, cell, 5, master_seed=1927, streams=REGISTERED_STREAMS, kappas=kappas)
    # a development run needs no flag and still reaches the builder
    assert len(Y.x3_input("size", 0, 1, master_seed=R.DEV_SEED, streams=DS)) == 259


@pytest.fixture(scope="module")
def run():
    tables = R.constructed_tables((45, 52, 60, 90))
    episodes = tuple(H1Episode(j, o, FINAL[j]) for j, o in enumerate(R.ONSETS))
    return tables, analyze(tables, episodes, master_seed=R.DEV_SEED, streams=DS, B=3, interval_B=40)


def test_window_specific_eligibility_with_runs_of_45_52_60_and_90(run):
    _, result = run
    assert [s["status"] for s in result["selections_w32"]] == ["eligible"] * 4
    assert [s["failed_step"] for s in result["selections"]] == ["7.3", None, None, None]
    assert [s["failed_step"] for s in result["selections_w48"]] == ["7.3", "7.3", None, None]
    c = result["comparisons"]
    assert c["window32"].primary.observed.eligible_onsets == (0, 1, 2, 3)
    assert c["primary"].primary.observed.eligible_onsets == (1, 2, 3)
    assert c["wild"].primary.observed.eligible_onsets == (1, 2, 3)
    assert c["window48"].primary.observed.eligible_onsets == (2, 3)
    assert c["primary"].trend.observed.eligible_onsets == (2, 3)                 # Kendall needs n_v >= 55
    assert c["primary"].lag1.observed.eligible_onsets == (1, 2, 3)
    assert result["m_E4"] == 3 and [r["m"] for r in result["secondary_table"]] == [3, 4, 2, 3, 2, 3]


@pytest.mark.parametrize("name,window,kind,stream", [("primary", 40, "residual", "primary"),
                                                      ("window32", 32, "residual", "window32"),
                                                      ("window48", 48, "residual", "window48"),
                                                      ("wild", 40, "wild", "wild")])
def test_each_comparison_draws_from_its_annex_a_stream_with_cell_j(run, name, window, kind, stream):
    tables, result = run
    key = {"primary": "selections", "window32": "selections_w32", "window48": "selections_w48",
           "wild": "selections"}[name]
    eligible = [s for s in result[key] if s["status"] == "eligible"]
    episodes = [EpisodeInput(s["j"], np.asarray(s["series"]["growth"])) for s in eligible]
    rngs = {e.j: R.generator(R.DEV_SEED, getattr(DS, stream), e.j, 0) for e in episodes}
    direct = compare(episodes, rngs, window=window, B=3, kind=kind, comparators=(name == "primary"))
    code = result["comparisons"][name]
    assert [a.statistic for a in code.primary.attempts] == [a.statistic for a in direct.primary.attempts]
    assert code.rng_after == direct.rng_after
    if name == "primary":
        assert [a.statistic for a in code.trend.attempts] == [a.statistic for a in direct.trend.attempts]
        assert [a.statistic for a in code.lag1.attempts] == [a.statistic for a in direct.lag1.attempts]


def test_the_episode_interval_uses_stream_interval_cell_0_replicate_0(run):
    _, result = run
    obs = result["comparisons"]["primary"].primary.observed
    direct = episode_percentile_interval(obs.components, rng=R.generator(R.DEV_SEED, DS.interval, 0, 0), B=40)
    assert tuple(result["episode_interval"]["interval"]) == direct.interval
    assert result["episode_interval"]["requested"] == 40 and result["episode_interval"]["episode_count"] == 3
