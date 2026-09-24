"""Reproduce the plan's small, unregistered M0 acceptance-target checks.

This is an independent audit script, not the production research package. It
uses only the sunspots dataset distributed with statsmodels and exact symbolic
algebra. No UK observations, random draws, or registered simulation cells are
loaded or generated. Run from the repository root:

    .venv/Scripts/python.exe tools/audit_baseline.py
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

import numpy as np
import sympy as sp
from statsmodels.datasets import sunspots


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_SHA256 = "85a594b0baf6d7b5a72d3ca1ec856f0df06b1106aaf3319e48f5b3967854dde7"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def array_digest(array: np.ndarray) -> str:
    """Digest explicitly specified little-endian float64, row-major bytes."""
    return hashlib.sha256(np.asarray(array, dtype="<f8").tobytes(order="C")).hexdigest()


def series_1d(values: np.ndarray) -> np.ndarray:
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or len(x) < 4 or not np.isfinite(x).all():
        raise ValueError("Expected a finite one-dimensional series of at least four values")
    return x


def ols_ar2(values: np.ndarray) -> dict:
    """OLS with intercept; lags are made AFTER restricting the input interval."""
    x = series_1d(values)
    design = np.column_stack((np.ones(len(x) - 2), x[1:-1], x[:-2]))
    beta, _, rank, _ = np.linalg.lstsq(design, x[2:], rcond=None)
    if rank != 3:
        raise ValueError("AR(2) design is not full rank")
    return {"intercept": float(beta[0]), "phi": beta[1:].tolist(),
            "input_count": len(x), "regression_count": len(x) - 2}


def yule_walker_ar2(values: np.ndarray) -> dict:
    """Plan's common-denominator autocorrelations; no lag-adjusted denominator."""
    x = series_1d(values)
    centered = x - x.mean()
    denominator = np.dot(centered, centered)
    if denominator <= 0:
        raise ValueError("Yule-Walker requires nonconstant observations")
    correlations = np.array([
        np.dot(centered[:-lag], centered[lag:]) / denominator
        for lag in (1, 2)
    ])
    matrix = np.array([[1, correlations[0]], [correlations[0], 1]])
    phi = np.linalg.solve(matrix, correlations)
    return {"phi": phi.tolist(), "r1_r2": correlations.tolist(),
            "input_count": len(x), "mean_removed": float(x.mean()),
            "common_sum_of_squares_denominator": float(denominator)}


def root_metrics(phi: list[float] | np.ndarray) -> dict:
    """Roots of lambda^2 - phi1*lambda - phi2, i.e. companion eigenvalues."""
    p1, p2 = map(float, phi)
    roots = np.roots([1.0, -p1, -p2])
    radius = float(np.max(np.abs(roots)))
    discriminant = p1 * p1 + 4 * p2
    result = {
        "discriminant": discriminant,
        "roots_real_imag": [[float(z.real), float(z.imag)] for z in roots],
        "spectral_radius": radius,
        "complex_pair": discriminant < 0,
        "stable": radius < 1,
        "period_years": None,
        "half_life_years": None,
        "complex_modulus_formula": None,
    }
    if discriminant < 0:
        theta = float(np.arccos(p1 / (2 * np.sqrt(-p2))))
        result["angle_radians"] = theta
        result["period_years"] = float(2 * np.pi / theta)
        result["complex_modulus_formula"] = float(np.sqrt(-p2))
    if 0 < radius < 1:
        result["half_life_years"] = float(np.log(2) / -np.log(radius))
    return result


def comparison(actual: float, stated: float, tolerance: float) -> dict:
    error = abs(float(actual) - stated)
    return {"computed": float(actual), "stated": stated,
            "absolute_error": error, "absolute_tolerance": tolerance,
            "passed": bool(error <= tolerance)}


def numerical_check(actual: dict, targets: dict) -> dict:
    checks = {key: comparison(actual[key], target, tolerance)
              for key, (target, tolerance) in targets.items()}
    return {"status": "passed" if all(c["passed"] for c in checks.values()) else "failed",
            "checks": checks}


def symbolic_checks() -> dict:
    p1, p2, innovation_variance = sp.symbols("phi1 phi2 innovation_variance", real=True)
    rho1 = p1 / (1 - p2)
    rho2 = p1 * rho1 + p2
    gamma0 = innovation_variance / (1 - p1 * rho1 - p2 * rho2)
    lag_covariance = gamma0 * sp.Matrix([[1, rho1], [rho1, 1]])
    sigma = sp.Matrix([[1 - p2**2, -p1 * (1 + p2)],
                       [-p1 * (1 + p2), 1 - p2**2]])
    covariance_residual = (innovation_variance * lag_covariance.inv() - sigma).applyfunc(sp.factor)
    gradient = sp.Matrix([2 * p1, 4])
    delta_direct = sp.expand((gradient.T * sigma * gradient)[0])
    delta_stated = 4 * (1 + p2) * (4 * (1 - p2) - p1**2 * (3 + p2))
    delta_residual = sp.factor(delta_direct - delta_stated)
    boundary = sp.factor(delta_direct.subs(p2, -p1**2 / 4))
    boundary_residual = sp.factor(boundary - (4 - p1**2)**3 / 4)
    boundary_targets = []
    for value, stated in [(sp.Rational(0), 16.0), (sp.Rational(4, 5), 9.48),
                          (sp.Rational(7, 5), 2.12)]:
        exact = sp.factor(boundary.subs(p1, value))
        boundary_targets.append({"phi1_exact": str(value), "variance_exact": str(exact),
                                 "variance_computed": float(exact), "plan_display": stated,
                                 "absolute_display_difference": abs(float(exact) - stated)})
    # If p2 < 0, the gap is nonnegative, establishing the bound used in the lemma.
    gap = sp.factor(-4 * p2 - (4 * p2 / (1 - p2))**2)
    gap_expected = -4 * p2 * (1 + p2)**2 / (1 - p2)**2
    example_p1, example_p2 = sp.Rational(1), -sp.Rational(3, 10)
    example = {
        "phi_exact": [str(example_p1), str(example_p2)],
        "discriminant_exact": str(example_p1**2 + 4 * example_p2),
        "spectral_peak_margin_exact": str(-4 * example_p2 - abs(example_p1) * (1 - example_p2)),
        "stability_triangle_positive_margins_exact": [
            str(1 - example_p1 - example_p2), str(1 - example_p2 + example_p1), str(1 + example_p2)],
        "complex_roots": bool(example_p1**2 + 4 * example_p2 < 0),
        "interior_spectral_peak": bool(example_p2 < 0 and abs(example_p1) * (1 - example_p2) < -4 * example_p2),
    }
    identities = {
        "innovation_variance_times_inverse_lag_covariance_equals_Sigma": covariance_residual == sp.zeros(2),
        "delta_method_gradient_identity": delta_residual == 0,
        "boundary_variance_identity": boundary_residual == 0,
        "spectral_inclusion_gap_identity": sp.factor(gap - gap_expected) == 0,
    }
    return {
        "status": "algebra_verified" if all(identities.values()) else "failed",
        "identities": identities,
        "covariance_residual": str(covariance_residual),
        "delta_method_residual": str(delta_residual),
        "boundary_residual": str(boundary_residual),
        "boundary_variance_formula": str(boundary),
        "AT_17_boundary_display_values": boundary_targets,
        "spectral_inclusion_nonnegative_gap_for_phi2_negative": str(gap),
        "strict_inclusion_example": example,
        "scope": "Exact computer algebra, not a Lean proof, asymptotic-normality proof, or Monte Carlo acceptance check.",
        "assumptions": [
            "Stationary AR(2) under the stochastic assumptions needed for OLS asymptotic covariance; positive innovation variance.",
            "The Yule-Walker covariance equations are assumed. Their rational matrix identity is checked exactly.",
            "The repeated-root boundary is stationary only for abs(phi1) < 2.",
            "The spectral-density interpretation is restricted to stationary AR(2); the inclusion gap is nonnegative for phi2 < 0.",
        ],
    }


def build_audit(source_path: Path | None = None) -> dict:
    data = sunspots.load_pandas().data
    rows = data[["YEAR", "SUNACTIVITY"]].to_numpy(dtype=float)
    expected_years = np.arange(1700, 2009, dtype=float)
    if not np.array_equal(rows[:, 0], expected_years):
        raise ValueError("Unexpected bundled sunspots coverage or year order")
    intervals = {}
    for label, start, end in [("1749-1924", 1749, 1924), ("1925-2008", 1925, 2008)]:
        selected = rows[(rows[:, 0] >= start) & (rows[:, 0] <= end)]
        if not np.array_equal(selected[:, 0], np.arange(start, end + 1)):
            raise ValueError("Missing or duplicate observations in required interval")
        fit = ols_ar2(selected[:, 1])
        intervals[label] = {
            "year_start": start, "year_end": end,
            "regression_year_start": start + 2, "regression_year_end": end,
            "year_value_array_sha256": array_digest(selected),
            "ols": fit, "root_metrics": root_metrics(fit["phi"]),
        }
    early = intervals["1749-1924"]
    late = intervals["1925-2008"]
    x = rows[(rows[:, 0] >= 1749) & (rows[:, 0] <= 1924), 1]
    yw = yule_walker_ar2(x)
    yw_metrics = root_metrics(yw["phi"])
    scaled = ols_ar2(x / 0.6 + 5)
    scale_error = np.abs(np.array(scaled["phi"]) - early["ols"]["phi"])
    checks = {
        "AT-1": numerical_check({"phi1": early["ols"]["phi"][0], "phi2": early["ols"]["phi"][1],
                                 "modulus": early["root_metrics"]["spectral_radius"],
                                 "period_years": early["root_metrics"]["period_years"],
                                 "half_life_years": early["root_metrics"]["half_life_years"]},
                                {"phi1": (1.336, 0.001), "phi2": (-0.650, 0.001),
                                 "modulus": (0.806, 0.001), "period_years": (10.57, 0.01),
                                 "half_life_years": (3.2, 0.1)}),
        "AT-2": numerical_check({"phi1": yw["phi"][0], "phi2": yw["phi"][1],
                                 "modulus": yw_metrics["spectral_radius"], "period_years": yw_metrics["period_years"]},
                                {"phi1": (1.326, 0.001), "phi2": (-0.642, 0.001),
                                 "modulus": (0.801, 0.001), "period_years": (10.55, 0.01)}),
        "AT-3": numerical_check({"phi1": late["ols"]["phi"][0], "phi2": late["ols"]["phi"][1],
                                 "modulus": late["root_metrics"]["spectral_radius"],
                                 "period_years": late["root_metrics"]["period_years"]},
                                {"phi1": (1.414, 0.001), "phi2": (-0.762, 0.001),
                                 "modulus": (0.873, 0.001), "period_years": (10.02, 0.01)}),
        "AT-4": numerical_check({"phi1_absolute_change": scale_error[0], "phi2_absolute_change": scale_error[1]},
                                {"phi1_absolute_change": (0.0, 1e-6), "phi2_absolute_change": (0.0, 1e-6)}),
        "AT-6": numerical_check({"modulus_formula": early["root_metrics"]["complex_modulus_formula"],
                                 "formula_minus_root_modulus": abs(early["root_metrics"]["complex_modulus_formula"]
                                                                     - early["root_metrics"]["spectral_radius"])},
                                {"modulus_formula": (0.806, 0.001), "formula_minus_root_modulus": (0.0, 1e-12)}),
    }
    checks["AT-6"]["extra_audit_tolerance"] = "1e-12 for formula/root agreement; the plan's target tolerance is 0.001."
    for number in range(1, 22):
        name = f"AT-{number}"
        if name not in checks:
            checks[name] = {"status": "not_run", "reason": "Outside this bounded M0 baseline audit."}
    for name, reason in {
        "AT-9": "Covariance algebra verified; required finite-sample Monte Carlo experiment not run.",
        "AT-10": "Strict-inclusion algebra/example verified; required numerical spectral grid not run.",
        "AT-17": "Boundary variance algebra and displayed values verified; required Monte Carlo experiment not run.",
    }.items():
        checks[name] = {"status": "partial_algebra_only", "reason": reason}
    symbolic = symbolic_checks()
    original = source_path if source_path is not None else ROOT.parent / "Unit_Circle_Programme_Plan.pdf"
    pdf_hash = sha256_file(original) if original.exists() else None
    dataset_file = Path(sunspots.__file__).resolve().parent / "sunspots.csv"
    return {
        "schema_version": 1,
        "purpose": "M0 independent acceptance-target audit; no registration or original programme gate is passed by this output.",
        "source_plan": {"relative_path": "../Unit_Circle_Programme_Plan.pdf", "pages": [13, 14, 21, 22],
                        "sha256": pdf_hash, "expected_sha256": ORIGINAL_SHA256,
                        "status": "not_available_in_this_clone" if pdf_hash is None else
                                  ("verified" if pdf_hash == ORIGINAL_SHA256 else "mismatch"),
                        "matches_preserved_original": None if pdf_hash is None else pdf_hash == ORIGINAL_SHA256},
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "packages": {name: importlib.metadata.version(name)
                                     for name in ["numpy", "scipy", "pandas", "statsmodels", "sympy", "pytest"]}},
        "audit_script_sha256": sha256_file(Path(__file__)),
        "data_provenance": {
            "source": "statsmodels.datasets.sunspots bundled data; no network request",
            "coverage": [1700, 2008], "observation_count": len(rows),
            "array_columns": ["YEAR", "SUNACTIVITY"],
            "array_digest_encoding": "C-order little-endian IEEE-754 float64 bytes; year then activity in each row",
            "full_year_value_array_sha256": array_digest(rows),
            "package_csv_sha256": sha256_file(dataset_file) if dataset_file.exists() else None,
        },
        "sample_conventions": {
            "ols": "Restrict to inclusive year interval first, then regress x[2:] on [1, x[1:-1], x[:-2]]. No preceding-period observations.",
            "yule_walker": "Subtract full interval mean; r_k=sum_{t=1}^{N-k}(x_t-mean)(x_{t+k}-mean)/sum_{t=1}^N(x_t-mean)^2.",
            "roots": "Companion roots of lambda^2-phi1*lambda-phi2; these are not reciprocal lag-polynomial roots.",
            "AT-4": "Transform each raw observation as x/0.6+5 and refit with an intercept; compare both AR coefficients.",
        },
        "intervals": intervals,
        "yule_walker_1749_1924": {"fit": yw, "root_metrics": yw_metrics},
        "affine_transform_1749_1924": {"fit": scaled, "phi_absolute_changes": scale_error.tolist()},
        "acceptance_tests": {f"AT-{n}": checks[f"AT-{n}"] for n in range(1, 22)},
        "symbolic_checks": symbolic,
        "audit_success": bool((pdf_hash is None or pdf_hash == ORIGINAL_SHA256) and symbolic["status"] == "algebra_verified"
                              and all(checks[name]["status"] == "passed" for name in ["AT-1", "AT-2", "AT-3", "AT-4", "AT-6"])),
        "limitations": [
            "Only AT-1, AT-2, AT-3, AT-4 and AT-6 are claimed passed; all other acceptance tests retain explicit partial/not-run states.",
            "The dataset is the specified statsmodels series, not an independently reconstructed historical Yule dataset.",
            "No synthetic Monte Carlo evidence, asymptotic theorem proof, formal Lean proof, or real UK analysis is produced.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "audit" / "baseline_results.json")
    args = parser.parse_args()
    result = build_audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    output_label = args.output.resolve().relative_to(ROOT) if args.output.resolve().is_relative_to(ROOT) else args.output.name
    print(f"Evidence written: {output_label}")
    print("Passed: " + ", ".join(name for name, record in result["acceptance_tests"].items() if record["status"] == "passed"))
    print(f"Symbolic checks: {result['symbolic_checks']['status']}; Monte Carlo checks not run.")
    return 0 if result["audit_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
