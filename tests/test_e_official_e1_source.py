"""E1 X.2 rules on artificial workbooks: version statement, header-only output, selection, stop rules,
territory. No test reads Bank of England data."""
import json

import numpy as np
import pytest

from e_official_artificial import (HEADLINE, LABEL, TERRITORY, XlsxWriter, artificial_levels, artificial_workbook,
                        standard_columns)
from uc_ext import e1
from uc_ext_official import e1_source as s
from uc_ext_official.workbook import Workbook


def workbook(**options):
    return Workbook(artificial_workbook(**options))


# ------------------------------------------------------------------------------ version

def test_version_statement_identifies_version_3_1():
    statements = s.version_statements(workbook())
    result = s.check_version(statements)
    assert result["statement"]["version"] == "3.1" and result["statement"]["location"] == "Cover (artificial)!A2"
    assert result["designated_by_operator"] is False
    other = [x for x in result["other_versions"] if x["version"] == "9.0"]
    assert other and other[0]["level"] == "other"      # another dataset's version in source notes: recorded only


@pytest.mark.parametrize("options, message", [
    (dict(version_text=None), "do not identify it as version 3.1"),
    (dict(version_text="Version 3.0 (artificial)"), "do not identify it as version 3.1"),
    (dict(version_text="v3.1 (artificial)", extra_cover=("Previous release: version 3.0",)), "another version"),
    (dict(version_text="Version 3.1.2 (artificial)"), "do not identify it as version 3.1"),
])
def test_version_stops_before_any_value(options, message):
    with pytest.raises(s.SourceStop, match=message) as stop:
        s.check_version(s.version_statements(workbook(**options)))
    assert stop.value.stage == "version"


def test_operator_may_name_the_files_own_statement_when_others_are_listed():
    statements = s.version_statements(workbook(version_text="This file: version 3.1 (artificial)",
                                               extra_cover=("History: version 3.0, version 2.2",)))
    result = s.check_version(statements, "Cover (artificial)!A2")
    assert result["designated_by_operator"] is True and result["statement"]["version"] == "3.1"
    with pytest.raises(s.SourceStop, match="does not identify"):
        s.check_version(statements, "Cover (artificial)!A3")
    with pytest.raises(s.SourceStop, match="No version statement"):
        s.check_version(statements, "Cover (artificial)!A9")


def test_version_forms_and_document_properties():
    content = XlsxWriter(title="Artificial dataset, Version: 3.1").sheet("Cover", {1: {1: LABEL}}).build()
    statement = s.check_version(s.version_statements(Workbook(content)))["statement"]
    assert statement["location"] == "docProps/core.xml:title"
    assert [m.group(1) for m in s.VERSION.finditer("V3.1; vers. 3.1; rev3.1; (v 3.1)")] == ["3.1", "3.1", "3.1"]


# ------------------------------------------------------------------ header-only and selection

def test_selection_rule_picks_the_uk_or_geographically_consistent_real_gdp_column():
    output = s.header_only(workbook())
    selection = output["selection"]
    assert (selection["sheet"], selection["column"], selection["year_column"], selection["first_data_row"]) == (
        HEADLINE, "C", "A", 6)
    assert selection["rule_step"] == 2 and selection["units"] == "GBP mn, artificial prices"
    assert selection["label"].startswith("Real GDP at market prices, UK")
    assert [c["column"] for c in output["real_gdp_columns"]] == ["B", "C"]        # per head and nominal excluded
    assert output["layout_source"] == "cell types"


def test_header_only_output_holds_no_numeric_cell():
    wb = Workbook(artificial_workbook())
    levels = {cell.text for cell in wb.cells(wb.sheet(HEADLINE), numbers=True, columns={2, 3, 4, 5})
              if cell.kind == "number"}
    assert len(levels) > 1000
    output = s.header_only(wb)
    text = s.format_header_only(output, s.check_version(s.version_statements(wb)), "0" * 64)
    serialised = json.dumps(output)
    assert not [value for value in levels if value in text or value in serialised]
    assert "Real GDP at market prices" in text and "Units" in text


def test_numbers_are_never_parsed_by_the_header_stage(monkeypatch):
    wb = Workbook(artificial_workbook())
    original = Workbook._classify

    def watched(self, element, numbers):
        assert numbers is False, "the header stage asked for numeric values"
        return original(self, element, numbers)
    monkeypatch.setattr(Workbook, "_classify", watched)
    s.header_only(wb)
    s.version_statements(wb)


def test_single_real_gdp_column_is_taken_without_the_tie_break():
    columns = [standard_columns()[1], standard_columns()[3]]
    selection = s.header_only(workbook(columns=columns))["selection"]
    assert selection["column"] == "B" and selection["rule_step"] == 1


def test_merged_heading_over_territory_columns_is_propagated():
    writer = XlsxWriter()
    writer.sheet("Cover", {1: {1: LABEL}, 2: {1: "Version 3.1"}})
    body = {1: {1: "Artificial", 2: "Real GDP (artificial)"},
            2: {1: "Description", 2: "England (artificial)", 3: "UK (artificial)"},
            3: {1: "Units", 2: "GBP", 3: "GBP"}}
    for offset, (year, level) in enumerate(artificial_levels().items()):
        body[5 + offset] = {1: year, 2: level * .8, 3: level}
    writer.sheet(HEADLINE, body, merged=("B1:C1",))
    output = s.header_only(Workbook(writer.build()))
    assert [c["column"] for c in output["real_gdp_columns"]] == ["B", "C"]
    assert output["selection"]["column"] == "C" and output["selection"]["rule_step"] == 2
    assert any(c["inherited"] for c in output["selection"]["header_cells"])


@pytest.mark.parametrize("options, stage, message", [
    (dict(headline_name="A1. Main series (artificial)"), "selection", "0 sheets"),
    (dict(second_headline=True), "selection", "2 sheets"),
    (dict(columns=[standard_columns()[2], standard_columns()[3]]), "selection", "No column"),
    (dict(columns=[standard_columns()[1], ("Real GDP, United Kingdom (artificial)", None, None, lambda y, v: v)]),
     "selection", "2 of them"),
    (dict(columns=[standard_columns()[0], ("Real GDP of Scotland (artificial)", None, None, lambda y, v: v)]),
     "selection", "0 of them"),
])
def test_selection_stops(options, stage, message):
    with pytest.raises(s.SourceStop, match=message) as stop:
        s.header_only(workbook(**options))
    assert stop.value.stage == stage and "sheets" in stop.value.details


def test_layout_can_be_given_by_the_operator_and_is_recorded():
    output = s.header_only(workbook(), first_data_row=6, year_column="A")
    assert output["layout_source"] == "operator" and output["selection"]["column"] == "C"
    with pytest.raises(s.SourceStop, match="No data row"):
        s.header_only(workbook(), first_data_row=5)       # row 5 is blank


# ------------------------------------------------------------------------- extraction

def selected(**options):
    wb = workbook(**options)
    return wb, s.header_only(wb)["selection"]


def test_extraction_gives_317_levels_and_316_growth_values():
    wb, selection = selected()
    years, levels, growth_years, growth, details = s.extract_levels(wb, selection)
    expected = artificial_levels()
    assert years == tuple(range(1700, 2017)) and len(levels) == 317 and len(growth) == 316
    assert np.allclose(levels, [round(expected[y], 6) for y in range(1700, 2017)], rtol=0, atol=1e-9)
    assert growth_years[0] == 1701 and growth_years[-1] == 2016
    assert np.allclose(growth, e1.annual_growth(list(years), list(levels))[1])
    assert details["rows_in_sample"] == 317 and details["first_row"] == 6 + 100


def test_rows_outside_1700_2016_are_never_read(monkeypatch):
    wb, selection = selected()
    calls = []
    original = Workbook.cells

    def watched(self, sheet, **kwargs):
        calls.append(kwargs)
        return original(self, sheet, **kwargs)
    monkeypatch.setattr(Workbook, "cells", watched)
    s.extract_levels(wb, selection)
    value_call = [c for c in calls if c.get("columns") == {3}][0]
    assert value_call["rows"] == set(range(106, 106 + 317))       # only the sample rows of the value column


@pytest.mark.parametrize("options, message", [
    (dict(years=[y for y in range(1600, 2021) if y != 1850]), "not exactly 317 contiguous"),
    (dict(years=[*range(1600, 2021), 1900]), "duplicated"),
    (dict(value_overrides={(1750, 3): -1.0}), "Non-positive"),
    (dict(value_overrides={(1750, 3): 0.0}), "Non-positive"),
    (dict(value_overrides={(1750, 3): "n/a"}), "Non-numeric"),
    (dict(value_overrides={(1750, 3): None}), "Non-numeric"),
    (dict(years=range(1600, 2011)), "not exactly 317 contiguous"),
    (dict(descending=True), "not exactly 317 contiguous"),
    (dict(year_overrides={1800: 1800.5}), "not a whole year"),
])
def test_sample_stop_rules(options, message):
    wb, selection = selected(**options)
    with pytest.raises(s.SourceStop, match=message) as stop:
        s.extract_levels(wb, selection)
    assert stop.value.stage == "sample"


def test_values_outside_the_sample_do_not_matter():
    wb, selection = selected(value_overrides={(1650, 3): "n/a", (2019, 3): -5.0})
    assert len(s.extract_levels(wb, selection)[1]) == 317
    wb, selection = selected(year_overrides={1650: 1650.5, 2020: 0.25})     # not years, outside the block
    details = s.extract_levels(wb, selection)[4]
    assert details["levels"] == 317 and details["ambiguous_year_cells_outside_sample"] == 2


def test_text_years_are_accepted_only_when_they_are_whole_numbers():
    wb, selection = selected(year_overrides={1900: "1900"})
    assert len(s.extract_levels(wb, selection)[1]) == 317
    wb, selection = selected(year_overrides={1900: "1900*"})
    with pytest.raises(s.SourceStop, match="not exactly 317"):
        s.extract_levels(wb, selection)


# ---------------------------------------------------------------------------- territory

def test_territory_is_verified_against_the_workbook_text():
    wb = workbook()
    stretches = s.validate_territory(wb, TERRITORY)
    assert [(x["first_year"], x["last_year"], x["territory"]) for x in stretches] == [
        (1700, 1706, "England"), (1707, 1800, "Great Britain"), (1801, 2016, "UK")]
    assert s.stretches_for_flags(dict(stretches=stretches))[0] == (1700, 1706, "England")
    unstated = dict(stretches=[dict(first_year=1700, last_year=2016, territory=s.NOT_STATED, evidence=[])])
    assert s.validate_territory(wb, unstated)[0]["territory"] == s.NOT_STATED


def _with(index, **changes):
    spec = json.loads(json.dumps(TERRITORY))
    spec["stretches"][index].update(changes)
    return spec


@pytest.mark.parametrize("spec, message", [
    (dict(stretches=[]), "non-empty"),
    (_with(1, first_year=1708), "contiguously"),
    (_with(2, last_year=2015), "end in 2015"),
    (_with(2, last_year=2017), "contiguously"),
    (_with(0, territory=""), "named"),
    (_with(0, evidence=[]), "quote"),
    (_with(0, evidence=[dict(location=f"{HEADLINE}!C4", quote="Scotland to 1706")]), "not in the workbook"),
    (_with(0, evidence=[dict(location=f"{HEADLINE}!C7", quote="England to 1706")]), "not in the workbook"),
    (_with(0, evidence=[dict(location="Absent!A1", quote="England")]), "not in the workbook"),
    (_with(0, first_year="1700"), "integers"),
])
def test_territory_refusals(spec, message):
    with pytest.raises(ValueError, match=message):
        s.validate_territory(workbook(), spec)


def test_territory_evidence_may_come_from_a_note():
    wb = workbook(notes=(("C2", "Artificial note: UK from 1801"),))
    spec = _with(2, evidence=[dict(location=f"{HEADLINE}!C2 (note)", quote="UK from 1801")])
    assert s.validate_territory(wb, spec)[2]["evidence"][0]["location"].endswith("(note)")
