"""E4 X.4: the one registered run over the real-time vintage tables, its retained record, and the small-B run
on constructed data (prereg/E4.md sections 7 to 10 and Annex B).

Registered mode. Every gate fails closed, in this order, and nothing is written before all have passed: code
location (uc_core, uc_ext, uc_ext_official and uc_e4 are the research root's own); G4 for E4 (published
registration, tag and protocol record); the committed X.3 record showing passed official synthetic checks;
frozen code (E4's code identity equals the one that ran X.3, and its E1 part equals E1's frozen code); the output
directory (the registered path, not yet existing, outside the tree or git-ignored); the X.2 data
(`e4_source.read_level_tables`, which repeats the gates and checks the committed edition, acquisition and mapping
records and the recorded availability); and the frozen H1 record `audit/H1_RESULT.json`, committed, whose four
eligible episodes are the registered onsets (`uc_e4.vintage.load_h1_episodes`). Only then is the output directory
created and `uc_e4.analysis.analyze` run with master seed 1927, the registered streams of Annex A, B = 1,000
attempts and 10,000 episode resamples; nothing can override them. A verification recomputation passes the same
gates, writes to its own directory, is labelled a recomputation and is never frozen (D-039).

The run directory holds run-log.json (with RUN_COMPLETE.json, the only file that carries a time), analysis.json
(everything `analyze` returns, canonical JSON, non-finite numbers as null), report/ (`report_e4`: tables, the
vintage series and fitted nulls with their residuals, figures, report.json and manifest.json with the SHA-256 of
every report file) and RUN_COMPLETE.json, written last with the SHA-256 of the log, analysis.json and the report
manifest, after which every output is re-read against those hashes (`x4.complete`). A run that stops leaves no
RUN_COMPLETE.json, and `x4.verify_outputs` and the freeze refuse such a directory.

The small-B run on constructed data runs the same chain on `uc_e4.table.Tables` built by the caller from
arbitrary numbers, with the development seed and streams and small counts, passes no gate, is labelled in every
output and can never be frozen.
"""
from __future__ import annotations

import datetime as dt
from datetime import datetime, timezone
from pathlib import Path
import time

import numpy as np

from uc_core.validation_runner import serial

from . import gates, records, run, x4

H1_RECORD = "audit/H1_RESULT.json"
SMALL_B_RUN = "small-B run on constructed data"


def table_hashes(tables) -> dict:
    """SHA-256 of the cell kinds and of the levels (little-endian float64, NaN where no level), as
    `e4_source.read_level_tables` records them, and the counts. No level is returned."""
    kinds = np.ascontiguousarray(tables.availability.kinds)
    levels = np.ascontiguousarray(tables.levels.levels, dtype="<f8")
    return dict(kinds_sha256=gates.sha256_bytes(kinds.tobytes()), levels_sha256=gates.sha256_bytes(levels.tobytes()),
                n_vintages=int(levels.shape[1]), n_reference_quarters=int(levels.shape[0]),
                numeric_cells=int(np.isfinite(levels).sum()))


def release_dates_from(mapping) -> dict:
    """Vintage label -> datetime.date from a mapping of label to ISO date text (or dates). Empty or None means
    that every release is stated by its label month only (R-10.5)."""
    out = {}
    for label, value in dict(mapping or {}).items():
        if isinstance(value, dt.datetime):
            value = value.date()
        if not isinstance(value, dt.date):
            value = dt.date.fromisoformat(str(value))
        out[str(label)] = value
    return out


def input_record(tables, h1_sha256: str, release_dates: dict) -> tuple[dict, str]:
    """The inputs of one run (table hashes, the H1 record's hash and the release dates) and their joint SHA-256."""
    record = dict(tables=table_hashes(tables), h1_record_sha256=h1_sha256,
                  release_dates={label: date.isoformat() for label, date in sorted(release_dates.items())})
    return record, gates.sha256_bytes(records.canonical(record))


def report_metadata(log: dict) -> dict:
    """What the report manifest repeats from the run log: everything except times and durations, so that the
    report of the same inputs is the same bytes."""
    return {key: value for key, value in log.items() if key not in ("started_utc", "finished_utc", "seconds")}


def _finish(output: Path, log: dict, started: float, *, tables, result, record, input_sha256, D80,
            data_kind) -> dict:
    from . import report_e4
    files = x4.write_analysis(output, "e4", result)
    manifest = report_e4.write_report(output / "report", tables=tables, result=result, input_record=record,
                                      input_sha256=input_sha256, D80=D80, data_kind=data_kind,
                                      metadata=report_metadata(log))
    log.update(finished_utc=datetime.now(timezone.utc).isoformat(), seconds=round(time.perf_counter() - started, 1))
    (output / "run-log.json").write_bytes(records.canonical(log) + b"\n")
    x4.complete(output, files)
    return manifest


def run_e4(root, output, *, recomputation=False, release_dates=None) -> dict:
    """The registered E4 run (or a labelled recomputation) after every gate; returns the report manifest."""
    from uc_e4 import analysis
    from uc_e4.streams import REGISTERED_STREAMS
    from uc_e4.vintage import load_h1_episodes
    from . import e4_source, report_e4
    root = Path(root)
    location = gates.check_code_location(root, "e4")
    gate = gates.check_registration(root, "e4")
    x3 = gates.check_x3(root, "e4")
    identity = gates.check_code_frozen(root, x3, "e4")
    output = run._output(root, output, "e4", recomputation)
    data = e4_source.read_level_tables(root)
    gates.check_committed(root, H1_RECORD)
    tables, summary = data["tables"], data["summary"]
    hashes = table_hashes(tables)
    if (hashes["kinds_sha256"], hashes["levels_sha256"]) != (summary["kinds_sha256"], summary["levels_sha256"]):
        raise gates.GateClosed("The vintage tables differ from the ones the X.2 reader recorded")
    episodes = load_h1_episodes(root / H1_RECORD)
    h1_sha256 = gates.sha256_file(root / H1_RECORD)
    dates = release_dates_from(release_dates)
    record, input_sha256 = input_record(tables, h1_sha256, dates)
    log = dict(kind=x4.RECOMPUTATION if recomputation else x4.PRIMARY_RUN, extension="E4",
               data_kind=x4.REGISTERED_KIND["e4"], started_utc=datetime.now(timezone.utc).isoformat(),
               commit=identity["identity"]["commit"], code_sha256=identity["code_sha256"],
               e1_code_sha256=identity.get("e1_code_sha256"), x3_record=x3["record_path"],
               x3_record_sha256=x3["record_sha256"], D80=x3["D80"], registration=gate,
               environment=identity["identity"], imported=identity["imported"],
               package_sources=gates.package_sources(root), code_location=location, master_seed=gates.REGISTERED_SEED,
               streams=serial(REGISTERED_STREAMS), B=analysis.SURROGATE_ATTEMPTS,
               interval_B=analysis.EPISODE_RESAMPLES, h1_record=H1_RECORD, h1_record_sha256=h1_sha256,
               tables=summary, input=record, input_sha256=input_sha256)
    output.mkdir(parents=True)
    (output / "run-log.json").write_bytes(records.canonical(log) + b"\n")   # rewritten when the run finishes
    started = time.perf_counter()
    result = analysis.analyze(tables, episodes, master_seed=gates.REGISTERED_SEED, streams=REGISTERED_STREAMS,
                              allow_registered=True, B=analysis.SURROGATE_ATTEMPTS,
                              interval_B=analysis.EPISODE_RESAMPLES, release_dates=dates)
    return _finish(output, log, started, tables=tables, result=result, record=record, input_sha256=input_sha256,
                   D80=x3["D80"], data_kind=report_e4.data_kind(registered=True))


def small_b_run_e4(tables, h1_episodes, output, *, B, interval_B, h1_sha256, release_dates=None,
                   master_seed=None) -> dict:
    """The whole X.4 chain on constructed tables with a development seed and streams and small counts (no gate,
    no record touched); every output is labelled a small-B run on constructed data. Returns the report manifest."""
    from uc_e4 import analysis
    from uc_e4.streams import DEVELOPMENT_SEED, DEVELOPMENT_STREAMS
    from . import report_e4
    seed = DEVELOPMENT_SEED if master_seed is None else master_seed
    dates = release_dates_from(release_dates)
    record, input_sha256 = input_record(tables, h1_sha256, dates)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    log = dict(kind=SMALL_B_RUN, extension="E4", data_kind=report_e4.data_kind(registered=False),
               started_utc=datetime.now(timezone.utc).isoformat(), master_seed=seed,
               streams=serial(DEVELOPMENT_STREAMS), B=B, interval_B=interval_B, h1_record_sha256=h1_sha256,
               input=record, input_sha256=input_sha256)
    started = time.perf_counter()
    result = analysis.analyze(tables, h1_episodes, master_seed=seed, streams=DEVELOPMENT_STREAMS, B=B,
                              interval_B=interval_B, release_dates=dates)
    return _finish(output, log, started, tables=tables, result=result, record=record, input_sha256=input_sha256,
                   D80=None, data_kind=report_e4.data_kind(registered=False))
