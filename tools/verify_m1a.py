"""Verify the bounded local mathematical/estimator milestone; no UK data."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from pypdf import PdfReader
from statsmodels.datasets import sunspots

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uc_core import fit_ols, fit_yw, in_triangle, root_summary


def main() -> int:
    seed = 1927007
    rng = np.random.Generator(np.random.PCG64(seed))
    phi = rng.uniform([-3., -2.], [3., 2.], size=(100_000, 2))
    margins = np.column_stack((1-phi[:, 0]-phi[:, 1], 1+phi[:, 0]-phi[:, 1], 1+phi[:, 1]))
    keep = np.min(np.abs(margins), axis=1) > 1e-9
    companion = np.zeros((len(phi), 2, 2))
    companion[:, 0, :] = phi
    companion[:, 1, 0] = 1
    radii = np.max(np.abs(np.linalg.eigvals(companion)), axis=1)
    triangles = np.array([in_triangle(*p) for p in phi])
    mismatch = int(np.count_nonzero((triangles != (radii < 1)) & keep))
    source = sunspots.load_pandas().data
    x = source.loc[source.YEAR.between(1749, 1924), "SUNACTIVITY"].to_numpy()
    fits = {}
    for function in (fit_ols, fit_yw):
        fit = function(x)
        fits[fit.method] = {"coefficients": fit.coefficients, "intercept": fit.intercept,
                           "modulus": fit.diagnostics.modulus, "period": fit.diagnostics.period,
                           "half_life": fit.diagnostics.half_life}
    completed = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT,
                               capture_output=True, text=True, encoding="utf-8", check=False)
    pdf = ROOT / "proof/triangle.pdf"
    page_count = len(PdfReader(pdf).pages) if pdf.exists() else None
    files = ["src/uc_core/ar.py", "src/uc_core/__init__.py", "tests/test_ar_core.py",
             "proof/triangle.md", "proof/triangle.tex", "proof/triangle.pdf",
             "docs/CORE_CONVENTIONS.md", "requirements.lock", "tools/verify_m1a.py"]
    missing = [name for name in files if not (ROOT / name).is_file()]
    passed = mismatch == 0 and completed.returncode == 0 and not missing and page_count == 1
    report = {"milestone": "M1a", "verified_at_utc": datetime.now(timezone.utc).isoformat(),
              "passed": passed, "AT-7": {"seed": seed, "rng": "PCG64", "draws": len(phi),
              "kept": int(keep.sum()), "edge_exclusion": 1e-9, "mismatches": mismatch,
              "reference": "LAPACK companion eigenvalues; tested against open triangle",
              "coefficient_draws_sha256": hashlib.sha256(phi.astype('<f8').tobytes()).hexdigest()},
              "sunspot_fits_1749_1924": fits, "proof_pdf_pages": page_count,
              "pytest": {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr},
              "file_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files if name not in missing},
              "packages": {name: importlib.metadata.version(name) for name in ("numpy", "statsmodels", "pytest", "hypothesis", "pypdf")},
              "missing_files": missing,
              "limits": ["AT-7 is numerical agreement, not formal proof.",
                         "Visual and mathematical review of the PDF is recorded separately in the milestone report.",
                         "No G0-G7 gate, Lean certificate, preregistration, H1 analysis or C3 simulation is claimed."]}
    output = ROOT / "audit/m1a_verification.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print("M1a verification:", "PASS" if passed else "FAIL")
    print(f"AT-7: {int(keep.sum())} retained coefficient pairs; {mismatch} mismatches")
    print(completed.stdout.strip())
    print("Proof pages:", page_count)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
