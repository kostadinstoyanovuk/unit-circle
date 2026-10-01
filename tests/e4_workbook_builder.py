"""Constructed fixtures for the E4 X.2 tests: xlsx workbooks written with zipfile and hand-written XML from
arbitrary numbers (development seed), pages in the layout of the ONS dataset page, edition page and
release-calendar record with constructed content, and a throwaway research repository with a published
prereg-E4 tag. No ONS data is used or imitated; every workbook says it is a constructed test workbook.
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import shutil
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

import numpy as np

from e_official_artificial import x3_record

PACKAGE = Path(__file__).resolve().parents[1]
DEV_SEED, DEV_STREAM = 20260930, 9201        # development coordinates (not registered)
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
LABEL = "CONSTRUCTED TEST WORKBOOK - generated for software tests; not ONS data"
DATE_STYLE, CUSTOM_DATE_STYLE, NUMBER_STYLE = 1, 2, 3      # cellXfs indices written by `styles_xml`
E1_CODE = "e" * 64                           # the code identity of the constructed root's E1 X.3 record


class Date:
    """A numeric cell whose number format displays a date (style 1, built-in format 14, or 2, 'mmm-yy')."""

    def __init__(self, day: _dt.date, style=DATE_STYLE):
        self.day, self.style = day, style

    @property
    def serial(self):
        return (self.day - _dt.date(1899, 12, 30)).days


class Styled:
    """A numeric cell with an explicit style (for example style 3, a non-date custom format '0.0')."""

    def __init__(self, value, style=NUMBER_STYLE):
        self.value, self.style = value, style


class Raw:
    """A hand-written cell: `xml` with {ref} for the reference (a logical value, an error, a typed date)."""

    def __init__(self, xml):
        self.xml = xml


BOOLEAN = Raw('<c r="{ref}" t="b"><v>1</v></c>')
ERROR = Raw('<c r="{ref}" t="e"><v>#N/A</v></c>')


def iso_date_cell(text):
    return Raw(f'<c r="{{ref}}" t="d"><v>{text}</v></c>')


def letter(index):
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def styles_xml():
    return (f'<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="{MAIN}"><numFmts count="2">'
            '<numFmt numFmtId="164" formatCode="mmm\\-yy"/><numFmt numFmtId="165" formatCode="0.0"/></numFmts>'
            '<cellXfs count="4"><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/><xf numFmtId="165"/>'
            '</cellXfs></styleSheet>')


class Book:
    """Sheets of {(row, column): value}; str is a shared string, int/float a number, None blank."""

    def __init__(self, *, title=None, date1904=False):
        self.sheets, self.title, self.date1904, self.strings = [], title, date1904, []

    def sheet(self, name, cells, *, state="visible", merged=(), comments=()):
        self.sheets.append(dict(name=name, cells=cells, state=state, merged=merged, comments=comments))
        return self

    def _cell(self, ref, value):
        if isinstance(value, Raw):
            return value.xml.replace("{ref}", ref)
        if isinstance(value, Date):
            return f'<c r="{ref}" s="{value.style}"><v>{value.serial}</v></c>'
        if isinstance(value, Styled):
            return f'<c r="{ref}" s="{value.style}"><v>{value.value!r}</v></c>'
        if isinstance(value, str):
            if value not in self.strings:
                self.strings.append(value)
            return f'<c r="{ref}" t="s"><v>{self.strings.index(value)}</v></c>'
        return f'<c r="{ref}"><v>{value!r}</v></c>'

    def build(self) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
            rels = []
            for number, sheet in enumerate(self.sheets, start=1):
                rows = {}
                for (row, column), value in sheet["cells"].items():
                    if value is not None:
                        rows.setdefault(row, {})[column] = value
                body = "".join(f'<row r="{row}">' + "".join(self._cell(f"{letter(column)}{row}", rows[row][column])
                                                            for column in sorted(rows[row])) + "</row>"
                               for row in sorted(rows))
                merged = "".join(f'<mergeCell ref="{m}"/>' for m in sheet["merged"])
                merged = f'<mergeCells count="{len(sheet["merged"])}">{merged}</mergeCells>' if merged else ""
                package.writestr(f"xl/worksheets/sheet{number}.xml", f'<?xml version="1.0" encoding="UTF-8"?>'
                                 f'<worksheet xmlns="{MAIN}"><sheetData>{body}</sheetData>{merged}</worksheet>')
                if sheet["comments"]:
                    notes = "".join(f'<comment ref="{ref}" authorId="0"><text><r><t>{escape(text)}</t></r></text>'
                                    "</comment>" for ref, text in sheet["comments"])
                    package.writestr(f"xl/comments{number}.xml", f'<?xml version="1.0" encoding="UTF-8"?><comments '
                                     f'xmlns="{MAIN}"><authors><author>test</author></authors><commentList>{notes}'
                                     "</commentList></comments>")
                    package.writestr(f"xl/worksheets/_rels/sheet{number}.xml.rels", f'<?xml version="1.0" '
                                     f'encoding="UTF-8"?><Relationships xmlns="{PKG}"><Relationship Id="rIdC" '
                                     f'Type="{REL}/comments" Target="../comments{number}.xml"/></Relationships>')
                rels.append(f'<Relationship Id="rId{number}" Type="{REL}/worksheet" Target="worksheets/sheet{number}.xml"/>')
            strings = "".join(f"<si><t>{escape(text)}</t></si>" for text in self.strings)
            package.writestr("xl/sharedStrings.xml", f'<?xml version="1.0" encoding="UTF-8"?><sst xmlns="{MAIN}">'
                             f"{strings}</sst>")
            package.writestr("xl/styles.xml", styles_xml())
            rels += [f'<Relationship Id="rIdS" Type="{REL}/sharedStrings" Target="sharedStrings.xml"/>',
                     f'<Relationship Id="rIdY" Type="{REL}/styles" Target="styles.xml"/>']
            sheets = "".join(f'<sheet name="{escape(s["name"])}" sheetId="{n}" r:id="rId{n}"'
                             + (f' state="{s["state"]}"' if s["state"] != "visible" else "") + "/>"
                             for n, s in enumerate(self.sheets, start=1))
            pr = '<workbookPr date1904="1"/>' if self.date1904 else ""
            package.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{MAIN}" '
                             f'xmlns:r="{REL}">{pr}<sheets>{sheets}</sheets></workbook>')
            package.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0" encoding="UTF-8"?><Relationships '
                             f'xmlns="{PKG}">{"".join(rels)}</Relationships>')
            if self.title:
                package.writestr("docProps/core.xml", '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/'
                                 'package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                                 f"<dc:title>{escape(self.title)}</dc:title></cp:coreProperties>")
            package.writestr("_rels/.rels", f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{PKG}">'
                             f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="xl/workbook.xml"/>'
                             "</Relationships>")
            package.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://'
                             'schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" '
                             'ContentType="application/xml"/></Types>')
        return buffer.getvalue()


# ------------------------------------------------------------------------- vintage-by-quarter tables

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def month_labels(first=(2016, 1), n=6):
    year, month = first
    out = []
    for _ in range(n):
        out.append(f"{MONTHS[month - 1]} {year}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def quarter_labels(first=(1955, 1), n=24):
    year, quarter = first
    out = []
    for _ in range(n):
        out.append(f"{year} Q{quarter}")
        year, quarter = (year + 1, 1) if quarter == 4 else (year, quarter + 1)
    return out


def levels(n_rows, n_columns, seed=DEV_SEED, stream=DEV_STREAM):
    """Arbitrary positive numbers from a recorded SeedSequence (development coordinates)."""
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, stream, n_rows, n_columns])))
    return np.round(100 + np.cumsum(rng.normal(0.5, 1.0, size=(n_rows, n_columns)), axis=0), 3)


def table_cells(*, vintages=None, quarters=None, top=4, left=1, overrides=None, separator_after=None, values=None,
                corner="Reference quarter", staircase=True):
    """{(row, column): value}: the header row of vintage labels at row `top`, the label column at `left`, one
    row per reference quarter below. Vintage k has a level for every quarter up to n - (n_v - 1) + k (a
    staircase) when `staircase`, else for every quarter. `overrides` maps (quarter index, vintage index) to a
    cell value. `separator_after` inserts a blank column after that vintage index."""
    vintages = month_labels() if vintages is None else list(vintages)
    quarters = quarter_labels() if quarters is None else list(quarters)
    numbers = levels(len(quarters), len(vintages)) if values is None else values
    overrides = overrides or {}
    cells = {(top, left): corner}
    columns = []
    column = left + 1
    for k in range(len(vintages)):
        columns.append(column)
        column += 2 if separator_after is not None and k == separator_after else 1
    for k, label in enumerate(vintages):
        cells[(top, columns[k])] = label
    for i, label in enumerate(quarters):
        row = top + 1 + i
        cells[(row, left)] = label
        for k in range(len(vintages)):
            covered = (not staircase) or i <= len(quarters) - len(vintages) + k
            value = float(numbers[i, k]) if covered else None
            cells[(row, columns[k])] = overrides.get((i, k), value)
    return cells


def workbook(*, title_rows=("Constructed real-time table of artificial levels",), notes_rows=(), sheet="Table",
             extra_sheets=(), doc_title=LABEL, merged=(), comments=(), date1904=False, **table):
    """One table sheet (titles above, notes below) plus `extra_sheets` [(name, cells, state)]."""
    top = table.pop("top", 2 + len(title_rows))
    cells = {(r + 1, 1): text for r, text in enumerate(title_rows)}
    cells[(1, 3)] = LABEL
    body = table_cells(top=top, **table)
    cells.update(body)
    last = max(row for row, _ in body)
    for offset, text in enumerate(notes_rows, start=2):
        cells[(last + offset, 1)] = text
    book = Book(title=doc_title, date1904=date1904).sheet(sheet, cells, merged=merged, comments=comments)
    for name, extra, state in extra_sheets:
        book.sheet(name, extra, state=state)
    return book.build()


def split_workbook(first=3, second_quarters=None, second_vintages=None):
    """The default table split across two sheets: vintages 0..first-1 and first.. (joinable by default)."""
    vintages, quarters = month_labels(n=6), quarter_labels()
    numbers = levels(len(quarters), 6)
    a = table_cells(vintages=vintages[:first], quarters=quarters, values=numbers[:, :first], top=3, staircase=False)
    b = table_cells(vintages=second_vintages or vintages[first:], quarters=second_quarters or quarters,
                    values=numbers[:, first:], top=3, staircase=False)
    a[(1, 1)] = b[(1, 1)] = LABEL
    return Book(title=LABEL).sheet("Part 1", a).sheet("Part 2", b).build()


# ---------------------------------------------------------------------------------------- pages

DATASET = "/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi"


def edition_entry(label, slug, *, file_type="xlsx", size="1.0 KB", edition_page=False, files=1):
    links = "".join(f'<a href="/file?uri={DATASET}/{slug}/constructedtestfile{n}.{file_type}" class="btn">'
                    f"<span>{file_type} ({size})</span></a>" for n in range(files))
    page = (f'<p><a href="{DATASET}/{slug}" class="underline-link">Previous versions </a> of this data are '
            "available.</p>") if edition_page else ""
    return ('<div class="show-hide show-hide--light js-show-hide border-top--abbey-sm"><div class="js-show-hide__title">'
            f'<h3 class="margin-top--0">{escape(label)} edition of this dataset </h3></div>'
            f'<div class="js-show-hide__content"><div class="margin-bottom--2">{links}</div>{page}</div></div>')


def dataset_page(entries, *, release="13 August 2026", next_release="30 September 2026"):
    """A page in the layout of the dataset landing page; entries are (label, slug) or edition_entry() text."""
    blocks = "".join(e if isinstance(e, str) else edition_entry(*e) for e in entries)
    return (f'<!DOCTYPE html><html><head><title>Constructed test dataset page</title></head><body>'
            '<ul><li class="meta__item"><div class="meta__term">Release date:</div><div>'
            f'{release}</div></li><li class="meta__item"><div class="meta__term">Next release:</div><div>'
            f'{next_release}</div></li></ul><section><h2>Edition in this dataset</h2>{blocks}</section>'
            "</body></html>").encode("utf-8")


def calendar_page(title, released="30 September 2026 7:00am", *, status="published", lists=True,
                  next_release="12 November 2026"):
    data = (f'<li><p><a href="{DATASET}">Constructed real-time database</a></p></li>' if lists else
            '<li><p><a href="/economy/grossdomesticproductgdp/datasets/otherconstructeddataset">Other</a></p></li>')
    return (f'<!DOCTYPE html><html><head><title>{escape(title)}</title></head><body>'
            f'<div class="release" data-gtm-release-status="{status}"><h1><span>{escape(title)}</span></h1>'
            f'<span>Released:</span> <span>{released}</span> <span>Next release:</span> <span>{next_release}</span>'
            f"</div><section><h2>Data</h2><ul>{data}</ul></section></body></html>").encode("utf-8")


def edition_page(release="13 August 2026", next_release="30 September 2026"):
    return ("<!DOCTYPE html><html><head><title>Constructed edition page</title></head><body>"
            f'<p class="meta__item"><span>Release date: </span><br/>{release}<br/></p>'
            f'<p class="meta__item"><span>Next release: </span><br/>{next_release}</p>'
            "</body></html>").encode("utf-8")


Q2_FIRST = ("Quarter 2 (Apr to June) 2026, first estimate", "quarter2aprtojune2026firstestimate")
Q2_QNA = ("Quarter 2 (Apr to June) 2026, quarterly national accounts", "quarter2aprtojune2026quarterlynationalaccounts")
Q1_QNA = ("Quarter 1 (Jan to Mar) 2026, quarterly national accounts", "quarter1jantomar2026quarterlynationalaccounts")
Q1_FIRST = ("Quarter 1 (Jan to Mar) 2026, first estimate", "quarter1jantomar2026firstestimate")


def page_29_september():
    """The constructed counterpart of the 29 September listing: latest edition released 13 August 2026."""
    return dataset_page([Q2_FIRST, Q1_QNA, Q1_FIRST], release="13 August 2026", next_release="30 September 2026")


def page_30_september(next_release="12 November 2026"):
    """The listing after the release of 30 September 2026: a new first entry."""
    return dataset_page([Q2_QNA, Q2_FIRST, Q1_QNA, Q1_FIRST], release="30 September 2026", next_release=next_release)


def file_url(slug, n=0, file_type="xlsx"):
    return f"https://www.ons.gov.uk/file?uri={DATASET}/{slug}/constructedtestfile{n}.{file_type}"


# ------------------------------------------------------------------------ throwaway research root

def git(root, *args):
    return subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args], cwd=root,
                          check=True, capture_output=True, text=True).stdout.strip()


GATE_RUNNER = '''"""Test runner for E4 (constructed root): the registration gate of tools/run_e_checks.py for E4, and a
fixed code identity for the frozen-code check. Not the research runner."""
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location("run_e_checks_for_e4_tests", Path(__file__).with_name("run_e_checks.py"))
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
verify_extension_gate = _module.verify_extension_gate
gate_record = _module.gate_record


def run_identity(root, *, registered):
    identity = json.loads((Path(root) / "tools/e4_test_identity.json").read_text())
    return dict(code_sha256=identity["code_sha256"], e1_code_sha256=identity["e1_code_sha256"])
'''


def e4_root(tmp_path, *, code_sha256="c" * 64, e1_code_sha256=E1_CODE):
    """A git repository with prereg/E4.md tagged prereg-E4 (annotated, pushed to a local bare origin), a test
    copy of audit/E4_REGISTRATION.json naming that tag, a constructed E1 X.3 record (the frozen E1 code
    identity that the E4 identity must contain), the research .gitignore, a manifest and a test gate."""
    origin, root = tmp_path / "origin.git", tmp_path / "research"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    for relative in ("prereg/E4.md", ".gitignore", "tools/run_e_checks.py"):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PACKAGE / relative, root / relative)
    (root / "tools/run_e4_checks.py").write_text(GATE_RUNNER, encoding="utf-8")
    (root / "tools/e4_test_identity.json").write_text(json.dumps(dict(code_sha256=code_sha256,
                                                                     e1_code_sha256=e1_code_sha256)) + "\n")
    (root / "data/raw").mkdir(parents=True)
    (root / "data/raw/.gitkeep").write_text("")
    (root / "audit").mkdir()
    (root / "audit/E1_X3.json").write_text(json.dumps(x3_record("e1", E1_CODE), indent=1) + "\n", encoding="utf-8")
    (root / "DATA_MANIFEST.csv").write_text("file,source_url,series_id,retrieved_utc,sha256,licence,notes\n"
                                            "data/raw/.gitkeep,https://example.invalid,constructed,2026-09-30T00:00:00Z,"
                                            + "0" * 64 + ",constructed,constructed test row\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "constructed research root")
    git(root, "tag", "-a", "prereg-E4", "-m", "E4 registered addendum (test copy)")
    receipt = json.loads((PACKAGE / "audit/E4_REGISTRATION.json").read_text(encoding="utf-8"))
    commit = git(root, "rev-parse", "prereg-E4^{commit}")
    receipt.update(prereg_tag_commit=commit, source_commit=commit,
                   test_note="Test copy of the registration record with the tag commit replaced")
    (root / "audit/E4_REGISTRATION.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "registration record (test copy)")
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "-q", "origin", "HEAD:refs/heads/main", "--tags")
    return root


def commit_all(root, message="test step"):
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", message)


# -------------------------------------------- the layout that E4 amendment 1 describes (constructed labels)

FULL_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December")
# The three places of amendment 1, rule B, with the header texts that the amendment quotes (text only).
PLACES = (("1961 - 1982", "H", "Sep-62 [1958 prices]", "1962-03"),
          ("1961 - 1982", "CN", "Mar-62 [1963 prices]", "1969-03"),
          ("1961 - 1982", "GQ", "Feb-772", "1978-02"))


def short_label(year, month, *, full=False, four=False, note=None, code=None, before_code="\n", hyphen="-"):
    """A constructed vintage label in the form of amendment 1 ('Oct-61'), with an optional note and code."""
    text = f"{FULL_MONTHS[month - 1] if full else MONTHS[month - 1]}{hyphen}{year if four else f'{year % 100:02d}'}"
    if note:
        text += f" [{note} prices]"
    if code:
        text += before_code + code
    return text


def month_run(first, n):
    year, month = first
    out = []
    for _ in range(n):
        out.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def label_reading(*, pivot=61, places=PLACES, codes=("M1", "M2", "1st", "QNA")):
    """A constructed `label_reading` section of an amendment record (docs/E4_AMENDMENT_1_CODE.md)."""
    return dict(rule_a=dict(century_pivot=pivot, codes=list(codes)),
                readings_by_place=[dict(sheet=s, column=c, text=t, release_month=m) for s, c, t, m in places],
                join=dict(rule="first_labels_of_longest_part"))


def layout_cells(labels, n_quarters, *, values=None, title="Constructed real-time table of artificial levels"):
    """One sheet in the layout of amendment 1: vintage labels in row 4 from column B, reference-quarter labels
    in column A from row 5 (from 1955 Q1, no gap). The first half of the vintages has no level in the last row."""
    numbers = levels(n_quarters, len(labels)) if values is None else values
    cells = {(1, 1): LABEL, (2, 1): title, (4, 1): "Reference quarter"}
    for k, label in enumerate(labels):
        cells[(4, 2 + k)] = label
    for i, quarter in enumerate(quarter_labels(n=n_quarters)):
        cells[(5 + i, 1)] = quarter
        for k in range(len(labels)):
            covered = i < n_quarters - 1 or k >= len(labels) // 2
            cells[(5 + i, 2 + k)] = float(numbers[i, k]) if covered else None
    return cells


def sheet_1961(n_quarters=20, *, changes=None):
    """'1961 - 1982': 199 labels in columns B to GR, one month after the other from September 1961, so that the
    neighbours of H, CN and GQ are the months the amendment names; H, CN and GQ hold the three quoted texts."""
    labels = [short_label(y, m) for y, m in month_run((1961, 9), 199)]
    labels[1] = short_label(1961, 10, note=1950)                       # a constructed note
    labels[3] = short_label(1961, 12, code="M1")
    labels[4] = short_label(1962, 1, note=1950, code="M2")
    for _, column, text, _ in PLACES:
        labels[column_number(column) - 2] = text
    for column, text in (changes or {}).items():
        labels[column_number(column) - 2] = text
    return labels, n_quarters


def column_number(letters):
    number = 0
    for ch in letters:
        number = number * 26 + ord(ch) - 64
    return number


def sheet_1983(n_quarters=28):
    """'1983 - 2003': 40 labels from December 1982 with codes on the next line, and a tie: two labels of one
    release month side by side (the second with a note)."""
    months = month_run((1982, 12), 39)
    months.insert(12, months[11])
    labels = [short_label(y, m, code=("M1" if k % 3 == 0 else "M2" if k % 3 == 1 else None))
              for k, (y, m) in enumerate(months)]
    labels[12] = short_label(*months[12], note=1980)
    return labels, n_quarters


def sheet_2004(n_quarters=36):
    """'2004 - 2017': 40 labels from December 2003 with the codes QNA and 1st on the next line."""
    return [short_label(y, m, code=("QNA" if k % 2 else "1st")) for k, (y, m) in enumerate(month_run((2003, 12), 40))], \
        n_quarters


def sheet_2018(n_quarters=44):
    """'2018 - ': 40 labels from June 2018 with the irregular forms the amendment describes, constructed: the
    month in full, a four-digit year, spaces around the hyphen, a trailing space and line break, a code after a
    space."""
    months = month_run((2018, 6), 40)
    labels = [short_label(y, m, code="M1") for y, m in months]
    labels[3] = short_label(*months[3], full=True, code="QNA", before_code=" ")
    labels[5] = short_label(*months[5], four=True, code="1st", before_code=" ", hyphen="- ")
    labels[7] = short_label(*months[7], code="1st", before_code=" ", hyphen="- ") + " "
    labels[9] = short_label(*months[9]) + " \n1st"
    labels[11] = short_label(*months[11], code="M2", before_code=" ")
    return labels, n_quarters


def layout_workbook(sheets=None, *, cover=True, properties=None):
    """The four sheets of amendment 1's layout (constructed labels and numbers), after a cover sheet."""
    sheets = sheets if sheets is not None else [("1961 - 1982", *sheet_1961()), ("1983 - 2003", *sheet_1983()),
                                                ("2004 - 2017", *sheet_2004()), ("2018 - ", *sheet_2018())]
    book = Book(title=LABEL)
    if cover:
        book.sheet("Cover", {(1, 1): LABEL, (4, 1): "M1 and M2: constructed codes of the estimate"})
    for name, labels, n_quarters in sheets:
        book.sheet(name, layout_cells(labels, n_quarters))
    content = book.build()
    return with_core_properties(content, **properties) if properties else content


def with_core_properties(content, **properties):
    """The same package with docProps/core.xml holding the title and the given properties (creator,
    lastModifiedBy, ...)."""
    names = dict(creator="dc:creator", lastModifiedBy="cp:lastModifiedBy", title="dc:title", subject="dc:subject")
    body = "".join(f"<{names[k]}>{escape(v)}</{names[k]}>" for k, v in dict(dict(title=LABEL), **properties).items())
    source, buffer = zipfile.ZipFile(io.BytesIO(content)), io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        for item in source.infolist():
            if item.filename != "docProps/core.xml":
                package.writestr(item, source.read(item.filename))
        package.writestr("docProps/core.xml", '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/'
                         'package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
                         f"{body}</cp:coreProperties>")
    return buffer.getvalue()
