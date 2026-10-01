"""Gates for the registered E1, E3 and E4 execution steps, fail closed (prereg/E1.md, E3.md and E4.md, Annex B).

- Registration (G4): the X.3 runner's own check (`verify_extension_gate` of tools/run_e_checks.py for E1 and
  E3, of tools/run_e4_checks.py for E4), reused unchanged:
  a clean research tree, the annotated tag prereg-Ek published identically on origin, prereg/Ek.md equal
  to the tagged file, and audit/Ek_REGISTRATION.json showing an approved public registration whose
  archived protocol has the tagged bytes.
- Official synthetic checks (X.3): audit/Ek_X3.json, committed, recording that the registered size and
  power checks (and, for E3, the section 11 prerequisites) passed with the registered seed and sizes.
- Frozen code (Annex B, X.3 -> X.4): the code identity the extension's X.3 runner computes (every uc_ext and
  uc_core source, the runner, and the environment identity of the lock; for E4 also every uc_e4 source and its
  own runner) equals the one recorded in the X.3 record.
- Location: a registered run imports uc_core, uc_ext and this package from the research root it runs in.

Every refusal raises GateClosed with the reason; nothing is written by this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

REGISTERED_SEED = 1927
REGISTERED_SERIES = 200
REGISTERED_ATTEMPTS = 1000
REGISTERED_KAPPAS = (1.0, 1.2, 1.4, 1.6)
EXTENSIONS = ("e1", "e3", "e4")
RUNNER = "tools/run_e_checks.py"                 # E1 and E3
RUNNERS = dict(e1=RUNNER, e3=RUNNER, e4="tools/run_e4_checks.py")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class GateClosed(RuntimeError):
    """A required gate, record or identity is missing, not passed or inconsistent."""


def extension_name(extension: str) -> str:
    if extension not in EXTENSIONS:
        raise ValueError(f"Unknown extension {extension!r}; expected one of {EXTENSIONS}")
    return extension.upper()


def runner_path(extension: str) -> str:
    """The X.3 runner of an extension, relative to the research root."""
    extension_name(extension)
    return RUNNERS[extension]


def x3_record_path(extension: str) -> str:
    return f"audit/{extension_name(extension)}_X3.json"


def registration_record_path(extension: str) -> str:
    return f"audit/{extension_name(extension)}_REGISTRATION.json"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def utc(text: str) -> datetime:
    """An ISO 8601 time with an explicit offset, as UTC; a naive time is refused."""
    try:
        value = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Not an ISO 8601 time: {text!r}") from error
    if value.utcoffset() is None:
        raise ValueError(f"Time needs an explicit offset: {text!r}")
    return value.astimezone(timezone.utc)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def git(root, *args) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()


_RUNNERS = {}


def load_runner(root, extension: str = "e1"):
    """The research root's own X.3 runner for `extension` (tools/run_e_checks.py for E1 and E3,
    tools/run_e4_checks.py for E4), loaded once per path."""
    relative = runner_path(extension)
    path = (Path(root) / relative).resolve()
    if path not in _RUNNERS:
        if not path.is_file():
            raise GateClosed(f"{relative} is missing under {root}: the E pipelines are not integrated here")
        spec = importlib.util.spec_from_file_location(f"run_e_checks_{len(_RUNNERS)}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _RUNNERS[path] = module
    return _RUNNERS[path]


def _closed(call, *args, **kwargs):
    """Run a run_e_checks check, turning its SystemExit refusal into GateClosed."""
    try:
        return call(*args, **kwargs)
    except SystemExit as error:
        raise GateClosed(str(error)) from None


# ------------------------------------------------------------------------------- registration

def check_registration(root, extension: str) -> dict:
    """G4 for one extension (run_e_checks.verify_extension_gate), with the gate record and the
    registration's first verified public time, which starts the E1 release rule."""
    root = Path(root)
    runner = load_runner(root, extension)
    _closed(runner.verify_extension_gate, root, extension)
    gate = _closed(runner.gate_record, root, extension)
    receipt = json.loads((root / registration_record_path(extension)).read_text(encoding="utf-8"))
    gate.update(registration_url=receipt.get("registration_url"),
                public_first_verified_at_utc=utc(receipt["public_first_verified_at_utc"]).isoformat())
    return gate


def check_committed(root, relative: str) -> None:
    """The file is tracked and unchanged against HEAD."""
    root = Path(root)
    try:
        git(root, "ls-files", "--error-unmatch", relative)
    except subprocess.CalledProcessError:
        raise GateClosed(f"{relative} is not committed") from None
    if git(root, "status", "--porcelain", "--", relative):
        raise GateClosed(f"{relative} differs from the committed file")


def check_untracked(root, relative: str) -> None:
    """The file is not tracked by git (the E1 workbook is kept out of the repository, D-041)."""
    try:
        git(Path(root), "ls-files", "--error-unmatch", relative)
    except subprocess.CalledProcessError:
        return
    raise GateClosed(f"{relative} is tracked by git; the E1 workbook is kept out of the repository (D-041)")


# ------------------------------------------------------------------------------------ X.3

def validate_x3_record(record: dict, extension: str) -> dict:
    """The X.3 record says the registered official synthetic checks passed; else GateClosed."""
    name = extension_name(extension)
    problems = []
    if record.get("extension") != name or not str(record.get("record_type", "")).startswith(f"{name} X.3"):
        problems.append(f"it is not an {name} X.3 record")
    if record.get("X3") != "passed":
        problems.append(f"X3 is {record.get('X3')!r}, not 'passed'")
    for key in ("size_passed", "power_passed") + (("prerequisite_passed",) if extension == "e3" else ()):
        if record.get(key) is not True:
            problems.append(f"{key} is not true")
    if (record.get("mode"), record.get("master_seed"), record.get("n_series"), record.get("B")) != (
            "registered", REGISTERED_SEED, REGISTERED_SERIES, REGISTERED_ATTEMPTS):
        problems.append("it was not made with the registered mode, seed 1927, 200 series and B = 1000")
    if tuple(record.get("kappas") or ()) != REGISTERED_KAPPAS:
        problems.append("its power cells are not kappa 1.0, 1.2, 1.4, 1.6")
    if not HEX64.match(str(record.get("code_sha256", ""))):
        problems.append("it records no code identity")
    if "D80" not in record:
        problems.append("it must state D80, or null when it is undefined")
    if problems:
        raise GateClosed(f"The {name} official synthetic checks are not recorded as passed: " + "; ".join(problems))
    return record


def check_x3(root, extension: str) -> dict:
    """audit/Ek_X3.json exists, is committed, and records passed official synthetic checks."""
    root = Path(root)
    relative = x3_record_path(extension)
    path = root / relative
    if not path.is_file():
        raise GateClosed(f"{relative} does not exist: the {extension_name(extension)} official synthetic "
                         "checks (X.3) have not been recorded, so this step stays closed")
    record = validate_x3_record(json.loads(path.read_text(encoding="utf-8")), extension)
    check_committed(root, relative)
    return dict(record, record_sha256=sha256_file(path), record_path=relative)


# ------------------------------------------------------------------------------ frozen code

def code_identity(root, extension: str = "e1") -> dict:
    """The extension runner's run_identity in registered mode: lock, Python 3.12.14, clean tree, code hash."""
    return _closed(load_runner(root, extension).run_identity, Path(root), registered=True)


def check_code_frozen(root, x3: dict, extension: str | None = None) -> dict:
    """The code that runs X.4 is the code that ran X.3 (Annex B: not touched between them). The extension is
    the one given or, failing that, the one the X.3 record names. E4's identity includes E1's code (identity
    option e1-superset), and that part must be E1's frozen code as well."""
    extension = (extension or str(x3.get("extension") or "e1")).lower()
    identity = code_identity(root, extension)
    if identity["code_sha256"] != x3["code_sha256"]:
        raise GateClosed("The analysis code differs from the code that ran the official synthetic checks "
                         f"(X.3 code {x3['code_sha256'][:12]}..., now {identity['code_sha256'][:12]}...); "
                         "Annex B forbids touching it between X.3 and X.4")
    if extension == "e4":
        check_e1_code_unchanged(root, identity, x3)
    return identity


def check_e1_code_unchanged(root, identity: dict, x3: dict) -> None:
    """The E1 part of E4's code identity is the code frozen at E1's X.3 (audit/E1_X3.json), in the code now
    running and in the E4 X.3 record. A change to E1's frozen code would change both E4's hash and E1's."""
    frozen = check_x3(root, "e1")["code_sha256"]
    differing = [name for name, value in (("the code now running", identity.get("e1_code_sha256")),
                                          ("the E4 X.3 record", x3.get("e1_code_sha256"))) if value != frozen]
    if differing:
        raise GateClosed(f"The E1 part of the E4 code identity is not E1's frozen code identity ({frozen[:12]}...): "
                         f"it differs in {' and in '.join(differing)}; E1's frozen code is not touched")


def check_code_location(root, extension: str | None = None) -> dict:
    """uc_core, uc_ext and uc_ext_official (and, for E4, uc_e4) are imported from the research root's src/."""
    import uc_core
    import uc_ext
    import uc_ext_official
    packages = [uc_core, uc_ext, uc_ext_official]
    if extension == "e4":
        import uc_e4
        packages.append(uc_e4)
    root = Path(root).resolve()
    where = {}
    for package in packages:
        directory = Path(package.__file__).resolve().parent
        if directory != root / "src" / package.__name__:
            raise GateClosed(f"{package.__name__} was imported from {directory}, not from {root}/src; "
                             "registered runs use the research root's own code")
        where[package.__name__] = str(directory)
    return where


def package_sources(root) -> dict:
    """SHA-256 of every uc_ext_official source (recorded in run logs; not part of the X.3 identity)."""
    import uc_ext_official
    directory = Path(uc_ext_official.__file__).resolve().parent
    return {f"uc_ext_official/{path.name}": sha256_file(path) for path in sorted(directory.glob("*.py"))}


def ensure_src_on_path(root) -> None:
    source = str(Path(root).resolve() / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
