"""E4 X.2 (prereg/E4.md section 4): the release rule over saved pages, the page allow-list, the blanking of
numbers, the reader's date-formatted cells, and the structure mapping on constructed workbooks.

Tests marked by the environment variable UC_E4_ONS_PAGES also run the release rule on the three ONS pages
saved on 29 September 2026 (Annex C, items 1, 5 and 6) and on constructed variants of them; they are skipped
when the directory is not given, because the saved pages are not kept in this repository."""
import datetime as dt
import os
from pathlib import Path

import pytest

from e4_workbook_builder import (BOOLEAN, CUSTOM_DATE_STYLE, ERROR, LABEL, Q1_QNA, Q2_FIRST, Q2_QNA, Book, Date,
                                 Styled, calendar_page, dataset_page, edition_entry, edition_page, file_url,
                                 iso_date_cell, month_labels, page_29_september, page_30_september,
                                 quarter_labels, split_workbook, table_cells, workbook)
from uc_e4.table import Stop, build_tables
from uc_ext_official import e4_source as s
from uc_ext_official.workbook import Workbook, is_date_format, serial_to_date

REGISTRATION = "2026-09-30T06:27:00.909545Z"


def page(kind, content, name=None):
    return s.load_page(kind, content, source=name or f"{kind}.html")


def rule(*pages):
    return s.evaluate_editions(list(pages), REGISTRATION)


QNA_30 = "GDP quarterly national accounts, UK: April to June 2026"


# --------------------------------------------------------------------------------- page parsing

def test_dataset_page_lists_editions_with_files_and_dates():
    parsed = page("dataset", dataset_page([Q2_FIRST, edition_entry(*Q1_QNA, file_type="xls", size="874.0 KB",
                                                                   edition_page=True)]))["parsed"]
    assert parsed["release_date"] == dt.date(2026, 8, 13) and parsed["next_release"] == dt.date(2026, 9, 30)
    first, second = parsed["editions"]
    assert first["label"] == Q2_FIRST[0] and first["files"][0]["url"] == file_url(Q2_FIRST[1])
    assert (first["files"][0]["file_type"], first["files"][0]["size_text"]) == ("xlsx", "1.0 KB")
    assert first["edition_page_url"] is None
    assert second["files"][0]["file_type"] == "xls" and second["files"][0]["size_text"] == "874.0 KB"
    assert second["edition_page_url"] == f"https://www.ons.gov.uk{s.DATASET_PATH}/{Q1_QNA[1]}"


def test_release_calendar_time_is_converted_from_uk_time_to_utc():
    summer = page("calendar", calendar_page(QNA_30))["parsed"]
    assert summer["release_time"] == dt.time(7, 0) and summer["lists_dataset"] and summer["status"] == "published"
    assert summer["release_utc"] == dt.datetime(2026, 9, 30, 6, 0, tzinfo=dt.timezone.utc)
    winter = page("calendar", calendar_page("Constructed release", "12 November 2026 7:00am"))["parsed"]
    assert winter["release_utc"] == dt.datetime(2026, 11, 12, 7, 0, tzinfo=dt.timezone.utc)
    assert s.parse_time_of_day("9:30am") == dt.time(9, 30) and s.parse_time_of_day("12:00pm") == dt.time(12, 0)
    assert s.parse_time_of_day("07:00") == dt.time(7, 0) and s.parse_time_of_day("13:00pm") is None
    no_time = page("calendar", calendar_page(QNA_30, "30 September 2026"))["parsed"]
    assert no_time["release_date"] == dt.date(2026, 9, 30) and no_time["release_time"] is None


def test_edition_page_dates_are_parsed():
    parsed = page("edition", edition_page())["parsed"]
    assert (parsed["release_date"], parsed["next_release"]) == (dt.date(2026, 8, 13), dt.date(2026, 9, 30))


# ---------------------------------------------------------------------------------- release rule

def test_29_september_listing_alone_selects_but_names_the_missing_evidence():
    result = rule(page("dataset", page_29_september()))
    assert result["selected"]["label"] == Q2_FIRST[0] and not result["complete"]
    assert "announces the next release for 2026-09-30" in result["missing_evidence"][0]
    older = [row for row in result["editions"] if row["label"] != Q2_FIRST[0]]
    assert all(not row["eligible"] and "not established" in row["reason"] for row in older)


def test_30_september_edition_released_at_7am_is_selected_with_the_calendar_time():
    result = rule(page("dataset", page_30_september()), page("dataset", page_29_september()),
                  page("calendar", calendar_page(QNA_30)))
    selected = result["selected"]
    assert selected["label"] == Q2_QNA[0] and result["complete"] and result["missing_evidence"] == []
    assert selected["release_utc"] == "2026-09-30T06:00:00+00:00" and selected["release_time_uk"] == "07:00"
    assert selected["file_url"] == file_url(Q2_QNA[1])
    previous = next(row for row in result["editions"] if row["label"] == Q2_FIRST[0])
    assert previous["eligible"] and previous["release_date"] == "2026-08-13"


def test_same_day_release_without_a_time_is_not_eligible_and_the_missing_time_is_named():
    result = rule(page("dataset", page_30_september()), page("dataset", page_29_september()),
                  page("calendar", calendar_page(QNA_30, "30 September 2026")))
    new = next(row for row in result["editions"] if row["label"] == Q2_QNA[0])
    assert not new["eligible"] and "time of day is not established" in new["reason"]
    assert "release-calendar record" in new["missing_evidence"][0]
    assert result["selected"]["label"] == Q2_FIRST[0] and not result["complete"]
    assert any("time of day of the release on 2026-09-30" in item for item in result["missing_evidence"])


@pytest.mark.parametrize("released, eligible, complete", [("30 September 2026 7:27am", False, False),
                                                          ("30 September 2026 7:26am", True, True),
                                                          ("30 September 2026 9:30am", False, True)])
def test_registration_instant_is_compared_in_utc_with_the_stated_minute(released, eligible, complete):
    # Registration 06:27:00.909545 UTC is 07:27 UK time: the minute 7:27am contains it, so that release cannot
    # be established as preceding it; 7:26am ends before it; 9:30am is after it.
    result = rule(page("dataset", page_30_september()), page("dataset", page_29_september()),
                  page("calendar", calendar_page(QNA_30, released)))
    new = next(row for row in result["editions"] if row["label"] == Q2_QNA[0])
    assert new["eligible"] is eligible
    # A later release established as after registration completes the evidence for the earlier edition.
    assert result["complete"] is complete
    assert result["selected"]["label"] == (Q2_QNA[0] if eligible else Q2_FIRST[0])
    if not complete:
        assert "a release time stated to the second" in " ".join(result["missing_evidence"])


def test_calendar_record_must_list_the_dataset_and_be_published():
    for calendar in (calendar_page(QNA_30, lists=False), calendar_page(QNA_30, status="provisional")):
        result = rule(page("dataset", page_30_september()), page("dataset", page_29_september()),
                      page("calendar", calendar))
        assert not next(r for r in result["editions"] if r["label"] == Q2_QNA[0])["eligible"]


def test_edition_released_after_the_registration_day_is_not_eligible():
    later = dataset_page([("Quarter 3 (July to Sept) 2026, first estimate", "quarter3julytosept2026firstestimate"),
                          Q2_QNA, Q2_FIRST], release="12 November 2026", next_release="23 December 2026")
    result = rule(page("dataset", later), page("dataset", page_30_september()), page("calendar", calendar_page(QNA_30)))
    first = result["editions"][0]
    assert not first["eligible"] and "after the registration" in first["reason"]
    assert result["selected"]["label"] == Q2_QNA[0] and result["complete"]


def test_without_any_dated_eligible_edition_the_rule_stops():
    result = rule(page("dataset", page_30_september()))
    assert result["selected"] is None and "no edition" in result["stop"]
    with pytest.raises(s.SourceStop, match="no dataset page"):
        rule(page("calendar", calendar_page(QNA_30)))


def test_an_entry_with_two_files_cannot_be_identified():
    two = dataset_page([edition_entry(*Q2_FIRST, files=2), Q1_QNA])
    result = rule(page("dataset", two))
    assert result["selected"] is None and "exactly one file" in result["stop"]


def test_conflicting_release_dates_for_one_edition_are_not_used():
    other = dataset_page([Q2_FIRST, Q1_QNA], release="14 August 2026", next_release="30 September 2026")
    result = rule(page("dataset", page_29_september()), page("dataset", other, "other.html"))
    row = next(r for r in result["editions"] if r["label"] == Q2_FIRST[0])
    assert row["release_date"] is None and any("conflicting" in e for e in row["evidence"])


# ----------------------------------------------------------------------------- page allow-list

@pytest.mark.parametrize("url, allowed", [
    ("https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi", True),
    ("https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/revisionstrianglesforukgdpabmi", True),
    ("https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi/"
     "quarter2aprtojune2026firstestimate", True),
    ("https://www.ons.gov.uk/releases/gdpquarterlynationalaccountsukapriltojune2026", True),
    (file_url(Q2_FIRST[1]), False),
    ("https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi/"
     "quarter4octtodec2017month2/previous/v1", False),
    ("https://www.ons.gov.uk/economy/grossdomesticproductgdp/timeseries/abmi/qna", False),
    ("http://www.ons.gov.uk/releases/constructed", False),
    ("https://example.invalid/releases/constructed", False),
    ("https://www.ons.gov.uk/releases/constructed?x=1", False),
    ("https://www.ons.gov.uk/economy/constructed.xlsx", False)])
def test_listing_may_request_only_landing_edition_and_calendar_pages(url, allowed):
    assert s.page_url_allowed(url)[0] is allowed


def test_fetch_refuses_before_any_request_and_saves_only_html(tmp_path):
    calls = []

    def fake(url):
        calls.append(url)
        return page_29_september(), dict(content_type="text/html; charset=UTF-8", status=200)

    with pytest.raises(ValueError, match="Refused before any request"):
        s.fetch_pages([file_url(Q2_FIRST[1])], fake, tmp_path)
    assert calls == []
    pages = s.fetch_pages([f"https://www.ons.gov.uk{s.DATASET_PATH}"], fake, tmp_path)
    assert calls == [f"https://www.ons.gov.uk{s.DATASET_PATH}"] and pages[0]["kind"] == "dataset"
    assert pages[0]["parsed"]["editions"][0]["label"] == Q2_FIRST[0]

    def not_html(url):
        return b"PK\x03\x04", dict(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with pytest.raises(ValueError, match="not return an HTML page"):
        s.fetch_pages([f"https://www.ons.gov.uk{s.DATASET_PATH}"], not_html, tmp_path / "other")
    assert not list((tmp_path / "other").glob("*.html"))


# ------------------------------------------------------------------------------------- blanking

def test_numbers_are_blanked_as_in_annex_c():
    text = "Levels 1,234 and 12.5 rose 3% or 4 per cent to £250m; id 123456; Quarter 2 2026; 1955 Q1"
    out = s.blank_numbers(text)
    for kept in ("Quarter 2 2026", "1955 Q1"):
        assert kept in out
    for gone in ("1,234", "12.5", "3%", "4 per cent", "250m", "123456"):
        assert gone not in out
    assert out.count("[num]") == 6


# ------------------------------------------------------------------------ reader: date-formatted cells

def test_number_formats_that_display_dates():
    assert is_date_format("mmm\\-yy") and is_date_format("dd/mm/yyyy") and is_date_format("[$-809]mmmm yyyy")
    assert not is_date_format("0.0") and not is_date_format("General") and not is_date_format("0.00E+00")
    assert not is_date_format('"Month" 0') and not is_date_format("#,##0")
    assert serial_to_date("42370") == dt.date(2016, 1, 1) and serial_to_date("61") == dt.date(1900, 3, 1)
    assert serial_to_date("1") == dt.date(1900, 1, 1) and serial_to_date("0", date1904=True) == dt.date(1904, 1, 1)
    with pytest.raises(ValueError):
        serial_to_date("60")


def test_date_cells_are_recognised_only_on_request_and_never_read_without_numbers():
    cells = {(1, 1): Date(dt.date(2016, 1, 1)), (1, 2): Date(dt.date(2016, 2, 1), CUSTOM_DATE_STYLE),
             (1, 3): Styled(42430.0), (1, 4): 42461, (1, 5): iso_date_cell("2016-05-01")}
    book = Workbook(Book().sheet("Dates", cells).build())
    sheet = book.sheets[0]
    plain = [(c.column, c.kind, c.text) for c in book.cells(sheet)]
    assert plain == [(1, "number", None), (2, "number", None), (3, "number", None), (4, "number", None),
                     (5, "date", "2016-05-01")]
    typed = [(c.column, c.kind, c.text) for c in book.cells(sheet, dates=True)]
    assert typed == [(1, "date", None), (2, "date", None), (3, "number", None), (4, "number", None),
                     (5, "date", "2016-05-01")]
    assert [c.text for c in book.cells(sheet, dates=True, numbers=True)][:2] == ["42370", "42401"]
    assert book.date_styles == frozenset({1, 2}) and book.date1904 is False


# --------------------------------------------------------------------- structure mapping (unit)

def structure(content):
    return s.read_structure(Workbook(content))


def tables(content):
    found = structure(content)
    if found["stop"] is not None:
        raise found["stop"]
    return build_tables(found["parts"])


def test_one_table_below_titles_is_found_and_no_level_is_read():
    found = structure(workbook(notes_rows=("Note 1: constructed notes block.",)))
    assert found["stop"] is None and len(found["parts"]) == 1
    part = found["parts"][0]
    assert part.vintage_labels == tuple(month_labels()) and part.quarter_labels == tuple(quarter_labels())
    values = [v for row in part.cells for v in row if v is not None]
    assert values and all(v != v for v in values)             # numeric cells are NaN stand-ins: no value read
    texts = [t["text"] for t in found["texts"]]
    assert "Note 1: constructed notes block." in texts and "Jan 2016" not in texts
    built = build_tables(found["parts"])
    assert built.manifest["earliest_vintage"] == "Jan 2016" and built.manifest["earliest_reference_quarter"] == "1955Q1"


def test_cell_kinds_in_the_table_include_number_as_text_error_and_logical():
    for value in ("12.5", ERROR, BOOLEAN, Date(dt.date(2016, 1, 1))):
        with pytest.raises(Stop) as stop:
            tables(workbook(overrides={(0, 0): value}))
        assert stop.value.step == "4.2"
    built = tables(workbook(overrides={(0, 0): "..", (1, 0): "x", (2, 0): None}))
    kinds = built.availability.kinds[:, 0]
    assert list(kinds[:3]) == ["marker", "marker", "empty"] and kinds[3] == "numeric"


def test_labels_that_do_not_parse_and_repeated_or_disordered_labels_stop():
    cases = [(dict(vintages=["Jan 2016", "Feb 2016 (r)", "Mar 2016"]), "4.3"),
             (dict(quarters=quarter_labels(n=3) + ["1955 Q4 [note 1]"] + quarter_labels((1956, 1), 4)), "4.3"),
             (dict(quarters=quarter_labels(n=4) + quarter_labels(n=1)), "4.3"),
             (dict(vintages=["Jan 2016", "Mar 2016", "Feb 2016"]), "4.4")]
    for options, step in cases:
        with pytest.raises(Stop) as stop:
            tables(workbook(**options))
        assert stop.value.step == step


def test_two_vintages_with_the_same_release_month_keep_table_order():
    built = tables(workbook(vintages=["Jan 2016", "Feb 2016", "Feb 2016", "Mar 2016"]))
    assert [v.position for v in built.availability.vintages] == [0, 1, 2, 3]


def test_a_reference_quarter_with_no_row_is_no_level():
    quarters = quarter_labels(n=8)
    del quarters[3]
    built = tables(workbook(quarters=quarters))
    assert built.availability.row((1955, 4)) is None and not built.availability.present(0, (1955, 4))


def test_dates_typed_as_dates_and_as_text_parse_and_bare_numbers_do_not():
    typed = [Date(dt.date(2016, m, 1)) for m in (1, 2, 3)] + [Date(dt.date(2016, 4, 1), CUSTOM_DATE_STYLE)]
    built = tables(workbook(vintages=typed))
    assert [v.release_month for v in built.availability.vintages] == [(2016, 1), (2016, 2), (2016, 3), (2016, 4)]
    assert tables(workbook(vintages=["2016-01", "2016-02-01", "Mar 2016"])).manifest["latest_vintage"] == "Mar 2016"
    with pytest.raises(Stop) as stop:
        tables(workbook(vintages=["Jan 2016", 42401, "Mar 2016"]))
    assert stop.value.step == "4.3" and "number" in stop.value.detail["label"]
    with pytest.raises(Stop) as stop:
        tables(workbook(vintages=["Jan 2016", Styled(42401.0), "Mar 2016"]))
    assert stop.value.step == "4.3"


def test_no_table_two_tables_and_unlabelled_cells_stop_at_step_one():
    with pytest.raises(Stop, match="no vintage-by-quarter table") as stop:
        tables(Book().sheet("Notes", {(1, 1): LABEL, (2, 1): "Only notes here"}).build())
    assert stop.value.step == "4.1"
    second = table_cells(top=40, left=1)
    with pytest.raises(Stop, match="2 vintage-by-quarter tables"):
        tables(Book().sheet("Two", {**table_cells(top=3), **second}).build())
    hidden = ("Hidden copy", table_cells(top=3), "hidden")
    with pytest.raises(Stop, match="overlap"):
        tables(workbook(extra_sheets=(hidden,)))
    stray = table_cells(top=3)
    stray[(5, 12)] = "stray note beside the table"
    with pytest.raises(Stop, match="outside the columns"):
        tables(Book().sheet("T", stray).build())


def test_hidden_sheets_without_a_table_and_blank_separator_columns_are_allowed():
    notes = ("Hidden notes", {(1, 1): "Constructed hidden notes"}, "hidden")
    found = structure(workbook(extra_sheets=(notes,), separator_after=2))
    assert found["stop"] is None and [sh["state"] for sh in found["sheets"]] == ["visible", "hidden"]
    assert found["shaped"][0]["separator_columns"] == [5]
    assert len(build_tables(found["parts"]).availability.vintages) == 6


def test_table_split_across_two_sheets_joinable_and_not():
    joined = tables(split_workbook())
    assert joined.manifest["parts"] == "Part 1+Part 2" and joined.manifest["n_vintages"] == 6
    with pytest.raises(Stop, match="not identical"):
        tables(split_workbook(second_quarters=quarter_labels((1955, 2))))
    with pytest.raises(Stop, match="overlap"):
        tables(split_workbook(second_vintages=month_labels((2016, 3), 3)))


# ------------------------------------------------------------- title, cover and notes (release rule)

EDITION = dict(label=Q2_QNA[0], release_date="2026-09-30")


def conflicts(*texts):
    return s.check_title_and_notes([dict(where=f"t{i}", text=t) for i, t in enumerate(texts)], EDITION)


def test_titles_naming_the_selected_edition_and_release_date_pass():
    assert conflicts("Quarter 2 (Apr to June) 2026, quarterly national accounts",
                     "Released 30 September 2026", "Next release: 12 November 2026",
                     "Data from 1955 Q1; base year 2023") == []


def test_titles_naming_another_edition_or_release_date_stop():
    found = conflicts("Quarter 2 (Apr to June) 2026, first estimate", "Published 13 August 2026",
                      "Release date: 2026-08-13", "Next release: 30 September 2026")
    assert [c["kind"] for c in found] == ["another edition", "another release date", "another release date",
                                          "another release date"]


# ---------------------------------------------------------------- the saved pages of 29 September

PAGES = os.environ.get("UC_E4_ONS_PAGES")
saved = pytest.mark.skipif(not PAGES, reason="UC_E4_ONS_PAGES does not name the directory of the saved pages")
HASHES = {"landing_realtimedatabase_20260929T195308Z.html":
          "caef462265f03d648cce371e5beca175308ab678edc907e2ee1932ee582979b1",
          "edition_q4_2017_month2_20260929T195401Z.html":
          "95844f500247484681dd2994925f8c08016fb21e132b26e70a45a6e1b4ad2c68",
          "release_calendar_qna_jan_mar_2026_20260929T195416Z.html":
          "9b29d621a870405f0335ad39fc227d9a6b8991dc705c50484c4a2dfcf91bffb2"}


def saved_page(name):
    content = (Path(PAGES) / name).read_bytes()
    assert s.load_page("edition", content, source=name)["sha256"] == HASHES[name]       # Annex C
    return content


@saved
def test_saved_pages_parse_as_annex_c_states():
    landing = s.load_page("dataset", saved_page("landing_realtimedatabase_20260929T195308Z.html"), source="landing")
    parsed = landing["parsed"]
    assert len(parsed["editions"]) == 82 and parsed["release_date"] == dt.date(2026, 8, 13)
    assert parsed["next_release"] == dt.date(2026, 9, 30) and parsed["editions"][0]["label"] == Q2_FIRST[0]
    assert parsed["editions"][-1]["label"] == "Quarter 4 (Oct to Dec) 2015, Month 3"
    assert sum(e["files"][0]["file_type"] == "xlsx" for e in parsed["editions"]) == 39
    edition = s.load_page("edition", saved_page("edition_q4_2017_month2_20260929T195401Z.html"), source="e")["parsed"]
    assert edition["release_date"] == dt.date(2026, 8, 13)     # the dataset's date, not the 2018 edition's own
    calendar = s.load_page("calendar", saved_page("release_calendar_qna_jan_mar_2026_20260929T195416Z.html"),
                           source="c")["parsed"]
    assert calendar["release_utc"] == dt.datetime(2026, 6, 30, 6, 0, tzinfo=dt.timezone.utc) and calendar["lists_dataset"]
    result = rule(landing)
    assert result["selected"]["label"] == Q2_FIRST[0] and not result["complete"]


def variant_30_september(*, released="30 September 2026 7:00am"):
    """Constructed variants of the saved pages: a new first entry released on 30 September 2026, and the
    release-calendar record moved to that release (title and dates changed; the time removed if asked)."""
    landing = saved_page("landing_realtimedatabase_20260929T195308Z.html").decode("utf-8")
    entry = edition_entry(*Q2_QNA)
    marker = '<div class="show-hide show-hide--light js-show-hide'
    position = landing.index(marker)
    landing = landing[:position] + entry + landing[position:]
    landing = landing.replace("<div>13 August 2026</div>", "<div>30 September 2026</div>", 1)
    landing = landing.replace("30 September 2026\n", "12 November 2026\n", 1)
    calendar = saved_page("release_calendar_qna_jan_mar_2026_20260929T195416Z.html").decode("utf-8")
    calendar = calendar.replace("January to March 2026", "April to June 2026").replace("30 June 2026 7:00am", released)
    return landing.encode("utf-8"), calendar.encode("utf-8")


@saved
@pytest.mark.parametrize("released, selected, complete", [("30 September 2026 7:00am", Q2_QNA[0], True),
                                                          ("30 September 2026", Q2_FIRST[0], False),
                                                          ("30 September 2026 9:30am", Q2_FIRST[0], True)])
def test_variants_of_the_saved_pages_for_30_september(released, selected, complete):
    landing, calendar = variant_30_september(released=released)
    new = s.load_page("dataset", landing, source="landing-30")
    assert new["parsed"]["editions"][0]["label"] == Q2_QNA[0] and new["parsed"]["next_release"] == dt.date(2026, 11, 12)
    old = s.load_page("dataset", saved_page("landing_realtimedatabase_20260929T195308Z.html"), source="landing-29")
    result = rule(new, old, s.load_page("calendar", calendar, source="calendar-30"))
    assert result["selected"]["label"] == selected and result["complete"] is complete


def test_merged_titles_comments_and_document_properties_are_printed_with_numbers_blanked():
    content = workbook(title_rows=("Constructed title: index 12.5, 3% and £250m",), merged=("A1:F1",),
                       comments=(("A1", "Comment with 1,234 and 123456"),), doc_title="Constructed 98765.4")
    found = structure(content)
    sheet = found["sheets"][0]
    assert sheet["merged"] == ["A1:F1"] and found["document_properties"]["title"] == "Constructed [num]"
    printed = " ".join(t["text"] for t in sheet["texts"])
    assert "Constructed title: index [num], [num] and [num]" in printed and "Comment with [num] and [num]" in printed
    assert found["stop"] is None
