"""Constructed inputs for the E2 tests: a file in the ONS time-series layout that uc_core.abmi reads.

Every value is constructed from a development stream (seed 20260930, stream 9660); the header texts are the
layout of an ONS series file, not data. Negative growth quarters can be placed at chosen E2 positions so that
the section 7 rule has known episodes.
"""
import numpy as np

from uc_e2 import constants, streams

RELEASE = dict(title="GDP quarterly national accounts, UK: constructed test release",
               release_datetime="2026-06-30T06:00:00+00:00",
               release_url="https://www.ons.gov.uk/releases/constructedtestrelease",
               file_url="https://example.invalid/constructed.csv")
RELEASE_DATE_RECORD = "30-06-2026"


def growth_path(negative_e2_positions=()):
    """Quarterly growth for 1948 Q1-2021 Q4: positive, with -1 at the given E2 positions (H1 position + 64)."""
    rng = streams.stream_rng(streams.DEVELOPMENT_SEED, 9660)
    quarters = [f"{year} Q{q}" for year in range(1948, 2022) for q in range(1, 5)]
    growth = 2. + .5 * np.abs(rng.standard_normal(len(quarters)))
    first = quarters.index("1955 Q2")                       # H1 growth position 0
    for position in negative_e2_positions:
        growth[first + constants.H1_OFFSET + position] = -1.
    return quarters, growth


def ons_csv(negative_e2_positions=()):
    """The bytes of a constructed ABMI-layout file whose levels follow growth_path()."""
    quarters, growth = growth_path(negative_e2_positions)
    levels = 100 * np.exp(np.cumsum(growth / 400))
    rows = [["Title", "Gross Domestic Product: chained volume measures: Seasonally adjusted £m"],
            ["CDID", "ABMI"], ["Source dataset ID", "QNA"], ["PreUnit", "£"], ["Unit", "m"],
            ["Release date", RELEASE_DATE_RECORD], ["Next release", "30 September 2026"], ["Important notes", ""]]
    rows += [[str(year), f"{levels[i * 4]:.6f}"] for i, year in enumerate(range(1948, 2022))]
    rows += [[label, f"{level:.6f}"] for label, level in zip(quarters, levels)]
    return ("\n".join(",".join(f'"{cell}"' for cell in row) for row in rows) + "\n").encode("utf-8")
