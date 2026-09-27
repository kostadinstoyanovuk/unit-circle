"""S1.1: check the Yule (1927) transcription against Yule's own printed arithmetic.

Reads data/transcribed/yule1927.csv and yule1927_tableA.csv and writes
audit/yule1927_verification.json. No network access and no UK observation.
"""
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uc_core import yule  # noqa: E402
from uc_core.ar import fit_ols, fit_yw, root_summary  # noqa: E402

TRANSCRIBED = ROOT / 'data/transcribed'
OUTPUT = ROOT / 'audit/yule1927_verification.json'
SOURCE_PDF_SHA256 = '766518d7d4eaa7ab450df444a1299d8c9a7e1a29861c6bf64d8352478cc2993c'


def printed():
    with (TRANSCRIBED / 'yule1927.csv').open(encoding='utf-8', newline='') as source:
        return {row['item']: row for row in csv.DictReader(source)}


def number(items, key):
    return float(items[key]['value'])


def differences(reference, other):
    pairs = [(year, a, b) for year, a, b in zip(reference.years, reference.values, other)]
    differing = [(year, a, b) for year, a, b in pairs if abs(a - b) > 1e-9]
    return dict(years_differing=len(differing),
                max_absolute_difference=round(max((abs(a - b) for _, a, b in differing), default=0.0), 6),
                differing_years=[year for year, _, _ in differing])


def main():
    items = printed()
    table = yule.read_table_a(TRANSCRIBED / 'yule1927_tableA.csv')
    x = np.asarray(table.values)
    reproduction = yule.yule_serial_regression(x)
    disturbances = yule.yule_disturbances(x)
    period_31 = root_summary([number(items, 'eq31_coefficient_lag1'), number(items, 'eq31_coefficient_lag2')]).period
    period_repro = root_summary([reproduction['coefficient_lag1'], reproduction['coefficient_lag2']]).period
    checks = {
        'table4_r1_reproduced_to_6dp': round(reproduction['r1'], 6) == number(items, 'table4_r1'),
        'table4_r2_reproduced_to_6dp': round(reproduction['r2'], 6) == number(items, 'table4_r2'),
        'eq31_coefficients_within_1e-5': (abs(reproduction['coefficient_lag1'] - number(items, 'eq31_coefficient_lag1')) <= 1e-5
                                          and abs(reproduction['coefficient_lag2'] - number(items, 'eq31_coefficient_lag2')) <= 1e-5),
        'eq31_period_from_printed_coefficients_to_3dp': round(period_31, 3) == number(items, 'eq31_period_years'),
        'sd_disturbances_to_2dp': round(float(np.std(disturbances)), 2) == number(items, 'eq31_sd_disturbances_points'),
        'sd_series_within_0.02': abs(float(np.std(x)) - number(items, 'sd_series_points')) <= 0.02,
    }
    v1 = yule.read_v1(ROOT / 'data/raw/yearssn.dat').sample(*yule.EARLY)
    import statsmodels.api as sm
    data = sm.datasets.sunspots.load_pandas().data
    statsmodels_early = data.SUNACTIVITY[(data.YEAR >= 1749) & (data.YEAR <= 1924)].to_numpy()
    fits = {}
    for name, fit in (('ols', fit_ols(x)), ('yw', fit_yw(x))):
        d = fit.diagnostics
        fits[name] = dict(phi1=fit.coefficients[0], phi2=fit.coefficients[1], intercept=fit.intercept,
                          modulus=d.modulus, period=d.period, half_life=d.half_life)
    record = dict(
        record_type='S1.1 transcription of Yule (1927) and reproduction of his arithmetic',
        source=dict(citation='Yule, G. U. (1927) Phil. Trans. R. Soc. A 226, 267-298, doi:10.1098/rsta.1927.0007',
                    pdf_sha256=SOURCE_PDF_SHA256, pages=32),
        transcription_sha256={name: hashlib.sha256((TRANSCRIBED / name).read_bytes()).hexdigest()
                              for name in ('yule1927.csv', 'yule1927_tableA.csv')},
        table_a=dict(first_year=table.years[0], last_year=table.last_year, values=len(x),
                     mean=float(np.mean(x)), sd_population=float(np.std(x))),
        reproduction=dict(method='deviations from the mean rounded to the nearest unit; Pearson serial correlations; '
                                 'phi1 = r1(1-r2)/(1-r1^2), phi2 = (r2-r1^2)/(1-r1^2)',
                          **reproduction, period=period_repro,
                          printed=dict(r1=number(items, 'table4_r1'), r2=number(items, 'table4_r2'),
                                       coefficient_lag1=number(items, 'eq31_coefficient_lag1'),
                                       coefficient_lag2=number(items, 'eq31_coefficient_lag2'),
                                       period=number(items, 'eq31_period_years'))),
        eq31_period_from_printed_coefficients=period_31,
        disturbances=dict(coefficients='1.343, -0.655, 13.854 (p. 282)', count=len(disturbances),
                          sd_population=float(np.std(disturbances)), mean=float(np.mean(disturbances)),
                          printed_sd=number(items, 'eq31_sd_disturbances_points')),
        checks=checks, passed=all(checks.values()),
        programme_fits_on_table_a=fits,
        table_a_vs_silso_v1=differences(table, v1),
        table_a_vs_statsmodels=differences(table, statsmodels_early),
        scope='Transcription check and descriptive comparison on sunspot data; no UK observation.',
    )
    OUTPUT.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(passed=record['passed'], checks=checks,
                          vs_v1=record['table_a_vs_silso_v1']['years_differing'],
                          vs_statsmodels=record['table_a_vs_statsmodels']['years_differing']), indent=2))


if __name__ == '__main__':
    main()
