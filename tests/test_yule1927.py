"""S1.1: the Yule (1927) transcription reproduces Yule's printed arithmetic."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from uc_core import yule
from uc_core.ar import root_summary

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIBED = ROOT / 'data/transcribed'
RECORD = json.loads((ROOT / 'audit/yule1927_verification.json').read_text(encoding='utf-8'))
TABLE = yule.read_table_a(TRANSCRIBED / 'yule1927_tableA.csv')
PRINTED = {row['item']: row for row in csv.DictReader((TRANSCRIBED / 'yule1927.csv').open(encoding='utf-8'))}


def value(key):
    return float(PRINTED[key]['value'])


def test_transcription_files_match_record():
    for name, digest in RECORD['transcription_sha256'].items():
        assert hashlib.sha256((TRANSCRIBED / name).read_bytes()).hexdigest() == digest


def test_table_a_covers_yules_sample():
    assert (TABLE.years[0], TABLE.last_year, len(TABLE.years)) == (1749, 1924, 176)
    assert all(row['page'] for row in PRINTED.values())
    deviations = np.asarray(TABLE.values) - np.mean(TABLE.values)
    assert not np.any(np.isclose(np.abs(deviations - np.floor(deviations)), 0.5))


def test_table_iv_and_equation_31_are_reproduced():
    result = yule.yule_serial_regression(TABLE.values)
    assert round(result['r1'], 6) == value('table4_r1')
    assert round(result['r2'], 6) == value('table4_r2')
    assert result['coefficient_lag1'] == pytest.approx(value('eq31_coefficient_lag1'), abs=1e-5)
    assert result['coefficient_lag2'] == pytest.approx(value('eq31_coefficient_lag2'), abs=1e-5)


def test_printed_period_and_disturbance_spread():
    period = root_summary([value('eq31_coefficient_lag1'), value('eq31_coefficient_lag2')]).period
    assert round(period, 3) == value('eq31_period_years')
    assert round(float(np.std(yule.yule_disturbances(TABLE.values))), 2) == value('eq31_sd_disturbances_points')
    assert float(np.std(TABLE.values)) == pytest.approx(value('sd_series_points'), abs=0.02)


def test_record_summary():
    assert RECORD['passed'] is True
    assert RECORD['table_a_vs_silso_v1']['years_differing'] == 49
    assert RECORD['table_a_vs_statsmodels']['years_differing'] == 22
