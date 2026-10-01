"""E4 sections 7 to 10 assembled: one run over a built table, with every secondary analysis and the tables.

`analyze` performs no I/O. The registered run (X.4) passes master seed 1927, the registered streams and
`allow_registered=True` from a tool that has verified the gates; every other call is a development run.
Nothing here decides the outcome wording (section 11) or applies DR-2: `holm_input` is what this
extension would enter (its raw p, or 1 when it is not estimable or failed).
"""
from __future__ import annotations

import numpy as np

from uc_core import surrogate as s
from uc_core.secondary import episode_percentile_interval
from uc_core.validation_runner import serial
from uc_ext import common as c

from .descriptive import real_time_against_final, two_clocks
from .procedure import EpisodeInput, compare, measure
from .streams import Streams, check_run, stream_rng
from .vintage import DEFAULT_WINDOW, select_episodes

SURROGATE_ATTEMPTS = 1000
EPISODE_RESAMPLES = 10000


def _run(selections, master_seed, stream, *, window, B, kind="residual", comparators=False, registered=False):
    """One §§6-9 comparison over the E4-eligible episodes of `selections` (generator of j: stream, j, 0)."""
    episodes = [EpisodeInput(sel.j, sel.series.growth) for sel in selections if sel.status == "eligible"]
    rngs = {e.j: stream_rng(master_seed, stream, e.j, 0, allow_registered=registered) for e in episodes}
    return compare(episodes, rngs, window=window, B=B, kind=kind, comparators=comparators)


def analyze(tables, h1_episodes, *, master_seed, streams: Streams, allow_registered=False,
            B=SURROGATE_ATTEMPTS, interval_B=EPISODE_RESAMPLES, release_dates=None) -> dict:
    registered = check_run(master_seed, streams, allow_registered)
    B = s._integer(B, "B")
    interval_B = s._integer(interval_B, "interval_B")
    sel40 = select_episodes(tables, h1_episodes, DEFAULT_WINDOW)
    sel32 = select_episodes(tables, h1_episodes, 32)
    sel48 = select_episodes(tables, h1_episodes, 48)
    primary = _run(sel40, master_seed, streams.primary, window=40, B=B, comparators=True, registered=registered)
    win32 = _run(sel32, master_seed, streams.window32, window=32, B=B, registered=registered)
    win48 = _run(sel48, master_seed, streams.window48, window=48, B=B, registered=registered)
    wild = _run(sel40, master_seed, streams.wild, window=40, B=B, kind="wild", registered=registered)
    eligible = [sel for sel in sel40 if sel.status == "eligible"]
    per_episode = {sel.j: measure(sel.series.growth, window=40)["primary"] for sel in eligible}
    deltas = {j: v[1] for j, v in per_episode.items() if v[0] == "ok"}
    obs = primary.primary.observed
    if not eligible:
        interval = dict(status="no_eligible_episode", interval=None)
    elif obs.status == "failed":
        interval = dict(status="observed_statistic_failed", interval=None, error=obs.error)   # H1 section 8
    else:
        interval = serial(episode_percentile_interval(
            obs.components, rng=stream_rng(master_seed, streams.interval, 0, 0, allow_registered=registered),
            B=interval_B))
    rows = [c.comparison_row("primary (W = 40, fixed dates per vintage)", serial(primary.primary), 40),
            c.comparison_row("W = 32", serial(win32.primary), 32),
            c.comparison_row("W = 48", serial(win48.primary), 48),
            c.comparison_row("wild signs (W = 40)", serial(wild.primary), 40),
            c.comparison_row("Kendall trend (W = 40)", serial(primary.trend), 40),
            c.comparison_row("lag-one comparator (W = 40)", serial(primary.lag1), 40)]
    p = primary.primary
    status = ("not_estimable" if not eligible else
              "ok" if p.status == "ok" else "failed")
    return dict(
        run=dict(registered=registered, master_seed=int(master_seed), streams=serial(streams), B=B,
                 interval_B=interval_B, label="registered run" if registered else "development run"),
        status=status,
        m_E4=len(eligible),
        S_rt=obs.value, k=sum(v > 0 for v in obs.components) if obs.components else None,
        raw_p=p.p_value, raw_p_label=p.p_label, holm_input=p.p_value if (status == "ok" and p.p_value) else 1.0,
        selections=serial(sel40), selections_w32=serial(sel32), selections_w48=serial(sel48),
        comparisons=dict(primary=primary, window32=win32, window48=win48, wild=wild),
        secondary_table=rows, episode_interval=interval,
        real_time_against_final=real_time_against_final(sel40, deltas, release_dates, tables),
        two_clocks=two_clocks(tables, sel40, release_dates),
        manifest=tables.manifest)
