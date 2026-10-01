"""Independent recomputation of quantities defined in prereg/E4.md sections 4 to 9 and 11, on constructed data.

Each expected value is derived in the test from the registered text (tests/e4_review_support.py) and not by
calling the function under test: an unscaled least-squares AR(2) fit with an intercept column, the companion
roots from numpy.roots, generators built directly from SeedSequence([seed, stream, cell, replicate]), and the
p-value and Wilson formulas of H1 section 6. Development run on constructed data: master seed 20260930, stream
ids from 9000, small B.
"""
import numpy as np
import pytest

import e4_review_support as R
from uc_core.rolling import max_modulus
from uc_core.validation_design import wilson_interval
from uc_e4 import synthetic as Y
from uc_e4.procedure import EpisodeInput, compare, measure
from uc_e4.streams import DEVELOPMENT_STREAMS as DS
from uc_e4.table import RawPart, Stop, availability_report, build_tables, quarter_from_index, quarter_index
from uc_e4.vintage import H1Episode, select_episode, vintage_series

TOL = 1e-9


def test_rolling_modulus_at_each_window_agrees_with_an_independent_fit():
    g = R.constructed_growth(70, replicate=1)
    mine = R.rolling_modulus(g, 40)
    code = max_modulus(g, 40).to_numpy()
    assert np.isnan(code[:39]).all() and np.isnan(mine[:39]).all()       # first indicator at position 39 (section 6)
    assert np.allclose(code[39:], mine[39:], rtol=0, atol=TOL)


@pytest.mark.parametrize("n_v", [48, 49, 61, 90])
def test_pre_onset_change_is_m_at_n_v_minus_1_minus_m_at_n_v_minus_9(n_v):
    g = R.constructed_growth(n_v, replicate=n_v)
    kind, value = measure(g, window=40)["primary"]
    m = R.rolling_modulus(g, 40)
    assert kind == "ok"
    assert value == pytest.approx(m[n_v - 1] - m[n_v - 9], abs=TOL)       # later minus earlier: a rise is positive
    assert value == pytest.approx(R.delta(g), abs=TOL)


def test_onset_eligibility_at_its_boundary_positions():
    g = R.constructed_growth(48, replicate=3)
    assert measure(g[:47], window=40)["primary"] == ("ineligible", None)  # M(38) does not exist at W = 40
    kind, value = measure(g, window=40)["primary"]                        # n_v = 48: M(39) is the first indicator
    assert kind == "ok" and value == pytest.approx(R.rolling_modulus(g, 40)[47] - R.rolling_modulus(g, 40)[39], abs=TOL)
    for window, n_ok in ((32, 40), (48, 56)):
        h = R.constructed_growth(n_ok, replicate=window)
        assert measure(h[:-1], window=window)["primary"] == ("ineligible", None)
        assert measure(h, window=window)["primary"][1] == pytest.approx(R.delta(h, window), abs=TOL)


def _episodes(sizes=(52, 60, 75)):
    return [EpisodeInput(j, R.constructed_growth(n, replicate=10 + j)) for j, n in enumerate(sizes)]


@pytest.mark.parametrize("kind,stream", [("residual", DS.primary), ("wild", DS.wild)])
def test_episode_mean_null_draws_and_p_value_agree_with_an_independent_derivation(kind, stream):
    e = _episodes()
    B = 8
    out = compare(e, {x.j: R.generator(R.DEV_SEED, stream, x.j, 0) for x in e}, B=B, kind=kind).primary
    deltas = [R.delta(x.growth) for x in e]
    assert out.observed.components == pytest.approx(deltas, abs=TOL)
    assert out.observed.value == pytest.approx(np.mean(deltas), abs=TOL)                # S_rt: mean, signs kept
    mine = R.surrogate_statistics([x.growth for x in e], R.DEV_SEED, stream, B, kind=kind)
    assert [a.status for a in out.attempts] == ["retained"] * B
    assert [a.statistic for a in out.attempts] == pytest.approx(mine, abs=1e-8)
    assert min(abs(s - out.observed.value) for s in mine) > 1e-6                    # no near tie: counts are exact
    p, k = R.p_value(out.observed.value, mine)
    assert out.exceedances == k and out.p_value == p and out.retained == B
    lo, hi = R.wilson(k, B)
    assert out.q == k / B and out.q_wilson == pytest.approx((lo, hi), abs=1e-12)


@pytest.mark.parametrize("k,n", [(0, 1), (1, 1), (0, 12), (5, 12), (12, 12), (0, 1000), (37, 1000), (1000, 1000)])
def test_wilson_interval_follows_the_h1_section_6_formula(k, n):
    assert wilson_interval(k, n) == pytest.approx(R.wilson(k, n), abs=1e-12)


def test_synthetic_vintages_are_the_truncations_at_49_99_149_199_249():
    rec = Y.size_replicate(0, master_seed=R.DEV_SEED, streams=DS, B=2)
    x = np.asarray(rec["input"])
    expected = [R.delta(x[:r]) for r in (49, 99, 149, 199, 249)]
    assert rec["observed"]["eligible_onsets"] == [0, 1, 2, 3, 4]
    assert rec["observed"]["components"] == pytest.approx(expected, abs=TOL)
    assert rec["S"] == pytest.approx(np.mean(expected), abs=TOL)


# ---- section 4 and 5 on a hand-built availability table -----------------------------------------------
QUARTERS = [quarter_from_index(i) for i in range(quarter_index((1955, 1)), quarter_index((1973, 4)) + 1)]
LABELS = ("Jan 2016", "Feb 2016", "Feb 2016", "Apr 2016")


def _level(i, k):
    return 100.0 * np.exp(0.004 * i + 0.003 * k + 0.01 * np.sin(1.3 * i))


def _hand_part(extra_label=None, duplicate=None):
    """Vintage 0 stops at 1973Q1; vintage 1 holds 1955Q1-1973Q2 with a marker at 1960Q4 and an empty cell at
    1958Q2; vintage 2 (same release month as 1) holds 1955Q1-1973Q2; vintage 3 holds every row to 1973Q4."""
    labels = LABELS + ((extra_label,) if extra_label else ())
    rows, cells = [], []
    quarters = QUARTERS + ([duplicate] if duplicate else [])
    for i, q in enumerate(quarters):
        idx = quarter_index(q)
        row = [_level(i, 0) if idx <= quarter_index((1973, 1)) else None,
               ".." if q == (1960, 4) else (None if q == (1958, 2) else (_level(i, 1) if idx <= quarter_index((1973, 2)) else "")),
               _level(i, 2) if idx <= quarter_index((1973, 2)) else None,
               _level(i, 3)]
        if extra_label:
            row.append(None)
        rows.append(f"{q[0]} Q{q[1]}")
        cells.append(tuple(row))
    return RawPart("hand", labels, tuple(rows), tuple(cells))


def test_availability_reading_of_a_hand_built_table():
    t = build_tables([_hand_part()])
    av = t.availability
    # by hand: kinds per vintage over 76 rows (1955Q1-1973Q4)
    report = availability_report(av)
    counts = [(r["vintage"], r["numeric"], r["empty"], r["marker"], r["other"]) for r in report["per_vintage"]]
    assert counts == [("Jan 2016", 73, 3, 0, 0), ("Feb 2016", 72, 3, 1, 0), ("Feb 2016", 74, 2, 0, 0),
                      ("Apr 2016", 76, 0, 0, 0)]
    assert [v.position for v in av.vintages] == [0, 1, 2, 3]               # equal months keep table order
    assert report["marker_cells"] == [dict(vintage="Feb 2016", quarter="1960 Q4", content="..")]
    # section 7 step 1 and section 5 by hand: v_j = vintage 1; the run starts after the marker at 1960Q4
    sel = select_episode(t, H1Episode(0, (1973, 3), -0.17))
    assert sel.vintage == 1 and sel.previous_vintage_label == "Jan 2016"
    s = sel.series
    assert s.first_quarter == (1961, 1) and s.run_ended_by == "gap:1960Q4"
    n_v = quarter_index((1973, 2)) - quarter_index((1961, 1))
    assert s.n_v == n_v == 49 and sel.status == "eligible"
    levels = [_level(QUARTERS.index(q), 1) for q in QUARTERS if quarter_index((1961, 1)) <= quarter_index(q) <= quarter_index((1973, 2))]
    assert s.growth == pytest.approx(400 * np.diff(np.log(levels)), abs=1e-12)
    # vintage 3 has later quarters: they do not enter its series (section 5)
    later = vintage_series(av, t.levels, 3, (1973, 3))
    assert later.last_quarter == (1973, 2) and later.n_v == quarter_index((1973, 2)) - quarter_index((1955, 1))


def test_a_quarter_published_twice_and_an_extra_column_stop_the_mapping():
    with pytest.raises(Stop) as twice:
        build_tables([_hand_part(duplicate=(1960, 4))])
    assert twice.value.step == "4.3" and "twice" in twice.value.reason
    with pytest.raises(Stop) as extra:
        build_tables([_hand_part(extra_label="Notes")])
    assert extra.value.step == "4.3" and "vintage label" in extra.value.reason
