from copy import deepcopy
import csv
import json

import numpy as np
import pytest

from uc_core.h1 import analyze_h1
from uc_core.h1_reporting import assemble_report, comparison_rows, primary_interpretation, write_development_report
from uc_core.validation_store import digest
from uc_core.validation_runner import serial


@pytest.fixture(scope='module')
def fixture():
    values = np.random.default_rng(440031).uniform(1, 3, 100)
    values[20:22] = [-1, -.6]
    values[48:50] = [-1, -.6]
    values[55:57] = [-1, -.6]
    values[80:82] = [-1, -.6]
    return values, analyze_h1(values, B=4, interval_B=20)


def test_report_preserves_all_rows_attempts_and_merging(fixture):
    values, results = fixture
    report = assemble_report(values, results)
    rows = report['comparisons']
    assert [r['analysis'] for r in rows] == ['primary','window32','window48','fixed','wild','trend','lag1']
    assert rows[0]['value'] == results['joint'].primary.observed.value
    assert rows[0]['p_value'] == results['joint'].primary.p_value
    assert rows[0]['retained'] == results['joint'].primary.retained
    assert len(report['primary_surrogates']) == results['joint'].primary.attempted
    assert [r['onset'] for r in report['qualifying_runs']] == [20,48,55,80]
    assert [r['onset'] for r in report['episodes']] == [20,48,80]
    assert report['episodes'][0]['structurally_eligible'] is False
    assert report['episodes'][1]['qualifying_runs'] == 2
    assert report['episodes'][1]['end'] == 56
    assert all(r['modulus'] is None for r in report['rolling'][:39])
    assert all(r['modulus'] is not None for r in report['rolling'][39:])
    assert report['interpretation']['D80'] is None
    assert report['input_sha256'] == results['input_sha256'] == digest(values.astype('<f8').tobytes())


@pytest.mark.parametrize('value,sign', [(-.2,'negative'), (0.,'zero'), (.2,'positive')])
def test_upper_tail_rejection_does_not_relabel_signed_change(value, sign):
    result = primary_interpretation(dict(status='ok', value=value, p_value=.05), {'interval':[-.3,.4]})
    assert result['conclusion'] == 'upper_tail_rejection'
    assert result['statistic_sign'] == sign
    assert ('nonpositive' in result['text']) == (value <= 0)
    assert result['branch_B_condition'] is None


@pytest.mark.parametrize('upper,d80,expected', [(.1,.2,True), (.2,.2,False), (.3,.2,False)])
def test_branch_B_is_strict_and_never_equivalence(upper, d80, expected):
    result = primary_interpretation(dict(status='ok', value=.03, p_value=.05001),
                                    {'interval':[-.1,upper]}, D80=d80)
    assert result['conclusion'] == 'inconclusive'
    assert result['branch_B_condition'] is expected
    assert 'does not establish absence or equivalence' in result['branch_B_scope']


@pytest.mark.parametrize('status', ['observed_not_estimable','null_model_failed','invalid_surrogate_failure'])
def test_missing_p_is_never_reported_as_nonrejection(status):
    result = primary_interpretation(dict(status=status, value=None, p_value=None), {'interval':None})
    assert result['conclusion'] in ('not_estimable','failed')
    assert result['branch_B_condition'] is None


@pytest.mark.parametrize('position', [47, -1])
def test_input_result_mismatch_is_rejected(fixture, position):
    values, results = fixture
    altered = values.copy()
    # The final observation leaves every pre-onset statistic unchanged, but
    # changes the full-sample null; it must not acquire the earlier results.
    altered[position] += 1
    with pytest.raises(ValueError, match='does not match'):
        assemble_report(altered, results)


def test_results_without_original_input_identity_cannot_be_exported(tmp_path, fixture):
    values, results = fixture
    changed = serial(results)
    del changed['input_sha256']
    folder = tmp_path/'unbound'
    with pytest.raises(ValueError, match='input hash is missing'):
        write_development_report(folder, values, changed,
            fixture_metadata={'data_kind':'artificial_development_fixture'})
    assert not folder.exists()


def test_failed_row_retains_cause_and_does_not_erase_other_rows(fixture):
    _, results = fixture
    changed = serial(results)
    changed['window32'] = dict(status='null_model_failed', observed={'mean_change':-.2},
                               p_value=None, requested=4, attempted=0, error='constructed unstable null')
    rows = comparison_rows(changed)
    assert len(rows) == 7 and rows[0]['value'] is not None
    assert rows[1]['value'] == -.2 and rows[1]['retained'] == 0
    assert rows[1]['error'] == 'constructed unstable null' and rows[1]['p_value'] is None


@pytest.mark.parametrize('mutation', ['attempted', 'p', 'failed_p', 'ledger'])
def test_inconsistent_accounting_or_p_cannot_be_presented_as_valid(fixture, mutation):
    _, results = fixture
    changed = serial(results)
    row = changed['fixed']
    if mutation == 'attempted':
        row['attempted'] += 1
    elif mutation == 'p':
        row['p_value'] = -.1
    elif mutation == 'failed_p':
        row['status'] = 'invalid_surrogate_failure'
    else:
        row['attempts'] = []
    with pytest.raises(ValueError):
        comparison_rows(changed)


def test_failed_attempt_cannot_be_hidden_by_successful_summary(fixture):
    _, results = fixture
    changed = serial(results)
    attempt = changed['fixed']['attempts'][0]
    attempt.update(status='failed', statistic=None, error='constructed failure')
    with pytest.raises(ValueError, match='ledger statuses'):
        comparison_rows(changed)


@pytest.mark.parametrize('mutation', [
    'number', 'duplicate_number', 'status', 'nonfinite', 'missing_statistic',
    'changed_statistic', 'exceedances', 'grid_spacing', 'retention_counts',
])
def test_ledger_details_must_agree_with_comparison(fixture, mutation):
    _, results = fixture
    changed = serial(results)
    row = changed['fixed']
    if mutation == 'number':
        row['attempts'][0]['number'] = 10
    elif mutation == 'duplicate_number':
        row['attempts'][1]['number'] = 0
    elif mutation == 'status':
        row['attempts'][0]['status'] = 'unknown'
    elif mutation == 'nonfinite':
        row['attempts'][0]['statistic'] = float('nan')
    elif mutation == 'missing_statistic':
        row['attempts'][0]['statistic'] = None
    elif mutation == 'changed_statistic':
        assert row['attempts'][0]['statistic'] >= row['observed']['mean_change']
        row['attempts'][0]['statistic'] = row['observed']['mean_change'] - 1
    elif mutation == 'exceedances':
        row['exceedances'] -= 1
        row['p_value'] = (1+row['exceedances'])/(1+row['retained'])
    elif mutation == 'grid_spacing':
        row['p_grid_spacing'] *= 2
    else:
        row['retained'] -= 1
        row['no_episode'] += 1
        row['exceedances'] -= 1
        row['p_value'] = (1+row['exceedances'])/(1+row['retained'])
        row['p_grid_spacing'] = 1/(1+row['retained'])
    with pytest.raises(ValueError):
        comparison_rows(changed)


def test_consistent_failed_ledger_keeps_failure_and_suppresses_p(fixture):
    _, results = fixture
    changed = serial(results)
    row = changed['fixed']
    row['attempts'][0].update(status='failed', statistic=None,
                              eligible_onsets=[], changes=[], error='constructed failure')
    row.update(status='invalid_surrogate_failure', p_value=None,
               retained=row['retained']-1, failed=1)
    row['exceedances'] = sum(a['statistic'] >= row['observed']['mean_change']
                             for a in row['attempts'] if a['status'] == 'retained')
    row['p_grid_spacing'] = 1/(row['retained']+1)
    reported = comparison_rows(changed)[3]
    assert reported['status'] == 'invalid_surrogate_failure'
    assert reported['failed'] == 1 and reported['p_value'] is None
    row['p_value'] = (1+row['exceedances'])/(1+row['retained'])
    with pytest.raises(ValueError, match='cannot carry an inferential p-value'):
        comparison_rows(changed)
    row['p_value'] = None
    row['attempts'][0]['statistic'] = .1
    with pytest.raises(ValueError, match='cannot retain a statistic'):
        comparison_rows(changed)


def test_no_episode_attempt_cannot_retain_a_statistic(fixture):
    _, results = fixture
    changed = serial(results)
    row = changed['joint']['primary']
    assert row['attempts'][0]['status'] == 'no_eligible_episode'
    row['attempts'][0]['statistic'] = 0.
    with pytest.raises(ValueError, match='cannot retain a statistic'):
        comparison_rows(changed)


def test_empty_episodes_and_distribution_remain_empty():
    values = np.random.default_rng(81731).uniform(1, 3, 70)
    results = analyze_h1(values, B=2, interval_B=10)
    report = assemble_report(values, results)
    assert report['episodes'] == report['primary_surrogates'] == []
    assert report['comparisons'][0]['value'] is None
    assert report['comparisons'][0]['p_value'] is None
    assert report['interpretation']['conclusion'] == 'not_estimable'
    altered = values.copy()
    altered[-1] += 1
    with pytest.raises(ValueError, match='does not match'):
        assemble_report(altered, results)


def test_failed_rolling_path_is_explicit_not_silently_filled():
    values = np.ones(80)
    values[48:50] = [-1,-.6]
    results = analyze_h1(values, B=2, interval_B=10)
    report = assemble_report(values, results)
    assert report['rolling_error']
    assert all(r['modulus'] is None for r in report['rolling'])
    assert all(r['status'] == 'unavailable_after_failure' for r in report['rolling'])
    assert report['interpretation']['conclusion'] == 'failed'
    altered = values.copy()
    altered[-1] += 1
    with pytest.raises(ValueError, match='does not match'):
        assemble_report(altered, results)


def test_development_bundle_is_labelled_complete_and_cannot_overwrite(tmp_path, fixture):
    values, results = fixture
    folder = tmp_path/'report'
    manifest = write_development_report(folder, values, results,
        fixture_metadata={'data_kind':'artificial_development_fixture'})
    assert len(manifest['file_sha256']) == 12
    for name, checksum in manifest['file_sha256'].items():
        assert digest((folder/name).read_bytes()) == checksum
    for path in folder.glob('*.csv'):
        with path.open(newline='') as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames[0] == 'data_kind'
            assert all(row['data_kind'] == 'artificial_development_fixture' for row in reader)
    for name in ('report.json','analysis.json'):
        assert json.loads((folder/name).read_bytes())['data_kind'] == 'artificial_development_fixture'
    for name in ('persistence.svg','surrogates.svg'):
        assert 'no UK observations' in (folder/name).read_text(encoding='utf-8')
    before = (folder/'manifest.json').read_bytes()
    with pytest.raises(FileExistsError):
        write_development_report(folder, values, results, fixture_metadata={'data_kind':'artificial_development_fixture'})
    assert (folder/'manifest.json').read_bytes() == before


def test_export_rejects_unlabelled_empirical_input_before_creating_files(tmp_path, fixture):
    values, results = fixture
    with pytest.raises(ValueError, match='development'):
        write_development_report(tmp_path/'no-export', values, results, fixture_metadata={'data_kind':'observed'})
    assert not (tmp_path/'no-export').exists()


@pytest.mark.parametrize('interval,d80', [([1.,0.],None), ([0.,float('nan')],None), ([0.,1.],float('inf'))])
def test_invalid_interval_or_D80_is_rejected(interval, d80):
    with pytest.raises(ValueError):
        primary_interpretation(dict(status='ok', value=.2, p_value=.3), {'interval':interval}, D80=d80)
