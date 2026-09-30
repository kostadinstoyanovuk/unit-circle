"""E4 section 10, descriptive tables: real time against final, and the two clocks (SD-07).

Description only: no test is attached and nothing here is a claim of real-time warning. The release dates
come from ONS metadata and are arguments (a mapping from vintage label to date); where a date is not
established the label month is used and the table says so.
"""
from __future__ import annotations

import datetime as dt
import math

import numpy as np

from .table import AvailabilityTable, LevelTable, previous_quarter, quarter_from_index, quarter_index, quarter_text

LABEL_MONTH_ONLY = "label month only"


def quarter_last_day(q) -> dt.date:
    first_of_next = quarter_from_index(quarter_index(q) + 1)
    return dt.date(first_of_next[0], 3 * (first_of_next[1] - 1) + 1, 1) - dt.timedelta(days=1)


def months_between(earlier, later) -> int:
    return (later[0] - earlier[0]) * 12 + (later[1] - earlier[1])


def _sign(x):
    return (x > 0) - (x < 0)


def first_vintage_showing_onset(av: AvailabilityTable, lv: LevelTable, onset):
    """Vintage number of the first vintage in which quarters q_j and q_j + 1 both show negative growth
    (the first in which the H1 rule could see this onset), or None. Growth of quarter q is
    400*(ln Y(q) - ln Y(q-1)); a vintage lacking a positive finite level for q_j - 1, q_j or q_j + 1 does not show it."""
    onset = tuple(onset)
    quarters = [previous_quarter(onset), onset, quarter_from_index(quarter_index(onset) + 1)]
    for k in range(len(av.vintages)):
        if not all(av.present(k, q) for q in quarters):
            continue
        y = np.array([lv.level(k, av.row(q)) for q in quarters])
        if not (np.isfinite(y).all() and (y > 0).all()):
            continue
        g = 400 * np.diff(np.log(y))
        if g[0] < 0 and g[1] < 0:
            return k
    return None


def real_time_against_final(selections, deltas_rt, release_dates=None):
    """One row per H1 eligible episode, unavailable ones included, and the summaries over E4-eligible ones.

    `deltas_rt` maps j -> Delta_rt for the E4-eligible episodes whose observed statistic exists; an eligible
    episode without one (failed statistic) has None. difference = Delta_rt - Delta_final.
    """
    release_dates = release_dates or {}
    rows = []
    for sel in selections:
        d_rt = deltas_rt.get(sel.j) if sel.status == "eligible" else None
        row = dict(j=sel.j, onset=quarter_text(sel.onset), status=sel.status, failed_step=sel.failed_step,
                   reason=sel.reason, vintage=sel.vintage_label,
                   release_date=(release_dates[sel.vintage_label].isoformat()
                                 if sel.vintage_label in release_dates else None),
                   release_basis="ONS metadata" if sel.vintage_label in release_dates else LABEL_MONTH_ONLY,
                   n_v=sel.series.n_v if sel.series is not None else None,
                   delta_rt=d_rt, delta_final=sel.delta_final,
                   difference=(d_rt - sel.delta_final) if d_rt is not None and sel.delta_final is not None else None)
        rows.append(row)
    usable = [r for r in rows if r["delta_rt"] is not None and r["delta_final"] is not None]
    eligible = [r for r in rows if r["status"] == "eligible"]
    summary = dict(m_E4=len(eligible), S_rt=None, S_final_m=None, mean_difference=None, same_sign=None)
    if eligible and len(usable) == len(eligible):
        s_rt = float(np.mean([r["delta_rt"] for r in usable]))
        s_final = float(np.mean([r["delta_final"] for r in usable]))
        summary.update(S_rt=s_rt, S_final_m=s_final, mean_difference=s_rt - s_final,
                       same_sign=sum(_sign(r["delta_rt"]) == _sign(r["delta_final"]) != 0 for r in usable))
    return dict(rows=rows, summary=summary,
                note="No test is attached. Same sign counts episodes where both changes are positive or both negative.")


def two_clocks(tables, selections, release_dates=None):
    """For each episode: q_j - 1; the release of v_j and whether it falls before the end of q_j; the release
    month of the vintage before v_j and the months between; and the first vintage in which q_j and q_j + 1
    both show negative growth ("none" if no vintage does)."""
    release_dates = release_dates or {}
    av, lv = tables.availability, tables.levels
    rows = []
    for sel in selections:
        k = sel.vintage
        vintage = av.vintages[k] if k is not None else None
        end = quarter_last_day(sel.onset)
        if vintage is None:
            before = None
        elif vintage.label in release_dates:
            before = release_dates[vintage.label] <= end
        else:
            m_end = (end.year, end.month)
            before = True if vintage.release_month < m_end else (False if vintage.release_month > m_end
                                                                 else "undetermined: label month only")
        previous = av.vintages[k - 1] if k is not None and k > 0 else None
        seen = first_vintage_showing_onset(av, lv, sel.onset)
        rows.append(dict(
            j=sel.j, onset=quarter_text(sel.onset), reference_quarter=quarter_text(previous_quarter(sel.onset)),
            vintage=vintage.label if vintage else None,
            release_date=release_dates[vintage.label].isoformat() if vintage and vintage.label in release_dates else None,
            release_month=f"{vintage.release_month[0]}-{vintage.release_month[1]:02d}" if vintage else None,
            release_basis="ONS metadata" if vintage and vintage.label in release_dates else LABEL_MONTH_ONLY,
            onset_quarter_ends=end.isoformat(), release_before_end_of_onset_quarter=before,
            previous_vintage=previous.label if previous else None,
            previous_release_month=(f"{previous.release_month[0]}-{previous.release_month[1]:02d}" if previous else None),
            months_since_previous=months_between(previous.release_month, vintage.release_month) if previous else None,
            first_vintage_showing_the_onset=av.vintages[seen].label if seen is not None else "none"))
    return dict(rows=rows, note="Description, not a test and not a claim of real-time warning (SD-07).")
