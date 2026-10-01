"""E4 X.2 stages (select, acquire, map, and the gated level reader for X.4) on a throwaway research
repository: constructed pages and workbooks, a test copy of the registration record with its own published
tag, and constructed X.3 records. Every refusal path named in prereg/E4.md section 4 and Annex B is exercised,
and no stage may print or record a level."""
import csv
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path

import numpy as np
import pytest

from e4_workbook_builder import (Q2_FIRST, Q2_QNA, calendar_page, commit_all, e4_root, file_url, git, levels,
                                 page_29_september, page_30_september, workbook)
from e_official_artificial import x3_record
from uc_e4.table import Stop
from uc_ext_official import e4_source as s, gates, records

AFTER = "2026-09-30T19:00:00Z"            # a constructed retrieval time after the registration was verified
CODE = "c" * 64
QNA_30 = "GDP quarterly national accounts, UK: April to June 2026"
TOOL = Path(__file__).resolve().parents[1] / "tools/acquire_e4.py"


@pytest.fixture
def root(tmp_path):
    saved = list(sys.path)
    yield e4_root(tmp_path)
    sys.path[:] = saved


def tool():
    spec = importlib.util.spec_from_file_location("acquire_e4_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_pages(root, *pages):
    directory = root.parent / "pages"
    directory.mkdir(exist_ok=True)
    paths = []
    for name, content in pages:
        (directory / name).write_bytes(content)
        paths.append(directory / name)
    return paths


def pages_30():
    return [s.load_page("dataset", page_30_september(), source="dataset-30.html"),
            s.load_page("dataset", page_29_september(), source="dataset-29.html"),
            s.load_page("calendar", calendar_page(QNA_30), source="calendar-30.html")]


def selected(root):
    s.select_edition(root, pages_30())
    commit_all(root, "edition record")


def acquire(root, content=None, **changes):
    arguments = dict(source_url=file_url(Q2_QNA[1]), retrieved_utc=AFTER, method="constructed test download",
                     response=None, licence="constructed licence", licence_url="https://example.invalid/licence")
    arguments.update(changes)
    return s.acquire(root, workbook() if content is None else content, **arguments)


def acquired(root, content=None):
    selected(root)
    record = acquire(root, content)
    commit_all(root, "acquired")
    return record


def manifest(root):
    return list(csv.DictReader((root / "DATA_MANIFEST.csv").open(encoding="utf-8")))


# --------------------------------------------------------------------------------------- select

def test_select_needs_g4_and_writes_the_edition_record_once(root):
    git(root, "tag", "-d", "prereg-E4")
    with pytest.raises(gates.GateClosed, match="prereg-E4"):
        s.select_edition(root, pages_30())
    assert not (root / s.EDITION_RECORD).exists()


def test_select_records_every_edition_and_refuses_a_second_selection(root):
    record = s.select_edition(root, pages_30())
    assert record["selected"]["label"] == Q2_QNA[0] and record["complete"]
    assert record["registration"]["public_registration_timestamp_utc"] == "2026-09-30T06:27:00.909545+00:00"
    saved = json.loads((root / s.EDITION_RECORD).read_text(encoding="utf-8"))
    assert [e["label"] for e in saved["editions"]][:2] == [Q2_QNA[0], Q2_FIRST[0]]
    assert all(page["sha256"] and page["bytes"] for page in saved["pages"])
    with pytest.raises(gates.GateClosed, match="clean"):          # G4 needs the record committed first
        s.select_edition(root, pages_30())
    commit_all(root, "edition record")
    with pytest.raises(records.RecordExists):
        s.select_edition(root, pages_30())


def test_select_refuses_incomplete_evidence_unless_it_is_recorded_as_unobtainable(root):
    only = [s.load_page("dataset", page_29_september(), source="dataset-29.html")]
    with pytest.raises(s.SourceStop, match="missing evidence"):
        s.select_edition(root, only)
    assert not (root / s.EDITION_RECORD).exists()
    record = s.select_edition(root, only, accept_missing_evidence=True)
    assert record["selected"]["label"] == Q2_FIRST[0] and record["accepted_missing_evidence"] is True


def test_list_and_select_from_saved_files_through_the_tool(root, capsys):
    paths = write_pages(root, ("d30.html", page_30_september()), ("d29.html", page_29_september()),
                        ("c30.html", calendar_page(QNA_30, "30 September 2026")))
    options = ["--dataset-page", str(paths[0]), "--dataset-page", str(paths[1]),
               "--calendar-page", str(paths[2])]
    tool().main(["--root", str(root), "list"] + options)
    out = capsys.readouterr().out
    assert "time of day is not established" in out and "Evidence complete: no" in out
    with pytest.raises(SystemExit, match="Stop before reading any value"):
        tool().main(["--root", str(root), "select"] + options)
    assert not (root / s.EDITION_RECORD).exists()


def test_fetch_through_the_tool_uses_only_allowed_addresses(root, capsys):
    calls = []

    def fake(url):
        calls.append(url)
        return page_29_september(), dict(content_type="text/html", status=200, retrieved_utc=AFTER)

    with pytest.raises(SystemExit, match="Refused"):
        tool().main(["--root", str(root), "list", "--fetch", file_url(Q2_FIRST[1]), "--pages-dir",
                     str(root.parent / "fetched")], fetch=fake)
    assert calls == []
    tool().main(["--root", str(root), "list", "--fetch", s.DATASET_URL, "--pages-dir", str(root.parent / "fetched")],
                fetch=fake)
    assert calls == [s.DATASET_URL] and "Selected: " + Q2_FIRST[0] in capsys.readouterr().out


# -------------------------------------------------------------------------------------- acquire

def test_acquire_refusals_before_anything_is_written(root):
    with pytest.raises(gates.GateClosed, match="not committed"):
        acquire(root)
    selected(root)
    with pytest.raises(gates.GateClosed, match="not the file URL"):
        acquire(root, source_url=file_url(Q2_FIRST[1]))
    with pytest.raises(gates.GateClosed, match="not after the verified public registration"):
        acquire(root, retrieved_utc="2026-09-30T06:00:00Z")
    with pytest.raises(s.SourceStop, match="not an xlsx workbook"):
        acquire(root, content=b"<html>constructed challenge page</html>")
    with pytest.raises(ValueError, match="licence"):
        acquire(root, licence="")
    assert not list((root / "data/raw").glob("E4_*")) and len(manifest(root)) == 1


def test_acquire_once_read_only_ignored_with_record_and_manifest_row(root):
    content = workbook()
    record = acquired(root, content)
    raw = root / record["file"]
    assert raw.read_bytes() == content and stat.S_IMODE(raw.stat().st_mode) & 0o222 == 0
    assert record["file"] == s.RAW_PREFIX + Q2_QNA[1] + ".xlsx"
    assert git(root, "check-ignore", record["file"]) == record["file"]
    assert record["edition_label"] == Q2_QNA[0] and record["release_utc"] == "2026-09-30T06:00:00+00:00"
    row = manifest(root)[-1]
    assert (row["file"], row["sha256"], row["source_url"]) == (record["file"], gates.sha256_bytes(content),
                                                               file_url(Q2_QNA[1]))
    assert row["notes"].startswith(s.NOT_DISTRIBUTED) and Q2_QNA[0] in row["notes"]
    with pytest.raises(records.RecordExists, match="acquired once"):
        acquire(root)


def test_acquire_through_the_tool_with_an_injected_download(root, capsys):
    selected(root)
    requested = []

    def fake(url):
        requested.append(url)
        return workbook(), AFTER, dict(status=200)

    tool().main(["--root", str(root), "acquire", "--download", "--licence", "constructed", "--licence-url",
                 "https://example.invalid/licence"], fetch_file=fake)
    assert requested == [file_url(Q2_QNA[1])] and (root / s.ACQUISITION_RECORD).is_file()


# ------------------------------------------------------------------------------------------ map

def test_map_gates_hash_read_only_and_untracked(root):
    record = acquired(root)
    raw = root / record["file"]
    os.chmod(raw, 0o644)
    with pytest.raises(gates.GateClosed, match="not read-only"):
        s.map_structure(root)
    content = raw.read_bytes()
    raw.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
    os.chmod(raw, 0o444)
    with pytest.raises(gates.GateClosed, match="differ"):
        s.map_structure(root)
    os.chmod(raw, 0o644)
    raw.write_bytes(content)
    os.chmod(raw, 0o444)
    git(root, "add", "-f", record["file"])
    git(root, "commit", "-q", "-m", "workbook committed by mistake")
    with pytest.raises(gates.GateClosed, match="tracked by git"):
        s.map_structure(root)
    assert not (root / s.ATTEMPTS_LOG).exists()


def test_map_needs_the_committed_acquisition_record(root):
    selected(root)
    acquire(root)
    with pytest.raises(gates.GateClosed, match="clean"):
        s.map_structure(root)


def test_completed_mapping_is_recorded_once_with_coverage_in_the_manifest(root):
    record = acquired(root)
    outcome = s.map_structure(root)
    result = outcome["result"]
    assert result["status"] == "mapped" and result["manifest"]["earliest_vintage"] == "Jan 2016"
    for relative in (s.MAPPING_JSON, s.MAPPING_TEXT, f"{s.SOURCE_DIR}/structure-attempt-1.json",
                     f"{s.SOURCE_DIR}/structure-attempt-1.txt", s.ATTEMPTS_LOG):
        assert (root / relative).is_file()
    row = next(r for r in manifest(root) if r["file"] == record["file"])
    assert "earliest vintage Jan 2016" in row["notes"] and "earliest reference quarter 1955Q1" in row["notes"]
    printed = (root / s.MAPPING_TEXT).read_text(encoding="utf-8")
    assert "Vintage labels: Jan 2016 | Feb 2016 |" in printed and "Reference-quarter labels: 1955 Q1 | 1955 Q2" in printed
    assert "  Jan 2016 | 2016-01 | 19 | 5 | 0 | 0" in printed          # the staircase: counts per vintage, no level
    commit_all(root, "mapped")
    with pytest.raises(records.RecordExists):
        s.map_structure(root)


def test_a_stop_is_recorded_exits_non_zero_and_a_rerun_needs_a_committed_amendment(root, capsys):
    acquired(root, workbook(overrides={(0, 0): "12.5"}))
    with pytest.raises(SystemExit, match="Stop and amend"):
        tool().main(["--root", str(root), "map"])
    assert "kind other" in capsys.readouterr().out
    attempt = json.loads((root / f"{s.SOURCE_DIR}/structure-attempt-1.json").read_text(encoding="utf-8"))
    assert attempt["status"] == "stopped" and attempt["stop"]["step"] == "4.2"
    assert attempt["stop"]["detail"][0]["content"] == "##.#" and not (root / s.MAPPING_JSON).exists()
    commit_all(root, "stopped attempt")
    with pytest.raises(gates.GateClosed, match="amendment"):
        s.map_structure(root)
    (root / "audit/E4_AMENDMENT_1.json").write_text('{"record_type": "constructed amendment record"}\n')
    commit_all(root, "amendment record")
    second = s.map_structure(root, amendment="audit/E4_AMENDMENT_1.json")["result"]
    assert second["attempt"] == 2 and second["status"] == "stopped" and second["amendment"]["record"]
    lines = (root / s.ATTEMPTS_LOG).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["attempt"] for line in lines] == [1, 2]


@pytest.mark.parametrize("title, kind", [("Quarter 2 (Apr to June) 2026, first estimate", "another edition"),
                                         ("Published 13 August 2026", "another release date")])
def test_title_naming_another_edition_or_release_date_stops_under_the_release_rule(root, title, kind):
    acquired(root, workbook(title_rows=(title,)))
    result = s.map_structure(root)["result"]
    assert result["status"] == "stopped" and result["stop"]["kind"] == "release rule"
    assert result["conflicts"][0]["kind"] == kind and "which file is used" in result["stop"]["consequence"]


def test_title_naming_the_selected_edition_passes(root):
    acquired(root, workbook(title_rows=(f"{Q2_QNA[0]}; released 30 September 2026",)))
    assert s.map_structure(root)["result"]["status"] == "mapped"


# ------------------------------------------------------------------------ no level in any output

PLANTED = (9876543.21, 1357924.68)
TEXTS = ("9876543", "1357924", "87654321", "35792468")


def scrub(text):
    return re.sub(r"[0-9a-f]{64}|[0-9a-f]{12}\.\.\.", "", text)


def test_no_level_appears_in_any_printed_or_recorded_output(root, capsys):
    values = levels(24, 6)
    values[0, 0], values[5, 3] = PLANTED
    content = workbook(values=values, title_rows=("Constructed title with 12.5% and 1,234 and 98765",),
                       notes_rows=("Note: 9876543.21 is a planted value and is blanked",))
    paths = write_pages(root, ("d30.html", page_30_september()), ("d29.html", page_29_september()),
                        ("c30.html", calendar_page(QNA_30)))
    module = tool()
    module.main(["--root", str(root), "select", "--dataset-page", str(paths[0]), "--dataset-page", str(paths[1]),
                 "--calendar-page", str(paths[2])])
    commit_all(root, "edition")
    download = root.parent / "download.xlsx"
    download.write_bytes(content)
    module.main(["--root", str(root), "acquire", "--downloaded-file", str(download), "--source-url",
                 file_url(Q2_QNA[1]), "--retrieved-utc", AFTER, "--licence", "constructed", "--licence-url",
                 "https://example.invalid/licence"])
    commit_all(root, "acquired")
    module.main(["--root", str(root), "map"])
    streams = capsys.readouterr()
    outputs = [streams.out, streams.err] + [p.read_text(encoding="utf-8") for p in (root / "audit").rglob("*")
                                            if p.is_file()] + [(root / "DATA_MANIFEST.csv").read_text(encoding="utf-8")]
    assert "Earliest vintage: Jan 2016" in streams.out and "[num]" in streams.out
    for text in outputs:
        for planted in TEXTS:
            assert planted not in scrub(text)
    assert "12.5%" not in streams.out and "1,234" not in streams.out and "98765" not in scrub(streams.out)


# --------------------------------------------------------------------- level tables for X.4

def mapped(root, content):
    acquired(root, content)
    assert s.map_structure(root)["result"]["status"] == "mapped"
    commit_all(root, "mapped")


def test_level_tables_are_closed_without_x3_and_frozen_code(root):
    values = levels(24, 6)
    mapped(root, workbook(values=values))
    with pytest.raises(gates.GateClosed, match="have not been recorded"):
        s.read_level_tables(root)
    (root / gates.x3_record_path("e4")).write_text(json.dumps(x3_record("e4", "d" * 64), indent=1))
    commit_all(root, "constructed X.3 record with another code identity")
    with pytest.raises(gates.GateClosed, match="differs from the code"):
        s.read_level_tables(root)


def test_level_tables_hold_the_numbers_apart_and_report_only_counts_and_hashes(root):
    values = levels(24, 6)
    mapped(root, workbook(values=values))
    (root / gates.x3_record_path("e4")).write_text(json.dumps(x3_record("e4", CODE), indent=1))
    commit_all(root, "constructed X.3 record")
    out = s.read_level_tables(root)
    table = out["tables"].levels.levels
    present = np.isfinite(table)
    assert np.array_equal(table[present], values[present])          # constructed numbers only
    assert out["summary"]["numeric_cells"] == int(present.sum()) and len(out["summary"]["levels_sha256"]) == 64
    assert set(out["summary"]) == {"n_vintages", "n_reference_quarters", "numeric_cells", "kinds_sha256",
                                   "levels_sha256", "mapping_sha256", "x3_record_sha256"}
