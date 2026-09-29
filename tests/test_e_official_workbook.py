"""The standard-library xlsx reader, on artificial workbooks only."""
import io
import zipfile

import pytest

from e_official_artificial import HEADLINE, XlsxWriter, artificial_workbook
from uc_ext_official import workbook as w


def test_column_letters_and_references():
    assert [w.column_letter(n) for n in (1, 26, 27, 52, 703)] == ["A", "Z", "AA", "AZ", "AAA"]
    assert all(w.column_index(w.column_letter(n)) == n for n in range(1, 2000))
    assert w.split_reference("AB12") == (12, 28)
    for bad in ("", "12", "A0", "a1", "A1:B2"):
        with pytest.raises(ValueError):
            w.split_reference(bad)
    with pytest.raises(ValueError):
        w.column_letter(0)


@pytest.mark.parametrize("inline", [False, True])
def test_types_are_read_from_markup_and_numbers_are_not_read_by_default(inline):
    book = XlsxWriter(inline_strings=inline, title="Artificial title v3.1").sheet(
        "S (artificial)", {1: {1: "Label", 2: 12.5, 3: "  "}, 3: {2: 7}},
        raw_cells=[(2, 1, '<c r="{ref}" t="b"><v>1</v></c>'), (2, 2, '<c r="{ref}" t="e"><v>#N/A</v></c>'),
                   (2, 3, '<c r="{ref}" t="str"><f>A1</f><v>formula text</v></c>'),
                   (2, 4, '<c r="{ref}" s="3"/>')]).build()
    workbook = w.Workbook(book)
    sheet = workbook.sheets[0]
    cells = list(workbook.cells(sheet))
    assert [(c.ref, c.kind, c.text) for c in cells] == [
        ("A1", "text", "Label"), ("B1", "number", None), ("A2", "boolean", "1"), ("B2", "error", "#N/A"),
        ("C2", "text", "formula text"), ("B3", "number", None)]
    numbers = [c.text for c in workbook.cells(sheet, numbers=True) if c.kind == "number"]
    assert numbers == ["12.5", "7"]                     # raw text, never converted by the reader
    assert [c.ref for c in workbook.cells(sheet, max_row=1)] == ["A1", "B1"]
    assert [c.ref for c in workbook.cells(sheet, columns={2}, rows={3})] == ["B3"]
    assert workbook.text_cell(sheet, "A1") == "Label" and workbook.text_cell(sheet, "B1") is None
    assert workbook.document_properties() == {"title": "Artificial title v3.1"}


def test_notes_merged_ranges_and_sheets():
    content = artificial_workbook(merged=("B2:C2",), notes=(("C2", "UK note (artificial)"),))
    workbook = w.Workbook(content)
    assert [s.name for s in workbook.sheets][2] == HEADLINE
    sheet = workbook.sheet(HEADLINE)
    assert workbook.merged_ranges(sheet) == ((2, 2, 2, 3),)
    assert workbook.notes(sheet) == (w.Note("C2", "comment", "UK note (artificial)"),)
    with pytest.raises(w.WorkbookError):
        workbook.sheet("absent")


def test_non_workbooks_are_refused():
    with pytest.raises(w.WorkbookError, match="zip"):
        w.Workbook(b"<html>challenge page</html>")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("readme.txt", "not a workbook")
    with pytest.raises(w.WorkbookError, match="Content_Types"):
        w.Workbook(buffer.getvalue())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
    with pytest.raises(w.WorkbookError, match="workbook part"):
        w.Workbook(buffer.getvalue())


def test_malformed_sheet_xml_is_reported():
    content = XlsxWriter().sheet("S", {1: {1: "x"}}).build()
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(buffer, "w") as target:
        for item in source.infolist():
            data = source.read(item)
            target.writestr(item, b"<worksheet><sheetData><row>" if item.filename.endswith("sheet1.xml") else data)
    workbook = w.Workbook(buffer.getvalue())
    with pytest.raises(w.WorkbookError, match="Malformed"):
        list(workbook.cells(workbook.sheets[0]))
