"""Gates and records for the registered H1 acquisition and one-shot run (H1 sections 3, 8, 10, 12).

Every function fails closed. Acquisition requires G1 and a passed G2 review;
the release must be a quarterly national accounts publication released
strictly before the verified public-registration timestamp (D-017) with no
later such publication before that time. The raw file's own header must
identify ABMI, the QNA dataset and the chosen release date.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat

from . import abmi

REGISTRATION_TIMESTAMP = datetime(2026, 9, 27, 4, 49, 1, 989076, tzinfo=timezone.utc)  # D-017
ACQUISITION_RECORD = 'data/raw/ABMI_acquisition.json'
G2_RECORD = 'audit/G2_REVIEW.json'
LICENCE = 'Open Government Licence v3.0'
UK_SUMMER_OFFSET = timedelta(hours=1)


class GateClosed(RuntimeError):
    """A required gate or record is missing or not passed."""


def _utc(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.utcoffset() is None:
        raise ValueError(f'Timestamp needs an explicit offset: {text!r}')
    return value.astimezone(timezone.utc)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def check_g2(root) -> dict:
    """Return the G2 review record only if it exists and records a pass of AT-5, AT-15 and AT-16."""
    path = Path(root) / G2_RECORD
    if not path.is_file():
        raise GateClosed('G2 has not been reviewed; UK acquisition and the registered run stay closed')
    record = json.loads(path.read_text(encoding='utf-8'))
    if record.get('G2') != 'passed' or not all(record.get(key) is True for key in ('AT5_passed', 'AT15_passed', 'AT16_passed')):
        raise GateClosed('G2 is not recorded as passed')
    if 'D80' not in record:
        raise GateClosed('The G2 record must state D80, or null when it is undefined')
    return record


def check_release(release: dict, calendar: list[dict]) -> datetime:
    """The chosen release must be the latest QNA publication strictly before registration."""
    for key in ('title', 'release_datetime', 'release_url', 'file_url'):
        if not release.get(key):
            raise abmi.AcquisitionStop(f'Release metadata lacks {key}')
    if 'quarterly national accounts' not in release['title'].lower():
        raise abmi.AcquisitionStop('The release is not a quarterly national accounts publication')
    if not release['release_url'].startswith('https://www.ons.gov.uk/releases/'):
        raise abmi.AcquisitionStop('The release URL is not an ONS release-calendar record')
    released = _utc(release['release_datetime'])
    if not released < REGISTRATION_TIMESTAMP:
        raise abmi.AcquisitionStop('The release is not strictly before the public-registration timestamp')
    later = [entry['title'] for entry in calendar
             if 'quarterly national accounts' in entry['title'].lower()
             and 'time series' not in entry['title'].lower()
             and released < _utc(entry['release_datetime']) < REGISTRATION_TIMESTAMP]
    if later:
        raise abmi.AcquisitionStop(f'A later eligible publication exists: {later}')
    return released


def uk_release_date(released: datetime) -> str:
    """The DD-MM-YYYY date the ONS file header carries (UK summer time for these dates)."""
    return (released + UK_SUMMER_OFFSET).strftime('%d-%m-%Y')


def record_acquisition(root, content: bytes, release: dict, calendar: list[dict], *,
                       retrieved_utc: str, raw_name: str, retrieval_method: str) -> dict:
    """Check identity from the header, then store the raw bytes read-only with their record."""
    root = Path(root)
    released = check_release(release, calendar)
    parsed = abmi.parse_time_series_csv(content)
    identity = abmi.check_identity(parsed, release_date=uk_release_date(released))
    raw = root / 'data/raw' / raw_name
    record_path = root / ACQUISITION_RECORD
    if raw.exists() or record_path.exists():
        raise abmi.AcquisitionStop('A raw ABMI file or acquisition record already exists; acquisition happens once')
    retrieved = _utc(retrieved_utc)
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(content)
    os.chmod(raw, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    record = dict(file=f'data/raw/{raw_name}', series_id=abmi.SERIES_ID, dataset_id=abmi.DATASET_ID,
                  release_title=release['title'], release_datetime_utc=released.isoformat(),
                  release_url=release['release_url'], file_url=release['file_url'],
                  retrieved_utc=retrieved.isoformat(), retrieval_method=retrieval_method,
                  bytes=len(content), sha256=_sha256(content), licence=LICENCE,
                  registration_timestamp_utc=REGISTRATION_TIMESTAMP.isoformat(), header_identity=identity)
    record_path.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    manifest = root / 'DATA_MANIFEST.csv'
    with manifest.open('a', encoding='utf-8', newline='') as output:
        csv.writer(output, lineterminator='\n').writerow([
            record['file'], record['file_url'], f"ONS {abmi.SERIES_ID} ({abmi.DATASET_ID})", record['retrieved_utc'],
            record['sha256'], LICENCE,
            f"{release['title']}; released {record['release_datetime_utc']}; {release['release_url']}; "
            f"{len(content)} bytes; record {ACQUISITION_RECORD}"])
    return record


def load_registered_levels(root):
    """Verify the frozen raw file and return its record with the 260 registered levels and labels."""
    root = Path(root)
    path = root / ACQUISITION_RECORD
    if not path.is_file():
        raise GateClosed('No acquisition record; the raw ABMI file has not been acquired')
    record = json.loads(path.read_text(encoding='utf-8'))
    raw = root / record['file']
    content = raw.read_bytes()
    if _sha256(content) != record['sha256'] or len(content) != record['bytes']:
        raise abmi.AcquisitionStop('Raw ABMI file bytes differ from the acquisition record')
    parsed = abmi.parse_time_series_csv(content)
    abmi.check_identity(parsed, release_date=record['header_identity']['release_date_record'])
    labels, levels = abmi.registered_sample(parsed)
    return record, labels, levels


def load_registered_growth(root):
    """Verify the frozen raw file and return the 259 registered growth observations with labels."""
    record, labels, levels = load_registered_levels(root)
    growth_labels, values = abmi.growth(labels, levels)
    return record, growth_labels, values
