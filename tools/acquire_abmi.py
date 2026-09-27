"""Record the registered ABMI vintage once (H1 section 3). Closed until G1 and G2 have passed.

The release is chosen by the registered rule from official release metadata,
not from values. Supply that metadata and the ONS release-calendar evidence
as JSON. The file may be fetched here or supplied after a browser download
from the same file URL, with its retrieval time. The header must identify
ABMI, the QNA dataset and the chosen release date, or the command stops
before any value is read.

Example release JSON:
  {"title": "GDP quarterly national accounts, UK: January to March 2026",
   "release_datetime": "2026-06-30T06:00:00+00:00",
   "release_url": "https://www.ons.gov.uk/releases/gdpquarterlynationalaccountsukjanuarytomarch2026",
   "file_url": "https://www.ons.gov.uk/generator?format=csv&uri=..."}
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uc_core import h1_official  # noqa: E402
from uc_core.validation_runner import verify_registration  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--release', type=Path, required=True, help='release metadata JSON')
    parser.add_argument('--calendar', type=Path, required=True, help='JSON list of QNA publications with title and release_datetime')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--download', action='store_true', help='fetch file_url now')
    source.add_argument('--downloaded-file', type=Path, help='bytes saved by a browser from file_url')
    parser.add_argument('--retrieved-utc', help='retrieval time of --downloaded-file (ISO 8601 with offset)')
    parser.add_argument('--raw-name', default='ABMI_QNA.csv')
    args = parser.parse_args()

    receipt = json.loads((ROOT / 'audit/H1_REGISTRATION.json').read_text(encoding='utf-8'))
    verify_registration(ROOT, receipt)
    h1_official.check_g2(ROOT)
    release = json.loads(args.release.read_text(encoding='utf-8'))
    calendar = json.loads(args.calendar.read_text(encoding='utf-8'))
    h1_official.check_release(release, calendar)
    if args.download:
        request = urllib.request.Request(release['file_url'], headers={'User-Agent': 'unit-circle-research'})
        retrieved = datetime.now(timezone.utc).isoformat()
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
        method = 'scripted HTTPS request'
    else:
        if not args.retrieved_utc:
            parser.error('--downloaded-file requires --retrieved-utc')
        content, retrieved, method = args.downloaded_file.read_bytes(), args.retrieved_utc, 'browser download'
    record = h1_official.record_acquisition(ROOT, content, release, calendar, retrieved_utc=retrieved,
                                            raw_name=args.raw_name, retrieval_method=method)
    print(json.dumps({key: record[key] for key in ('file', 'release_title', 'release_datetime_utc', 'bytes', 'sha256')}, indent=2))
    print('Header identity verified; no observation values were printed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
