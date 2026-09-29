"""The E3 report: every section 8-10 number, table and figure from uc_ext.e3.analyze (Annex B X.4).

Tables: comparisons (primary, held fixed, fixed dates, wild signs, Kendall; m, k, K, B', q, Wilson and
the raw p labelled "raw, not family-adjusted"), episodes and qualifying runs (H1 rules), the filtered
states a(t|t) for t = 2..258 with the filtered M(t) beside H1's rolling M(t) (W = 40), the observed
likelihood grid, and every primary surrogate attempt. Descriptive: sigma2, r1, r2, q1, q2 with their
boundary flags and l(r) - l(0, 0) (no chi-squared p). Every surrogate's fit (grid, refinement, flags)
is retained in the run's surrogate-fits.json.gz (Annex B). The primary result is re-derived from the
filtered path and the episodes, and the report refuses to be written if they disagree.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from uc_core.recession import episodes, pre_onset_changes
from uc_core.rolling import max_modulus
from uc_core.validation_runner import serial

from . import gates, report_common as rc, x4

TITLE = dict(registered="UK real GDP growth, 1955Q2-2019Q4 (ONS ABMI): time-varying AR(2), E3",
             rehearsal="Artificial pipeline rehearsal - no UK observations")
NUMERIC_ERRORS = (ValueError, FloatingPointError, np.linalg.LinAlgError)


def assemble(growth, labels, result, *, D80):
    from uc_ext import e3
    values = np.asarray(growth, dtype=float)
    labels = tuple(labels)
    if values.ndim != 1 or len(values) != len(labels):
        raise ValueError("One quarter label is required per growth observation")
    results = serial(result)
    if results.get("input_sha256") != gates.sha256_bytes(values.astype("<f8").tobytes()):
        raise ValueError("The analysis input hash does not match the supplied growth series")
    rows = results["report"]["rows"]
    primary = results["joint"]["primary"]["observed"]
    changes = dict(zip(primary.get("eligible_onsets") or [], primary.get("components") or []))
    grouped = episodes(values, minimum_run=e3.MINIMUM_RUN, merge=e3.MERGE)
    episode_rows, run_rows = [], []
    for number, episode in enumerate(grouped):
        episode_rows.append(dict(episode=number, onset=episode.onset, onset_quarter=labels[episode.onset],
                                 end=episode.end, end_quarter=labels[episode.end], qualifying_runs=len(episode.runs),
                                 structurally_eligible=episode.onset >= e3.FIRST_ELIGIBLE,
                                 statistic_available=episode.onset in changes, change=changes.get(episode.onset)))
        run_rows += [dict(episode=number, onset=run.onset, onset_quarter=labels[run.onset], end=run.end,
                          end_quarter=labels[run.end]) for run in episode.runs]
    descriptive = results.get("descriptive")
    rolling_error = None
    try:
        rolling = max_modulus(values, e3.FIRST_INDICATOR + 1).to_numpy()
    except NUMERIC_ERRORS as error:
        rolling, rolling_error = np.full(len(values), np.nan), f"{type(error).__name__}: {error}"
    states = (descriptive or {}).get("filtered_states")
    modulus = (descriptive or {}).get("filtered_modulus")
    filtered = []
    for t in range(len(values)):
        state = states[t - 2] if states is not None and t >= 2 else [None, None, None]
        filtered.append(dict(position=t, quarter=labels[t], growth=float(values[t]), c=state[0], phi1=state[1],
                             phi2=state[2], modulus=modulus[t] if modulus is not None else None,
                             h1_rolling_modulus=rolling[t],
                             status=("indicator" if modulus is not None and t >= e3.FIRST_INDICATOR else
                                     "warm-up" if modulus is not None else "unavailable_after_failure")))
    if primary["status"] == "ok":
        if modulus is None:
            raise ValueError("A successful primary result needs the observed filtered path")
        check = pre_onset_changes(np.array([np.nan if v is None else v for v in modulus]),
                                  [e.onset for e in grouped], lookback=e3.LOOKBACK)
        if (check.mean_change != primary["value"] or list(check.changes) != primary["components"]
                or list(check.eligible_onsets) != primary["eligible_onsets"]):
            raise ValueError("The primary result does not match the filtered path and the episodes")
    fit = results["joint"].get("observed_fit") or {}
    grid = [dict(r1=e3.GRID[i], r2=e3.GRID[j], loglik=value)
            for i, row in enumerate(fit.get("grid_loglik") or []) for j, value in enumerate(row)]
    summary = None
    if descriptive is not None:
        summary = {k: v for k, v in descriptive.items() if k not in ("filtered_states", "filtered_modulus")}
        summary.update(grid_max=fit.get("grid_max"), refinement=fit.get("refinement"), accepted=fit.get("accepted"),
                       grid_point_failure=fit.get("grid_point_failure"),
                       grid_filter_failures=fit.get("grid_filter_failures"), engine=results.get("engine"))
    interval = results["episode_interval"]
    return dict(comparisons=rows, report_quantities={k: v for k, v in results["report"].items() if k != "rows"},
                episodes=episode_rows, qualifying_runs=run_rows, filtered=filtered, rolling_error=rolling_error,
                likelihood_grid=grid, descriptive=summary,
                observed_fit_status=dict(status=fit.get("status"), error=fit.get("error"),
                                         fit_error=results["joint"].get("fit_error")),
                primary_surrogates=rc.surrogate_rows(results["joint"]["primary"]),
                episode_interval=interval, input_sha256=results["input_sha256"],
                interpretation=x4.interpretation("e3", rows[0], interval, D80))


def write_report(directory, *, growth, labels, result, D80, data_kind, metadata):
    """Write report/ for a registered run or a labelled artificial rehearsal; returns the manifest."""
    from uc_ext import e3
    if data_kind not in (x4.REGISTERED_KIND["e3"], x4.REHEARSAL_KIND):
        raise ValueError("Unknown E3 report kind")
    directory = Path(directory)
    report = assemble(growth, labels, result, D80=D80)
    directory.mkdir(parents=True, exist_ok=False)
    rc.labelled_csv(directory / "comparisons.csv", report["comparisons"], rc.comparison_fields(), data_kind)
    rc.labelled_csv(directory / "episodes.csv", report["episodes"],
                    ["episode", "onset", "onset_quarter", "end", "end_quarter", "qualifying_runs",
                     "structurally_eligible", "statistic_available", "change"], data_kind)
    rc.labelled_csv(directory / "qualifying-runs.csv", report["qualifying_runs"],
                    ["episode", "onset", "onset_quarter", "end", "end_quarter"], data_kind)
    rc.labelled_csv(directory / "filtered.csv", report["filtered"],
                    ["position", "quarter", "growth", "c", "phi1", "phi2", "modulus", "h1_rolling_modulus", "status"],
                    data_kind)
    rc.labelled_csv(directory / "likelihood-grid.csv", report["likelihood_grid"], ["r1", "r2", "loglik"], data_kind)
    rc.labelled_csv(directory / "primary-surrogates.csv", report["primary_surrogates"],
                    ["number", "status", "statistic", "eligible_episodes", "error"], data_kind)
    registered = data_kind != x4.REHEARSAL_KIND
    title = TITLE["registered" if registered else "rehearsal"]
    spans = [(row["onset"], row["end"], "Recession episode (two or more negative quarters, merged)",
              rc.COLOURS["eligible"], .15) for row in report["episodes"]]
    rc.persistence_figure(directory, x=[row["position"] for row in report["filtered"]],
                          paths=[([row["modulus"] if row["status"] == "indicator" else None for row in report["filtered"]],
                                  "Filtered time-varying AR(2) modulus M(t)", rc.COLOURS["path"]),
                                 ([row["h1_rolling_modulus"] for row in report["filtered"]],
                                  "H1 rolling AR(2) modulus, W = 40", rc.COLOURS["second"])],
                          spans=spans, xlabel="Quarter", title=title, salt="e3-registered-report",
                          ticks=[(row["position"], row["quarter"][:4]) for row in report["filtered"]
                                 if row["quarter"].endswith("Q1") and row["quarter"][:4].isdigit()
                                 and int(row["quarter"][:4]) % 10 == 0],
                          note=("Filtered indicator unavailable: fit failure" if report["descriptive"] is None
                                else None))
    rc.surrogate_figure(directory, retained=[r["statistic"] for r in report["primary_surrogates"]
                                             if r["status"] == "retained"],
                        row=report["comparisons"][0], title=title, salt="e3-registered-report")
    return rc.finish(directory, report=report, analysis_report_rows=report["comparisons"], data_kind=data_kind,
                     metadata=metadata, interpretation=report["interpretation"])
