"""Registered H1 execution tooling on artificial ONS-format files only; never UK observations."""
import csv
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from uc_core import abmi, h1_official

ROOT = Path(__file__).resolve().parents[1]
RELEASE = dict(title='GDP quarterly national accounts, UK: artificial test release',
               release_datetime='2026-06-30T06:00:00+00:00',
               release_url='https://www.ons.gov.uk/releases/artificialtestrelease',
               file_url='https://example.invalid/artificial.csv')


def artificial_ons_csv(seed=7, *, drop=None, duplicate=None, cdid='ABMI', release_date='30-06-2026',
                       bad_value=None):
    """An artificial file in the ONS time-series layout; values come from a random AR(2)."""
    rng = np.random.default_rng(seed)
    quarters = [f'{year} Q{q}' for year in range(1948, 2022) for q in range(1, 5)]
    g = np.empty(len(quarters))
    g[:2] = 2.5
    for t in range(2, len(g)):
        g[t] = 1.5 + 0.3 * g[t - 1] + 0.1 * g[t - 2] + rng.normal(0, 3.5)
    levels = 100 * np.exp(np.cumsum(g / 400))
    rows = [['Title', 'Gross Domestic Product: chained volume measures: Seasonally adjusted £m'],
            ['CDID', cdid], ['Source dataset ID', 'QNA'], ['PreUnit', '£'], ['Unit', 'm'],
            ['Release date', release_date], ['Next release', '30 September 2026'], ['Important notes', '']]
    rows += [[str(year), f'{levels[i * 4]:.0f}'] for i, year in enumerate(range(1948, 2022))]
    for label, level in zip(quarters, levels):
        if label == drop:
            continue
        value = f'{level:.0f}' if label != bad_value else '-5'
        rows.append([label, value])
        if label == duplicate:
            rows.append([label, value])
    lines = [','.join(f'"{cell}"' for cell in row) for row in rows]
    return ('\n'.join(lines) + '\n').encode('utf-8')


def test_registered_sample_and_growth():
    parsed = abmi.parse_time_series_csv(artificial_ons_csv())
    identity = abmi.check_identity(parsed, release_date='30-06-2026')
    assert identity['cdid'] == 'ABMI' and identity['quarterly_rows'] == 296
    labels, levels = abmi.registered_sample(parsed)
    assert len(labels) == 260 and labels[0] == '1955 Q1' and labels[-1] == '2019 Q4'
    growth_labels, g = abmi.growth(labels, levels)
    assert len(g) == 259 and growth_labels[0] == '1955 Q2' and growth_labels[-1] == '2019 Q4'
    assert g[0] == pytest.approx(400 * np.log(levels[1] / levels[0]))


@pytest.mark.parametrize('kwargs, message', [
    (dict(drop='1970 Q3'), 'contiguous'),
    (dict(duplicate='1980 Q2'), 'Duplicate'),
    (dict(bad_value='1990 Q1'), 'positive'),
])
def test_sample_stop_rules(kwargs, message):
    parsed = abmi.parse_time_series_csv(artificial_ons_csv(**kwargs))
    with pytest.raises(abmi.AcquisitionStop, match=message):
        abmi.registered_sample(parsed)


def test_identity_stop_rules():
    with pytest.raises(abmi.AcquisitionStop, match='CDID'):
        abmi.check_identity(abmi.parse_time_series_csv(artificial_ons_csv(cdid='YBHA')), release_date='30-06-2026')
    with pytest.raises(abmi.AcquisitionStop, match='Release date'):
        abmi.check_identity(abmi.parse_time_series_csv(artificial_ons_csv(release_date='31-03-2026')),
                            release_date='30-06-2026')
    with pytest.raises(abmi.AcquisitionStop, match='after observation rows'):
        abmi.parse_time_series_csv(artificial_ons_csv() + b'"Title","late"\n')


def test_release_rule():
    assert h1_official.check_release(RELEASE, []).isoformat() == '2026-06-30T06:00:00+00:00'
    assert h1_official.uk_release_date(h1_official.check_release(RELEASE, [])) == '30-06-2026'
    with pytest.raises(abmi.AcquisitionStop, match='strictly before'):
        h1_official.check_release(dict(RELEASE, release_datetime='2026-09-30T06:00:00+00:00'), [])
    with pytest.raises(abmi.AcquisitionStop, match='later eligible'):
        h1_official.check_release(RELEASE, [dict(title='GDP quarterly national accounts, UK: later',
                                                 release_datetime='2026-08-01T06:00:00+00:00')])
    later_series = [dict(title='GDP quarterly national accounts, UK: later time series',
                         release_datetime='2026-10-01T06:00:00+00:00')]
    assert h1_official.check_release(RELEASE, later_series)
    with pytest.raises(abmi.AcquisitionStop, match='quarterly national accounts'):
        h1_official.check_release(dict(RELEASE, title='GDP first quarterly estimate'), [])


def test_g2_gate(tmp_path):
    with pytest.raises(h1_official.GateClosed):
        h1_official.check_g2(tmp_path)
    (tmp_path / 'audit').mkdir()
    record = dict(G2='passed', AT5_passed=True, AT15_passed=True, AT16_passed=False, D80=None)
    (tmp_path / h1_official.G2_RECORD).write_text(json.dumps(record))
    with pytest.raises(h1_official.GateClosed):
        h1_official.check_g2(tmp_path)
    (tmp_path / h1_official.G2_RECORD).write_text(json.dumps(dict(record, AT16_passed=True)))
    assert h1_official.check_g2(tmp_path)['D80'] is None


def test_acquisition_record_is_written_once_and_verified(tmp_path):
    (tmp_path / 'DATA_MANIFEST.csv').write_text('file,source_url,series_id,retrieved_utc,sha256,licence,notes\n')
    content = artificial_ons_csv()
    record = h1_official.record_acquisition(tmp_path, content, RELEASE, [], retrieved_utc='2026-09-28T07:00:00Z',
                                            raw_name='ABMI_QNA.csv', retrieval_method='test')
    assert record['bytes'] == len(content) and record['header_identity']['release_date_record'] == '30-06-2026'
    rows = list(csv.DictReader((tmp_path / 'DATA_MANIFEST.csv').open(encoding='utf-8')))
    assert rows[-1]['sha256'] == record['sha256']
    with pytest.raises(abmi.AcquisitionStop, match='once'):
        h1_official.record_acquisition(tmp_path, content, RELEASE, [], retrieved_utc='2026-09-28T07:00:00Z',
                                       raw_name='ABMI_QNA.csv', retrieval_method='test')
    _, labels, values = h1_official.load_registered_growth(tmp_path)
    assert len(values) == 259 and labels[-1] == '2019 Q4'
    stored = json.loads((tmp_path / h1_official.ACQUISITION_RECORD).read_text())
    stored['sha256'] = '0' * 64
    (tmp_path / h1_official.ACQUISITION_RECORD).write_text(json.dumps(stored))
    with pytest.raises(abmi.AcquisitionStop, match='differ'):
        h1_official.load_registered_growth(tmp_path)


def _tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'tools/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rehearsal_runs_the_whole_pipeline_on_artificial_data(tmp_path):
    source = tmp_path / 'artificial.csv'
    source.write_bytes(artificial_ons_csv(seed=11))
    manifest = _tool('run_h1').rehearse(source, '30-06-2026', tmp_path / 'rehearsal', surrogates=6, resamples=40)
    assert manifest['data_kind'] == 'artificial_pipeline_rehearsal'
    report = tmp_path / 'rehearsal/report'
    rolling = list(csv.DictReader((report / 'rolling.csv').open(encoding='utf-8')))
    assert len(rolling) == 259 and rolling[0]['quarter'] == '1955 Q2'
    assert all(row['data_kind'] == 'artificial_pipeline_rehearsal' for row in rolling)
    assert {'persistence.svg', 'persistence.pdf', 'surrogates.png', 'surrogates.pdf', 'comparisons.csv',
            'episodes.csv'} <= set(manifest['file_sha256'])
    again = _tool('run_h1').rehearse(source, '30-06-2026', tmp_path / 'again', surrogates=6, resamples=40)
    assert again['file_sha256'] == manifest['file_sha256'], 'the report, tables and figures must be byte-reproducible'
    assert manifest['interpretation']['D80'] is None
    freeze = _tool('freeze_h1')
    run = tmp_path / 'rehearsal'
    (run / 'run-log.json').write_text(json.dumps(dict(kind='registered primary run')))
    (run / 'analysis.json').write_text('{}')
    from uc_core.validation_store import digest
    (run / 'RUN_COMPLETE.json').write_text(json.dumps(dict(
        run_log_sha256=digest((run / 'run-log.json').read_bytes()),
        analysis_sha256=digest((run / 'analysis.json').read_bytes()),
        report_manifest_sha256=digest((report / 'manifest.json').read_bytes()))))
    with pytest.raises(SystemExit, match='Only the registered primary run'):
        freeze.verify(run)


def test_registered_run_is_closed_before_g2():
    if (ROOT / h1_official.G2_RECORD).exists():
        pytest.skip('G2 has been reviewed')
    with pytest.raises(h1_official.GateClosed):
        h1_official.check_g2(ROOT)
