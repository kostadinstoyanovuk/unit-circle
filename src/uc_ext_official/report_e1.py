"""The E1 report: every section 8-10 number, table and figure from uc_ext.e1.analyze (Annex B X.4).

Tables: comparisons (all seven rows with m, k, K, B', q, Wilson and the raw p labelled "raw, not
family-adjusted"), merged episodes with their runs, years and classification (eligible, ineligible,
exogenous) and signed Delta, qualifying runs, the exogenous descriptive table, the territory stretch of
each eligible episode's windows, the rolling fits (W = 30, and M(t) at W = 25 and 35) and every primary
surrogate attempt. Figure: the M(t) path 1730-2016 with eligible and exogenous episodes shaded
differently, and S against its retained surrogate distribution. The primary result is re-derived from
the rolling path and the episode record, and the report refuses to be written if they disagree.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from uc_core.recession import pre_onset_changes
from uc_core.rolling import max_modulus, rolling_ar2
from uc_core.validation_runner import serial

from . import gates, report_common as rc, x4

TITLE = dict(registered="UK annual real GDP growth, 1701-2016 (Bank of England millennium dataset, E1)",
             rehearsal="Artificial pipeline rehearsal - no E1 data")
NUMERIC_ERRORS = (ValueError, FloatingPointError, np.linalg.LinAlgError)


def assemble(growth, years, result, stretches, *, D80):
    from uc_ext import e1
    values = np.asarray(growth, dtype=float)
    years = tuple(int(y) for y in years)
    if values.ndim != 1 or len(values) != len(years):
        raise ValueError("One year label is required per growth observation")
    results = serial(result)
    if results.get("input_sha256") != gates.sha256_bytes(values.astype("<f8").tobytes()):
        raise ValueError("The analysis input hash does not match the supplied growth series")
    rows = results["report"]["rows"]
    episodes, episode_error = results["episodes"], None
    if isinstance(episodes, dict):
        episode_error, episodes = episodes.get("error"), []
    episode_rows, run_rows = [], []
    for number, episode in enumerate(episodes):
        episode_rows.append(dict(episode=number, onset=episode["onset"], end=episode["end"],
                                 onset_year=episode["onset_year"], end_year=episode["end_year"],
                                 qualifying_runs=len(episode["runs"]), classification=episode["classification"],
                                 delta=episode["delta"]))
        run_rows += [dict(episode=number, onset=a, end=b, onset_year=years[a], end_year=years[b])
                     for a, b in episode["runs"]]
    exogenous = [row for row in episode_rows if row["classification"] == "exogenous"]
    flags = e1.territory_flags(episodes, stretches) if stretches else []
    rolling_error, moduli = None, {}
    try:
        fitted = rolling_ar2(values, e1.WINDOW)
        for window in e1.SENSITIVITY_WINDOWS:
            moduli[window] = max_modulus(values, window).to_numpy()
        rolling = []
        for i, fit in enumerate(fitted.to_dict("records")):
            rolling.append(dict(position=i, year=years[i], growth=float(values[i]), intercept=fit["intercept"],
                                phi1=fit["phi1"], phi2=fit["phi2"], modulus=fit["modulus"], status=fit["status"],
                                **{f"modulus_w{w}": moduli[w][i] for w in e1.SENSITIVITY_WINDOWS}))
    except NUMERIC_ERRORS as error:
        rolling_error = f"{type(error).__name__}: {error}"
        rolling = [dict(position=i, year=years[i], growth=float(v), status="unavailable_after_failure")
                   for i, v in enumerate(values)]
    primary = results["joint"]["primary"]["observed"]
    if primary["status"] == "ok":
        if rolling_error is not None:
            raise ValueError("A successful primary result cannot be paired with a failed rolling path")
        onsets = [row["onset"] for row in episode_rows if row["classification"] != "exogenous"]
        check = pre_onset_changes(fitted["modulus"].to_numpy(), onsets, lookback=e1.LOOKBACK)
        if (check.mean_change != primary["value"] or list(check.changes) != primary["components"]
                or list(check.eligible_onsets) != primary["eligible_onsets"]):
            raise ValueError("The primary result does not match the rolling path and the episode record")
    interval = results["episode_interval"]
    return dict(comparisons=rows, report_quantities={k: v for k, v in results["report"].items() if k != "rows"},
                episodes=episode_rows, episode_error=episode_error, qualifying_runs=run_rows,
                exogenous_episodes=exogenous, territory_flags=flags, territory_stretches=stretches,
                rolling=rolling, rolling_error=rolling_error,
                primary_surrogates=rc.surrogate_rows(results["joint"]["primary"]),
                episode_interval=interval, input_sha256=results["input_sha256"],
                interpretation=x4.interpretation("e1", rows[0], interval, D80))


def write_report(directory, *, growth, years, result, stretches, D80, data_kind, metadata):
    """Write report/ for a registered run or a labelled artificial rehearsal; returns the manifest."""
    from uc_ext import e1
    if data_kind not in (x4.REGISTERED_KIND["e1"], x4.REHEARSAL_KIND):
        raise ValueError("Unknown E1 report kind")
    directory = Path(directory)
    report = assemble(growth, years, result, stretches, D80=D80)
    directory.mkdir(parents=True, exist_ok=False)
    rc.labelled_csv(directory / "comparisons.csv", report["comparisons"], rc.comparison_fields(), data_kind)
    episode_fields = ["episode", "onset", "onset_year", "end", "end_year", "qualifying_runs", "classification",
                      "delta"]
    rc.labelled_csv(directory / "episodes.csv", report["episodes"], episode_fields, data_kind)
    rc.labelled_csv(directory / "qualifying-runs.csv", report["qualifying_runs"],
                    ["episode", "onset", "onset_year", "end", "end_year"], data_kind)
    rc.labelled_csv(directory / "exogenous.csv", report["exogenous_episodes"], episode_fields, data_kind)
    rc.labelled_csv(directory / "territory-flags.csv", report["territory_flags"],
                    ["onset", "onset_year", "level_years", "territories", "crosses_boundary"], data_kind)
    rc.labelled_csv(directory / "rolling.csv", report["rolling"],
                    ["position", "year", "growth", "intercept", "phi1", "phi2", "modulus", "status",
                     *[f"modulus_w{w}" for w in e1.SENSITIVITY_WINDOWS]], data_kind)
    rc.labelled_csv(directory / "primary-surrogates.csv", report["primary_surrogates"],
                    ["number", "status", "statistic", "eligible_episodes", "error"], data_kind)
    registered = data_kind != x4.REHEARSAL_KIND
    title = TITLE["registered" if registered else "rehearsal"]
    first = e1.WINDOW - 1
    colours = dict(eligible=(rc.COLOURS["eligible"], .18), exogenous=(rc.COLOURS["exogenous"], .25),
                   ineligible=(rc.COLOURS["ineligible"], .2))
    names = dict(eligible="Eligible episode (one or more negative years, merged)",
                 exogenous="Exogenous-shock episode (onset 1914-18, 1939-45), excluded",
                 ineligible="Ineligible episode (M(r-3) unavailable)")
    spans = [(row["onset_year"], row["end_year"], names[row["classification"]],
              *colours[row["classification"]]) for row in report["episodes"]]
    rc.persistence_figure(directory, x=[row["year"] for row in report["rolling"]],
                          paths=[([row.get("modulus") for row in report["rolling"]],
                                  f"Rolling AR(2) modulus M(t), W = {e1.WINDOW}", rc.COLOURS["path"])],
                          spans=spans, xlabel="Year", title=title, salt="e1-registered-report",
                          xlim=(report["rolling"][first]["year"] - 1, report["rolling"][-1]["year"] + 1)
                          if len(report["rolling"]) > first else None,
                          note="Indicator unavailable: fitting failure" if report["rolling_error"] else None)
    rc.surrogate_figure(directory, retained=[r["statistic"] for r in report["primary_surrogates"]
                                             if r["status"] == "retained"],
                        row=report["comparisons"][0], title=title, salt="e1-registered-report")
    return rc.finish(directory, report=report, analysis_report_rows=report["comparisons"], data_kind=data_kind,
                     metadata=metadata, interpretation=report["interpretation"])
