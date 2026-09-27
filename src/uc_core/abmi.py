"""ONS ABMI time-series file: identity, the registered 1955Q1-2019Q4 sample and growth (H1 section 3).

The parser separates the file's header records (title, CDID, dataset, release
date) from its observation rows. Identity is checked from the header alone.
Values are read only by `registered_sample`, which applies the registered
stop rules: exactly 260 distinct contiguous quarters, all positive and
finite; no filling, splicing or reordering. Rows outside the sample are not
returned. Every failure raises AcquisitionStop.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import math
import re

import numpy as np

SERIES_ID = 'ABMI'
DATASET_ID = 'QNA'
FIRST, LAST = (1955, 1), (2019, 4)
LEVELS = 260
QUARTER = re.compile(r'^(\d{4}) Q([1-4])$')
ANNUAL = re.compile(r'^\d{4}$')
MONTH = re.compile(r'^\d{4} [A-Z]{3}$')


class AcquisitionStop(RuntimeError):
    """Stop before analysis: identity or sample requirements are not met (H1 section 3)."""


@dataclass(frozen=True)
class TimeSeriesFile:
    header: dict
    quarterly_rows: tuple[tuple[str, str], ...]
    other_rows: int


def parse_time_series_csv(content: bytes) -> TimeSeriesFile:
    """Split an ONS time-series CSV into header records and raw observation rows."""
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise AcquisitionStop('File is not UTF-8 text') from error
    header, quarterly, other = {}, [], 0
    in_data = False
    for row in csv.reader(io.StringIO(text)):
        if not row or not any(cell.strip() for cell in row):
            continue
        if len(row) < 2:
            raise AcquisitionStop(f'Unexpected row shape: {row!r}')
        key, value = row[0].strip(), row[1].strip()
        if QUARTER.match(key):
            in_data = True
            quarterly.append((key, value))
        elif ANNUAL.match(key) or MONTH.match(key):
            in_data = True
            other += 1
        elif in_data:
            raise AcquisitionStop(f'Header record after observation rows: {key!r}')
        else:
            if key in header:
                raise AcquisitionStop(f'Duplicate header record: {key!r}')
            header[key] = value
    return TimeSeriesFile(header, tuple(quarterly), other)


def check_identity(parsed: TimeSeriesFile, *, release_date: str) -> dict:
    """Header-only identity checks; release_date is the file's own DD-MM-YYYY record."""
    header = parsed.header
    problems = []
    if header.get('CDID') != SERIES_ID:
        problems.append(f"CDID is {header.get('CDID')!r}, not {SERIES_ID!r}")
    if header.get('Source dataset ID') != DATASET_ID:
        problems.append(f"Source dataset ID is {header.get('Source dataset ID')!r}, not {DATASET_ID!r}")
    title = header.get('Title', '')
    for fragment in ('chained volume', 'Seasonally adjusted'):
        if fragment.lower() not in title.lower():
            problems.append(f'Title lacks {fragment!r}: {title!r}')
    if header.get('Release date') != release_date:
        problems.append(f"Release date record is {header.get('Release date')!r}, not {release_date!r}")
    if not parsed.quarterly_rows:
        problems.append('No quarterly rows')
    if problems:
        raise AcquisitionStop('; '.join(problems))
    return dict(title=title, cdid=header['CDID'], dataset=header['Source dataset ID'],
                release_date_record=header['Release date'], unit=header.get('Unit'),
                pre_unit=header.get('PreUnit'), quarterly_rows=len(parsed.quarterly_rows),
                other_rows=parsed.other_rows)


def _quarter_number(label: str) -> int:
    match = QUARTER.match(label)
    if not match:
        raise AcquisitionStop(f'Invalid quarter label {label!r}')
    return int(match.group(1)) * 4 + int(match.group(2)) - 1


def registered_sample(parsed: TimeSeriesFile) -> tuple[tuple[str, ...], np.ndarray]:
    """Exactly the 260 levels 1955Q1-2019Q4 in order; stop on any gap, duplicate or invalid value."""
    first, last = FIRST[0] * 4 + FIRST[1] - 1, LAST[0] * 4 + LAST[1] - 1
    numbers = [_quarter_number(label) for label, _ in parsed.quarterly_rows]
    if len(set(numbers)) != len(numbers):
        raise AcquisitionStop('Duplicate quarter labels')
    if numbers != sorted(numbers):
        raise AcquisitionStop('Quarter labels are not in chronological order')
    selected = [(label, raw) for (label, raw), number in zip(parsed.quarterly_rows, numbers)
                if first <= number <= last]
    expected = [f'{n // 4} Q{n % 4 + 1}' for n in range(first, last + 1)]
    if [label for label, _ in selected] != expected:
        raise AcquisitionStop(f'The sample needs exactly {LEVELS} contiguous quarters 1955 Q1-2019 Q4')
    values = []
    for label, raw in selected:
        try:
            value = float(raw)
        except ValueError as error:
            raise AcquisitionStop(f'Non-numeric level at {label}') from error
        if not math.isfinite(value) or value <= 0:
            raise AcquisitionStop(f'Level at {label} is not positive and finite')
        values.append(value)
    return tuple(expected), np.asarray(values, dtype=float)


def growth(labels, levels) -> tuple[tuple[str, ...], np.ndarray]:
    """g[t] = 400 (ln Y[t] - ln Y[t-1]): 259 annualised growth rates, 1955Q2-2019Q4."""
    levels = np.asarray(levels, dtype=float)
    if len(labels) != LEVELS or levels.shape != (LEVELS,):
        raise AcquisitionStop('Growth requires the 260 registered levels')
    return tuple(labels[1:]), 400 * np.diff(np.log(levels))
