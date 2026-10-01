"""Unit tests of the E2 section 4 and section 7 data rules on constructed inputs (Annex B, X.3 prerequisites).

Section 4: the quarterly-row grammar, the span, missing and duplicated quarters, the [0, 100] range and the
literal fallback trigger, on constructed labelled rows (the X.2 tool turns a file's fields into numbers or
None before calling variables()). Section 7: runs, merges and eligibility on constructed growth paths. Every
number is constructed here; development stream 9650 only.
"""
import numpy as np
import pytest

from uc_e2 import constants, procedure, streams, variables

SPAN = [f"{year} Q{quarter}" for year in range(1971, 2020) for quarter in range(1, 5)]
LEVELS = [100. + i for i in range(len(SPAN))]
RATES = [5. + .01 * i for i in range(len(SPAN))]


def run_variables(labels, rates):
    return variables.variables(SPAN, LEVELS, labels, rates)


# --------------------------------------------------------------------------------------------- section 4

def test_section4_quarterly_annual_and_monthly_rows_only_quarterly_rows_are_used():
    labels = ["1971", "1971 JAN", "1971 FEB"] + SPAN + ["2019", "2019 DEC", "Title", ""]
    rates = ["not inspected", 99., None] + RATES + [None, "x", "header", None]
    quarters, x = run_variables(labels, rates)
    assert len(quarters) == constants.N_OBS and np.array_equal(x[:, 1], np.diff(RATES))


def test_section4_label_with_spaces_at_either_end_is_a_quarterly_row():
    labels = ["  " + label + " " for label in SPAN]
    assert np.array_equal(run_variables(labels, RATES)[1], run_variables(SPAN, RATES)[1])
    assert variables.quarterly_row_quarter(" 1990 Q3  ") == "1990 Q3"


@pytest.mark.parametrize("label", ["1971 q1", "1971  Q1", "1971 Q5", "1971Q1", "71 Q1", "1971 Q1\n",
                                   "١٩٧١ Q1", "1971 Q1 (p)"])
def test_section4_other_labels_are_not_quarterly_rows(label):
    assert variables.quarterly_row_quarter(label) is None
    with pytest.raises(ValueError, match="contiguous"):           # the quarter it would have supplied is missing
        run_variables([label] + SPAN[1:], RATES)


def test_section4_missing_value_stops():
    for missing in (None, float("nan"), float("inf")):
        rates = list(RATES)
        rates[100] = missing
        with pytest.raises(ValueError):
            run_variables(SPAN, rates)


def test_section4_missing_and_duplicated_quarter_inside_the_span_stop():
    with pytest.raises(ValueError, match="contiguous"):
        run_variables(SPAN[:50] + SPAN[51:], RATES[:50] + RATES[51:])
    with pytest.raises(ValueError, match="duplicated"):
        run_variables(SPAN[:51] + SPAN[50:], RATES[:51] + RATES[50:])


def test_section4_rows_outside_the_span_are_not_inspected():
    labels = ["1970 Q3", "1970 Q4"] + SPAN + ["2020 Q1", "2020 Q1"]
    rates = [-5., "x"] + RATES + [500., None]
    assert np.array_equal(run_variables(labels, rates)[1], run_variables(SPAN, RATES)[1])


def test_section4_values_of_0_and_100_are_used_and_values_just_outside_stop():
    rates = list(RATES)
    rates[10], rates[20] = 0., 100.
    assert run_variables(SPAN, rates)[1].shape == (constants.N_OBS, constants.K)
    for outside in (np.nextafter(0., -1.), np.nextafter(100., 200.)):
        rates = list(RATES)
        rates[30] = outside
        with pytest.raises(ValueError, match="admissible"):
            run_variables(SPAN, rates)


def test_section4_fallback_only_for_a_file_with_no_quarterly_row_in_the_span():
    monthly = [f"{year} {month}" for year in range(1971, 2020) for month in ("JAN", "FEB", "MAR")]
    assert variables.unemployment_rule(["1971", "1972"] + monthly) == "three_month_averages"
    assert variables.unemployment_rule(monthly + ["1970 Q4", "2020 Q1"]) == "three_month_averages"
    assert variables.unemployment_rule(monthly + SPAN) == "quarterly_rows"


def test_section4_file_with_quarterly_rows_for_part_of_the_span_stops():
    partial = SPAN[84:]                                            # quarterly rows from 1992 Q1 only
    assert variables.unemployment_rule(["1971 JAN"] + partial) == "quarterly_rows"
    with pytest.raises(ValueError, match="contiguous"):
        run_variables(partial, RATES[84:])


# --------------------------------------------------------------------------------------------- section 7

def h1_growth(negative_e2_positions):
    """259 positive H1 growth values with negative quarters at the given E2 positions (H1 position + 64)."""
    growth = np.full(constants.N_OBS + constants.H1_OFFSET, 2.)
    for position in negative_e2_positions:
        growth[position + constants.H1_OFFSET] = -1.
    return growth


def table_onsets(negative):
    return [(row["onset"], row["end"]) for row in variables.onset_table(h1_growth(negative))["rows"]]


def test_section7_run_at_the_start_of_the_sample():
    assert table_onsets([0, 1]) == [(0, 1)]


def test_section7_single_negative_quarter_is_not_a_run():
    assert table_onsets([60]) == [] and table_onsets([60, 62]) == []


def test_section7_merge_distance_of_8_merges_and_of_9_does_not():
    assert table_onsets([60, 61, 69, 70]) == [(60, 70)]               # 69 - 61 = 8
    assert table_onsets([60, 61, 70, 71]) == [(60, 61), (70, 71)]     # 70 - 61 = 9


def test_section7_chained_merges():
    assert table_onsets([60, 61, 69, 70, 78, 79, 87, 88]) == [(60, 88)]


@pytest.mark.parametrize("onset, w40, w32, w48", [(47, False, True, False), (48, True, True, False),
                                                  (55, True, True, False), (56, True, True, True)])
def test_section7_structural_eligibility_at_onsets_47_48_55_and_56(onset, w40, w32, w48):
    [row] = variables.onset_table(h1_growth([onset, onset + 1]))["rows"]
    assert row["eligible"] == {40: w40, 32: w32, 48: w48}


@pytest.mark.parametrize("onset, primary, kendall", [(47, False, False), (48, True, False),
                                                     (54, True, False), (55, True, True)])
def test_section7_primary_and_kendall_eligibility_on_a_fitted_path(onset, primary, kendall):
    rng = streams.stream_rng(streams.DEVELOPMENT_SEED, 9650)
    x = np.column_stack((5. + .5 * rng.standard_normal(constants.N_OBS), rng.standard_normal(constants.N_OBS)))
    x[onset:onset + 2, 0] = -1.
    measured = procedure._measure(x)
    assert (measured["primary"].status == "ok") is primary and (measured["lag1"].status == "ok") is primary
    assert (measured["trend"].status == "ok") is kendall
    if primary:
        assert measured["primary"].eligible_onsets == (onset,)
