"""Re-run M0 evidence without any network or real UK data acquisition."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = "85a594b0baf6d7b5a72d3ca1ec856f0df06b1106aaf3319e48f5b3967854dde7"
REQUIRED_FILES = (
    "README.md", "STATUS.md", "MILESTONES.md", "DECISIONS.md",
    "DEVIATIONS.md", "requirements.lock",
    "audit/SPECIFICATION_AUDIT.md", "audit/STATISTICAL_DESIGN.md",
    "audit/STATISTICAL_SOURCES.json", "audit/FORMAL_FEASIBILITY.md",
    "audit/FORMAL_SOURCES.json", "audit/BASELINE_CHECKS.md",
    "audit/PREREGISTRATION_READINESS.md",
    "tools/audit_baseline.py", "tools/verify_m0.py", "tests/test_audit_baseline.py",
    "pyproject.toml",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    audit = ROOT / "audit"
    audit.mkdir(exist_ok=True)
    result = {
        "milestone": "M0",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scope": "Local specification-audit evidence and baseline only; no original research gate is certified.",
        "commands": [],
        "errors": [],
    }
    for filename in REQUIRED_FILES:
        if not (ROOT / filename).is_file():
            result["errors"].append(f"Missing required M0 evidence: {filename}")

    lock = ROOT / "requirements.lock"
    versions = {}
    if lock.is_file():
        for line in lock.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.count("==") != 1:
                result["errors"].append(f"Dependency is not exactly pinned: {line}")
                continue
            name, expected = line.split("==")
            try:
                actual = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                actual = None
            versions[name] = {"expected": expected, "actual": actual}
            if actual != expected:
                result["errors"].append(f"Environment mismatch: {name}: {actual} != {expected}")
        result["dependency_versions"] = versions

    source = ROOT.parent / "Unit_Circle_Programme_Plan.pdf"
    if source.is_file():
        actual_hash = digest(source)
        result["original_plan"] = {"sha256": actual_hash, "expected_sha256": SOURCE_SHA256,
                                   "status": "verified" if actual_hash == SOURCE_SHA256 else "mismatch"}
        if actual_hash != SOURCE_SHA256:
            result["errors"].append("Original plan differs from the audited source.")
    else:
        result["original_plan"] = {"expected_sha256": SOURCE_SHA256,
                                   "status": "not_available_in_this_clone"}

    for args in (["-m", "pip", "check"], ["tools/audit_baseline.py"], ["-m", "pytest", "tests/test_audit_baseline.py", "-q"]):
        completed = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", check=False)
        result["commands"].append({"command": "python " + " ".join(args),
                                   "returncode": completed.returncode,
                                   "stdout": completed.stdout, "stderr": completed.stderr})
        if completed.returncode:
            result["errors"].append("Failed: python " + " ".join(args))
    result["file_sha256"] = {name: digest(ROOT / name) for name in REQUIRED_FILES
                              if (ROOT / name).is_file()}
    baseline = ROOT / "audit/baseline_results.json"
    if baseline.is_file():
        result["file_sha256"]["audit/baseline_results.json"] = digest(baseline)
    else:
        result["errors"].append("Baseline run did not produce its evidence file.")
    result["passed"] = not result["errors"]
    (audit / "m0_verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("M0 verification:", "PASS" if result["passed"] else "FAIL")
    for check in result["commands"]:
        print(f"  {check['command']}: exit {check['returncode']}")
    for error in result["errors"]:
        print("  ERROR:", error)
    print("Evidence: audit/m0_verification.json")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
