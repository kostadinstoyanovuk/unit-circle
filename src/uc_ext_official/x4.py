"""X.4 and X.5 for E1 and E3: one registered run, outputs verified against their own hashes, then frozen.

A run directory holds run-log.json, the complete analysis (analysis.json; for E3 also every surrogate
fit in surrogate-fits.json.gz), report/ (tables, figures and manifest.json with the SHA-256 of every
report file) and RUN_COMPLETE.json with the SHA-256 of the log, the analysis files and the report
manifest. The run re-reads everything it wrote before it reports success; the freeze verifies the
same hashes again, copies the outputs into audit/ek/ and figures/, verifies the copies, and writes
audit/Ek_RESULT.json. Tags (e1-frozen, e3-frozen) are named in printed instructions only.

Outcome wording (prereg/E1.md and prereg/E3.md section 11, as H1 section 10). DR-E1 and DR-E3 decide
with the Holm-adjusted p at family closure (DR-2); at freeze only the raw p exists and is reported as
"raw, not family-adjusted". Because a Holm-adjusted p is never below its raw p, a raw p above 0.05
already fixes the inconclusive branch; a raw p at or below 0.05 leaves the decision to family closure
and no rejection is declared from it.
"""
from __future__ import annotations

import gzip
import json
import math
import shutil
from pathlib import Path

from uc_core.validation_runner import serial

from . import gates, records

REGISTERED_OUTPUT = dict(e1="runs/e1-registered", e3="runs/e3-registered")
REGISTERED_KIND = dict(e1="boe_millennium_e1_registered", e3="uk_abmi_e3_registered")
REHEARSAL_KIND = "artificial_pipeline_rehearsal"
PRIMARY_RUN, RECOMPUTATION = "registered primary run", "recomputation"
RAW_P_LABEL = "raw, not family-adjusted"
LEVEL = 0.05
FIGURES = ("persistence", "surrogates")
FIGURE_EXTENSIONS = ("svg", "png", "pdf")
STATEMENTS = dict(
    e1=dict(reject=("The observed mean pre-onset change in annual data was unusually large relative to the "
                    "registered fitted constant-AR(2) surrogate procedure."),
            inconclusive=("The E1 comparison did not detect an unusually large pre-onset change under the "
                          "registered surrogate model.")),
    e3=dict(reject=("The observed mean pre-onset change was unusually large relative to the registered fitted "
                    "constant-AR(2) surrogate procedure with a re-estimated time-varying AR(2)."),
            inconclusive=("The primary comparison did not detect an unusually large pre-onset change under the "
                          "registered surrogate model.")))
BRANCH_B_SCOPE = "A labelled diagnostic, not a finding of absence or equivalence (H1 section 10)."


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def interpretation(extension: str, row: dict, interval, D80) -> dict:
    """The section 11 outcome at freeze for the primary comparison row (uc_ext report row)."""
    name = gates.extension_name(extension)
    value, p, status = row.get("value"), row.get("p_value"), row.get("status")
    if value is not None and not _finite(value):
        raise ValueError("Non-finite observed statistic")
    if D80 is not None and not _finite(D80):
        raise ValueError("D80 must be finite or null")
    bounds = (serial(interval) or {}).get("interval") if interval is not None else None
    sign = "unavailable" if value is None else "positive" if value > 0 else "negative" if value < 0 else "zero"
    result = dict(extension=name, decision_rule=(f"DR-{name}: reject when the Holm-adjusted p <= 0.05 at family "
                                                 "closure (section 10); no rejection is declared from the raw p alone"),
                  raw_p=p, p_label=RAW_P_LABEL, adjusted_p=None,
                  adjusted_p_status="computed at family closure (DR-2); not available at freeze",
                  statistic=value, statistic_sign=sign, eligible_episodes=row.get("m"),
                  positive_changes=row.get("k"), D80=D80, episode_interval=bounds, statements=STATEMENTS[extension],
                  branch_B=dict(status="unavailable", condition=None, scope=BRANCH_B_SCOPE))
    if status != "ok" or p is None:
        result.update(conclusion="not_estimable" if status in ("observed_not_estimable", "no_retained_surrogates")
                      else "failed",
                      text=(f"The {name} primary comparison is {status}; it is neither a rejection nor a "
                            "non-rejection. Reasons: " + str(row.get("error") or status)),
                      basis=("An undefined p or a failure is not estimable or failed, with reasons (section 11). "
                             "At family closure a registered extension that failed enters DR-2 with Holm input 1 "
                             "(H1 section 11)."))
        return result
    if not _finite(p) or not 0 <= p <= 1 or value is None:
        raise ValueError("Invalid successful primary comparison")
    if p > LEVEL:
        branch = dict(status="unavailable", condition=None, scope=BRANCH_B_SCOPE)
        if D80 is not None and bounds is not None:
            branch = dict(status="ok", condition=bool(bounds[1] < D80), scope=BRANCH_B_SCOPE,
                          rule="adjusted p > 0.05, D80 defined and the upper end of the 90% episode interval "
                               "strictly below D80")
        result.update(conclusion="inconclusive", text=STATEMENTS[extension]["inconclusive"], branch_B=branch,
                      basis=(f"Raw p = {p:.4g} > 0.05 ({RAW_P_LABEL}). A Holm-adjusted p is never below its raw p, "
                             "so the adjusted p at family closure also exceeds 0.05 and the registered outcome is "
                             "inconclusive; the adjusted value itself is reported at closure."))
    else:
        result.update(conclusion="pending_family_closure", text=None,
                      branch_B=dict(status="pending_family_closure", condition=None, scope=BRANCH_B_SCOPE),
                      basis=(f"Raw p = {p:.4g} <= 0.05 ({RAW_P_LABEL}). No rejection is declared from the raw p "
                             f"alone: DR-{name} rejects only if the Holm-adjusted p at family closure is <= 0.05, "
                             "when statements['reject'] applies; otherwise statements['inconclusive'] applies."))
    if value <= 0:
        result["nonpositive_note"] = ("The observed mean change S is nonpositive; an upper-tail comparison does not "
                                      "show an absolute positive rise in persistence.")
    return result


# ------------------------------------------------------------------------------- run outputs

def write_analysis(output: Path, extension: str, result: dict) -> list[str]:
    """analysis.json (canonical JSON; non-finite numbers as null) and, for E3, surrogate-fits.json.gz."""
    payload = serial(result)
    names = ["analysis.json"]
    if extension == "e3":
        fits = payload.pop("surrogate_fits", None)
        data = gzip.compress(records.canonical(dict(surrogate_fits=fits)) + b"\n", compresslevel=9, mtime=0)
        records.write_once(output / "surrogate-fits.json.gz", data)
        names.append("surrogate-fits.json.gz")
    records.write_once(output / "analysis.json", records.canonical(payload) + b"\n")
    return names


def complete(output: Path, analysis_files) -> dict:
    """RUN_COMPLETE.json, then the run's own hash verification of everything it wrote."""
    content = dict(run_log_sha256=gates.sha256_file(output / "run-log.json"),
                   analysis_sha256={name: gates.sha256_file(output / name) for name in analysis_files},
                   report_manifest_sha256=gates.sha256_file(output / "report/manifest.json"))
    records.write_once(output / "RUN_COMPLETE.json", records.canonical(content) + b"\n")
    verify_outputs(output)
    return content


def verify_outputs(run: Path):
    """Every output of a completed run matches the hashes it recorded; returns (log, manifest, complete)."""
    run = Path(run)
    if not (run / "RUN_COMPLETE.json").is_file():
        raise gates.GateClosed(f"{run} has no RUN_COMPLETE.json: the run did not complete")
    done = records.read_json(run / "RUN_COMPLETE.json")
    expected = {"run-log.json": done["run_log_sha256"], "report/manifest.json": done["report_manifest_sha256"],
                **done["analysis_sha256"]}
    for name, digest in expected.items():
        if not (run / name).is_file() or gates.sha256_file(run / name) != digest:
            raise gates.GateClosed(f"Run output changed or missing after completion: {name}")
    manifest = records.read_json(run / "report/manifest.json")
    listed = set(manifest["file_sha256"])
    present = {path.name for path in (run / "report").iterdir()} - {"manifest.json"}
    if listed != present:
        raise gates.GateClosed(f"Report files differ from the manifest list: {sorted(listed ^ present)}")
    for name, digest in manifest["file_sha256"].items():
        if gates.sha256_file(run / "report" / name) != digest:
            raise gates.GateClosed(f"Report file changed after completion: {name}")
    return records.read_json(run / "run-log.json"), manifest, done


# ------------------------------------------------------------------------------------ freeze

def verify_for_freeze(run: Path, extension: str):
    log, manifest, done = verify_outputs(run)
    if log.get("kind") != PRIMARY_RUN or manifest.get("data_kind") != REGISTERED_KIND[extension] \
            or log.get("extension") != gates.extension_name(extension):
        raise gates.GateClosed(f"Only the registered {gates.extension_name(extension)} primary run can be frozen")
    return log, manifest, done


def summary(extension: str, run: Path, log: dict, manifest: dict, frozen: dict) -> dict:
    """audit/Ek_RESULT.json: the registered result in the addendum's wording, with every count."""
    name = gates.extension_name(extension)
    report = records.read_json(run / "report/report.json")["result"]
    rows = report["comparisons"]
    primary = rows[0]
    interval = report.get("episode_interval") or {}
    record = dict(
        record_type=f"{name} registered primary result",
        registration=f"https://doi.org/{log['registration']['doi']}", protocol=f"prereg/{name}.md",
        run_log=log, interpretation=manifest["interpretation"],
        primary=dict(S=primary["value"], raw_p=primary["p_value"], p_label=primary.get("p_label", RAW_P_LABEL),
                     eligible_episodes=primary["m"], positive_changes=primary["k"], exceedances=primary["exceedances"],
                     retained=primary["retained"], attempted=primary["attempted"], no_eligible=primary["no_eligible"],
                     failed=primary["failed"], q=primary["q"], q_wilson=primary["q_wilson"],
                     p_grid_spacing=primary["p_grid_spacing"], status=primary["status"], error=primary.get("error")),
        family=dict(rule=("DR-2 (H1 section 11): Holm at family-wise alpha 0.05 over E1-E4 at family closure; "
                          "a registered extension never run or failed enters with Holm input 1"),
                    raw_p=primary["p_value"],
                    holm_input=primary["p_value"] if primary["status"] == "ok" and primary["p_value"] is not None else 1.0,
                    adjusted_p=None, adjusted_p_status="pending family closure"),
        episode_interval=dict(status=interval.get("status"), interval=interval.get("interval"),
                              episodes=interval.get("episode_count"), requested=interval.get("requested")),
        comparisons=rows, episodes=report["episodes"], frozen_files=frozen)
    for key in ("exogenous_episodes", "territory_flags", "descriptive"):
        if key in report:
            record[key] = report[key]
    return record


def freeze(root, run, extension: str) -> dict:
    """Verify the registered run, copy it into audit/ek/ and figures/, verify the copies, write Ek_RESULT."""
    root, run = Path(root), Path(run)
    name = gates.extension_name(extension)
    log, manifest, done = verify_for_freeze(run, extension)
    target = root / f"audit/{extension}"
    result_path = root / f"audit/{name}_RESULT.json"
    if target.exists() or result_path.exists():
        raise records.RecordExists(f"audit/{extension}/ or audit/{name}_RESULT.json already exists; "
                                   "a result is frozen once")
    figures = {f"{figure}.{suffix}" for figure in FIGURES for suffix in FIGURE_EXTENSIONS}
    existing = [f"figures/{extension}_{file}" for file in sorted(figures & set(manifest["file_sha256"]))
                if (root / "figures" / f"{extension}_{file}").exists()]
    if existing:
        raise records.RecordExists(f"{', '.join(existing)} already exist; a result is frozen once")
    copies = {"run-log.json": "run-log.json", "RUN_COMPLETE.json": "RUN_COMPLETE.json",
              **{file: file for file in done["analysis_sha256"]},
              **{f"report/{file}": file for file in manifest["file_sha256"] if file not in figures},
              "report/manifest.json": "manifest.json"}
    target.mkdir(parents=True)
    frozen = {}
    for source, destination in copies.items():
        shutil.copyfile(run / source, target / destination)
        frozen[f"audit/{extension}/{destination}"] = gates.sha256_file(target / destination)
    (root / "figures").mkdir(exist_ok=True)
    for file in sorted(figures & set(manifest["file_sha256"])):
        destination = root / "figures" / f"{extension}_{file}"
        shutil.copyfile(run / "report" / file, destination)
        frozen[f"figures/{extension}_{file}"] = gates.sha256_file(destination)
    expected = {"run-log.json": done["run_log_sha256"], "manifest.json": done["report_manifest_sha256"],
                **done["analysis_sha256"],
                **{file: digest for file, digest in manifest["file_sha256"].items() if file not in figures}}
    for file, digest in expected.items():
        if frozen[f"audit/{extension}/{file}"] != digest:
            raise gates.GateClosed(f"The frozen copy of {file} differs from the run's recorded hash")
    for file in figures & set(manifest["file_sha256"]):
        if frozen[f"figures/{extension}_{file}"] != manifest["file_sha256"][file]:
            raise gates.GateClosed(f"The frozen figure {file} differs from the run's recorded hash")
    record = summary(extension, run, log, manifest, frozen)
    records.write_once(result_path, records.pretty(record))
    return record


def tag_instructions(extension: str) -> str:
    name = gates.extension_name(extension)
    tag = f"{extension}-frozen"
    return (f"Review, commit and push audit/{extension}/, audit/{name}_RESULT.json and figures/{extension}_*, update "
            f"STATUS.md, then: git tag -a {tag} -m \"{name} registered result frozen\" && git push origin {tag}")


def json_dump(value) -> str:
    return json.dumps(records.json_safe(value), indent=2)
