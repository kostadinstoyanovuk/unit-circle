"""The E2 X.3 runner in development mode on tiny sizes (2 series, B = 3), and its refusals.

Development seed 20260930 and development stream ids only; registered-mode refusals are exercised without the
registered environment.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = _module("run_e2_checks_under_test", "tools/run_e2_checks.py")


def run(*argv):
    return RUNNER.main(["e2", *argv])


def lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def test_manifest_and_records_repeat_mode_seed_settings_and_code(tmp_path):
    out = tmp_path / "size.jsonl"
    assert run("size", "--out", str(out), "--n-series", "2", "--B", "3") == 0
    manifest, session, *records = lines(out)
    assert manifest["record_type"] == "manifest" and session["record_type"] == "session"
    assert (manifest["extension"], manifest["check"], manifest["mode"], manifest["master_seed"]) == (
        "e2", "size", "development", 20260930)
    assert manifest["streams"]["size_generation"] == 9220 and manifest["streams"]["at12"] == 9012
    assert manifest["settings"]["power_onset_source"] == "development_fixture"
    assert manifest["identity_option"] == "e1-superset" and manifest["e1_code_sha256"] != manifest["code_sha256"]
    assert [r["replicate"] for r in records] == [0, 1]
    for record in records:
        assert record["registered"] is False and record["B"] == 3
        assert all(record[name] == manifest[name] for name in RUNNER.RECORD_FIELDS)
        assert "created_utc" not in record and "started_utc" not in record


def test_e1_code_hash_is_the_one_run_e_checks_computes():
    e1 = _module("run_e_checks_for_identity", "tools/run_e_checks.py")
    mine = RUNNER.run_identity(ROOT, registered=False)
    assert mine["e1_code_sha256"] == e1.run_identity(ROOT, registered=False)["code_sha256"]
    assert {"uc_e2/streams.py", "tools/run_e2_checks.py"} <= set(mine["imported"]["sources"])


def test_resume_reverifies_and_parts_concatenate_to_one_process(tmp_path):
    whole, part = tmp_path / "whole.jsonl", tmp_path / "part.jsonl"
    assert run("power", "--out", str(whole), "--n-series", "2", "--B", "3", "--cells", "3") == 0
    assert run("power", "--out", str(part), "--n-series", "2", "--B", "3", "--cells", "3", "--replicates", "0:1") == 0
    assert run("power", "--out", str(part), "--n-series", "2", "--B", "3", "--cells", "3") == 0
    replicate_lines = [[line for line in Path(p).read_text().splitlines() if '"record_type": "replicate"' in line]
                       for p in (whole, part)]
    assert replicate_lines[0] == replicate_lines[1] and len(replicate_lines[0]) == 2
    assert sum(r["record_type"] == "session" for r in lines(part)) == 2


def test_altered_record_foreign_manifest_and_truncated_line_are_refused(tmp_path):
    out = tmp_path / "size.jsonl"
    assert run("size", "--out", str(out), "--n-series", "2", "--B", "3", "--replicates", "0:1") == 0
    with pytest.raises(SystemExit, match="another run"):
        run("size", "--out", str(out), "--n-series", "2", "--B", "4")
    original = out.read_text()
    altered = original.replace('"input": [[', '"input": [[1.0, 0.0], [', 1)
    out.write_text(altered)
    with pytest.raises(SystemExit, match="input"):
        run("size", "--out", str(out), "--n-series", "2", "--B", "3")
    out.write_text(original.rstrip("\n"))
    with pytest.raises(SystemExit, match="truncated"):
        run("size", "--out", str(out), "--n-series", "2", "--B", "3")


def test_summarize_needs_disjoint_parts_of_one_run(tmp_path, capsys):
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    assert run("size", "--out", str(first), "--n-series", "2", "--B", "3", "--replicates", "0:1") == 0
    assert run("size", "--out", str(second), "--n-series", "2", "--B", "3", "--replicates", "1:2") == 0
    capsys.readouterr()
    assert run("summarize", "--out", str(first), "--out", str(second)) == 0
    printed = json.loads(capsys.readouterr().out)
    assert [entry["records"] for entry in printed["inputs"]] == [1, 1]
    assert printed["summary"]["cell"]["requested"] == 2 and printed["summary"]["passed"] is False
    with pytest.raises(SystemExit, match="repeats coordinates"):
        run("summarize", "--out", str(first), "--out", str(first))


def test_development_prerequisite_record_passes_and_is_written_once(tmp_path):
    out = tmp_path / "prerequisite.jsonl"
    assert run("prerequisite", "--out", str(out)) == 0
    manifest, record = lines(out)
    assert record["record_type"] == "prerequisite" and RUNNER.prerequisite_passed(record)
    assert record["f4"]["passed"] is True and record["unit_tests"] == ["tests/test_e2_data_rules.py"]
    with pytest.raises(SystemExit, match="never overwritten"):
        run("prerequisite", "--out", str(out))
    size = tmp_path / "size.jsonl"
    assert run("size", "--out", str(size), "--n-series", "1", "--B", "2", "--prerequisite", str(out)) == 0
    assert lines(size)[-1]["prerequisite_sha256"] == lines(size)[0]["prerequisite"]["sha256"]


@pytest.mark.parametrize("argv, message", [
    (["size", "--registered"], "--root"),
    (["size", "--registered", "--root", ".", "--n-series", "2"], "registered sizes"),
    (["size", "--registered", "--root", "/"], "research root"),
    (["size", "--cells", "1"], "power check only"),
    (["power", "--cells", "4"], "kappa indices"),
    (["size", "--replicates", "2:1"], "outside"),
    (["size", "--n-series", "201"], "1 to 200"),
])
def test_refusals_before_any_computation(tmp_path, argv, message):
    with pytest.raises(SystemExit, match=message):
        run(*argv, "--out", str(tmp_path / "x.jsonl"))
    assert not (tmp_path / "x.jsonl").exists()


# ------------------------------------------------------------------------------------- code identity

def research_copy(tmp_path):
    """A copy of the files the X.3 identity reads, as a separate git repository (test-only)."""
    root = tmp_path / "research"
    for package in ("uc_core", "uc_ext", "uc_e2"):
        shutil.copytree(ROOT / "src" / package, root / "src" / package, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("tools/run_e_checks.py", "tools/run_e2_checks.py", "tools/run_validation.py",
                 "tools/verify_validation_runner.py", "prereg/H1.md", "requirements.lock"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, root / name)
    (root / ".gitignore").write_text("__pycache__/\nruns/\n")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "constructed research root"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=root,
                       check=True, capture_output=True)
    return root


IDENTITY = r'''
import importlib.util, json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "src"))
spec = importlib.util.spec_from_file_location("run_e2_checks", root / "tools/run_e2_checks.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
def identity():
    value = runner.run_identity(root, registered=False)
    return [value["code_sha256"], value["e1_code_sha256"]]
results = dict(base=identity())
for name in ("src/uc_e2/streams.py", "tools/run_e2_checks.py", "src/uc_ext/common.py"):
    path = root / name
    original = path.read_bytes()
    path.write_bytes(original + b"# constructed change\n")
    results[name] = identity()
    path.write_bytes(original)
results["restored"] = identity()
print(json.dumps(results))
'''


def test_identity_changes_with_uc_e2_and_the_runner_but_its_e1_part_only_with_e1_code(tmp_path):
    here = RUNNER.run_identity(ROOT, registered=False)
    root = research_copy(tmp_path)
    script = tmp_path / "identity.py"
    script.write_text(IDENTITY)
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run([sys.executable, str(script), str(root)], capture_output=True, text=True,
                               env=environment, cwd=root)
    assert completed.returncode == 0, completed.stderr
    results = json.loads(completed.stdout.splitlines()[-1])
    code, e1_code = results["base"]
    assert (code, e1_code) == (here["code_sha256"], here["e1_code_sha256"])        # the bytes decide
    for name in ("src/uc_e2/streams.py", "tools/run_e2_checks.py"):
        assert results[name][0] != code and results[name][1] == e1_code, name
    assert results["src/uc_ext/common.py"][0] != code and results["src/uc_ext/common.py"][1] != e1_code
    assert results["restored"] == [code, e1_code]
