"""The E2 X.3 record (uc_ext_official.x3 with tools/run_e2_checks.py). Registered-looking summaries are
accepted; development outputs, mixed code identities, a prerequisite record that is missing, failed or not the
one the outputs name, and wrong designs are refused; E1, E3 and E4 records keep their fields; and the chain from
runner parts through summarize to build_record holds at development size on constructed data. No registered
computation is started."""
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from uc_e2 import streams
from uc_ext_official import gates, x3

TREE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_e2_checks_for_record", TREE / "tools/run_e2_checks.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
CODE, E1_CODE, PREREQUISITE = "c" * 64, "e" * 64, "f" * 64
KAPPAS = [1.0, 1.2, 1.4, 1.6]
DEVELOPMENT_STREAMS = dict(streams.stream_ids(20260930), at12=streams.at12_stream(20260930))


def manifest(kind, **changes):
    value = dict(record_type="manifest", schema=2, extension="e2", check=kind, mode="registered", master_seed=1927,
                 n_series=200, B=1000, kappas=KAPPAS if kind == "power" else None, settings={},
                 streams=dict(x3.E2_REGISTERED_STREAMS), code_sha256=CODE, e1_code_sha256=E1_CODE,
                 identity_option="e1-superset", identity=dict(commit="d" * 40, python="3.12.14", packages={}),
                 imported=dict(ext_commit=None), lock=dict(satisfied=True), gate=dict(tag="prereg-E2"),
                 prerequisite=dict(path="runs/extensions/E2/x3_prerequisite.jsonl", sha256=PREREQUISITE,
                                   passed=True))
    value.update(changes)
    return value


def prerequisite(passed=True, **manifest_changes):
    """The prerequisite evidence in the shape x3.prerequisite_evidence returns."""
    changed = dict(extension="e2", check="prerequisite", mode="registered", master_seed=1927, code_sha256=CODE)
    changed.update(manifest_changes)
    return dict(path="x3_prerequisite.jsonl", sha256=PREREQUISITE, manifest=changed, record={}, passed=passed)


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


def test_the_registered_stream_plan_is_the_one_the_runner_writes():
    assert x3.E2_REGISTERED_STREAMS == dict(streams.stream_ids(1927), at12=streams.at12_stream(1927))
    assert sorted(x3.E2_REGISTERED_STREAMS.values()) == [2012, 5200, 5201, 5202, 5203, 5204, 5205, 5220, 5221, 5230,
                                                         5231]
    assert x3.REGISTERED_STREAMS == dict(e2=x3.E2_REGISTERED_STREAMS, e4=x3.E4_REGISTERED_STREAMS)


def test_a_registered_looking_e2_run_gives_a_passed_record_stating_its_design(tmp_path):
    log = tmp_path / "e2-data-rule-tests.log"
    log.write_text("constructed test log\n")
    evidence = x3.evidence_entries([log])
    record = x3.build_record("e2", *summaries(), prerequisite(), created_utc="2026-10-02T00:00:00+00:00",
                             evidence=evidence)
    assert gates.validate_x3_record(record, "e2") is record
    assert record["record_type"].startswith("E2 X.3") and record["X3"] == "passed" and record["failures"] == []
    assert (record["size_passed"], record["power_passed"], record["prerequisite_passed"], record["mode"],
            record["master_seed"], record["n_series"], record["B"], record["kappas"]) == (
        True, True, True, "registered", 1927, 200, 1000, KAPPAS)
    assert "D80" in record and record["D80"] is None                  # undefined D80 is stated as null
    assert record["streams"] == x3.E2_REGISTERED_STREAMS
    assert record["streams"]["size_generation"] == 5220 and record["streams"]["at12"] == 2012
    assert (record["code_sha256"], record["e1_code_sha256"], record["identity_option"]) == (CODE, E1_CODE,
                                                                                            "e1-superset")
    assert len(record["size"]["inputs"]) == 8 and len(record["power"]["inputs"]) == 32
    assert record["prerequisite"]["sha256"] == PREREQUISITE and record["supporting_evidence"] == evidence
    assert x3.build_record("e2", *summaries(D80=0.31), prerequisite(), created_utc="t")["D80"] == 0.31


@pytest.mark.parametrize("options, prerequisite_passed, failing", [
    (dict(size_passed=False), True, "size"),
    (dict(power_passed=False), True, "power"),
    ({}, False, "prerequisite"),
])
def test_failed_e2_checks_are_recorded_and_keep_the_gate_closed(options, prerequisite_passed, failing):
    record = x3.build_record("e2", *summaries(**options), prerequisite(prerequisite_passed), created_utc="t")
    assert record["X3"] == "failed" and any(f.startswith(failing) for f in record["failures"])
    assert record["prerequisite_passed"] is prerequisite_passed
    with pytest.raises(gates.GateClosed, match="not recorded as passed"):
        gates.validate_x3_record(record, "e2")


@pytest.mark.parametrize("options, extra, message", [
    (dict(size=dict(mode="development")), prerequisite(), "registered mode"),
    (dict(power=dict(master_seed=20260930)), prerequisite(), "seed 1927"),
    (dict(size=dict(n_series=2)), prerequisite(), "200 series"),
    (dict(power=dict(B=9)), prerequisite(), "B = 1000"),
    (dict(power=dict(kappas=[1.0, 1.2])), prerequisite(), "kappa"),
    (dict(size=dict(streams=DEVELOPMENT_STREAMS)), prerequisite(), "Annex A"),
    (dict(power=dict(streams=dict(x3.E2_REGISTERED_STREAMS, power_null=5221))), prerequisite(), "Annex A"),
    (dict(power=dict(streams=dict(x3.E4_REGISTERED_STREAMS))), prerequisite(), "Annex A"),
    (dict(last_power=dict(code_sha256="0" * 64)), prerequisite(), "different code"),
    (dict(last_power=dict(e1_code_sha256="0" * 64)), prerequisite(), "one E1 code identity"),
    (dict(size=dict(e1_code_sha256=None), power=dict(e1_code_sha256=None)), prerequisite(), "one E1 code identity"),
    (dict(size=dict(identity_option=None), power=dict(identity_option=None)), prerequisite(), "identity option"),
    (dict(last_power=dict(identity_option="another")), prerequisite(), "identity option"),
    (dict(size=dict(extension="e4")), prerequisite(), "not an e2 size output"),
    (dict(power=dict(check="size")), prerequisite(), "not an e2 power output"),
    ({}, None, "E2 needs its prerequisite"),
    ({}, prerequisite(code_sha256="0" * 64), "another code identity"),
    ({}, prerequisite(mode="development"), "not a registered E2 prerequisite"),
    ({}, prerequisite(master_seed=20260930), "not a registered E2 prerequisite"),
    ({}, prerequisite(extension="e3"), "not a registered E2 prerequisite"),
    ({}, prerequisite(check="size"), "not a registered E2 prerequisite"),
    (dict(last_power=dict(prerequisite=dict(path="p", sha256="0" * 64, passed=True))), prerequisite(),
     "does not name the supplied prerequisite"),
    (dict(size=dict(prerequisite=None)), prerequisite(), "does not name the supplied prerequisite"),
])
def test_inputs_that_are_not_one_registered_e2_run_are_refused(options, extra, message):
    with pytest.raises(x3.X3InputError, match=message):
        x3.build_record("e2", *summaries(**options), extra, created_utc="t")


def test_e1_records_keep_their_fields_and_e3_still_names_its_prerequisite_by_hash():
    fingerprint = dict(schema=2, extension="e1", mode="registered", master_seed=1927, n_series=200, B=1000,
                       settings={}, code_sha256=CODE, commit="d" * 40, python="3.12.14", packages={}, gate={})
    size = dict(inputs=[dict(path="s", sha256="1" * 64, records=200, manifest=dict(fingerprint, check="size"))],
                summary=dict(cell={}, registered_design=True, passed=True))
    power = dict(inputs=[dict(path="p", sha256="2" * 64, records=800,
                              manifest=dict(fingerprint, check="power", kappas=KAPPAS))],
                 summary=dict(D80=None, registered_design=True, passed=True))
    record = x3.build_record("e1", size, power, created_utc="t")
    assert record["X3"] == "passed" and not {"streams", "e1_code_sha256", "identity_option"} & set(record)
    e3 = dict(fingerprint, extension="e3", prerequisite="p" * 64)
    size["inputs"][0]["manifest"] = dict(e3, check="size")
    power["inputs"][0]["manifest"] = dict(e3, check="power", kappas=KAPPAS)
    named = prerequisite(extension="e3", code_sha256=CODE)
    named["sha256"] = "p" * 64
    record = x3.build_record("e3", size, power, named, created_utc="t")
    assert record["X3"] == "passed" and record["prerequisite_passed"] is True and "streams" not in record


def test_the_chain_from_runner_parts_through_summarize_to_the_record(tmp_path, capsys):
    """What this proves, at development size (2 series, B = 9, development seed and streams) on constructed
    data: the runner's part files, combined by its own summarize and tied to its prerequisite record, give
    exactly the structure x3.build_record reads (a fingerprint per file with every field it checks, and the
    prerequisite named by path, hash and pass flag); build_record refuses them as development outputs, for
    their mode, seed, sizes, streams and prerequisite only; and the same summaries with only those design fields
    and the pass flags replaced by registered values are accepted with the runner's own code identity and E1
    identity. Not exercised: the registration gate, the lock under Python 3.12.14 and the clean tree, which
    x3.summarize and x3.record_x3 require through the runner's registered mode."""
    prerequisite_file = tmp_path / "prerequisite.jsonl"
    assert runner.main(["e2", "prerequisite", "--out", str(prerequisite_file)]) == 0
    files = dict(size=[], power=[])
    for check, extra in (("size", ["--replicates", "0:1"]), ("size", ["--replicates", "1:2"]),
                         ("power", ["--cells", "0,1"]), ("power", ["--cells", "2,3"])):
        path = tmp_path / f"{check}_{len(files[check])}.jsonl"
        runner.main(["e2", check, "--out", str(path), "--n-series", "2", "--B", "9",
                     "--prerequisite", str(prerequisite_file), *extra])
        files[check].append(path)
    capsys.readouterr()
    summaries_ = {}
    for check, paths in files.items():
        runner.main(["e2", "summarize", *sum((["--out", str(p)] for p in paths), [])])
        summaries_[check] = json.loads(capsys.readouterr().out)
    assert [entry["records"] for entry in summaries_["power"]["inputs"]] == [4, 4]
    assert [cell["valid"] for cell in summaries_["power"]["summary"]["cells"]] == [2, 2, 2, 2]
    evidence = x3.prerequisite_evidence(TREE, prerequisite_file, "e2")
    assert evidence["passed"] is True and evidence["sha256"] == hashlib.sha256(prerequisite_file.read_bytes()).hexdigest()
    named = summaries_["size"]["inputs"][0]["manifest"]["prerequisite"]
    assert named["sha256"] == evidence["sha256"] and named["passed"] is True
    with pytest.raises(x3.X3InputError) as refused:
        x3.build_record("e2", summaries_["size"], summaries_["power"], evidence, created_utc="t")
    reasons = str(refused.value)
    assert "registered mode with seed 1927" in reasons and "200 series and B = 1000" in reasons
    assert "Annex A" in reasons and "not a registered E2 prerequisite" in reasons
    assert not any(word in reasons for word in ("different code", "E1 code identity", "identity option",
                                                "different settings", "not an e2", "does not name",
                                                "another code identity", "needs its prerequisite"))
    looking, looking_evidence = copy.deepcopy(summaries_), copy.deepcopy(evidence)
    looking_evidence["manifest"].update(mode="registered", master_seed=1927)
    for summary in looking.values():
        for entry in summary["inputs"]:
            entry["manifest"].update(mode="registered", master_seed=1927, n_series=200, B=1000,
                                     streams=dict(x3.E2_REGISTERED_STREAMS))
        summary["summary"].update(registered_design=True, passed=True)
    record = x3.build_record("e2", looking["size"], looking["power"], looking_evidence, created_utc="t")
    first = runner.read_output(files["size"][0])[0]
    assert record["X3"] == "passed" and record["code_sha256"] == first["code_sha256"]
    assert record["e1_code_sha256"] == first["e1_code_sha256"] == runner.run_identity(
        TREE, registered=False)["e1_code_sha256"]
    assert record["size"]["inputs"][0]["sha256"] == hashlib.sha256(files["size"][0].read_bytes()).hexdigest()
    assert record["prerequisite"]["sha256"] == evidence["sha256"] and record["prerequisite_passed"] is True


def test_the_prerequisite_evidence_needs_exactly_one_e2_prerequisite_record(tmp_path):
    head = dict(record_type="manifest", extension="e2", check="prerequisite", mode="registered", master_seed=1927)
    record = dict(record_type="prerequisite", passed=True, at12=dict(passed=True), reduction=dict(passed=True),
                  f4=dict(passed=True))
    path = tmp_path / "prerequisite.jsonl"
    path.write_text(json.dumps(head) + "\n" + json.dumps(record) + "\n")
    evidence = x3.prerequisite_evidence(TREE, path, "e2")
    assert evidence["passed"] is True and evidence["manifest"] == runner.fingerprint(head)
    path.write_text(json.dumps(head) + "\n" + json.dumps(dict(record, at12=dict(passed=False))) + "\n")
    assert x3.prerequisite_evidence(TREE, path, "e2")["passed"] is False
    path.write_text(json.dumps(head) + "\n" + json.dumps(record) + "\n" + json.dumps(record) + "\n")
    with pytest.raises(x3.X3InputError, match="exactly one"):
        x3.prerequisite_evidence(TREE, path, "e2")
    path.write_text(json.dumps(head) + "\n")
    with pytest.raises(x3.X3InputError, match="exactly one"):
        x3.prerequisite_evidence(TREE, path, "e2")


def test_recording_e2_goes_through_the_e2_runners_gate(tmp_path, monkeypatch):
    """gates.load_runner(root, "e2") loads the root's tools/run_e2_checks.py, whose gate is run_e_checks'."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    root = tmp_path / "research"
    for name in ("tools/run_e_checks.py", "tools/run_e2_checks.py", "prereg/E2.md"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TREE / name, root / name)
    (root / ".gitignore").write_text("__pycache__/\n")
    for arguments in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "constructed root"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *arguments], cwd=root,
                       check=True, capture_output=True)
    for call in (lambda: gates.check_registration(root, "e2"),
                 lambda: x3.record_x3(root, "e2", size_files=[tmp_path / "s.jsonl"],
                                      power_files=[tmp_path / "p.jsonl"],
                                      prerequisite_file=tmp_path / "prerequisite.jsonl")):
        with pytest.raises(gates.GateClosed, match="prereg-E2 is absent"):
            call()
    assert gates.load_runner(root, "e2").HERE == root.resolve()
    assert not (root / "audit/E2_X3.json").exists()
