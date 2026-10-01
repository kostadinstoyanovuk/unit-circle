"""prereg/E4.md sections 5, 8 and 9 and H1 sections 6 and 8: the records and failure paths of the comparison
and of the vintage series that the other tests leave open.

Failures and ties are forced on constructed data by replacing, inside the test only, the uc_core function that
the comparison calls (the rolling modulus, the surrogate draw, the null fit); the package code is unchanged.
Development run on constructed data: master seed 20260930, stream ids from 9000, small B.
"""
import dataclasses
import datetime as dt
import json
from types import SimpleNamespace

import numpy as np
import pytest

import e4_review_support as R
from uc_e4 import analysis as A
from uc_e4 import descriptive as D
from uc_e4 import procedure as P
from uc_e4 import synthetic as Y
from uc_e4.procedure import EpisodeInput, Observed, compare, measure
from uc_e4.analysis import analyze
from uc_e4.streams import (DEVELOPMENT_STREAMS as DS, REGISTERED_IDS_TO_AVOID, RegisteredRunRefused, check_run,
                           stream_rng)
from uc_e4.table import (RawPart, Stop, build_tables, parse_quarter, parse_release_month, quarter_from_index,
                         quarter_index)
from uc_e4.vintage import H1Episode, load_h1_episodes, vintage_series


def _episodes(sizes=(52, 60, 75)):
    return [EpisodeInput(j, R.constructed_growth(n, replicate=30 + j)) for j, n in enumerate(sizes)]


def _rngs(episodes, stream=DS.primary):
    return {e.j: R.generator(R.DEV_SEED, stream, e.j, 0) for e in episodes}


def test_a_failed_measurement_of_one_surrogate_invalidates_the_p_value(monkeypatch):
    """E4 section 9: "A failure in any episode's attempt b is recorded and invalidates the p-value, as H1 §6."
    The rolling fit of episode 1 fails in attempt 2: a measurement failure, not a generation failure."""
    e = _episodes()
    original, calls = P.max_modulus, {"n": 0}
    fail_at = len(e) * 3 + 2                   # observed fits, attempts 0 and 1, then episode 1 of attempt 2

    def failing_once(values, window):
        calls["n"] += 1
        if calls["n"] == fail_at:
            raise FloatingPointError("constructed failure of one rolling fit")
        return original(values, window)

    monkeypatch.setattr(P, "max_modulus", failing_once)
    B = 4
    out = compare(e, _rngs(e), B=B).primary
    assert out.status == "invalid_surrogate_failure" and out.p_value is None
    assert (out.attempted, out.retained, out.failed) == (B, B - 1, 1)
    bad = [a for a in out.attempts if a.status == "failed"]
    assert [a.number for a in bad] == [2]
    assert bad[0].error == "episode 1: FloatingPointError: constructed failure of one rolling fit"


def test_a_surrogate_statistic_equal_to_the_observed_one_counts_in_k(monkeypatch):
    """E4 section 9: "K = count(S_b ≥ S_rt)"; H1 section 6 counts ties. Every surrogate path is replaced by the
    episode's own series, so every S_b equals S_rt exactly and K must equal B'."""
    e = _episodes()
    series, state = [x.growth for x in e], {"i": 0}

    def own_series(model, rng, kind="residual"):
        rng.integers(0, 2, size=3)
        g = series[state["i"] % len(series)]
        state["i"] += 1
        return np.array(g, copy=True)

    monkeypatch.setattr(P.s, "draw_surrogate", own_series)
    B = 5
    out = compare(e, _rngs(e), B=B).primary
    assert [a.statistic for a in out.attempts] == [out.observed.value] * B
    assert (out.retained, out.exceedances, out.q, out.p_value) == (B, B, 1.0, 1.0)


def test_a_null_failure_records_zero_draws_and_keeps_an_unestimable_comparator(monkeypatch):
    """H1 section 8: "Preserve finite observed statistics if the full-sample null fails and record zero draws
    and the null failure." Every episode is below the Kendall threshold n_v >= W + 15, so the trend
    comparator is not estimable and keeps that status and its zero counts."""
    e = _episodes(sizes=(49, 50, 52))

    def refuse(growth):
        raise P.s.NullModelError("constructed unstable null")

    monkeypatch.setattr(P.s, "prepare_null", refuse)
    out = compare(e, _rngs(e), B=4, comparators=True)
    assert out.null_error == "constructed unstable null" and out.null_models == {} and out.generated_attempts == 0
    for m in (out.primary, out.lag1):
        assert m.status == "null_model_failed" and m.observed.status == "ok" and m.p_value is None
        assert (m.attempted, m.retained, m.no_episode, m.failed, m.exceedances) == (0, 0, 0, 0, None)
    t = out.trend
    assert t is not None and t.status == "observed_not_estimable" and t.observed.status == "no_eligible_episode"
    assert (t.attempted, t.retained, t.no_episode, t.failed, t.exceedances, t.p_value) == (0, 0, 0, 0, None, None)


def test_the_comparison_records_its_window_kind_and_the_attempts_generated():
    e = _episodes()
    out = compare(e, _rngs(e, DS.wild), B=3, kind="wild")
    assert (out.window, out.kind, out.generated_attempts) == (40, "wild", 3)
    assert (out.primary.requested, out.primary.attempted) == (3, 3)


def test_a_window_below_five_observations_is_refused():
    with pytest.raises(ValueError):
        compare((), {}, window=4, B=1)
    assert compare((), {}, window=5, B=1).primary.status == "observed_not_estimable"


def test_a_failed_observed_fit_is_recorded_with_the_first_failing_episode(monkeypatch):
    """H1 section 4: a non-finite or unidentified window fails the statistic; the record names the episode."""
    def failing(values, window):
        raise FloatingPointError("constructed failure")

    monkeypatch.setattr(P, "max_modulus", failing)
    e = _episodes()
    piece = measure(e[0].growth, window=40)["primary"]
    assert piece[0] == "failed" and piece[1].status == "failed" and piece[1].value is None
    out = compare(e, _rngs(e), B=2)
    assert out.primary.status == "observed_statistic_failed" and out.generated_attempts == 0
    assert out.primary.observed.error == "episode 0: FloatingPointError: constructed failure"


def test_the_mean_change_of_an_observed_statistic_is_its_value():
    assert Observed("ok", 0.25).mean_change == 0.25


LABELS = ("Jan 2016", "Feb 2016", "Mar 2016", "Apr 2016", "May 2016")
ROWS = [quarter_from_index(i) for i in range(quarter_index((1955, 1)), quarter_index((1956, 4)) + 1)]
ONSET = (1957, 1)


def _cell(k, q, i):
    """Vintage 0: one level before a gap; 1: two levels; 2: no level for q_j - 1; 3: two non-positive levels;
    4: every level between 0 and 1 (positive, so no stop)."""
    if k == 0:
        return None if q == (1956, 3) else 100.0 + i
    if k == 1:
        return None if q == (1956, 2) else 100.0 + 2 * i
    if k == 2:
        return None if q == (1956, 4) else 100.0 + i
    if k == 3:
        return {(1955, 3): -2.0, (1956, 2): 0.0}.get(q, 100.0 + i)
    return 0.5 + 0.05 * i


def test_vintage_series_records_and_short_runs_follow_section_5():
    """E4 section 5: the run of present quarters ends at q_j - 1, starts no earlier than 1955Q1, and a
    non-positive or non-finite level inside it is a stop; n_v = n_levels - 1 growth values."""
    cells = tuple(tuple(_cell(k, q, i) for k in range(5)) for i, q in enumerate(ROWS))
    t = build_tables([RawPart("hand", LABELS, tuple(f"{y} Q{n}" for y, n in ROWS), cells)])
    av, lv = t.availability, t.levels
    one = vintage_series(av, lv, 0, ONSET)
    assert (one.vintage, one.onset, one.status, one.n_levels, one.n_v) == (0, ONSET, "ok", 1, 0)
    assert one.run_ended_by == "gap:1956Q3" and one.growth.shape == (0,)
    two = vintage_series(av, lv, 1, ONSET)
    assert (two.vintage, two.onset, two.status, two.n_levels, two.n_v, two.first_quarter) == (
        1, ONSET, "ok", 2, 1, (1956, 3))
    assert two.growth == pytest.approx([400 * np.log(114.0 / 112.0)], abs=1e-12)
    none = vintage_series(av, lv, 2, ONSET)
    assert (none.vintage, none.onset, none.status, none.n_levels, none.n_v, none.growth) == (
        2, ONSET, "no_level", 0, 0, None)
    assert none.last_quarter == (1956, 4)
    stop = vintage_series(av, lv, 3, ONSET)
    assert (stop.vintage, stop.onset, stop.status, stop.first_quarter, stop.run_ended_by) == (
        3, ONSET, "stop", (1955, 1), "floor")
    assert stop.growth is None and (stop.n_levels, stop.n_v) == (8, 7)
    assert stop.stop == "non-positive level in the run at 1955Q3 (2 such level(s))"
    small = vintage_series(av, lv, 4, ONSET)
    assert (small.vintage, small.onset, small.status, small.n_v) == (4, ONSET, "ok", 7)
    assert small.growth == pytest.approx(400 * np.diff(np.log([0.5 + 0.05 * i for i in range(8)])), abs=1e-12)


def test_the_h1_record_is_read_from_a_file(tmp_path):
    """Section 4: the four eligible H1 episodes, numbered among those with an available statistic."""
    record = {"episodes": [
        {"statistic_available": True, "onset_quarter": "1973 Q3", "change": -0.5},
        {"statistic_available": False, "onset_quarter": "1975 Q1", "change": None},
        {"statistic_available": True, "onset_quarter": "1980 Q1", "change": 0.25},
        {"statistic_available": True, "onset_quarter": "1990 Q3", "change": -1.0},
        {"statistic_available": True, "onset_quarter": "2008 Q2", "change": 2.0}]}
    path = tmp_path / "constructed_record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert load_h1_episodes(path) == (H1Episode(0, (1973, 3), -0.5), H1Episode(1, (1980, 1), 0.25),
                                      H1Episode(2, (1990, 3), -1.0), H1Episode(3, (2008, 2), 2.0))


def _part(name, labels, rows, value=lambda i, k: 100.0 + i + k):
    return RawPart(name, tuple(labels), tuple(f"{y} Q{n}" for y, n in rows),
                   tuple(tuple(value(i, k) for k in range(len(labels))) for i in range(len(rows))))


def test_two_vintages_suffice_and_the_manifest_names_the_earliest_and_latest():
    """Section 4 step 4 needs release months that increase in one direction, which two vintages can do."""
    m = build_tables([_part("p", ("Jan 2016", "Feb 2016"), ROWS)]).manifest
    assert (m["earliest_vintage"], m["latest_vintage"], m["n_vintages"]) == ("Jan 2016", "Feb 2016", 2)
    assert (m["earliest_vintage_month"], m["latest_vintage_month"]) == ((2016, 1), (2016, 2))


def test_a_descending_part_joined_with_a_single_vintage_part_is_read_in_descending_order():
    """R-4.8: parts are joined in descending order of range when every part with a direction descends; a
    part with a single vintage has no direction."""
    t = build_tables([_part("a", ("Mar 2016", "Feb 2016"), ROWS), _part("b", ("Jan 2016",), ROWS)])
    assert [v.label for v in t.availability.vintages] == ["Jan 2016", "Feb 2016", "Mar 2016"]
    assert t.manifest["parts"] == "a+b"


def test_a_cell_of_kind_other_in_the_last_row_and_column_stops_the_reading():
    """Section 4 step 2: a cell of kind other stops the reading wherever it is."""
    last = len(ROWS) - 1
    with pytest.raises(Stop) as stop:
        build_tables([_part("p", ("Jan 2016", "Feb 2016"), ROWS,
                            lambda i, k: "note 7" if (i, k) == (last, 1) else 100.0 + i)])
    assert stop.value.step == "4.2"


@pytest.mark.parametrize("label,expected", [("1000 Q1", (1000, 1)), ("2999 Q4", (2999, 4)),
                                            ("Quarter 1, 1955", (1955, 1)), ("QTR. 3 1960", (1960, 3))])
def test_reference_quarter_labels_at_the_edges_of_the_accepted_forms(label, expected):
    assert parse_quarter(label) == expected


@pytest.mark.parametrize("label", ["0999 Q1", "3000 Q1"])
def test_years_outside_1000_to_2999_do_not_parse(label):
    with pytest.raises(ValueError):
        parse_quarter(label)


def test_a_release_label_with_a_day_number_from_1_to_31_parses():
    """R-4.4: at most one day number besides the month name and the four-digit year."""
    assert parse_release_month("1 January 2016") == (2016, 1)
    assert parse_release_month("31 Jan 2016") == (2016, 1)
    with pytest.raises(ValueError):
        parse_release_month("32 Jan 2016")


def test_registered_attempt_and_resample_counts():
    """E4 section 9: B = 1,000 attempts; section 10: 10,000 episode resamples; section 11: 0.02 to 0.09."""
    assert (A.SURROGATE_ATTEMPTS, A.EPISODE_RESAMPLES, Y.SURROGATE_ATTEMPTS) == (1000, 10000, 1000)
    assert Y.SIZE_BOUNDS == (0.02, 0.09) and Y.ONSETS == (49, 99, 149, 199, 249)


def _no_series(rng, kappa=1.0):
    raise FloatingPointError("constructed generation failure")


def test_a_generation_failure_is_recorded_with_zero_attempts_and_annex_a_coordinates(monkeypatch):
    """Annex A: power surrogates use stream 5431 with cell = 10 * kappa index + j; a failed generation is
    recorded with zero surrogate attempts (development stream ids stand in for the registered ones)."""
    monkeypatch.setattr(Y, "h1_design_series", _no_series)
    r = Y.power_replicate(2, 3, master_seed=R.DEV_SEED, streams=DS, B=2)
    assert (r["status"], r["cell_index"], r["replicate"]) == ("generation_failed", 2, 3)
    assert r["error"] == "FloatingPointError: constructed generation failure"
    assert (r["surrogate_attempted"], r["surrogate_retained"], r["surrogate_no_episode"], r["surrogate_failed"]) == (
        0, 0, 0, 0)
    assert sorted(r["analysis_rng_before"]) == [0, 1, 2, 3, 4]
    for j in range(5):
        assert r["analysis_rng_before"][j] == R.generator(R.DEV_SEED, DS.power_null, 20 + j, 3).bit_generator.state
    assert r["generation_rng_before"] == R.generator(R.DEV_SEED, DS.power_generation, 2, 3).bit_generator.state
    size = Y.size_replicate(4, master_seed=R.DEV_SEED, streams=DS, B=2)
    assert (size["cell_index"], size["replicate"]) == (0, 4) and sorted(size["analysis_rng_before"]) == [0, 1, 2, 3, 4]
    assert size["analysis_rng_before"][4] == R.generator(R.DEV_SEED, DS.size_null, 4, 4).bit_generator.state


def test_the_progress_callback_receives_each_record_as_it_is_made(monkeypatch):
    monkeypatch.setattr(Y, "h1_design_series", _no_series)
    seen = []
    Y.run_power_check(master_seed=R.DEV_SEED, streams=DS, n_series=2, B=1, kappas=(1.0, 1.2), progress=seen.append)
    assert [(r["cell_index"], r["replicate"]) for r in seen] == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_months_between_and_the_sign_convention_of_the_descriptive_table():
    assert D.months_between((2015, 11), (2016, 2)) == 3 and D.months_between((2016, 2), (2016, 2)) == 0
    assert [D._sign(x) for x in (0.0, -0.0, 2.5, -1e-300)] == [0, 0, 1, -1]


def test_the_first_vintage_showing_an_onset_needs_both_quarters_negative():
    """Descriptive table (section 10): the first vintage in which quarters q_j and q_j + 1 both show negative
    growth. Vintage 0 shows only q_j + 1 falling, vintage 1 only q_j, and the last vintage shows two small
    falls (growth between -1 and 0), so the answer is the last vintage."""
    levels = {0: (104.0, 105.0, 95.0), 1: (104.0, 95.0, 106.0), 2: (104.0, 103.9, 103.8)}
    quarters = ((1956, 1), (1956, 2), (1956, 3))

    def value(i, k):
        return levels[k][quarters.index(ROWS[i])] if ROWS[i] in quarters else 100.0 + i
    t = build_tables([_part("p", ("Jan 2016", "Feb 2016", "Mar 2016"), ROWS, value)])
    assert D.first_vintage_showing_onset(t.availability, t.levels, (1956, 2)) == 2


def test_a_release_on_the_last_day_of_the_onset_quarter_and_a_label_month_equal_to_its_last_month():
    """Section 10: whether the release of v_j falls before the end of q_j; a release date on the last day
    counts as before the end, and a label month equal to the last month of q_j cannot be decided."""
    t = build_tables([_part("p", ("Jan 2016", "Feb 2016", "Mar 2016"), ROWS)])
    selections = [SimpleNamespace(j=0, vintage=2, onset=(2016, 1)), SimpleNamespace(j=1, vintage=1, onset=(2016, 1)),
                  SimpleNamespace(j=2, vintage=0, onset=(2016, 1))]
    rows = D.two_clocks(t, selections, {"Jan 2016": dt.date(2016, 3, 31)})["rows"]
    assert [r["release_before_end_of_onset_quarter"] for r in rows] == ["undetermined: label month only", True, True]
    assert [r["release_basis"] for r in rows] == ["label month only", "label month only", "ONS metadata"]


def test_a_release_instant_is_reduced_to_its_date_in_the_two_clocks_table():
    """A release date may arrive as a datetime (the release instant); the question is about the date."""
    t = build_tables([_part("p", ("Jan 2016", "Feb 2016", "Mar 2016"), ROWS)])
    selections = [SimpleNamespace(j=0, vintage=0, onset=(2016, 1))]
    for released, before in ((dt.datetime(2016, 3, 31, 23, 30), True), (dt.datetime(2016, 4, 1, 0, 0), False),
                             (dt.date(2016, 3, 31), True)):
        rows = D.two_clocks(t, selections, {"Jan 2016": released})["rows"]
        assert rows[0]["release_before_end_of_onset_quarter"] is before
        assert rows[0]["release_date"] == released.isoformat() and rows[0]["release_basis"] == "ONS metadata"


def test_the_real_time_table_states_the_label_month_of_the_vintage_where_it_is_given_the_tables():
    """Section 10: the vintage's release date from ONS metadata where it can be established, otherwise the label
    month. Each row states the label month; an episode with no vintage states none."""
    t = build_tables([_part("p", ("Jan 2016", "Feb 2016", "Mar 2016"), ROWS)])

    def selection(j, vintage, label, status="eligible"):
        return SimpleNamespace(j=j, status=status, failed_step=None, reason=None, vintage=vintage, vintage_label=label,
                               onset=(2016, 1), series=None, delta_final=-0.1)
    selections = [selection(0, 1, "Feb 2016"), selection(1, 2, "Mar 2016"), selection(2, None, None, "unavailable")]
    rows = D.real_time_against_final(selections, {0: -0.2}, {"Feb 2016": dt.date(2016, 2, 12)}, t)["rows"]
    assert [r["release_month"] for r in rows] == ["2016-02", "2016-03", None]
    assert [r["release_basis"] for r in rows] == ["ONS metadata", "label month only", "label month only"]
    assert [r["release_date"] for r in rows] == ["2016-02-12", None, None]
    plain = D.real_time_against_final(selections, {0: -0.2})["rows"]            # without the tables: as before
    assert [r["release_month"] for r in plain] == [None, None, None]


def test_development_ids_start_at_9000_and_bad_ids_are_refused_by_kind():
    assert check_run(R.DEV_SEED, dataclasses.replace(DS, primary=9000)) is False
    with pytest.raises(RegisteredRunRefused):
        check_run(R.DEV_SEED, dataclasses.replace(DS, primary=0))
    with pytest.raises(ValueError):
        check_run(R.DEV_SEED, dataclasses.replace(DS, primary=-1))


def test_the_list_of_registered_ids_that_development_runs_avoid():
    """The stream ids already registered in the programme (H1, E3, E1 and the extensions, 5100 to 5431)."""
    expected = {*range(100, 106), 200, 201, 300, 301, 400, 401, 1001, 1013, 2008, 2012, *range(5100, 5432)}
    assert set(REGISTERED_IDS_TO_AVOID) == expected and len(REGISTERED_IDS_TO_AVOID) == len(expected)


def test_the_generator_defaults_are_cell_0_and_replicate_0():
    a = stream_rng(R.DEV_SEED, DS.interval).integers(0, 2 ** 62, size=4)
    assert np.array_equal(a, R.generator(R.DEV_SEED, DS.interval, 0, 0).integers(0, 2 ** 62, size=4))


def test_window_thresholds_at_their_boundaries_and_real_time_deltas_at_w_40():
    """Section 10: eligibility is n_v >= 40 for W = 32 and n_v >= 56 for W = 48; section 7: n_v >= 48 for
    W = 40. Runs of exactly 40, 56, 47 and 48 growth values sit on the boundaries. The real-time table
    reports the W = 40 Delta_rt of the primary comparison."""
    tables = R.constructed_tables((40, 56, 47, 48))
    episodes = tuple(H1Episode(j, o, f) for j, (o, f) in enumerate(zip(R.ONSETS, (-0.1, 0.2, -0.3, 0.4))))
    out = analyze(tables, episodes, master_seed=R.DEV_SEED, streams=DS, B=2, interval_B=20)
    assert [s["status"] == "eligible" for s in out["selections_w32"]] == [True] * 4
    assert [s["status"] == "eligible" for s in out["selections"]] == [False, True, False, True]
    assert [s["status"] == "eligible" for s in out["selections_w48"]] == [False, True, False, False]
    components = out["comparisons"]["primary"].primary.observed.components
    rows = out["real_time_against_final"]["rows"]
    assert [r["delta_rt"] for r in rows if r["delta_rt"] is not None] == list(components)
