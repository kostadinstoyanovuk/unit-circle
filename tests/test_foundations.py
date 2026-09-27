"""Foundations F2, F4, F5 (D-019): Schur-Cohn recursion, spectral radius, Kalman filter."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from uc_core import linalg, schur, statespace
from uc_core.ar import fit_ols, root_summary

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads((ROOT / 'audit/foundations_verification.json').read_text(encoding='utf-8'))


def sunspots_1749_1924():
    import statsmodels.api as sm
    data = sm.datasets.sunspots.load_pandas().data
    return data.SUNACTIVITY[(data.YEAR >= 1749) & (data.YEAR <= 1924)].to_numpy()


def test_schur_recursion_on_known_polynomials():
    assert schur.schur_cohn_stable([0.06, -0.5, 1])          # roots 0.2 and 0.3
    assert not schur.schur_cohn_stable([2, 1])              # root -2
    assert not schur.schur_cohn_stable([-1, 0, 1])          # roots on the circle
    assert schur.schur_cohn_stable([5])                     # non-zero constant
    assert schur.schur_cohn_stable(np.poly([0.5j, -0.9, 0.3 + 0.4j])[::-1])


def test_schur_transform_degree_and_leading_coefficient():
    p = np.array([0.3 + 0.1j, -0.2j, 0.5, 1 - 1j])
    q = schur.schur_transform(p)
    assert q.size == 3
    assert q[-1] == pytest.approx(abs(p[-1]) ** 2 - abs(p[0]) ** 2)
    np.testing.assert_allclose(schur.conjugate_reciprocal([1, 2j], degree=2), [0, -2j, 1])


def test_at8_reduced_sample_has_no_mismatch():
    result = schur.at8(count_per_degree=400, seed=(1927, 99))
    assert result['total']['mismatches'] == 0


def test_at8_record_passed():
    assert RECORD['AT8']['passed'] is True
    assert RECORD['AT8']['total']['mismatches'] == 0 and RECORD['AT8']['total']['compared'] >= 100_000


def test_spectral_radius_matches_roots_and_diagonals():
    assert linalg.spectral_radius(np.diag([0.3, -0.8])) == 0.8
    for phi in ([1.336, -0.65], [0.5, 0.2], [-1.2, -0.5]):
        assert linalg.spectral_radius(linalg.companion(phi)) == pytest.approx(root_summary(phi).modulus, abs=1e-12)
    block = linalg.var_companion([np.diag([0.5, 0.1]), np.diag([0.2, 0.0])])
    assert block.shape == (4, 4)
    assert linalg.spectral_radius(block) == pytest.approx(root_summary([0.5, 0.2]).modulus, abs=1e-12)


def test_at12_reduced_and_record():
    assert linalg.at12(draws=2_000, stream=99)['passed']
    assert RECORD['AT12']['passed'] is True


def test_at11_square_root_filter_reproduces_least_squares():
    result = statespace.regression_at11(sunspots_1749_1924())
    assert result['passed'] and result['max_abs_difference'] < 1e-8


def test_square_root_filter_matches_joseph_form_on_well_conditioned_models():
    rng = np.random.default_rng(20260927)
    for _ in range(20):
        m, n = int(rng.integers(1, 4)), 40
        Z, y = rng.standard_normal((n, m)), rng.standard_normal(n)
        T = np.diag(rng.uniform(-0.9, 0.9, m))
        B = rng.standard_normal((m, m))
        Q = 0.1 * B @ B.T
        result = statespace.kalman_filter(y, Z, T, Q, 0.7, np.zeros(m), np.eye(m))
        a, P, loglik, identity = np.zeros(m), np.eye(m), 0.0, np.eye(m)
        for t in range(n):
            z = Z[t]
            v = y[t] - z @ a
            F = z @ P @ z + 0.7
            K = P @ z / F
            a = a + K * v
            A = identity - np.outer(K, z)
            P = A @ P @ A.T + 0.7 * np.outer(K, K)
            assert result.filtered_states[t] == pytest.approx(a, abs=1e-10)
            loglik -= 0.5 * (math.log(2 * math.pi) + math.log(F) + v * v / F)
            a, P = T @ a, T @ P @ T.T + Q
        assert result.loglik == pytest.approx(loglik, abs=1e-9)


def test_local_level_matches_durbin_koopman():
    import statsmodels.api as sm
    nile = sm.datasets.nile.load_pandas().data.volume.to_numpy(dtype=float)
    estimate = statespace.local_level_mle(nile)
    assert estimate['converged']
    assert estimate['irregular'] == pytest.approx(15099.0, rel=0.005)
    assert estimate['level'] == pytest.approx(1469.1, rel=0.005)
    assert RECORD['passed'] == {'AT8': True, 'AT11': True, 'local_level': True, 'AT12': True}


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        schur.schur_cohn_stable([1, 0])
    with pytest.raises(ValueError):
        statespace.kalman_filter([1.0], [[1.0]], [[1.0]], [[0.0]], 0.0, [0.0], [[1.0]])
    assert fit_ols(sunspots_1749_1924()).diagnostics.complex_pair
