"""Small regression tests for scientific conventions that can silently change results."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest
from statsmodels.datasets import sunspots
from statsmodels.regression.linear_model import yule_walker
from statsmodels.tsa.ar_model import AutoReg


spec = importlib.util.spec_from_file_location("audit_baseline", Path(__file__).resolve().parents[1] / "tools" / "audit_baseline.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.fixture(scope="module")
def early_series():
    data = sunspots.load_pandas().data
    return data.loc[data.YEAR.between(1749, 1924), "SUNACTIVITY"].to_numpy()


def test_root_sign_and_nonreciprocal_convention():
    # Known companion roots are 1/2 and 1/5; wrong signs/reciprocals cannot pass.
    metrics = audit.root_metrics([0.7, -0.1])
    assert sorted(z[0] for z in metrics["roots_real_imag"]) == pytest.approx([0.2, 0.5])
    assert metrics["spectral_radius"] == pytest.approx(0.5)
    assert metrics["stable"] and not metrics["complex_pair"]
    assert metrics["period_years"] is None


def test_quadrature_complex_roots():
    metrics = audit.root_metrics([0, -0.25])
    assert metrics["period_years"] == pytest.approx(4)
    assert metrics["half_life_years"] == pytest.approx(1)
    assert metrics["complex_modulus_formula"] == pytest.approx(0.5)


def test_ols_sample_and_library_crosscheck(early_series):
    fit = audit.ols_ar2(early_series)
    reference = AutoReg(early_series, lags=2, trend="c").fit()
    assert fit["input_count"] == 176 and fit["regression_count"] == 174
    assert [fit["intercept"], *fit["phi"]] == pytest.approx(reference.params, abs=1e-12, rel=0)
    # Common alternative (no intercept) is materially different on these data.
    no_intercept = np.linalg.lstsq(np.column_stack((early_series[1:-1], early_series[:-2])), early_series[2:], rcond=None)[0]
    assert np.max(np.abs(no_intercept - fit["phi"])) > 0.01


def test_yule_walker_common_denominator(early_series):
    result = audit.yule_walker_ar2(early_series)
    expected, _ = yule_walker(early_series, order=2, method="mle", demean=True, result_object=False)
    adjusted, _ = yule_walker(early_series, order=2, method="adjusted", demean=True, result_object=False)
    assert result["phi"] == pytest.approx(expected, abs=1e-12, rel=0)
    assert np.max(np.abs(adjusted - result["phi"])) > 0.001


@pytest.mark.parametrize("scale,offset", [(1 / 0.6, 5), (-3.5, 120), (0.01, -2)])
def test_affine_invariance_requires_correct_intercept(early_series, scale, offset):
    base = audit.ols_ar2(early_series)
    transformed = audit.ols_ar2(scale * early_series + offset)
    assert transformed["phi"] == pytest.approx(base["phi"], abs=1e-10, rel=0)
    expected_intercept = scale * base["intercept"] + offset * (1 - sum(base["phi"]))
    assert transformed["intercept"] == pytest.approx(expected_intercept, abs=1e-10, rel=0)


def test_reject_nonidentifiable_and_invalid_data():
    with pytest.raises(ValueError):
        audit.ols_ar2(np.ones(10))
    with pytest.raises(ValueError):
        audit.yule_walker_ar2(np.ones(10))
    with pytest.raises(ValueError):
        audit.ols_ar2(np.array([1, 2, np.nan, 3]))


def test_symbolic_checks_and_strict_inclusion():
    result = audit.symbolic_checks()
    assert all(result["identities"].values())
    assert [row["variance_computed"] for row in result["AT_17_boundary_display_values"]] == pytest.approx([16, 9.483264, 2.122416])
    example = result["strict_inclusion_example"]
    assert example["complex_roots"] and not example["interior_spectral_peak"]
    assert example["discriminant_exact"] == "-1/5"
    assert example["spectral_peak_margin_exact"] == "-1/10"


def test_evidence_preserves_partial_status_and_sample_boundaries():
    result = audit.build_audit()
    assert result["audit_success"]
    assert result["intervals"]["1925-2008"]["ols"]["regression_count"] == 82
    assert result["intervals"]["1925-2008"]["regression_year_start"] == 1927
    passed = {name for name, record in result["acceptance_tests"].items() if record["status"] == "passed"}
    assert passed == {"AT-1", "AT-2", "AT-3", "AT-4", "AT-6"}
    assert result["acceptance_tests"]["AT-17"]["status"] == "partial_algebra_only"
    assert result["acceptance_tests"]["AT-5"]["status"] == "not_run"


def test_clone_without_original_does_not_claim_source_verification(tmp_path):
    result = audit.build_audit(source_path=tmp_path / "absent.pdf")
    assert result["audit_success"]
    assert result["source_plan"]["status"] == "not_available_in_this_clone"
    assert result["source_plan"]["matches_preserved_original"] is None


def test_modified_original_fails_provenance_check(tmp_path):
    source = tmp_path / "modified.pdf"
    source.write_bytes(b"not the original plan")
    result = audit.build_audit(source_path=source)
    assert not result["audit_success"]
    assert result["source_plan"]["status"] == "mismatch"
