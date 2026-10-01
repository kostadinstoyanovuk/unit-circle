"""E2 sections 4, 5 and 7: the sample, the variables (g, du) and the table of onsets computed by rule.

No function reads or downloads data: the caller supplies labelled values (the X.2 tool) or H1's growth values
(the X.1 onsets tool). Episodes are the registered uc_core functions, imported unchanged.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from uc_core.constants import MASTER_SEED
from uc_core.recession import episodes
from uc_ext import common as c

from .constants import (DEVELOPMENT_POWER_ONSETS, FIRST_LEVEL_QUARTER, H1_OFFSET, LAST_QUARTER, LOOKBACK, MERGE,
                        MINIMUM_ONSET_GAP, MINIMUM_RUN, N_LEVELS, N_OBS, ONSETS_RECORD, QUARTER_LABEL, WINDOW)


# ------------------------------------------------------------------------------ sections 4-5: variables

def _quarter_number(label):
    match = QUARTER_LABEL.match(label) if isinstance(label, str) else None
    if not match:
        raise ValueError(f"Quarter label {label!r} is not of the form 'YYYY Qn'")
    return int(match.group(1)) * 4 + int(match.group(2)) - 1


def quarter_label(position):
    """Quarter of E2 position p (0 = 1971Q2, 39 = 1981Q1, 48 = 1983Q2, 194 = 2019Q4)."""
    number = FIRST_LEVEL_QUARTER[0] * 4 + FIRST_LEVEL_QUARTER[1] + int(position)
    return f"{number // 4} Q{number % 4 + 1}"


def _select(quarters, values, name, check):
    quarters, values = list(quarters), list(values)
    if len(quarters) != len(values):
        raise ValueError(f"{name}: quarters and values differ in length")
    numbers = [_quarter_number(q) for q in quarters]
    first = _quarter_number(f"{FIRST_LEVEL_QUARTER[0]} Q{FIRST_LEVEL_QUARTER[1]}")
    last = _quarter_number(f"{LAST_QUARTER[0]} Q{LAST_QUARTER[1]}")
    selected = [(number, value) for number, value in zip(numbers, values) if first <= number <= last]
    found = [number for number, _ in selected]
    if len(set(found)) != len(found):
        raise ValueError(f"{name}: a quarter in 1971Q1-2019Q4 is duplicated")
    if found != list(range(first, last + 1)):
        raise ValueError(f"{name}: 1971Q1-2019Q4 are not exactly {N_LEVELS} contiguous increasing quarters")
    result = []
    for number, value in selected:
        label = f"{number // 4} Q{number % 4 + 1}"
        if isinstance(value, (bool, np.bool_, str)) or value is None:
            raise ValueError(f"{name}: non-numeric value at {label}")
        try:
            number_value = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name}: non-numeric value at {label}") from error
        if not math.isfinite(number_value) or not check(number_value):
            raise ValueError(f"{name}: value at {label} outside its admissible range")
        result.append(number_value)
    return np.asarray(result)


def variables(gdp_quarters, gdp_levels, rate_quarters, rates):
    """Sections 4-5 stop rules and variables: (quarters, X) with X[t] = (g[t], du[t]), 195 x 2, 1971Q2-2019Q4.

    Rows outside 1971Q1-2019Q4 are dropped by label alone; their values are not inspected. Raises ValueError
    (stop and amend) on a missing, duplicated or unidentifiable quarter, a non-positive or non-finite level,
    or a rate outside [0, 100]. g = 400*diff(ln Y), the expression of uc_core.abmi.growth, so g equals H1's
    growth for the same quarters bit for bit; du = diff(u) in percentage points. Which MGSX rows supply u
    (quarterly rows, or the three-month average ending in the quarter's last month) is decided by the X.2
    tool, which passes the chosen quarterly values here with 'YYYY Qn' labels.
    """
    levels = _select(gdp_quarters, gdp_levels, "GDP levels", lambda v: v > 0)
    unemployment = _select(rate_quarters, rates, "Unemployment rates", lambda v: 0 <= v <= 100)
    growth = 400 * np.diff(np.log(levels))
    return tuple(quarter_label(p) for p in range(N_OBS)), np.column_stack((growth, np.diff(unemployment)))


def e2_growth_from_h1(h1_growth):
    """The 195 E2 growth values are H1's growth positions 64-258 (section 5: g equals H1's g)."""
    values = np.asarray(h1_growth, dtype=float)
    if values.shape != (N_OBS + H1_OFFSET,) or not np.isfinite(values).all():
        raise ValueError("Expected H1's 259 finite growth values (1955Q2-2019Q4)")
    return values[H1_OFFSET:].copy()


def onset_table(h1_growth):
    """Section 7's table, computed by rule from H1's 259 growth values (X.1; GDP only, no unemployment).

    One row per merged E2 episode on positions 0-194: onset and end positions and quarters, the runs,
    eligibility at W = 32, 40 and 48 and whether H1 has an episode with the same onset quarter. R3:
    eligibility here is structural (M(r-9) exists: r >= W + 8); whether the required moduli are finite can
    only be known once the VAR is fitted at X.4. `power_onsets` is the tuple of W = 40 eligible onsets that
    the power check uses (ONSETS_RECORD). Nothing in this repository has applied it to the registered file.
    """
    growth = e2_growth_from_h1(h1_growth)
    h1_episodes = episodes(np.asarray(h1_growth, dtype=float), minimum_run=MINIMUM_RUN, merge=MERGE)
    h1_onsets = {e.onset - H1_OFFSET for e in h1_episodes}
    rows = []
    for episode in episodes(growth, minimum_run=MINIMUM_RUN, merge=MERGE):
        rows.append(dict(onset=episode.onset, onset_quarter=quarter_label(episode.onset), end=episode.end,
                         end_quarter=quarter_label(episode.end),
                         runs=[(run.onset, run.end) for run in episode.runs],
                         eligible={w: episode.onset >= w + LOOKBACK for w in (32, WINDOW, 48)},
                         also_h1_onset=episode.onset in h1_onsets))
    power = tuple(row["onset"] for row in rows if row["eligible"][WINDOW])
    return dict(rows=rows, m_E2=len(power), power_onsets=power)


def onset_record(h1_growth, h1_labels=None):
    """The X.1 record ONSETS_RECORD: the section 7 table and the W = 40 eligible onsets, from H1's growth.

    With labels (H1's 259 'YYYY Qn' labels), position 64 must be 1971 Q2 and position 258 2019 Q4.
    """
    if h1_labels is not None:
        labels = list(h1_labels)
        if (len(labels) != N_OBS + H1_OFFSET or labels[H1_OFFSET] != quarter_label(0)
                or labels[-1] != quarter_label(N_OBS - 1)):
            raise ValueError("H1 growth labels do not run 1955 Q2-2019 Q4 with 1971 Q2 at position 64")
    table = onset_table(h1_growth)
    return dict(record="E2 section 7 onsets", rule="H1 section 5 applied to g at E2 positions 0-194 "
                "(H1 growth positions 64-258); eligibility structural (r >= W + 8)",
                h1_growth_sha256=c.sha256_values(np.asarray(h1_growth, dtype=float)), window=WINDOW,
                m_E2=table["m_E2"], power_onsets=list(table["power_onsets"]), episodes=table["rows"])


def read_onsets_record(path):
    """R1: the W = 40 eligible onsets from an ONSETS_RECORD file, validated; ValueError when unusable."""
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"{path} is missing or unreadable: {error}") from error
    if (not isinstance(record, dict) or record.get("record") != "E2 section 7 onsets"
            or record.get("window") != WINDOW):
        raise ValueError(f"{path} is not an E2 section 7 onsets record")
    onsets = record.get("power_onsets")
    if not isinstance(onsets, list) or record.get("m_E2") != len(onsets):
        raise ValueError(f"{path}: power_onsets and m_E2 disagree")
    if not onsets:
        raise ValueError(f"{path} lists no eligible onset: E2 is not registered (section 0) and has no power check")
    listed = [row.get("onset") for row in record.get("episodes") or []
              if (row.get("eligible") or {}).get(str(WINDOW))]
    if listed != onsets:
        raise ValueError(f"{path}: power_onsets differ from the W = 40 eligible episodes it lists")
    return check_power_onsets(onsets)


def imposed_onsets(master_seed, onsets=None):
    """R1: the imposed power onsets. Under the registered seed they must be supplied (from ONSETS_RECORD);
    otherwise supplied onsets are used, or the development fixture."""
    if int(master_seed) == MASTER_SEED and onsets is None:
        raise c.RegisteredRunRefused(f"No section 7 onsets: registered E2 power onsets come from {ONSETS_RECORD} "
                                     "(tools/e2_onsets.py at X.1), read by the runner")
    return check_power_onsets(DEVELOPMENT_POWER_ONSETS if onsets is None else onsets)


def check_power_onsets(onsets):
    """Imposed onsets: integers, increasing, at least MINIMUM_ONSET_GAP apart, W = 40 eligible and in range."""
    values = tuple(onsets)
    if not values or any(isinstance(t, (bool, np.bool_)) or not isinstance(t, (int, np.integer)) for t in values):
        raise ValueError("Power onsets must be a non-empty sequence of integer positions")
    values = tuple(int(t) for t in values)
    if values[0] < WINDOW + LOOKBACK or values[-1] >= N_OBS or any(
            b - a < MINIMUM_ONSET_GAP for a, b in zip(values, values[1:])):
        raise ValueError(f"Power onsets must lie in {WINDOW + LOOKBACK}..{N_OBS - 1}, increasing and at least "
                         f"{MINIMUM_ONSET_GAP} apart")
    return values
