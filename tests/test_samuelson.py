"""S2 filters and the Samuelson mapping on artificial series only (D-021)."""
import numpy as np
import pytest

from uc_core import samuelson
from uc_core.ar import root_summary


def test_samuelson_mapping_round_trip_and_oscillation_condition():
    rng = np.random.default_rng(1)
    checked = 0
    for phi1, phi2 in rng.uniform([-2, -1], [2, 1], size=(20_000, 2)):
        reading = samuelson.samuelson(phi1, phi2)
        if reading['v'] is None:
            assert phi1 + phi2 <= 0
            continue
        c, v = reading['c'], reading['v']
        assert c * (1 + v) == pytest.approx(phi1, abs=1e-12)
        assert -c * v == pytest.approx(phi2, abs=1e-12)
        if abs(phi1 * phi1 + 4 * phi2) > 1e-9:
            assert reading['oscillates'] == root_summary([phi1, phi2]).complex_pair
            checked += 1
    assert checked > 5_000


def test_linear_cycle_removes_a_linear_trend():
    t = np.arange(80.0)
    assert np.max(np.abs(samuelson.linear_cycle(3 + 0.5 * t))) < 1e-10
    cycle = samuelson.linear_cycle(3 + 0.5 * t + np.sin(t / 3))
    assert abs(cycle.mean()) < 1e-10 and abs(cycle @ (t - t.mean())) < 1e-8


def test_hp_cycle_matches_the_penalised_least_squares_solution():
    rng = np.random.default_rng(2)
    y = np.cumsum(rng.normal(size=60))
    n = len(y)
    K = np.zeros((n - 2, n))
    for i in range(n - 2):
        K[i, i:i + 3] = (1, -2, 1)
    trend = np.linalg.solve(np.eye(n) + 1600 * K.T @ K, y)
    assert samuelson.hp_cycle(y) == pytest.approx(y - trend, abs=1e-8)


def test_hamilton_cycle_length_and_known_cases():
    t = np.arange(120.0)
    with pytest.raises(ValueError, match='rank deficient'):
        samuelson.hamilton_cycle(2 + 0.3 * t)  # lagged regressors of a pure line are collinear
    rng = np.random.default_rng(3)
    walk = np.cumsum(rng.normal(size=20_000))
    rows = range(3, len(walk) - 8)
    X = np.array([[1, *walk[r - np.arange(4)]] for r in rows])
    coefficients, *_ = np.linalg.lstsq(X, walk[[r + 8 for r in rows]], rcond=None)
    assert coefficients[1] == pytest.approx(1, abs=0.05) and abs(coefficients[2:]).max() < 0.05
    assert len(samuelson.hamilton_cycle(walk)) == len(walk) - 11


def test_three_rows_on_artificial_levels():
    rng = np.random.default_rng(4)
    g = np.empty(260)
    g[:2] = 2.5
    for i in range(2, 260):
        g[i] = 1.5 + 0.3 * g[i - 1] + 0.1 * g[i - 2] + rng.normal(0, 3.5)
    rows = samuelson.s2_rows(100 * np.exp(np.cumsum(g / 400)))
    assert [row['filter'] for row in rows] == list(samuelson.FILTERS)
    assert [row['cycle_observations'] for row in rows] == [260, 260, 249]
    for row in rows:
        if row['v'] is not None:
            assert row['oscillates'] == row['complex_roots']
    with pytest.raises(ValueError):
        samuelson.s2_rows(np.r_[np.ones(30), -1.0])
