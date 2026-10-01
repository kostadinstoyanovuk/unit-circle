"""The E4 report and retained record: every section 8-10 number, table and figure from uc_e4.analysis.analyze,
and what Annex B of prereg/E4.md retains (X.4).

Tables (CSV; every row carries the data kind; a blank cell is unavailable, not zero; lists are JSON):
  episodes.csv                 one row per H1 eligible episode at W = 40: the selection, with the failed step
                               where the episode is unavailable, v_j and the vintage before it, n_v, the signed
                               Delta_rt, Delta_final and their difference (sections 7, 8 and 10)
  selections.csv               every vintage selection at W = 40, 32 and 48 (section 7; section 10)
  comparisons.csv              the primary and the five secondary comparisons with m, k, K, B', q, the Wilson
                               interval and the raw p labelled "raw, not family-adjusted" (sections 9 and 10)
  episode-interval.csv         the episode interval (section 10, as H1 section 7)
  real-time-against-final.csv  and real-time-summary.csv (section 10)
  two-clocks.csv               the two clocks (section 10; SD-07)
  availability.csv             the kind of every cell: reference quarters by vintages in vintage order (Annex B)
  availability-counts.csv      cells of each kind per vintage (section 4, step 2)
  availability-markers.csv     every marker cell and its content (a marker holds no digit)
  rolling.csv                  rolling fits and indicators of every compared vintage series (H1 section 12)
  primary-surrogates.csv       every primary attempt: status, S_b and each episode's Delta_b (section 9)
JSON:
  vintage-series.json          every vintage series selected (section 5): its run, its growth and the SHA-256
                               of the levels of its run
  null-models.json             the fitted null and centred residuals of every compared vintage series (Annex B)
  report.json                  the tables above except availability.csv, rolling.csv and the two JSON files,
                               with the outcome at freeze (section 11)
Figures (svg, png and pdf with fixed metadata): `realtime`, the real-time and final-data changes of every
episode with their signs, and `surrogates`, the primary S_b with S_rt marked. Both are drawn, with a note, when
no episode is E4-eligible.

No level is written. Each selected vintage series is retained as its growth (section 5; Annex B "every vintage
selection"), with the first and last quarter of its run and the SHA-256 of the run's levels (little-endian
float64), which ties it to the acquired workbook without repeating the workbook's numbers. The primary
Delta_rt of every E4-eligible episode is re-derived from the rolling modulus path of its vintage series, and the
fitted null of every compared series is re-derived with uc_core.surrogate.prepare_null; the report refuses to
be written if either disagrees with the analysis.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from uc_core import surrogate
from uc_core.rolling import max_modulus, rolling_ar2
from uc_core.secondary import rolling_lag1
from uc_core.validation_runner import serial
from uc_e4.table import availability_report, quarter_from_index, quarter_index, quarter_text
from uc_e4.vintage import DEFAULT_WINDOW, LOOKBACK, minimum_growth

from . import gates, records, report_common as rc, x4

TITLE = dict(registered="UK real GDP in the first vintage containing the quarter before onset (ONS ABMI), E4",
             constructed="Small-B run on constructed data - no UK observations")
CONSTRUCTED_KIND = "constructed_tables_small_b_run"
SALT = "e4-registered-report"
SELECTION_KEYS = {40: "selections", 32: "selections_w32", 48: "selections_w48"}
COMPARISON_NAMES = dict(primary="primary (W = 40)", window32="W = 32", window48="W = 48", wild="wild signs (W = 40)")
NUMERIC_ERRORS = (ValueError, FloatingPointError, np.linalg.LinAlgError)
NULL_FIELDS = ("coefficients", "intercept", "initial", "residuals", "residual_mean_removed", "modulus")


def data_kind(*, registered: bool) -> str:
    """The data kind written in every output: the registered E4 data, or a small-B run on constructed data."""
    return x4.REGISTERED_KIND["e4"] if registered else CONSTRUCTED_KIND


def _q(value):
    return None if value is None else quarter_text(value)


def _sign(value):
    if value is None:
        return None
    return "positive" if value > 0 else "negative" if value < 0 else "zero"


def growth_quarters(series: dict) -> list:
    """Quarter of each growth position: position n_v - 1 is q_j - 1 (section 5)."""
    last = quarter_index(series["last_quarter"])
    return [quarter_text(quarter_from_index(last - series["n_v"] + 1 + i)) for i in range(series["n_v"])]


def run_levels_sha256(tables, series: dict):
    """SHA-256 of the levels of the run of one selected vintage series (section 5) as little-endian float64, in
    quarter order; None when the series has no run. The levels themselves are not returned."""
    if series.get("first_quarter") is None:
        return None
    av, lv = tables.availability, tables.levels
    first, last = quarter_index(series["first_quarter"]), quarter_index(series["last_quarter"])
    levels = np.array([lv.level(series["vintage"], av.row(quarter_from_index(i))) for i in range(first, last + 1)],
                      dtype="<f8")
    return gates.sha256_bytes(levels.tobytes())


# ------------------------------------------------------------------------------------ tables

def selection_rows(results) -> list:
    rows = []
    for window, key in SELECTION_KEYS.items():
        for sel in results[key]:
            series = sel.get("series") or {}
            rows.append(dict(window=window, minimum_n_v=minimum_growth(window), j=sel["j"], onset=_q(sel["onset"]),
                             reference_quarter=_q(series.get("last_quarter")), status=sel["status"],
                             failed_step=sel["failed_step"], reason=sel["reason"], vintage=sel["vintage_label"],
                             vintage_number=sel["vintage"], previous_vintage=sel["previous_vintage_label"],
                             first_quarter=_q(series.get("first_quarter")), run_ended_by=series.get("run_ended_by"),
                             n_levels=series.get("n_levels"), n_v=series.get("n_v"), series_status=series.get("status"),
                             stop=series.get("stop"), stop_note=sel.get("stop_note")))
    return rows


def episode_rows(results) -> list:
    """One row per H1 eligible episode at W = 40 (sections 7, 8 and 10)."""
    by_j = {sel["j"]: sel for sel in results["selections"]}
    rows = []
    for row in results["real_time_against_final"]["rows"]:
        sel = by_j[row["j"]]
        statistic = ("unavailable" if row["status"] != "eligible" else "ok" if row["delta_rt"] is not None
                     else "failed")
        rows.append(dict(j=row["j"], onset=row["onset"], reference_quarter=_q((sel.get("series") or {}).get(
            "last_quarter")), status=row["status"], failed_step=row["failed_step"], reason=row["reason"],
            vintage=row["vintage"], previous_vintage=sel["previous_vintage_label"], release_date=row["release_date"],
            release_basis=row["release_basis"], n_v=row["n_v"], statistic=statistic, delta_rt=row["delta_rt"],
            delta_rt_sign=_sign(row["delta_rt"]), delta_final=row["delta_final"],
            delta_final_sign=_sign(row["delta_final"]), difference=row["difference"]))
    return rows


def interval_row(interval: dict) -> dict:
    bounds = interval.get("interval")
    return dict(status=interval.get("status"), lower=bounds[0] if bounds else None, upper=bounds[1] if bounds else None,
                episodes=interval.get("episode_count"), requested=interval.get("requested"),
                attempted=interval.get("attempted"),
                note=("single episode: the interval is degenerate (H1 section 7)"
                      if interval.get("status") == "single_episode" else None),
                error=interval.get("error"))


def availability_rows(tables) -> tuple[list, list]:
    av = tables.availability
    columns = [f"{k:03d} {v.label}" for k, v in enumerate(av.vintages)]
    rows = [dict(reference_quarter_label=av.quarter_labels[r], reference_quarter=quarter_text(av.quarters[r]),
                 **{columns[k]: str(av.kinds[r, k]) for k in range(len(av.vintages))})
            for r in range(len(av.quarters))]
    return rows, ["reference_quarter_label", "reference_quarter", *columns]


def surrogate_rows(primary: dict, episodes: int) -> list:
    rows = []
    for attempt in primary.get("attempts") or []:
        changes = dict(zip(attempt.get("eligible_onsets") or [], attempt.get("changes") or []))
        rows.append(dict(number=attempt["number"], status=attempt["status"], statistic=attempt["statistic"],
                         **{f"delta_j{j}": changes.get(j) for j in range(episodes)}, error=attempt.get("error")))
    return rows


# ------------------------------------------------------------------ vintage series, nulls, rolling

def vintage_series_records(tables, results) -> list:
    """Every vintage series selected at W = 40 (the series does not depend on the window): its run, the SHA-256
    of the run's levels and its growth, as section 5 defines them. Episodes that failed step 7.1 or 7.2 have no
    series."""
    out = []
    for sel in results["selections"]:
        series = sel.get("series")
        if series is None:
            continue
        growth = series.get("growth")
        out.append(dict(j=sel["j"], onset=_q(sel["onset"]), status=sel["status"], failed_step=sel["failed_step"],
                        vintage=sel["vintage_label"], vintage_number=sel["vintage"],
                        first_quarter=_q(series.get("first_quarter")), last_quarter=_q(series.get("last_quarter")),
                        run_ended_by=series.get("run_ended_by"), n_levels=series.get("n_levels"),
                        n_v=series.get("n_v"), series_status=series.get("status"), stop=series.get("stop"),
                        levels_sha256=run_levels_sha256(tables, series),
                        growth_quarters=growth_quarters(series) if growth is not None else [],
                        growth=growth if growth is not None else []))
    return out


def compared(results) -> dict:
    """j -> growth series of every episode that is E4-eligible at one window or more (each is compared)."""
    series = {}
    for key in SELECTION_KEYS.values():
        for sel in results[key]:
            if sel["status"] == "eligible":
                series.setdefault(sel["j"], sel["series"]["growth"])
    return dict(sorted(series.items()))


def null_model_records(results) -> list:
    """The fitted null and centred residuals of every compared vintage series (Annex B), re-derived with the
    registered function and checked against every comparison that fitted it."""
    out = []
    for j, growth in compared(results).items():
        used = {name: comparison["null_models"][j] for name, comparison in results["comparisons"].items()
                if j in (comparison.get("null_models") or {})}
        try:
            model = serial(surrogate.prepare_null(growth))
            status, error = "ok", None
        except surrogate.NullModelError as exc:
            model, status, error = None, "failed", str(exc)
        for name, fitted in used.items():
            if model is None or any(fitted[field] != model[field] for field in NULL_FIELDS):
                raise ValueError(f"The fitted null of episode {j} differs from the one the {name} comparison used")
        record = dict(j=j, status=status, error=error, n_v=len(growth), rows=len(growth) - 2,
                      used_by=[COMPARISON_NAMES[name] for name in used])
        if model is not None:
            record.update(phi1=model["coefficients"][0], phi2=model["coefficients"][1], intercept=model["intercept"],
                          initial=model["initial"], modulus=model["modulus"],
                          residual_mean_removed=model["residual_mean_removed"], residuals=model["residuals"])
        out.append(record)
    return out


def rolling_records(results) -> tuple[list, list, dict]:
    """Rolling fits (W = 40), the modulus at W = 32 and 48 and the lag-one path (W = 40) of every compared series.
    Returns the rows, the failures, and j -> the W = 40 modulus path (None after a failure)."""
    rows, failures, paths = [], [], {}
    for j, growth in compared(results).items():
        values = np.asarray(growth, dtype=float)
        n_v = len(values)
        quarters = growth_quarters(dict(last_quarter=_last_quarter(results, j), n_v=n_v))
        try:
            fits = rolling_ar2(values, DEFAULT_WINDOW).to_dict("records")
            paths[j] = np.array([fit["modulus"] for fit in fits], dtype=float)
        except NUMERIC_ERRORS as error:
            fits, paths[j] = None, None
            failures.append(dict(j=j, path="rolling AR(2), W = 40", error=f"{type(error).__name__}: {error}"))
        extra = {}
        for name, function, window in (("modulus_w32", max_modulus, 32), ("modulus_w48", max_modulus, 48),
                                       ("lag1_w40", rolling_lag1, DEFAULT_WINDOW)):
            try:
                extra[name] = function(values, window).to_numpy()
            except NUMERIC_ERRORS as error:
                extra[name] = None
                failures.append(dict(j=j, path=name, error=f"{type(error).__name__}: {error}"))
        for i in range(n_v):
            fit = fits[i] if fits is not None else {}
            rows.append(dict(j=j, position=i, quarter=quarters[i], growth=float(values[i]),
                             intercept=fit.get("intercept"), phi1=fit.get("phi1"), phi2=fit.get("phi2"),
                             modulus=fit.get("modulus"),
                             status=fit.get("status") if fits is not None else "unavailable_after_failure",
                             **{name: (None if path is None else path[i]) for name, path in extra.items()}))
    return rows, failures, paths


def _last_quarter(results, j):
    for key in SELECTION_KEYS.values():
        for sel in results[key]:
            if sel["j"] == j and sel.get("series"):
                return sel["series"]["last_quarter"]
    raise ValueError(f"episode {j} has no vintage series")


def check_primary(results, paths) -> None:
    """Delta_rt = M(n_v - 1) - M(n_v - 9) of every E4-eligible episode, from its rolling modulus path, equals the
    analysis; a failed observed statistic must have a failed or non-finite path (section 7, step 4)."""
    observed = results["comparisons"]["primary"]["primary"]["observed"]
    eligible = [sel for sel in results["selections"] if sel["status"] == "eligible"]
    derived, broken = {}, []
    for sel in eligible:
        path, n_v = paths.get(sel["j"]), sel["series"]["n_v"]
        value = None if path is None else path[n_v - 1] - path[n_v - 1 - LOOKBACK]
        if value is None or not math.isfinite(value):
            broken.append(sel["j"])
        else:
            derived[sel["j"]] = float(value)
    if observed["status"] == "ok":
        if broken or list(observed["eligible_onsets"]) != list(derived) \
                or list(observed["components"]) != list(derived.values()) \
                or observed["value"] != float(np.mean(list(derived.values()))):
            raise ValueError("The primary result does not match the rolling paths of the vintage series")
        table = {row["j"]: row["delta_rt"] for row in results["real_time_against_final"]["rows"]
                 if row["status"] == "eligible"}
        if table != derived:
            raise ValueError("The real-time table does not match the rolling paths of the vintage series")
    elif observed["status"] == "failed" and not broken:
        raise ValueError("A failed observed statistic needs a failed or non-finite rolling path")


# ----------------------------------------------------------------------------------- figures

def realtime_figure(directory: Path, *, rows, m_E4, title, salt=SALT):
    """Real-time Delta_rt beside final-data Delta_final for every H1 eligible episode, each value signed."""
    plt = rc._pyplot(salt)
    fig, ax = plt.subplots(figsize=(10, 4.5), layout="constrained")
    x = np.arange(len(rows), dtype=float)
    width = 0.38
    series = (("delta_rt", -width / 2, rc.COLOURS["path"],
               "Real time: Delta_rt in v_j, the first vintage containing q_j - 1"),
              ("delta_final", width / 2, rc.COLOURS["second"], "Final data: Delta_final (frozen H1 record)"))
    for key, offset, colour, label in series:
        present = [(position, row[key]) for position, row in zip(x, rows) if row[key] is not None]
        ax.bar([p + offset for p, _ in present], [v for _, v in present], width, color=colour, label=label)
        for position, value in present:
            ax.text(position + offset, value, f"{value:+.4f}", ha="center", va="bottom" if value >= 0 else "top",
                    fontsize=8)
    for position, row in zip(x, rows):
        if row["delta_rt"] is None:
            why = (f"unavailable\n(step {row['failed_step']})" if row["status"] != "eligible"
                   else "statistic\nfailed")
            ax.text(position - width / 2, 0, why, ha="center", va="bottom", fontsize=7, color=rc.COLOURS["second"])
    ax.axhline(0, color=rc.COLOURS["second"], linewidth=.8)
    ax.set_xticks(x, [f"{row['onset']}\nv_j: {row['vintage'] or 'none'}" for row in rows])
    ax.set_xlim(-.7, len(rows) - .3)
    ax.set(ylabel="Pre-onset change M(n_v - 1) - M(n_v - 9)", title=title)
    if not m_E4:
        ax.text(.5, .97, "No E4-eligible episode (m_E4 = 0): E4 is not estimable; final-data changes shown",
                ha="center", va="top", transform=ax.transAxes, fontsize=9)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    rc._save(fig, directory, "realtime")
    plt.close(fig)


def surrogate_figure(directory: Path, *, retained, row, m_E4, title, salt=SALT):
    """The primary S_b (fixed dates per vintage) with the observed S_rt marked."""
    plt = rc._pyplot(salt)
    fig, ax = plt.subplots(figsize=(10, 4.5), layout="constrained")
    if retained:
        ax.hist(retained, bins=40, color=rc.COLOURS["histogram"], edgecolor="#fcfcfb",
                label="Retained surrogate statistics S_b (fixed dates per vintage)")
    else:
        ax.text(.5, .5, "No retained surrogate distribution" +
                ("\n(no E4-eligible episode: m_E4 = 0)" if not m_E4 else ""),
                ha="center", va="center", transform=ax.transAxes)
    if row.get("value") is not None:
        ax.axvline(row["value"], color=rc.COLOURS["observed"], linewidth=1.8,
                   label=f"Observed S_rt = {row['value']:.4f}")
    ax.set(xlabel="Mean real-time pre-onset change (modulus units)", ylabel="Count", title=title)
    if retained or row.get("value") is not None:
        ax.legend(loc="upper left", fontsize=8)
    p = row.get("p_value")
    ax.text(.99, .96, (f"p = {p:.4f} (raw, not family-adjusted)\nretained {row.get('retained')} of "
                       f"{row.get('attempted')}; m_E4 = {m_E4}") if p is not None
            else f"Status: {row.get('status')}; m_E4 = {m_E4}", ha="right", va="top", transform=ax.transAxes,
            fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    rc._save(fig, directory, "surrogates")
    plt.close(fig)


# ------------------------------------------------------------------------------------ report

def assemble(tables, result, *, input_record, input_sha256, D80) -> dict:
    results = serial(result)
    episodes = len(results["selections"])
    rows = results["secondary_table"]
    primary = results["comparisons"]["primary"]["primary"]
    rolling, rolling_failures, paths = rolling_records(results)
    check_primary(results, paths)
    nulls = null_model_records(results)
    episode_table = episode_rows(results)
    deltas = [dict(j=row["j"], onset=row["onset"], delta_rt=row["delta_rt"]) for row in episode_table
              if row["status"] == "eligible"]
    interval = results["episode_interval"]
    availability = availability_report(tables.availability)
    head = rows[0]
    return dict(
        status=results["status"], m_E4=results["m_E4"], comparisons=rows,
        primary=dict(S_rt=results["S_rt"], k=results["k"], m_E4=results["m_E4"],
                     k_over_m=f"{results['k']}/{results['m_E4']}" if results["k"] is not None else None,
                     raw_p=results["raw_p"], p_label=results["raw_p_label"], K=head["exceedances"],
                     B_prime=head["B_prime"], q=head["q"], q_wilson=head["q_wilson"], status=head["status"],
                     holm_input=results["holm_input"]),
        episodes=episode_table, selections=selection_rows(results),
        episode_interval={k: v for k, v in interval.items() if k not in ("draw_means", "rng_before", "rng_after")},
        real_time_against_final=results["real_time_against_final"], two_clocks=results["two_clocks"],
        availability_summary=dict(structure=results["manifest"], kinds_total=availability["kinds_total"],
                                  per_vintage=availability["per_vintage"],
                                  marker_cells=availability["marker_cells"]),
        null_models=[{k: v for k, v in record.items() if k != "residuals"} for record in nulls],
        rolling_failures=rolling_failures, primary_surrogates=surrogate_rows(primary, episodes),
        run=results["run"], input=input_record, input_sha256=input_sha256,
        interpretation=x4.interpretation("e4", head, interval, D80, details=dict(deltas=deltas)),
        _rolling=rolling, _nulls=nulls, _series=vintage_series_records(tables, results))


def write_report(directory, *, tables, result, input_record, input_sha256, D80, data_kind, metadata):
    """Write report/ for a registered run, a recomputation or a labelled small-B run on constructed data;
    returns the manifest. Nothing is written if the report cannot be assembled."""
    if data_kind not in (x4.REGISTERED_KIND["e4"], CONSTRUCTED_KIND):
        raise ValueError("Unknown E4 report kind")
    directory = Path(directory)
    report = assemble(tables, result, input_record=input_record, input_sha256=input_sha256, D80=D80)
    rolling, nulls, series = report.pop("_rolling"), report.pop("_nulls"), report.pop("_series")
    directory.mkdir(parents=True, exist_ok=False)
    rc.labelled_csv(directory / "comparisons.csv", report["comparisons"], rc.comparison_fields(), data_kind)
    rc.labelled_csv(directory / "episodes.csv", report["episodes"],
                    ["j", "onset", "reference_quarter", "status", "failed_step", "reason", "vintage",
                     "previous_vintage", "release_date", "release_basis", "n_v", "statistic", "delta_rt",
                     "delta_rt_sign", "delta_final", "delta_final_sign", "difference"], data_kind)
    rc.labelled_csv(directory / "selections.csv", report["selections"],
                    ["window", "minimum_n_v", "j", "onset", "reference_quarter", "status", "failed_step", "reason",
                     "vintage", "vintage_number", "previous_vintage", "first_quarter", "run_ended_by", "n_levels",
                     "n_v", "series_status", "stop", "stop_note"], data_kind)
    rc.labelled_csv(directory / "episode-interval.csv", [interval_row(report["episode_interval"])],
                    ["status", "lower", "upper", "episodes", "requested", "attempted", "note", "error"], data_kind)
    rtf = report["real_time_against_final"]
    rc.labelled_csv(directory / "real-time-against-final.csv", rtf["rows"],
                    ["j", "onset", "status", "failed_step", "reason", "vintage", "release_date", "release_basis",
                     "n_v", "delta_rt", "delta_final", "difference"], data_kind)
    rc.labelled_csv(directory / "real-time-summary.csv", [dict(rtf["summary"], note=rtf["note"])],
                    ["m_E4", "S_rt", "S_final_m", "mean_difference", "same_sign", "note"], data_kind)
    clocks = report["two_clocks"]
    rc.labelled_csv(directory / "two-clocks.csv", [dict(row, note=clocks["note"]) for row in clocks["rows"]],
                    ["j", "onset", "reference_quarter", "vintage", "release_date", "release_month", "release_basis",
                     "onset_quarter_ends", "release_before_end_of_onset_quarter", "previous_vintage",
                     "previous_release_month", "months_since_previous", "first_vintage_showing_the_onset", "note"],
                    data_kind)
    grid, fields = availability_rows(tables)
    rc.labelled_csv(directory / "availability.csv", grid, fields, data_kind)
    summary = report["availability_summary"]
    rc.labelled_csv(directory / "availability-counts.csv",
                    [dict(row, k=k) for k, row in enumerate(summary["per_vintage"])],
                    ["k", "vintage", "release_month", "numeric", "empty", "marker", "other"], data_kind)
    rc.labelled_csv(directory / "availability-markers.csv", summary["marker_cells"], ["vintage", "quarter", "content"],
                    data_kind)
    rc.labelled_csv(directory / "rolling.csv", rolling,
                    ["j", "position", "quarter", "growth", "intercept", "phi1", "phi2", "modulus", "status",
                     "modulus_w32", "modulus_w48", "lag1_w40"], data_kind)
    episodes = len(report["episodes"])
    rc.labelled_csv(directory / "primary-surrogates.csv", report["primary_surrogates"],
                    ["number", "status", "statistic", *[f"delta_j{j}" for j in range(episodes)], "error"], data_kind)
    records.write_once(directory / "vintage-series.json", records.pretty(dict(
        data_kind=data_kind, note=("Each selected vintage series: its run, the SHA-256 of the run's levels "
                                   "(little-endian float64) and its growth g[t] = 400*(ln Y[t] - ln Y[t-1]) "
                                   "(prereg/E4.md section 5). No level is written."), series=series)))
    records.write_once(directory / "null-models.json", records.pretty(dict(
        data_kind=data_kind, note=("Intercept-inclusive OLS AR(2) fitted to all n_v growth values of each compared "
                                   "vintage series (n_v - 2 rows), strictly stable, with its centred residuals "
                                   "(prereg/E4.md section 9)."), null_models=nulls)))
    title = TITLE["registered" if data_kind == x4.REGISTERED_KIND["e4"] else "constructed"]
    realtime_figure(directory, rows=report["episodes"], m_E4=report["m_E4"], title=title)
    surrogate_figure(directory, retained=[r["statistic"] for r in report["primary_surrogates"]
                                          if r["status"] == "retained"],
                     row=report["comparisons"][0], m_E4=report["m_E4"], title=title)
    return rc.finish(directory, report=report, analysis_report_rows=report["comparisons"], data_kind=data_kind,
                     metadata=metadata, interpretation=report["interpretation"])
