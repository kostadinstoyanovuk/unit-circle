"""The check runner: development runs at tiny sizes, resume, and the fail-closed registered path.

Registered mode is exercised only with stubs in place of every computation, and the end-to-end test also
replaces uc_ext.common.stream_rng by a guard that raises if a generator from the registered seed 1927 is
requested. No test ever starts a registered computation.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import uc_core
from uc_core import validation_runner
from uc_ext import common as c, e3

TOOL = Path(__file__).resolve().parents[1] / "tools/run_e_checks.py"
spec = importlib.util.spec_from_file_location("run_e_checks", TOOL)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
TREE = Path(__file__).resolve().parents[1]
RESEARCH = Path(uc_core.__file__).resolve().parents[2]
DEV = c.DEVELOPMENT_MASTER_SEED


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def replicates(path):
    return [r for r in lines(path) if r.get("record_type") == "replicate"]


def git(root, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()


# ------------------------------------------------------------------ development runs and resume

def test_development_run_resumes_without_duplicates_and_summarizes(tmp_path, capsys):
    out = tmp_path / "e1_size.jsonl"
    runner.main(["e1", "size", "--out", str(out), "--n-series", "2", "--B", "3", "--replicates", "0:1"])
    runner.main(["e1", "size", "--out", str(out), "--n-series", "2", "--B", "3"])
    records = replicates(out)
    assert [(r["cell_index"], r["replicate"]) for r in records] == [(0, 0), (0, 1)]
    assert all(r["registered"] is False for r in records)
    assert [r["record_type"] for r in lines(out)] == ["manifest", "session", "replicate", "session", "replicate"]
    fresh = tmp_path / "fresh.jsonl"
    runner.main(["e1", "size", "--out", str(fresh), "--n-series", "2", "--B", "3"])
    assert replicates(fresh) == records          # a resumed run gives the uninterrupted run's records
    capsys.readouterr()
    runner.main(["e1", "summarize", "--out", str(out)])
    summary = json.loads(capsys.readouterr().out)
    assert list(summary)[0] == "manifest" and summary["manifest"]["check"] == "summarize"
    assert summary["summary"]["cell"]["attempted"] == 2 and summary["summary"]["passed"] is False
    assert summary["summary"]["cell"]["requested"] == 2   # taken from the file's manifest


def test_power_cells_can_be_split(tmp_path):
    out = tmp_path / "e1_power.jsonl"
    runner.main(["e1", "power", "--out", str(out), "--n-series", "1", "--B", "2", "--cells", "3"])
    assert [(r["cell_index"], r["kappa"]) for r in replicates(out)] == [(3, 1.6)]


# ------------------------------------------------------------------------ S4: manifest first

def test_every_output_starts_with_a_manifest_and_records_carry_provenance(tmp_path):
    out = tmp_path / "e1_size.jsonl"
    runner.main(["e1", "size", "--out", str(out), "--n-series", "1", "--B", "2"])
    manifest, session, record = lines(out)
    assert manifest["record_type"] == "manifest" and session["record_type"] == "session"
    assert (manifest["extension"], manifest["check"], manifest["mode"], manifest["master_seed"],
            manifest["n_series"], manifest["B"]) == ("e1", "size", "development", DEV, 1, 2)
    identity = manifest["identity"]
    assert {"commit", "dirty", "python", "packages", "source_sha256", "numpy_runtime"} <= set(identity)
    imported = manifest["imported"]["sources"]
    for name in ("uc_ext/common.py", "uc_ext/e1.py", "uc_ext/e3.py", "uc_core/surrogate.py"):
        package = TREE / "src" if name.startswith("uc_ext") else RESEARCH / "src"
        assert imported[name] == hashlib.sha256((package / name).read_bytes()).hexdigest()
    assert imported["tools/run_e_checks.py"] == hashlib.sha256(TOOL.read_bytes()).hexdigest()
    assert manifest["code_sha256"] == runner._canonical_sha256(dict(environment=identity["source_sha256"],
                                                                    imported=imported))
    for name, value in dict(mode="development", master_seed=DEV, B=2, settings={},
                            code_sha256=manifest["code_sha256"], record_type="replicate").items():
        assert record[name] == value


def test_registered_identity_refuses_outside_the_lock_or_interpreter(monkeypatch, tmp_path):
    def raising(root):
        raise validation_runner.IntegrityError("Installed dependency differs from lock: numpy")
    monkeypatch.setattr(validation_runner, "environment_identity", raising)
    with pytest.raises(SystemExit, match="lock"):
        runner.run_identity(RESEARCH, registered=True)
    development = runner.run_identity(RESEARCH, registered=False)
    assert development["lock"]["satisfied"] is False and "numpy" in development["lock"]["error"]
    good = dict(commit="c" * 40, dirty=False, python=runner.REGISTERED_PYTHON, platform="p", machine="m",
                numpy_runtime="n", packages={}, source_sha256={})
    for changes in (dict(python="3.12.3"), dict(dirty=True)):
        monkeypatch.setattr(validation_runner, "environment_identity", lambda root, changes=changes: good | changes)
        with pytest.raises(SystemExit):
            runner.run_identity(RESEARCH, registered=True)
    monkeypatch.setattr(validation_runner, "environment_identity", lambda root: good)
    assert runner.run_identity(RESEARCH, registered=True)["lock"]["satisfied"] is True


# ------------------------------------------------------------------ S5: resume verification

def _tampered(tmp_path, name, source, change):
    path = tmp_path / name
    rows = lines(source)
    change(rows)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def test_resume_refuses_another_run_or_altered_records(tmp_path):
    source = tmp_path / "source.jsonl"
    runner.main(["e1", "size", "--out", str(source), "--n-series", "3", "--B", "2", "--replicates", "0:2"])
    other = replicates(source)[1]

    def record_change(**changes):
        return lambda rows: rows[2].update(changes)

    def replace_input(rows):
        rows[2].update(input=other["input"], input_sha256=other["input_sha256"])

    def alter_input(rows):
        rows[2]["input"][5] += 1e-9

    cases = dict(
        other_B=(None, ["--B", "3"]),
        other_seed=(lambda rows: rows[0].update(master_seed=DEV + 1), []),
        other_code=(lambda rows: rows[0].update(code_sha256="0" * 64), []),
        other_commit=(lambda rows: rows[0]["identity"].update(commit="0" * 40), []),
        other_packages=(lambda rows: rows[0]["identity"]["packages"].update(numpy="0"), []),
        no_manifest=(lambda rows: rows.pop(0), []),
        altered_input=(alter_input, []),
        input_from_other_coordinates=(replace_input, []),
        duplicate=(lambda rows: rows.append(rows[2]), []),
        record_mode=(record_change(mode="registered"), []),
        record_seed=(record_change(master_seed=1927), []),
        record_B=(record_change(B=9), []),
        record_code=(record_change(code_sha256="0" * 64), []),
        record_outside=(record_change(replicate=7), []),
        unknown_line=(lambda rows: rows.append(dict(record_type="note")), []),
    )
    for name, (change, extra) in cases.items():
        path = source if change is None else _tampered(tmp_path, f"{name}.jsonl", source, change)
        before = path.read_bytes()
        with pytest.raises(SystemExit):
            runner.main(["e1", "size", "--out", str(path), "--n-series", "3", "--B", "2", *extra])
        assert path.read_bytes() == before, name       # nothing is appended to a refused file
    with pytest.raises(SystemExit):                    # summarize re-verifies too
        runner.main(["e1", "summarize", "--out", str(_tampered(tmp_path, "s.jsonl", source, alter_input))])
    runner.main(["e1", "size", "--out", str(source), "--n-series", "3", "--B", "2"])
    assert [r["replicate"] for r in replicates(source)] == [0, 1, 2]


# ------------------------------------------------------------ S1: E3 prerequisites stop the run

def test_prerequisite_command_exits_zero_only_when_every_prerequisite_passes(tmp_path, monkeypatch, capsys):
    out = tmp_path / "prerequisite.jsonl"
    assert runner.main(["e3", "prerequisite", "--out", str(out)]) == 0
    manifest, record = lines(out)
    assert manifest["record_type"] == "manifest" and manifest["check"] == "prerequisite"
    assert record["passed"] and record["r0"]["passed"] and record["agreement"]["passed"] and record["at11"]["passed"]
    assert record["mode"] == "development" and record["code_sha256"] == manifest["code_sha256"]
    with pytest.raises(SystemExit):          # a prerequisite record is never overwritten
        runner.main(["e3", "prerequisite", "--out", str(out)])
    runner.main(["e3", "size", "--out", str(tmp_path / "e3.jsonl"), "--n-series", "1", "--B", "1",
                 "--prerequisite", str(out)])
    (size,) = replicates(tmp_path / "e3.jsonl")
    assert size["prerequisite_sha256"] == runner._sha256_file(out)
    assert size["settings"] == dict(engine="batched", check_agreement=True, grid_point_failure="discard",
                                    retention="base_fits") and size["filter_agreement"]["passed"]
    for failing in ("r0", "agreement", "at11"):
        def forced(*, master_seed, allow_registered=False, failing=failing):
            parts = {name: dict(passed=name != failing) for name in ("r0", "agreement", "at11")}
            return dict(input_sha256="x", passed=False, **parts)
        monkeypatch.setattr(e3, "prerequisite_fixture", forced)
        failed = tmp_path / f"failed_{failing}.jsonl"
        assert runner.main(["e3", "prerequisite", "--out", str(failed)]) != 0
        assert lines(failed)[1]["passed"] is False
        with pytest.raises(SystemExit):
            runner.main(["e3", "size", "--out", str(tmp_path / f"x_{failing}.jsonl"), "--prerequisite", str(failed)])
    capsys.readouterr()


def test_verify_prerequisite_needs_a_passed_record_of_the_same_mode_seed_and_code(tmp_path):
    def prerequisite(name, manifest_changes=(), **changes):
        manifest = dict(record_type="manifest", extension="e3", check="prerequisite", mode="registered",
                        master_seed=1927, code_sha256="a" * 64, identity=dict(commit="b" * 40))
        manifest.update(manifest_changes)
        record = dict(record_type="prerequisite", mode="registered", master_seed=1927, passed=True,
                      r0=dict(passed=True), agreement=dict(passed=True), at11=dict(passed=True), code_sha256="a" * 64)
        record.update(changes)
        path = tmp_path / name
        path.write_text(json.dumps(manifest) + "\n" + json.dumps(record) + "\n")
        return path

    expected = dict(mode="registered", master_seed=1927, commit="b" * 40, code_sha256="a" * 64)
    assert runner.verify_prerequisite(prerequisite("ok.jsonl"), **expected)["passed"] is True
    refused = [None, prerequisite("failed.jsonl", passed=False), prerequisite("part.jsonl", at11=dict(passed=False)),
               prerequisite("dev.jsonl", mode="development"), prerequisite("seed.jsonl", master_seed=DEV),
               prerequisite("code.jsonl", code_sha256="0" * 64),
               prerequisite("commit.jsonl", manifest_changes=dict(identity=dict(commit="0" * 40))),
               prerequisite("check.jsonl", manifest_changes=dict(check="size"))]
    for path in refused:
        with pytest.raises(SystemExit):
            runner.verify_prerequisite(path, **expected)


# ------------------------------------------------------------------------------ S2: the gate

def _registered_repository(tmp_path):
    """A throwaway repository with an annotated, pushed prereg-E1 tag and a matching registration record."""
    origin, root = tmp_path / "origin.git", tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    (root / "prereg").mkdir(parents=True)
    (root / "audit").mkdir()
    # Bytes, not text: on Windows text mode writes CRLF, which git normalises to LF in the tagged blob.
    (root / "prereg/E1.md").write_bytes(b"E1 protocol\n")
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "protocol")
    git(root, "tag", "-a", "prereg-E1", "-m", "E1 registered")
    protocol = hashlib.sha256(b"E1 protocol\n").hexdigest()
    receipt = dict(registration_id="test1", doi="10.0/TEST1", prereg_tag="prereg-E1",
                   prereg_tag_commit=git(root, "rev-parse", "prereg-E1^{commit}"),
                   api_date_registered_utc="2026-09-28T15:47:57.051933Z",
                   public_first_verified_at_utc="2026-09-28T15:57:37Z",
                   anonymous_api_check=dict(public=True, pending_registration_approval=False, embargoed=False,
                                            withdrawn=False, archiving=False, revision_state="approved"),
                   expected_attachment_sha256={"prereg/E1.md": protocol},
                   archived_attachments=[dict(file_name="E1.md", osf_sha256=protocol, downloaded_sha256=protocol)],
                   archived_attachment_bytes_verified=True)
    git(root, "remote", "add", "origin", str(origin))
    return root, receipt


def _commit_receipt(root, receipt):
    (root / "audit/E1_REGISTRATION.json").write_text(json.dumps(receipt, indent=1))
    git(root, "add", ".")
    git(root, "commit", "-q", "--allow-empty", "-m", "receipt")


def test_gate_reads_the_public_registration_record(tmp_path):
    root, receipt = _registered_repository(tmp_path)
    _commit_receipt(root, receipt)
    with pytest.raises(SystemExit, match="not published"):
        runner.verify_extension_gate(root, "e1")          # the tag is not on origin yet
    git(root, "push", "-q", "origin", "HEAD", "--tags")
    assert runner.verify_extension_gate(root, "e1") == "prereg-E1"
    gate = runner.gate_record(root, "e1")
    assert gate["registration_id"] == "test1" and gate["protocol_sha256"] == receipt["expected_attachment_sha256"]["prereg/E1.md"]

    def api(**changes):
        return dict(anonymous_api_check=receipt["anonymous_api_check"] | changes)

    other = "0" * 64
    variants = [api(public=False), api(revision_state="pending"), api(pending_registration_approval=True),
                api(embargoed=True), api(withdrawn=True), api(archiving=True),
                dict(archived_attachment_bytes_verified=False),
                dict(archived_attachments=[dict(receipt["archived_attachments"][0], osf_sha256=other)]),
                dict(archived_attachments=[dict(receipt["archived_attachments"][0], downloaded_sha256=other)]),
                dict(archived_attachments=[]), dict(expected_attachment_sha256={"prereg/E1.md": other}),
                dict(prereg_tag="prereg-E3"), dict(prereg_tag_commit="0" * 40), dict(registration_id=None),
                dict(public_first_verified_at_utc="2026-09-28T15:57:37"), dict(api_date_registered_utc="yesterday")]
    for changes in variants:
        _commit_receipt(root, receipt | changes)
        with pytest.raises(SystemExit):
            runner.verify_extension_gate(root, "e1")
    _commit_receipt(root, receipt)
    assert runner.verify_extension_gate(root, "e1") == "prereg-E1"
    (root / "stray.txt").write_text("uncommitted\n")
    with pytest.raises(SystemExit, match="clean"):
        runner.verify_extension_gate(root, "e1")
    (root / "stray.txt").unlink()
    (root / "audit/E1_REGISTRATION.json").unlink()
    git(root, "commit", "-q", "-am", "receipt removed")
    with pytest.raises(SystemExit, match="missing"):
        runner.verify_extension_gate(root, "e1")
    (root / "prereg/E1.md").write_bytes(b"E1 protocol, edited\n")
    git(root, "commit", "-q", "-am", "protocol edited")
    with pytest.raises(SystemExit, match="differs"):
        runner.verify_extension_gate(root, "e1")
    with pytest.raises(SystemExit, match="absent"):
        runner.verify_extension_gate(root, "e3")
    git(root, "tag", "prereg-E3")                           # lightweight
    with pytest.raises(SystemExit, match="annotated"):
        runner.verify_extension_gate(root, "e3")


# ------------------------------------------------------------------- S3: where the code runs

def test_registered_runs_start_only_from_the_research_root(tmp_path, monkeypatch):
    root, receipt = _registered_repository(tmp_path)
    for extension in ("e1", "e3"):
        with pytest.raises(SystemExit, match="research root"):
            runner.main([extension, "size", "--out", str(tmp_path / "x.jsonl"), "--registered", "--root", str(root)])
    with pytest.raises(SystemExit):
        runner.main(["e3", "size", "--out", str(tmp_path / "x.jsonl"), "--registered", "--root", str(TREE),
                     "--n-series", "2"])
    assert not (tmp_path / "x.jsonl").exists()
    with pytest.raises(SystemExit, match="research root"):
        runner.verify_code_location(root)
    monkeypatch.setattr(runner, "HERE", root.resolve())      # right runner location, but uc_ext is not the root's
    with pytest.raises(SystemExit, match="imported from"):
        runner.verify_code_location(root)


def test_registered_outputs_must_not_dirty_the_research_tree(tmp_path):
    root, _ = _registered_repository(tmp_path)
    (root / ".gitignore").write_text("runs/\n")
    runner.verify_output_location(root, root / "runs/E1/x3_size.jsonl")
    runner.verify_output_location(root, tmp_path / "elsewhere.jsonl")
    with pytest.raises(SystemExit, match="git-ignored"):
        runner.verify_output_location(root, root / "audit/x3_size.jsonl")


# ------------------------------------ S1-S4 end to end on a temporary integrated research root (stubs)

WRAPPER = r'''
import importlib.util, json, shutil, sys
from pathlib import Path
root, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
sys.path.insert(0, str(root / "src"))
from uc_ext import common, e1, e3
original = common.stream_rng
def guarded(master_seed, *args, **kwargs):
    if int(master_seed) == 1927:
        raise RuntimeError("test guard: a generator from the registered seed was requested")
    return original(master_seed, *args, **kwargs)
common.stream_rng = guarded
calls = []
def stub(kind):
    def replicate(*args, **kwargs):
        calls.append([kind, list(args), kwargs])
        cell, number = (args[0], args[1]) if kind == "power" else (0, args[0])
        return dict(cell="size" if kind == "size" else f"power_{cell}", cell_index=cell, replicate=number,
                    status="generation_failed", input=None, input_sha256=None, stub=True)
    return replicate
for module in (e1, e3):
    module.size_replicate, module.power_replicate = stub("size"), stub("power")
def prerequisite(*, master_seed, allow_registered=False):
    calls.append(["prerequisite", [], dict(master_seed=master_seed, allow_registered=allow_registered)])
    return dict(input_sha256=None, r0=dict(passed=True), agreement=dict(passed=True), at11=dict(passed=True),
                passed=True, stub=True)
e3.prerequisite_fixture = prerequisite
spec = importlib.util.spec_from_file_location("run_e_checks", root / "tools/run_e_checks.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
base = ["--registered", "--root", str(root)]
outcomes = {}
def attempt(label, arguments):
    try:
        outcomes[label] = runner.main(arguments)
    except SystemExit as error:
        outcomes[label] = f"refused: {error}"
attempt("e1 size", ["e1", "size", *base, "--out", str(out / "e1_size.jsonl")])
attempt("e3 size without prerequisite", ["e3", "size", *base, "--out", str(out / "e3_size.jsonl")])
attempt("e3 prerequisite", ["e3", "prerequisite", *base, "--out", str(out / "e3_prerequisite.jsonl")])
power = ["e3", "power", *base, "--out", str(out / "e3_power.jsonl"), "--prerequisite",
         str(out / "e3_prerequisite.jsonl"), "--cells", "2"]
attempt("e3 power", [*power, "--replicates", "0:3"])
attempt("e3 power resumed", [*power, "--replicates", "0:5"])
attempt("output inside the tree", ["e1", "power", *base, "--out", str(root / "audit/x.jsonl")])
(root / "stray.txt").write_text("x")
attempt("dirty tree", ["e1", "power", *base, "--out", str(out / "e1_power.jsonl")])
print(json.dumps(dict(outcomes=outcomes, calls=calls)))
'''


def test_registered_preflight_on_an_integrated_research_root_with_stubs(tmp_path):
    try:
        validation_runner.environment_identity(RESEARCH)
        subprocess.run(["git", "rev-parse", "-q", "--verify", "refs/tags/prereg-E3"], cwd=RESEARCH, check=True,
                       capture_output=True)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"needs the research checkout with its tags and the locked environment: {error}")
    if sys.version.split()[0] != runner.REGISTERED_PYTHON:
        pytest.skip("registered preflight needs Python 3.12.14")
    clone = tmp_path / "research"
    subprocess.run(["git", "clone", "-q", str(RESEARCH), str(clone)], check=True)   # origin = the checkout
    for path in [*(TREE / "src/uc_ext").glob("*.py"), TOOL]:
        target = clone / path.relative_to(TREE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    git(clone, "add", "-A")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=clone).returncode:
        git(clone, "commit", "-q", "-m", "integrate uc_ext (test)")
    head = git(clone, "rev-parse", "HEAD")
    (tmp_path / "wrapper.py").write_text(WRAPPER)
    out = tmp_path / "runs"
    out.mkdir()
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    completed = subprocess.run([sys.executable, str(tmp_path / "wrapper.py"), str(clone), str(out)],
                               capture_output=True, text=True, env=environment, cwd=clone)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.splitlines()[-1])
    outcomes, calls = result["outcomes"], result["calls"]
    assert outcomes["e1 size"] == 0 and outcomes["e3 prerequisite"] == 0
    assert outcomes["e3 power"] == 0 and outcomes["e3 power resumed"] == 0
    assert "--prerequisite" in outcomes["e3 size without prerequisite"]
    assert "git-ignored" in outcomes["output inside the tree"] and "clean" in outcomes["dirty tree"]
    size_calls = [call for call in calls if call[0] == "size"]
    power_calls = [call for call in calls if call[0] == "power"]
    assert len(size_calls) == 200 and sorted(call[1][0] for call in size_calls) == list(range(200))
    assert all(call[2] == dict(master_seed=1927, B=1000, allow_registered=True) for call in size_calls)
    assert [call[1] for call in power_calls] == [[2, r] for r in range(5)]
    assert all(call[2] == dict(master_seed=1927, B=1000, allow_registered=True, engine="batched",
                               check_agreement=True, retain_fits=True) for call in power_calls)
    manifest = lines(out / "e1_size.jsonl")[0]
    assert (manifest["mode"], manifest["master_seed"], manifest["n_series"], manifest["B"]) == ("registered", 1927, 200, 1000)
    assert manifest["gate"]["tag"] == "prereg-E1" and manifest["gate"]["registration_id"] == "mjg9w"
    assert manifest["gate"]["protocol_sha256"] == "d0d7b0859593b301a0af8bd9b5d48f92bcd3aef27082d9d7b6c4cf2d4e26e4fd"
    assert manifest["identity"]["commit"] == head and manifest["identity"]["dirty"] is False
    assert manifest["identity"]["python"] == "3.12.14" and manifest["lock"]["satisfied"] is True
    assert manifest["imported"]["sources"]["uc_ext/e3.py"] == runner._sha256_file(TREE / "src/uc_ext/e3.py")
    power = lines(out / "e3_power.jsonl")
    assert power[0]["gate"]["registration_id"] == "rhzsm"
    assert power[0]["settings"] == dict(engine="batched", check_agreement=True, grid_point_failure="discard",
                                        retention="all_fits")      # S6 default reading, S7 registered default
    assert power[0]["prerequisite"]["sha256"] == runner._sha256_file(out / "e3_prerequisite.jsonl")
    assert [r["record_type"] for r in power] == ["manifest", "session", *["replicate"] * 3, "session", *["replicate"] * 2]
    assert all(r["registered"] is True and r["master_seed"] == 1927 for r in power if r["record_type"] == "replicate")


# ------------------------------------------------------ S7: compressed retention of every surrogate fit

def test_retained_surrogate_fits_are_stored_compressed_and_reverified(tmp_path):
    import gzip
    out = tmp_path / "e3_size.jsonl"
    with pytest.raises(SystemExit):
        runner.main(["e1", "size", "--out", str(out), "--retention", "all_fits"])
    runner.main(["e3", "size", "--out", str(out), "--n-series", "2", "--B", "2", "--replicates", "0:1",
                 "--retention", "all_fits"])
    manifest, _, record = lines(out)
    assert manifest["settings"]["retention"] == record["settings"]["retention"] == "all_fits"
    assert record["surrogate_fits"] is None and record["surrogate_fits_count"] == 2
    fits = tmp_path / record["surrogate_fits_file"]
    assert fits.name == "size_000.json.gz" and runner._sha256_file(fits) == record["surrogate_fits_sha256"]
    payload = json.loads(gzip.decompress(fits.read_bytes()))
    assert list(payload)[0] == "manifest" and payload["manifest"] == manifest
    retained = [f for f in payload["surrogate_fits"].values() if f is not None]
    assert retained and all(len(f["grid_loglik"]) == 16 and "refinement" in f and "at_upper" in f for f in retained)
    original = fits.read_bytes()
    fits.write_bytes(gzip.compress(b"{}"))
    with pytest.raises(SystemExit, match="surrogate-fit file"):
        runner.main(["e3", "size", "--out", str(out), "--n-series", "2", "--B", "2", "--retention", "all_fits"])
    fits.unlink()
    with pytest.raises(SystemExit, match="surrogate-fit file"):
        runner.main(["e3", "summarize", "--out", str(out)])
    fits.write_bytes(original)
    runner.main(["e3", "size", "--out", str(out), "--n-series", "2", "--B", "2", "--retention", "all_fits"])
    assert [r["surrogate_fits_file"] for r in replicates(out)] == ["e3_size.jsonl.fits/size_000.json.gz",
                                                                    "e3_size.jsonl.fits/size_001.json.gz"]
    with pytest.raises(SystemExit):          # a resumed run must keep the file's retention setting
        runner.main(["e3", "size", "--out", str(out), "--n-series", "2", "--B", "2"])



# ------------------------------------------------------ C6: summarize combines split outputs

def test_summarize_combines_files_from_parallel_processes(tmp_path, capsys):
    first, second = tmp_path / "part0.jsonl", tmp_path / "part1.jsonl"
    runner.main(["e1", "power", "--out", str(first), "--n-series", "2", "--B", "2", "--cells", "0,1"])
    runner.main(["e1", "power", "--out", str(second), "--n-series", "2", "--B", "2", "--cells", "2,3"])
    capsys.readouterr()
    runner.main(["e1", "summarize", "--out", str(first), "--out", str(second)])
    result = json.loads(capsys.readouterr().out)
    assert [cell["attempted"] for cell in result["summary"]["cells"]] == [2, 2, 2, 2]
    assert [entry["records"] for entry in result["inputs"]] == [4, 4]
    with pytest.raises(SystemExit, match="repeats"):
        runner.main(["e1", "summarize", "--out", str(first), "--out", str(first)])
    other = tmp_path / "other.jsonl"
    runner.main(["e1", "power", "--out", str(other), "--n-series", "2", "--B", "3", "--cells", "2,3"])
    with pytest.raises(SystemExit, match="another run"):
        runner.main(["e1", "summarize", "--out", str(first), "--out", str(other)])
    with pytest.raises(SystemExit, match="Only summarize"):
        runner.main(["e1", "power", "--out", str(first), "--out", str(second)])
    capsys.readouterr()
