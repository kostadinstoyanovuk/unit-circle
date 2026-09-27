"""S1.3-S1.4 and AT-13: fits and bootstrap bands on both SILSO versions (D-018).

Writes data/derived/s1_fits.csv, data/derived/s1_bootstrap_draws.npz and the
committed evidence record audit/s1_verification.json. No network access and no
UK observation.
"""
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tools'))
from check_data import check  # noqa: E402
from uc_core import yule  # noqa: E402
from uc_core.ar import fit_ols  # noqa: E402

RAW = ROOT / 'data/raw'
DERIVED = ROOT / 'data/derived'
FITS_CSV = DERIVED / 's1_fits.csv'
DRAWS = DERIVED / 's1_bootstrap_draws.npz'
RECORD = ROOT / 'audit/s1_verification.json'
FIELDS = ['version', 'sample', 'start', 'end', 'n', 'method', 'phi1', 'phi2', 'intercept',
          'modulus', 'period', 'half_life', 'complex_pair', 'stable']


def statsmodels_series():
    import statsmodels.api as sm
    data = sm.datasets.sunspots.load_pandas().data
    return [int(year) for year in data.YEAR], [float(value) for value in data.SUNACTIVITY]


def compare_v1(v1, years, values):
    reference = dict(zip(v1.years, v1.values))
    differences = [(year, value, reference[year]) for year, value in zip(years, values)
                   if year in reference and value != reference[year]]
    early = [row for row in differences if yule.EARLY[0] <= row[0] <= yule.EARLY[1]]
    return dict(overlap_years=[years[0], years[-1]], years_compared=len(years),
                years_differing=len(differences),
                years_differing_1749_1924=len(early),
                max_absolute_difference=max((abs(a - b) for _, a, b in differences), default=0.0),
                differing_years=[row[0] for row in differences])


def main():
    checked, problems = check(ROOT)
    if problems:
        raise SystemExit('Raw data check failed: ' + '; '.join(problems))
    v1 = yule.read_v1(RAW / 'yearssn.dat')
    v2 = yule.read_v2(RAW / 'SN_y_tot_V2.0.csv')
    sm_years, sm_values = statsmodels_series()

    rows, summaries, arrays = [], [], {}
    for k, (series, label, start, end, method) in enumerate(yule.fit_plan(v1, v2)):
        row = yule.fit_row(series, label, start, end, method)
        result = yule.residual_bootstrap(series.sample(start, end), method, yule.stream(k))
        summary = yule.bootstrap_summary(result)
        rows.append(row)
        summaries.append(dict(k=k, stream=[yule.MASTER_SEED, yule.BOOTSTRAP_STREAM, k],
                              version=row['version'], sample=label, method=method, **summary))
        arrays[f'draws_{k}'] = result['draws']
        arrays[f'complex_{k}'] = result['complex_pair']

    def lookup(version, sample, method):
        return next(r for r in rows if r['version'] == version and r['sample'] == sample and r['method'] == method)

    differences = []
    for method in yule.METHODS:
        a, b = lookup('V1', '1749-1924', method), lookup('V2', '1749-1924', method)
        differences.append(dict(sample='1749-1924', method=method,
                                **{f'{key}_V2_minus_V1': (None if a[key] is None or b[key] is None else b[key] - a[key])
                                   for key in ('phi1', 'phi2', 'modulus', 'period', 'half_life')}))
    early_v1, early_v2 = v1.sample(*yule.EARLY), v2.sample(*yule.EARLY)
    ratio = early_v2 / np.where(early_v1 == 0, np.nan, early_v1)
    rescaled = fit_ols(early_v1 / 0.6)
    original = fit_ols(early_v1)
    rescale = dict(description='V1/0.6 refitted by least squares, 1749-1924',
                   max_coefficient_difference=float(max(abs(p - q) for p, q in zip(rescaled.coefficients, original.coefficients))),
                   identical_within_1e_10=bool(np.allclose(rescaled.coefficients, original.coefficients, atol=1e-10, rtol=0)),
                   median_ratio_V2_to_V1=float(np.nanmedian(ratio)))

    early_index = [i for i, year in enumerate(sm_years) if yule.EARLY[0] <= year <= yule.EARLY[1]]
    at13 = yule.at13([sm_values[i] for i in early_index])

    DERIVED.mkdir(parents=True, exist_ok=True)
    with FITS_CSV.open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    np.savez_compressed(DRAWS, **arrays)

    record = dict(
        record_type='S1 Yule centenary fits, bootstrap bands and AT-13',
        decision='D-018',
        inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                for p in ('data/raw/yearssn.dat', 'data/raw/SN_y_tot_V2.0.csv')},
        raw_files_checked=checked,
        versions={'V1': dict(first=v1.years[0], last=v1.last_year),
                  'V2': dict(first=v2.years[0], last=v2.last_year,
                             provisional_rows=sum(not flag for flag in v2.definitive))},
        statsmodels_vs_silso_v1=compare_v1(v1, sm_years, sm_values),
        fits=rows,
        bootstrap=dict(B=yule.BOOTSTRAP_B, master_seed=yule.MASTER_SEED, stream=yule.BOOTSTRAP_STREAM,
                       band='95% percentile, NumPy linear interpolation', summaries=summaries),
        version_differences=differences,
        rescaling_check=rescale,
        AT13=at13,
        environment=dict(python=platform.python_version(),
                         numpy=importlib.metadata.version('numpy'),
                         statsmodels=importlib.metadata.version('statsmodels')),
        scope='Descriptive replication on sunspot data. No difference test between versions; no UK observation.',
    )
    RECORD.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(fits=len(rows), AT13_passed=at13['passed'], AT13_checks=at13['checks'],
                          statsmodels_years_differing=record['statsmodels_vs_silso_v1']['years_differing']), indent=2))


if __name__ == '__main__':
    main()
