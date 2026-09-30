"""Shared constructors for constructed workbooks and availability tables (no file, no data)."""
import datetime as dt
import pytest
from uc_e4.table import RawPart, build_tables


def quarter_labels(first=(1955, 1), n=12, style="{y} Q{q}"):
    y, q = first
    out = []
    for _ in range(n):
        out.append(style.format(y=y, q=q))
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return tuple(out)


def month_labels(first=(2016, 1), n=4, style="{m} {y}"):
    names = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    y, m = first
    out = []
    for _ in range(n):
        out.append(style.format(m=names[m - 1], y=y))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return tuple(out)


def part(name="A", vintages=None, quarters=None, fill=None):
    vintages = vintages if vintages is not None else month_labels()
    quarters = quarters if quarters is not None else quarter_labels()
    cells = tuple(tuple((fill(r, c) if fill else 100.0 + r + 0.5 * c) for c in range(len(vintages)))
                  for r in range(len(quarters)))
    return RawPart(name, tuple(vintages), tuple(quarters), cells)


import math
from uc_e4.table import quarter_from_index, quarter_index


def make_tables(*, first_row=(1955, 1), last_row=(2012, 4), n_vintages=6, first_month=(2016, 1),
                covers=None, overrides=None, drop_rows=()):
    """Constructed workbook -> Tables. `covers[k] = (first_q, last_q)` (inclusive) is the reference-quarter
    range in which vintage k has numeric levels; other cells are empty. `overrides[(k, quarter)]` is a raw cell.
    The levels are arbitrary smooth positive numbers (nothing here resembles a real series)."""
    from uc_e4.table import build_tables
    covers = covers or {}
    overrides = overrides or {}
    rows = [quarter_from_index(i) for i in range(quarter_index(first_row), quarter_index(last_row) + 1)
            if quarter_from_index(i) not in drop_rows]
    vintages = month_labels(first_month, n_vintages)
    cells = []
    for q in rows:
        row = []
        for k in range(n_vintages):
            lo, hi = covers.get(k, (first_row, last_row))
            if (k, q) in overrides:
                row.append(overrides[(k, q)])
            elif quarter_index(lo) <= quarter_index(q) <= quarter_index(hi):
                i = quarter_index(q) - quarter_index((1950, 1))
                row.append(100.0 * math.exp(0.006 * i + 0.02 * math.sin(0.7 * i + k)))
            else:
                row.append(None)
        cells.append(tuple(row))
    from uc_e4.table import RawPart
    return build_tables([RawPart("T", tuple(vintages), tuple(f"{y} Q{q}" for y, q in rows), tuple(cells))])


import numpy as np
from uc_core.validation_design import h1_design_series
from uc_e4.streams import stream_rng

DEV_SEED = 20260930


def growth_series(n, replicate=0, *, kappa=1.0):
    """A synthetic AR(2) growth-like series (H1's generator, development stream 9990): first n values."""
    return h1_design_series(stream_rng(DEV_SEED, 9990, 0, replicate), kappa=kappa)[:n]


def ar_tables(n_growth=259):
    """Constructed workbook whose vintages are built from one synthetic AR(2) growth series (arbitrary numbers).

    Levels of vintage k: 100*exp(cumsum(g)/400) times a small vintage-specific factor, so that vintages differ.
    Coverage: vintage 0 ends at 1972Q4, 1 at 1979Q3, 2 at 1990Q1, 3 at 2007Q4, 4 and 5 at 2019Q4, so the first
    vintage holding q_j - 1 is 1, 2, 3, 4 for the four registered onsets and each first release is verifiable.
    """
    from uc_e4.table import RawPart, build_tables, quarter_from_index, quarter_index
    g = growth_series(n_growth, replicate=77)
    base = np.concatenate([[0.0], np.cumsum(g) / 400.0])            # log-levels from 1955Q1
    ends = {0: (1972, 4), 1: (1979, 3), 2: (1990, 1), 3: (2007, 4), 4: (2019, 4), 5: (2019, 4)}
    rows = [quarter_from_index(quarter_index((1955, 1)) + i) for i in range(len(base))]
    vintages = ("Jan 2016", "Feb 2016", "Mar 2016", "Apr 2016", "May 2016", "Jun 2016")
    cells = []
    for i, q in enumerate(rows):
        cells.append(tuple(100.0 * math.exp(base[i] + 0.0005 * k * math.sin(0.9 * i)) if quarter_index(q) <=
                           quarter_index(ends[k]) else None for k in range(6)))
    return build_tables([RawPart("T", vintages, tuple(f"{y} Q{qq}" for y, qq in rows), tuple(cells))])
