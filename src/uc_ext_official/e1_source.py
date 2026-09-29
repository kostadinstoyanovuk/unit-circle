"""E1 X.2: the Bank of England millennium workbook, acquired once and read by header first.

prereg/E1.md section 4 and Annex B X.2, as four recorded stages, each fail closed:

acquire    Gates: G4 for E1 and the passed official synthetic checks (audit/E1_X3.json). The file served
           at the registered URL at the first download after verified public registration is stored
           read-only with its source identity, retrieval time, size and SHA-256, and a DATA_MANIFEST row.
           Only an xlsx package is accepted as the download (an error or challenge page is not the file).
           The workbook itself is kept out of git (D-041): its path is git-ignored and only its record and
           the manifest row are committed; every later stage checks it against the committed record.
select     Reads text only. (1) Version: the file's own contents must identify it as version 3.1.
           (2) Header-only output: the sheet names, each sheet's title, and the text cells above the
           first data row of the headline-series sheet with the notes attached to it. No numeric cell
           is read or printed; the first data row is located by cell type. (3) The selection rule.
territory  The territory of each stretch of the selected column, from the workbook's own notes and
           headers: each stretch quotes its evidence, which is checked against the workbook's text.
extract    The first stage that reads values: the 317 levels 1700-2016 under the stop rules (through
           uc_ext.e1.annual_growth). Rows outside 1700-2016 are located by their year label and their
           values are never read. The manifest row is completed with the version statement, sheet,
           column letter, header, units and territory.

Readings of section 4 made here (each is a named constant, recorded with the selection):
- A version statement is 'version', 'ver', 'vers' or 'v' followed by a dotted number. Statements in the
  document properties, sheet names, sheet titles (first text cell) and the first (cover) sheet are the
  file's own identification; the file qualifies when they name 3.1 and no other version. Mentions
  elsewhere (for example other datasets' versions in source notes) are recorded, not decisive. The
  operator may instead name the one statement that identifies the file (--version-location), which is
  recorded as such, when the title-level text also lists other versions.
- The headline-series sheet is the one sheet whose name or title contains the word 'headline'. When more
  than one sheet qualifies the selection stops, as section 4 requires. A committed amendment record
  (audit/E1_AMENDMENT_1.json, with its text prereg/E1_amendment_1.md) may name one of those sheets; select
  then uses only that sheet and records the amendment with the selection.
- A real-GDP column is one with a header cell (own, or a merged heading over it) naming real GDP
  ('real' with 'GDP' or 'gross domestic product') without a transformation (per head, growth, deflator,
  per cent, change, contribution, share, ratio). With more than one, the tie-break keeps those whose
  header or notes describe them as UK, United Kingdom or geographically consistent.
"""
from __future__ import annotations

from collections import defaultdict
import math
import os
from pathlib import Path
import re
import stat
import subprocess

import numpy as np

from . import gates, records
from .workbook import Workbook, WorkbookError, column_index, column_letter

FILE_URL = ("https://www.bankofengland.co.uk/-/media/boe/files/statistics/research-datasets/"
            "a-millennium-of-macroeconomic-data-for-the-uk.xlsx")
LANDING_URL = "https://www.bankofengland.co.uk/statistics/research-datasets"
SOURCE_TITLE = "Bank of England, A millennium of macroeconomic data for the UK"
REQUIRED_VERSION = "3.1"
RAW_FILE = "data/raw/a-millennium-of-macroeconomic-data-for-the-uk.xlsx"
ACQUISITION_RECORD = "data/raw/E1_acquisition.json"
SOURCE_DIR = "audit/e1_source"
HEADER_TEXT = f"{SOURCE_DIR}/header-only.txt"
HEADER_JSON = f"{SOURCE_DIR}/header-only.json"
SELECTION_RECORD = f"{SOURCE_DIR}/selection.json"
ATTEMPTS_LOG = f"{SOURCE_DIR}/selection-attempts.jsonl"
TERRITORY_RECORD = f"{SOURCE_DIR}/territory.json"
EXTRACTION_RECORD = f"{SOURCE_DIR}/extraction.json"
EXTRACTION_STOP = f"{SOURCE_DIR}/extraction-stop.json"
AMENDMENT_RECORD = "audit/E1_AMENDMENT_1.json"
AMENDMENT_TEXT = "prereg/E1_amendment_1.md"
FIRST_YEAR, LAST_YEAR = 1700, 2016
NOT_STATED = "not stated in the workbook"
# The manifest note that marks a row whose file is kept out of git (tools/check_data.py uses the same words).
NOT_DISTRIBUTED = "Not distributed in this repository"

VERSION = re.compile(r"(?<![A-Za-z0-9])(?:version|vers|ver|v)\.?[\s:]*(\d+(?:\.\d+)+)", re.IGNORECASE)
HEADLINE = re.compile(r"\bheadline\b", re.IGNORECASE)
REAL = re.compile(r"\breal\b", re.IGNORECASE)
GDP = re.compile(r"\bGDP\b|gross\s+domestic\s+product", re.IGNORECASE)
TRANSFORMATION = re.compile(r"per\s+(?:head|capita|person|worker|hour|employee)|\bgrowth\b|\bdeflator\b|%|"
                            r"\bper\s*cent|\bpercentage\b|\bchange\b|\bcontributions?\b|\bshares?\b|\bratios?\b",
                            re.IGNORECASE)
UK_OR_CONSISTENT = re.compile(r"\bUK\b|United\s+Kingdom|geographically[\s-]+consistent", re.IGNORECASE)
UNITS_LABEL = re.compile(r"\bunits?\b", re.IGNORECASE)
YEAR_TEXT = re.compile(r"^\s*(\d{3,4})\s*$")
READINGS = dict(version=VERSION.pattern, headline=HEADLINE.pattern, real=REAL.pattern, gdp=GDP.pattern,
                transformation=TRANSFORMATION.pattern, uk_or_consistent=UK_OR_CONSISTENT.pattern,
                units_label=UNITS_LABEL.pattern,
                first_data_row="the first row whose leftmost non-blank cell is numeric (by cell type)",
                year_column="the column of that cell")


class SourceStop(RuntimeError):
    """Stop and document an amendment (prereg/E1.md section 4); `details` hold text-only evidence."""

    def __init__(self, message, *, stage, details=None):
        super().__init__(message)
        self.stage = stage
        self.details = details or {}


# ------------------------------------------------------------------------ version (text only)

def version_statements(workbook: Workbook) -> list[dict]:
    """Every version statement in the workbook's text, with its location and level ('title' or 'other')."""
    found = []

    def scan(location, level, text):
        for match in VERSION.finditer(text or ""):
            found.append(dict(location=location, level=level, text=" ".join(text.split()),
                              version=match.group(1)))

    for field, text in sorted(workbook.document_properties().items()):
        scan(f"docProps/core.xml:{field}", "title", text)
    for sheet in workbook.sheets:
        scan(f"sheet name: {sheet.name}", "title", sheet.name)
        first = True
        for cell in workbook.cells(sheet):
            if cell.kind != "text":
                continue
            scan(f"{sheet.name}!{cell.ref}", "title" if first or sheet.index == 0 else "other", cell.text)
            first = False
        for note in workbook.notes(sheet):
            scan(f"{sheet.name}!{note.ref} ({note.kind})", "other", note.text)
    return found


def check_version(statements: list[dict], designated: str | None = None) -> dict:
    """The version statement that identifies the file as 3.1, or SourceStop."""
    own = [s for s in statements if s["level"] == "title"]
    others = [s for s in statements if s["version"] != REQUIRED_VERSION]
    evidence = dict(title_level=own, all_statements=statements)
    if designated is not None:
        at = [s for s in statements if s["location"] == designated]
        chosen = [s for s in at if s["version"] == REQUIRED_VERSION]
        if not chosen:
            raise SourceStop(f"The statement at {designated!r} does not identify version {REQUIRED_VERSION}"
                             if at else f"No version statement at {designated!r}", stage="version", details=evidence)
        return dict(statement=chosen[0], designated_by_operator=True, other_versions=others, **evidence)
    matching = [s for s in own if s["version"] == REQUIRED_VERSION]
    conflicting = [s for s in own if s["version"] != REQUIRED_VERSION]
    if not matching:
        raise SourceStop(f"The workbook's properties, sheet names, titles and cover do not identify it as "
                         f"version {REQUIRED_VERSION}; stop before reading any value and document an amendment",
                         stage="version", details=evidence)
    if conflicting:
        listed = "; ".join(f"{s['location']}: {s['text']!r}" for s in conflicting)
        raise SourceStop(f"The workbook's own identification also names another version ({listed}). Read the "
                         "statements; if one of them identifies this file as version 3.1, name it with "
                         "--version-location, otherwise document an amendment", stage="version", details=evidence)
    return dict(statement=matching[0], designated_by_operator=False, other_versions=others, **evidence)


# ------------------------------------------------------------------- header-only (text only)

def sheet_layout(workbook: Workbook, sheet, *, first_data_row=None, year_column=None) -> dict:
    """Title, first data row, year column and the text cells above the first data row of one sheet.

    Located by cell type only: the first data row is the first row whose leftmost non-blank cell is
    numeric, and the year column is that cell's column, unless the operator supplies either.
    """
    header, data_row, data_column, previous = [], None, None, None
    for cell in workbook.cells(sheet):
        leftmost = cell.row != previous
        previous = cell.row
        if first_data_row is not None:
            if cell.row >= first_data_row:
                if cell.row == first_data_row and leftmost and cell.kind == "number":
                    data_row, data_column = cell.row, cell.column
                elif cell.row == first_data_row and leftmost:
                    data_row = cell.row
                break
        elif leftmost and cell.kind == "number":
            data_row, data_column = cell.row, cell.column
            break
        if cell.kind == "text":
            header.append(dict(ref=cell.ref, row=cell.row, column=cell.column, text=cell.text))
    if year_column is not None:
        data_column = column_index(year_column)
    return dict(sheet=sheet.name, index=sheet.index, state=sheet.state,
                title=header[0] if header else None, first_data_row=data_row,
                year_column=column_letter(data_column) if data_column else None,
                layout_source="operator" if first_data_row is not None or year_column is not None else "cell types",
                header=header)


def real_gdp_label(text: str) -> bool:
    return bool(REAL.search(text) and GDP.search(text) and not TRANSFORMATION.search(text))


def _column_headers(layout, merged):
    """Header text per column: its own text cells, plus merged headings that span it."""
    by_column = defaultdict(list)
    for cell in layout["header"]:
        by_column[cell["column"]].append(dict(ref=cell["ref"], text=cell["text"], inherited=False))
    origins = {(cell["row"], cell["column"]): cell for cell in layout["header"]}
    for top, left, bottom, right in merged:
        origin = origins.get((top, left))
        if origin is None:
            continue
        for column in range(left + 1, right + 1):
            by_column[column].append(dict(ref=origin["ref"], text=origin["text"], inherited=True))
    return {column: sorted(cells, key=lambda c: (int(re.sub(r"[A-Z]", "", c["ref"])), c["inherited"]))
            for column, cells in by_column.items()}


def header_only(workbook: Workbook, *, first_data_row=None, year_column=None, headline_sheet=None) -> dict:
    """The header-only output and the selection rule's result. SourceStop carries the output so far.

    headline_sheet is the sheet a committed amendment names when more than one sheet identifies itself as the
    headline series (prereg/E1.md section 4); it must be one of those sheets.
    """
    layouts = [sheet_layout(workbook, sheet) for sheet in workbook.sheets]
    output = dict(sheets=[dict(index=l["index"], name=l["sheet"], state=l["state"], title=l["title"])
                          for l in layouts], readings=READINGS)
    matches = []
    for layout in layouts:
        by = [label for label, text in (("name", layout["sheet"]),
                                        ("title", (layout["title"] or {}).get("text", ""))) if HEADLINE.search(text)]
        if by:
            matches.append((layout, by))
    output["headline_candidates"] = [dict(sheet=l["sheet"], matched_by=by) for l, by in matches]
    if headline_sheet is not None:
        named = [(l, by) for l, by in matches if l["sheet"] == headline_sheet]
        if len(named) != 1:
            raise SourceStop(f"The amendment names {headline_sheet!r}, which is not one of the {len(matches)} sheets "
                             "identifying themselves as the headline series", stage="selection", details=output)
        output["headline_named_by_amendment"] = headline_sheet
        matches = named
    if len(matches) != 1:
        raise SourceStop(f"{len(matches)} sheets have a name or title identifying them as the headline series; "
                         "exactly one is required", stage="selection", details=output)
    layout, matched_by = matches[0]
    sheet = workbook.sheet(layout["sheet"])
    if first_data_row is not None or year_column is not None:
        layout = sheet_layout(workbook, sheet, first_data_row=first_data_row, year_column=year_column)
    output.update(headline_sheet=layout["sheet"], headline_matched_by=matched_by,
                  first_data_row=layout["first_data_row"], year_column=layout["year_column"],
                  layout_source=layout["layout_source"], header_cells=layout["header"],
                  notes=[note._asdict() for note in workbook.notes(sheet)])
    if layout["first_data_row"] is None or layout["year_column"] is None:
        raise SourceStop("No data row located on the headline-series sheet (no row starts with a numeric cell)",
                         stage="layout", details=output)
    merged = [m for m in workbook.merged_ranges(sheet) if m[0] < layout["first_data_row"]]
    output["merged_header_ranges"] = [f"{column_letter(l)}{t}:{column_letter(r)}{b}" for t, l, b, r in merged]
    headers = _column_headers(layout, merged)
    year = column_index(layout["year_column"])
    notes_by_column = defaultdict(list)
    for note in output["notes"]:
        try:
            notes_by_column[column_index(re.sub(r"\d", "", note["ref"]))].append(note["text"])
        except ValueError:
            continue
    columns = []
    for column in sorted(headers):
        if column == year:
            continue
        cells = headers[column]
        labels = [c for c in cells if real_gdp_label(c["text"])]
        described = [c["text"] for c in cells if UK_OR_CONSISTENT.search(c["text"])] + [
            text for text in notes_by_column[column] if UK_OR_CONSISTENT.search(text)]
        columns.append(dict(column=column_letter(column), header=cells, real_gdp_labels=[c["ref"] for c in labels],
                            uk_or_consistent=described))
    candidates = [c for c in columns if c["real_gdp_labels"]]
    output["real_gdp_columns"] = candidates
    if not candidates:
        raise SourceStop("No column of the headline-series sheet is labelled as real GDP", stage="selection",
                         details=output)
    step = 1
    if len(candidates) > 1:
        step = 2
        candidates = [c for c in candidates if c["uk_or_consistent"]]
        if len(candidates) != 1:
            raise SourceStop(f"{len(output['real_gdp_columns'])} real-GDP columns, and {len(candidates)} of them "
                             "are described as the UK or geographically consistent estimate; exactly one is "
                             "required", stage="selection", details=output)
    chosen = candidates[0]
    label = next(c["text"] for c in chosen["header"] if c["ref"] in chosen["real_gdp_labels"])
    unit_rows = {cell["row"] for cell in layout["header"]
                 if cell["column"] == year and UNITS_LABEL.search(cell["text"])}
    units = [c["text"] for c in chosen["header"] if int(re.sub(r"[A-Z]", "", c["ref"])) in unit_rows]
    output["selection"] = dict(sheet=layout["sheet"], sheet_index=layout["index"], column=chosen["column"],
                               year_column=layout["year_column"], first_data_row=layout["first_data_row"],
                               layout_source=layout["layout_source"], label=label,
                               header=" | ".join(c["text"] for c in chosen["header"]), header_cells=chosen["header"],
                               units=" | ".join(units) if units else None,
                               rule_step=step, rule=("the only real-GDP column" if step == 1 else
                                                     "the only real-GDP column described as the UK or "
                                                     "geographically consistent estimate"))
    return output


def format_header_only(output: dict, version: dict | None, raw_sha256: str) -> str:
    """The printable header-only record: text cells only; no numeric cell appears."""
    lines = ["E1 header-only output (prereg/E1.md section 4). Text cells only: no numeric cell is read or printed.",
             f"Workbook SHA-256: {raw_sha256}", ""]
    if version:
        statement = version["statement"]
        lines += [f"Version statement ({statement['location']}): {statement['text']}"
                  + (" [named by the operator]" if version["designated_by_operator"] else ""), ""]
    lines.append(f"Sheets ({len(output['sheets'])}):")
    for sheet in output["sheets"]:
        title = sheet["title"]["text"] if sheet["title"] else ""
        lines.append(f"  {sheet['index'] + 1}. {sheet['name']!r} [{sheet['state']}] title: {title!r}")
    if "headline_sheet" in output:
        named = f"; named by the amendment in {AMENDMENT_RECORD}" if output.get("headline_named_by_amendment") else ""
        lines += ["", f"Headline-series sheet: {output['headline_sheet']!r} (matched by "
                      f"{', '.join(output['headline_matched_by'])}{named})",
                  f"First data row: {output['first_data_row']}; year column: {output['year_column']} "
                  f"(located by {output['layout_source']})", "", "Text cells above the first data row:"]
        lines += [f"  {cell['ref']}: {cell['text']}" for cell in output["header_cells"]]
        if output.get("merged_header_ranges"):
            lines.append(f"Merged header ranges: {', '.join(output['merged_header_ranges'])}")
        lines += ["", "Notes attached to the sheet:"]
        lines += [f"  {note['ref']} ({note['kind']}): {note['text']}" for note in output["notes"]] or ["  none"]
    if "real_gdp_columns" in output:
        lines += ["", "Columns labelled as real GDP:"]
        for column in output["real_gdp_columns"]:
            lines.append(f"  {column['column']}: {' | '.join(c['text'] for c in column['header'])}"
                         + ("  [described as UK or geographically consistent]" if column["uk_or_consistent"] else ""))
    if "selection" in output:
        selection = output["selection"]
        lines += ["", f"Selected: sheet {selection['sheet']!r}, column {selection['column']} ({selection['rule']})",
                  f"  header: {selection['header']}", f"  units: {selection['units'] or 'not stated in the header'}"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------- extraction (values)

def _year(cell):
    if cell.kind == "number":
        try:
            number = float(cell.text)
        except (TypeError, ValueError):
            raise SourceStop(f"Year cell {cell.ref} cannot be read as a number", stage="sample") from None
        if not math.isfinite(number) or number != int(number):
            raise SourceStop(f"Year cell {cell.ref} is not a whole year, so the years cannot be identified "
                             "unambiguously", stage="sample")
        return int(number)
    if cell.kind == "text":
        match = YEAR_TEXT.match(cell.text)
        return int(match.group(1)) if match else None
    return None


def extract_levels(workbook: Workbook, selection: dict):
    """The 317 levels 1700-2016 of the selected column under the section 4 stop rules.

    Returns (years, levels, growth_years, growth, details). Raises SourceStop without printing a value.
    """
    from uc_ext import e1
    sheet = workbook.sheet(selection["sheet"])
    year_column, value_column = column_index(selection["year_column"]), column_index(selection["column"])
    first = selection["first_data_row"]
    years, ambiguous = {}, {}
    for cell in workbook.cells(sheet, numbers=True, columns={year_column}):
        if cell.row >= first:
            try:
                year = _year(cell)
            except SourceStop as stop:
                ambiguous[cell.row] = str(stop)
                continue
            if year is not None:
                years[cell.row] = year
    sample_rows = {row: year for row, year in years.items() if FIRST_YEAR <= year <= LAST_YEAR}
    inside = [reason for row, reason in sorted(ambiguous.items())
              if sample_rows and min(sample_rows) < row < max(sample_rows)]
    if inside:
        raise SourceStop(inside[0], stage="sample", details=dict(ambiguous_year_cells_in_sample=len(inside)))
    values = {}
    for cell in workbook.cells(sheet, numbers=True, columns={value_column}, rows=set(sample_rows)):
        if cell.kind == "number":
            try:
                values[cell.row] = float(cell.text)
            except (TypeError, ValueError):
                values[cell.row] = cell.text
        else:
            values[cell.row] = cell.text if cell.text is not None else cell.kind
    ordered = sorted(sample_rows)
    try:
        growth_years, growth = e1.annual_growth([sample_rows[row] for row in ordered],
                                                [values.get(row) for row in ordered])
    except ValueError as error:
        raise SourceStop(f"Sample stop rule: {error}", stage="sample",
                         details=dict(rows_with_years=len(years), rows_in_sample=len(sample_rows))) from None
    levels = np.asarray([values[row] for row in ordered], dtype=float)
    details = dict(first_row=ordered[0], last_row=ordered[-1], rows_with_years=len(years),
                   rows_in_sample=len(sample_rows), ambiguous_year_cells_outside_sample=len(ambiguous),
                   levels=len(levels), growth=len(growth),
                   levels_sha256=gates.sha256_bytes(levels.astype("<f8").tobytes()),
                   growth_sha256=gates.sha256_bytes(np.asarray(growth, dtype=float).astype("<f8").tobytes()))
    return tuple(range(FIRST_YEAR, LAST_YEAR + 1)), levels, tuple(growth_years), growth, details


# --------------------------------------------------------------------------------- territory

def _normalised(text):
    return " ".join((text or "").split())


def evidence_text(workbook: Workbook, location: str) -> str | None:
    """Text at 'Sheet!B5', 'Sheet!B5 (note)' or 'docProps/core.xml:field'; None if there is none."""
    if location.startswith("docProps/core.xml:"):
        return workbook.document_properties().get(location.split(":", 1)[1])
    sheet_name, _, reference = location.rpartition("!")
    note = reference.endswith(" (note)")
    reference = reference.removesuffix(" (note)")
    try:
        sheet = workbook.sheet(sheet_name)
    except WorkbookError:
        return None
    if note:
        texts = [n.text for n in workbook.notes(sheet) if n.ref == reference]
        return "\n".join(texts) if texts else None
    try:
        return workbook.text_cell(sheet, reference)
    except ValueError:
        return None


def validate_territory(workbook: Workbook, spec: dict) -> list[dict]:
    """Stretches covering 1700-2016 contiguously, each with its territory quoted from the workbook."""
    stretches = spec.get("stretches") if isinstance(spec, dict) else None
    if not isinstance(stretches, list) or not stretches:
        raise ValueError("The territory record needs a non-empty list 'stretches'")
    expected, checked = FIRST_YEAR, []
    for number, stretch in enumerate(stretches):
        first, last = stretch.get("first_year"), stretch.get("last_year")
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (first, last)):
            raise ValueError(f"Stretch {number}: years must be integers")
        if first != expected or last < first or last > LAST_YEAR:
            raise ValueError(f"Stretch {number}: stretches must cover {FIRST_YEAR}-{LAST_YEAR} contiguously "
                             f"(expected a stretch starting in {expected})")
        territory = stretch.get("territory")
        if not isinstance(territory, str) or not territory.strip():
            raise ValueError(f"Stretch {number}: the territory must be named (or '{NOT_STATED}')")
        evidence = stretch.get("evidence") or []
        if territory != NOT_STATED and not evidence:
            raise ValueError(f"Stretch {number}: quote the workbook text that states the territory")
        verified = []
        for item in evidence:
            location, quote = item.get("location"), item.get("quote")
            if not isinstance(location, str) or not isinstance(quote, str) or not quote.strip():
                raise ValueError(f"Stretch {number}: evidence needs a location and a quote")
            found = evidence_text(workbook, location)
            if found is None or _normalised(quote) not in _normalised(found):
                raise ValueError(f"Stretch {number}: the quote is not in the workbook text at {location!r}")
            verified.append(dict(location=location, quote=quote))
        checked.append(dict(first_year=first, last_year=last, territory=territory.strip(), evidence=verified))
        expected = last + 1
    if expected != LAST_YEAR + 1:
        raise ValueError(f"The stretches end in {expected - 1}, not {LAST_YEAR}")
    return checked


def stretches_for_flags(territory: dict) -> list[tuple]:
    """(first level year, last level year, territory) for uc_ext.e1.territory_flags."""
    return [(s["first_year"], s["last_year"], s["territory"]) for s in territory["stretches"]]


# ------------------------------------------------------------------------ records and stages

def _raw(root, acquisition=None):
    """The workbook's bytes. The file is kept out of git (D-041): it must be present on this machine, must not be
    tracked, and must equal the committed acquisition record."""
    root = Path(root)
    acquisition = acquisition or load_acquisition(root)
    path = root / acquisition["file"]
    if not path.is_file():
        raise gates.GateClosed(f"{acquisition['file']} is missing. The workbook is kept out of git (D-041): restore "
                               f"the file with SHA-256 {acquisition['sha256']} from {acquisition['source_url']}")
    gates.check_untracked(root, acquisition["file"])
    content = path.read_bytes()
    if gates.sha256_bytes(content) != acquisition["sha256"] or len(content) != acquisition["bytes"]:
        raise SourceStop("The raw workbook's bytes differ from its acquisition record", stage="identity")
    return content


def load_acquisition(root) -> dict:
    path = Path(root) / ACQUISITION_RECORD
    if not path.is_file():
        raise gates.GateClosed("No E1 acquisition record: the workbook has not been acquired")
    return records.read_json(path)


def response_is_workbook(content: bytes) -> Workbook:
    try:
        return Workbook(content)
    except WorkbookError as error:
        raise SourceStop(f"The download is not an xlsx workbook ({error}); it is not the registered file and "
                         "nothing was recorded", stage="identity") from None


def acquire(root, content: bytes, *, retrieved_utc: str, method: str, response: dict | None,
            licence: str, licence_url: str) -> dict:
    """Store the first download after verified public registration, read-only, with its records."""
    root = Path(root)
    gate = gates.check_registration(root, "e1")
    x3 = gates.check_x3(root, "e1")
    raw, record_path = root / RAW_FILE, root / ACQUISITION_RECORD
    if raw.exists() or record_path.exists() or records.manifest_row(root, RAW_FILE) is not None:
        raise records.RecordExists("An E1 workbook, acquisition record or manifest row already exists; "
                                   "the workbook is acquired once")
    if subprocess.run(["git", "check-ignore", "-q", ACQUISITION_RECORD], cwd=root).returncode == 0:
        raise gates.GateClosed(f"{ACQUISITION_RECORD} would be ignored by git; add its .gitignore exception "
                               "first so the record can be committed")
    if subprocess.run(["git", "check-ignore", "-q", RAW_FILE], cwd=root).returncode != 0:
        raise gates.GateClosed(f"{RAW_FILE} would not be ignored by git; the workbook is kept out of the "
                               "repository (D-041), so its path must be git-ignored before it is written")
    retrieved = gates.utc(retrieved_utc)
    if not retrieved > gates.utc(gate["public_first_verified_at_utc"]):
        raise gates.GateClosed("The retrieval is not after the verified public registration of E1 "
                               f"({gate['public_first_verified_at_utc']}); section 4 uses the first download after it")
    if not licence or not licence_url:
        raise ValueError("State the licence and the page it is taken from")
    response_is_workbook(content)
    raw.parent.mkdir(parents=True, exist_ok=True)
    with raw.open("xb") as output:
        output.write(content)
    os.chmod(raw, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    record = dict(record_type="E1 source acquisition (prereg/E1.md section 4; Annex B, X.2)",
                  file=RAW_FILE, source=SOURCE_TITLE, source_url=FILE_URL, landing_url=LANDING_URL,
                  retrieval_method=method, retrieved_utc=retrieved.isoformat(), http=response,
                  bytes=len(content), sha256=gates.sha256_bytes(content), licence=licence, licence_url=licence_url,
                  read_only=True, repository_copy=f"{NOT_DISTRIBUTED} (git-ignored, D-041); the SHA-256 identifies it",
                  release_rule="the file served at the registered URL at the first download after "
                  "verified public registration; qualifies only if its own contents identify version 3.1",
                  registration=gate, x3_record_sha256=x3["record_sha256"], x3_code_sha256=x3["code_sha256"])
    records.write_once(record_path, records.pretty(record))
    records.append_manifest_row(root, dict(
        file=RAW_FILE, source_url=FILE_URL, series_id=f"{SOURCE_TITLE} (workbook)",
        retrieved_utc=record["retrieved_utc"], sha256=record["sha256"], licence=licence,
        notes=(f"{NOT_DISTRIBUTED}: obtain it from the source URL and check the SHA-256; landing page "
               f"{LANDING_URL}; {len(content)} bytes; record {ACQUISITION_RECORD}; E1 X.2: version statement, "
               f"selection and territory pending ({SOURCE_DIR}/)")))
    return record


def _attempt(root, entry):
    path = Path(root) / ATTEMPTS_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(records.canonical(entry).decode("ascii") + "\n")


def load_amendment(root) -> dict | None:
    """The amendment that names the headline-series sheet, or None when there is none.

    prereg/E1.md section 4 requires an amendment when the sheet rule does not give exactly one sheet. Its
    record (audit/E1_AMENDMENT_1.json) and its text (prereg/E1_amendment_1.md) must both be committed and
    unchanged, and the record must give the registration, the text's path and SHA-256, the amendment's
    address and the time it was first verified public. `select` uses the sheet it names.
    """
    root = Path(root)
    if not (root / AMENDMENT_RECORD).exists():
        return None
    for relative in (AMENDMENT_RECORD, AMENDMENT_TEXT):
        if not (root / relative).is_file():
            raise gates.GateClosed(f"{relative} is missing; the amendment record needs its text")
        gates.check_committed(root, relative)
    record = records.read_json(root / AMENDMENT_RECORD)
    registration = load_acquisition(root)["registration"]["registration_id"]
    if record.get("registration_id") != registration:
        raise gates.GateClosed(f"{AMENDMENT_RECORD} does not belong to the E1 registration ({registration})")
    if record.get("attachment") != AMENDMENT_TEXT or record.get("attachment_sha256") != gates.sha256_file(root / AMENDMENT_TEXT):
        raise gates.GateClosed(f"{AMENDMENT_TEXT} does not match the path and SHA-256 given in {AMENDMENT_RECORD}")
    sheet = record.get("headline_sheet")
    if not isinstance(sheet, str) or not sheet.strip():
        raise gates.GateClosed(f"{AMENDMENT_RECORD} does not name a sheet")
    for field in ("amendment_url", "public_first_verified_at_utc"):
        if not record.get(field):
            raise gates.GateClosed(f"{AMENDMENT_RECORD} has no {field}")
    gates.utc(record["public_first_verified_at_utc"])
    return dict(record, record_sha256=gates.sha256_file(root / AMENDMENT_RECORD))


def select(root, *, version_location=None, first_data_row=None, year_column=None) -> dict:
    """Version check, header-only output and the selection rule; every attempt is logged."""
    root = Path(root)
    acquisition = load_acquisition(root)
    if (root / SELECTION_RECORD).exists():
        raise records.RecordExists(f"{SELECTION_RECORD} already exists; the selection is made once")
    content = _raw(root, acquisition)
    amendment = load_amendment(root)
    options = dict(version_location=version_location, first_data_row=first_data_row, year_column=year_column,
                   amendment=None if amendment is None else dict(
                       record=AMENDMENT_RECORD, record_sha256=amendment["record_sha256"], text=AMENDMENT_TEXT,
                       text_sha256=amendment["attachment_sha256"], headline_sheet=amendment["headline_sheet"]))
    entry = dict(time_utc=gates.now_utc(), raw_sha256=acquisition["sha256"], options=options)
    version = None
    try:
        workbook = Workbook(content)
        version = check_version(version_statements(workbook), version_location)
        output = header_only(workbook, first_data_row=first_data_row, year_column=year_column,
                             headline_sheet=None if amendment is None else amendment["headline_sheet"])
    except SourceStop as stop:
        _attempt(root, dict(entry, status="stopped", stage=stop.stage, reason=str(stop), details=stop.details,
                            version=version))
        raise
    except (WorkbookError, ValueError) as error:
        _attempt(root, dict(entry, status="stopped", stage="read", reason=f"{type(error).__name__}: {error}"))
        raise SourceStop(f"The workbook could not be read: {error}", stage="read") from None
    text = format_header_only(output, version, acquisition["sha256"])
    selection = dict(record_type="E1 series selection by header only (prereg/E1.md section 4; D-023 E1-6)",
                     raw_sha256=acquisition["sha256"], version=dict(statement=version["statement"],
                     designated_by_operator=version["designated_by_operator"],
                     other_versions=version["other_versions"]), options=options, readings=READINGS,
                     **output["selection"], selected_utc=entry["time_utc"])
    records.write_once(root / HEADER_TEXT, text.encode("utf-8"))
    records.write_once(root / HEADER_JSON, records.pretty(dict(output, version=version)))
    records.write_once(root / SELECTION_RECORD, records.pretty(selection))
    _attempt(root, dict(entry, status="selected", sheet=selection["sheet"], column=selection["column"]))
    return dict(selection=selection, text=text)


def load_selection(root) -> dict:
    path = Path(root) / SELECTION_RECORD
    if not path.is_file():
        raise gates.GateClosed("No E1 selection record: run the header-only selection first")
    return records.read_json(path)


def record_territory(root, spec: dict) -> dict:
    root = Path(root)
    acquisition = load_acquisition(root)
    selection = load_selection(root)
    if (root / TERRITORY_RECORD).exists():
        raise records.RecordExists(f"{TERRITORY_RECORD} already exists; it is written once")
    workbook = Workbook(_raw(root, acquisition))
    stretches = validate_territory(workbook, spec)
    record = dict(record_type="E1 territory of each stretch of the selected column (prereg/E1.md section 4)",
                  raw_sha256=acquisition["sha256"], selection_sha256=gates.sha256_file(root / SELECTION_RECORD),
                  sheet=selection["sheet"], column=selection["column"], stretches=stretches,
                  note=spec.get("note"), use=("Documentation only: the column is used as the workbook gives it, "
                                              "with no re-splicing, re-basing, interpolation or territorial "
                                              "adjustment"), recorded_utc=gates.now_utc())
    records.write_once(root / TERRITORY_RECORD, records.pretty(record))
    return record


def _manifest_notes(acquisition, selection, territory):
    statement = selection["version"]["statement"]
    stretches = "; ".join(f"{s['first_year']}-{s['last_year']} {s['territory']}" for s in territory["stretches"])
    return (f"{NOT_DISTRIBUTED}: obtain it from the source URL and check the SHA-256. Version statement "
            f"\"{statement['text']}\" ({statement['location']}); sheet '{selection['sheet']}', "
            f"column {selection['column']}, header \"{selection['header']}\"; units: "
            f"{selection['units'] or 'not stated in the header'}; territory: {stretches}; landing page "
            f"{LANDING_URL}; {acquisition['bytes']} bytes; records {ACQUISITION_RECORD} and {SOURCE_DIR}/")


def extract(root) -> dict:
    """The first reading of values: the 317 levels under the stop rules, recorded without printing them."""
    root = Path(root)
    gates.check_registration(root, "e1")
    x3 = gates.check_x3(root, "e1")
    acquisition = load_acquisition(root)
    for relative in (ACQUISITION_RECORD, SELECTION_RECORD, TERRITORY_RECORD):
        if not (root / relative).is_file():
            raise gates.GateClosed(f"{relative} is missing; acquire, select and record the territory first")
        gates.check_committed(root, relative)
    if (root / EXTRACTION_RECORD).exists() or (root / EXTRACTION_STOP).exists():
        raise records.RecordExists("The E1 levels have already been extracted (or stopped); extraction happens once")
    selection, territory = load_selection(root), records.read_json(root / TERRITORY_RECORD)
    workbook = Workbook(_raw(root, acquisition))
    base = dict(raw_sha256=acquisition["sha256"], selection_sha256=gates.sha256_file(root / SELECTION_RECORD),
                territory_sha256=gates.sha256_file(root / TERRITORY_RECORD), x3_record_sha256=x3["record_sha256"])
    try:
        _, _, growth_years, _, details = extract_levels(workbook, selection)
    except SourceStop as stop:
        records.write_once(root / EXTRACTION_STOP, records.pretty(dict(
            record_type="E1 sample stop (prereg/E1.md section 4): stop and document an amendment",
            reason=str(stop), details=stop.details, stopped_utc=gates.now_utc(), **base)))
        raise
    record = dict(record_type="E1 levels extracted under the section 4 stop rules (Annex B, X.2)",
                  first_year=FIRST_YEAR, last_year=LAST_YEAR, first_growth_year=growth_years[0],
                  last_growth_year=growth_years[-1], sheet=selection["sheet"], column=selection["column"],
                  year_column=selection["year_column"], extracted_utc=gates.now_utc(), **details, **base)
    records.write_once(root / EXTRACTION_RECORD, records.pretty(record))
    records.replace_manifest_row(root, RAW_FILE, acquisition["sha256"],
                                 series_id=(f"{SOURCE_TITLE}: '{selection['sheet']}' column {selection['column']} "
                                            "(E1 headline annual real GDP)"),
                                 notes=_manifest_notes(acquisition, selection, territory))
    return record


def load_registered_growth(root) -> dict:
    """For the one-shot run: every X.2 record present and committed, the raw bytes and the re-extracted
    levels identical to the extraction record. Returns records, record hashes, years and growth."""
    root = Path(root)
    acquisition = load_acquisition(root)
    for relative in (ACQUISITION_RECORD, SELECTION_RECORD, TERRITORY_RECORD, EXTRACTION_RECORD):
        if not (root / relative).is_file():
            raise gates.GateClosed(f"{relative} is missing; E1 X.2 is not complete")
        gates.check_committed(root, relative)
    selection = load_selection(root)
    territory = records.read_json(root / TERRITORY_RECORD)
    extraction = records.read_json(root / EXTRACTION_RECORD)
    _, levels, growth_years, growth, details = extract_levels(Workbook(_raw(root, acquisition)), selection)
    if (details["levels_sha256"], details["growth_sha256"]) != (extraction["levels_sha256"],
                                                                extraction["growth_sha256"]):
        raise SourceStop("The re-extracted levels differ from the extraction record", stage="identity")
    hashes = {relative: gates.sha256_file(root / relative)
              for relative in (ACQUISITION_RECORD, SELECTION_RECORD, TERRITORY_RECORD, EXTRACTION_RECORD)}
    used = (selection.get("options") or {}).get("amendment")
    if used:
        amendment = load_amendment(root)
        if (amendment is None or amendment["record_sha256"] != used["record_sha256"]
                or amendment["attachment_sha256"] != used["text_sha256"]):
            raise gates.GateClosed(f"The selection relied on {AMENDMENT_RECORD}, which is missing or differs from "
                                   "the record the selection cites")
        hashes.update({AMENDMENT_RECORD: amendment["record_sha256"], AMENDMENT_TEXT: amendment["attachment_sha256"]})
    return dict(acquisition=acquisition, selection=selection, territory=territory, extraction=extraction,
                record_sha256=hashes, growth_years=growth_years, growth=growth, levels_count=len(levels))
