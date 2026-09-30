"""Run the E4 X.3 checks (prereg/E4.md section 11, Annex B step 3) and append one JSON record per replicate
(resumable, splittable), under the conventions of tools/run_e_checks.py (E1 and E3).

Development:  python tools/run_e4_checks.py e4 size --out e4_size_dev.jsonl --n-series 2 --B 9
Registered:   python tools/run_e4_checks.py e4 size --registered --root . --replicates 0:25 \
                  --out runs/extensions/E4/x3_size_r000-025.jsonl
              run from the research root, with the root's own copy of this file; tools/plan_e4_x3.py prints
              the registered split of the checks into parts, one process each.

The size check is 200 series of the base process (stream 5420, cell 0) and the power check 200 series at each
of kappa = 1.0, 1.2, 1.4, 1.6 (stream 5430, cell = kappa index); every series is analysed at its five
truncation-only vintages with surrogates from stream 5421 (cell j) or 5431 (cell 10 * kappa index + j) and
B = 1000 attempts per vintage (uc_e4.synthetic).

A registered run fails closed unless every one of these holds (checked before any computation). The checks are
the functions of the same root's tools/run_e_checks.py, loaded by path and reused unchanged (that file is part
of this runner's identity):
  - S3: this runner, tools/run_e_checks.py, uc_e4, uc_ext and uc_core are all the research root's own files;
  - S2: the gate (verify_extension_gate, check_registration_receipt): a clean research tree; the annotated tag
    prereg-E4 present on origin with the same object; prereg/E4.md equal to the tagged file;
    audit/E4_REGISTRATION.json showing a public, approved registration of the tagged protocol;
  - S3: --out lies outside the research tree or in a git-ignored path (verify_output_location);
  - S4: the research lock under Python 3.12.14 and a clean tree (run_e_checks.run_identity).
Registered runs take only the registered design: master seed 1927, the stream plan of Annex A
(uc_e4.streams.REGISTERED_STREAMS), 200 series, B = 1000, kappa 1.0, 1.2, 1.4, 1.6; allow_registered=True is
passed to uc_e4 only after these checks. Development runs use the development seed 20260930, stream ids from
9000 (uc_e4.streams.DEVELOPMENT_STREAMS) and small sizes, and every record says mode "development".

Identity: the environment identity and the imported sources of tools/run_e_checks.py (every uc_core and uc_ext
source and that runner) plus every uc_e4 source and this runner, hashed in the canonical form of
run_e_checks (code_sha256). E1's own identity is recomputed by run_e_checks for the same root in the same
environment (e1_code_sha256): it does not change when uc_e4 or this runner change.

Files: JSON Lines; a manifest line first (extension, check, mode, master seed, sizes, kappas, settings, stream
plan, identity, gate), a session line at every start (with the thread settings OMP_NUM_THREADS,
OPENBLAS_NUM_THREADS and MKL_NUM_THREADS as found; this runner does not change them), then one replicate line
per series. A replicate line holds what uc_e4.synthetic.size_replicate or power_replicate returns, including
every attempt's statistic and per-vintage components, and repeats mode, master seed, B, settings, the code hash
and `registered`; it holds nothing time-dependent. A file is resumed only into a manifest whose fingerprint
matches this run, and only after every saved record is re-verified: its fields against the manifest, its
stored input against input_sha256, and that hash against the series regenerated from its seed coordinates. A
truncated last line is refused (the operator removes it by hand). --replicates a:b (half-open, zero-based)
and --cells split the work across processes, each writing its own file; saved coordinates are skipped.
`summarize` takes one or more --out files, requires their fingerprints to match and their coordinates to be
disjoint, re-verifies every record and prints {manifest, inputs, summary} as JSON; the summary comes from the
shared functions of uc_ext.common. No data file is read.
"""
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
if str(HERE / "src") not in sys.path:
    sys.path.insert(0, str(HERE / "src"))

E1_RUNNER = "tools/run_e_checks.py"
SCHEMA = 2
IDENTITY_OPTION = "e1-superset"      # E1's identity sources plus every uc_e4 source and this runner
SETTINGS = {}                        # E4 has no run-time settings; recorded as an empty mapping
RECORD_FIELDS = ("mode", "master_seed", "B", "settings", "code_sha256")   # repeated in every replicate record
THREAD_VARIABLES = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
MAX_SERIES = 200                     # the registered number of series per cell bounds every run

_E1 = {}


def e1_runner():
    """tools/run_e_checks.py of the research root that holds this runner, loaded by path once."""
    path = HERE / E1_RUNNER
    if path not in _E1:
        if not path.is_file():
            raise SystemExit(f"{E1_RUNNER} is missing next to this runner under {HERE}")
        spec = importlib.util.spec_from_file_location("uc_e4_x3_run_e_checks", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _E1[path] = module
    return _E1[path]


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ----------------------------------------------------- S2, S3: gate and file checks of run_e_checks, reused

def check_registration_receipt(receipt, name, tag, protocol_sha256, tag_commit):
    return e1_runner().check_registration_receipt(receipt, name, tag, protocol_sha256, tag_commit)


def verify_extension_gate(root, extension):
    return e1_runner().verify_extension_gate(root, extension)


def gate_record(root, extension):
    return e1_runner().gate_record(root, extension)


def verify_output_location(root, path):
    return e1_runner().verify_output_location(root, path)


def read_output(path):
    """(manifest, replicate records, other records), by run_e_checks.read_output; a file whose last line has
    no newline is refused as well, so that nothing is ever appended to a partial line."""
    data = Path(path).read_bytes()
    if data and not data.endswith(b"\n"):
        raise SystemExit(f"{path} ends in a truncated last line (no newline): remove that line by hand, "
                         "then run again")
    return e1_runner().read_output(path)


def verify_code_location(root):
    """S3: a registered run uses only the research root's own runners, uc_e4, uc_ext and uc_core."""
    import uc_e4
    root = Path(root).resolve()
    if HERE != root:
        raise SystemExit(f"Registered runs start only from the research root: run {root}/tools/run_e4_checks.py, "
                         f"not {HERE}/tools/run_e4_checks.py")
    e1 = e1_runner()
    if Path(e1.__file__).resolve() != root / E1_RUNNER:
        raise SystemExit(f"{E1_RUNNER} was loaded from {e1.__file__}, not from {root}")
    e1.verify_code_location(root)
    where = Path(uc_e4.__file__).resolve().parent
    if where != root / "src" / "uc_e4":
        raise SystemExit(f"uc_e4 was imported from {where}, not from {root}/src")


# ------------------------------------------------------------------------- S4: identity and manifest

def e4_sources():
    """SHA-256 of every uc_e4 source and of this runner, as imported."""
    import uc_e4
    directory = Path(uc_e4.__file__).resolve().parent
    sources = {f"uc_e4/{path.name}": _sha256_file(path) for path in sorted(directory.glob("*.py"))}
    sources["tools/run_e4_checks.py"] = _sha256_file(__file__)
    return sources


def run_identity(root, *, registered):
    """S4: run_e_checks.run_identity(root) (environment identity, lock, interpreter and clean-tree checks) with
    the uc_e4 sources and this runner added to its imported sources, and their combined code hash.

    Returns dict(identity, imported, lock, code_sha256, e1_code_sha256, identity_option): `identity` and `lock`
    are run_e_checks' own; `e1_code_sha256` is the code hash run_e_checks computes for the same root.
    """
    e1 = e1_runner()
    base = e1.run_identity(root, registered=registered)
    sources = {**base["imported"]["sources"], **e4_sources()}
    code_sha256 = e1._canonical_sha256(dict(environment=base["identity"].get("source_sha256"), imported=sources))
    return dict(identity=base["identity"], imported=dict(base["imported"], sources=sources), lock=base["lock"],
                code_sha256=code_sha256, e1_code_sha256=base["code_sha256"], identity_option=IDENTITY_OPTION)


def fingerprint(manifest):
    """The manifest fields a resumed run, and every file combined by summarize, must reproduce exactly (S5)."""
    identity = manifest.get("identity") or {}
    return dict(schema=manifest.get("schema"), extension=manifest.get("extension"), check=manifest.get("check"),
                mode=manifest.get("mode"), master_seed=manifest.get("master_seed"),
                n_series=manifest.get("n_series"), B=manifest.get("B"), kappas=manifest.get("kappas"),
                settings=manifest.get("settings"), streams=manifest.get("streams"),
                code_sha256=manifest.get("code_sha256"), e1_code_sha256=manifest.get("e1_code_sha256"),
                identity_option=manifest.get("identity_option"), commit=identity.get("commit"),
                ext_commit=(manifest.get("imported") or {}).get("ext_commit"), python=identity.get("python"),
                packages=identity.get("packages"), lock_satisfied=(manifest.get("lock") or {}).get("satisfied"),
                gate=manifest.get("gate"))


def thread_settings():
    """The thread-count variables of the numerical libraries, as found in the environment (None when unset)."""
    return {name: os.environ.get(name) for name in THREAD_VARIABLES}


# ------------------------------------------------------------------------------ coordinates

def work_coordinates(check, *, n_series, cells=None, replicates=None):
    """The (cell, replicate) pairs one process computes, in order: `replicates` is 'a:b' (half-open, zero-based,
    0 <= a < b <= n_series) and `cells` a comma-separated list of kappa indices (power only)."""
    from uc_e4 import synthetic as Y
    if replicates is None:
        first, last = 0, n_series
    else:
        match = re.fullmatch(r"(\d+):(\d+)", replicates)
        if not match:
            raise SystemExit(f"--replicates must read a:b (two non-negative integers), not {replicates!r}")
        first, last = int(match.group(1)), int(match.group(2))
        if not 0 <= first < last <= n_series:
            raise SystemExit(f"--replicates {first}:{last} lies outside 0 <= a < b <= {n_series}")
    if check == "size":
        if cells is not None:
            raise SystemExit("--cells applies to the power check only; the size check has one cell")
        chosen = [0]
    elif cells is None:
        chosen = list(range(len(Y.KAPPAS)))
    else:
        try:
            chosen = [int(value) for value in cells.split(",")]
        except ValueError as error:
            raise SystemExit(f"--cells must list kappa indices such as 0,1,2,3, not {cells!r}") from error
        if len(set(chosen)) != len(chosen) or any(not 0 <= cell < len(Y.KAPPAS) for cell in chosen):
            raise SystemExit(f"--cells must list distinct kappa indices from 0 to {len(Y.KAPPAS) - 1}")
        chosen = sorted(chosen)
    return [(cell, replicate) for cell in chosen for replicate in range(first, last)]


def _streams(manifest):
    from uc_e4.streams import Streams
    try:
        return Streams(**manifest["streams"])
    except (KeyError, TypeError) as error:
        raise SystemExit("The file's manifest does not hold a stream plan of Annex A's form") from error


def verify_saved(records, manifest, allow):
    """S5: every saved record belongs to this run and its input is the one its seed coordinates generate."""
    from uc_e4 import synthetic as Y
    from uc_ext import common as c
    check = manifest["check"]
    kappas = tuple(manifest["kappas"]) if check == "power" else None
    streams = _streams(manifest)
    cells = [0] if check == "size" else list(range(len(kappas)))
    registered = manifest["mode"] == "registered"
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
        if record.get("kappa") != (1.0 if check == "size" else kappas[key[0]]):
            raise SystemExit(f"{where} has the wrong kappa")
        for name in RECORD_FIELDS:
            if record.get(name) != manifest[name]:
                raise SystemExit(f"{where}: {name} differs from the file's manifest")
        if record.get("registered") is not registered:
            raise SystemExit(f"{where}: registered differs from the file's mode")
        if record.get("input") is None:
            if record.get("status") != "generation_failed" or record.get("input_sha256") is not None:
                raise SystemExit(f"{where} has no input but is not a generation failure")
            continue
        if c.sha256_values(record["input"]) != record.get("input_sha256"):
            raise SystemExit(f"{where}: the stored input does not match input_sha256")
        regenerated = Y.x3_input(check, key[0], key[1], master_seed=manifest["master_seed"], streams=streams,
                                 kappas=kappas or Y.KAPPAS, allow_registered=allow)
        if c.sha256_values(regenerated) != record["input_sha256"]:
            raise SystemExit(f"{where}: input_sha256 differs from the series its seed coordinates generate")


# ------------------------------------------------------------------------------------------ main

def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("extension", choices=["e4"])
    parser.add_argument("check", choices=["size", "power", "summarize"])
    parser.add_argument("--out", required=True, action="append",
                        help="output file (summarize: give --out once per file to combine)")
    parser.add_argument("--registered", action="store_true")
    parser.add_argument("--root", help="research checkout (registered runs: the root this runner lives in)")
    parser.add_argument("--n-series", type=int, help=f"development runs only: series per cell (1 to {MAX_SERIES})")
    parser.add_argument("--B", type=int, help="development runs only: surrogate attempts per vintage")
    parser.add_argument("--replicates", help="a:b half-open, zero-based replicate range")
    parser.add_argument("--cells", help="comma-separated power cells (kappa indices 0 to 3)")
    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve() if args.root else None
    if args.registered:
        if not root or args.n_series is not None or args.B is not None:
            raise SystemExit("Registered runs take --root and use the registered sizes only")
        if HERE != root:
            raise SystemExit(f"Registered runs start only from the research root: run {root}/tools/run_e4_checks.py")
    if root and str(root / "src") not in sys.path:
        sys.path.insert(0, str(root / "src"))
    import uc_core
    from uc_e4 import synthetic as Y
    from uc_e4.streams import DEVELOPMENT_SEED, DEVELOPMENT_STREAMS, REGISTERED_STREAMS
    from uc_ext import common as c
    root = root or Path(uc_core.__file__).resolve().parents[2]
    if len(args.out) > 1 and args.check != "summarize":
        raise SystemExit("Only summarize combines several --out files; each run writes one file")
    out = Path(args.out[0])
    if args.registered:
        verify_code_location(root)
        verify_extension_gate(root, args.extension)
        gate = gate_record(root, args.extension)
        if args.check != "summarize":
            verify_output_location(root, out)
        master, streams, n_series, B, allow = (e1_runner().REGISTERED_SEED, REGISTERED_STREAMS, Y.SERIES_PER_CELL,
                                               Y.SURROGATE_ATTEMPTS, True)
        if not Y._registered(master, streams, n_series, B, Y.KAPPAS):
            raise SystemExit("The registered design of uc_e4.synthetic is not seed 1927, Annex A, 200 and 1000")
    else:
        gate = None
        master, streams, allow = DEVELOPMENT_SEED, DEVELOPMENT_STREAMS, False
        n_series = 2 if args.n_series is None else args.n_series
        B = 9 if args.B is None else args.B
        if not 1 <= n_series <= MAX_SERIES or B < 1:
            raise SystemExit(f"Development runs take 1 to {MAX_SERIES} series per cell and B of at least 1")
    mode = "registered" if args.registered else "development"
    run = run_identity(root, registered=args.registered)
    manifest = dict(record_type="manifest", schema=SCHEMA, created_utc=e1_runner()._now(), extension=args.extension,
                    check=args.check, mode=mode, master_seed=master, n_series=n_series, B=B,
                    kappas=list(Y.KAPPAS) if args.check == "power" else None, settings=SETTINGS,
                    streams=asdict(streams), code_sha256=run["code_sha256"], e1_code_sha256=run["e1_code_sha256"],
                    identity_option=run["identity_option"], identity=run["identity"], imported=run["imported"],
                    lock=run["lock"], gate=gate, prerequisite=None, argv=argv)

    if args.check == "summarize":
        inputs, records, seen = [], [], set()
        for path in map(Path, args.out):
            saved, found, others = read_output(path)
            if saved.get("extension") != args.extension or saved.get("mode") != mode:
                raise SystemExit(f"{path} was made by another extension or mode than this summary")
            if saved.get("check") not in ("size", "power") or others:
                raise SystemExit(f"{path} is not a size or power output of replicate records only")
            if inputs and fingerprint(saved) != inputs[0]["manifest"]:
                raise SystemExit(f"{path} belongs to another run than {inputs[0]['path']}: summary refused")
            if args.registered and saved.get("code_sha256") != run["code_sha256"]:
                raise SystemExit(f"{path} was made by other code than this summary's: summary refused")
            verify_saved(found, saved, allow)
            keys = {(r["cell_index"], r["replicate"]) for r in found}
            if keys & seen:
                raise SystemExit(f"{path} repeats coordinates already in another file: summary refused")
            seen |= keys
            records += found
            inputs.append(dict(path=str(path), sha256=_sha256_file(path), manifest=fingerprint(saved),
                               records=len(found)))
        requested = saved["n_series"]
        if args.n_series is not None and args.n_series != requested:
            raise SystemExit(f"{path} was run with n_series = {requested}")
        kappas = tuple(saved["kappas"]) if saved["check"] == "power" else Y.KAPPAS
        design = (mode == "registered" and all(r.get("registered") is True for r in records)
                  and Y._registered(saved["master_seed"], _streams(saved), requested, saved["B"], kappas))
        if saved["check"] == "size":
            summary = c.summarize_size(records, requested=requested, bounds=Y.SIZE_BOUNDS, registered=design)
        else:
            cells = [c.summarize_cell([r for r in records if r["cell_index"] == i], requested)
                     for i in range(len(kappas))]
            summary = c.summarize_power_cells(cells, kappas, registered=design)
        print(json.dumps(dict(manifest=manifest, inputs=inputs, summary=summary), indent=1, default=str))
        return 0

    coordinates = work_coordinates(args.check, n_series=n_series, cells=args.cells, replicates=args.replicates)
    done, existed = set(), out.exists()
    if existed:
        saved, records, others = read_output(out)
        differing = sorted(k for k, v in fingerprint(manifest).items() if fingerprint(saved)[k] != v)
        if differing:
            raise SystemExit(f"{out} belongs to another run ({', '.join(differing)} differ): resume refused")
        if others:
            raise SystemExit(f"{out} holds records that are not replicate records")
        verify_saved(records, saved, allow)
        done = {(r["cell_index"], r["replicate"]) for r in records}
    cells = sorted({cell for cell, _ in coordinates})
    span = [coordinates[0][1], coordinates[-1][1] + 1]
    session = e1_runner()._session(argv, cells=cells, replicates=span, resumed_records=len(done),
                                   threads=thread_settings())
    with out.open("a") as handle:
        if not existed:
            handle.write(json.dumps(manifest) + "\n")
        handle.write(json.dumps(session) + "\n")
        handle.flush()
        for cell, replicate in coordinates:
            if (cell, replicate) in done:
                continue
            if args.check == "size":
                record = Y.size_replicate(replicate, master_seed=master, streams=streams, B=B, allow_registered=allow)
            else:
                record = Y.power_replicate(cell, replicate, master_seed=master, streams=streams, B=B,
                                           kappas=Y.KAPPAS, allow_registered=allow)
            record.update(record_type="replicate", registered=bool(args.registered), mode=mode, master_seed=master,
                          B=B, settings=SETTINGS, code_sha256=run["code_sha256"])
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return 0


if __name__ == "__main__":
    sys.exit(main())
