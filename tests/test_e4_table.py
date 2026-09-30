"""prereg/E4.md section 4 (structure mapping) and Annex B step 3: unit tests on constructed workbooks and
availability tables. Nothing here reads a file or a real level; the numbers are arbitrary."""
import datetime as dt
import json

import numpy as np
import pytest

from e4_artificial import month_labels, part, quarter_labels
from uc_e4.table import (EMPTY, MARKER, NUMERIC, OTHER, ErrorValue, RawPart, Stop, availability_report,
                         build_tables, join_parts, kind_of, mask_digits, parse_quarter, parse_release_month)


# ---- step 2: the four cell kinds --------------------------------------------------------------------
@pytest.mark.parametrize("cell,kind", [
    (123.5, NUMERIC), (7, NUMERIC), (np.float64(1.5), NUMERIC), (float("nan"), NUMERIC), (float("inf"), NUMERIC),
    (-3.0, NUMERIC), (0, NUMERIC),
    (None, EMPTY), ("", EMPTY),
    ("..", MARKER), ("-", MARKER), ("x", MARKER), ("n/a", MARKER), (" ", MARKER), ("[c]", MARKER),
    ("12", OTHER), ("1,234.5", OTHER), ("x1", OTHER), ("²", OTHER),          # text with a digit, number as text
    ("#N/A", OTHER), ("#DIV/0!", OTHER), (ErrorValue("#REF!"), OTHER),             # error values
    (True, OTHER), (False, OTHER), (np.bool_(True), OTHER),                        # logical values
    (dt.datetime(2016, 1, 1), OTHER), (dt.date(2016, 1, 1), OTHER),               # any other content
])
def test_cell_kinds(cell, kind):
    assert kind_of(cell) == kind


def test_mask_digits():
    assert mask_digits("ab12.5-x9") == "ab##.#-x#"
    assert mask_digits("..") == ".."


def cells_with(kinds_at):
    """fill function: default numeric, listed (row, col) get the given raw cell."""
    return lambda r, c: kinds_at.get((r, c), 100.0 + r + 0.5 * c)


def test_numeric_empty_marker_other_in_one_table():
    quarters = quarter_labels(n=5)
    p = part(quarters=quarters, fill=cells_with({(0, 0): None, (1, 0): "..", (2, 1): "-", (3, 2): ""}))
    t = build_tables([p])
    counts = availability_report(t.availability)
    assert [v[k] for v in counts["per_vintage"] for k in (NUMERIC, EMPTY, MARKER, OTHER)] == [
        3, 1, 1, 0,      # vintage 0: empty (0,0), marker (1,0)
        4, 0, 1, 0,      # vintage 1: marker (2,1)
        4, 1, 0, 0,      # vintage 2: empty "" (3,2)
        5, 0, 0, 0]
    assert counts["kinds_total"] == {NUMERIC: 16, EMPTY: 2, MARKER: 2, OTHER: 0}
    assert sorted(m["content"] for m in counts["marker_cells"]) == ["-", ".."]
    assert not t.availability.present(0, (1955, 1)) and t.availability.present(1, (1955, 1))


def test_report_prints_no_level_and_levels_are_held_apart():
    secret = 98765.4321
    p = part(fill=lambda r, c: secret + r if r == 3 else 100.0 + r)
    t = build_tables([p])
    text = json.dumps(availability_report(t.availability)) + repr(t.availability)
    assert "98765" not in text and str(secret) not in text
    assert not hasattr(t.availability, "levels")
    assert t.levels.level(0, 3) == secret + 3


def test_other_cell_stops_and_masks_digits():
    for bad in ("12.5", "1,234", "#N/A", ErrorValue("#VALUE!"), True):
        p = part(fill=cells_with({(2, 1): bad}))
        with pytest.raises(Stop) as e:
            build_tables([p])
        assert e.value.step == "4.2"
        assert all(ch not in json.dumps(e.value.detail) for ch in "0123456789") or "#" in json.dumps(e.value.detail)
        assert "12.5" not in json.dumps(e.value.detail) and "1,234" not in json.dumps(e.value.detail)


def test_marker_and_empty_do_not_stop():
    p = part(fill=cells_with({(0, 0): "..", (1, 1): None}))
    build_tables([p])


# ---- step 3: labels ---------------------------------------------------------------------------------
@pytest.mark.parametrize("label,expected", [
    ("Jan 2016", (2016, 1)), ("January 2016", (2016, 1)), ("2016 Jan", (2016, 1)), ("Sept 2016", (2016, 9)),
    ("2016-03", (2016, 3)), ("2016/03", (2016, 3)), ("03/2016", (2016, 3)), ("2016-03-15", (2016, 3)),
    ("15 March 2016", (2016, 3)), ("March 15th, 2016", (2016, 3)), ("2016-03-15 00:00:00", (2016, 3)),
    (dt.datetime(2015, 12, 31), (2015, 12)), (dt.date(2015, 2, 1), (2015, 2)),
])
def test_vintage_labels_that_parse(label, expected):
    assert parse_release_month(label) == expected


@pytest.mark.parametrize("label", [
    "Jan-16", "Jan", "2016", "Quarter 4 (Oct to Dec) 2015", "Oct to Dec 2015", "Vintage 3", "Jan 2016 Month 2",
    "2016-13", "13/2016", "", "first estimate", 5.0, None, "Jan 2016 2017", "Jan 32 2016"])
def test_vintage_labels_that_do_not_parse(label):
    with pytest.raises(ValueError):
        parse_release_month(label)


@pytest.mark.parametrize("label,expected", [
    ("1955 Q1", (1955, 1)), ("1955Q4", (1955, 4)), ("1955-Q2", (1955, 2)), ("Q3 1955", (1955, 3)),
    ("1955 quarter 1", (1955, 1)), ("1st quarter 1955", (1955, 1)), ("  1955   q2 ", (1955, 2))])
def test_quarter_labels_that_parse(label, expected):
    assert parse_quarter(label) == expected


@pytest.mark.parametrize("label", ["1955", "1955 Q5", "1955 Q0", "Q1", "Mar 1955", dt.date(1955, 3, 31), 1955.1,
                                   "1955 H1", "55 Q1", None])
def test_quarter_labels_that_do_not_parse(label):
    with pytest.raises(ValueError):
        parse_quarter(label)


def test_label_that_does_not_parse_stops():
    with pytest.raises(Stop) as e:
        build_tables([part(vintages=("Jan 2016", "Feb 16", "Mar 2016"))])
    assert e.value.step == "4.3"
    with pytest.raises(Stop) as e:
        build_tables([part(quarters=("1955 Q1", "1955 Q2", "spring 1955"))])
    assert e.value.step == "4.3"


def test_reference_quarter_twice_stops():
    with pytest.raises(Stop) as e:
        build_tables([part(quarters=("1955 Q1", "1955 Q2", "1955Q1"))])
    assert e.value.step == "4.3" and "twice" in e.value.reason


def test_reference_quarter_with_no_row_is_no_level():
    t = build_tables([part(quarters=quarter_labels(n=4))]).availability
    assert t.row((1955, 1)) == 0 and t.row((1956, 1)) is None
    assert not t.present(0, (1956, 1)) and t.first_present((1956, 1)) is None


# ---- step 4: order ----------------------------------------------------------------------------------
def test_vintages_ordered_by_release_month_ascending_and_ties_by_position():
    labels = ("Jan 2016", "Feb 2016", "Feb 2016", "Mar 2016")
    t = build_tables([part(vintages=labels, fill=lambda r, c: 10.0 * c + r)])
    assert [v.position for v in t.availability.vintages] == [0, 1, 2, 3]
    assert [t.levels.level(k, 0) for k in range(4)] == [0.0, 10.0, 20.0, 30.0]


def test_descending_table_is_read_in_the_direction_in_which_months_increase():
    labels = ("Mar 2016", "Feb 2016", "Feb 2016", "Jan 2016")          # newest first
    t = build_tables([part(vintages=labels, fill=lambda r, c: 10.0 * c + r)])
    assert [v.release_month for v in t.availability.vintages] == [(2016, 1), (2016, 2), (2016, 2), (2016, 3)]
    assert [v.position for v in t.availability.vintages] == [3, 2, 1, 0]      # the two February vintages: 2 before 1
    assert [t.levels.level(k, 0) for k in range(4)] == [30.0, 20.0, 10.0, 0.0]


def test_two_vintages_with_the_same_release_month_are_kept_in_table_order():
    labels = ("Jan 2016", "Jan 2016", "Feb 2016")
    t = build_tables([part(vintages=labels)]).availability
    assert [v.position for v in t.vintages] == [0, 1, 2]


@pytest.mark.parametrize("labels", [("Jan 2016", "Mar 2016", "Feb 2016"), ("Mar 2016", "Jan 2016", "Feb 2016"),
                                    ("Jan 2016", "Jan 2016", "Jan 2016"), ("Jan 2016", "Feb 2016", "Jan 2016")])
def test_release_months_that_do_not_increase_in_one_direction_stop(labels):
    with pytest.raises(Stop) as e:
        build_tables([part(vintages=labels)])
    assert e.value.step == "4.4"


def test_single_vintage_stops():
    with pytest.raises(Stop) as e:
        build_tables([part(vintages=("Jan 2016",))])
    assert e.value.step == "4.4"


def test_date_typed_vintage_labels():
    labels = (dt.datetime(2016, 1, 15), dt.datetime(2016, 2, 15), dt.datetime(2016, 3, 15))
    t = build_tables([part(vintages=labels)]).availability
    assert [v.release_month for v in t.vintages] == [(2016, 1), (2016, 2), (2016, 3)]
    assert t.vintages[0].label.startswith("2016-01-15")


# ---- step 1: joining parts --------------------------------------------------------------------------
def two_parts(second_first=(2016, 5), second_n=3, quarters2=None, order_reversed=False):
    a = part("A", vintages=month_labels((2016, 1), 4), fill=lambda r, c: 1000.0 + 10 * c + r)
    b = part("B", vintages=month_labels(second_first, second_n), quarters=quarters2,
             fill=lambda r, c: 2000.0 + 10 * c + r)
    return [b, a] if order_reversed else [a, b]


def test_table_split_across_two_sheets_joinable():
    for reversed_ in (False, True):                      # the sheets may be found in either order
        t = build_tables(two_parts(order_reversed=reversed_))
        assert t.manifest["parts"] == "A+B"
        assert [v.release_month for v in t.availability.vintages] == \
               [(2016, m) for m in (1, 2, 3, 4, 5, 6, 7)]
        assert t.levels.level(0, 0) == 1000.0 and t.levels.level(6, 2) == 2020.0 + 2


def test_table_split_across_two_sheets_descending_parts():
    a = part("A", vintages=("Apr 2016", "Mar 2016", "Feb 2016", "Jan 2016"), fill=lambda r, c: 1000.0 + c)
    b = part("B", vintages=("Jul 2016", "Jun 2016", "May 2016"), fill=lambda r, c: 2000.0 + c)
    t = build_tables([a, b])
    assert [v.release_month for v in t.availability.vintages] == [(2016, m) for m in range(1, 8)]


def test_table_split_across_two_sheets_not_joinable():
    with pytest.raises(Stop) as e:                       # overlapping ranges
        build_tables(two_parts(second_first=(2016, 3)))
    assert e.value.step == "4.1" and "overlap" in e.value.reason
    with pytest.raises(Stop) as e:                       # touching ranges share a month: overlap (R-4.6)
        build_tables(two_parts(second_first=(2016, 4)))
    assert e.value.step == "4.1"
    with pytest.raises(Stop) as e:                       # different reference-quarter labels
        build_tables(two_parts(quarters2=quarter_labels(n=11)))
    assert e.value.step == "4.1" and "labels" in e.value.reason
    with pytest.raises(Stop) as e:                       # same quarters, different text (R-4.7)
        build_tables(two_parts(quarters2=quarter_labels(n=12, style="{y}Q{q}")))
    assert e.value.step == "4.1"
    with pytest.raises(Stop):                            # no table at all
        build_tables([])


def test_join_direction_conflict_is_caught_by_the_order_rule():
    a = part("A", vintages=("Jan 2016", "Feb 2016"))
    b = part("B", vintages=("Jun 2016", "May 2016"))
    with pytest.raises(Stop) as e:
        build_tables([a, b])
    assert e.value.step == "4.4"


def test_other_cell_in_a_joined_part_stops():
    a = part("A", vintages=month_labels((2016, 1), 2))
    b = part("B", vintages=month_labels((2016, 5), 2), fill=cells_with({(0, 0): "5"}))
    with pytest.raises(Stop) as e:
        build_tables([a, b])
    assert e.value.step == "4.2"


# ---- step 5: manifest -------------------------------------------------------------------------------
def test_manifest_records_earliest_and_latest_vintage_and_earliest_quarter():
    quarters = ("1956 Q1", "1955 Q4", "1955 Q3")                       # rows need not be sorted
    t = build_tables([part(vintages=("Mar 2016", "Feb 2016", "Jan 2016"), quarters=quarters)])
    assert t.manifest["earliest_vintage"] == "Jan 2016" and t.manifest["latest_vintage"] == "Mar 2016"
    assert t.manifest["earliest_reference_quarter"] == "1955Q3"
    assert t.manifest["n_vintages"] == 3 and t.manifest["n_reference_quarters"] == 3


def test_raw_part_shape_is_validated():
    with pytest.raises(ValueError):
        RawPart("x", ("Jan 2016",), ("1955 Q1",), ((1.0, 2.0),))
