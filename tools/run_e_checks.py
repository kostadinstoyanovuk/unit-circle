"""Run the E1 or E3 X.3 checks and append one JSON record per replicate (resumable, splittable).

Development:  python tools/run_e_checks.py e1 size --out e1_size_dev.jsonl --n-series 3 --B 9
Registered:   python tools/run_e_checks.py e1 size --registered --root . --out runs/extensions/E1/x3_size.jsonl
              run from the research root, with the root's own copy of this file.

A registered run fails closed unless every one of these holds (checked before any computation):
  - S3: this runner, uc_ext and uc_core are all the research root's (--root) own files;
  - S2: the gate (verify_extension_gate): a clean research tree; the annotated tag prereg-Ek present on
    origin with the same object; prereg/Ek.md equal to the tagged file; audit/Ek_REGISTRATION.json showing
    a public, approved registration (not pending, embargoed, withdrawn or archiving) whose OSF-archived
    Ek.md hash equals the tagged protocol, naming this tag and its commit, with time-zoned timestamps;
  - S3: --out lies outside the research tree or in a git-ignored path, so the tree stays clean;
  - S4: the research lock under Python 3.12.14 (uc_core.validation_runner.environment_identity).

E3 prerequisites:  python tools/run_e_checks.py e3 prerequisite [--registered --root .] --out prereq.jsonl
              runs the section 11 prerequisites (r = 0 and agreement on stream 5320/1/0; AT-11 and the
              agreement test on AT-11's fixture), writes the record and exits 0 only if every one passes.
              E3 size and power take --prerequisite <that file> (required when registered) and refuse to
              start unless it holds a passed record of the same mode and seed made by the same code.

S4/S5: every output file starts with a manifest line: extension, check, mode, master seed, sizes and
settings; environment_identity(root) (research commit, source hashes, package versions, interpreter); the
SHA-256 of every uc_ext and uc_core source and of this runner as imported, with their combined code hash;
the gate record. Each start appends a session line. Every replicate record repeats mode, master seed, B,
settings and the code hash. An interrupted run resumes only into a file whose manifest matches this run
(mode, seed, sizes, settings, code hash, commits, interpreter, packages, gate, prerequisite), and only after
every saved record is re-verified: its fields against the manifest, its stored input against input_sha256,
and that hash against the series regenerated from its seed coordinates. Saved coordinates are skipped;
--replicates a:b and --cells split the work across processes, each writing its own file; `summarize` takes
one or more --out files (C6), requires their manifests to match and their coordinates to be disjoint,
re-verifies every record and prints the cell summary, D80 and pass flags under a manifest of its own.
No data file is read.

S6/S7 settings (E3): the grid-point failure reading (e3.GRID_POINT_FAILURE) and the fit retention
(e3.X3_RETENTION: all_fits under the registered seed) are code settings, recorded in the manifest and in
every record; registered runs cannot override them. With all_fits, each replicate's surrogate fits go to
a gzip file <out>.fits/<cell>_<replicate>.json.gz that starts with the manifest; the record keeps its
path, SHA-256 and count, and resume and summarize re-verify it.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))

REGISTERED_SEED = 1927
REGISTERED_PYTHON = "3.12.14"
SCHEMA = 2
RECORD_FIELDS = ("mode", "master_seed", "B", "settings", "code_sha256")   # repeated in every replicate record


def _git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _git_or_none(root, *args):
    try:
        return _git(root, *args)
    except (OSError, subprocess.CalledProcessError):
        return None


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------------------------ S2: the gate

def check_registration_receipt(receipt, name, tag, protocol_sha256, tag_commit):
    """S2: the public-registration evidence in audit/Ek_REGISTRATION.json, fail closed."""
    where = f"audit/{name}_REGISTRATION.json"
    api = receipt.get("anonymous_api_check") or {}
    if not (api.get("public") is True and api.get("revision_state") == "approved"
            and api.get("pending_registration_approval") is False and api.get("embargoed") is False
            and api.get("withdrawn") is False and api.get("archiving") is False):
        raise SystemExit(f"{where} does not show a public, approved registration")
    if receipt.get("archived_attachment_bytes_verified") is not True:
        raise SystemExit(f"{where} does not record verified archived attachment bytes")
    archived = [a for a in receipt.get("archived_attachments") or [] if a.get("file_name") == f"{name}.md"]
    if (len(archived) != 1 or archived[0].get("osf_sha256") != protocol_sha256
            or archived[0].get("downloaded_sha256") != protocol_sha256):
        raise SystemExit(f"The OSF-archived {name}.md in {where} differs from the tagged protocol")
    if (receipt.get("expected_attachment_sha256") or {}).get(f"prereg/{name}.md") != protocol_sha256:
        raise SystemExit(f"The expected attachment hash in {where} differs from the tagged protocol")
    if receipt.get("prereg_tag") != tag or receipt.get("prereg_tag_commit") != tag_commit:
        raise SystemExit(f"{where} names another tag or tag commit than {tag} at {tag_commit}")
    if not receipt.get("registration_id"):
        raise SystemExit(f"{where} has no registration id")
    for key in ("api_date_registered_utc", "public_first_verified_at_utc"):
        try:
            stamp = datetime.fromisoformat(str(receipt[key]).replace("Z", "+00:00"))
        except (KeyError, ValueError) as error:
            raise SystemExit(f"{where} lacks a valid {key}") from error
        if stamp.utcoffset() is None:
            raise SystemExit(f"{where}: {key} has no time zone")


def verify_extension_gate(root, extension):
    """G4 for one extension, fail closed: the research repository and its public-registration record.

    Repository: clean tree; annotated tag prereg-Ek, published identically on origin; prereg/Ek.md equal to
    the tagged file. Registration: audit/Ek_REGISTRATION.json checked by check_registration_receipt against
    the SHA-256 of the tagged protocol and the tag's commit. Returns the tag name.
    """
    root = Path(root)
    name = extension.upper()
    tag, protocol = f"prereg-{name}", f"prereg/{name}.md"
    if _git(root, "status", "--porcelain"):
        raise SystemExit("Registered runs need a clean research checkout")
    try:
        kind = _git(root, "cat-file", "-t", f"refs/tags/{tag}")
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"Tag {tag} is absent: {name} is not registered here") from error
    if kind != "tag":
        raise SystemExit(f"{tag} must be an annotated tag")
    tagged = subprocess.check_output(["git", "show", f"{tag}:{protocol}"], cwd=root)
    if tagged != (root / protocol).read_bytes():
        raise SystemExit(f"{protocol} differs from the tagged protocol")
    remote = _git(root, "ls-remote", "origin", f"refs/tags/{tag}").split()
    if not remote or remote[0] != _git(root, "rev-parse", f"refs/tags/{tag}"):
        raise SystemExit(f"{tag} is not published identically on origin")
    try:
        receipt = json.loads((root / f"audit/{name}_REGISTRATION.json").read_text())
    except (OSError, ValueError) as error:
        raise SystemExit(f"audit/{name}_REGISTRATION.json is missing or unreadable") from error
    check_registration_receipt(receipt, name, tag, hashlib.sha256(tagged).hexdigest(),
                               _git(root, "rev-parse", f"refs/tags/{tag}^{{commit}}"))
    return tag


def gate_record(root, extension):
    """What the gate verified, for the manifest (called only after verify_extension_gate passed)."""
    root = Path(root)
    name = extension.upper()
    tag, receipt_path = f"prereg-{name}", root / f"audit/{name}_REGISTRATION.json"
    receipt = json.loads(receipt_path.read_text())
    return dict(tag=tag, tag_object=_git(root, "rev-parse", f"refs/tags/{tag}"),
                tag_commit=_git(root, "rev-parse", f"refs/tags/{tag}^{{commit}}"),
                protocol_sha256=_sha256_file(root / f"prereg/{name}.md"),
                registration_file_sha256=_sha256_file(receipt_path),
                registration_id=receipt.get("registration_id"), doi=receipt.get("doi"))


# ------------------------------------------------------------------------ S3: where the code runs

def verify_code_location(root):
    """S3: a registered run uses only the research root's runner, uc_ext and uc_core."""
    import uc_core
    import uc_ext
    root = Path(root).resolve()
    if HERE != root:
        raise SystemExit(f"Registered runs start only from the research root: run {root}/tools/run_e_checks.py, "
                         f"not {HERE}/tools/run_e_checks.py")
    for package in (uc_ext, uc_core):
        where = Path(package.__file__).resolve().parent
        if where != root / "src" / package.__name__:
            raise SystemExit(f"{package.__name__} was imported from {where}, not from {root}/src")


def verify_output_location(root, path):
    """S3: registered outputs must not dirty the research tree (outside it, or in a git-ignored path)."""
    root, path = Path(root).resolve(), Path(path).resolve()
    try:
        relative = path.relative_to(root)
    except ValueError:
        return
    if subprocess.run(["git", "check-ignore", "-q", str(relative)], cwd=root).returncode != 0:
        raise SystemExit(f"{path} is inside the research tree and not git-ignored (use runs/..., which is ignored)")


# ------------------------------------------------------------------ S4: identity and manifest

def code_identity():
    """SHA-256 of every uc_ext and uc_core source and of this runner as imported, and the uc_ext commit."""
    import uc_core
    import uc_ext
    sources = {}
    for package in (uc_ext, uc_core):
        directory = Path(package.__file__).resolve().parent
        for path in sorted(directory.glob("*.py")):
            sources[f"{directory.name}/{path.name}"] = _sha256_file(path)
    sources["tools/run_e_checks.py"] = _sha256_file(__file__)
    ext_directory = Path(uc_ext.__file__).resolve().parent
    status = _git_or_none(ext_directory, "status", "--porcelain", ".")
    return dict(ext_commit=_git_or_none(ext_directory, "rev-parse", "HEAD"),
                ext_dirty=None if status is None else bool(status), sources=sources)


def _fallback_identity(root):
    """Development only, outside the lock: environment_identity's fields, recomputed without its checks."""
    import numpy as np
    versions = {}
    lock = Path(root) / "requirements.lock"
    for line in lock.read_text().splitlines() if lock.is_file() else []:
        if "==" in line and not line.startswith("#"):
            package = line.strip().split("==")[0]
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = None
    status = _git_or_none(root, "status", "--porcelain")
    return dict(commit=_git_or_none(root, "rev-parse", "HEAD"), dirty=None if status is None else bool(status),
                python=platform.python_version(), platform=platform.platform(), machine=platform.machine(),
                numpy_runtime=str(np.__config__.CONFIG), packages=versions, source_sha256=None)


def run_identity(root, *, registered):
    """S4: environment_identity(root), the imported sources and their code hash; refuses a registered run
    outside the lock, on another interpreter than 3.12.14 or on a dirty tree."""
    from uc_core.validation_runner import environment_identity
    try:
        identity, lock = environment_identity(root), dict(satisfied=True, error=None)
    except (ValueError, OSError, subprocess.CalledProcessError, importlib.metadata.PackageNotFoundError) as error:
        if registered:
            raise SystemExit(f"Registered runs need the research lock and its files: {type(error).__name__}: "
                             f"{error}") from error
        identity, lock = _fallback_identity(root), dict(satisfied=False, error=f"{type(error).__name__}: {error}")
    if registered and (identity["dirty"] or identity["python"] != REGISTERED_PYTHON):
        raise SystemExit(f"Registered runs need a clean research tree and Python {REGISTERED_PYTHON}")
    imported = code_identity()
    code_sha256 = _canonical_sha256(dict(environment=identity.get("source_sha256"), imported=imported["sources"]))
    return dict(identity=identity, imported=imported, lock=lock, code_sha256=code_sha256)


def fingerprint(manifest):
    """The manifest fields a resumed run must reproduce exactly (S5)."""
    identity = manifest.get("identity") or {}
    return dict(schema=manifest.get("schema"), extension=manifest.get("extension"), check=manifest.get("check"),
                mode=manifest.get("mode"), master_seed=manifest.get("master_seed"),
                n_series=manifest.get("n_series"), B=manifest.get("B"), kappas=manifest.get("kappas"),
                settings=manifest.get("settings"), code_sha256=manifest.get("code_sha256"),
                commit=identity.get("commit"), ext_commit=(manifest.get("imported") or {}).get("ext_commit"),
                python=identity.get("python"), packages=identity.get("packages"), gate=manifest.get("gate"),
                prerequisite=(manifest.get("prerequisite") or {}).get("sha256"))


def read_output(path):
    """(manifest, replicate records, other records) of an output file that starts with a manifest line."""
    try:
        lines = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    except ValueError as error:
        raise SystemExit(f"{path} has an unreadable line (a truncated last line must be removed by hand): "
                         f"{error}") from error
    if not lines or lines[0].get("record_type") != "manifest":
        raise SystemExit(f"{path} does not start with a manifest line")
    kinds = [line.get("record_type") for line in lines[1:]]
    if "manifest" in kinds or None in kinds:
        raise SystemExit(f"{path} holds a second manifest or a line without a record type")
    return (lines[0], [line for line in lines[1:] if line["record_type"] == "replicate"],
            [line for line in lines[1:] if line["record_type"] not in ("replicate", "session")])


def write_fits(out, manifest, record):
    """S7: move a replicate's retained surrogate fits to a compressed file that starts with the manifest."""
    directory = Path(f"{out}.fits")
    directory.mkdir(exist_ok=True)
    name = f"{record['cell']}_{record['replicate']:03d}.json.gz"
    payload = dict(manifest=manifest, cell=record["cell"], cell_index=record["cell_index"],
                   replicate=record["replicate"], input_sha256=record.get("input_sha256"),
                   surrogate_fits=record["surrogate_fits"])
    data = gzip.compress(json.dumps(payload).encode(), compresslevel=9, mtime=0)
    temporary = directory / f"{name}.tmp"
    temporary.write_bytes(data)
    os.replace(temporary, directory / name)
    record.update(surrogate_fits=None, surrogate_fits_file=f"{directory.name}/{name}",
                  surrogate_fits_sha256=hashlib.sha256(data).hexdigest(),
                  surrogate_fits_count=len(payload["surrogate_fits"]))


def verify_saved(records, manifest, module, common, allow, out=None):
    """S5: every saved record belongs to this run and its input is the one its seed coordinates generate;
    a record's compressed surrogate-fit file (S7) must exist with the recorded SHA-256."""
    check = manifest["check"]
    kappas = tuple(manifest["kappas"]) if manifest.get("kappas") else module.KAPPAS
    cells = [0] if check == "size" else list(range(len(kappas)))
    seen = set()
    for record in records:
        key = (record.get("cell_index"), record.get("replicate"))
        where = f"Saved record (cell {key[0]}, replicate {key[1]})"
        if key in seen:
            raise SystemExit(f"{where} appears twice")
        seen.add(key)
        if key[0] not in cells or type(key[1]) is not int or not 0 <= key[1] < manifest["n_series"]:
            raise SystemExit(f"{where} lies outside this run's coordinates")
        if record.get("cell") != ("size" if check == "size" else f"power_{key[0]}"):
            raise SystemExit(f"{where} has the wrong cell name")
        for name in RECORD_FIELDS:
            if record.get(name) != manifest[name]:
                raise SystemExit(f"{where}: {name} differs from the file's manifest")
        if record.get("surrogate_fits_file") is not None:
            fits = Path(out).parent / record["surrogate_fits_file"] if out else None
            if fits is None or not fits.is_file() or _sha256_file(fits) != record.get("surrogate_fits_sha256"):
                raise SystemExit(f"{where}: its compressed surrogate-fit file is missing or altered")
        if record.get("input") is None:
            if record.get("status") != "generation_failed" or record.get("input_sha256") is not None:
                raise SystemExit(f"{where} has no input but is not a generation failure")
            continue
        if common.sha256_values(record["input"]) != record.get("input_sha256"):
            raise SystemExit(f"{where}: the stored input does not match input_sha256")
        regenerated = module.x3_input(check, key[0], key[1], master_seed=manifest["master_seed"], kappas=kappas,
                                      allow_registered=allow)
        if common.sha256_values(regenerated) != record["input_sha256"]:
            raise SystemExit(f"{where}: input_sha256 differs from the series its seed coordinates generate")


def _session(args, **extra):
    return dict(record_type="session", started_utc=_now(), pid=os.getpid(), python=platform.python_version(),
                platform=platform.platform(), argv=list(args), **extra)


# ------------------------------------------------------------------------- S1: E3 prerequisites

def prerequisite_passed(record):
    """Every section 11 prerequisite in an E3 prerequisite record passed (recomputed from its parts)."""
    parts = [record.get(name) or {} for name in ("r0", "agreement", "at11")]
    return record.get("passed") is True and all(part.get("passed") is True for part in parts)


def verify_prerequisite(path, *, mode, master_seed, commit, code_sha256):
    """S1: E3 size and power start only after a passed prerequisite record from the same code and mode."""
    if not path:
        raise SystemExit("Registered E3 size and power need --prerequisite <file written by 'e3 prerequisite'>")
    manifest, _, others = read_output(path)
    records = [line for line in others if line.get("record_type") == "prerequisite"]
    if manifest.get("extension") != "e3" or manifest.get("check") != "prerequisite" or len(records) != 1:
        raise SystemExit(f"{path} must hold exactly one E3 prerequisite record under its manifest")
    record = records[0]
    if not prerequisite_passed(record):
        raise SystemExit("The E3 prerequisite record did not pass: size and power may not start")
    if {manifest.get("mode"), record.get("mode")} != {mode} or {manifest.get("master_seed"),
                                                              record.get("master_seed")} != {master_seed}:
        raise SystemExit("The E3 prerequisite record was made in another mode or with another master seed")
    if ((manifest.get("identity") or {}).get("commit"), manifest.get("code_sha256"),
            record.get("code_sha256")) != (commit, code_sha256, code_sha256):
        raise SystemExit("The E3 prerequisite record was made by another code commit or other source files")
    return dict(path=str(path), sha256=_sha256_file(path), passed=True)


# ------------------------------------------------------------------------------------------ main

def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = argparse.ArgumentParser()
    parser.add_argument("extension", choices=["e1", "e3"])
    parser.add_argument("check", choices=["size", "power", "summarize", "prerequisite"])
    parser.add_argument("--out", required=True, action="append",
                        help="output file (summarize: give --out once per file to combine)")
    parser.add_argument("--registered", action="store_true")
    parser.add_argument("--root", help="research checkout (registered runs: the root this runner lives in)")
    parser.add_argument("--n-series", type=int)
    parser.add_argument("--B", type=int)
    parser.add_argument("--replicates", help="a:b half-open replicate range")
    parser.add_argument("--cells", help="comma-separated power cells")
    parser.add_argument("--prerequisite", help="passed E3 prerequisite record (required for registered E3 size/power)")
    parser.add_argument("--retention", choices=["all_fits", "base_fits"],
                        help="E3 development runs only: override the S7 retention setting")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else None
    if args.retention and (args.registered or args.extension != "e3"):
        raise SystemExit("--retention applies to E3 development runs only; registered runs use e3.X3_RETENTION")
    if args.registered:
        if not root or args.n_series or args.B:
            raise SystemExit("Registered runs take --root and use the registered sizes only")
        if HERE != root:
            raise SystemExit(f"Registered runs start only from the research root: run {root}/tools/run_e_checks.py")
    if root:
        sys.path.insert(0, str(root / "src"))
    from uc_ext import common as c, e1, e3
    import uc_core
    root = root or Path(uc_core.__file__).resolve().parents[2]
    module = e1 if args.extension == "e1" else e3
    if len(args.out) > 1 and args.check != "summarize":
        raise SystemExit("Only summarize combines several --out files; each run writes one file")
    out = Path(args.out[0])
    if args.registered:
        verify_code_location(root)
        verify_extension_gate(root, args.extension)
        gate = gate_record(root, args.extension)
        if args.check != "summarize":
            verify_output_location(root, out)
        master, n_series, B, allow = REGISTERED_SEED, module.SERIES_PER_CELL, module.SURROGATE_ATTEMPTS, True
    else:
        gate = None
        master, allow = c.DEVELOPMENT_MASTER_SEED, False
        n_series = args.n_series or 2
        B = args.B or 9
    mode = "registered" if args.registered else "development"
    run = run_identity(root, registered=args.registered)
    settings = module.x3_settings(master_seed=master, retain_fits=(None if not args.retention
                                                                  else args.retention == "all_fits"))
    manifest = dict(record_type="manifest", schema=SCHEMA, created_utc=_now(), extension=args.extension,
                    check=args.check, mode=mode, master_seed=master, n_series=n_series, B=B,
                    kappas=list(module.KAPPAS) if args.check == "power" else None, settings=settings,
                    code_sha256=run["code_sha256"], identity=run["identity"], imported=run["imported"],
                    lock=run["lock"], gate=gate, prerequisite=None, argv=argv)

    if args.check == "summarize":
        inputs, records, seen = [], [], set()
        for path in map(Path, args.out):
            saved, found, _ = read_output(path)
            if saved.get("extension") != args.extension or saved.get("mode") != mode:
                raise SystemExit(f"{path} was made by another extension or mode than this summary")
            if inputs and fingerprint(saved) != inputs[0]["manifest"]:
                raise SystemExit(f"{path} belongs to another run than {inputs[0]['path']}: summary refused")
            verify_saved(found, saved, module, c, allow, path)
            keys = {(r["cell_index"], r["replicate"]) for r in found}
            if keys & seen:
                raise SystemExit(f"{path} repeats coordinates already in another file: summary refused")
            seen |= keys
            records += found
            inputs.append(dict(path=str(path), sha256=_sha256_file(path), manifest=fingerprint(saved),
                               records=len(found)))
        requested = saved["n_series"]
        if args.n_series and args.n_series != requested:
            raise SystemExit(f"{out} was run with n_series = {requested}")
        design = (mode == "registered" and all(r.get("registered") is True for r in records)
                  and module._registered(saved["master_seed"], requested, saved["B"],
                                         saved.get("kappas") or module.KAPPAS))
        if saved["check"] == "size":
            summary = c.summarize_size(records, requested=requested, bounds=module.SIZE_BOUNDS, registered=design)
        else:
            cells = [c.summarize_cell([r for r in records if r["cell_index"] == i], requested)
                     for i in range(len(saved["kappas"]))]
            summary = c.summarize_power_cells(cells, tuple(saved["kappas"]), registered=design)
        print(json.dumps(dict(manifest=manifest, inputs=inputs, summary=summary), indent=1, default=str))
        return 0

    if args.check == "prerequisite":
        if args.extension != "e3":
            raise SystemExit("Only E3 has a separate synthetic prerequisite fixture here")
        if out.exists():
            raise SystemExit(f"{out} exists: a prerequisite record is never overwritten")
        with out.open("x") as handle:
            handle.write(json.dumps(manifest) + "\n")
            handle.flush()
            record = dict(record_type="prerequisite", mode=mode, master_seed=master, registered=bool(args.registered),
                          code_sha256=run["code_sha256"],
                          **e3.prerequisite_fixture(master_seed=master, allow_registered=allow))
            handle.write(json.dumps(record) + "\n")
        print(json.dumps(record, indent=1))
        return 0 if prerequisite_passed(record) else 1

    if args.extension == "e3" and (args.registered or args.prerequisite):
        manifest["prerequisite"] = verify_prerequisite(args.prerequisite, mode=mode, master_seed=master,
                                                       commit=run["identity"]["commit"],
                                                       code_sha256=run["code_sha256"])
    first, last = (map(int, args.replicates.split(":")) if args.replicates else (0, n_series))
    cells = [0] if args.check == "size" else ([int(v) for v in args.cells.split(",")] if args.cells
                                              else list(range(len(module.KAPPAS))))
    done, file_manifest = set(), manifest
    if out.exists():
        saved, records, others = read_output(out)
        file_manifest = saved
        differing = sorted(k for k, v in fingerprint(manifest).items() if fingerprint(saved)[k] != v)
        if differing:
            raise SystemExit(f"{out} belongs to another run ({', '.join(differing)} differ): resume refused")
        if others:
            raise SystemExit(f"{out} holds records that are not replicate records")
        verify_saved(records, saved, module, c, allow, out)
        done = {(r["cell_index"], r["replicate"]) for r in records}
    with out.open("a") as handle:
        if not done and out.stat().st_size == 0:
            handle.write(json.dumps(manifest) + "\n")
        handle.write(json.dumps(_session(argv, cells=cells, replicates=[first, last], resumed_records=len(done)))
                     + "\n")
        handle.flush()
        for cell in cells:
            for replicate in range(first, last):
                if (cell, replicate) in done:
                    continue
                if args.check == "size":
                    record = module.size_replicate(replicate, master_seed=master, B=B, allow_registered=allow,
                                                   **module.x3_arguments(settings))
                else:
                    record = module.power_replicate(cell, replicate, master_seed=master, B=B,
                                                    allow_registered=allow, **module.x3_arguments(settings))
                if record.get("settings", settings) != settings:
                    raise SystemExit("A replicate ran under other settings than the manifest records")
                record.update(record_type="replicate", registered=bool(args.registered), mode=mode,
                              master_seed=master, B=B, settings=settings, code_sha256=run["code_sha256"])
                if record.get("surrogate_fits") is not None:
                    write_fits(out, file_manifest, record)
                if manifest["prerequisite"]:
                    record["prerequisite_sha256"] = manifest["prerequisite"]["sha256"]
                handle.write(json.dumps(record) + "\n")
                handle.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
