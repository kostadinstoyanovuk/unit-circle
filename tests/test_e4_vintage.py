"""prereg/E4.md sections 5 and 7 on constructed tables (Annex B step 3). Arbitrary numbers, no real data."""
import math

import numpy as np
import pytest

from e4_artificial import make_tables
from uc_e4.table import quarter_from_index, quarter_index
from uc_e4.vintage import (FLOOR, REGISTERED_ONSETS, H1Episode, growth_from_levels, h1_episodes_from_record,
                           minimum_growth, select_episode, select_episodes, vintage_series)

ONSET = (1973, 3)
LAST = (1973, 2)                       # q_j - 1


def q(offset_from_last):
    return quarter_from_index(quarter_index(LAST) + offset_from_last)


def episodes():
    return tuple(H1Episode(j, o, None) for j, o in enumerate(REGISTERED_ONSETS))


def first_release_covers(first_q=(1955, 1)):
    """vintage 0 ends one quarter before q_j - 1; vintage 1 (v_j) is the first with q_j - 1."""
    return {0: (first_q, q(-1)), 1: (first_q, q(0)), 2: (first_q, q(4)), 3: (first_q, q(8)), 4: (first_q, q(12)),
            5: (first_q, q(16))}


def test_minimum_growth_by_window():
    assert [minimum_growth(w) for w in (32, 40, 48)] == [40, 48, 56]


def test_growth_formula_is_h1s():
    y = np.array([100.0, 101.0, 103.0])
    assert np.array_equal(growth_from_levels(y), 400 * np.diff(np.log(y)))


def test_series_run_and_growth_positions():
    t = make_tables(covers=first_release_covers())
    s = vintage_series(t.availability, t.levels, 1, ONSET)
    assert s.status == "ok" and s.last_quarter == LAST and s.first_quarter == FLOOR
    assert s.run_ended_by == "floor"
    n_levels = quarter_index(LAST) - quarter_index(FLOOR) + 1
    assert s.n_levels == n_levels and s.n_v == n_levels - 1 == len(s.growth)
    # position n_v - 1 is q_j - 1 (growth of q_j - 1 over q_j - 2); quarters after q_j - 1 are ignored
    row = t.availability.row
    y = lambda quarter: t.levels.level(1, row(quarter))
    assert s.growth[-1] == 400 * (math.log(y(LAST)) - math.log(y(q(-1))))
    later = vintage_series(t.availability, t.levels, 3, ONSET)          # vintage 3 holds quarters after q_j - 1
    assert later.n_v == s.n_v and later.status == "ok"


def test_quarters_after_the_onset_are_ignored_even_if_odd():
    over = {(3, q(2)): ".."}                                  # a marker after q_j - 1 does not matter
    t = make_tables(covers=first_release_covers(), overrides=over)
    assert vintage_series(t.availability, t.levels, 3, ONSET).status == "ok"


def test_no_level_for_the_quarter_before_onset():
    t = make_tables(covers=first_release_covers())
    s = vintage_series(t.availability, t.levels, 0, ONSET)             # vintage 0 stops one quarter early
    assert s.status == "no_level" and s.n_v == 0 and s.growth is None


def test_floor_1955q1_even_if_the_table_reaches_further_back():
    t = make_tables(first_row=(1948, 1), covers=first_release_covers(first_q=(1948, 1)))
    s = vintage_series(t.availability, t.levels, 1, ONSET)
    assert s.first_quarter == (1955, 1) and s.run_ended_by == "floor"
    assert s.n_levels == quarter_index(LAST) - quarter_index((1955, 1)) + 1


def test_non_positive_level_before_the_floor_is_not_in_the_run():
    t = make_tables(first_row=(1950, 1), covers=first_release_covers(first_q=(1950, 1)),
                    overrides={(1, (1954, 3)): -5.0, (1, (1950, 1)): 0.0})
    s = vintage_series(t.availability, t.levels, 1, ONSET)
    assert s.status == "ok" and s.first_quarter == FLOOR


@pytest.mark.parametrize("bad,word", [(0.0, "non-positive"), (-3.0, "non-positive"),
                                      (float("nan"), "non-finite"), (float("inf"), "non-finite")])
def test_non_positive_or_non_finite_level_in_the_run_is_a_stop(bad, word):
    t = make_tables(covers=first_release_covers(), overrides={(1, (1966, 2)): bad})
    s = vintage_series(t.availability, t.levels, 1, ONSET)
    assert s.status == "stop" and word in s.stop and "1966Q2" in s.stop and s.growth is None
    sel = select_episode(t, H1Episode(0, ONSET, None))
    assert sel.status == "unavailable" and sel.failed_step == "7.4" and word in sel.reason


def test_a_bad_level_after_a_gap_is_outside_the_run():
    gap = {(1, (1970, 1)): None, (1, (1960, 1)): -1.0}
    t = make_tables(covers=first_release_covers(), overrides=gap)
    s = vintage_series(t.availability, t.levels, 1, ONSET)
    assert s.status == "ok" and s.first_quarter == (1970, 2) and s.run_ended_by == "gap:1970Q1"


@pytest.mark.parametrize("gap_offset,expected_nv,eligible", [(-48, 47, False), (-49, 48, True)])
def test_missing_quarter_before_onset_gives_n_v_47_and_48(gap_offset, expected_nv, eligible):
    gap_quarter = q(gap_offset)                     # the run starts at the quarter after the gap
    t = make_tables(covers=first_release_covers(), overrides={(1, gap_quarter): None})
    s = vintage_series(t.availability, t.levels, 1, ONSET)
    assert s.n_v == expected_nv and s.run_ended_by.startswith("gap:")
    sel = select_episode(t, H1Episode(0, ONSET, None))
    assert (sel.status == "eligible") is eligible
    if not eligible:
        assert sel.failed_step == "7.3" and "47" in sel.reason


def test_marker_gap_and_missing_row_both_end_the_run():
    t = make_tables(covers=first_release_covers(), overrides={(1, q(-10)): ".."})
    assert vintage_series(t.availability, t.levels, 1, ONSET).run_ended_by == f"gap:{q(-10)[0]}Q{q(-10)[1]}"
    t2 = make_tables(covers=first_release_covers(), drop_rows=(q(-10),))
    s2 = vintage_series(t2.availability, t2.levels, 1, ONSET)
    assert s2.run_ended_by.startswith("no_row:") and s2.n_v == 9


def test_no_row_for_the_quarter_before_onset_is_step_1():
    t = make_tables(covers=first_release_covers(), drop_rows=(LAST,))
    sel = select_episode(t, H1Episode(0, ONSET, None))
    assert sel.status == "unavailable" and sel.failed_step == "7.1" and sel.vintage is None


def test_v_j_is_the_first_vintage_with_the_level_and_the_one_before_has_none():
    t = make_tables(covers=first_release_covers())
    sel = select_episode(t, H1Episode(0, ONSET, None))
    assert sel.status == "eligible" and sel.vintage == 1
    assert sel.vintage_label == "Feb 2016" and sel.previous_vintage_label == "Jan 2016"


def test_v_j_as_the_earliest_vintage_is_unavailable_first_release_unverifiable():
    covers = {k: ((1955, 1), q(k)) for k in range(6)}
    covers[0] = ((1955, 1), q(3))
    t = make_tables(covers=covers)
    sel = select_episode(t, H1Episode(0, ONSET, None))
    assert sel.status == "unavailable" and sel.failed_step == "7.2" and sel.vintage == 0
    assert "unverifiable" in sel.reason


def test_length_thresholds_on_each_side_of_40_48_and_56():
    # a run of n_v growth values: levels from q_j - 1 - n_v to q_j - 1
    for window, threshold in ((32, 40), (40, 48), (48, 56)):
        for n_v, expected in ((threshold - 1, False), (threshold, True), (threshold + 1, True)):
            first = q(-n_v)
            t = make_tables(first_row=first, covers=first_release_covers(first_q=first))
            sel = select_episode(t, H1Episode(0, ONSET, None), window)
            assert vintage_series(t.availability, t.levels, 1, ONSET).n_v == n_v
            assert (sel.status == "eligible") is expected, (window, n_v)
            if not expected:
                assert sel.failed_step == "7.3"


def test_episode_index_is_never_renumbered():
    # vintage 0 already holds 1973Q2, so episode 0 is unavailable (first release unverifiable); each later
    # episode has its first vintage one step later and keeps its index j = 1, 2, 3
    covers = {0: ((1955, 1), (1975, 4)), 1: ((1955, 1), (1985, 4)), 2: ((1955, 1), (1995, 4)),
              3: ((1955, 1), (2010, 4)), 4: ((1955, 1), (2010, 4)), 5: ((1955, 1), (2010, 4))}
    t = make_tables(covers=covers)
    sel = select_episodes(t, episodes())
    assert [s.j for s in sel] == [0, 1, 2, 3]
    assert [s.status for s in sel] == ["unavailable", "eligible", "eligible", "eligible"]
    assert sel[0].failed_step == "7.2" and [s.vintage for s in sel] == [0, 1, 2, 3]
    assert [s.series.n_v for s in sel[1:]] == [quarter_index((1979, 4)) - quarter_index((1955, 1)),
                                               quarter_index((1990, 2)) - quarter_index((1955, 1)),
                                               quarter_index((2008, 1)) - quarter_index((1955, 1))]


def test_zero_eligible_episodes():
    covers = {k: ((1955, 1), (2010, 4)) for k in range(6)}      # every vintage holds everything: all first releases unverifiable
    t = make_tables(covers=covers)
    sel = select_episodes(t, episodes())
    assert all(s.failed_step == "7.2" for s in sel)


def test_h1_record_loader_checks_the_registered_onsets():
    rec = {"episodes": [dict(onset_quarter="1956 Q2", statistic_available=False, change=None),
                        dict(onset_quarter="1973 Q3", statistic_available=True, change=-0.1),
                        dict(onset_quarter="1980 Q1", statistic_available=True, change=-0.2),
                        dict(onset_quarter="1990 Q3", statistic_available=True, change=-0.3),
                        dict(onset_quarter="2008 Q2", statistic_available=True, change=0.4)]}
    eps = h1_episodes_from_record(rec)
    assert [e.j for e in eps] == [0, 1, 2, 3] and [e.onset for e in eps] == list(REGISTERED_ONSETS)
    rec["episodes"][1]["onset_quarter"] = "1973 Q4"
    with pytest.raises(ValueError):
        h1_episodes_from_record(rec)
