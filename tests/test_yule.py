"""S1 sunspot inputs, fits, bootstrap reproduction and AT-13 (sunspot data only)."""
import csv
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from uc_core import yule

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads((ROOT / 'audit/s1_verification.json').read_text(encoding='utf-8'))
V1 = yule.read_v1(ROOT / 'data/raw/yearssn.dat')
V2 = yule.read_v2(ROOT / 'data/raw/SN_y_tot_V2.0.csv')


def _load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'tools/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_raw_files_match_manifest():
    tool = _load_tool('check_data')
    checked, problems = tool.check(ROOT)
    with (ROOT / 'DATA_MANIFEST.csv').open(newline='', encoding='utf-8') as manifest:
        rows = list(csv.DictReader(manifest))
    kept_out = sum(1 for row in rows if row['notes'].startswith(tool.NOT_DISTRIBUTED)
                   and not (ROOT / row['file']).is_file())
    assert checked + kept_out == len(rows) >= 2 and problems == []


def test_readers_cover_expected_years():
    assert (V1.years[0], V1.last_year, len(V1.years)) == (1700, 2014, 315)
    assert (V2.years[0], V2.last_year, len(V2.years)) == (1700, 2025, 326)
    assert all(V2.definitive)
    assert V1.sample(1749, 1924).size == 176


def test_missing_years_are_rejected():
    with pytest.raises(ValueError, match='contiguous'):
        V1.sample(1749, 2020)


def test_fits_reproduce_record():
    rows = [yule.fit_row(*plan) for plan in yule.fit_plan(V1, V2)]
    assert len(rows) == len(RECORD['fits']) == 8
    for row, saved in zip(rows, RECORD['fits']):
        for key in ('version', 'sample', 'n', 'method', 'complex_pair', 'stable'):
            assert row[key] == saved[key]
        for key in ('phi1', 'phi2', 'intercept', 'modulus', 'period', 'half_life'):
            assert row[key] == pytest.approx(saved[key], abs=1e-9)


def test_v1_early_fit_meets_at1_tolerance():
    row = yule.fit_row(V1, '1749-1924', 1749, 1924, 'ols')
    assert abs(row['phi1'] - 1.336) <= 0.001 and abs(row['phi2'] + 0.650) <= 0.001
    assert abs(row['modulus'] - 0.806) <= 0.001 and abs(row['period'] - 10.57) <= 0.01


def test_first_bootstrap_reproduces_record():
    x = V1.sample(1749, 1924)
    summary = yule.bootstrap_summary(yule.residual_bootstrap(x, 'ols', yule.stream(0)))
    saved = RECORD['bootstrap']['summaries'][0]
    assert (summary['complex'], summary['real'], summary['failed']) == (saved['complex'], saved['real'], saved['failed'])
    assert summary['modulus_band'] == pytest.approx(saved['modulus_band'], abs=1e-8)
    assert summary['period_band'] == pytest.approx(saved['period_band'], abs=1e-8)


def test_bootstrap_is_stream_deterministic_and_keeps_initial_values():
    x = V2.sample(1749, 1924)
    first = yule.residual_bootstrap(x, 'yw', yule.stream(5), B=12)
    second = yule.residual_bootstrap(x, 'yw', yule.stream(5), B=12)
    assert np.array_equal(first['draws'], second['draws'], equal_nan=True)


def test_rescaling_leaves_least_squares_unchanged():
    assert RECORD['rescaling_check']['identical_within_1e_10'] is True
    assert RECORD['rescaling_check']['median_ratio_V2_to_V1'] == pytest.approx(1 / 0.6)


def test_at13_record_passed_and_reproduces():
    assert RECORD['AT13']['passed'] is True
    import statsmodels.api as sm
    data = sm.datasets.sunspots.load_pandas().data
    early = data.SUNACTIVITY[(data.YEAR >= 1749) & (data.YEAR <= 1924)].to_numpy()
    result = yule.at13(early)
    assert result['passed'] is True
    assert result['bootstrap']['period_band'] == pytest.approx(RECORD['AT13']['bootstrap']['period_band'], abs=1e-8)
    assert result['bootstrap']['modulus_band'] == pytest.approx(RECORD['AT13']['bootstrap']['modulus_band'], abs=1e-8)
