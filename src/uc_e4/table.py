"""E4 section 4: the availability-table model (structure mapping at X.2, steps 1 to 5).

The model works on constructed or read cell values and never on a file: reading a workbook is the X.2
tool's job. It keeps two structures apart on purpose.

* `AvailabilityTable` holds only the KIND of every cell (numeric, empty, marker, other), the ordered
  vintages and the reference quarters. Its report prints counts and, for marker and other cells, their
  content with every digit replaced by `#`. It has no access to any level.
* `LevelTable` holds the numbers of the numeric cells and is used only from section 5 on.

Every situation that section 4 says "stop and amend (section 13)" about raises `Stop`; a Stop is not a
deviation and is never converted into a default. Readings of the text where it is silent are listed in
READINGS.md (R-4.1 onwards) and cited in the comments below.
"""
from __future__ import annotations

import datetime as _dt
import numbers
import re
from dataclasses import dataclass

import numpy as np

NUMERIC, EMPTY, MARKER, OTHER = "numeric", "empty", "marker", "other"
KINDS = (NUMERIC, EMPTY, MARKER, OTHER)

# R-4.2: a text equal to one of these literals is an error value (kind other), not a marker.
EXCEL_ERRORS = frozenset({"#NULL!", "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#N/A", "#GETTING_DATA"})


class Stop(Exception):
    """A registered stop: the mapping halts, an amendment is registered before any level is read (section 13).

    `step` names the section 4 step (4.1 table and join, 4.2 kinds, 4.3 labels, 4.4 order); `detail` carries
    printable facts (digits already masked where cell content is involved).
    """

    def __init__(self, step, reason, detail=None):
        super().__init__(f"E4 section 4, step {step}: {reason}")
        self.step, self.reason, self.detail = step, reason, detail


@dataclass(frozen=True)
class ErrorValue:
    """An error value read from a cell (for example a reader's data_type 'e'); its kind is other."""
    text: str


def kind_of(cell) -> str:
    """Kind of one cell (section 4, step 2). R-4.1: exact mapping of Python cell values to the four kinds."""
    if cell is None:
        return EMPTY
    if isinstance(cell, (ErrorValue, bool, np.bool_)):
        return OTHER                                    # error value, logical value
    if isinstance(cell, numbers.Real):
        return NUMERIC                                  # int/float, finite or not: section 5 decides on the value
    if isinstance(cell, str):
        if cell == "":
            return EMPTY
        if cell.strip().upper() in EXCEL_ERRORS:
            return OTHER                                # R-4.2
        return OTHER if any(ch.isdigit() for ch in cell) else MARKER     # R-4.3: any Unicode digit
    return OTHER                                        # dates, times and anything else


def mask_digits(text) -> str:
    """Content with every digit replaced by `#` (step 2 prints only this for marker and other cells)."""
    return "".join("#" if ch.isdigit() else ch for ch in str(text))


# ---- labels (step 3) ------------------------------------------------------------------------------
_MONTHS = {}
for _i, _names in enumerate([("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
                             ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
                             ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
                             ("dec", "december")], start=1):
    for _n in _names:
        _MONTHS[_n] = _i
_IGNORABLE = frozenset({"st", "nd", "rd", "th", "of"})


def _valid_year(y):
    return 1000 <= y <= 2999


@dataclass(frozen=True)
class ReadLabel:
    """A vintage label handed over together with the release month that a registered amendment reads in it.

    The source stage reads a label under the amendment's rules and passes the label text (with each run of
    spaces and line breaks replaced by one space) and the month read; this model then treats the label as
    any other label, so the analysis code does not depend on the amendment.
    """
    text: str
    year: int
    month: int

    def __str__(self):
        return self.text


def parse_release_month(label) -> tuple[int, int]:
    """(year, month) of a vintage label, or ValueError (step 3). R-4.4.

    A label parses if it is a date (date or datetime) or a text that states a calendar month and a
    four-digit year: `2016-01`, `2016/01`, `01/2016`, `2016-01-15` (a date as text), or exactly one month
    name (three letters or in full) and exactly one four-digit year, in either order, with at most one
    day number and the ordinal suffixes. Two-digit years, two month names, other words and numbers do not parse.
    A `ReadLabel` carries the reading of a registered amendment: its year and month, checked for range.
    """
    if isinstance(label, ReadLabel):
        if not (isinstance(label.year, int) and isinstance(label.month, int) and _valid_year(label.year)
                and 1 <= label.month <= 12):
            raise ValueError("year or month out of range")
        return label.year, label.month
    if isinstance(label, _dt.date):                     # datetime is a subclass of date
        return label.year, label.month
    if not isinstance(label, str):
        raise ValueError("not a date or text")
    text = " ".join(label.split())
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?", text)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
    else:
        m = re.fullmatch(r"(\d{1,2})[-/](\d{4})", text)
        if m:
            year, month = int(m.group(2)), int(m.group(1))
        else:
            tokens = re.findall(r"[A-Za-z]+|\d+", text)
            names = [_MONTHS[t.lower()] for t in tokens if t.isalpha() and t.lower() in _MONTHS]
            words = [t for t in tokens if t.isalpha() and t.lower() not in _MONTHS and t.lower() not in _IGNORABLE]
            numbers_ = [t for t in tokens if t.isdigit()]
            years = [int(t) for t in numbers_ if len(t) == 4]
            days = [t for t in numbers_ if len(t) != 4]
            if len(names) != 1 or len(years) != 1 or words or len(days) > 1 or (
                    days and not 1 <= int(days[0]) <= 31):
                raise ValueError("does not state exactly one calendar month and one year")
            year, month = years[0], names[0]
    if not (_valid_year(year) and 1 <= month <= 12):
        raise ValueError("year or month out of range")
    return year, month


_QUARTER_PATTERNS = (
    (re.compile(r"(\d{4})\s?-?\s?Q\s?([1-4])"), (1, 2)),
    (re.compile(r"Q\s?([1-4])\s?[-, ]?\s?(\d{4})"), (2, 1)),
    (re.compile(r"(\d{4})\s+(?:QUARTER|QTR)\.?\s*([1-4])"), (1, 2)),
    (re.compile(r"(?:QUARTER|QTR)\.?\s*([1-4])\s*,?\s*(\d{4})"), (2, 1)),
    (re.compile(r"([1-4])(?:ST|ND|RD|TH)\s+(?:QUARTER|QTR)\.?\s*,?\s*(\d{4})"), (2, 1)),
)


def parse_quarter(label) -> tuple[int, int]:
    """(year, quarter) of a reference-quarter label, or ValueError (step 3). R-4.5.

    Only a text that states a calendar quarter parses (`1955 Q1`, `1955Q1`, `1955-Q1`, `Q1 1955`,
    `1955 quarter 1`, `1st quarter 1955`); a date does not.
    """
    if not isinstance(label, str):
        raise ValueError("not a text")
    text = " ".join(label.upper().split())
    for pattern, (yi, qi) in _QUARTER_PATTERNS:
        m = pattern.fullmatch(text)
        if m:
            year, quarter = int(m.group(yi)), int(m.group(qi))
            if _valid_year(year):
                return year, quarter
    raise ValueError("does not state a calendar quarter")


def quarter_index(q) -> int:
    return 4 * q[0] + q[1] - 1


def quarter_from_index(i: int) -> tuple[int, int]:
    return i // 4, i % 4 + 1


def previous_quarter(q, n=1):
    return quarter_from_index(quarter_index(q) - n)


def quarter_text(q) -> str:
    return f"{q[0]}Q{q[1]}"


# ---- raw parts ------------------------------------------------------------------------------------
@dataclass(frozen=True)
class RawPart:
    """One vintage-by-quarter block as found: column headers = vintages, row labels = reference quarters."""
    name: str
    vintage_labels: tuple
    quarter_labels: tuple
    cells: tuple            # cells[row][column]; raw values

    def __post_init__(self):
        if len(self.cells) != len(self.quarter_labels) or any(len(r) != len(self.vintage_labels) for r in self.cells):
            raise ValueError("cells must have one row per quarter label and one column per vintage label")


def _months_or_stop(part):
    out = []
    for label in part.vintage_labels:
        try:
            out.append(parse_release_month(label))
        except ValueError as error:
            raise Stop("4.3", "a vintage label does not parse", dict(label=mask_digits(label), why=str(error))) from None
    return out


def _direction(months):
    """+1 non-decreasing with a rise, -1 non-increasing with a fall, 0 constant or a single vintage, None otherwise."""
    up = all(a <= b for a, b in zip(months, months[1:]))
    down = all(a >= b for a, b in zip(months, months[1:]))
    if up and down:
        return 0
    return 1 if up else (-1 if down else None)


def join_parts(parts) -> RawPart:
    """Step 1: the one table, or Stop. Several parts are joined only when their vintage ranges do not
    overlap and their reference-quarter labels are identical (R-4.6, R-4.7, R-4.8)."""
    parts = tuple(parts)
    if not parts:
        raise Stop("4.1", "there is no vintage-by-quarter table")
    if len(parts) == 1:
        return parts[0]
    months = [_months_or_stop(p) for p in parts]
    if any(not m for m in months):
        raise Stop("4.1", "a part has no vintage")
    if any(tuple(p.quarter_labels) != tuple(parts[0].quarter_labels) for p in parts[1:]):
        raise Stop("4.1", "parts cannot be joined: their reference-quarter labels are not identical")
    ranges = [(min(m), max(m)) for m in months]
    order = sorted(range(len(parts)), key=lambda i: ranges[i])
    for a, b in zip(order, order[1:]):
        if ranges[b][0] <= ranges[a][1]:                # closed ranges: sharing a month is an overlap (R-4.6)
            raise Stop("4.1", "parts cannot be joined: their vintage ranges overlap")
    directions = [_direction(m) for m in months]
    if any(d == -1 for d in directions) and not any(d == 1 for d in directions):
        order = order[::-1]                             # descending tables are joined in descending range order (R-4.8)
    chosen = [parts[i] for i in order]
    return RawPart("+".join(p.name for p in chosen),
                   tuple(l for p in chosen for l in p.vintage_labels),
                   tuple(parts[0].quarter_labels),
                   tuple(sum((tuple(p.cells[r]) for p in chosen), ()) for r in range(len(parts[0].quarter_labels))))


# ---- the model ------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Vintage:
    label: str               # the vintage label as text (a date label as ISO text)
    release_month: tuple     # (year, month), parsed from the label (step 3)
    position: int            # position in the joined table, left to right


@dataclass(frozen=True)
class AvailabilityTable:
    """Kinds only. `kinds[row, k]` is the kind of the cell of vintage number k (in vintage order) and the
    reference quarter of table row `row`. No level is stored here."""
    vintages: tuple
    quarters: tuple          # (year, quarter) per row, in table row order
    quarter_labels: tuple    # the raw row labels as text
    kinds: np.ndarray
    markers: tuple = ()      # (row, k, text) of every marker cell; a marker has no digit, so nothing is masked

    def row(self, quarter):
        try:
            return self.quarters.index(tuple(quarter))
        except ValueError:
            return None                                 # a reference quarter with no row is no level

    def present(self, k, quarter) -> bool:
        row = self.row(quarter)
        return row is not None and self.kinds[row, k] == NUMERIC

    def first_present(self, quarter):
        """Vintage number of the earliest vintage with a level for `quarter`, or None (section 7, step 1)."""
        row = self.row(quarter)
        if row is None:
            return None
        hits = np.flatnonzero(self.kinds[row] == NUMERIC)
        return int(hits[0]) if len(hits) else None


@dataclass(frozen=True)
class LevelTable:
    """The numbers of the numeric cells (NaN elsewhere), held apart from the availability table."""
    levels: np.ndarray

    def level(self, k, row) -> float:
        return float(self.levels[row, k])


@dataclass(frozen=True)
class Tables:
    availability: AvailabilityTable
    levels: LevelTable
    manifest: dict


def _label_text(label) -> str:
    if isinstance(label, ReadLabel):
        return label.text
    return label.isoformat() if isinstance(label, _dt.date) else str(label)


def build_tables(parts) -> Tables:
    """Steps 1 to 5 in the text's order; the first stop found is raised (R-4.9)."""
    part = join_parts(parts)                                                     # step 1
    n_rows, n_cols = len(part.quarter_labels), len(part.vintage_labels)
    kinds = np.empty((n_rows, n_cols), dtype="<U7")
    for r in range(n_rows):
        for c in range(n_cols):
            kinds[r, c] = kind_of(part.cells[r][c])
    others = [(part.vintage_labels[c], part.quarter_labels[r], mask_digits(part.cells[r][c]))
              for r in range(n_rows) for c in range(n_cols) if kinds[r, c] == OTHER]
    if others:                                                                   # step 2
        raise Stop("4.2", f"{len(others)} cell(s) of kind other in the table",
                   [dict(vintage=mask_digits(v), quarter=mask_digits(q), content=x) for v, q, x in others[:50]])
    months = _months_or_stop(part)                                               # step 3
    quarters = []
    for label in part.quarter_labels:
        try:
            quarters.append(parse_quarter(label))
        except ValueError as error:
            raise Stop("4.3", "a reference-quarter label does not parse",
                       dict(label=mask_digits(label), why=str(error))) from None
    if len(set(quarters)) != len(quarters):
        raise Stop("4.3", "a reference quarter appears twice")
    direction = _direction(months)                                               # step 4
    if direction in (None, 0) or len(months) < 2:
        raise Stop("4.4", "the release months do not increase in one direction across the table")
    order = list(range(n_cols)) if direction == 1 else list(range(n_cols))[::-1]
    vintages = tuple(Vintage(_label_text(part.vintage_labels[p]), months[p], p) for p in order)
    markers = tuple((r, k, part.cells[r][p]) for r in range(n_rows) for k, p in enumerate(order)
                    if kinds[r, p] == MARKER)
    availability = AvailabilityTable(vintages, tuple(quarters), tuple(_label_text(q) for q in part.quarter_labels),
                                     kinds[:, order], markers)
    levels = np.full((n_rows, n_cols), np.nan)
    for r in range(n_rows):
        for k, p in enumerate(order):
            if kinds[r, p] == NUMERIC:
                levels[r, k] = float(part.cells[r][p])
    first = min(quarters)                                                        # step 5
    manifest = dict(earliest_vintage=vintages[0].label, earliest_vintage_month=vintages[0].release_month,
                    latest_vintage=vintages[-1].label, latest_vintage_month=vintages[-1].release_month,
                    earliest_reference_quarter=quarter_text(first), n_vintages=n_cols, n_reference_quarters=n_rows,
                    parts=part.name)
    return Tables(availability, LevelTable(levels), manifest)


def availability_report(av: AvailabilityTable) -> dict:
    """What the X.2 script prints (step 2): per vintage the number of cells of each kind, and for marker and
    other cells their content with every digit replaced by `#`. It takes no LevelTable: no level can appear."""
    rows = []
    for k, v in enumerate(av.vintages):
        rows.append(dict(vintage=v.label, release_month=f"{v.release_month[0]}-{v.release_month[1]:02d}",
                         **{kind: int(np.sum(av.kinds[:, k] == kind)) for kind in KINDS}))
    markers = [dict(vintage=av.vintages[k].label, quarter=av.quarter_labels[r], content=mask_digits(text))
               for r, k, text in av.markers]
    return dict(per_vintage=rows, kinds_total={kind: int(np.sum(av.kinds == kind)) for kind in KINDS},
                marker_cells=markers)
