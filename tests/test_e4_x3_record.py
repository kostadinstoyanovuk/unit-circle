"""The E4 X.3 record (uc_ext_official.x3 with tools/run_e4_checks.py). Registered-looking summaries are
accepted; development outputs, mixed code identities and wrong designs are refused; E1 and E3 records keep
their fields; and the chain from runner parts through summarize to build_record holds at development size on
constructed data. No registered computation is started."""
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from uc_ext_official import gates, x3

TREE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_e4_checks_for_record", TREE / "tools/run_e4_checks.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
CODE, E1_CODE = "c" * 64, "e" * 64
KAPPAS = [1.0, 1.2, 1.4, 1.6]
DEVELOPMENT_STREAMS = dict(primary=9400, window32=9401, window48=9402, wild=9404, interval=9405,
                           size_generation=9420, size_null=9421, power_generation=9430, power_null=9431)


def manifest(kind, **changes):
    value = dict(record_type="manifest", schema=2, extension="e4", check=kind, mode="registered", master_seed=1927,
                 n_series=200, B=1000, kappas=KAPPAS if kind == "power" else None, settings={},
                 streams=dict(x3.E4_REGISTERED_STREAMS), code_sha256=CODE, e1_code_sha256=E1_CODE,
                 identity_option="e1-superset", identity=dict(commit="d" * 40, python="3.12.14", packages={}),
                 imported=dict(ext_commit=None), lock=dict(satisfied=True), gate=dict(tag="prereg-E4"),
                 prerequisite=None)
    value.update(changes)
    return value


def summaries(*, size_passed=True, power_passed=True, D80=None, size=None, power=None, last_power=None):
    """Summaries in the shape the runner's summarize prints, for the 40 parts of the default plan."""
    size_inputs = [dict(path=f"x3_size_r{a:03d}-{a + 25:03d}.jsonl", sha256="1" * 64, records=25,
                        manifest=runner.fingerprint(manifest("size", **(size or {})))) for a in range(0, 200, 25)]
    power_inputs = [dict(path=f"x3_power_c{k}_r{a:03d}-{a + 25:03d}.jsonl", sha256="2" * 64, records=25,
                         manifest=runner.fingerprint(manifest("power", **(power or {}))))
                    for k in range(4) for a in range(0, 200, 25)]
    if last_power:
        power_inputs[-1]["manifest"].update(last_power)
    return (dict(manifest=dict(check="summarize"), inputs=size_inputs,
                 summary=dict(cell=dict(rate=.05 if size_passed else .12, valid=200, requested=200),
                              bounds=[.02, .09], registered_design=True, passed=size_passed)),
            dict(manifest=dict(check="summarize"), inputs=power_inputs,
                 summary=dict(cells=[], D80=D80, kappa80=None, crossing=None, decrease_flags=[False] * 3,
                              registered_design=True, passed=power_passed)))


def test_a_registered_looking_e4_run_gives_a_passed_record_stating_its_design(tmp_path):
    log = tmp_path / "e4-prerequisite-tests.log"
    log.write_text("constructed test log\n")
    evidence = x3.evidence_entries([log])
    record = x3.build_record("e4", *summaries(), created_utc="2026-10-01T00:00:00+00:00", evidence=evidence)
    assert gates.validate_x3_record(record, "e4") is record
    assert record["record_type"].startswith("E4 X.3") and record["X3"] == "passed" and record["failures"] == []
    assert (record["size_passed"], record["power_passed"], record["mode"], record["master_seed"],
            record["n_series"], record["B"], record["kappas"]) == (True, True, "registered", 1927, 200, 1000, KAPPAS)
    assert "D80" in record and record["D80"] is None                  # undefined D80 is stated as null
    assert record["streams"] == x3.E4_REGISTERED_STREAMS and record["streams"]["size_generation"] == 5420
    assert (record["code_sha256"], record["e1_code_sha256"], record["identity_option"]) == (CODE, E1_CODE,
                                                                                            "e1-superset")
    assert len(record["size"]["inputs"]) == 8 and len(record["power"]["inputs"]) == 32
    assert record["supporting_evidence"] == evidence and "prerequisite_passed" not in record
    assert x3.build_record("e4", *summaries(D80=0.31), created_utc="t")["D80"] == 0.31


@pytest.mark.parametrize("options, failing", [(dict(size_passed=False), "size"), (dict(power_passed=False), "power")])
def test_failed_e4_checks_are_recorded_and_keep_the_gate_closed(options, failing):
    record = x3.build_record("e4", *summaries(**options), created_utc="t")
    assert record["X3"] == "failed" and any(f.startswith(failing) for f in record["failures"])
    with pytest.raises(gates.GateClosed, match="not recorded as passed"):
        gates.validate_x3_record(record, "e4")


@pytest.mark.parametrize("options, extra, message", [
    (dict(size=dict(mode="development")), None, "registered mode"),
    (dict(power=dict(master_seed=20260930)), None, "seed 1927"),
    (dict(size=dict(n_series=2)), None, "200 series"),
    (dict(power=dict(B=9)), None, "B = 1000"),
    (dict(power=dict(kappas=[1.0, 1.2])), None, "kappa"),
    (dict(size=dict(streams=DEVELOPMENT_STREAMS)), None, "Annex A"),
    (dict(power=dict(streams=dict(x3.E4_REGISTERED_STREAMS, power_null=5421))), None, "Annex A"),
    (dict(last_power=dict(code_sha256="0" * 64)), None, "different code"),
    (dict(last_power=dict(e1_code_sha256="0" * 64)), None, "one E1 code identity"),
    (dict(size=dict(e1_code_sha256=None), power=dict(e1_code_sha256=None)), None, "one E1 code identity"),
    (dict(size=dict(identity_option=None), power=dict(identity_option=None)), None, "identity option"),
    (dict(last_power=dict(identity_option="another")), None, "identity option"),
    (dict(size=dict(extension="e1")), None, "not an e4 size output"),
    (dict(power=dict(check="size")), None, "not an e4 power output"),
    ({}, dict(path="p.jsonl", sha256="p" * 64, manifest={}, record={}, passed=True), "no separate prerequisite"),
])
def test_inputs_that_are_not_one_registered_e4_run_are_refused(options, extra, message):
    with pytest.raises(x3.X3InputError, match=message):
        x3.build_record("e4", *summaries(**options), extra, created_utc="t")


def test_e1_records_keep_their_fields_and_are_not_asked_for_a_stream_plan():
    fingerprint = dict(schema=2, extension="e1", mode="registered", master_seed=1927, n_series=200, B=1000,
                       settings={}, code_sha256=CODE, commit="d" * 40, python="3.12.14", packages={}, gate={})
    size = dict(inputs=[dict(path="s", sha256="1" * 64, records=200, manifest=dict(fingerprint, check="size"))],
                summary=dict(cell={}, registered_design=True, passed=True))
    power = dict(inputs=[dict(path="p", sha256="2" * 64, records=800,
                              manifest=dict(fingerprint, check="power", kappas=KAPPAS))],
                 summary=dict(D80=None, registered_design=True, passed=True))
    record = x3.build_record("e1", size, power, created_utc="t")
    assert record["X3"] == "passed" and not {"streams", "e1_code_sha256", "identity_option"} & set(record)


def test_the_chain_from_runner_parts_through_summarize_to_the_record(tmp_path, capsys):
    """What this proves, at development size (2 series, B = 9, development seed and streams) on constructed
    data: the runner's part files, combined by its own summarize, give exactly the structure x3.build_record
    reads (a fingerprint per file with every field it checks); build_record refuses them as development outputs,
    for their mode, seed, sizes and streams only; and the same summaries with only those design fields and the
    pass flags replaced by registered values are accepted with the runner's own code identity and E1 identity.
    Not exercised: the registration gate, the lock under Python 3.12.14 and the clean tree, which
    x3.summarize and x3.record_x3 require through the runner's registered mode."""
    files = dict(size=[], power=[])
    for check, extra in (("size", ["--replicates", "0:1"]), ("size", ["--replicates", "1:2"]),
                         ("power", ["--cells", "0,1"]), ("power", ["--cells", "2,3"])):
        path = tmp_path / f"{check}_{len(files[check])}.jsonl"
        runner.main(["e4", check, "--out", str(path), "--n-series", "2", "--B", "9", *extra])
        files[check].append(path)
    capsys.readouterr()
    summaries_ = {}
    for check, paths in files.items():
        runner.main(["e4", "summarize", *sum((["--out", str(p)] for p in paths), [])])
        summaries_[check] = json.loads(capsys.readouterr().out)
    assert [entry["records"] for entry in summaries_["power"]["inputs"]] == [4, 4]
    assert [cell["valid"] for cell in summaries_["power"]["summary"]["cells"]] == [2, 2, 2, 2]
    with pytest.raises(x3.X3InputError) as refused:
        x3.build_record("e4", summaries_["size"], summaries_["power"], created_utc="t")
    reasons = str(refused.value)
    assert "registered mode with seed 1927" in reasons and "200 series and B = 1000" in reasons
    assert "Annex A" in reasons
    assert not any(word in reasons for word in ("different code", "E1 code identity", "identity option",
                                                "different settings", "not an e4"))
    looking = copy.deepcopy(summaries_)
    for summary in looking.values():
        for entry in summary["inputs"]:
            entry["manifest"].update(mode="registered", master_seed=1927, n_series=200, B=1000,
                                     streams=dict(x3.E4_REGISTERED_STREAMS))
        summary["summary"].update(registered_design=True, passed=True)
    record = x3.build_record("e4", looking["size"], looking["power"], created_utc="t")
    first = runner.read_output(files["size"][0])[0]
    assert record["X3"] == "passed" and record["code_sha256"] == first["code_sha256"]
    assert record["e1_code_sha256"] == first["e1_code_sha256"] == runner.run_identity(
        TREE, registered=False)["e1_code_sha256"]
    assert record["size"]["inputs"][0]["sha256"] == hashlib.sha256(files["size"][0].read_bytes()).hexdigest()


def test_recording_e4_goes_through_the_e4_runners_gate(tmp_path, monkeypatch):
    """gates.load_runner(root, "e4") loads the root's tools/run_e4_checks.py, whose gate is run_e_checks'."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    root = tmp_path / "research"
    for name in ("tools/run_e_checks.py", "tools/run_e4_checks.py", "prereg/E4.md"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TREE / name, root / name)
    (root / ".gitignore").write_text("__pycache__/\n")
    for arguments in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "constructed root"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *arguments], cwd=root,
                       check=True, capture_output=True)
    for call in (lambda: gates.check_registration(root, "e4"),
                 lambda: x3.record_x3(root, "e4", size_files=[tmp_path / "s.jsonl"],
                                      power_files=[tmp_path / "p.jsonl"])):
        with pytest.raises(gates.GateClosed, match="prereg-E4 is absent"):
            call()
    assert gates.load_runner(root, "e4").HERE == root.resolve()
    assert not (root / "audit/E4_X3.json").exists()
