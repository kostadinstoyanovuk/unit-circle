"""E4 X.3 entry point, development copy (prereg/E4.md section 11, Annex B step 3).

One process runs one slice of one check; the five checks are separate streams: `size` (200 series at the
base process) and `power0` to `power3` (200 series each at kappa 1.0, 1.2, 1.4, 1.6), every series analysed at
its five truncation-only vintages (uc_e4.synthetic). Splitting the replicates across processes is what
shortens the run, so a slice is the unit of work:

  python run_e4_checks.py size   --out-dir DIR --n-series 2 --B 9 --replicates 0:1
  python run_e4_checks.py power2 --out-dir DIR --n-series 2 --B 9 --replicates 0:2

A slice a:b is half-open and zero-based, 0 <= a < b <= n_series, n_series <= 200 (the registered count).
Files in DIR, per slice: `<check>.<aaa>-<bbb>.jsonl` (one JSON line per replicate, nothing else, no time
stamp, so the slice files of one check, in replicate order, concatenate byte for byte to the file a single
process writes for 0:n_series) and `<check>.<aaa>-<bbb>.manifest.json` (the manifest of that slice: code
identity fields, seed, streams, B, n_series, slice, interpreter and package versions, start and end markers,
session log). Guards, all checked before anything is computed or written:
  - a slice file is resumed only under a manifest that matches this run (fingerprint), after every saved
    record is re-verified (its fields, its stored input against input_sha256 and against the series its seed
    coordinates regenerate); a truncated final line (no newline) is dropped and recomputed, a complete line
    that does not parse is refused;
  - a slice that overlaps a recorded slice of the same check is refused;
  - a new slice (a gap-fill) must match the recorded slices of its check: same fingerprint;
  - only development coordinates: the registered master seed 1927, registered stream ids and `--registered`
    are refused (registered mode needs the gate and the integrated code location, READINGS.md R-X3.1/R-X3.2).
No data file is read. Every run is a development run and a cloud rehearsal unless made on the registered
interpreter by the gated registered mode that does not exist yet.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]          # the research root that holds this runner
if str(HERE / "src") not in sys.path:
    sys.path.insert(0, str(HERE / "src"))

SCHEMA = 1
REGISTERED_SERIES = 200
CHECKS = ("size", "power0", "power1", "power2", "power3")
IDENTITY_OPTION = "1"      # R-X3.1 option 1: the code lives in uc_e4/ and this runner, outside E1's identity
FINGERPRINT = ("schema", "extension", "check", "cell", "kappa", "mode", "master_seed", "streams", "B",
               "n_series", "identity_option", "code_sha256", "e1_code_sha256", "python", "packages",
               "lock_satisfied")
RECORD_FIELDS = ("mode", "master_seed", "B", "code_sha256")          # repeated in every replicate record
ENVIRONMENT_FILES = ("tools/run_validation.py", "tools/verify_validation_runner.py", "prereg/H1.md",
                     "requirements.lock")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha256(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ------------------------------------------------------------------------------------ code identity
def environment_sources(root) -> dict:
    """The environment part of the identity: what uc_core.validation_runner.environment_identity hashes
    (src/uc_core/*.py, the two validation tools, prereg/H1.md, requirements.lock), recomputed from the files
    without its installed-package check, so that it also works outside the lock."""
    root = Path(root)
    names = sorted(str(p.relative_to(root)).replace("\\", "/") for p in (root / "src/uc_core").glob("*.py"))
    names += list(ENVIRONMENT_FILES)
    missing = [n for n in names if not (root / n).is_file()]
    if missing:
        raise SystemExit(f"Not a research root: missing {missing}")
    return {n: sha256_file(root / n) for n in names}


def code_identity(root, package_dir=None, runner_path=None) -> dict:
    """R-X3.1, option 1. E4's identity hashes the environment part, every src/uc_core and src/uc_ext source,
    tools/run_e_checks.py (so that the set contains E1's), every uc_e4 source and this runner.

    `e1_code_sha256` recomputes E1's own identity, which hashes the same environment part and only the
    uc_core and uc_ext sources and tools/run_e_checks.py: it does not change when uc_e4 or this runner
    change, and equals the identity of the E1 synthetic checks while those files are untouched.
    """
    root = Path(root)
    package_dir = Path(package_dir) if package_dir else HERE / "src" / "uc_e4"
    runner_path = Path(runner_path) if runner_path else Path(__file__).resolve()
    environment = environment_sources(root)
    e1_sources = {}
    for name in ("uc_ext", "uc_core"):
        for path in sorted((root / "src" / name).glob("*.py")):
            e1_sources[f"{name}/{path.name}"] = sha256_file(path)
    e1_sources["tools/run_e_checks.py"] = sha256_file(root / "tools/run_e_checks.py")
    e4_sources = dict(e1_sources)
    for path in sorted(package_dir.glob("*.py")):
        e4_sources[f"uc_e4/{path.name}"] = sha256_file(path)
    e4_sources["tools/run_e4_checks.py"] = sha256_file(runner_path)
    return dict(option=IDENTITY_OPTION,
                code_sha256=canonical_sha256(dict(environment=environment, imported=e4_sources)),
                e1_code_sha256=canonical_sha256(dict(environment=environment, imported=e1_sources)),
                environment_sources=environment, sources=e4_sources)


def installed_packages(root):
    """Installed versions of the lock's packages (None if absent) and whether the lock is satisfied."""
    versions, satisfied = {}, True
    for line in (Path(root) / "requirements.lock").read_text().splitlines():
        if "==" in line and not line.startswith("#"):
            name, version = line.strip().split("==")[:2]
            try:
                installed = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                installed = None
            versions[name] = installed
            satisfied = satisfied and installed == version
    return versions, satisfied


# ---------------------------------------------------------------------------------------- arguments
def parse_slice(text, n_series):
    """'a:b' half-open, zero-based, 0 <= a < b <= n_series (n_series itself at most the registered 200)."""
    match = re.fullmatch(r"(\d+):(\d+)", text or "")
    if not match:
        raise SystemExit(f"--replicates must read a:b (two non-negative integers), not {text!r}")
    a, b = int(match.group(1)), int(match.group(2))
    if not 0 <= a < b <= n_series:
        raise SystemExit(f"--replicates {a}:{b} is outside 0 <= a < b <= {n_series} "
                         f"(half-open, zero-based, bounded by the number of series)")
    return a, b


def _cell_of(check):
    return None if check == "size" else int(check[len("power"):])


# ------------------------------------------------------------------------------------ manifest, files
def fingerprint(manifest) -> dict:
    return {key: manifest.get(key) for key in FINGERPRINT}


def slice_paths(out_dir, check, a, b):
    base = Path(out_dir) / f"{check}.{a:03d}-{b:03d}"
    return base.with_name(base.name + ".jsonl"), base.with_name(base.name + ".manifest.json")


def recorded_slices(out_dir, check):
    """[(a, b, manifest, path)] of every manifest of this check in out_dir, names checked against contents."""
    found = []
    for path in sorted(Path(out_dir).glob(f"{check}.*.manifest.json")):
        match = re.fullmatch(rf"{re.escape(check)}\.(\d+)-(\d+)\.manifest\.json", path.name)
        if not match:
            continue
        try:
            manifest = json.loads(path.read_text())
        except ValueError as error:
            raise SystemExit(f"{path} is not readable JSON: {error}") from error
        if manifest.get("slice") != [int(match.group(1)), int(match.group(2))] or manifest.get("check") != check:
            raise SystemExit(f"{path} records another slice or check than its name says")
        found.append((int(match.group(1)), int(match.group(2)), manifest, path))
    return found


def write_manifest(path, manifest):
    temporary = Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=1, default=str) + "\n")
    os.replace(temporary, path)


def read_complete_lines(path):
    """(records, bytes of a truncated final line, offset to cut at). A line is complete when it ends in a
    newline and parses; a partial last line is reported, never parsed; a complete line that does not parse is
    refused. The file is not modified here."""
    data = Path(path).read_bytes()
    cut = data.rfind(b"\n") + 1
    dropped = len(data) - cut
    records = []
    for number, line in enumerate(data[:cut].split(b"\n")[:-1]):
        try:
            records.append(json.loads(line))
        except ValueError as error:
            raise SystemExit(f"{path}, line {number + 1}: a complete line does not parse "
                             f"(not a truncation; refused): {error}") from error
    return records, dropped, cut


def x3_input(check, replicate, *, seed, streams):
    """The series of one replicate, regenerated from its seed coordinates alone (as run_e_checks.verify_saved)."""
    from uc_core.validation_design import h1_design_series
    from uc_e4 import synthetic as Y
    from uc_e4.streams import stream_rng
    cell = _cell_of(check)
    if cell is None:
        return h1_design_series(stream_rng(seed, streams.size_generation, 0, replicate), kappa=1.0)
    return h1_design_series(stream_rng(seed, streams.power_generation, cell, replicate), kappa=Y.KAPPAS[cell])


def verify_saved(records, manifest, *, streams):
    """Every saved record belongs to this slice and run, in order from a, and its input is the one its seed
    coordinates generate."""
    from uc_ext import common as c
    a, b = manifest["slice"]
    check, cell = manifest["check"], manifest["cell"]
    for offset, record in enumerate(records):
        replicate, where = a + offset, f"Saved record {offset} of slice {a}:{b}"
        if record.get("record_type") != "replicate" or record.get("replicate") != replicate:
            raise SystemExit(f"{where} is not replicate {replicate} (records must run a, a+1, ... without gaps)")
        if record.get("cell_index") != (0 if cell is None else cell) or record.get("cell") != (
                "size" if cell is None else f"power_{cell}"):
            raise SystemExit(f"{where} belongs to another cell than {check}")
        for name in RECORD_FIELDS:
            if record.get(name) != manifest[name]:
                raise SystemExit(f"{where}: {name} differs from the manifest")
        if record.get("input") is None or c.sha256_values(record["input"]) != record.get("input_sha256"):
            raise SystemExit(f"{where}: the stored input does not match input_sha256")
        if c.sha256_values(x3_input(check, replicate, seed=manifest["master_seed"], streams=streams)) \
                != record["input_sha256"]:
            raise SystemExit(f"{where}: input_sha256 differs from the series its seed coordinates generate")


def compute(check, replicate, *, seed, streams, B):
    from uc_e4 import synthetic as Y
    cell = _cell_of(check)
    if cell is None:
        return Y.size_replicate(replicate, master_seed=seed, streams=streams, B=B)
    return Y.power_replicate(cell, replicate, master_seed=seed, streams=streams, B=B)


def build_manifest(*, check, a, b, seed, streams, B, n_series, root, argv):
    from dataclasses import asdict
    from uc_e4 import synthetic as Y
    identity = code_identity(root)
    packages, satisfied = installed_packages(root)
    cell = _cell_of(check)
    return dict(record_type="manifest", schema=SCHEMA, extension="e4", check=check, cell=cell,
                kappa=None if cell is None else Y.KAPPAS[cell], mode="development", master_seed=seed,
                streams=asdict(streams), B=B, n_series=n_series, slice=[a, b], identity_option=identity["option"],
                code_sha256=identity["code_sha256"], e1_code_sha256=identity["e1_code_sha256"],
                identity=dict(environment_sources=identity["environment_sources"], sources=identity["sources"]),
                python=platform.python_version(), platform=platform.platform(), machine=platform.machine(),
                packages=packages, lock_satisfied=satisfied, label="development run, cloud rehearsal",
                created_utc=_now(), started_utc=_now(), ended_utc=None, records=0, jsonl_sha256=None,
                sessions=[], argv=list(argv))


# ---------------------------------------------------------------------------------------- the run
def run_slice(out_dir, check, a, b, *, seed, n_series, B, root, argv=(), streams=None):
    """Run or resume one slice; returns the final manifest. Every guard fires before anything is written."""
    from uc_e4.streams import DEVELOPMENT_STREAMS, RegisteredRunRefused, check_run
    streams = streams or DEVELOPMENT_STREAMS
    try:
        check_run(seed, streams, allow_registered=False)
    except RegisteredRunRefused as error:
        raise SystemExit(f"Refused: {error}") from error
    if check not in CHECKS:
        raise SystemExit(f"Unknown check {check!r}; the checks are {', '.join(CHECKS)}")
    if not isinstance(n_series, int) or not 1 <= n_series <= REGISTERED_SERIES or not isinstance(B, int) or B < 1:
        raise SystemExit(f"n_series must lie in 1..{REGISTERED_SERIES} and B must be at least 1")
    if not 0 <= a < b <= n_series:
        raise SystemExit(f"slice {a}:{b} is outside 0 <= a < b <= {n_series}")
    out_dir = Path(out_dir)
    manifest = build_manifest(check=check, a=a, b=b, seed=seed, streams=streams, B=B, n_series=n_series,
                              root=root, argv=argv)
    jsonl, man_path = slice_paths(out_dir, check, a, b)
    resumed = None
    for a2, b2, other, path in recorded_slices(out_dir, check) if out_dir.is_dir() else []:
        if (a2, b2) != (a, b) and a < b2 and a2 < b:
            raise SystemExit(f"Slice {a}:{b} overlaps the recorded slice {a2}:{b2} ({path.name}): refused")
        differing = sorted(k for k, v in fingerprint(manifest).items() if fingerprint(other)[k] != v)
        if differing and (a2, b2) == (a, b):
            raise SystemExit(f"{path.name} belongs to another run ({', '.join(differing)} differ): resume refused")
        if differing:
            raise SystemExit(f"Slice {a}:{b} does not match the recorded slice {a2}:{b2} "
                             f"({', '.join(differing)} differ): gap-fill refused")
        if (a2, b2) == (a, b):
            resumed = other
    records, dropped = [], 0
    if resumed is None and jsonl.exists():
        raise SystemExit(f"{jsonl.name} exists without its manifest: refused")
    if resumed is not None:
        if resumed.get("ended_utc") is not None and jsonl.exists() and sha256_file(jsonl) != resumed.get("jsonl_sha256"):
            raise SystemExit(f"{jsonl.name} no longer matches the SHA-256 recorded when the slice ended")
        if jsonl.exists():
            records, dropped, cut = read_complete_lines(jsonl)
            verify_saved(records, resumed, streams=streams)
            if dropped:
                os.truncate(jsonl, cut)
        manifest = dict(resumed, ended_utc=None)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest["sessions"] = list(manifest.get("sessions", [])) + [dict(
        started_utc=_now(), pid=os.getpid(), argv=list(argv), resumed_records=len(records),
        dropped_partial_bytes=dropped)]
    write_manifest(man_path, manifest)
    with jsonl.open("ab") as handle:
        for replicate in range(a + len(records), b):
            record = compute(check, replicate, seed=seed, streams=streams, B=B)
            record.update(record_type="replicate", mode="development", master_seed=seed, B=B,
                          code_sha256=manifest["code_sha256"])
            handle.write((json.dumps(record, default=str) + "\n").encode())
            handle.flush()
            os.fsync(handle.fileno())
    final, _, _ = read_complete_lines(jsonl)
    manifest.update(ended_utc=_now(), records=len(final), jsonl_sha256=sha256_file(jsonl))
    write_manifest(man_path, manifest)
    return manifest


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("check", choices=CHECKS)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--replicates", help="a:b half-open, zero-based (default 0:n_series)")
    parser.add_argument("--n-series", type=int, default=2, help=f"development size, at most {REGISTERED_SERIES}")
    parser.add_argument("--B", type=int, default=9)
    parser.add_argument("--seed", type=int, default=None, help="development master seed (default 20260930)")
    parser.add_argument("--root", help="research checkout (default: the one uc_core was imported from)")
    parser.add_argument("--registered", action="store_true")
    args = parser.parse_args(argv)
    if args.registered:
        raise SystemExit("Registered mode is not available in this development copy: it needs the gate "
                         "(prereg-E4 tag, registration receipt), the lock under Python 3.12.14 and the integrated "
                         "code location (READINGS.md R-X3.1, R-X3.2)")
    import uc_core
    from uc_e4.streams import DEVELOPMENT_SEED
    root = Path(args.root).resolve() if args.root else Path(uc_core.__file__).resolve().parents[2]
    n_series = args.n_series
    if not 1 <= n_series <= REGISTERED_SERIES:
        raise SystemExit(f"--n-series must lie in 1..{REGISTERED_SERIES}")
    a, b = parse_slice(args.replicates, n_series) if args.replicates else (0, n_series)
    manifest = run_slice(args.out_dir, args.check, a, b, seed=DEVELOPMENT_SEED if args.seed is None else args.seed,
                         n_series=n_series, B=args.B, root=root, argv=argv)
    print(json.dumps({k: manifest[k] for k in ("check", "slice", "records", "started_utc", "ended_utc",
                                                "jsonl_sha256", "code_sha256", "e1_code_sha256")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
