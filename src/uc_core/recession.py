"""Retrospective H1 episodes and pre-onset statistic, using positional indices."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
from .rolling import _observations_and_index, _validate_index


@dataclass(frozen=True)
class NegativeRun:
    onset: int
    end: int


@dataclass(frozen=True)
class Episode:
    onset: int
    end: int
    runs: tuple[NegativeRun, ...]


@dataclass(frozen=True)
class PreOnsetResult:
    mean_change: float | None
    changes: tuple[float, ...]
    eligible_onsets: tuple[int, ...]
    ineligible_onsets: tuple[int, ...]


def episodes(growth, *, minimum_run: int = 2, merge: int = 8) -> tuple[Episode, ...]:
    """Runs of strictly negative growth, merged against the previous run's end.

    Indices are zero-based observation positions; endpoints are inclusive.
    A qualifying run beginning within `merge` position steps of the preceding
    qualifying run's end extends that episode, retaining its FIRST onset.
    Chained runs can extend the same episode. Isolated negative quarters are
    not qualifying runs and cannot reset the merging clock.
    """
    if isinstance(minimum_run, bool) or not isinstance(minimum_run, (int, np.integer)) or minimum_run < 1:
        raise ValueError("minimum_run must be a positive integer")
    if isinstance(merge, bool) or not isinstance(merge, (int, np.integer)) or merge < 0:
        raise ValueError("merge must be a nonnegative integer")
    x, _ = _observations_and_index(growth)
    negative = x < 0
    transitions = np.diff(np.r_[False, negative, False].astype(np.int8))
    starts, stops = np.flatnonzero(transitions == 1), np.flatnonzero(transitions == -1) - 1
    result: list[Episode] = []
    for start, end in zip(starts, stops):
        start, end = int(start), int(end)
        if end - start + 1 < minimum_run:
            continue
        run = NegativeRun(start, end)
        if result and start - result[-1].end <= merge:
            previous = result[-1]
            result[-1] = Episode(previous.onset, end, previous.runs + (run,))
        else:
            result.append(Episode(start, end, (run,)))
    return tuple(result)


def pre_onset_changes(modulus, onsets, *, lookback: int = 8) -> PreOnsetResult:
    """Delta=M[onset-1]-M[onset-lookback-1]; mean over eligible episodes.

    Onsets are unique, increasing zero-based positions. NaNs are allowed ONLY
    as a contiguous leading warm-up prefix. Empty eligible sets return None,
    not zero. No onset-quarter value is used. This function has no p-value.
    """
    if isinstance(lookback, bool) or not isinstance(lookback, (int, np.integer)) or lookback < 1:
        raise ValueError("lookback must be a positive integer")
    if isinstance(modulus, pd.Series):
        _validate_index(modulus.index)
    values = np.asarray(modulus)
    if np.iscomplexobj(values):
        raise ValueError("Modulus must be real")
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or np.isinf(values).any() or np.any(values[np.isfinite(values)] < 0):
        raise ValueError("Modulus must be one-dimensional, nonnegative and finite after warm-up")
    available = np.flatnonzero(np.isfinite(values))
    if len(available) and not np.isfinite(values[available[0]:]).all():
        raise ValueError("Missing modulus inside fitted region; do not silently exclude episodes")
    supplied = list(onsets)
    if any(isinstance(t, (bool, np.bool_)) or not isinstance(t, (int, np.integer)) for t in supplied):
        raise ValueError("Onsets must be integer positions")
    supplied = [int(t) for t in supplied]
    if any(t < 0 or t >= len(values) for t in supplied) or any(b <= a for a, b in zip(supplied, supplied[1:])):
        raise ValueError("Onsets must be unique, increasing positions inside the observed series")
    eligible, ineligible, changes = [], [], []
    for onset in supplied:
        earlier, later = onset - lookback - 1, onset - 1
        if earlier < 0 or not np.isfinite(values[earlier]):
            ineligible.append(onset)
            continue
        eligible.append(onset)
        changes.append(float(values[later] - values[earlier]))
    return PreOnsetResult(float(np.mean(changes)) if changes else None,
                         tuple(changes), tuple(eligible), tuple(ineligible))
