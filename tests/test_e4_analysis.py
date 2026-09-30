"""E4 sections 7-10 assembled on a constructed workbook (arbitrary numbers; development run, seed 20260930)."""
import datetime as dt
import json

import numpy as np
import pytest

from e4_artificial import DEV_SEED, ar_tables, make_tables
from uc_core.validation_runner import serial
from uc_e4.analysis import analyze
from uc_e4.descriptive import first_vintage_showing_onset, quarter_last_day
from uc_e4.procedure import EpisodeInput, compare, measure
from uc_e4.streams import DEVELOPMENT_STREAMS as DS, REGISTERED_STREAMS, RegisteredRunRefused, stream_rng
from uc_e4.vintage import REGISTERED_ONSETS, H1Episode, select_episodes

B = 6
FINAL = (-0.1722, -0.0638, -0.2034, 0.0662)


def h1_eps():
    return tuple(H1Episode(j, o, FINAL[j]) for j, o in enumerate(REGISTERED_ONSETS))


@pytest.fixture(scope="module")
def tables():
    return ar_tables()


@pytest.fixture(scope="module")
def result(tables):
    return analyze(tables, h1_eps(), master_seed=DEV_SEED, streams=DS, B=B, interval_B=200,
                   release_dates={"Feb 2016": dt.date(1974, 2, 14)})


def test_all_four_episodes_are_eligible_with_their_first_vintages(result):
    assert result["m_E4"] == 4 and result["status"] == "ok"
    sel = result["selections"]
    assert [s["vintage_label"] for s in sel] == ["Feb 2016", "Mar 2016", "Apr 2016", "May 2016"]
    assert [s["series"]["n_v"] for s in sel] == [73, 99, 141, 212]
    assert [s["j"] for s in sel] == [0, 1, 2, 3]


def test_primary_equals_the_procedure_run_on_the_same_series(tables, result):
    sel = select_episodes(tables, h1_eps())
    eps = [EpisodeInput(s.j, s.series.growth) for s in sel]
    direct = compare(eps, {e.j: stream_rng(DEV_SEED, DS.primary, e.j, 0) for e in eps}, B=B, comparators=True)
    assert result["S_rt"] == direct.primary.observed.value
    assert result["raw_p"] == direct.primary.p_value
    deltas = [measure(e.growth, window=40)["primary"][1] for e in eps]
    assert result["S_rt"] == float(np.mean(deltas)) and result["k"] == sum(d > 0 for d in deltas)
    assert result["holm_input"] == result["raw_p"] and result["raw_p_label"] == "raw, not family-adjusted"


def test_secondary_table_has_the_six_registered_rows_with_their_own_denominators(result):
    rows = result["secondary_table"]
    assert [r["window"] for r in rows] == [40, 32, 48, 40, 40, 40]
    assert all(r["status"] == "ok" and r["p_label"] == "raw, not family-adjusted" for r in rows)
    assert all(r["attempted"] == B and r["B_prime"] == B and r["failed"] == 0 for r in rows)
    assert rows[0]["m"] == 4 and rows[1]["m"] == 4 and rows[2]["m"] == 4     # n_v 73, 99, 141, 212 all >= 56
    assert rows[4]["m"] == 4 and rows[5]["m"] == 4                         # Kendall needs n_v >= 55: all four have it


def test_window_specific_selection_and_kendall_denominator(tables, result):
    # n_v = 73 is >= 40, 48, 55, 56: every episode is eligible everywhere in this table
    assert [s["status"] for s in result["selections_w32"]] == ["eligible"] * 4
    assert [s["status"] for s in result["selections_w48"]] == ["eligible"] * 4
    tr = result["comparisons"]["primary"].trend
    assert tr.observed.eligible_onsets == (0, 1, 2, 3)


def test_streams_are_per_analysis(tables):
    a = analyze(tables, h1_eps(), master_seed=DEV_SEED, streams=DS, B=B, interval_B=50)
    b = analyze(tables, h1_eps(), master_seed=DEV_SEED, streams=DS, B=B, interval_B=50)
    assert json.dumps(serial(a["secondary_table"]), sort_keys=True) == json.dumps(serial(b["secondary_table"]), sort_keys=True)
    ps = {r["analysis"]: [x.statistic for x in c.attempts] for r, c in
          zip(a["secondary_table"][:4], [a["comparisons"][k].primary for k in ("primary", "window32", "window48", "wild")])}
    assert len({tuple(v) for v in ps.values()}) == 4            # four different stream ids give four different path sets


def test_episode_interval_uses_the_delta_values_and_stream_5405_analogue(result):
    from uc_core.secondary import episode_percentile_interval
    obs = result["comparisons"]["primary"].primary.observed
    direct = episode_percentile_interval(obs.components, rng=stream_rng(DEV_SEED, DS.interval, 0, 0), B=200)
    assert tuple(result["episode_interval"]["interval"]) == direct.interval


def test_real_time_against_final_table(result):
    t = result["real_time_against_final"]
    assert [r["onset"] for r in t["rows"]] == ["1973Q3", "1980Q1", "1990Q3", "2008Q2"]
    assert t["rows"][0]["release_basis"] == "ONS metadata" and t["rows"][1]["release_basis"] == "label month only"
    for r, f in zip(t["rows"], FINAL):
        assert r["delta_final"] == f and r["difference"] == r["delta_rt"] - f
    s = t["summary"]
    assert s["m_E4"] == 4 and s["S_final_m"] == float(np.mean(FINAL))
    assert s["mean_difference"] == s["S_rt"] - s["S_final_m"]
    assert s["same_sign"] == sum((np.sign(r["delta_rt"]) == np.sign(f)) for r, f in zip(t["rows"], FINAL))


def test_two_clocks_table(result):
    rows = result["two_clocks"]["rows"]
    assert rows[0]["reference_quarter"] == "1973Q2" and rows[0]["vintage"] == "Feb 2016"
    assert rows[0]["release_date"] == "1974-02-14" and rows[0]["release_before_end_of_onset_quarter"] is False
    assert rows[0]["onset_quarter_ends"] == "1973-09-30"
    assert rows[1]["release_basis"] == "label month only" and rows[1]["release_before_end_of_onset_quarter"] is False
    assert rows[0]["previous_vintage"] == "Jan 2016" and rows[0]["months_since_previous"] == 1


def test_quarter_end_dates():
    assert quarter_last_day((1973, 3)) == dt.date(1973, 9, 30)
    assert quarter_last_day((1980, 1)) == dt.date(1980, 3, 31)
    assert quarter_last_day((2008, 4)) == dt.date(2008, 12, 31)


def test_first_vintage_showing_the_onset():
    # constructed levels: growth of q_j and q_j + 1 negative only from vintage 2 on; none before
    onset = (1973, 3)
    over = {}
    for k in range(6):
        y_prev, y_o, y_n = 100.0, (99.0 if k >= 2 else 101.0), (98.0 if k >= 2 else 102.0)
        over[(k, (1973, 2))], over[(k, (1973, 3))], over[(k, (1973, 4))] = y_prev, y_o, y_n
    t = make_tables(overrides=over, covers={k: ((1955, 1), (1975, 4)) for k in range(6)})
    k = first_vintage_showing_onset(t.availability, t.levels, onset)
    assert k == 2
    over2 = {key: (101.0 if key[1] != (1973, 2) else 100.0) for key in over}
    t2 = make_tables(overrides=over2, covers={k: ((1955, 1), (1975, 4)) for k in range(6)})
    assert first_vintage_showing_onset(t2.availability, t2.levels, onset) is None
    # a vintage lacking q_j + 1 does not show it
    over3 = {**over, **{(k, (1973, 4)): None for k in range(6)}}
    t3 = make_tables(overrides=over3, covers={k: ((1955, 1), (1973, 3)) for k in range(6)})
    assert first_vintage_showing_onset(t3.availability, t3.levels, onset) is None


def test_no_eligible_episode_is_not_estimable_and_enters_holm_with_one():
    covers = {k: ((1955, 1), (2019, 4)) for k in range(6)}
    t = make_tables(last_row=(2019, 4), covers=covers)             # every vintage has everything: first release unverifiable
    r = analyze(t, h1_eps(), master_seed=DEV_SEED, streams=DS, B=B, interval_B=50)
    assert r["status"] == "not_estimable" and r["m_E4"] == 0 and r["raw_p"] is None and r["holm_input"] == 1.0
    assert r["episode_interval"]["status"] == "no_eligible_episode"
    assert all(s["failed_step"] == "7.2" for s in r["selections"])
    assert r["comparisons"]["primary"].generated_attempts == 0


def test_registered_coordinates_are_refused_without_the_gate_flag(tables):
    with pytest.raises(RegisteredRunRefused):
        analyze(tables, h1_eps(), master_seed=1927, streams=REGISTERED_STREAMS, B=B)
    with pytest.raises(RegisteredRunRefused):
        analyze(tables, h1_eps(), master_seed=DEV_SEED, streams=REGISTERED_STREAMS, B=B)


def test_the_result_is_serialisable_and_labelled(result):
    text = json.dumps(serial({k: v for k, v in result.items() if k != "comparisons"}), default=str)
    assert '"development run"' in text
    assert result["run"]["registered"] is False and result["run"]["master_seed"] == DEV_SEED
