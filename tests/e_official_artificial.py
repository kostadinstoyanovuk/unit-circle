"""Artificial fixtures only: xlsx workbooks in the layout the E1 selection rule expects, ONS-format
files, and a throwaway integrated research root. Every value comes from a recorded development seed;
every workbook and file says it is artificial. No Bank of England or ONS data are used or imitated.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

import numpy as np

# Once integrated, the research root holds uc_core, uc_ext, uc_ext_official and the tools. Before that,
# UC_RESEARCH_ROOT names a research checkout and UC_E_PIPELINES the E-pipelines delivery directory.
PACKAGE = Path(__file__).resolve().parents[1]
if (PACKAGE / "src/uc_core/__init__.py").is_file():
    RESEARCH = PIPELINES = PACKAGE
else:
    try:
        RESEARCH, PIPELINES = Path(os.environ["UC_RESEARCH_ROOT"]), Path(os.environ["UC_E_PIPELINES"])
    except KeyError as error:
        raise RuntimeError("Set UC_RESEARCH_ROOT (research checkout) and UC_E_PIPELINES (E-pipelines delivery "
                           "with src/uc_ext and tools/run_e_checks.py)") from error
TOOLS = ("record_e_x3.py", "acquire_e1.py", "note_e3_data.py", "run_e1.py", "run_e3.py", "freeze_e.py")
GITIGNORE_ADDITIONS = ("!data/raw/a-millennium-of-macroeconomic-data-for-the-uk.xlsx", "!data/raw/E1_acquisition.json")

SEED = 20260929                       # development seed for artificial fixtures (not a registered seed)
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
LABEL = "ARTIFICIAL TEST WORKBOOK - generated for software tests; not Bank of England data"


def letter(index):
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


class XlsxWriter:
    """A minimal xlsx writer: shared or inline strings, numbers, notes, merged cells, core title."""

    def __init__(self, *, inline_strings=False, title=None):
        self.sheets, self.inline, self.title, self.strings = [], inline_strings, title, []

    def sheet(self, name, rows, *, merged=(), notes=(), raw_cells=()):
        """rows: {row number: {column number: value}}; a str is text, a number is numeric, None is blank.
        raw_cells: (row, column, xml) for hand-written cells (for example a boolean or an error)."""
        self.sheets.append(dict(name=name, rows=rows, merged=merged, notes=notes, raw=raw_cells))
        return self

    def _string(self, text):
        if text not in self.strings:
            self.strings.append(text)
        return self.strings.index(text)

    def _cell(self, reference, value):
        if isinstance(value, str):
            if self.inline:
                return f'<c r="{reference}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            return f'<c r="{reference}" t="s"><v>{self._string(value)}</v></c>'
        return f'<c r="{reference}"><v>{repr(float(value)) if isinstance(value, float) else value}</v></c>'

    def build(self) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
            sheet_xml, rels, comments = [], [], {}
            for number, sheet in enumerate(self.sheets, start=1):
                rows_xml = []
                raw = {}
                for row, column, xml in sheet["raw"]:
                    raw.setdefault(row, {})[column] = xml
                for row in sorted(set(sheet["rows"]) | set(raw)):
                    cells = dict(sheet["rows"].get(row, {}))
                    parts = []
                    for column in sorted(set(cells) | set(raw.get(row, {}))):
                        if column in raw.get(row, {}):
                            parts.append(raw[row][column].replace("{ref}", f"{letter(column)}{row}"))
                        elif cells[column] is not None:
                            parts.append(self._cell(f"{letter(column)}{row}", cells[column]))
                    rows_xml.append(f'<row r="{row}">{"".join(parts)}</row>')
                merged = "".join(f'<mergeCell ref="{m}"/>' for m in sheet["merged"])
                merged = f'<mergeCells count="{len(sheet["merged"])}">{merged}</mergeCells>' if merged else ""
                sheet_xml.append((number, f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{MAIN}">'
                                          f'<sheetData>{"".join(rows_xml)}</sheetData>{merged}</worksheet>'))
                if sheet["notes"]:
                    notes = "".join(f'<comment ref="{ref}" authorId="0"><text><r><t>{escape(text)}</t></r></text>'
                                    f'</comment>' for ref, text in sheet["notes"])
                    comments[number] = (f'<?xml version="1.0" encoding="UTF-8"?><comments xmlns="{MAIN}"><authors>'
                                        f'<author>test</author></authors><commentList>{notes}</commentList></comments>')
                rels.append(f'<Relationship Id="rId{number}" Type="{REL}/worksheet" '
                            f'Target="worksheets/sheet{number}.xml"/>')
            for number, xml in sheet_xml:
                package.writestr(f"xl/worksheets/sheet{number}.xml", xml)
            for number, xml in comments.items():
                package.writestr(f"xl/comments{number}.xml", xml)
                package.writestr(f"xl/worksheets/_rels/sheet{number}.xml.rels",
                                 f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PKG}">'
                                 f'<Relationship Id="rIdC" Type="{REL}/comments" Target="../comments{number}.xml"/>'
                                 f'</Relationships>')
            strings = "".join(f"<si><t>{escape(text)}</t></si>" for text in self.strings)
            package.writestr("xl/sharedStrings.xml", f'<?xml version="1.0" encoding="UTF-8"?><sst xmlns="{MAIN}" '
                                                     f'count="{len(self.strings)}">{strings}</sst>')
            rels.append(f'<Relationship Id="rIdS" Type="{REL}/sharedStrings" Target="sharedStrings.xml"/>')
            sheets = "".join(f'<sheet name="{escape(sheet["name"])}" sheetId="{number}" r:id="rId{number}"/>'
                             for number, sheet in enumerate(self.sheets, start=1))
            package.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{MAIN}" '
                                                f'xmlns:r="{REL}"><sheets>{sheets}</sheets></workbook>')
            package.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0" encoding="UTF-8"?><Relationships '
                                                           f'xmlns="{PKG}">{"".join(rels)}</Relationships>')
            core = ""
            if self.title:
                core = (f'<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
                        f'core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{escape(self.title)}'
                        f'</dc:title></cp:coreProperties>')
                package.writestr("docProps/core.xml", core)
            package.writestr("_rels/.rels", f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PKG}">'
                                            f'<Relationship Id="rId1" Type="{REL}/officeDocument" '
                                            f'Target="xl/workbook.xml"/></Relationships>')
            package.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns='
                                                    '"http://schemas.openxmlformats.org/package/2006/content-types">'
                                                    '<Default Extension="xml" ContentType="application/xml"/></Types>')
        return buffer.getvalue()


def artificial_levels(first_year=1600, last_year=2020, seed=SEED):
    """Positive artificial levels from an AR(2) in annual growth (development seed)."""
    rng = np.random.default_rng(seed)
    n = last_year - first_year + 1
    g = np.empty(n)
    g[:2] = 1.0
    for t in range(2, n):
        g[t] = 0.5 + 0.3 * g[t - 1] + 0.1 * g[t - 2] + rng.normal(0, 3.5)
    return dict(zip(range(first_year, last_year + 1), 100 * np.exp(np.cumsum(g / 100))))


HEADLINE = "A1 Headline series (artificial)"


def headline_rows(columns, *, years=None, first_data_row=6, units_row=True, value_overrides=None,
                  year_overrides=None, levels=None, descending=False, title=HEADLINE):
    """Header rows 1..first_data_row-1 and one data row per year.

    columns: list of (header text, units text or None, note row text or None, value function or None).
    value function(year, level) -> cell value; None leaves that column's data blank.
    """
    levels = levels or artificial_levels()
    years = list(years or levels)
    if descending:
        years = years[::-1]
    rows = {1: {1: f"{title} - {LABEL}"}, 2: {1: "Description"}, 3: {1: "Units"} if units_row else {1: "Scale"},
            4: {1: "Notes"}}
    for number, (header, units, note, _) in enumerate(columns, start=2):
        rows[2][number] = header
        if units is not None:
            rows[3][number] = units
        if note is not None:
            rows[4][number] = note
    value_overrides, year_overrides = value_overrides or {}, year_overrides or {}
    for offset, year in enumerate(years):
        row = first_data_row + offset
        rows[row] = {1: year_overrides.get(year, year)}
        for number, (_, _, _, function) in enumerate(columns, start=2):
            if function is not None:
                value = function(year, levels[year]) if year in levels else None
                rows[row][number] = value_overrides.get((year, number), value)
    return rows


def standard_columns():
    return [("Real GDP of England, artificial", "GBP mn, artificial prices", "England only (artificial)",
             lambda year, level: round(level * 0.8, 6)),
            ("Real GDP at market prices, UK, geographically consistent estimate (artificial)",
             "GBP mn, artificial prices", "Artificial territory: England to 1706, Great Britain 1707-1800, UK from 1801",
             lambda year, level: round(level, 6)),
            ("Real GDP per head (artificial)", "GBP, artificial prices", None, lambda year, level: round(level / 5, 6)),
            ("Nominal GDP (artificial)", "GBP mn", None, lambda year, level: round(level * 1.1, 6))]


def artificial_workbook(*, version_text="Version 3.1 (artificial test fixture)", extra_cover=(), columns=None,
                        headline_name=HEADLINE, second_headline=False, inline_strings=False, title=None,
                        merged=(), notes=(), **rows_options) -> bytes:
    writer = XlsxWriter(inline_strings=inline_strings, title=title)
    cover = {1: {1: LABEL}, 2: {1: version_text} if version_text else {1: "No version statement"}}
    for offset, text in enumerate(extra_cover, start=3):
        cover[offset] = {1: text}
    writer.sheet("Cover (artificial)", cover)
    writer.sheet("Notes (artificial)", {1: {1: "Notes (artificial)"},
                                         2: {1: "Source notes cite another artificial dataset, version 9.0."},
                                         3: {1: "Territory: England to 1706; Great Britain 1707-1800; UK from 1801."}})
    writer.sheet(headline_name, headline_rows(columns or standard_columns(), title=headline_name, **rows_options),
                 merged=merged,
                 notes=notes)
    if second_headline:
        writer.sheet("A2 Headline copy (artificial)", {1: {1: "Headline copy (artificial)"}})
    writer.sheet("A3. Other data (artificial)", {1: {1: "Other data (artificial)"}, 2: {1: 1700, 2: 1.5}})
    return writer.build()


TERRITORY = dict(stretches=[
    dict(first_year=1700, last_year=1706, territory="England",
         evidence=[dict(location=f"{HEADLINE}!C4", quote="England to 1706")]),
    dict(first_year=1707, last_year=1800, territory="Great Britain",
         evidence=[dict(location=f"{HEADLINE}!C4", quote="Great Britain 1707-1800")]),
    dict(first_year=1801, last_year=2016, territory="UK",
         evidence=[dict(location="Notes (artificial)!A3", quote="UK from 1801")])],
    note="Artificial territory record for software tests.")


# ------------------------------------------------------------------------ ONS-format (E3)

def artificial_ons_csv(seed=SEED, release_date="30-06-2026"):
    """An artificial file in the ONS time-series layout (as the research repository's H1 tests build)."""
    rng = np.random.default_rng(seed)
    quarters = [f"{year} Q{q}" for year in range(1948, 2022) for q in range(1, 5)]
    g = np.empty(len(quarters))
    g[:2] = 2.5
    for t in range(2, len(g)):
        g[t] = 1.5 + 0.3 * g[t - 1] + 0.1 * g[t - 2] + rng.normal(0, 3.5)
    levels = 100 * np.exp(np.cumsum(g / 400))
    rows = [["Title", "Gross Domestic Product: chained volume measures: Seasonally adjusted £m"], ["CDID", "ABMI"],
            ["Source dataset ID", "QNA"], ["PreUnit", "£"], ["Unit", "m"], ["Release date", release_date],
            ["Next release", "artificial"], ["Important notes", "ARTIFICIAL TEST FILE - not ONS data"]]
    rows += [[str(year), f"{levels[i * 4]:.0f}"] for i, year in enumerate(range(1948, 2022))]
    rows += [[label, f"{level:.0f}"] for label, level in zip(quarters, levels)]
    return ("\n".join(",".join(f'"{cell}"' for cell in row) for row in rows) + "\n").encode("utf-8")


# ------------------------------------------------------------ a throwaway integrated research root

def git(root, *args):
    return subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args], cwd=root,
                          check=True, capture_output=True, text=True).stdout.strip()


RESEARCH_FILES = ("prereg/E1.md", "prereg/E3.md", "prereg/H1.md", "prereg/E_SOURCE_METADATA.md", "requirements.lock",
                  "tools/run_validation.py", "tools/verify_validation_runner.py", "tools/check_data.py",
                  "pyproject.toml")


def integrated_root(tmp_path, research: Path = RESEARCH, pipelines: Path = PIPELINES, package: Path = PACKAGE, *,
                    extensions=("E1", "E3")):
    """A git repository shaped like the research root after integration, with an origin, published
    annotated prereg-E1/E3 tags and registration records naming them (copies of the real receipts with
    the tag commit replaced; clearly test-only). The ABMI file is an artificial ONS-format file."""
    origin, root = tmp_path / "origin.git", tmp_path / "research"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    root.mkdir()
    for relative in RESEARCH_FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(research / relative, root / relative)
    shutil.copytree(research / "src/uc_core", root / "src/uc_core", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(pipelines / "src/uc_ext", root / "src/uc_ext", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copyfile(pipelines / "tools/run_e_checks.py", root / "tools/run_e_checks.py")
    shutil.copytree(package / "src/uc_ext_official", root / "src/uc_ext_official",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for tool in TOOLS:
        shutil.copyfile(package / "tools" / tool, root / "tools" / tool)
    gitignore = (research / ".gitignore").read_text(encoding="utf-8").rstrip("\n").splitlines()
    missing = [line for line in GITIGNORE_ADDITIONS if line not in gitignore]
    (root / ".gitignore").write_text("\n".join([*gitignore, "# E1 X.2", *missing]) + "\n")
    (root / "audit").mkdir()
    (root / "figures").mkdir()
    (root / "data/raw").mkdir(parents=True)
    abmi = artificial_ons_csv()
    (root / "data/raw/ABMI_QNA.csv").write_bytes(abmi)
    acquisition = dict(file="data/raw/ABMI_QNA.csv", series_id="ABMI", dataset_id="QNA",
                       release_title="GDP quarterly national accounts, UK: artificial test release",
                       release_datetime_utc="2026-06-30T06:00:00+00:00",
                       release_url="https://www.ons.gov.uk/releases/artificialtestrelease",
                       file_url="https://example.invalid/artificial.csv", retrieved_utc="2026-09-28T22:20:50+00:00",
                       retrieval_method="artificial test fixture", bytes=len(abmi),
                       sha256=hashlib.sha256(abmi).hexdigest(), licence="artificial",
                       registration_timestamp_utc="2026-09-27T04:49:01.989076+00:00",
                       header_identity=dict(title="Gross Domestic Product: chained volume measures: Seasonally "
                                                  "adjusted £m", cdid="ABMI", dataset="QNA",
                                            release_date_record="30-06-2026"))
    (root / "data/raw/ABMI_acquisition.json").write_text(json.dumps(acquisition, indent=2) + "\n")
    with (root / "DATA_MANIFEST.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(["file", "source_url", "series_id", "retrieved_utc", "sha256", "licence", "notes"])
        writer.writerow(["data/raw/ABMI_QNA.csv", acquisition["file_url"], "ONS ABMI (QNA)",
                         acquisition["retrieved_utc"], acquisition["sha256"], "artificial",
                         "ARTIFICIAL test row; record data/raw/ABMI_acquisition.json"])
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "artificial integrated root for tests")
    for name in extensions:
        git(root, "tag", "-a", f"prereg-{name}", "-m", f"{name} registered addendum (test copy)")
    for name in extensions:
        receipt = json.loads((research / f"audit/{name}_REGISTRATION.json").read_text(encoding="utf-8"))
        commit = git(root, "rev-parse", f"prereg-{name}^{{commit}}")
        receipt.update(prereg_tag_commit=commit, source_commit=commit,
                       test_note="Test copy of the registration record with the tag commit replaced")
        (root / f"audit/{name}_REGISTRATION.json").write_text(json.dumps(receipt, indent=2) + "\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "registration records (test copies)")
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "-q", "origin", "HEAD:refs/heads/main", "--tags")
    return root


def x3_record(extension, code_sha256, *, D80=None, **changes):
    """An artificial X.3 record in the shape tools/record_e_x3.py writes (test-only)."""
    name = extension.upper()
    record = dict(record_type=f"{name} X.3 official synthetic checks (artificial test record)", extension=name,
                  X3="passed", size_passed=True, power_passed=True, mode="registered", master_seed=1927,
                  n_series=200, B=1000, kappas=[1.0, 1.2, 1.4, 1.6], D80=D80, code_sha256=code_sha256,
                  artificial="test fixture; not an official check")
    if extension == "e3":
        record["prerequisite_passed"] = True
    record.update(changes)
    return record


def commit_all(root, message="test step"):
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", message)
