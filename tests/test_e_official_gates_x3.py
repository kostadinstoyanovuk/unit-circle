"""The X.3 record and the gates that read it; every refusal path. Artificial records only."""
import json

import pytest

from e_official_artificial import git, x3_record
from uc_ext_official import gates, x3

CODE = "c" * 64


def fingerprint(extension, check, **changes):
    value = dict(schema=2, extension=extension, check=check, mode="registered", master_seed=1927, n_series=200,
                 B=1000, kappas=[1.0, 1.2, 1.4, 1.6] if check == "power" else None, settings={}, code_sha256=CODE,
                 commit="d" * 40, ext_commit=None, python="3.12.14", packages={}, gate={"tag": f"prereg-{extension}"},
                 prerequisite=None)
    value.update(changes)
    return value


def summaries(extension="e1", *, size_passed=True, power_passed=True, D80=None, prerequisite=None, **changes):
    size = dict(manifest=dict(check="summarize"), inputs=[dict(path="size.jsonl", sha256="1" * 64, records=200,
                                                              manifest=fingerprint(extension, "size",
                                                                                   prerequisite=prerequisite))],
                summary=dict(cell=dict(rate=.05 if size_passed else .12, valid=200, requested=200),
                             bounds=[.02, .09], registered_design=True, passed=size_passed))
    power = dict(manifest=dict(check="summarize"),
                 inputs=[dict(path=f"power{i}.jsonl", sha256=str(i) * 64, records=400,
                              manifest=fingerprint(extension, "power", prerequisite=prerequisite)) for i in (2, 3)],
                 summary=dict(cells=[], D80=D80, kappa80=None, crossing=None, decrease_flags=[False, False, False],
                              registered_design=True, passed=power_passed))
    for key, value in changes.items():
        target, field = key.split("__")
        for entry in (size if target == "size" else power)["inputs"]:
            entry["manifest"][field] = value
    return size, power


def prerequisite(passed=True, **manifest_changes):
    manifest = dict(extension="e3", check="prerequisite", mode="registered", master_seed=1927, code_sha256=CODE)
    manifest.update(manifest_changes)
    return dict(path="prerequisite.jsonl", sha256="p" * 64, manifest=manifest, record={}, passed=passed)


# ------------------------------------------------------------------------------ build_record

def test_passed_record_for_e1_and_e3():
    record = x3.build_record("e1", *summaries(D80=0.12), created_utc="2026-10-01T00:00:00+00:00")
    assert record["X3"] == "passed" and record["D80"] == 0.12 and record["code_sha256"] == CODE
    assert gates.validate_x3_record(record, "e1") is record
    size, power = summaries("e3", prerequisite="p" * 64)
    record = x3.build_record("e3", size, power, prerequisite(), created_utc="t")
    assert record["X3"] == "passed" and record["prerequisite_passed"] is True
    assert gates.validate_x3_record(record, "e3")


@pytest.mark.parametrize("extension, options, failing", [
    ("e1", dict(size_passed=False), "size"),
    ("e1", dict(power_passed=False), "power"),
    ("e3", dict(prerequisite_passed=False), "prerequisite"),
])
def test_failed_checks_are_recorded_and_keep_the_gates_closed(extension, options, failing):
    passed = options.pop("prerequisite_passed", True)
    size, power = summaries(extension, prerequisite="p" * 64 if extension == "e3" else None, **options)
    record = x3.build_record(extension, size, power, prerequisite(passed) if extension == "e3" else None,
                             created_utc="t")
    assert record["X3"] == "failed" and any(f.startswith(failing) for f in record["failures"])
    with pytest.raises(gates.GateClosed, match="not recorded as passed"):
        gates.validate_x3_record(record, extension)


@pytest.mark.parametrize("extension, changes, extra, message", [
    ("e1", dict(size__mode="development"), None, "registered mode"),
    ("e1", dict(power__master_seed=20260928), None, "seed 1927"),
    ("e1", dict(size__n_series=2), None, "200 series"),
    ("e1", dict(power__B=9), None, "B = 1000"),
    ("e1", dict(power__kappas=[1.0, 1.2]), None, "kappa"),
    ("e1", dict(size__extension="e3"), None, "not an e1 size output"),
    ("e1", dict(power__check="size"), None, "not an e1 power output"),
    ("e1", dict(power__code_sha256="0" * 64), None, "different code"),
    ("e1", dict(power__settings={"engine": "reference"}), None, "different settings"),
    ("e1", {}, prerequisite(), "E1 has no separate prerequisite"),
    ("e3", {}, None, "needs its prerequisite"),
    ("e3", {}, prerequisite(code_sha256="0" * 64), "another code identity"),
    ("e3", {}, prerequisite(mode="development"), "not a registered E3 prerequisite"),
])
def test_inputs_that_are_not_one_registered_run_are_refused(extension, changes, extra, message):
    size, power = summaries(extension, prerequisite="p" * 64 if extension == "e3" else None, **changes)
    with pytest.raises(x3.X3InputError, match=message):
        x3.build_record(extension, size, power, extra, created_utc="t")


def test_e3_outputs_must_name_the_supplied_prerequisite():
    size, power = summaries("e3", prerequisite="q" * 64)
    with pytest.raises(x3.X3InputError, match="does not name"):
        x3.build_record("e3", size, power, prerequisite(), created_utc="t")


def test_missing_inputs_are_refused():
    size, power = summaries()
    size["inputs"] = []
    with pytest.raises(x3.X3InputError, match="no size output"):
        x3.build_record("e1", size, power, None, created_utc="t")


# ------------------------------------------------------------------------- validate / check

@pytest.mark.parametrize("changes, message", [
    (dict(extension="E3"), "not an E1 X.3 record"),
    (dict(record_type="E1 something else"), "not an E1 X.3 record"),
    (dict(X3="failed"), "X3 is 'failed'"),
    (dict(size_passed=None), "size_passed"),
    (dict(power_passed=False), "power_passed"),
    (dict(mode="development"), "registered mode"),
    (dict(master_seed=20260928), "registered mode"),
    (dict(n_series=2), "registered mode"),
    (dict(B=9), "registered mode"),
    (dict(kappas=[1.0]), "kappa"),
    (dict(code_sha256="short"), "code identity"),
])
def test_validate_refusals(changes, message):
    record = x3_record("e1", CODE)
    record.update(changes)
    with pytest.raises(gates.GateClosed, match=message):
        gates.validate_x3_record(record, "e1")
    record = x3_record("e1", CODE)
    del record["D80"]
    with pytest.raises(gates.GateClosed, match="D80"):
        gates.validate_x3_record(record, "e1")
    record = x3_record("e3", CODE, prerequisite_passed=False)
    with pytest.raises(gates.GateClosed, match="prerequisite_passed"):
        gates.validate_x3_record(record, "e3")


def test_check_x3_needs_a_committed_unchanged_record(tmp_path):
    root = tmp_path / "repo"
    (root / "audit").mkdir(parents=True)
    git(root, "init", "-q")
    with pytest.raises(gates.GateClosed, match="have not been recorded"):
        gates.check_x3(root, "e1")
    path = root / "audit/E1_X3.json"
    path.write_text(json.dumps(x3_record("e1", CODE)))
    with pytest.raises(gates.GateClosed, match="not committed"):
        gates.check_x3(root, "e1")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "x3")
    record = gates.check_x3(root, "e1")
    assert record["record_path"] == "audit/E1_X3.json" and len(record["record_sha256"]) == 64
    path.write_text(json.dumps(x3_record("e1", CODE, D80=0.2)))
    with pytest.raises(gates.GateClosed, match="differs from the committed"):
        gates.check_x3(root, "e1")
    path.write_text(json.dumps(x3_record("e1", CODE, X3="failed")))
    git(root, "commit", "-q", "-am", "failed x3")
    with pytest.raises(gates.GateClosed, match="not recorded as passed"):
        gates.check_x3(root, "e1")


def test_code_freeze_compares_the_x3_identity(monkeypatch):
    monkeypatch.setattr(gates, "code_identity", lambda root, extension="e1": dict(code_sha256=CODE, identity={}))
    assert gates.check_code_frozen("unused", dict(code_sha256=CODE))["code_sha256"] == CODE
    with pytest.raises(gates.GateClosed, match="Annex B"):
        gates.check_code_frozen("unused", dict(code_sha256="0" * 64))


def test_runner_refusals_become_gate_refusals(tmp_path):
    root = tmp_path / "repo"
    (root / "tools").mkdir(parents=True)
    (root / ".gitignore").write_text("__pycache__/\n")
    git(root, "init", "-q")
    with pytest.raises(gates.GateClosed, match="not integrated"):
        gates.check_registration(root, "e1")
    from e_official_artificial import PIPELINES
    (root / "tools/run_e_checks.py").write_bytes((PIPELINES / "tools/run_e_checks.py").read_bytes())
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "runner")
    with pytest.raises(gates.GateClosed, match="prereg-E1 is absent"):
        gates.check_registration(root, "e1")
    with pytest.raises(ValueError):
        gates.extension_name("e2")


def test_time_helpers():
    assert gates.utc("2026-09-28T15:57:37Z").isoformat() == "2026-09-28T15:57:37+00:00"
    with pytest.raises(ValueError, match="offset"):
        gates.utc("2026-09-28T15:57:37")
    with pytest.raises(ValueError, match="ISO"):
        gates.utc("yesterday")


def test_code_location_must_be_the_research_roots_own(tmp_path):
    with pytest.raises(gates.GateClosed, match="imported from"):
        gates.check_code_location(tmp_path)


def test_code_identity_refusals_become_gate_refusals(tmp_path, monkeypatch):
    from e_official_artificial import PIPELINES
    runner = gates.load_runner(PIPELINES)

    def refused(root, *, registered):
        raise SystemExit("Registered runs need the research lock and its files: numpy differs")
    monkeypatch.setattr(runner, "run_identity", refused)
    with pytest.raises(gates.GateClosed, match="research lock"):
        gates.code_identity(PIPELINES)


def test_prerequisite_evidence_needs_exactly_one_record(tmp_path):
    from e_official_artificial import PIPELINES
    manifest = dict(record_type="manifest", extension="e3", check="prerequisite", mode="registered", master_seed=1927)
    record = dict(record_type="prerequisite", passed=True, r0=dict(passed=True), agreement=dict(passed=True),
                  at11=dict(passed=True))
    path = tmp_path / "prerequisite.jsonl"
    path.write_text(json.dumps(manifest) + "\n" + json.dumps(record) + "\n")
    runner = gates.load_runner(PIPELINES)
    evidence = x3.prerequisite_evidence(PIPELINES, path)
    assert evidence["passed"] is True and evidence["sha256"] == gates.sha256_file(path)
    assert evidence["manifest"] == runner.fingerprint(manifest)
    path.write_text(json.dumps(manifest) + "\n" + json.dumps(record) + "\n" + json.dumps(record) + "\n")
    with pytest.raises(x3.X3InputError, match="exactly one"):
        x3.prerequisite_evidence(PIPELINES, path)
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(gates.GateClosed, match="manifest"):
        x3.prerequisite_evidence(PIPELINES, path)


def test_supporting_evidence_is_hashed_into_the_record(tmp_path):
    log = tmp_path / "prerequisite-tests.log"
    log.write_text("artificial test log\n", encoding="utf-8")
    entries = x3.evidence_entries([log])
    assert entries == [dict(path=str(log), sha256=gates.sha256_file(log), bytes=log.stat().st_size)]
    record = x3.build_record("e1", *summaries(), created_utc="t", evidence=entries)
    assert record["supporting_evidence"] == entries and record["X3"] == "passed"
    with pytest.raises(x3.X3InputError, match="does not exist"):
        x3.evidence_entries([tmp_path / "absent.log"])
