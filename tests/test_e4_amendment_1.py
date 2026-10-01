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


# ------------------------------------------------------------------------------- rule A (step 3)

from e4_workbook_builder import label_reading, layout_workbook, sheet_1961, sheet_2004  # noqa: E402
from uc_ext_official import e4_source as s, gates  # noqa: E402
from uc_ext_official.workbook import Workbook  # noqa: E402

READING = s.validate_label_reading(label_reading())
NO_PLACES = s.validate_label_reading(label_reading(places=()))    # parts not named as the places


@pytest.mark.parametrize("text, normal, month", [
    ("Oct-71", "Oct-71", (1971, 10)),                                   # plain
    ("Mar-74 [1950 prices]", "Mar-74 [1950 prices]", (1974, 3)),        # price-base note
    ("Apr-75\nM1", "Apr-75 M1", (1975, 4)),                             # code on the next line
    ("Apr-75 M2", "Apr-75 M2", (1975, 4)),                              # code after a space
    ("May-90\nQNA", "May-90 QNA", (1990, 5)),
    ("Jun-12\n1st", "Jun-12 1st", (2012, 6)),
    ("Jul-77 [1950 prices]\nM2", "Jul-77 [1950 prices] M2", (1977, 7)),  # note and code
    ("September-19 QNA", "September-19 QNA", (2019, 9)),                # month in full
    ("Nov- 2019 1st", "Nov- 2019 1st", (2019, 11)),                     # four-digit year, space after the hyphen
    ("Dec - 19", "Dec - 19", (2019, 12)),                               # spaces on either side of the hyphen
    ("Feb- 20 1st ", "Feb- 20 1st", (2020, 2)),                         # trailing space
    ("Jan-20 \n1st", "Jan-20 1st", (2020, 1)),                          # trailing space and a line break
    ("Aug-81  \n\n M1", "Aug-81 M1", (1981, 8)),                        # a run of spaces and line breaks
    ("oct-71", "oct-71", (1971, 10)),                                   # month read without regard to case
    ("Oct-61", "Oct-61", (1961, 10)), ("Oct-60", "Oct-60", (2060, 10)),  # the pivot 61 from the record
    ("Oct-00", "Oct-00", (2000, 10)), ("Oct-99", "Oct-99", (1999, 10)),
])
def test_rule_a_reads_every_form_the_amendment_describes(text, normal, month):
    """Amendment 1, rule A (draft item 3 forms, invented months and years). Reading taken: the month name is
    read without regard to case; the white space normalised is spaces and line breaks only."""
    label = s.read_vintage_label(text, century_pivot=61)
    assert (label.text, (label.year, label.month)) == (normal, month)


@pytest.mark.parametrize("text", [
    "Jan-Feb-62", "Jan Feb-62",                     # two month names
    "15 Jan-62", "Jan-15-62",                       # a day number
    "Jan-62 M3",                                    # an unknown code
    "Feb-772", "Feb-7",                             # a year of three digits, of one digit
    "Jan-62 [1954 price]", "Jan-62 [19540 prices]", "Jan-62 [195 prices]",
    "Jan-", "Jan", "",                              # no year, empty text
    "Jan-62 revised", "Jan-62 M1 M2", "Jan-62 M1 [1954 prices]",   # extra words, two codes, code before note
    "Sept-62", "Jn-62",                             # not a full name nor its first three letters
    "Jan 1962", "1962-01", "Jan–62", "Jan-62\tM1",   # registered forms and other characters are not rule A
    "Jan-62 qna", "Jan-62 [1954 Prices]",           # codes and the word 'prices' are read as written
])
def test_rule_a_does_not_read_other_forms(text):
    with pytest.raises(ValueError):
        s.read_vintage_label(text, century_pivot=61)


def test_rule_a_reads_only_texts_and_a_date_keeps_the_registered_treatment():
    import datetime as dt
    with pytest.raises(ValueError, match="not a text"):
        s.read_vintage_label(dt.date(1961, 10, 1), century_pivot=61)
    assert parse_release_month(dt.date(1961, 10, 1)) == (1961, 10)       # R-4.4: a date is a date


# -------------------------------------------------------------------------- rule B (step 3)

def structure(content, reading=READING):
    return s.read_structure(Workbook(content), label_reading=reading)


def one_sheet(labels, n=8):
    return layout_workbook([("1961 - 1982", labels, n)], cover=False)


def test_rule_b_reads_the_three_places_and_keeps_their_text():
    labels, _ = sheet_1961()
    st = structure(one_sheet(labels))
    assert st["stop"] is None
    read = {r["column"]: r for r in st["label_readings"]}
    assert {c: (read[c]["text"], read[c]["year"], read[c]["month"], read[c]["rule"]) for c in ("H", "CN", "GQ")} == {
        "H": ("Sep-62 [1958 prices]", 1962, 3, "B"), "CN": ("Mar-62 [1963 prices]", 1969, 3, "B"),
        "GQ": ("Feb-772", 1978, 2, "B")}
    assert [(p["before"]["release_month"], p["after"]["release_month"]) for p in st["amended"]["readings_by_place"]] \
        == [("1962-02", "1962-04"), ("1969-02", "1969-04"), ("1978-01", "1978-03")]
    assert all(r["rule"] == "A" for r in st["label_readings"] if r["column"] not in ("H", "CN", "GQ"))


@pytest.mark.parametrize("changes, words", [
    ({"H": "Sep-62 [1959 prices]"}, "column H: the cell does not hold exactly the listed text"),
    ({"GQ": "Feb-773"}, "column GQ: the cell does not hold exactly the listed text"),
    ({"G": "Jan-62"}, "column H: the labels on either side do not read as two months apart"),
    ({"CO": "May-69"}, "column CN: the labels on either side do not read as two months apart"),
    ({"GR": "Feb-78"}, "column GQ: the labels on either side do not read as two months apart"),
    ({"I": "Apr 1962"}, "column H: the label in column I does not read by rule A"),
    ({"CM": "Feb-772"}, "column CN: the label in column CM does not read by rule A"),
])
def test_rule_b_stops_at_step_3_naming_the_place_when_a_condition_fails(changes, words):
    labels, _ = sheet_1961(changes=changes)
    stop = structure(one_sheet(labels))["stop"]
    assert stop is not None and stop.step == "4.3" and "sheet '1961 - 1982', " + words in stop.reason


def test_rule_b_text_in_another_column_or_sheet_is_read_by_rule_a():
    labels, _ = sheet_1961(changes={"N": "Sep-62 [1958 prices]"})       # column N holds September 1962
    other = [s_ for s_ in sheet_2004()[0]]
    other[0] = "Sep-62 [1958 prices]"
    st = structure(layout_workbook([("1961 - 1982", labels, 8), ("2004 - 2017", other[:1], 12)], cover=False))
    read = {(r["sheet"], r["column"]): r for r in st["label_readings"]}
    assert (read[("1961 - 1982", "N")]["rule"], read[("1961 - 1982", "N")]["month"]) == ("A", 9)
    assert (read[("2004 - 2017", "B")]["rule"], read[("2004 - 2017", "B")]["year"]) == ("A", 1962)


@pytest.mark.parametrize("place", [("1961 - 1982", "GZ", "Feb-772", "1978-02"), ("1962 - 1982", "H", "Feb-62", "1962-02"),
                                   ("1961 - 1982", "A", "Reference quarter", "1962-02")])
def test_rule_b_entry_for_a_place_that_does_not_exist_stops(place):
    reading = s.validate_label_reading(label_reading(places=(place,)))
    stop = structure(one_sheet(sheet_1961()[0]), reading)["stop"]
    assert stop.step == "4.3" and "there is no vintage label of the table at that place" in stop.reason


def test_without_rule_b_the_three_texts_do_not_all_read():
    """Without its readings by place, 'Feb-772' is not of rule A's form: step 3 stops (registered order)."""
    reading = s.validate_label_reading(label_reading(places=()))
    st = structure(one_sheet(sheet_1961()[0]), reading)
    assert st["stop"] is None and st["amended"]["rule_a_failures"][0]["column"] == "GQ"
    with pytest.raises(Stop, match="step 4.3"):
        build_tables(st["parts"])


# ---------------------------------------------------------------------------- rule C (step 1)

def piece(name, months, quarters, rows=None):
    """A part as the source stage hands it to `table_parts`: header cells, labels and constructed numbers."""
    from uc_ext_official.workbook import Cell
    columns = list(range(2, 2 + len(months)))
    labels = {c: Cell(4, c, "text", f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m - 1]}"
                                    f"-{y % 100:02d}") for c, (y, m) in zip(columns, months)}
    rows = rows or list(range(5, 5 + len(quarters)))
    cells = tuple(tuple(float(10 * i + k) for k in range(len(months))) for i in range(len(quarters)))
    return dict(sheet=name, columns=columns, rows=rows, header=labels, serials={}, quarter_labels=tuple(quarters),
                cells=cells)


QUARTERS = tuple(f"{1955 + i // 4} Q{i % 4 + 1}" for i in range(12))


def test_rule_c_joins_parts_of_different_lengths_with_empty_padding_counted_as_empty():
    pieces = [piece("A", [(1961, 9), (1961, 10)], QUARTERS[:4]), piece("B", [(1983, 1), (1983, 2)], QUARTERS[:7]),
              piece("C", [(2004, 1)], QUARTERS[:12]), piece("D", [(2018, 6), (2018, 7)], QUARTERS[:9])]
    built = s.table_parts(pieces, NO_PLACES, False)
    assert built["amended"]["join"]["longest_part"] == "C"
    assert built["amended"]["join"]["padded_rows"] == {"A": 8, "B": 5, "C": 0, "D": 3}
    tables = build_tables(built["parts"])
    kinds = tables.availability.kinds
    assert kinds.shape == (12, 7) and tables.manifest["parts"] == "A+B+C+D"
    assert list(kinds[:, 0]) == ["numeric"] * 4 + ["empty"] * 8                # padded rows are empty cells
    assert availability_report(tables.availability)["per_vintage"][0]["empty"] == 8
    assert np.isnan(tables.levels.levels[4:, 0]).all() and tables.levels.levels[3, 0] == 30.0


def test_rule_c_parts_given_in_another_sheet_order_are_joined_in_the_order_of_their_ranges():
    pieces = [piece("D", [(2018, 6)], QUARTERS[:9]), piece("A", [(1961, 9)], QUARTERS[:4]),
              piece("B", [(1983, 1)], QUARTERS[:12])]
    tables = build_tables(s.table_parts(pieces, NO_PLACES, False)["parts"])
    assert tables.manifest["parts"] == "A+B+D" and [v.release_month for v in tables.availability.vintages] == [
        (1961, 9), (1983, 1), (2018, 6)]


@pytest.mark.parametrize("shorter, where", [
    (QUARTERS[1:5], "row 5 (position 1)"),                                      # not the first labels
    (QUARTERS[:2] + QUARTERS[3:5], "row 7 (position 3)"),                       # the same labels with a gap
    (QUARTERS[:3] + ("1955Q4",), "row 8 (position 4)"),                         # a label written otherwise
])
def test_rule_c_stops_at_step_1_naming_the_part_and_the_row(shorter, where):
    pieces = [piece("A", [(1961, 9)], shorter), piece("B", [(1983, 1)], QUARTERS)]
    with pytest.raises(Stop) as stop:
        s.table_parts(pieces, NO_PLACES, False)
    assert stop.value.step == "4.1" and "part on sheet 'A'" in stop.value.reason and where in stop.value.reason


def test_rule_c_keeps_the_registered_overlap_condition():
    pieces = [piece("A", [(1961, 9), (1983, 1)], QUARTERS[:4]), piece("B", [(1983, 1)], QUARTERS)]
    with pytest.raises(Stop, match="vintage ranges overlap"):
        build_tables(s.table_parts(pieces, NO_PLACES, False)["parts"])


def test_one_part_alone_is_not_changed():
    built = s.table_parts([piece("A", [(1961, 9)], QUARTERS[:4])], NO_PLACES, False)
    assert built["amended"]["join"] is None and len(built["parts"][0].quarter_labels) == 4


def test_without_an_amendment_the_registered_strict_rule_applies():
    """R-4.7: identical labels join; different labels stop at step 1, as before the amendment."""
    def registered(name, labels, quarters):
        return RawPart(name, tuple(labels), tuple(quarters), tuple((1.0,) * len(labels) for _ in quarters))
    same = s.table_parts([dict(piece("A", [(1961, 9)], QUARTERS[:4]), header={2: None}),
                          dict(piece("B", [(1983, 1)], QUARTERS[:4]), header={2: None})], None, False)
    assert len(same["parts"]) == 2 and same["amended"] is None and same["label_readings"] == []
    joined = build_tables([registered("A", ["Sep 1961"], QUARTERS[:4]), registered("B", ["Jan 1983"], QUARTERS[:4])])
    assert joined.manifest["parts"] == "A+B"
    with pytest.raises(Stop, match="not identical"):
        build_tables([registered("A", ["Sep 1961"], QUARTERS[:4]), registered("B", ["Jan 1983"], QUARTERS[:6])])
    with pytest.raises(Stop, match="step 4.3"):                                 # 'Sep-61' is not R-4.4
        build_tables([registered("A", ["Sep-61"], QUARTERS[:4]), registered("B", ["Jan 1983"], QUARTERS[:6])])


def test_an_unread_label_stops_at_step_3_before_the_join_condition_as_registered():
    """R-4.9: in step 1 the labels are parsed before the join condition, so a label rule A does not read is a
    step 3 stop even when the reference-quarter labels would not join either."""
    bad = piece("A", [(1961, 9)], QUARTERS[1:5])
    bad["header"] = {2: bad["header"][2]._replace(text="Sept-61")}
    built = s.table_parts([bad, piece("B", [(1983, 1)], QUARTERS)], NO_PLACES, False)
    assert built["amended"]["join"] is None and built["amended"]["rule_a_failures"][0]["column"] == "B"
    with pytest.raises(Stop, match="step 4.3"):
        build_tables(built["parts"])


def test_what_does_not_change_a_cell_of_kind_other_and_the_order_rule_still_stop():
    """Amendment 1, "What does not change": step 2 (kind other) and step 4 (release months that do not
    increase in one direction) apply as registered to the joined parts."""
    other = piece("A", [(1961, 9)], QUARTERS[:4])
    other["cells"] = ((1.0,), ("1.5",), (2.0,), (3.0,))
    with pytest.raises(Stop, match="step 4.2"):
        build_tables(s.table_parts([other, piece("B", [(1983, 1)], QUARTERS)], NO_PLACES, False)["parts"])
    zigzag = piece("A", [(1961, 9), (1961, 11), (1961, 10)], QUARTERS[:4])
    with pytest.raises(Stop, match="step 4.4"):
        build_tables(s.table_parts([zigzag, piece("B", [(1983, 1)], QUARTERS)], NO_PLACES, False)["parts"])


# -------------------------------------------------------------- the amendment record (schema)

@pytest.mark.parametrize("change, words", [
    (lambda r: r.pop("join"), "exactly rule_a, readings_by_place and join"),
    (lambda r: r.update(extra=1), "exactly rule_a, readings_by_place and join"),
    (lambda r: r["rule_a"].update(century_pivot="61"), "century_pivot"),
    (lambda r: r["rule_a"].update(century_pivot=True), "century_pivot"),
    (lambda r: r["rule_a"].update(codes=["M1", "M2", "1st"]), "codes must be exactly"),
    (lambda r: r["rule_a"].update(codes=["M1", "M2", "1st", "QNA", "M3"]), "codes must be exactly"),
    (lambda r: r["readings_by_place"][0].pop("text"), "exactly sheet, column, text and release_month"),
    (lambda r: r["readings_by_place"][0].update(column="h"), "not a column letter"),
    (lambda r: r["readings_by_place"][0].update(release_month="1962-3"), "YYYY-MM"),
    (lambda r: r["readings_by_place"][0].update(release_month="1962-13"), "YYYY-MM"),
    (lambda r: r["readings_by_place"].append(dict(r["readings_by_place"][0])), "two readings by place"),
    (lambda r: r.update(readings_by_place={}), "must be a list"),
    (lambda r: r.update(join={"rule": "identical"}), "join must be"),
])
def test_a_malformed_label_reading_section_is_refused(change, words):
    section = label_reading()
    change(section)
    with pytest.raises(gates.GateClosed, match=words):
        s.validate_label_reading(section)


# ------------------------------------- the mapping and the level reader under the amendment (constructed root)

import json  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402

from e4_workbook_builder import E1_CODE, commit_all, git, with_core_properties  # noqa: E402
from e_official_artificial import x3_record  # noqa: E402
from test_e4_source_stages import CODE, PLANTED, TEXTS, acquired, scrub  # noqa: E402

AMENDMENT = "audit/E4_AMENDMENT_1.json"


@pytest.fixture
def root(tmp_path):
    from e4_workbook_builder import e4_root
    saved = list(sys.path)
    yield e4_root(tmp_path)
    sys.path[:] = saved


def write_amendment(root, section=None, *, without=False):
    record = dict(record_type="constructed amendment record (test)")
    if not without:
        record["label_reading"] = label_reading() if section is None else section
    (root / AMENDMENT).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    commit_all(root, "amendment record")


def stopped_then_amended(root, content=None):
    """Attempt 1 under the registered readings stops at step 3; the amendment record is committed."""
    acquired(root, layout_workbook() if content is None else content)
    first = s.map_structure(root)["result"]
    assert first["status"] == "stopped" and first["stop"]["step"] == "4.3"
    commit_all(root, "attempt 1")
    write_amendment(root)


def test_the_layout_maps_under_the_amendment_and_records_what_was_read_how(root):
    stopped_then_amended(root)
    outcome = s.map_structure(root, amendment=AMENDMENT)
    result, text = outcome["result"], outcome["text"]
    assert result["status"] == "mapped" and result["attempt"] == 2
    assert result["manifest"]["parts"] == "1961 - 1982+1983 - 2003+2004 - 2017+2018 - "
    assert result["manifest"]["earliest_vintage"] == "Sep-61" and result["manifest"]["n_vintages"] == 319
    assert result["label_readings_sha256"] == s.label_readings_sha256(result["label_readings"])
    assert len(result["label_readings"]) == 319 and {r["rule"] for r in result["label_readings"]} == {"A", "B"}
    tie = [r for r in result["label_readings"] if r["sheet"] == "1983 - 2003"][11:13]
    assert [(r["year"], r["month"]) for r in tie] == [(1983, 11), (1983, 11)]          # a tie of two release months
    assert result["amended_reading"]["join"]["padded_rows"] == {"1961 - 1982": 24, "1983 - 2003": 16,
                                                                 "2004 - 2017": 8, "2018 - ": 0}
    assert result["label_reading"]["readings_by_place"][2] == dict(sheet="1961 - 1982", column="GQ", text="Feb-772",
                                                                   release_month="1978-02")
    for words in ("Amendment cited: audit/E4_AMENDMENT_1.json",
                  "part '2018 - ': 40 vintage labels (plain 0, with note 0, with code 40, by place 0",
                  "release months 2018-06 to 2021-09; 44 reference-quarter rows, last 1965 Q4",
                  "'1961 - 1982' column GQ: 'Feb-772' read as 1978-02 (column GP 'Jan-78' 1978-01; column GR 'Mar-78' "
                  "1978-03)",
                  "Join (rule C): longest part '2018 - ' (44 reference-quarter rows); rows padded with empty cells: "
                  "'1961 - 1982' 24, '1983 - 2003' 16, '2004 - 2017' 8, '2018 - ' 0",
                  "  Sep-61 | 1961-09 | 19 | 25 | 0 | 0"):                # a vintage of the first part: padded rows empty
        assert words in text, words
    assert (root / s.MAPPING_JSON).is_file()


def x3_committed(root):
    (root / gates.x3_record_path("e4")).write_text(json.dumps(x3_record("e4", CODE, e1_code_sha256=E1_CODE), indent=1))
    commit_all(root, "constructed X.3 record")


def test_the_level_reader_reads_the_labels_and_joins_exactly_as_the_mapping(root):
    stopped_then_amended(root)
    assert s.map_structure(root, amendment=AMENDMENT)["result"]["status"] == "mapped"
    commit_all(root, "mapped")
    x3_committed(root)
    out = s.read_level_tables(root)
    mapping = json.loads((root / s.MAPPING_JSON).read_text(encoding="utf-8"))
    tables = out["tables"]
    assert out["summary"]["kinds_sha256"] == mapping["kinds_sha256"]
    assert [v.label for v in tables.availability.vintages][:3] == ["Sep-61", "Oct-61 [1950 prices]", "Nov-61"]
    assert tables.availability.vintages[6].release_month == (1962, 3)                 # rule B at H
    levels_ = tables.levels.levels
    assert levels_.shape == (44, 319) and np.isnan(levels_[20:, :199]).all()          # padded rows: no level
    assert np.isfinite(levels_[:19, :199]).all()


def test_the_level_reader_refuses_a_changed_amendment_record_or_workbook_or_label_list(root):
    stopped_then_amended(root)
    s.map_structure(root, amendment=AMENDMENT)
    commit_all(root, "mapped")
    x3_committed(root)
    record = json.loads((root / AMENDMENT).read_text(encoding="utf-8"))
    record["label_reading"]["rule_a"]["century_pivot"] = 60
    (root / AMENDMENT).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    commit_all(root, "amendment record changed")
    with pytest.raises(gates.GateClosed, match="differs from the amendment record that the mapping cites"):
        s.read_level_tables(root)
    git(root, "revert", "--no-edit", "HEAD")
    mapping = json.loads((root / s.MAPPING_JSON).read_text(encoding="utf-8"))
    mapping["label_readings"][6]["month"] = 4
    (root / s.MAPPING_JSON).write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")
    commit_all(root, "mapping record changed")
    with pytest.raises(gates.GateClosed, match="re-read under the amendment differ"):
        s.read_level_tables(root)
    git(root, "revert", "--no-edit", "HEAD")
    raw = root / json.loads((root / s.ACQUISITION_RECORD).read_text(encoding="utf-8"))["file"]
    content = raw.read_bytes()
    raw.chmod(0o644)
    raw.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
    raw.chmod(0o444)
    with pytest.raises(gates.GateClosed, match="differ from its acquisition record"):
        s.read_level_tables(root)


def test_after_a_stop_at_step_3_an_amendment_record_without_label_reading_is_refused(root):
    acquired(root, layout_workbook())
    s.map_structure(root)
    commit_all(root, "attempt 1")
    write_amendment(root, without=True)
    with pytest.raises(gates.GateClosed, match="no label_reading section"):
        s.map_structure(root, amendment=AMENDMENT)
    write_amendment(root, dict(label_reading(), join={"rule": "identical"}))
    with pytest.raises(gates.GateClosed, match="malformed"):
        s.map_structure(root, amendment=AMENDMENT)
    assert len((root / s.ATTEMPTS_LOG).read_text(encoding="utf-8").splitlines()) == 1     # nothing attempted


def test_a_failed_reading_by_place_is_a_recorded_stop_at_step_3(root):
    labels = sheet_1961(changes={"I": "May-62"})[0]
    stopped_then_amended(root, layout_workbook([("1961 - 1982", labels, 8), ("2018 - ", *__import__(
        "e4_workbook_builder").sheet_2018())]))
    result = s.map_structure(root, amendment=AMENDMENT)["result"]
    assert result["status"] == "stopped" and result["stop"]["step"] == "4.3"
    assert "sheet '1961 - 1982', column H" in result["stop"]["reason"] and not (root / s.MAPPING_JSON).exists()


def test_no_level_appears_in_any_output_of_the_amended_mapping(root, capsys):
    from e4_workbook_builder import Book, LABEL, layout_cells, sheet_2018
    labels, n = sheet_2018()
    cells = layout_cells(labels, n)
    cells[(5, 2)], cells[(10, 5)] = PLANTED
    cells[(60, 1)] = "Note: 9876543.21 is a planted value and is blanked"
    content = Book(title=LABEL).sheet("1961 - 1982", layout_cells(*sheet_1961(8))).sheet("2018 - ", cells).build()
    stopped_then_amended(root, content)
    from test_e4_source_stages import tool
    tool().main(["--root", str(root), "map", "--amendment", AMENDMENT])           # through the X.2 tool
    assert json.loads((root / s.MAPPING_JSON).read_text(encoding="utf-8"))["status"] == "mapped"
    commit_all(root, "mapped")
    x3_committed(root)
    s.read_level_tables(root)
    streams = capsys.readouterr()
    assert "Join (rule C): longest part '2018 - '" in streams.out and "Mapped." in streams.out
    outputs = [streams.out, streams.err] + [p.read_text(encoding="utf-8") for p in (root / "audit").rglob("*")
                                            if p.is_file()] + [(root / "DATA_MANIFEST.csv").read_text(encoding="utf-8")]
    for text in outputs:
        for planted in TEXTS:
            assert planted not in scrub(text)


# ------------------------------------------------------------------ names in the file properties

def test_creator_and_last_modified_by_are_neither_printed_nor_recorded(root):
    content = with_core_properties(layout_workbook(), creator="Constructed Person A",
                                   lastModifiedBy="Constructed Person B", subject="Constructed subject")
    st = s.read_structure(Workbook(content))
    assert st["document_properties"] == {"creator": "(name withheld)", "lastModifiedBy": "(name withheld)",
                                         "subject": "Constructed subject", "title": st["document_properties"]["title"]}
    stopped_then_amended(root, content)
    s.map_structure(root, amendment=AMENDMENT)
    for path in (root / "audit").rglob("*"):
        if path.is_file():
            assert "Constructed Person" not in path.read_text(encoding="utf-8")
    for path in list((root / "audit/e4_source").glob("structure-attempt-*")) + [root / s.MAPPING_JSON]:
        assert "(name withheld)" in path.read_text(encoding="utf-8")
    assert "creator: (name withheld)" in (root / s.MAPPING_TEXT).read_text(encoding="utf-8")


def test_a_withheld_property_naming_another_release_is_recorded_without_its_text(root):
    content = with_core_properties(layout_workbook(), creator="Published 13 August 2026")
    acquired(root, content)
    result = s.map_structure(root)["result"]
    assert result["status"] == "stopped" and result["stop"]["kind"] == "release rule"     # the check is unchanged
    assert result["conflicts"] == [dict(where="document property creator", kind="another release date",
                                        date="2026-08-13", text="(name withheld)")]
    assert "13 August" not in (root / f"{s.SOURCE_DIR}/structure-attempt-1.json").read_text(encoding="utf-8")
