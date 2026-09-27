"""Registration-timestamp evidence checks; saved metadata only, no network or UK data."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'verify_registration_timestamp', ROOT / 'tools/verify_registration_timestamp.py')
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


@pytest.fixture
def evidence(tmp_path):
    target = tmp_path / 'evidence'
    shutil.copytree(check.EVIDENCE, target)
    return target


def _rewrite(path, change):
    data = json.loads(path.read_text(encoding='utf-8'))
    change(data)
    path.write_text(json.dumps(data), encoding='utf-8')


def _rehash(evidence, name):
    log_path = evidence / 'retrieval-log.json'
    log = json.loads(log_path.read_text(encoding='utf-8'))
    for entry in log['retrievals']:
        if entry.get('file') == name:
            entry['sha256'] = check._sha256(evidence / name)
    log_path.write_text(json.dumps(log), encoding='utf-8')


def test_saved_evidence_reproduces_committed_record():
    committed = json.loads((ROOT / 'audit/h1_timestamp_verification.json').read_text(encoding='utf-8'))
    result = check.verify()
    assert result == committed
    assert result['release_rule_invariant_over_interval'] is True
    assert result['qna_publications_released_in_interval'] == []
    assert result['admissible_interval_utc'][0] < result['public_registration_timestamp_utc']
    assert result['public_registration_timestamp_utc'] < result['admissible_interval_utc'][1]


def test_altered_registry_bytes_fail(evidence):
    path = evidence / 'osf-schema-responses.json'
    path.write_bytes(path.read_bytes().replace(b'04:49:01', b'03:49:01'))
    with pytest.raises(check.EvidenceError, match='bytes changed'):
        check.verify(evidence)


def test_pending_registration_fails(evidence):
    name = 'osf-registration.json'
    _rewrite(evidence / name, lambda d: d['data']['attributes'].update(pending_registration_approval=True))
    _rehash(evidence, name)
    with pytest.raises(check.EvidenceError, match='pending_registration_approval'):
        check.verify(evidence)


def test_qna_publication_inside_interval_breaks_invariance(evidence):
    name = 'ons-calendar-observations.json'

    def add_release(data):
        published = data['observations'][0]
        published['releases'].append({'title': 'GDP quarterly national accounts, UK: constructed',
                                      'release_date_uk': '26 September 2026 7:00am',
                                      'status': 'Published', 'path': '/constructed'})
        published['result_count'] += 1
    _rewrite(evidence / name, add_release)
    result = check.verify(evidence)
    assert result['release_rule_invariant_over_interval'] is False
    assert result['qna_publications_released_in_interval'] == ['GDP quarterly national accounts, UK: constructed']


def test_ons_times_use_british_summer_time():
    assert check._ons_time('30 September 2026 7:00am').isoformat() == '2026-09-30T06:00:00+00:00'
    assert check._ons_time('25 September 2026 9:30am').isoformat() == '2026-09-25T08:30:00+00:00'
    assert check._ons_time('25 September 2026 12:15pm').isoformat() == '2026-09-25T11:15:00+00:00'
