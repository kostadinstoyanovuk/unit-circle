"""Verify the H1 public-registration timestamp and QNA release-rule invariance.

The check reads saved registry and release-calendar evidence only. It uses no
network access and reads no UK observations. The saved OSF API responses and
Internet Archive metadata are verified against their recorded SHA-256 values;
the ONS entries are programmatically extracted calendar metadata.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'audit/registration-evidence/2026-09-27'
OUTPUT = ROOT / 'audit/h1_timestamp_verification.json'
REGISTRATION_ID = 'wcnbz'
DOI = '10.17605/OSF.IO/WCNBZ'
# First anonymous HTTP 200 observation of the approved public record.
FIRST_PUBLIC_VERIFICATION = '2026-09-27T20:58:15.037124+00:00'
# British Summer Time applies to every ONS release date used here.
UK_OFFSET = timedelta(hours=1)
QNA = re.compile(r'quarterly national accounts', re.IGNORECASE)
MONTHS = {m: i for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July',
     'August', 'September', 'October', 'November', 'December'], start=1)}


class EvidenceError(RuntimeError):
    """Saved evidence is missing, altered or inconsistent."""


def _utc(text):
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)  # OSF and IA timestamps are UTC
    return value.astimezone(timezone.utc)


def _iso(value):
    return value.astimezone(timezone.utc).isoformat()


def _ons_time(text):
    match = re.fullmatch(r'(\d{1,2}) ([A-Za-z]+) (\d{4}) (\d{1,2}):(\d{2})(am|pm)', text.strip())
    if not match:
        raise EvidenceError(f'Unrecognised ONS release time: {text!r}')
    day, month, year, hour, minute, half = match.groups()
    hour = int(hour) % 12 + (12 if half == 'pm' else 0)
    local = datetime(int(year), MONTHS[month], int(day), hour, int(minute))
    return (local - UK_OFFSET).replace(tzinfo=timezone.utc)


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise EvidenceError(f'Unreadable evidence: {path.name}') from error


def _require(condition, message):
    if not condition:
        raise EvidenceError(message)


def verify(evidence=EVIDENCE):
    evidence = Path(evidence)
    log = _load(evidence / 'retrieval-log.json')
    hashes = {}
    for entry in log['retrievals']:
        if entry.get('sha256'):
            actual = _sha256(evidence / entry['file'])
            _require(actual == entry['sha256'], f"Evidence bytes changed: {entry['file']}")
            hashes[entry['file']] = actual

    registration = _load(evidence / 'osf-registration.json')['data']
    attributes = registration['attributes']
    _require(registration['id'] == REGISTRATION_ID, 'Unexpected registration')
    _require(attributes['registration'] is True and attributes['public'] is True,
             'Registration is not public')
    _require(attributes['revision_state'] == 'approved', 'Registration is not approved')
    for flag in ('pending_registration_approval', 'embargoed', 'withdrawn',
                 'pending_withdrawal', 'archiving'):
        _require(attributes[flag] is False, f'Registration state flag is set: {flag}')
    submitted = _utc(attributes['date_registered'])

    responses = _load(evidence / 'osf-schema-responses.json')['data']
    _require(len(responses) == 1, 'Expected exactly one registration response')
    response = responses[0]
    _require(response['relationships']['registration']['data']['id'] == REGISTRATION_ID,
             'Response belongs to another registration')
    _require(response['attributes']['is_original_response'] is True, 'Not the original response')
    _require(response['attributes']['reviews_state'] == 'approved', 'Response is not approved')
    approved = _utc(response['attributes']['date_modified'])

    archive = _load(evidence / 'ia-metadata.json')['metadata']
    _require(archive['identifier'] == f'osf-registrations-{REGISTRATION_ID}-v1', 'Unexpected archive item')
    _require(archive['osf_registration_doi'] == DOI, 'Archive DOI differs')
    _require(archive['source'] == f'https://osf.io/{REGISTRATION_ID}/', 'Archive source differs')
    archived_public = _utc(archive['publicdate'].replace(' ', 'T'))

    first_public = _utc(FIRST_PUBLIC_VERIFICATION)
    _require(submitted < approved <= archived_public <= first_public,
             'Registry timestamps are not in the expected order')

    calendar = _load(evidence / 'ons-calendar-observations.json')['observations']
    published, upcoming = calendar
    _require(published['further_pages'] is False, 'Published calendar is incomplete')
    _require(published['result_count'] == len(published['releases']), 'Calendar count mismatch')
    window_start = (datetime(2026, 9, 25) - UK_OFFSET).replace(tzinfo=timezone.utc)
    window_end = (datetime(2026, 9, 28) - UK_OFFSET).replace(tzinfo=timezone.utc)
    _require(window_start <= submitted and first_public < window_end,
             'Calendar window does not cover the admissible interval')
    for item in published['releases']:
        _require(window_start <= _ons_time(item['release_date_uk']) < window_end,
                 'Calendar entry outside its filter')
    inside = [item['title'] for item in published['releases']
              if QNA.search(item['title'])
              and submitted <= _ons_time(item['release_date_uk']) < first_public]
    later = sorted(_ons_time(item['release_date_uk']) for item in upcoming['releases']
                   if QNA.search(item['title']) and item['status'] == 'Confirmed')
    _require(later, 'No confirmed upcoming QNA publication recorded')
    invariant = not inside and later[0] > first_public

    return {
        'record_type': 'H1 public-registration timestamp and release-rule invariance',
        'registration_id': REGISTRATION_ID,
        'doi': DOI,
        'registry_record_timestamp_utc': _iso(submitted),
        'registry_record_timestamp_meaning': 'OSF date_registered: registration record and attached files frozen at submission; pending approval, not yet public',
        'approval_state_recorded_utc': _iso(approved),
        'approval_state_source': 'OSF original registration response: reviews_state approved, date_modified',
        'internet_archive_public_utc': _iso(archived_public),
        'first_anonymous_public_verification_utc': _iso(first_public),
        'public_registration_timestamp_utc': _iso(approved),
        'public_registration_timestamp_basis': 'Recorded approval of the registration submitted for immediate public visibility; independently bounded above by the Internet Archive public date and the first anonymous verification',
        'admissible_interval_utc': [_iso(submitted), _iso(first_public)],
        'qna_publications_released_in_interval': inside,
        'next_confirmed_qna_publication_utc': _iso(later[0]),
        'release_rule_invariant_over_interval': invariant,
        'release_rule_consequence': 'Every admissible timestamp selects the same latest completed QNA publication; its identity, release-specific file and availability are resolved only after G2 under the registered stop-and-amend rule',
        'evidence_sha256': dict(sorted(hashes.items())),
        'uk_observations_accessed': False,
    }


def main():
    result = verify()
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({key: result[key] for key in (
        'public_registration_timestamp_utc', 'admissible_interval_utc',
        'release_rule_invariant_over_interval')}, indent=2))
    return 0 if result['release_rule_invariant_over_interval'] else 1


if __name__ == '__main__':
    sys.exit(main())
