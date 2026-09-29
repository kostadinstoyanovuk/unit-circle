"""Tables, figures and the report manifest shared by the E1 and E3 reports.

Every CSV row carries the data kind (registered data or an artificial rehearsal); a blank cell means
unavailable, not zero, and lists are written as JSON. Figures use fixed metadata so that each file is
byte-reproducible (as uc_core.h1_reporting does for H1).
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

from uc_core.h1_reporting import _figure_metadata

from . import gates, records

COLOURS = dict(path="#2a78d6", second="#52514e", eligible="#52514e", exogenous="#eb6834", ineligible="#a7bac8",
               histogram="#a7bac8", observed="#eb6834")


def cell(value):
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(records.json_safe(value), separators=(",", ":"))
    return value


def labelled_csv(path: Path, rows, fields, data_kind: str) -> None:
    with Path(path).open("x", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["data_kind", *fields], lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(data_kind=data_kind, **{key: cell(row.get(key)) for key in fields}))


def _save(fig, directory: Path, stem: str):
    for extension in ("png", "svg", "pdf"):
        fig.savefig(directory / f"{stem}.{extension}", dpi=200, metadata=_figure_metadata(extension))


def _pyplot(salt: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["svg.hashsalt"] = salt
    return plt


def persistence_figure(directory: Path, *, x, paths, spans, xlabel, title, salt, xlim=None, note=None, ticks=None):
    """M(t) path(s) with episodes shaded by kind. paths: [(values, label, colour)];
    spans: [(start, end, kind label, colour, alpha)] in x units, each kind labelled once."""
    plt = _pyplot(salt)
    fig, ax = plt.subplots(figsize=(10, 4.5), layout="constrained")
    for values, label, colour in paths:
        ax.plot(x, [np.nan if v is None else v for v in values], color=colour, linewidth=1.5, label=label)
    labelled = set()
    for start, end, kind, colour, alpha in spans:
        ax.axvspan(start - .5, end + .5, color=colour, alpha=alpha, label=None if kind in labelled else kind)
        labelled.add(kind)
    ax.axhline(1, color=COLOURS["second"], linewidth=.8, linestyle=":", label="Unit modulus")
    if xlim:
        ax.set_xlim(*xlim)
    if ticks:
        ax.set_xticks([position for position, _ in ticks], [label for _, label in ticks])
    ax.set(xlabel=xlabel, ylabel="Largest root modulus M(t)", title=title)
    if note:
        ax.text(.5, .5, note, ha="center", va="center", transform=ax.transAxes)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, directory, "persistence")
    plt.close(fig)


def surrogate_figure(directory: Path, *, retained, row, title, salt):
    """S against its retained surrogate distribution."""
    plt = _pyplot(salt)
    fig, ax = plt.subplots(figsize=(10, 4.5), layout="constrained")
    if retained:
        ax.hist(retained, bins=40, color=COLOURS["histogram"], edgecolor="#fcfcfb",
                label="Retained surrogate statistics S_b")
    else:
        ax.text(.5, .5, "No retained surrogate distribution", ha="center", va="center", transform=ax.transAxes)
    if row.get("value") is not None:
        ax.axvline(row["value"], color=COLOURS["observed"], linewidth=1.8, label=f"Observed S = {row['value']:.4f}")
    ax.set(xlabel="Mean pre-onset change S (modulus units)", ylabel="Count", title=title)
    if retained or row.get("value") is not None:
        ax.legend(loc="upper left", fontsize=8)
    p = row.get("p_value")
    ax.text(.99, .96, (f"p = {p:.4f} (raw, not family-adjusted)\nretained {row.get('retained')} of "
                       f"{row.get('attempted')}") if p is not None else f"Status: {row.get('status')}",
            ha="right", va="top", transform=ax.transAxes, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    _save(fig, directory, "surrogates")
    plt.close(fig)


def finish(directory: Path, *, report: dict, analysis_report_rows, data_kind, metadata, interpretation):
    """report.json, then manifest.json with the SHA-256 of every report file."""
    records.write_once(directory / "report.json", records.canonical(dict(data_kind=data_kind, result=report)) + b"\n")
    manifest = dict(data_kind=data_kind, metadata=metadata, input_sha256=report["input_sha256"],
                    interpretation=interpretation,
                    file_sha256={path.name: gates.sha256_file(path) for path in sorted(directory.iterdir())})
    records.write_once(directory / "manifest.json", records.canonical(manifest) + b"\n")
    return manifest


def comparison_fields():
    return ["analysis", "window", "status", "value", "m", "k", "p_value", "p_label", "requested", "attempted",
            "retained", "no_eligible", "failed", "exceedances", "B_prime", "p_grid_spacing", "q", "q_wilson", "error"]


def surrogate_rows(primary: dict):
    return [dict(number=a["number"], status=a["status"], statistic=a["statistic"],
                 eligible_episodes=len(a.get("eligible_onsets") or ()), error=a.get("error"))
            for a in primary.get("attempts") or []]
