"""E4 sections 5 and 7: the vintage series of an episode and the episode's eligibility.

Input is the pair of tables from `uc_e4.table.build_tables`: the availability table decides which levels
are present and the level table supplies the numbers. Nothing is interpolated, spliced or ranked by value.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from .table import AvailabilityTable, LevelTable, Tables, parse_quarter, previous_quarter, quarter_index, quarter_text

FLOOR = (1955, 1)                                         # section 5: "the later of 1955Q1 and the first quarter of that run"
REGISTERED_ONSETS = ((1973, 3), (1980, 1), (1990, 3), (2008, 2))   # section 7: j = 0..3, never renumbered
LOOKBACK = 8
DEFAULT_WINDOW = 40


def minimum_growth(window: int) -> int:
    """Section 7 step 3 and section 10: n_v >= window + 8 (48, 40, 56 for W = 40, 32, 48): M(n_v - 9) exists."""
    return int(window) + LOOKBACK


@dataclass(frozen=True)
class H1Episode:
    j: int
    onset: tuple                 # (year, quarter) of q_j
    delta_final: float | None    # from the h1-frozen record; used only by the descriptive tables


def h1_episodes_from_record(record) -> tuple:
    """The four H1 eligible primary episodes, from a loaded `audit/H1_RESULT.json` (the frozen public record).

    j is the position among the episodes with an available statistic (chronological); the onsets must equal
    the four registered ones (section 4), otherwise the record is not the one E4 was written for.
    """
    rows = [e for e in record["episodes"] if e.get("statistic_available")]
    found = tuple((parse_quarter(e["onset_quarter"]), e["change"]) for e in rows)
    if tuple(q for q, _ in found) != REGISTERED_ONSETS:
        raise ValueError("the H1 eligible episodes are not the four onsets of prereg/E4.md section 4")
    return tuple(H1Episode(j, q, float(change)) for j, (q, change) in enumerate(found))


def load_h1_episodes(path) -> tuple:
    with open(path, encoding="utf-8") as handle:
        return h1_episodes_from_record(json.load(handle))


@dataclass(frozen=True)
class VintageSeries:
    """The section 5 series of one episode in one vintage."""
    vintage: int                       # vintage number (vintage order)
    onset: tuple                       # q_j
    status: str                        # 'ok', 'no_level' (no level for q_j - 1) or 'stop' (section 5 stop)
    first_quarter: tuple | None        # first quarter of the run used (levels), after the 1955Q1 floor
    last_quarter: tuple | None         # q_j - 1
    run_ended_by: str | None           # 'gap:<quarter>' (empty cell or marker), 'no_row:<quarter>' or 'floor' (1955Q1)
    n_levels: int
    n_v: int                           # growth observations = n_levels - 1 (0 when there are fewer than two levels)
    growth: np.ndarray | None
    stop: str | None                   # the reason of a section 5 stop (recorded, the episode is unavailable)


def growth_from_levels(levels) -> np.ndarray:
    """g[t] = 400*(ln(Y[t]) - ln(Y[t-1])), the expression H1 uses (uc_core.abmi.growth)."""
    return 400 * np.diff(np.log(np.asarray(levels, dtype=float)))


def vintage_series(av: AvailabilityTable, lv: LevelTable, k: int, onset) -> VintageSeries:
    """Section 5 for vintage number k and onset quarter q_j.

    The run is the contiguous run of present quarters ending at q_j - 1, started no earlier than 1955Q1; a
    quarter before q_j - 1 with no level (empty cell, marker or no row) ends it; quarters after q_j - 1 are
    ignored. A non-positive or non-finite level inside the run is a stop: no growth is returned.
    """
    onset = tuple(onset)
    last = previous_quarter(onset)
    if not av.present(k, last):
        return VintageSeries(k, onset, "no_level", None, last, None, 0, 0, None, None)
    run, quarter = [last], last
    while True:
        earlier = previous_quarter(quarter)
        if quarter_index(earlier) < quarter_index(FLOOR):
            ended = "floor"
            break
        if not av.present(k, earlier):
            ended = f"{'gap' if av.row(earlier) is not None else 'no_row'}:{quarter_text(earlier)}"
            break
        run.append(earlier)
        quarter = earlier
    run.reverse()
    levels = np.array([lv.level(k, av.row(q)) for q in run])
    n_levels = len(levels)
    n_v = max(n_levels - 1, 0)
    bad = [(q, x) for q, x in zip(run, levels) if not np.isfinite(x) or x <= 0]
    if bad:
        q, x = bad[0]
        why = "non-finite" if not np.isfinite(x) else "non-positive"
        return VintageSeries(k, onset, "stop", run[0], last, ended, n_levels, n_v, None,
                             f"{why} level in the run at {quarter_text(q)} ({len(bad)} such level(s))")
    growth = growth_from_levels(levels) if n_levels >= 2 else np.empty(0)
    return VintageSeries(k, onset, "ok", run[0], last, ended, n_levels, n_v, growth, None)


@dataclass(frozen=True)
class EpisodeSelection:
    """Section 7 outcome for one H1 episode; `failed_step` is 7.1 to 7.4 for an unavailable episode."""
    j: int
    onset: tuple
    delta_final: float | None
    status: str                        # 'eligible' or 'unavailable'
    failed_step: str | None
    reason: str | None
    vintage: int | None                # v_j (vintage number), None when step 7.1 failed
    vintage_label: str | None
    previous_vintage_label: str | None
    series: VintageSeries | None
    stop_note: str | None = None       # a section 5 stop found in a series whose episode failed an earlier step


def select_episode(tables: Tables, episode: H1Episode, window: int = DEFAULT_WINDOW) -> EpisodeSelection:
    av, lv = tables.availability, tables.levels
    base = dict(j=episode.j, onset=episode.onset, delta_final=episode.delta_final)
    last = previous_quarter(episode.onset)
    k = av.first_present(last)                                                  # step 1
    if k is None:
        return EpisodeSelection(**base, status="unavailable", failed_step="7.1",
                                reason=f"no vintage has a level for {quarter_text(last)}", vintage=None,
                                vintage_label=None, previous_vintage_label=None, series=None)
    label = av.vintages[k].label
    if k == 0:                                                                  # step 2
        return EpisodeSelection(**base, status="unavailable", failed_step="7.2",
                                reason="first release unverifiable: v_j is the earliest vintage in the workbook",
                                vintage=k, vintage_label=label, previous_vintage_label=None, series=None)
    previous = av.vintages[k - 1].label
    if av.present(k - 1, last):        # cannot happen when v_j is the earliest vintage with a level (kept as the text's check)
        return EpisodeSelection(**base, status="unavailable", failed_step="7.2",
                                reason="the vintage before v_j already has a level for q_j - 1", vintage=k,
                                vintage_label=label, previous_vintage_label=previous, series=None)
    series = vintage_series(av, lv, k, episode.onset)
    if series.n_v < minimum_growth(window):                                     # step 3
        return EpisodeSelection(**base, status="unavailable", failed_step="7.3",
                                reason=f"n_v = {series.n_v} < {minimum_growth(window)} growth observations "
                                       f"(run ended by {series.run_ended_by})",
                                vintage=k, vintage_label=label, previous_vintage_label=previous, series=series,
                                stop_note=series.stop)
    if series.status == "stop":                                                 # step 4
        return EpisodeSelection(**base, status="unavailable", failed_step="7.4", reason=series.stop, vintage=k,
                                vintage_label=label, previous_vintage_label=previous, series=series)
    return EpisodeSelection(**base, status="eligible", failed_step=None, reason=None, vintage=k,
                            vintage_label=label, previous_vintage_label=previous, series=series)


def select_episodes(tables: Tables, episodes, window: int = DEFAULT_WINDOW) -> tuple:
    """Section 7 for every H1 eligible episode, in chronological order; j is never renumbered."""
    return tuple(select_episode(tables, e, window) for e in episodes)
