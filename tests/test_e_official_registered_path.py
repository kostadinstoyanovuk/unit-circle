"""The registered X.3 record, X.4 run and X.5 freeze paths on a throwaway integrated research root.

Registered mode is exercised in a subprocess that imports the root's own code (as the location gate
requires), with uc_ext.e1.analyze and uc_ext.e3.analyze replaced by wrappers that check they were called
with the registered seed and no overrides and then compute with a development seed and tiny counts on
the artificial data. uc_ext.common.stream_rng is guarded: a generator from seed 1927 raises. No
registered computation is started by any test.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from e_official_artificial import TERRITORY, artificial_workbook, commit_all, integrated_root, x3_record
from e_official_artificial import RESEARCH
from uc_core import validation_runner
from uc_ext_official import e1_source, e3_source, gates

AFTER = "2026-09-29T01:00:00Z"

WRAPPER = r'''
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
steps = json.loads(sys.argv[2])
sys.path.insert(0, str(root / "src"))
from uc_ext import common, e1, e3
original_rng = common.stream_rng
def guarded(master_seed, *args, **kwargs):
    if int(master_seed) == 1927:
        raise RuntimeError("test guard: a generator from the registered seed was requested")
    return original_rng(master_seed, *args, **kwargs)
common.stream_rng = guarded
calls = []
def stub(module, **small):
    original = module.analyze
    def analyze(values, **kwargs):
        calls.append(dict(module=module.__name__, kwargs=kwargs, n=len(values)))
        if kwargs != {"master_seed": 1927, "allow_registered": True}:
            raise RuntimeError(f"unexpected analysis arguments {kwargs}")
        return original(values, master_seed=common.DEVELOPMENT_MASTER_SEED, **small)
    module.analyze = analyze
stub(e1, B=3, interval_B=30)
stub(e3, B=2, interval_B=30)
from uc_ext_official import gates, run, x3, x4
outcomes = []
for step in steps:
    kind, arguments = step[0], step[1:]
    try:
        if kind == "identity":
            value = gates.code_identity(root)["code_sha256"]
        elif kind == "run":
            extension, output, recomputation = arguments
            function = run.run_e1 if extension == "e1" else run.run_e3
            value = function(root, root / output, recomputation=recomputation)["interpretation"]["conclusion"]
        elif kind == "freeze":
            extension, output = arguments
            value = x4.freeze(root, root / output, extension)["record_type"]
        elif kind == "remove":
            value = (root / arguments[0]).unlink()
        elif kind == "record_x3":
            extension, size, power = arguments
            value = x3.record_x3(root, extension, size_files=[root / size], power_files=[root / power])["X3"]
        outcomes.append(["ok", value])
    except (gates.GateClosed, x3.X3InputError, x4.records.RecordExists, RuntimeError) as error:
        outcomes.append(["refused", f"{type(error).__name__}: {error}"])
print(json.dumps(dict(outcomes=outcomes, calls=calls)))
'''


def wrapper(tmp_path, root, *steps):
    script = tmp_path / "wrapper.py"
    script.write_text(WRAPPER)
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    environment.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    completed = subprocess.run([sys.executable, str(script), str(root), json.dumps(steps)], capture_output=True,
                               text=True, env=environment, cwd=root)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.splitlines()[-1])


@pytest.fixture
def root(tmp_path):
    try:
        validation_runner.environment_identity(RESEARCH)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"needs the locked environment: {error}")
    if sys.version.split()[0] != "3.12.14":
        pytest.skip("the registered path needs Python 3.12.14")
    saved = list(sys.path)
    yield integrated_root(tmp_path)
    sys.path[:] = saved


def write_x3(root, code, **changes):
    for extension in ("e1", "e3"):
        (root / gates.x3_record_path(extension)).write_text(
            json.dumps(x3_record(extension, code, D80=0.5, **changes), indent=1))
    commit_all(root, "artificial X.3 records")


def test_registered_run_and_freeze(tmp_path, root):
    code = wrapper(tmp_path, root, ["identity"])["outcomes"][0][1]
    assert len(code) == 64
    early = wrapper(tmp_path, root, ["run", "e1", "runs/e1-registered", False])["outcomes"][0]
    assert early[0] == "refused" and "have not been recorded" in early[1]
    write_x3(root, "0" * 64)
    frozen_code = wrapper(tmp_path, root, ["run", "e1", "runs/e1-registered", False])["outcomes"][0]
    assert frozen_code[0] == "refused" and "Annex B" in frozen_code[1]
    write_x3(root, code)
    no_data = wrapper(tmp_path, root, ["run", "e1", "runs/e1-registered", False],
                      ["run", "e3", "runs/e3-registered", False])["outcomes"]
    assert "No E1 acquisition record" in no_data[0][1] and "E3 X.2" in no_data[1][1]

    e1_source.acquire(root, artificial_workbook(), retrieved_utc=AFTER, method="artificial test download",
                      response=None, licence="artificial licence", licence_url="https://example.invalid/licence")
    e1_source.select(root)
    e1_source.record_territory(root, TERRITORY)
    commit_all(root, "E1 X.2 records")
    e1_source.extract(root)
    commit_all(root, "E1 extraction")
    e3_source.record_data_note(root)
    (root / "stray.txt").write_text("uncommitted\n")
    dirty = wrapper(tmp_path, root, ["run", "e1", "runs/e1-registered", False])["outcomes"][0]
    assert dirty[0] == "refused" and "clean" in dirty[1]
    (root / "stray.txt").unlink()
    commit_all(root, "E3 data note")

    (root / "figures/e3_surrogates.png").write_bytes(b"placeholder")
    commit_all(root, "a figure already present")
    result = wrapper(tmp_path, root,
                     ["run", "e1", "runs/elsewhere", False],
                     ["run", "e1", "runs/e1-registered", False],
                     ["run", "e1", "runs/e1-registered", False],
                     ["run", "e1", "runs/e1-registered", True],
                     ["run", "e1", "audit/e1-recomputation", True],
                     ["run", "e1", "runs/e1-recomputation", True],
                     ["run", "e3", "runs/e3-registered", False],
                     ["freeze", "e1", "runs/e1-recomputation"],
                     ["freeze", "e1", "runs/e1-registered"],
                     ["freeze", "e1", "runs/e1-registered"],
                     ["freeze", "e3", "runs/e3-registered"],
                     ["remove", "figures/e3_surrogates.png"],
                     ["freeze", "e3", "runs/e3-registered"])
    outcomes, calls = result["outcomes"], result["calls"]
    assert outcomes[0][0] == "refused" and "writes only to runs/e1-registered" in outcomes[0][1]
    assert outcomes[1][0] == "ok" and outcomes[1][1] in ("inconclusive", "pending_family_closure", "not_estimable")
    assert outcomes[2][0] == "refused" and "runs once" in outcomes[2][1]
    assert outcomes[3][0] == "refused" and "its own output directory" in outcomes[3][1]
    assert outcomes[4][0] == "refused" and "git-ignored" in outcomes[4][1]
    assert outcomes[5][0] == "ok" and outcomes[6][0] == "ok"
    assert outcomes[7][0] == "refused" and "Only the registered E1 primary run" in outcomes[7][1]
    assert outcomes[8] == ["ok", "E1 registered primary result"]
    assert outcomes[9][0] == "refused" and "frozen once" in outcomes[9][1]
    assert outcomes[10][0] == "refused" and "figures/e3_surrogates.png already exist" in outcomes[10][1]
    assert outcomes[12] == ["ok", "E3 registered primary result"]
    assert [(c["module"], c["kwargs"], c["n"]) for c in calls] == [
        ("uc_ext.e1", {"master_seed": 1927, "allow_registered": True}, 316),
        ("uc_ext.e1", {"master_seed": 1927, "allow_registered": True}, 316),
        ("uc_ext.e3", {"master_seed": 1927, "allow_registered": True}, 259)]

    log = json.loads((root / "runs/e1-registered/run-log.json").read_text(encoding="utf-8"))
    assert (log["kind"], log["extension"], log["master_seed"], log["B"], log["interval_B"]) == (
        "registered primary run", "E1", 1927, 1000, 10000)
    assert log["code_sha256"] == code and log["x3_record"] == "audit/E1_X3.json" and log["D80"] == 0.5
    assert log["registration"]["registration_id"] == "mjg9w" and log["environment"]["dirty"] is False
    assert set(log["x2_records"]) == {e1_source.ACQUISITION_RECORD, e1_source.SELECTION_RECORD,
                                      e1_source.TERRITORY_RECORD, e1_source.EXTRACTION_RECORD}
    assert "uc_ext_official/run.py" in log["package_sources"]
    recomputation = json.loads((root / "runs/e1-recomputation/run-log.json").read_text(encoding="utf-8"))
    assert recomputation["kind"] == "recomputation"

    summary = json.loads((root / "audit/E1_RESULT.json").read_text(encoding="utf-8"))
    assert summary["registration"] == "https://doi.org/10.17605/OSF.IO/MJG9W"
    assert summary["primary"]["p_label"] == "raw, not family-adjusted" and summary["family"]["adjusted_p"] is None
    assert summary["interpretation"]["D80"] == 0.5 and summary["interpretation"]["extension"] == "E1"
    assert {"exogenous_episodes", "territory_flags"} <= set(summary)
    frozen = summary["frozen_files"]
    assert {"audit/e1/analysis.json", "audit/e1/run-log.json", "audit/e1/RUN_COMPLETE.json",
            "audit/e1/manifest.json", "audit/e1/comparisons.csv", "figures/e1_persistence.svg"} <= set(frozen)
    assert all(gates.sha256_file(root / name) == digest for name, digest in frozen.items())
    e3_summary = json.loads((root / "audit/E3_RESULT.json").read_text(encoding="utf-8"))
    assert e3_summary["registration"] == "https://doi.org/10.17605/OSF.IO/RHZSM" and "descriptive" in e3_summary
    assert "audit/e3/surrogate-fits.json.gz" in e3_summary["frozen_files"]
    assert "audit/e3/filtered.csv" in e3_summary["frozen_files"]


def _registered_output(path, extension, check, code, commit):
    manifest = dict(record_type="manifest", schema=2, extension=extension, check=check, mode="registered",
                    master_seed=1927, n_series=200, B=1000, kappas=[1.0, 1.2, 1.4, 1.6] if check == "power" else None,
                    settings={}, code_sha256=code, identity=dict(commit=commit, python="3.12.14", packages={}),
                    imported=dict(ext_commit=None), gate=dict(tag=f"prereg-{extension.upper()}"), prerequisite=None)
    cells = [(0, r) for r in range(3)] if check == "size" else [(c, r) for c in range(4) for r in range(2)]
    lines = [manifest] + [dict(record_type="replicate", cell="size" if check == "size" else f"power_{c}",
                               cell_index=c, replicate=r, status="generation_failed", input=None, input_sha256=None,
                               registered=True, mode="registered", master_seed=1927, B=1000, settings={},
                               code_sha256=code) for c, r in cells]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))


def test_x3_record_from_registered_outputs(tmp_path, root):
    """Stub registered-mode outputs (replicates recorded as generation failures, so no series is ever
    regenerated from seed 1927): the record is written, says failed, and the gates stay closed."""
    code = "c" * 64
    for check in ("size", "power"):
        _registered_output(root / f"runs/extensions/E1/x3_{check}.jsonl", "e1", check, code, "d" * 40)
    development = root / "runs/extensions/E1/dev_power.jsonl"
    lines = (root / "runs/extensions/E1/x3_power.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["mode"] = "development"
    development.write_text("\n".join([json.dumps(first), *lines[1:]]) + "\n")
    outcomes = wrapper(tmp_path, root,
                       ["record_x3", "e1", "runs/extensions/E1/x3_size.jsonl", "runs/extensions/E1/dev_power.jsonl"],
                       ["record_x3", "e1", "runs/extensions/E1/x3_size.jsonl", "runs/extensions/E1/x3_power.jsonl"],
                       ["record_x3", "e1", "runs/extensions/E1/x3_size.jsonl", "runs/extensions/E1/x3_power.jsonl"],
                       )["outcomes"]
    assert outcomes[0][0] == "refused" and "mode" in outcomes[0][1]
    assert outcomes[1] == ["ok", "failed"]
    assert outcomes[2][0] == "refused" and "written once" in outcomes[2][1]
    record = json.loads((root / "audit/E1_X3.json").read_text(encoding="utf-8"))
    assert record["X3"] == "failed" and record["size_passed"] is False and record["code_sha256"] == code
    assert record["size"]["summary"]["cell"]["attempted"] == 3
    commit_all(root, "X.3 record (failed)")
    with pytest.raises(gates.GateClosed, match="not recorded as passed"):
        gates.check_x3(root, "e1")
