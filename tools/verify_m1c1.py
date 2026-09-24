"""Small synthetic mechanics check; never a registered size or power experiment."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uc_core.surrogate import csd_test


def main():
    fixture_seed = 1927140
    values = np.random.Generator(np.random.PCG64(fixture_seed)).uniform(1, 3, size=140)
    for onset in [48, 60, 100]:
        values[onset:onset+2] = [-1, -.6]
    specifications = [("residual_endogenous", "residual", "endogenous", 1927411),
                      ("residual_fixed", "residual", "fixed", 1927412),
                      ("wild_endogenous", "wild", "endogenous", 1927413)]
    runs = {}
    for name, innovation, onset, seed in specifications:
        started = time.perf_counter()
        result = csd_test(values, B=24, rng=np.random.Generator(np.random.PCG64(seed)),
                          onset_mode=onset, innovation_mode=innovation)
        runs[name] = {"development_seed": seed, "seconds": time.perf_counter()-started,
                      "result": asdict(result)}
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", check=False)
    counts_ok = all(r["result"]["attempted"] == 24 ==
                    r["result"]["retained"] + r["result"]["no_episode"] + r["result"]["failed"]
                    for r in runs.values())
    successful = all(r["result"]["status"] == "ok" and r["result"]["failed"] == 0
                     for r in runs.values())
    files = ["src/uc_core/ar.py", "src/uc_core/rolling.py", "src/uc_core/recession.py",
             "src/uc_core/surrogate.py", "tests/test_surrogate.py",
             "docs/M1C1_SURROGATE_CONTRACT.md", "tools/verify_m1c1.py", "requirements.lock"]
    result = {"milestone": "M1c.1", "verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "passed": tests.returncode == 0 and counts_ok and successful,
              "scope": "Synthetic mechanics only. No size, power, empirical H1 or exact-calibration claim.",
              "fixture": {"seed": fixture_seed, "rng": "PCG64", "length": len(values),
                          "input_sha256": hashlib.sha256(values.astype('<f8').tobytes()).hexdigest(),
                          "negative_runs": [[48, 49], [60, 61], [100, 101]]},
              "environment": {"python": platform.python_version(),
                              **{name: version(name) for name in ["numpy", "pandas", "pytest"]}},
              "count_accounting_passed": counts_ok, "runs": runs,
              "pytest": {"returncode": tests.returncode, "stdout": tests.stdout, "stderr": tests.stderr},
              "file_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}}
    (ROOT/"audit/m1c1_verification.json").write_text(
        json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")
    print("M1c.1 verification:", "PASS" if result["passed"] else "FAIL")
    print(tests.stdout.strip())
    for name, run in runs.items():
        r = run["result"]
        print(name, {k: r[k] for k in ["status", "attempted", "retained", "no_episode", "failed"]})
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
