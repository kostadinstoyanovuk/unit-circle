"""A minimal, standard-library reader for Office Open XML workbooks (.xlsx), built for header-only work.

A cell's type is read from its markup (the `t` attribute and whether it holds a value); a numeric
cell's value is returned only when the caller asks for numbers (`numbers=True`), and then as the raw
text of its `<v>` element, never converted here. Text cells (shared, inline and formula strings),
cell notes (legacy comments and threaded comments) and document properties can therefore be read
without any numeric value being parsed. No third-party package is needed, so the research lock is
unchanged. Workbook structure is streamed (xml.etree.ElementTree.iterparse) and elements are cleared
as they are consumed, so large sheets are read in bounded memory.
"""
from __future__ import annotations

import io
import posixpath
import re
from typing import Iterator, NamedTuple
import xml.etree.ElementTree as ET
import zipfile

OFFICE_DOCUMENT = "/officeDocument"
SHARED_STRINGS = "/sharedStrings"
COMMENTS = "/comments"
THREADED_COMMENT = "/threadedComment"
STYLES = "/styles"
REFERENCE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]*)$")
# Built-in number formats that display a date or a time (ECMA-376 Part 1, 18.8.30, including the
# East Asian built-in date formats 27-36 and 50-58).
BUILTIN_DATE_FORMATS = frozenset(range(14, 23)) | frozenset(range(27, 37)) | frozenset({45, 46, 47}) | frozenset(
    range(50, 59))


def is_date_format(code: str) -> bool:
    """True when a custom number-format code displays a date or a time: after removing quoted text,
    escaped and padding characters, bracketed sections (colours, conditions, locales) and scientific
    exponents (E+, E-), a day, month, year, hour or second code (d, m, y, h, s) remains. 'General' is not
    a date."""
    text = re.sub(r'"[^"]*"', "", code or "")
    text = re.sub(r"\\.|_.|\*.", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"[eE][+-]", "", text)
    if text.strip().lower() == "general":
        return False
    return bool(re.search(r"[dmyhs]", text, re.IGNORECASE))


def serial_to_date(serial: str, date1904: bool = False):
    """The calendar date of a date-formatted cell's serial number (the fraction of a day is dropped).

    1900 system: serial 1 is 1900-01-01, serial 60 is the non-existent 1900-02-29 (refused), and from 61 on
    the date is 1899-12-30 plus the serial. 1904 system: 1904-01-01 plus the serial. ValueError otherwise.
    """
    import datetime as _dt
    import math
    value = float(serial)
    if not math.isfinite(value) or value < 0:
        raise ValueError("not a date serial number")
    days = int(value)
    if date1904:
        return _dt.date(1904, 1, 1) + _dt.timedelta(days=days)
    if days == 0 or days == 60:
        raise ValueError("serial 0 or 60 is not a calendar date in the 1900 system")
    return (_dt.date(1899, 12, 31) + _dt.timedelta(days=days)) if days < 60 else (
        _dt.date(1899, 12, 30) + _dt.timedelta(days=days))


class WorkbookError(ValueError):
    """The bytes are not a readable xlsx workbook, or a requested part is missing."""


class Cell(NamedTuple):
    row: int                 # one-based
    column: int              # one-based
    kind: str                # 'text', 'number', 'boolean', 'error', 'date' or 'empty'
    text: str | None         # text of a non-numeric cell; a number's raw <v> text only when numbers=True

    @property
    def ref(self) -> str:
        return f"{column_letter(self.column)}{self.row}"


class Sheet(NamedTuple):
    index: int               # zero-based position in the workbook
    name: str
    state: str               # 'visible', 'hidden' or 'veryHidden'
    path: str                # part name inside the package, e.g. xl/worksheets/sheet1.xml


class Note(NamedTuple):
    ref: str
    kind: str                # 'comment' or 'threaded comment'
    text: str


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attribute(element, name):
    for key, value in element.attrib.items():
        if _local(key) == name:
            return value
    return None


def column_letter(index: int) -> str:
    """1 -> A, 26 -> Z, 27 -> AA."""
    if isinstance(index, bool) or not isinstance(index, int) or index < 1:
        raise ValueError("Column numbers are positive integers")
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def column_index(letters: str) -> int:
    """A -> 1, Z -> 26, AA -> 27."""
    if not isinstance(letters, str) or not re.fullmatch(r"[A-Z]{1,3}", letters):
        raise ValueError(f"Invalid column letters {letters!r}")
    index = 0
    for letter in letters:
        index = index * 26 + ord(letter) - 64
    return index


def split_reference(reference: str) -> tuple[int, int]:
    """'B12' -> (row 12, column 2)."""
    match = REFERENCE.match(reference or "")
    if not match:
        raise ValueError(f"Invalid cell reference {reference!r}")
    return int(match.group(2)), column_index(match.group(1))


def _text_of(element) -> str:
    """Text of a string item: plain <t> or rich-text runs <r><t>; phonetic runs (<rPh>) are skipped."""
    parts = []
    for child in element:
        name = _local(child.tag)
        if name == "t":
            parts.append(child.text or "")
        elif name == "r":
            parts.extend(grandchild.text or "" for grandchild in child if _local(grandchild.tag) == "t")
    return "".join(parts)


class Workbook:
    """Read-only access to one xlsx package held in memory."""

    def __init__(self, content: bytes):
        if not isinstance(content, (bytes, bytearray)) or not zipfile.is_zipfile(io.BytesIO(content)):
            raise WorkbookError("The content is not a zip package, so it is not an xlsx workbook")
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(bytes(content)))
        except zipfile.BadZipFile as error:
            raise WorkbookError(f"Unreadable zip package: {error}") from error
        self._names = set(self._zip.namelist())
        if "[Content_Types].xml" not in self._names:
            raise WorkbookError("The package has no [Content_Types].xml, so it is not an Office document")
        self.workbook_path = self._office_document()
        self._relationships = self._read_relationships(self.workbook_path)
        self.sheets = self._read_sheets()
        self._shared = None
        self._date_styles = None

    # -------------------------------------------------------------------- package structure

    def _xml(self, part):
        if part not in self._names:
            raise WorkbookError(f"The package has no part {part}")
        try:
            return ET.fromstring(self._zip.read(part))
        except ET.ParseError as error:
            raise WorkbookError(f"Malformed XML in {part}: {error}") from error

    @staticmethod
    def _rels_path(part):
        directory, name = posixpath.split(part)
        return posixpath.join(directory, "_rels", f"{name}.rels")

    def _read_relationships(self, part):
        """{id: (type, target part)} of one part; targets resolved against the part's directory."""
        path = self._rels_path(part)
        if path not in self._names:
            return {}
        result = {}
        for element in self._xml(path):
            if _local(element.tag) != "Relationship" or element.get("TargetMode") == "External":
                continue
            target = element.get("Target", "")
            resolved = (target.lstrip("/") if target.startswith("/")
                        else posixpath.normpath(posixpath.join(posixpath.dirname(part), target)))
            result[element.get("Id")] = (element.get("Type", ""), resolved)
        return result

    def _office_document(self):
        for kind, target in self._read_relationships("").values() if "_rels/.rels" in self._names else []:
            if kind.endswith(OFFICE_DOCUMENT):
                return target
        if "xl/workbook.xml" in self._names:
            return "xl/workbook.xml"
        raise WorkbookError("The package has no workbook part, so it is not an xlsx workbook")

    def _read_sheets(self):
        root = self._xml(self.workbook_path)
        sheets = []
        for element in root.iter():
            if _local(element.tag) != "sheet":
                continue
            relationship = self._relationships.get(_attribute(element, "id"))
            if relationship is None:
                raise WorkbookError(f"Sheet {element.get('name')!r} has no relationship target")
            sheets.append(Sheet(len(sheets), element.get("name", ""), element.get("state", "visible"),
                                relationship[1]))
        if not sheets:
            raise WorkbookError("The workbook lists no sheets")
        return tuple(sheets)

    def sheet(self, name: str) -> Sheet:
        matches = [sheet for sheet in self.sheets if sheet.name == name]
        if len(matches) != 1:
            raise WorkbookError(f"The workbook has {len(matches)} sheets named {name!r}")
        return matches[0]

    @property
    def shared_strings(self) -> tuple[str, ...]:
        if self._shared is None:
            paths = [target for kind, target in self._relationships.values() if kind.endswith(SHARED_STRINGS)]
            self._shared = (tuple(_text_of(item) for item in self._xml(paths[0]) if _local(item.tag) == "si")
                            if paths else ())
        return self._shared

    @property
    def date_styles(self) -> frozenset:
        """Indices of the cell formats (cellXfs) whose number format displays a date or a time.

        Read from the workbook's styles part (built-in format ids and custom format codes); empty when the
        package has no styles part. Only formats are read here, never a cell value.
        """
        if self._date_styles is None:
            paths = [target for kind, target in self._relationships.values() if kind.endswith(STYLES)]
            found = set()
            if paths:
                root = self._xml(paths[0])
                custom = {}
                for element in root.iter():
                    if _local(element.tag) == "numFmt":
                        try:
                            custom[int(element.get("numFmtId", ""))] = element.get("formatCode", "")
                        except ValueError:
                            continue
                for element in root:
                    if _local(element.tag) != "cellXfs":
                        continue
                    for index, xf in enumerate(child for child in element if _local(child.tag) == "xf"):
                        try:
                            number_format = int(xf.get("numFmtId", "0"))
                        except ValueError:
                            continue
                        if (number_format in custom and is_date_format(custom[number_format])) or (
                                number_format not in custom and number_format in BUILTIN_DATE_FORMATS):
                            found.add(index)
            self._date_styles = frozenset(found)
        return self._date_styles

    @property
    def date1904(self) -> bool:
        """True when the workbook uses the 1904 date system (workbookPr date1904)."""
        for element in self._xml(self.workbook_path).iter():
            if _local(element.tag) == "workbookPr":
                return str(element.get("date1904", "")).lower() in ("1", "true")
        return False

    # --------------------------------------------------------------------------------- cells

    def cells(self, sheet: Sheet, *, numbers: bool = False, max_row: int | None = None,
              columns: set[int] | None = None, rows: set[int] | None = None,
              dates: bool = False) -> Iterator[Cell]:
        """Every non-blank cell of a sheet in document order (row by row).

        numbers=False (the default) never reads a numeric value: such cells come back with kind
        'number' and text None. max_row stops the stream after that row; columns and rows restrict the
        cells returned, and a cell outside them is skipped before its content is read (cells are
        located by their references, not by their values). dates=True (not the default) returns a
        numeric cell whose format displays a date (`date_styles`) with kind 'date'; its text is the raw
        serial number only when numbers=True. With dates=False the behaviour is unchanged.
        """
        date_styles = self.date_styles if dates else frozenset()
        if sheet.path not in self._names:
            raise WorkbookError(f"The package has no part {sheet.path} for sheet {sheet.name!r}")
        row_number, column_number = 0, 0
        with self._zip.open(sheet.path) as stream:
            try:
                for event, element in ET.iterparse(stream, events=("start", "end")):
                    name = _local(element.tag)
                    if event == "start":
                        if name == "row":
                            given = element.get("r")
                            row_number = int(given) if given else row_number + 1
                            column_number = 0
                            if max_row is not None and row_number > max_row:
                                return
                        continue
                    if name == "row":
                        element.clear()
                        continue
                    if name != "c":
                        continue
                    reference = element.get("r")
                    if reference:
                        row_number, column_number = split_reference(reference)
                    else:
                        column_number += 1
                    if ((columns is not None and column_number not in columns)
                            or (rows is not None and row_number not in rows)):
                        element.clear()
                        continue
                    kind, text = self._classify(element, numbers)
                    if kind == "number" and date_styles and element.get("s") is not None:
                        try:
                            if int(element.get("s")) in date_styles:
                                kind = "date"
                        except ValueError:
                            pass
                    element.clear()
                    if kind != "empty":
                        yield Cell(row_number, column_number, kind, text)
            except ET.ParseError as error:
                raise WorkbookError(f"Malformed XML in {sheet.path}: {error}") from error

    def _classify(self, element, numbers):
        cell_type = element.get("t")
        value = inline = None
        for child in element:
            name = _local(child.tag)
            if name == "v":
                value = child.text
            elif name == "is":
                inline = _text_of(child)
        if cell_type == "s":
            if value is None:
                return "empty", None
            try:
                text = self.shared_strings[int(value)]
            except (ValueError, IndexError) as error:
                raise WorkbookError(f"Shared-string index {value!r} is invalid") from error
            return ("text", text) if text.strip() else ("empty", None)
        if cell_type == "inlineStr":
            return ("text", inline) if inline and inline.strip() else ("empty", None)
        if cell_type == "str":
            return ("text", value) if value and value.strip() else ("empty", None)
        if cell_type == "b":
            return ("boolean", value) if value is not None else ("empty", None)
        if cell_type == "e":
            return ("error", value) if value is not None else ("empty", None)
        if cell_type == "d":
            return ("date", value) if value is not None else ("empty", None)
        if cell_type not in (None, "n"):
            raise WorkbookError(f"Unknown cell type {cell_type!r}")
        if value is None or not value.strip():
            return "empty", None
        return "number", (value if numbers else None)

    def merged_ranges(self, sheet: Sheet) -> tuple[tuple[int, int, int, int], ...]:
        """Merged ranges as (first row, first column, last row, last column); cell contents are skipped."""
        found = []
        with self._zip.open(sheet.path) as stream:
            try:
                for _, element in ET.iterparse(stream, events=("end",)):
                    name = _local(element.tag)
                    if name == "mergeCell":
                        first, _, last = (element.get("ref") or "").partition(":")
                        top, left = split_reference(first)
                        bottom, right = split_reference(last or first)
                        found.append((top, left, bottom, right))
                    if name in ("c", "row", "mergeCell"):
                        element.clear()
            except ET.ParseError as error:
                raise WorkbookError(f"Malformed XML in {sheet.path}: {error}") from error
        return tuple(found)

    def text_cell(self, sheet: Sheet, reference: str) -> str | None:
        """The text of one cell if it is a text cell; None if it is blank or not text (never a number)."""
        row, column = split_reference(reference)
        for cell in self.cells(sheet, max_row=row, columns={column}):
            if cell.row == row and cell.column == column:
                return cell.text if cell.kind == "text" else None
        return None

    # --------------------------------------------------------------------------------- notes

    def notes(self, sheet: Sheet) -> tuple[Note, ...]:
        """Legacy cell comments ('notes') and threaded comments attached to a sheet."""
        found = []
        for kind, target in self._read_relationships(sheet.path).values():
            if kind.endswith(COMMENTS):
                for element in self._xml(target).iter():
                    if _local(element.tag) == "comment":
                        body = next((child for child in element if _local(child.tag) == "text"), None)
                        text = _text_of(body) if body is not None else ""
                        found.append(Note(element.get("ref", ""), "comment", text))
            elif kind.endswith(THREADED_COMMENT):
                for element in self._xml(target).iter():
                    if _local(element.tag) == "threadedComment":
                        body = next((child for child in element if _local(child.tag) == "text"), None)
                        found.append(Note(element.get("ref", ""), "threaded comment",
                                          (body.text or "") if body is not None else ""))
        return tuple(sorted(found, key=lambda note: (_sort_key(note.ref), note.kind)))

    def document_properties(self) -> dict:
        """Text fields of docProps/core.xml (title, subject, description, keywords, ...)."""
        if "docProps/core.xml" not in self._names:
            return {}
        return {_local(element.tag): element.text.strip() for element in self._xml("docProps/core.xml")
                if element.text and element.text.strip()}


def _sort_key(reference):
    try:
        return split_reference(reference)
    except ValueError:
        return (0, 0)
