"""Synthetic engineering evidence only; not a registered size/power study."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uc_core.rolling import max_modulus
from uc_core.recession import episodes, pre_onset_changes


def main():
    seed = 1927140
    generator = np.random.Generator(np.random.PCG64(seed))
    # Bounded positive noise with manually planted negative runs; no inferred model.
    values = generator.uniform(1, 3, size=140)
    for onset in [48, 60, 100]:
        values[onset:onset+2] = [-1, -.6]
    growth = pd.Series(values, index=pd.period_range("2000Q1", periods=140, freq="Q"))
    started = time.perf_counter()
    m = max_modulus(growth)
    elapsed = time.perf_counter() - started
    found = episodes(growth)
    onsets = [e.onset for e in found]
    statistic = pre_onset_changes(m, onsets)
    prefix = max_modulus(growth.iloc[:80])
    prefix_match = np.array_equal(m.iloc[:80].to_numpy(), prefix.to_numpy(), equal_nan=True)
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", check=False)
    files = ["src/uc_core/ar.py", "src/uc_core/rolling.py", "src/uc_core/recession.py",
             "tests/test_rolling_recession.py", "docs/M1B_CONVENTIONS.md", "tools/verify_m1b.py"]
    result = {"milestone": "M1b", "verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "passed": tests.returncode == 0 and onsets == [48, 60, 100] and prefix_match,
              "scope": "Synthetic software verification; these numbers have no empirical or power interpretation.",
              "fixture": {"seed": seed, "rng": "PCG64", "length": len(values),
                          "input_sha256": hashlib.sha256(values.astype('<f8').tobytes()).hexdigest(),
                          "negative_runs": [[48,49], [60,61], [100,101]]},
              "observed_episode_positions": [[e.onset, e.end] for e in found],
              "eligible_onsets": statistic.eligible_onsets, "synthetic_changes": statistic.changes,
              "synthetic_mean_change": statistic.mean_change, "prefix_invariance": prefix_match,
              "rolling_140_observation_runtime_seconds": elapsed,
              "pytest": {"returncode": tests.returncode, "stdout": tests.stdout, "stderr": tests.stderr},
              "file_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}}
    (ROOT/"audit/m1b_verification.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")
    print("M1b verification:", "PASS" if result["passed"] else "FAIL")
    print(tests.stdout.strip())
    print("Synthetic episode positions:", onsets, "; prefix invariant:", prefix_match)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
