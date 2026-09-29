"""The one-shot registered runs (Annex B X.4) and their artificial rehearsals.

Registered mode, each gate fail closed and in this order: code location (uc_core, uc_ext and this
package are the research root's own); G4 (run_e_checks.verify_extension_gate: clean tree, published
annotated tag, protocol and registration record); the committed X.3 record showing passed official
synthetic checks; frozen code (the X.3 code identity, which also requires the lock and Python 3.12.14);
the X.2 data (E1: every record committed and the levels re-extracted identically; E3: the committed
data note and uc_core.h1_official.load_registered_growth); the output directory (the registered path,
not yet existing, git-ignored). Then uc_ext.ek.analyze runs with the registered seed 1927, counts and
streams, and nothing can override them. A verification recomputation passes the same gates, writes
to a new directory and is labelled as a recomputation.

Rehearsal mode runs the same data path and pipeline on an artificial file with a development seed and
shortened counts, labels every output artificial and touches no record.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time

from . import gates, records, x4

ARTIFICIAL_TERRITORY = [(1700, 2016, "artificial rehearsal: no territory record")]


def _output(root, output, extension, recomputation):
    output = Path(output)
    registered = (Path(root) / x4.REGISTERED_OUTPUT[extension]).resolve()
    if not recomputation and output.resolve() != registered:
        raise gates.GateClosed(f"The registered run writes only to {x4.REGISTERED_OUTPUT[extension]}")
    if recomputation and output.resolve() == registered:
        raise gates.GateClosed("A recomputation needs its own output directory")
    if output.exists():
        raise gates.GateClosed(f"{output} exists; the registered analysis runs once into a new directory")
    gates._closed(gates.load_runner(root).verify_output_location, Path(root), output)
    return output


def _start(root, extension, output, recomputation):
    root = Path(root)
    location = gates.check_code_location(root)
    gate = gates.check_registration(root, extension)
    x3 = gates.check_x3(root, extension)
    identity = gates.check_code_frozen(root, x3)
    output = _output(root, output, extension, recomputation)
    log = dict(kind=x4.RECOMPUTATION if recomputation else x4.PRIMARY_RUN,
               extension=gates.extension_name(extension), started_utc=datetime.now(timezone.utc).isoformat(),
               commit=identity["identity"]["commit"], code_sha256=identity["code_sha256"],
               x3_record=x3["record_path"], x3_record_sha256=x3["record_sha256"], D80=x3["D80"],
               registration=gate, environment=identity["identity"], imported=identity["imported"],
               package_sources=gates.package_sources(root), code_location=location, master_seed=gates.REGISTERED_SEED)
    return output, log, x3


def _finish(output, extension, log, result, started, write_report):
    log.update(finished_utc=datetime.now(timezone.utc).isoformat(), seconds=round(time.perf_counter() - started, 1),
               input_sha256=result["input_sha256"])
    (output / "run-log.json").write_bytes(records.canonical(log) + b"\n")
    files = x4.write_analysis(output, extension, result)
    manifest = write_report(log)
    x4.complete(output, files)
    return manifest


def run_e1(root, output, *, recomputation=False):
    from uc_ext import e1
    from . import e1_source, report_e1
    output, log, x3 = _start(root, "e1", output, recomputation)
    data = e1_source.load_registered_growth(root)
    log.update(raw_file=data["acquisition"]["file"], raw_sha256=data["acquisition"]["sha256"],
               x2_records=data["record_sha256"], sheet=data["selection"]["sheet"], column=data["selection"]["column"],
               growth_observations=len(data["growth"]), first_year=data["growth_years"][0],
               last_year=data["growth_years"][-1], B=e1.SURROGATE_ATTEMPTS, interval_B=e1.EPISODE_RESAMPLES)
    output.mkdir(parents=True)
    (output / "run-log.json").write_bytes(records.canonical(log) + b"\n")
    started = time.perf_counter()
    result = e1.analyze(data["growth"], master_seed=gates.REGISTERED_SEED, allow_registered=True)
    stretches = [tuple(s) for s in (e1_source.stretches_for_flags(data["territory"]))]
    return _finish(output, "e1", log, result, started, lambda log: report_e1.write_report(
        output / "report", growth=data["growth"], years=data["growth_years"], result=result, stretches=stretches,
        D80=x3["D80"], data_kind=x4.REGISTERED_KIND["e1"], metadata=dict(run_log=log, D80_source=x3["record_path"])))


def run_e3(root, output, *, recomputation=False):
    from uc_core import h1_official
    from uc_ext import e3
    from . import e3_source, report_e3
    output, log, x3 = _start(root, "e3", output, recomputation)
    note = e3_source.check_data_note(root)
    acquisition, labels, values = h1_official.load_registered_growth(Path(root))
    if acquisition["sha256"] != note["sha256"]:
        raise gates.GateClosed("The ABMI file differs from the one named in the E3 data note")
    log.update(raw_file=acquisition["file"], raw_sha256=acquisition["sha256"], release=acquisition["release_title"],
               data_note_sha256=note["record_sha256"], growth_observations=len(values), first_quarter=labels[0],
               last_quarter=labels[-1], B=e3.SURROGATE_ATTEMPTS, interval_B=e3.EPISODE_RESAMPLES,
               settings=dict(engine="batched", grid_point_failure=e3.GRID_POINT_FAILURE))
    output.mkdir(parents=True)
    (output / "run-log.json").write_bytes(records.canonical(log) + b"\n")
    started = time.perf_counter()
    result = e3.analyze(values, master_seed=gates.REGISTERED_SEED, allow_registered=True)
    return _finish(output, "e3", log, result, started, lambda log: report_e3.write_report(
        output / "report", growth=values, labels=labels, result=result, D80=x3["D80"],
        data_kind=x4.REGISTERED_KIND["e3"], metadata=dict(run_log=log, D80_source=x3["record_path"])))


# ------------------------------------------------------------------------------- rehearsals

def _rehearsal_log(extension, input_file, surrogates, resamples, master_seed):
    return dict(kind="artificial pipeline rehearsal", extension=gates.extension_name(extension),
                data_kind=x4.REHEARSAL_KIND, input_file=str(input_file), master_seed=master_seed,
                B=surrogates, interval_B=resamples, started_utc=datetime.now(timezone.utc).isoformat())


def rehearse_e1(workbook_file, output, *, surrogates, resamples, territory=None, version_location=None,
                first_data_row=None, year_column=None):
    """The E1 X.2 selection and extraction and the X.4 pipeline on an artificial workbook."""
    from uc_ext import common, e1
    from . import e1_source, report_e1
    from .workbook import Workbook
    workbook = Workbook(Path(workbook_file).read_bytes())
    version = e1_source.check_version(e1_source.version_statements(workbook), version_location)
    header = e1_source.header_only(workbook, first_data_row=first_data_row, year_column=year_column)
    _, _, growth_years, growth, details = e1_source.extract_levels(workbook, header["selection"])
    stretches = ([(s["first_year"], s["last_year"], s["territory"])
                  for s in e1_source.validate_territory(workbook, territory)] if territory else ARTIFICIAL_TERRITORY)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    log = _rehearsal_log("e1", workbook_file, surrogates, resamples, common.DEVELOPMENT_MASTER_SEED)
    log.update(selection=header["selection"], version_statement=version["statement"], extraction=details)
    started = time.perf_counter()
    result = e1.analyze(growth, master_seed=common.DEVELOPMENT_MASTER_SEED, B=surrogates, interval_B=resamples)
    return _finish(output, "e1", log, result, started, lambda log: report_e1.write_report(
        output / "report", growth=growth, years=growth_years, result=result, stretches=stretches, D80=None,
        data_kind=x4.REHEARSAL_KIND, metadata=dict(input_file=str(workbook_file), surrogates=surrogates,
                                                   episode_resamples=resamples, master_seed=log["master_seed"])))


def rehearse_e3(input_file, release_date, output, *, surrogates, resamples):
    """The E3 X.4 pipeline on an artificial ONS-format file, read through the H1 identity and stop rules."""
    from uc_core import abmi
    from uc_ext import common, e3
    from . import report_e3
    parsed = abmi.parse_time_series_csv(Path(input_file).read_bytes())
    abmi.check_identity(parsed, release_date=release_date)
    labels, values = abmi.growth(*abmi.registered_sample(parsed))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    log = _rehearsal_log("e3", input_file, surrogates, resamples, common.DEVELOPMENT_MASTER_SEED)
    started = time.perf_counter()
    result = e3.analyze(values, master_seed=common.DEVELOPMENT_MASTER_SEED, B=surrogates, interval_B=resamples)
    return _finish(output, "e3", log, result, started, lambda log: report_e3.write_report(
        output / "report", growth=values, labels=labels, result=result, D80=None, data_kind=x4.REHEARSAL_KIND,
        metadata=dict(input_file=str(input_file), surrogates=surrogates, episode_resamples=resamples,
                      master_seed=log["master_seed"])))
