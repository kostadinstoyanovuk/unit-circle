"""E4 amendment 1 at X.2: reading the vintage labels (rules A and B) and joining parts whose reference-quarter
rows differ in number (rule C), on constructed workbooks only.

What is registered and what the amendment says is stated per test: the registered readings are R-4.4 (vintage
labels), R-4.7 (identical reference-quarter labels) and R-4.9 (order of stops) in docs/E4_READINGS.md; the
amendment's rules are quoted in docs/E4_AMENDMENT_1_CODE.md. Every label, number and month here is constructed,
except the three header texts of rule B and the place names, which the amendment itself quotes.
"""
import numpy as np
import pytest

from uc_e4.table import RawPart, ReadLabel, Stop, _label_text, availability_report, build_tables, mask_digits, \
    parse_release_month


# ------------------------------------------------------------------- ReadLabel (src/uc_e4/table.py)

def test_read_label_is_read_as_the_reading_it_carries():
    label = ReadLabel("Sep-62 [1958 prices]", 1962, 3)
    assert parse_release_month(label) == (1962, 3)                 # the carried reading, not the text
    assert str(label) == _label_text(label) == "Sep-62 [1958 prices]"
    assert mask_digits(label) == "Sep-## [#### prices]"
    for bad in (ReadLabel("x", 1962, 13), ReadLabel("x", 999, 1), ReadLabel("x", 1962, 0)):
        with pytest.raises(ValueError, match="out of range"):
            parse_release_month(bad)


def test_read_labels_flow_through_build_tables_as_any_label():
    labels = (ReadLabel("Oct-61", 1961, 10), ReadLabel("Nov-61 M1", 1961, 11), ReadLabel("Feb-772", 1961, 12))
    part = RawPart("constructed", labels, ("1955 Q1", "1955 Q2"), ((1.0, 2.0, None), (3.0, None, None)))
    tables = build_tables([part])
    assert [v.label for v in tables.availability.vintages] == ["Oct-61", "Nov-61 M1", "Feb-772"]
    assert [v.release_month for v in tables.availability.vintages] == [(1961, 10), (1961, 11), (1961, 12)]
    assert tables.manifest["earliest_vintage"] == "Oct-61" and tables.manifest["latest_vintage_month"] == (1961, 12)
    report = availability_report(tables.availability)
    assert [row["release_month"] for row in report["per_vintage"]] == ["1961-10", "1961-11", "1961-12"]
    assert np.array_equal(tables.levels.levels[:, 0], [1.0, 3.0])


def test_registered_reading_is_unchanged_for_texts_and_dates():
    """R-4.4 is unchanged: a two-digit year does not parse as a text; a four-digit one does."""
    with pytest.raises(ValueError):
        parse_release_month("Oct-61")
    assert parse_release_month("Oct 1961") == (1961, 10)
