"""Scientific contracts for the local production implementation."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st
from statsmodels.datasets import sunspots
from statsmodels.regression.linear_model import yule_walker
from statsmodels.tsa.ar_model import AutoReg

from uc_core import fit_ols, fit_yw, in_triangle, root_summary


@pytest.fixture(scope="module")
def data():
    return sunspots.load_pandas().data


@pytest.mark.parametrize("start,end", [(1749, 1924), (1925, 2008)])
def test_ols_matches_frozen_baseline_and_library(data, start, end):
    x = data.loc[data.YEAR.between(start, end), "SUNACTIVITY"]
    fit = fit_ols(x)
    reference = AutoReg(x.to_numpy(), lags=2, trend="c").fit()
    frozen = json.loads((Path(__file__).parents[1] / "audit/baseline_results.json").read_text())
    expected = frozen["intervals"][f"{start}-{end}"]["ols"]
    np.testing.assert_allclose([fit.intercept, *fit.coefficients], reference.params, rtol=0, atol=1e-11)
    np.testing.assert_allclose(fit.coefficients, expected["phi"], rtol=0, atol=1e-12)
    assert fit.n_regression_rows == end - start - 1
    assert abs(np.mean(fit.residuals)) < 1e-12
    assert fit.diagnostics.modulus == pytest.approx(np.max(np.abs(np.roots([1, *(-np.array(fit.coefficients))]))), abs=1e-14)


def test_yw_denominator_and_frozen_target(data):
    x = data.loc[data.YEAR.between(1749, 1924), "SUNACTIVITY"].to_numpy()
    fit = fit_yw(x)
    reference, _ = yule_walker(x, order=2, method="mle", demean=True, result_object=False)
    np.testing.assert_allclose(fit.coefficients, reference, rtol=0, atol=1e-12)
    assert fit.diagnostics.period == pytest.approx(10.545598579, abs=1e-9)
    assert fit.intercept == pytest.approx(x.mean() * (1 - sum(reference)), abs=1e-12)


@pytest.mark.parametrize("estimator", [fit_ols, fit_yw])
@pytest.mark.parametrize("scale,shift", [(1 / .6, 5), (-2, 1e4), (.01, 0)])
def test_affine_coefficients_and_intercept(data, estimator, scale, shift):
    x = data.loc[data.YEAR.between(1749, 1924), "SUNACTIVITY"].to_numpy()
    original = estimator(x)
    transformed = estimator(scale * x + shift)
    np.testing.assert_allclose(transformed.coefficients, original.coefficients, rtol=0, atol=1e-10)
    expected = scale * original.intercept + shift * (1 - sum(original.coefficients))
    assert transformed.intercept == pytest.approx(expected, rel=0, abs=1e-8)


@pytest.mark.parametrize("estimator", [fit_ols, fit_yw])
@pytest.mark.parametrize("bad", [[1, 2, 3, 4], [1, 2, 3, 4, np.nan], [1, 2, 3, 4, np.inf],
                                 np.ones(12), np.ones((8, 1)), [1j] * 8])
def test_invalid_data_not_silently_repaired(estimator, bad):
    with pytest.raises(ValueError):
        estimator(bad)


def test_ols_rejects_collinear_lags():
    with pytest.raises(ValueError, match="Rank-deficient"):
        fit_ols(np.arange(15.0))


def test_input_is_unchanged_and_pandas_is_accepted(data):
    x = data.loc[data.YEAR.between(1749, 1924), "SUNACTIVITY"].copy()
    original = x.copy()
    fit_ols(x)
    fit_yw(x)
    pd.testing.assert_series_equal(x, original)


@pytest.mark.parametrize("phi,roots", [((.3, .1), [.5, -.2]), ((1, -.25), [.5, .5]),
                                     ((0, 0), [0, 0]), ((0, -.25), [.5j, -.5j]),
                                     ((0, .25), [.5, -.5])])
def test_known_roots_and_degeneracies(phi, roots):
    calculated = root_summary(phi)
    np.testing.assert_allclose(np.sort_complex(calculated.roots), np.sort_complex(roots), rtol=0, atol=1e-14)
    assert calculated.stable


@pytest.mark.parametrize("phi", [(1, 0), (-1, 0), (0, -1), (2, -1), (-2, -1), (0, 1)])
def test_strict_boundary_is_excluded(phi):
    assert not in_triangle(*phi)
    summary = root_summary(phi)
    assert not summary.stable
    assert summary.half_life is None
    assert summary.spectral_peak is None


def test_explosive_fit_is_retained_instead_of_projected():
    x = [1., 2.]
    for _ in range(25):
        x.append(3 + 1.2 * x[-1] - .05 * x[-2])
    fit = fit_ols(x)
    np.testing.assert_allclose(fit.coefficients, [1.2, -.05], rtol=0, atol=1e-10)
    assert not fit.diagnostics.stable
    assert fit.diagnostics.half_life is None


def test_period_half_life_and_spectral_distinction():
    quadrature = root_summary([0, -.25])
    assert quadrature.period == pytest.approx(4)
    assert quadrature.half_life == pytest.approx(1)
    assert quadrature.peak_frequency == pytest.approx(np.pi / 2)
    assert root_summary([0, 0]).half_life == 0
    example = root_summary([1, -.3])
    assert example.complex_pair and example.stable and not example.spectral_peak
    assert example.peak_frequency is None
    assert root_summary([-.5, 0]).period is None


@settings(max_examples=250, derandomize=True, deadline=None)
@given(st.floats(-3, 3, allow_nan=False, allow_infinity=False),
       st.floats(-2, 2, allow_nan=False, allow_infinity=False))
def test_roots_agree_with_companion_eigenvalues(a, b):
    reference = np.linalg.eigvals([[a, b], [1., 0.]])
    summary = root_summary([a, b])
    np.testing.assert_allclose(np.sort_complex(summary.roots), np.sort_complex(reference), rtol=1e-9, atol=1e-12)
    margins = [1 - a - b, 1 + a - b, 1 + b]
    if min(abs(m) for m in margins) > 1e-9:
        assert summary.stable == bool(np.max(np.abs(reference)) < 1)
