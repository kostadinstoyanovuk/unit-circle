"""The X.3 evidence record, audit/Ek_X3.json: what the registered official synthetic checks found.

The E1, E2, E3 and E4 addenda (section 11, Annex B X.3) run the size and power checks after registration and
before any E1 value is read, any E3 statistic is computed on UK data, any E2 unemployment value is read or
any E4 real-time level is read; E2 and E3 first pass their prerequisites. Their outputs are the X.3 runner's
JSON Lines files (tools/run_e_checks.py for E1 and E3, tools/run_e2_checks.py for E2, tools/run_e4_checks.py
for E4), which are large and kept outside git.
This module summarises them with the runner's own registered `summarize` (which re-verifies the gate, the
lock and every saved record), checks that they belong to one registered run of one code identity, and
builds the committed record the X.2 and X.4 gates read. For E2 and E4 the inputs must also use the stream plan
of Annex A and record one E1 code identity (e1_code_sha256), which the record states with the stream plan.

The record is written whether the checks passed or not ("X3": "passed" or "failed"); a failed check
stays visible. Inputs that are not one registered run (development files, mixed code, seeds or
sizes) are refused and nothing is written.
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from . import gates, records

# prereg/E4.md, Annex A: the stream ids of the registered E4 run and of its X.3 checks (5403 is unused).
E4_REGISTERED_STREAMS = dict(primary=5400, window32=5401, window48=5402, wild=5404, interval=5405,
                             size_generation=5420, size_null=5421, power_generation=5430, power_null=5431)
# prereg/E2.md, Annex A: the stream ids of the registered E2 run and of its X.3 checks, and the stream of AT-12.
E2_REGISTERED_STREAMS = dict(primary=5200, window32=5201, window48=5202, fixed=5203, wild=5204, interval=5205,
                             size_generation=5220, size_null=5221, power_generation=5230, power_null=5231,
                             at12=2012)
REGISTERED_STREAMS = dict(e2=E2_REGISTERED_STREAMS, e4=E4_REGISTERED_STREAMS)


class X3InputError(ValueError):
    """The supplied outputs are not one complete registered X.3 run of this extension."""


def summarize(root, extension: str, files) -> dict:
    """The runner's registered `summarize` of one or more output files: {manifest, inputs, summary}."""
    runner = gates.load_runner(root, extension)
    arguments = [extension, "summarize", "--registered", "--root", str(Path(root).resolve())]
    for path in files:
        arguments += ["--out", str(path)]
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        gates._closed(runner.main, arguments)
    return json.loads(buffer.getvalue())


def prerequisite_evidence(root, path, extension: str = "e3") -> dict:
    """The E2 or E3 prerequisite file: its manifest fingerprint and its one prerequisite record."""
    runner = gates.load_runner(root, extension)
    manifest, _, others = gates._closed(runner.read_output, path)
    found = [line for line in others if line.get("record_type") == "prerequisite"]
    if len(found) != 1:
        raise X3InputError(f"{path} must hold exactly one prerequisite record")
    return dict(path=str(path), sha256=gates.sha256_file(path), manifest=runner.fingerprint(manifest),
                record=found[0], passed=bool(runner.prerequisite_passed(found[0])))


def _check_inputs(extension, check, summary, problems):
    for entry in summary.get("inputs") or []:
        fingerprint = entry.get("manifest") or {}
        where = entry.get("path")
        if (fingerprint.get("extension"), fingerprint.get("check")) != (extension, check):
            problems.append(f"{where} is not an {extension} {check} output")
        if (fingerprint.get("mode"), fingerprint.get("master_seed")) != ("registered", gates.REGISTERED_SEED):
            problems.append(f"{where} was not made in registered mode with seed 1927")
        if (fingerprint.get("n_series"), fingerprint.get("B")) != (gates.REGISTERED_SERIES,
                                                                 gates.REGISTERED_ATTEMPTS):
            problems.append(f"{where} does not use 200 series and B = 1000")
        if check == "power" and tuple(fingerprint.get("kappas") or ()) != gates.REGISTERED_KAPPAS:
            problems.append(f"{where} does not use kappa 1.0, 1.2, 1.4, 1.6")
        if extension in REGISTERED_STREAMS and fingerprint.get("streams") != REGISTERED_STREAMS[extension]:
            problems.append(f"{where} does not use the stream plan of prereg/{extension.upper()}.md Annex A")
    if not summary.get("inputs"):
        problems.append(f"no {check} output was supplied")


def _named_prerequisite(fingerprint):
    """The SHA-256 of the prerequisite record that an output names: E3 records the hash itself, E2 a dict
    (path, sha256, passed) that holds it."""
    named = fingerprint.get("prerequisite")
    return named.get("sha256") if isinstance(named, dict) else named


def evidence_entries(paths) -> list[dict]:
    """Supporting evidence named by the operator (for example the logs of the Annex B X.3 prerequisite tests:
    F1, AT-1 to AT-4 and the section 7 unit test for E1; the unit tests of sections 4 and 7 for E2; F2 and
    AT-11 for E3; F1, AT-1 to AT-4 and the unit tests of sections 4, 5 and 7 for E4), each with its SHA-256.
    Recorded, not evaluated: the gates read only the passed flags of the size, power and (E2, E3) prerequisite
    checks."""
    entries = []
    for path in paths or ():
        path = Path(path)
        if not path.is_file():
            raise X3InputError(f"Evidence file {path} does not exist")
        entries.append(dict(path=str(path), sha256=gates.sha256_file(path), bytes=path.stat().st_size))
    return entries


def build_record(extension: str, size: dict, power: dict, prerequisite: dict | None = None, *,
                 created_utc: str, evidence=()) -> dict:
    """The X.3 record from the size and power summaries (and, for E2 and E3, the prerequisite evidence).

    Raises X3InputError unless every input is a registered output of this extension with the registered
    seed, sizes and kappa grid, all made by one code identity (for E2 and E3, each naming the supplied
    prerequisite file; for E2 and E4, each with the stream plan of Annex A and one E1 code identity).
    Otherwise returns the record, passed or failed; an E2 or E4 record also states the stream plan,
    e1_code_sha256 and the identity option.
    """
    name = gates.extension_name(extension)
    problems = []
    _check_inputs(extension, "size", size, problems)
    _check_inputs(extension, "power", power, problems)
    fingerprints = [entry["manifest"] for entry in size.get("inputs", []) + power.get("inputs", [])]
    codes = {fingerprint.get("code_sha256") for fingerprint in fingerprints}
    if len(codes) != 1:
        problems.append("the outputs were made by different code identities")
    settings = {json.dumps(fingerprint.get("settings"), sort_keys=True) for fingerprint in fingerprints}
    if len(settings) > 1:
        problems.append("the outputs were made under different settings")
    if extension in gates.E1_SUPERSET_EXTENSIONS:
        e1_codes = {fingerprint.get("e1_code_sha256") for fingerprint in fingerprints}
        if len(e1_codes) != 1 or not gates.HEX64.match(str(next(iter(e1_codes)))):
            problems.append("the outputs do not record one E1 code identity (e1_code_sha256)")
        if len({fingerprint.get("identity_option") for fingerprint in fingerprints} - {None}) != 1:
            problems.append("the outputs do not record one identity option")
    if extension in gates.PREREQUISITE_EXTENSIONS:
        if prerequisite is None:
            problems.append(f"{name} needs its prerequisite record (section 11)")
        else:
            manifest = prerequisite["manifest"]
            if (manifest.get("extension"), manifest.get("check"), manifest.get("mode"),
                    manifest.get("master_seed")) != (extension, "prerequisite", "registered", gates.REGISTERED_SEED):
                problems.append(f"the prerequisite file is not a registered {name} prerequisite record")
            if manifest.get("code_sha256") not in codes:
                problems.append("the prerequisite was made by another code identity")
            if any(_named_prerequisite(fingerprint) != prerequisite["sha256"] for fingerprint in fingerprints):
                problems.append(f"an {name} output does not name the supplied prerequisite file")
    elif prerequisite is not None:
        problems.append(f"{name} has no separate prerequisite record")
    if problems:
        raise X3InputError("; ".join(problems))
    size_summary, power_summary = size["summary"], power["summary"]
    size_passed = size_summary.get("passed") is True and size_summary.get("registered_design") is True
    power_passed = power_summary.get("passed") is True and power_summary.get("registered_design") is True
    prerequisite_passed = None if prerequisite is None else prerequisite["passed"] is True
    failures = []
    if not size_passed:
        cell = size_summary.get("cell") or {}
        failures.append(f"size: rate {cell.get('rate')} with {cell.get('valid')} of {cell.get('requested')} "
                        f"replicates valid; registered bounds {size_summary.get('bounds')}")
    if not power_passed:
        failures.append("power: an incomplete or invalid cell, or a flagged decrease "
                        f"(flags {power_summary.get('decrease_flags')})")
    if prerequisite is not None and not prerequisite_passed:
        failures.append("prerequisite: at least one section 11 prerequisite did not pass")
    passed = size_passed and power_passed and prerequisite_passed is not False
    record = dict(
        record_type=f"{name} X.3 official synthetic checks (prereg/{name}.md section 11; Annex B, X.3)",
        extension=name, created_utc=created_utc, X3="passed" if passed else "failed",
        size_passed=size_passed, power_passed=power_passed, failures=failures,
        mode="registered", master_seed=gates.REGISTERED_SEED, n_series=gates.REGISTERED_SERIES,
        B=gates.REGISTERED_ATTEMPTS, kappas=list(gates.REGISTERED_KAPPAS),
        D80=power_summary.get("D80"), kappa80=power_summary.get("kappa80"),
        D80_crossing=power_summary.get("crossing"),
        code_sha256=codes.pop(), commits=sorted({fingerprint.get("commit") for fingerprint in fingerprints}),
        settings=fingerprints[0].get("settings"),
        size=dict(inputs=size["inputs"], summary=size_summary, summarize_manifest=size.get("manifest")),
        power=dict(inputs=power["inputs"], summary=power_summary, summarize_manifest=power.get("manifest")),
        supporting_evidence=list(evidence),
        scope=("The registered synthetic size and power design only; passing does not establish calibration "
               "outside this design (H1 section 9)."))
    if prerequisite is not None:
        record.update(prerequisite_passed=prerequisite_passed, prerequisite=prerequisite)
    if extension in gates.E1_SUPERSET_EXTENSIONS:
        record.update(streams=fingerprints[0]["streams"], e1_code_sha256=fingerprints[0]["e1_code_sha256"],
                      identity_option=fingerprints[0]["identity_option"])
    return record


def record_x3(root, extension: str, *, size_files, power_files, prerequisite_file=None, evidence_files=()) -> dict:
    """Summarise the registered outputs and write audit/Ek_X3.json once (after the registration gate)."""
    root = Path(root)
    target = root / gates.x3_record_path(extension)
    if target.exists():
        raise records.RecordExists(f"{target} already exists; the X.3 record is written once")
    gates.check_registration(root, extension)
    evidence = evidence_entries(evidence_files)
    size = summarize(root, extension, size_files)
    power = summarize(root, extension, power_files)
    prerequisite = prerequisite_evidence(root, prerequisite_file, extension) if prerequisite_file else None
    record = build_record(extension, size, power, prerequisite, created_utc=gates.now_utc(), evidence=evidence)
    records.write_once(target, records.pretty(record))
    return record
