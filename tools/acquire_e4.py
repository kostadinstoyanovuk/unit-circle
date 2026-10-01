"""E4 X.2: select the edition of the ONS real-time database, acquire it once, map its structure.

prereg/E4.md section 4 and Annex B step 2; the procedure is docs/E4_X2.md and the readings
docs/E4_X2_READINGS.md. Four stages, in order (the structure mapping is the `map` stage of this tool):

  python tools/acquire_e4.py list   --dataset-page FILE [--dataset-page FILE] [--calendar-page FILE]
                                    [--edition-page FILE] [--requests-log FILE]
  python tools/acquire_e4.py list   --fetch URL [--fetch URL ...] --pages-dir DIR
      The release rule over saved pages (or pages requested now through the address allow-list: the two
      dataset landing pages, edition pages and release-calendar records only; never a data file). Prints
      every edition considered, why it is or is not eligible, and any missing evidence. Writes no record.
  python tools/acquire_e4.py select (the same page options) [--accept-missing-evidence]
      G4 for E4. Writes audit/e4_source/edition.json once. Refuses while the pages cannot exclude a later
      edition released before the registration, unless --accept-missing-evidence records that the missing
      evidence cannot be obtained (R-X2.5).
  python tools/acquire_e4.py acquire --download --licence "..." --licence-url https://...
  python tools/acquire_e4.py acquire --downloaded-file FILE.xlsx --source-url URL --retrieved-utc 2026-...Z
                                     --licence "..." --licence-url https://...
      G4 for E4 and the committed edition record. Stores the selected edition's workbook once, read-only and
      git-ignored, with audit/E4_ACQUISITION.json and a DATA_MANIFEST.csv row. Refuses another URL, a file that
      is not an xlsx package and a second acquisition. The X.3 record is not needed.
  python tools/acquire_e4.py map [--amendment audit/E4_AMENDMENT_1.json]
      G4, the committed acquisition record, the workbook's hash and read-only state. Section 4 structure
      mapping, steps 1 to 5, from headers and cell types only. Writes audit/e4_source/structure-attempt-<k>.json
      and .txt for every attempt (and structure-attempts.jsonl); a completed mapping also writes
      structure-mapping.json and .txt and adds the coverage to the manifest row. A stop exits non-zero: stop and
      amend (section 13); after a stop the mapping is run again only with the committed amendment record named.

No stage reads or prints a level.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uc_e4.table import Stop  # noqa: E402
from uc_ext_official import e4_source, gates, records  # noqa: E402


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_page(url, timeout=30):
    """One documentation page; redirects are not followed (the caller has checked the allow-list)."""
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "unit-circle-research",
                                                   "Accept": "text/html", "Accept-Encoding": "identity"})
    with opener.open(request, timeout=timeout) as response:
        info = dict(status=response.status, content_type=response.headers.get("Content-Type"),
                    content_disposition=response.headers.get("Content-Disposition"),
                    retrieved_utc=datetime.now(timezone.utc).isoformat())
        if "text/html" not in str(info["content_type"]).lower():
            return b"", info
        return response.read(5 * 1024 * 1024), info


def download(url, timeout=300):
    """The selected edition's file, requested once."""
    request = urllib.request.Request(url, headers={"User-Agent": "unit-circle-research"})
    retrieved = datetime.now(timezone.utc).isoformat()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content = response.read()
        info = dict(status=response.status, final_url=response.geturl(),
                    content_type=response.headers.get("Content-Type"),
                    content_length=response.headers.get("Content-Length"),
                    last_modified=response.headers.get("Last-Modified"), etag=response.headers.get("ETag"))
    return content, retrieved, info


def _provenance(log):
    """{SHA-256: (url, retrieval time)} from a request log in the format of audit/e4_source/guarded_fetch.py."""
    found = {}
    if log is None:
        return found
    for line in Path(log).read_text(encoding="utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            if entry.get("sha256"):
                found[entry["sha256"]] = (entry.get("url"), entry.get("retrieved_utc") or entry.get("utc_response"))
    return found


def pages_from(args, fetch):
    if args.fetch:
        if not args.pages_dir:
            raise ValueError("--fetch needs --pages-dir, where the pages and the request log are saved")
        return e4_source.fetch_pages(args.fetch, fetch, args.pages_dir)
    known = _provenance(args.requests_log)
    pages = []
    for kind, files in (("dataset", args.dataset_page), ("calendar", args.calendar_page),
                        ("edition", args.edition_page)):
        for path in files or []:
            content = Path(path).read_bytes()
            url, retrieved = known.get(gates.sha256_bytes(content), (None, None))
            pages.append(e4_source.load_page(kind, content, source=Path(path).name, url=url, retrieved_utc=retrieved))
    if not pages:
        raise ValueError("Give the saved pages (--dataset-page, --calendar-page, --edition-page) or --fetch")
    return pages


def _page_options(parser):
    parser.add_argument("--dataset-page", action="append", type=Path, help="a saved dataset landing page")
    parser.add_argument("--calendar-page", action="append", type=Path, help="a saved release-calendar record")
    parser.add_argument("--edition-page", action="append", type=Path, help="a saved edition page")
    parser.add_argument("--requests-log", type=Path, help="request log giving each page's URL and retrieval time")
    parser.add_argument("--fetch", action="append", help="request this page now (allow-list applies)")
    parser.add_argument("--pages-dir", type=Path, help="where requested pages and their log are saved")


def main(argv=None, *, fetch=fetch_page, fetch_file=download):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    stages = parser.add_subparsers(dest="stage", required=True)
    _page_options(stages.add_parser("list"))
    select = stages.add_parser("select")
    _page_options(select)
    select.add_argument("--accept-missing-evidence", action="store_true",
                        help="record that the missing evidence named by the listing cannot be obtained")
    acquire = stages.add_parser("acquire")
    source = acquire.add_mutually_exclusive_group(required=True)
    source.add_argument("--download", action="store_true", help="request the selected edition's file URL now")
    source.add_argument("--downloaded-file", type=Path, help="bytes saved by a browser from the selected URL")
    acquire.add_argument("--source-url", help="the URL the browser download came from")
    acquire.add_argument("--retrieved-utc", help="retrieval time of --downloaded-file (ISO 8601 with offset)")
    acquire.add_argument("--licence", required=True, help="the licence as the dataset page states it")
    acquire.add_argument("--licence-url", required=True, help="the page the licence is taken from")
    mapping = stages.add_parser("map")
    mapping.add_argument("--amendment", help="the committed amendment record that settles the previous stop")
    args = parser.parse_args(argv)
    root = args.root
    try:
        if args.stage == "list":
            print(e4_source.format_evaluation(e4_source.list_editions(root, pages_from(args, fetch))), end="")
        elif args.stage == "select":
            record = e4_source.select_edition(root, pages_from(args, fetch),
                                              accept_missing_evidence=args.accept_missing_evidence)
            print(e4_source.format_evaluation(record), end="")
            print(f"Written: {e4_source.EDITION_RECORD}. Commit it, then run: acquire")
        elif args.stage == "acquire":
            selected = e4_source.load_edition(root)["selected"]
            if args.download:
                content, retrieved, response = fetch_file(selected["file_url"])
                url, method = selected["file_url"], "scripted HTTPS request"
            else:
                if not args.retrieved_utc or not args.source_url:
                    parser.error("--downloaded-file requires --source-url and --retrieved-utc")
                content, retrieved, response = args.downloaded_file.read_bytes(), args.retrieved_utc, None
                url, method = args.source_url, f"browser download from {args.source_url}"
            record = e4_source.acquire(root, content, source_url=url, retrieved_utc=retrieved, method=method,
                                       response=response, licence=args.licence, licence_url=args.licence_url)
            print(json.dumps({k: record[k] for k in ("file", "edition_label", "retrieved_utc", "bytes", "sha256")},
                             indent=2))
            print(f"Stored read-only and git-ignored. Commit {e4_source.ACQUISITION_RECORD} and DATA_MANIFEST.csv "
                  "(not the workbook), then run: map")
        else:
            outcome = e4_source.map_structure(root, amendment=args.amendment)
            print(outcome["text"], end="")
            result = outcome["result"]
            if result["status"] != "mapped":
                stop = result["stop"]
                raise SystemExit(f"Stopped at attempt {result['attempt']} ({stop['kind']}, step {stop['step']}): "
                                 f"{stop['reason']}. Stop and amend (prereg/E4.md section 13): register the amendment "
                                 "before any level is read, commit its record, then run map --amendment <record>.")
            print(f"Mapped. Commit {e4_source.SOURCE_DIR}/ and DATA_MANIFEST.csv.")
    except Stop as stop:
        detail = stop.detail if isinstance(stop.detail, dict) and "editions" in stop.detail else None
        if detail is not None:
            print(e4_source.format_evaluation(detail), end="", file=sys.stderr)
        raise SystemExit(f"Stopped ({stop.step}): {stop.reason}. Stop before reading any value and amend "
                         "(prereg/E4.md section 13).") from None
    except (gates.GateClosed, records.RecordExists, ValueError, OSError, urllib.error.URLError) as error:
        raise SystemExit(f"Refused: {error}") from None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
