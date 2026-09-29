"""E1 X.2: acquire the Bank of England millennium workbook once, select the series by header, extract.

Closed until G4 for E1 verifies and audit/E1_X3.json records passed official synthetic checks
(prereg/E1.md section 4, section 11 and Annex B). Four stages, in order:

  python tools/acquire_e1.py acquire --download --licence "..." --licence-url https://...
  python tools/acquire_e1.py acquire --downloaded-file FILE.xlsx --retrieved-utc 2026-...Z --licence ... --licence-url ...
      Stores the first download after verified public registration read-only as
      data/raw/a-millennium-of-macroeconomic-data-for-the-uk.xlsx, with data/raw/E1_acquisition.json and a
      DATA_MANIFEST.csv row. A browser download must come from the registered file URL. Refuses a second
      acquisition. Nothing is read beyond checking that the bytes are an xlsx package. The workbook is
      kept out of git (D-041): its path must be git-ignored, and only the record and the manifest row
      are committed.
  python tools/acquire_e1.py select [--version-location LOC] [--first-data-row N] [--year-column A]
      Text only: the version statement (version 3.1 or stop), the header-only output and the selection
      rule. Writes audit/e1_source/header-only.txt, header-only.json and selection.json once; every
      attempt, stopped or not, is appended to audit/e1_source/selection-attempts.jsonl. The options exist
      for text-only layout facts and for naming the file's own version statement; each is recorded.
  python tools/acquire_e1.py territory --record territory.json
      The territory of each stretch 1700-2016, each quoting the workbook text that states it (checked).
  python tools/acquire_e1.py extract
      Commit and push every record first (a clean tree is required). The first stage that reads values:
      the 317 levels under the section 4 stop rules. Prints counts and hashes only. Completes the
      manifest row. A stop writes audit/e1_source/extraction-stop.json: document an amendment.

No stage prints a numeric cell.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uc_ext_official import e1_source, gates, records  # noqa: E402


def download(url=e1_source.FILE_URL, timeout=300):
    request = urllib.request.Request(url, headers={"User-Agent": "unit-circle-research"})
    retrieved = datetime.now(timezone.utc).isoformat()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content = response.read()
        info = dict(status=response.status, final_url=response.geturl(),
                    content_type=response.headers.get("Content-Type"),
                    content_length=response.headers.get("Content-Length"),
                    last_modified=response.headers.get("Last-Modified"), etag=response.headers.get("ETag"))
    return content, retrieved, info


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    stages = parser.add_subparsers(dest="stage", required=True)
    acquire = stages.add_parser("acquire")
    source = acquire.add_mutually_exclusive_group(required=True)
    source.add_argument("--download", action="store_true", help="fetch the registered file URL now")
    source.add_argument("--downloaded-file", type=Path, help="bytes saved by a browser from the registered URL")
    acquire.add_argument("--retrieved-utc", help="retrieval time of --downloaded-file (ISO 8601 with offset)")
    acquire.add_argument("--licence", required=True, help="the licence as the Bank's terms state it")
    acquire.add_argument("--licence-url", required=True, help="the page the licence is taken from")
    select = stages.add_parser("select")
    select.add_argument("--version-location", help="the statement that identifies this file (as listed)")
    select.add_argument("--first-data-row", type=int)
    select.add_argument("--year-column")
    territory = stages.add_parser("territory")
    territory.add_argument("--record", type=Path, required=True)
    stages.add_parser("extract")
    args = parser.parse_args(argv)
    root = args.root
    try:
        if args.stage == "acquire":
            if args.download:
                content, retrieved, response = download()
                method = "scripted HTTPS request"
            else:
                if not args.retrieved_utc:
                    parser.error("--downloaded-file requires --retrieved-utc")
                content, retrieved, response = args.downloaded_file.read_bytes(), args.retrieved_utc, None
                method = f"browser download from {e1_source.FILE_URL}"
            record = e1_source.acquire(root, content, retrieved_utc=retrieved, method=method, response=response,
                                       licence=args.licence, licence_url=args.licence_url)
            print(json.dumps({k: record[k] for k in ("file", "retrieved_utc", "bytes", "sha256")}, indent=2))
            print("Stored read-only and git-ignored. Commit and push data/raw/E1_acquisition.json and "
                  "DATA_MANIFEST.csv (not the workbook), then run: select")
        elif args.stage == "select":
            result = e1_source.select(root, version_location=args.version_location,
                                      first_data_row=args.first_data_row, year_column=args.year_column)
            print(result["text"])
            print("Review the header-only output and the selection, then record the territory.")
        elif args.stage == "territory":
            spec = json.loads(args.record.read_text(encoding="utf-8"))
            record = e1_source.record_territory(root, spec)
            print(json.dumps(record["stretches"], indent=2, ensure_ascii=False))
            print("Commit and push every E1 X.2 record, then run: extract")
        else:
            record = e1_source.extract(root)
            print(json.dumps({k: record[k] for k in ("first_year", "last_year", "levels", "growth", "levels_sha256",
                                                     "growth_sha256")}, indent=2))
            print("Levels verified under the stop rules; no value was printed. Commit and push the record.")
    except e1_source.SourceStop as stop:
        print(json.dumps(dict(stage=stop.stage, reason=str(stop)), indent=2), file=sys.stderr)
        if stop.stage == "version":
            print("Version statements found (text only):", file=sys.stderr)
            for statement in stop.details.get("all_statements", []):
                print(f"  [{statement['level']}] {statement['location']}: {statement['text']}", file=sys.stderr)
        elif stop.details.get("sheets"):
            print(e1_source.format_header_only(stop.details, None, f"see {e1_source.ACQUISITION_RECORD}"),
                  file=sys.stderr)
        raise SystemExit(f"Stopped ({stop.stage}): {stop}. Stop and document an amendment, or correct a "
                         "text-only layout option, as prereg/E1.md section 4 allows.") from None
    except (gates.GateClosed, records.RecordExists, ValueError) as error:
        raise SystemExit(f"Refused: {error}") from None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
