"""Further tests for the E1 column amendment (audit/E1_AMENDMENT_2.json).

They use a replica of the header layout of sheet A1 (the header texts of the seven real-GDP columns as the stopped
selection of 30 September 2026 recorded them; artificial numbers below row 7), so the strings that the amendment
quotes are exercised as they are, including the pound sign. Nothing here reads any Bank of England value.
"""
import json

import pytest

from e_official_artificial import LABEL, XlsxWriter, artificial_levels, commit_all
from test_e_official_x2_stages import acquired, amend, amend_column, logged_attempts, root, two_uk_columns  # noqa: F401
from uc_ext_official import e1_source as s, gates, records
from uc_ext_official.workbook import Workbook

SHEET = "A1. Headline series"
A8 = "A8. Real GDP (A) 1700-2015"
UNITS = "£mn, Chained Volume measure, 2013 prices"
B_DESCRIPTION = "Real UK GDP at market prices, geographically-consistent estimate based on post-1922 borders"
HEADER_B = " | ".join(["A1. Headline Annual Series 1086-2016", "National Accounts", B_DESCRIPTION, A8, UNITS])
REAL_STOP = ("7 real-GDP columns, and 5 of them are described as the UK or geographically consistent estimate; "
             "exactly one is required")
COLUMNS = dict(B=2, D=4, F=6, H=8, J=10, L=12, N=14)


def replica_rows(last_year_of_b=2016):
    levels = artificial_levels(1086, 2016)
    rows = {1: {2: "A1. Headline Annual Series 1086-2016"},
            2: {1: "Back to front page"},
            3: {1: "Section", 2: "National Accounts"},
            4: {1: "Description", 2: B_DESCRIPTION,
                4: "Real UK GDP at factor cost, geographically-consistent estimate based on post-1922 borders",
                6: "Index of real UK GDP at market prices cost - based on changing political boundaries, ",
                8: "Real GDP of England at market prices", 10: "Real GDP of England at factor cost ",
                12: "Composite estimate of English and (geographically-consistent) UK real GDP at factor cost",
                14: "HP-filter of log of real composite estimate of English and UK real GDP at factor cost",
                32: "Labour productivity"},
            5: {1: "Worksheet", 2: A8, 4: A8, 6: A8, 8: "A21. GDP per capita", 10: "A21. GDP per capita",
                12: "A21. GDP per capita 1086"},
            6: {1: "Units", 2: UNITS, 3: "growth rate", 4: UNITS, 5: "growth rate",
                6: "GB before 1801, GB+Ireland 1801-1920, GB + Northern Ireland after 1920.  Indexed to 100 in 1920",
                7: "growth rate", 8: UNITS, 9: "growth rate", 10: UNITS, 11: "growth rate", 12: "2013=100",
                13: "growth rate", 14: "approx. % difference from trend", 32: "Real GDP per head, 2013 prices"},
            7: {1: "Documentation"}}
    for offset, year in enumerate(range(1086, 2017)):
        row = {1: year}
        if year >= 1700:
            for letter, number in COLUMNS.items():
                if not (letter == "B" and year > last_year_of_b):
                    row[number] = round(float(levels[year]), 6)
        rows[8 + offset] = row
    return rows


def replica(last_year_of_b=2016):
    writer = XlsxWriter()
    writer.sheet("Cover (replica)", {1: {1: LABEL}, 2: {1: "Version 3.1 (artificial replica of a header layout)"}})
    writer.sheet(SHEET, replica_rows(last_year_of_b))
    writer.sheet("Q1. Qrtly headline series", {1: {1: "Back to front page"}, 2: {1: 1955}})
    writer.sheet("M1. Mthly headline series", {1: {1: "Back to front page"}, 2: {1: 1846}})
    return writer.build()


def territory_spec():
    return dict(stretches=[dict(first_year=1700, last_year=2016, territory="UK, geographically consistent",
                                evidence=[dict(location=f"{SHEET}!B4", quote=B_DESCRIPTION)])], note="artificial")


def named(header=HEADER_B, letter="B", sheet=SHEET):
    return dict(sheet=sheet, column=letter, header=header)


# ------------------------------------------------------------------------------------------ header_only level

def test_replica_stops_as_the_real_attempt_did_and_column_b_settles_it():
    wb = Workbook(replica())
    with pytest.raises(s.SourceStop, match="3 sheets"):
        s.header_only(wb)
    with pytest.raises(s.SourceStop) as stop:
        s.header_only(wb, headline_sheet=SHEET)
    assert str(stop.value) == REAL_STOP                                  # the reason the stopped attempt logged
    columns = {c["column"]: bool(c["uk_or_consistent"]) for c in stop.value.details["real_gdp_columns"]}
    assert columns == dict(B=True, D=True, F=True, H=False, J=False, L=True, N=True)     # AF (per head) is not one
    chosen = s.header_only(wb, headline_sheet=SHEET, real_gdp_column=named())["selection"]
    assert (chosen["column"], chosen["rule_step"], chosen["first_data_row"], chosen["year_column"]) == ("B", 3, 8, "A")
    assert chosen["header"] == HEADER_B and chosen["units"] == UNITS and chosen["label"] == B_DESCRIPTION
    assert chosen["rule"] == "the real-GDP column named by the amendment in audit/E1_AMENDMENT_2.json"


def test_the_record_must_carry_the_whole_printed_header_not_only_the_description():
    wb = Workbook(replica())
    for header in (B_DESCRIPTION, B_DESCRIPTION + " | " + UNITS, HEADER_B.replace(" | ", "|"),
                   HEADER_B.replace("Real UK", "real UK"), HEADER_B.replace("£", "GBP ")):
        with pytest.raises(s.SourceStop, match="differs from the header text"):
            s.header_only(wb, headline_sheet=SHEET, real_gdp_column=named(header))


def test_header_comparison_ignores_only_whitespace():
    wb = Workbook(replica())
    for header in ("  " + HEADER_B + "\n", HEADER_B.replace(" ", "  "), HEADER_B.replace(" | ", " |\t"),
                   HEADER_B.replace("Real UK", "Real\u00a0UK")):        # a no-break space counts as whitespace
        assert s.header_only(wb, headline_sheet=SHEET, real_gdp_column=named(header))["selection"]["column"] == "B"


def test_an_amendment_may_name_a_real_gdp_column_the_tie_break_did_not_keep():
    """Documents a reading: the named column need only be one of the columns labelled as real GDP (H is England only)."""
    wb = Workbook(replica())
    header_h = "Real GDP of England at market prices | A21. GDP per capita | " + UNITS
    output = s.header_only(wb, headline_sheet=SHEET, real_gdp_column=named(header_h, "H"))
    assert output["selection"]["column"] == "H" and output["selection"]["rule_step"] == 3


def test_no_amendment_can_name_a_column_where_no_column_is_labelled_as_real_gdp():
    with pytest.raises(s.SourceStop, match="No column of the headline-series sheet is labelled as real GDP"):
        s.header_only(Workbook(replica_without_real_gdp()), real_gdp_column=named(HEADER_B))


def replica_without_real_gdp():
    writer = XlsxWriter()
    writer.sheet("Cover (replica)", {1: {1: LABEL}, 2: {1: "Version 3.1 (artificial)"}})
    writer.sheet(SHEET, {1: {2: "A1. Headline Annual Series"}, 2: {1: "Description", 2: "Nominal UK GDP at market prices"},
                         3: {1: "Units", 2: UNITS}, 4: {1: 1700, 2: 1.0}})
    return writer.build()


# ------------------------------------------------------------------------------------------------ stage level

def select_with_both_amendments(root, content):
    acquired(root, content)
    amend(root, SHEET)
    with pytest.raises(s.SourceStop, match="5 of them"):
        s.select(root)
    stopped = logged_attempts(root)[-1]
    header = " | ".join(c["text"] for c in stopped["details"]["real_gdp_columns"][0]["header"])
    assert header == HEADER_B                                              # what the log holds is what is recorded
    amend_column(root, SHEET, "B", header)
    return s.select(root)["selection"]


def test_the_pound_sign_and_the_header_survive_the_record_the_log_and_the_selection(root):
    selection = select_with_both_amendments(root, replica())
    assert selection["header"] == HEADER_B and selection["units"] == UNITS
    used = selection["options"]["column_amendment"]
    assert (used["sheet"], used["column"], used["header"]) == (SHEET, "B", HEADER_B)
    on_disk = json.loads((root / s.SELECTION_RECORD).read_text(encoding="utf-8"))
    assert on_disk["header"] == HEADER_B and on_disk["options"]["column_amendment"]["header"] == HEADER_B
    record = json.loads((root / s.COLUMN_AMENDMENT_RECORD).read_text(encoding="utf-8"))
    assert record["real_gdp_column"]["header"] == HEADER_B
    log = (root / s.ATTEMPTS_LOG).read_text(encoding="utf-8")
    assert log.isascii() and "\\u00a3mn" in log                            # the log is ASCII; the pound sign is escaped
    assert json.loads(log.splitlines()[-1])["options"]["column_amendment"]["header"] == HEADER_B
    assert "£mn" in (root / s.HEADER_TEXT).read_text(encoding="utf-8")


def test_a_column_amendment_works_when_only_one_headline_sheet_exists(root):
    from e_official_artificial import artificial_workbook
    acquired(root, artificial_workbook(columns=two_uk_columns()))
    with pytest.raises(s.SourceStop, match="2 of them"):
        s.select(root)
    header = " | ".join(c["text"] for c in logged_attempts(root)[-1]["details"]["real_gdp_columns"][0]["header"])
    from test_e_official_x2_stages import TWO_HEADLINES
    amend_column(root, TWO_HEADLINES, "B", header)
    selection = s.select(root)["selection"]
    assert selection["column"] == "B" and selection["rule_step"] == 3
    assert selection["options"]["amendment"] is None and selection["options"]["column_amendment"]["column"] == "B"


def test_a_column_amendment_record_without_its_text_is_refused(root):
    acquired(root, replica())
    amend(root, SHEET)
    with pytest.raises(s.SourceStop):
        s.select(root)
    amend_column(root, SHEET, "B", HEADER_B)
    (root / s.COLUMN_AMENDMENT_TEXT).unlink()
    commit_all(root, "text removed")
    with pytest.raises(gates.GateClosed, match="is missing; the amendment record needs its text"):
        s.select(root)
    assert not (root / s.SELECTION_RECORD).exists() and len(logged_attempts(root)) == 1   # a refused record is not an attempt


def test_a_text_without_its_record_chooses_nothing(root):
    acquired(root, replica())
    amend(root, SHEET)
    (root / s.COLUMN_AMENDMENT_TEXT).write_bytes(b"a text on its own\n")
    commit_all(root, "text only")
    with pytest.raises(s.SourceStop, match="5 of them"):
        s.select(root)
    assert not (root / s.SELECTION_RECORD).exists()


def test_the_x4_gate_and_extraction_refuse_a_changed_or_removed_amendment_record(root):
    select_with_both_amendments(root, replica())
    s.record_territory(root, territory_spec())
    commit_all(root, "selection and territory")
    assert s.extract(root)["column"] == "B"
    commit_all(root, "extraction")
    assert s.load_registered_growth(root)["record_sha256"][s.COLUMN_AMENDMENT_RECORD]
    for path, change in ((s.COLUMN_AMENDMENT_RECORD, "column"), (s.AMENDMENT_RECORD, "sheet")):
        original = (root / path).read_bytes()
        (root / path).write_bytes(original.replace(b"https://example.invalid", b"https://example.invalid/x"))
        commit_all(root, f"{change} amendment record altered")
        with pytest.raises(gates.GateClosed, match=f"relied on {path}"):
            s.load_registered_growth(root)
        (root / path).write_bytes(original)
        commit_all(root, f"{change} amendment record restored")
        assert s.load_registered_growth(root)
        (root / path).unlink()
        commit_all(root, f"{change} amendment record removed")
        with pytest.raises(gates.GateClosed, match=f"relied on {path}"):
            s.load_registered_growth(root)
        (root / path).write_bytes(original)
        commit_all(root, f"{change} amendment record restored again")


def test_amendment_1_changed_before_extraction_now_stops_extraction(root):
    select_with_both_amendments(root, replica())
    s.record_territory(root, territory_spec())
    original = (root / s.AMENDMENT_RECORD).read_bytes()
    (root / s.AMENDMENT_RECORD).write_bytes(original.replace(b"https://example.invalid", b"https://example.invalid/x"))
    commit_all(root, "selection, territory and an altered amendment 1")
    with pytest.raises(gates.GateClosed, match=f"relied on {s.AMENDMENT_RECORD}"):
        s.extract(root)
    assert not (root / s.EXTRACTION_RECORD).exists() and not (root / s.EXTRACTION_STOP).exists()


def test_a_column_that_ends_in_2015_stops_the_extraction_and_the_tool_offers_no_way_on(root):
    """The registered sample rule: 'If the column ends before 2016, stop and amend; do not shorten the sample.'"""
    select_with_both_amendments(root, replica(last_year_of_b=2015))
    s.record_territory(root, territory_spec())
    commit_all(root, "selection and territory")
    with pytest.raises(s.SourceStop) as stop:
        s.extract(root)
    assert stop.value.stage == "sample" and (root / s.EXTRACTION_STOP).is_file()
    assert not (root / s.EXTRACTION_RECORD).exists()
    stopped = json.loads((root / s.EXTRACTION_STOP).read_text(encoding="utf-8"))
    assert "Non-numeric level in 2016" in stopped["reason"]              # a stop by the sample rule, naming the year only
    commit_all(root, "extraction stopped")
    with pytest.raises(records.RecordExists, match="extraction happens once"):
        s.extract(root)
    with pytest.raises(records.RecordExists, match="the selection is made once"):
        s.select(root)                                   # no way to name another column without new records
    with pytest.raises(gates.GateClosed, match="E1 X.2 is not complete"):
        s.load_registered_growth(root)
