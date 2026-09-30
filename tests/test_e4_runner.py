"""The E4 X.3 runner (tools/run_e4_checks.py): development runs on constructed data at tiny sizes (2 series,
B = 9), resume with re-verification, splitting, summaries, the code identity and the fail-closed registered path.

Registered mode is exercised only for its refusals, on throwaway repositories, in a subprocess that replaces
uc_e4's generator constructor by a guard that raises if a generator from the registered seed 1927 is requested
and replaces the replicate functions by stubs. No test starts a registered computation. The results are those
of this interpreter; registered results come only from Python 3.12.14 under the research lock.
"""
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from uc_core import validation_runner
from uc_e4 import synthetic as Y
from uc_e4.streams import DEVELOPMENT_SEED as DEV, DEVELOPMENT_STREAMS as DS
from uc_ext import common as c

TREE = Path(__file__).resolve().parents[1]
TOOL = TREE / "tools/run_e4_checks.py"
spec = importlib.util.spec_from_file_location("run_e4_checks_under_test", TOOL)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
E1 = runner.e1_runner()
SMALL = ["--n-series", "2", "--B", "9"]


def lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def replicate_lines(path):
    return [line for line in Path(path).read_text().splitlines() if json.loads(line)["record_type"] == "replicate"]


def run(check, out, *extra, small=SMALL):
    return runner.main(["e4", check, "--out", str(out), *small, *extra])


def keys_of(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(keys_of(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(set(), *(keys_of(v) for v in value))
    return set()


# ------------------------------------------------------------------------ manifest, session, record

def test_manifest_session_and_record_contents(tmp_path, monkeypatch):
    monkeypatch.setenv("OMP_NUM_THREADS", "1")
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "2")
    monkeypatch.delenv("MKL_NUM_THREADS", raising=False)
    before = dict(os.environ)
    out = tmp_path / "size.jsonl"
    assert run("size", out, "--replicates", "0:1") == 0
    assert dict(os.environ) == before                   # the runner records the thread settings, never sets them
    manifest, session, record = lines(out)
    assert (manifest["record_type"], manifest["schema"], manifest["extension"], manifest["check"], manifest["mode"],
            manifest["master_seed"], manifest["n_series"], manifest["B"], manifest["kappas"]) == (
        "manifest", 2, "e4", "size", "development", DEV, 2, 9, None)
    assert manifest["settings"] == {} and manifest["gate"] is None and manifest["prerequisite"] is None
    assert manifest["streams"] == asdict(DS) and min(manifest["streams"].values()) >= 9000
    assert manifest["identity_option"] == "e1-superset"
    e1 = E1.run_identity(TREE, registered=False)
    assert manifest["identity"] == e1["identity"] and manifest["lock"] == e1["lock"]
    assert manifest["e1_code_sha256"] == e1["code_sha256"]
    sources = manifest["imported"]["sources"]
    e4_names = {f"uc_e4/{p.name}" for p in (TREE / "src/uc_e4").glob("*.py")} | {"tools/run_e4_checks.py"}
    assert set(sources) == set(e1["imported"]["sources"]) | e4_names
    for name, digest in sources.items():
        path = TREE / name if name.startswith("tools/") else TREE / "src" / name
        assert digest == hashlib.sha256(path.read_bytes()).hexdigest(), name
    canonical = json.dumps(dict(environment=manifest["identity"]["source_sha256"], imported=sources), sort_keys=True,
                           separators=(",", ":"))
    assert manifest["code_sha256"] == hashlib.sha256(canonical.encode()).hexdigest()
    assert session["record_type"] == "session" and session["cells"] == [0] and session["replicates"] == [0, 1]
    assert session["threads"] == dict(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS=None)
    for name, value in dict(record_type="replicate", registered=False, mode="development", master_seed=DEV, B=9,
                            settings={}, code_sha256=manifest["code_sha256"], cell="size", cell_index=0,
                            replicate=0, kappa=1.0, status="ok").items():
        assert record[name] == value, name
    assert record["input_sha256"] == c.sha256_values(Y.x3_input("size", 0, 0, master_seed=DEV, streams=DS))
    attempts = record["comparison"]["attempts"]
    assert len(attempts) == 9 and all(len(a["changes"]) == 5 and a["status"] == "retained" for a in attempts)
    for a in attempts:                                  # every attempt keeps its statistic and its five components
        assert a["statistic"] == pytest.approx(sum(a["changes"]) / 5, abs=1e-12)
    exceedances = sum(a["statistic"] >= record["S"] for a in attempts)
    assert record["p_value"] == (1 + exceedances) / (9 + 1)
    assert not {k for k in keys_of(record) if "utc" in k.lower() or "time" in k.lower()}


# ----------------------------------------------------------------------------- resume, determinism

def test_resume_skips_saved_coordinates_and_gives_the_uninterrupted_bytes(tmp_path):
    out, fresh = tmp_path / "resumed.jsonl", tmp_path / "fresh.jsonl"
    run("size", out, "--replicates", "0:1")
    run("size", out)
    assert [r["record_type"] for r in lines(out)] == ["manifest", "session", "replicate", "session", "replicate"]
    assert lines(out)[3]["resumed_records"] == 1
    run("size", fresh)
    assert replicate_lines(out) == replicate_lines(fresh)        # same coordinates, same record bytes


def test_parts_concatenate_to_the_records_of_one_process(tmp_path):
    whole = tmp_path / "whole.jsonl"
    run("power", whole, "--cells", "2,3")
    parts = [(tmp_path / "p1.jsonl", ["--cells", "2", "--replicates", "0:1"]),
             (tmp_path / "p2.jsonl", ["--cells", "2", "--replicates", "1:2"]),
             (tmp_path / "p3.jsonl", ["--cells", "3"])]
    for path, extra in parts:
        run("power", path, *extra)
    assert sum((replicate_lines(path) for path, _ in parts), []) == replicate_lines(whole)
    assert [(r["cell_index"], r["replicate"], r["kappa"]) for r in map(json.loads, replicate_lines(whole))] == [
        (2, 0, 1.4), (2, 1, 1.4), (3, 0, 1.6), (3, 1, 1.6)]


# -------------------------------------------------------------------- refusals before anything is written

def _tampered(tmp_path, name, source, change):
    rows = lines(source)
    change(rows)
    path = tmp_path / name
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def test_resume_refuses_foreign_manifests_altered_records_and_truncated_lines(tmp_path):
    source = tmp_path / "source.jsonl"
    run("size", source, "--replicates", "0:1")
    other = Y.x3_input("size", 0, 1, master_seed=DEV, streams=DS)

    def record(**changes):
        return lambda rows: rows[2].update(changes)

    def manifest(**changes):
        return lambda rows: rows[0].update(changes)

    def alter_input(rows):
        rows[2]["input"][5] += 1e-9

    def other_coordinates(rows):
        rows[2].update(input=other.tolist(), input_sha256=c.sha256_values(other))

    cases = dict(
        other_B=(None, ["--n-series", "2", "--B", "3"]), other_n_series=(None, ["--n-series", "3", "--B", "9"]),
        manifest_seed=(manifest(master_seed=DEV + 1), SMALL), manifest_code=(manifest(code_sha256="0" * 64), SMALL),
        manifest_e1_code=(manifest(e1_code_sha256="0" * 64), SMALL),
        manifest_identity_option=(manifest(identity_option="other"), SMALL),
        manifest_streams=(lambda rows: rows[0]["streams"].update(size_null=9999), SMALL),
        manifest_commit=(lambda rows: rows[0]["identity"].update(commit="0" * 40), SMALL),
        manifest_packages=(lambda rows: rows[0]["identity"]["packages"].update(numpy="0"), SMALL),
        manifest_schema=(manifest(schema=1), SMALL), no_manifest=(lambda rows: rows.pop(0), SMALL),
        second_manifest=(lambda rows: rows.append(dict(rows[0])), SMALL),
        record_mode=(record(mode="registered"), SMALL), record_registered=(record(registered=True), SMALL),
        record_seed=(record(master_seed=DEV + 1), SMALL), record_B=(record(B=10), SMALL),
        record_settings=(record(settings=dict(engine="other")), SMALL),
        record_code=(record(code_sha256="0" * 64), SMALL), record_outside=(record(replicate=7), SMALL),
        record_cell=(record(cell="power_0"), SMALL), record_kappa=(record(kappa=1.2), SMALL),
        altered_input=(alter_input, SMALL), input_from_other_coordinates=(other_coordinates, SMALL),
        duplicate=(lambda rows: rows.append(rows[2]), SMALL),
        unknown_line=(lambda rows: rows.append(dict(record_type="note")), SMALL),
    )
    for name, (change, small) in cases.items():
        path = source if change is None else _tampered(tmp_path, f"{name}.jsonl", source, change)
        before = path.read_bytes()
        with pytest.raises(SystemExit):
            run("size", path, small=small)
        assert path.read_bytes() == before, name              # nothing is appended to a refused file
    data = source.read_bytes()
    for name, cut in dict(half_line=data[:len(data) - 100], no_newline=data[:-1]).items():
        path = tmp_path / f"{name}.jsonl"
        path.write_bytes(cut)
        with pytest.raises(SystemExit, match="truncated"):
            run("size", path)
        with pytest.raises(SystemExit, match="truncated"):
            runner.main(["e4", "summarize", "--out", str(path)])
        assert path.read_bytes() == cut, name
    run("size", source)
    assert [r["replicate"] for r in map(json.loads, replicate_lines(source))] == [0, 1]


def test_arguments_outside_the_design_are_refused(tmp_path):
    for extra in (["--replicates", "1:1"], ["--replicates", "0:3"], ["--replicates", "a:b"], ["--cells", "0"]):
        with pytest.raises(SystemExit):
            run("size", tmp_path / "x.jsonl", *extra)
    for extra in (["--cells", "4"], ["--cells", "1,1"], ["--cells", "x"]):
        with pytest.raises(SystemExit):
            run("power", tmp_path / "x.jsonl", *extra)
    for small in (["--n-series", "201"], ["--n-series", "0"], ["--B", "0"]):
        with pytest.raises(SystemExit):
            run("size", tmp_path / "x.jsonl", small=small)
    with pytest.raises(SystemExit, match="Only summarize"):
        runner.main(["e4", "size", "--out", str(tmp_path / "a.jsonl"), "--out", str(tmp_path / "b.jsonl")])
    with pytest.raises(SystemExit, match="registered sizes"):
        runner.main(["e4", "size", "--out", str(tmp_path / "x.jsonl"), "--registered", "--root", str(TREE),
                     "--B", "9"])
    assert not (tmp_path / "x.jsonl").exists()
    assert runner.work_coordinates("power", n_series=3, cells="3,1", replicates="1:3") == [
        (1, 1), (1, 2), (3, 1), (3, 2)]


# -------------------------------------------------------------------------------------- summarize

def test_summarize_combines_disjoint_parts_and_refuses_overlaps_and_foreign_files(tmp_path, capsys):
    first, second, overlapping = tmp_path / "r0.jsonl", tmp_path / "r1.jsonl", tmp_path / "r01.jsonl"
    run("size", first, "--replicates", "0:1")
    run("size", second, "--replicates", "1:2")
    capsys.readouterr()
    runner.main(["e4", "summarize", "--out", str(first), "--out", str(second)])
    result = json.loads(capsys.readouterr().out)
    assert list(result) == ["manifest", "inputs", "summary"] and result["manifest"]["check"] == "summarize"
    assert [entry["records"] for entry in result["inputs"]] == [1, 1]
    assert result["inputs"][0]["sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()
    assert result["inputs"][0]["manifest"] == runner.fingerprint(lines(first)[0])
    cell = result["summary"]["cell"]
    assert (cell["requested"], cell["attempted"], cell["valid"]) == (2, 2, 2)
    assert result["summary"]["registered_design"] is False and result["summary"]["passed"] is False
    assert tuple(result["summary"]["bounds"]) == Y.SIZE_BOUNDS
    run("size", overlapping)
    for files, message in (([first, first], "repeats"), ([first, overlapping], "repeats")):
        with pytest.raises(SystemExit, match=message):
            runner.main(["e4", "summarize", *sum((["--out", str(p)] for p in files), [])])
    foreign = tmp_path / "foreign.jsonl"
    run("size", foreign, "--replicates", "1:2", small=["--n-series", "2", "--B", "3"])
    power = tmp_path / "power.jsonl"
    run("power", power, "--cells", "0", "--replicates", "1:2", small=["--n-series", "2", "--B", "3"])
    for files in ([first, foreign], [foreign, power]):
        with pytest.raises(SystemExit, match="another run"):
            runner.main(["e4", "summarize", *sum((["--out", str(p)] for p in files), [])])
    altered = _tampered(tmp_path, "altered.jsonl", second, lambda rows: rows[2]["input"].__setitem__(0, 0.0))
    with pytest.raises(SystemExit, match="input"):
        runner.main(["e4", "summarize", "--out", str(first), "--out", str(altered)])
    capsys.readouterr()


# ------------------------------------------------------------------------------------- code identity

def research_copy(tmp_path, *, with_git=True):
    """A copy of the files the X.3 identity and gate read, as a separate git repository (test-only)."""
    root = tmp_path / "research"
    for package in ("uc_core", "uc_ext", "uc_e4"):
        shutil.copytree(TREE / "src" / package, root / "src" / package, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("tools/run_e_checks.py", "tools/run_e4_checks.py", "tools/run_validation.py",
                 "tools/verify_validation_runner.py", "prereg/H1.md", "prereg/E4.md", "requirements.lock"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(TREE / name, root / name)
    (root / ".gitignore").write_text("__pycache__/\nruns/\n")
    if with_git:
        git(root, "init", "-q")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "constructed research root")
    return root


def git(root, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=root,
                          check=True, capture_output=True, text=True).stdout.strip()


def subprocess_json(tmp_path, script, *arguments, cwd):
    path = tmp_path / "wrapper.py"
    path.write_text(script)
    environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run([sys.executable, str(path), *map(str, arguments)], capture_output=True, text=True,
                               env=environment, cwd=cwd)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.splitlines()[-1])


IDENTITY = r'''
import importlib.util, json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / "src"))
spec = importlib.util.spec_from_file_location("run_e4_checks", root / "tools/run_e4_checks.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
def identity():
    value = runner.run_identity(root, registered=False)
    return [value["code_sha256"], value["e1_code_sha256"], value["lock"]["satisfied"]]
results = dict(base=identity())
for name in ("src/uc_e4/streams.py", "tools/run_e4_checks.py", "src/uc_ext/common.py", "prereg/H1.md"):
    path = root / name
    original = path.read_bytes()
    path.write_bytes(original + b"# constructed change\n")
    results[name] = identity()
    path.write_bytes(original)
results["restored"] = identity()
print(json.dumps(results))
'''


def test_identity_is_the_e1_identity_plus_uc_e4_and_this_runner(tmp_path):
    here = runner.run_identity(TREE, registered=False)
    e1 = E1.run_identity(TREE, registered=False)
    assert here["e1_code_sha256"] == e1["code_sha256"] and here["identity"] == e1["identity"]
    assert here["identity_option"] == "e1-superset" and here["code_sha256"] != e1["code_sha256"]
    if here["lock"]["satisfied"] is not True:
        pytest.skip("the sensitivity check needs the research lock (the environment part of the identity)")
    root = research_copy(tmp_path)
    results = subprocess_json(tmp_path, IDENTITY, root, cwd=root)
    code, e1_code, lock = results["base"]
    assert lock is True and (code, e1_code) == (here["code_sha256"], here["e1_code_sha256"])   # bytes decide
    assert results["src/uc_e4/streams.py"][0] != code and results["src/uc_e4/streams.py"][1] == e1_code
    assert results["tools/run_e4_checks.py"][0] != code and results["tools/run_e4_checks.py"][1] == e1_code
    for name in ("src/uc_ext/common.py", "prereg/H1.md"):
        assert results[name][0] != code and results[name][1] != e1_code, name
    assert results["restored"][:2] == [code, e1_code]


# ---------------------------------------------------------------- registered mode: refusals only

REGISTERED = r'''
from dataclasses import asdict
import importlib.util, json, platform, sys
from pathlib import Path
root, steps = Path(sys.argv[1]).resolve(), json.loads(sys.argv[2])
sys.path.insert(0, str(root / "src"))
from uc_e4 import streams, synthetic
original = streams.stream_rng
def guarded(master_seed, *args, **kwargs):
    if int(master_seed) == 1927:
        raise RuntimeError("test guard: a generator from the registered seed was requested")
    return original(master_seed, *args, **kwargs)
streams.stream_rng = synthetic.stream_rng = guarded
calls = []
def stub(kind):
    def replicate(*args, **kwargs):
        calls.append([kind, list(args), kwargs["master_seed"], kwargs["B"], kwargs["allow_registered"],
                      asdict(kwargs["streams"])])
        cell, number = (args[0], args[1]) if kind == "power" else (0, args[0])
        return dict(cell="size" if kind == "size" else f"power_{cell}", cell_index=cell, replicate=number,
                    status="generation_failed", input=None, input_sha256=None,
                    kappa=1.0 if kind == "size" else synthetic.KAPPAS[cell], stub=True)
    return replicate
synthetic.size_replicate, synthetic.power_replicate = stub("size"), stub("power")
spec = importlib.util.spec_from_file_location("run_e4_checks", root / "tools/run_e4_checks.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
e1 = runner.e1_runner()
if platform.python_version() == e1.REGISTERED_PYTHON:   # the refusal of another interpreter, on any interpreter
    e1.REGISTERED_PYTHON = "3.12.14 (another build)"
outcomes = {}
for label, arguments in steps:
    try:
        outcomes[label] = runner.main(arguments)
    except SystemExit as error:
        outcomes[label] = f"refused: {error}"
print(json.dumps(dict(outcomes=outcomes, calls=calls)))
'''


def _receipt(root):
    protocol = hashlib.sha256((root / "prereg/E4.md").read_bytes()).hexdigest()
    return dict(registration_id="test4", doi="10.0/TEST4", prereg_tag="prereg-E4",
                prereg_tag_commit=git(root, "rev-parse", "prereg-E4^{commit}"),
                api_date_registered_utc="2026-09-30T06:00:00Z", public_first_verified_at_utc="2026-09-30T06:30:00Z",
                anonymous_api_check=dict(public=True, pending_registration_approval=False, embargoed=False,
                                         withdrawn=False, archiving=False, revision_state="approved"),
                expected_attachment_sha256={"prereg/E4.md": protocol},
                archived_attachments=[dict(file_name="E4.md", osf_sha256=protocol, downloaded_sha256=protocol)],
                archived_attachment_bytes_verified=True)


def test_registered_mode_refuses_wrong_root_untagged_or_dirty_tree_output_inside_and_other_interpreter(tmp_path):
    """Temporary repositories only: every attempt below must be refused before any replicate is computed."""
    try:
        validation_runner.environment_identity(TREE)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"needs the locked environment: {error}")
    root = research_copy(tmp_path)
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    git(root, "remote", "add", "origin", str(origin))
    outside = tmp_path / "outputs"
    outside.mkdir()
    base = ["--registered", "--root", str(root)]

    def attempt(*steps):
        return subprocess_json(tmp_path, REGISTERED, root, json.dumps(steps), cwd=root)

    first = attempt(["wrong root", ["e4", "size", "--registered", "--root", str(tmp_path), "--out",
                                    str(outside / "a.jsonl")]],
                    ["development size", ["e4", "size", *base, "--n-series", "2", "--out", str(outside / "a.jsonl")]],
                    ["untagged", ["e4", "size", *base, "--out", str(outside / "a.jsonl")]])
    outcomes = first["outcomes"]
    assert "research root" in outcomes["wrong root"] and "registered sizes" in outcomes["development size"]
    assert "prereg-E4 is absent" in outcomes["untagged"]
    git(root, "tag", "-a", "prereg-E4", "-m", "E4 registered (constructed)")
    git(root, "push", "-q", "origin", "HEAD", "--tags")
    (root / "audit").mkdir()
    (root / "audit/E4_REGISTRATION.json").write_text(json.dumps(_receipt(root), indent=1) + "\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "registration record (constructed)")
    (root / "stray.txt").write_text("uncommitted\n")
    dirty = attempt(["dirty", ["e4", "power", *base, "--out", str(outside / "b.jsonl")]])
    assert "clean research checkout" in dirty["outcomes"]["dirty"]
    (root / "stray.txt").unlink()
    last = attempt(["inside", ["e4", "size", *base, "--out", str(root / "audit/x3.jsonl")]],
                   ["interpreter", ["e4", "size", *base, "--replicates", "0:25", "--out", str(outside / "c.jsonl")]],
                   ["summarize", ["e4", "summarize", *base, "--out", str(outside / "c.jsonl")]])
    outcomes = last["outcomes"]
    assert "git-ignored" in outcomes["inside"]
    assert "Python" in outcomes["interpreter"] and "Python" in outcomes["summarize"]
    assert first["calls"] == dirty["calls"] == last["calls"] == []        # no replicate was ever started
    assert not list(outside.iterdir()) and not (root / "audit/x3.jsonl").exists()
    assert git(root, "status", "--porcelain") == ""
