"""E1 X.2 (acquire, select, territory, extract) and E3 X.2 (data note) on a throwaway integrated research
root: artificial workbook, artificial ONS-format ABMI file, test copies of the registration records with
their own published tags, and artificial X.3 records. Every refusal path is exercised."""
import csv
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from e_official_artificial import (GITIGNORE_ADDITIONS, TERRITORY, artificial_workbook, commit_all, git,
                                   integrated_root, x3_record)
from uc_ext_official import e1_source as s, e3_source, gates, records

CODE = "c" * 64
AFTER = "2026-09-29T01:00:00Z"              # an artificial retrieval time after the registration was verified


@pytest.fixture
def root(tmp_path):
    saved = list(sys.path)
    yield integrated_root(tmp_path)
    sys.path[:] = saved


def passed_x3(root, extension="e1", **changes):
    (root / gates.x3_record_path(extension)).write_text(json.dumps(x3_record(extension, CODE, **changes), indent=1))
    commit_all(root, f"artificial {extension} X.3 record")


def acquire(root, content=None, **changes):
    arguments = dict(retrieved_utc=AFTER, method="artificial test download", response=None,
                     licence="artificial licence", licence_url="https://example.invalid/licence")
    arguments.update(changes)
    return s.acquire(root, artificial_workbook() if content is None else content, **arguments)


def manifest_rows(root):
    return list(csv.DictReader((root / "DATA_MANIFEST.csv").open(encoding="utf-8")))


def check_data_module(root):
    spec = importlib.util.spec_from_file_location("check_data_test", root / "tools/check_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_data(root):
    return check_data_module(root).check(root)


# ------------------------------------------------------------------------------- acquire

def test_acquire_is_closed_until_x3_has_passed(root):
    with pytest.raises(gates.GateClosed, match="have not been recorded"):
        acquire(root)
    passed_x3(root, X3="failed", size_passed=False)
    with pytest.raises(gates.GateClosed, match="not recorded as passed"):
        acquire(root)
    assert not (root / s.RAW_FILE).exists() and not (root / s.ACQUISITION_RECORD).exists()


def test_acquire_refusals_before_anything_is_written(root):
    passed_x3(root)
    (root / "stray.txt").write_text("uncommitted\n")
    with pytest.raises(gates.GateClosed, match="clean"):
        acquire(root)
    (root / "stray.txt").unlink()
    with pytest.raises(gates.GateClosed, match="not after the verified public registration"):
        acquire(root, retrieved_utc="2026-09-28T15:57:37Z")
    with pytest.raises(ValueError, match="offset"):
        acquire(root, retrieved_utc="2026-09-29T01:00:00")
    with pytest.raises(s.SourceStop, match="not an xlsx workbook"):
        acquire(root, content=b"<html>artificial challenge page</html>")
    with pytest.raises(ValueError, match="licence"):
        acquire(root, licence="")
    kept = [line for line in (root / ".gitignore").read_text(encoding="utf-8").splitlines() if line not in GITIGNORE_ADDITIONS]
    (root / ".gitignore").write_text("\n".join(kept) + "\n")
    commit_all(root, "the exception for the acquisition record removed")
    with pytest.raises(gates.GateClosed, match="ignored by git"):
        acquire(root)
    assert not (root / s.RAW_FILE).exists() and len(manifest_rows(root)) == 1


def test_acquire_once_read_only_with_manifest_row(root):
    passed_x3(root)
    content = artificial_workbook()
    record = acquire(root, content)
    raw = root / s.RAW_FILE
    assert raw.read_bytes() == content and stat.S_IMODE(raw.stat().st_mode) & 0o222 == 0
    assert record["sha256"] == gates.sha256_bytes(content) and record["registration"]["registration_id"] == "mjg9w"
    assert record["x3_code_sha256"] == CODE and record["source_url"] == s.FILE_URL
    row = manifest_rows(root)[-1]
    assert (row["file"], row["sha256"], row["source_url"]) == (s.RAW_FILE, record["sha256"], s.FILE_URL)
    assert check_data(root) == (2, [])
    commit_all(root, "acquired")
    with pytest.raises(records.RecordExists, match="acquired once"):
        acquire(root)


# ------------------------------------------------------------- select, territory, extract

def acquired(root, content=None):
    passed_x3(root)
    acquire(root, content)
    commit_all(root, "acquired")


def test_full_x2_sequence(root):
    acquired(root)
    with pytest.raises(gates.GateClosed, match="No E1 selection record"):
        s.record_territory(root, TERRITORY)
    result = s.select(root)
    assert result["selection"]["column"] == "C" and "Selected: sheet" in result["text"]
    assert (root / s.HEADER_TEXT).read_text(encoding="utf-8") == result["text"]
    attempts = [json.loads(line) for line in (root / s.ATTEMPTS_LOG).read_text(encoding="utf-8").splitlines()]
    assert [a["status"] for a in attempts] == ["selected"]
    with pytest.raises(records.RecordExists):
        s.select(root)
    with pytest.raises(ValueError, match="not in the workbook"):
        s.record_territory(root, dict(stretches=[dict(first_year=1700, last_year=2016, territory="Wales",
                                                      evidence=[dict(location="Cover (artificial)!A1",
                                                                     quote="Wales")])]))
    assert not (root / s.TERRITORY_RECORD).exists()
    territory = s.record_territory(root, TERRITORY)
    assert [x["territory"] for x in territory["stretches"]] == ["England", "Great Britain", "UK"]
    with pytest.raises(records.RecordExists):
        s.record_territory(root, TERRITORY)
    with pytest.raises(gates.GateClosed, match="clean"):
        s.extract(root)                                     # records not yet committed
    commit_all(root, "selection and territory")
    record = s.extract(root)
    assert (record["levels"], record["growth"], record["first_growth_year"]) == (317, 316, 1701)
    row = manifest_rows(root)[-1]
    assert "Version 3.1 (artificial test fixture)" in row["notes"] and "column C" in row["notes"]
    assert "units: GBP mn, artificial prices" in row["notes"] and "1801-2016 UK" in row["notes"]
    assert row["sha256"] == record["raw_sha256"] and check_data(root) == (2, [])
    manifest = (root / "DATA_MANIFEST.csv").read_text(encoding="utf-8").splitlines()
    assert manifest[1].startswith("data/raw/ABMI_QNA.csv")              # other rows unchanged
    with pytest.raises(gates.GateClosed, match="clean"):
        s.extract(root)
    commit_all(root, "extraction")
    with pytest.raises(records.RecordExists, match="once"):
        s.extract(root)
    loaded = s.load_registered_growth(root)
    assert len(loaded["growth"]) == 316 and loaded["growth_years"][-1] == 2016
    assert set(loaded["record_sha256"]) == {s.ACQUISITION_RECORD, s.SELECTION_RECORD, s.TERRITORY_RECORD,
                                            s.EXTRACTION_RECORD}
    raw = root / s.RAW_FILE
    os.chmod(raw, stat.S_IWUSR | stat.S_IRUSR)
    raw.write_bytes(artificial_workbook(version_text="Version 3.1 (artificial, altered)"))
    with pytest.raises((s.SourceStop, gates.GateClosed), match="differ"):
        s.load_registered_growth(root)


def test_stopped_selection_is_logged_and_the_operator_may_name_the_version(root):
    content = artificial_workbook(version_text="This file: version 3.1 (artificial)",
                                  extra_cover=("History: version 3.0 (artificial)",))
    acquired(root, content)
    with pytest.raises(s.SourceStop, match="another version"):
        s.select(root)
    assert not (root / s.SELECTION_RECORD).exists() and not (root / s.HEADER_TEXT).exists()
    result = s.select(root, version_location="Cover (artificial)!A2")
    assert result["selection"]["version"]["designated_by_operator"] is True
    attempts = [json.loads(line) for line in (root / s.ATTEMPTS_LOG).read_text(encoding="utf-8").splitlines()]
    assert [(a["status"], a.get("stage")) for a in attempts] == [("stopped", "version"), ("selected", None)]
    assert attempts[1]["options"]["version_location"] == "Cover (artificial)!A2"


def test_selection_stop_for_an_ambiguous_column_is_logged(root):
    from e_official_artificial import standard_columns
    columns = [standard_columns()[1], ("Real GDP, United Kingdom (artificial)", None, None, lambda y, v: v)]
    acquired(root, artificial_workbook(columns=columns))
    with pytest.raises(s.SourceStop, match="exactly one") as stop:
        s.select(root)
    assert len(stop.value.details["real_gdp_columns"]) == 2
    (attempt,) = [json.loads(line) for line in (root / s.ATTEMPTS_LOG).read_text(encoding="utf-8").splitlines()]
    assert attempt["status"] == "stopped" and attempt["stage"] == "selection"


def test_sample_stop_writes_a_stop_record_and_extraction_stays_closed(root):
    acquired(root, artificial_workbook(years=[y for y in range(1600, 2021) if y != 1900]))
    s.select(root)
    s.record_territory(root, TERRITORY)
    commit_all(root, "records")
    with pytest.raises(s.SourceStop, match="317 contiguous"):
        s.extract(root)
    stop = json.loads((root / s.EXTRACTION_STOP).read_text(encoding="utf-8"))
    assert "317 contiguous" in stop["reason"] and not (root / s.EXTRACTION_RECORD).exists()
    commit_all(root, "stop record")
    with pytest.raises(records.RecordExists):
        s.extract(root)
    with pytest.raises(gates.GateClosed, match="E1 X.2 is not complete"):
        s.load_registered_growth(root)


def test_extract_needs_every_record(root):
    acquired(root)
    with pytest.raises(gates.GateClosed, match="missing"):
        s.extract(root)
    s.select(root)
    commit_all(root, "selection")
    with pytest.raises(gates.GateClosed, match="territory.json is missing"):
        s.extract(root)


def test_extract_rechecks_the_x3_gate(root):
    acquired(root)
    s.select(root)
    s.record_territory(root, TERRITORY)
    (root / gates.x3_record_path("e1")).write_text(json.dumps(x3_record("e1", CODE, X3="failed")))
    commit_all(root, "records; X.3 record replaced")
    with pytest.raises(gates.GateClosed, match="not recorded as passed"):
        s.extract(root)


# ------------------------------------------------------------------------------ E3 note

def test_e3_data_note(root):
    record = e3_source.record_data_note(root)
    assert record["sha256"] == json.loads((root / "data/raw/ABMI_acquisition.json").read_text(encoding="utf-8"))["sha256"]
    row = manifest_rows(root)[0]
    assert "E3 (prereg-E3, OSF rhzsm) uses this file unchanged" in row["notes"] and check_data(root) == (1, [])
    with pytest.raises(gates.GateClosed, match="clean"):
        e3_source.record_data_note(root)
    with pytest.raises(gates.GateClosed, match="not committed"):
        e3_source.check_data_note(root)
    commit_all(root, "E3 note")
    assert e3_source.check_data_note(root)["file"] == "data/raw/ABMI_QNA.csv"
    with pytest.raises(records.RecordExists):
        e3_source.record_data_note(root)


def test_e3_data_note_refusals(root):
    with pytest.raises(gates.GateClosed, match="E3 X.2"):
        e3_source.check_data_note(root)
    abmi = root / "data/raw/ABMI_QNA.csv"
    abmi.write_bytes(abmi.read_bytes() + b"\n")
    commit_all(root, "artificial ABMI altered")
    with pytest.raises(gates.GateClosed, match="differ"):
        e3_source.record_data_note(root)
    git(root, "tag", "-d", "prereg-E3")
    with pytest.raises(gates.GateClosed, match="absent"):
        e3_source.record_data_note(root)


def test_select_refusals(root):
    with pytest.raises(gates.GateClosed, match="has not been acquired"):
        s.select(root)
    acquired(root)
    raw = root / s.RAW_FILE
    os.chmod(raw, stat.S_IWUSR | stat.S_IRUSR)
    raw.write_bytes(raw.read_bytes() + b"\0")
    with pytest.raises(s.SourceStop, match="differ from its acquisition record"):
        s.select(root)
    assert not (root / s.ATTEMPTS_LOG).exists()


def test_re_extraction_must_equal_the_extraction_record(root):
    acquired(root)
    s.select(root)
    s.record_territory(root, TERRITORY)
    commit_all(root, "records")
    s.extract(root)
    record = json.loads((root / s.EXTRACTION_RECORD).read_text(encoding="utf-8"))
    record["levels_sha256"] = "0" * 64
    (root / s.EXTRACTION_RECORD).write_text(json.dumps(record))
    commit_all(root, "extraction record altered")
    with pytest.raises(s.SourceStop, match="re-extracted levels differ"):
        s.load_registered_growth(root)


def test_e3_note_edge_cases(root):
    lines = (root / "DATA_MANIFEST.csv").read_text(encoding="utf-8").splitlines()
    (root / "DATA_MANIFEST.csv").write_text(lines[0] + "\n")
    commit_all(root, "ABMI row removed")
    with pytest.raises(gates.GateClosed, match="does not list"):
        e3_source.record_data_note(root)
    (root / "DATA_MANIFEST.csv").write_text("\n".join(lines) + "\n")
    commit_all(root, "ABMI row restored")
    e3_source.record_data_note(root)
    note = json.loads((root / e3_source.NOTE_RECORD).read_text(encoding="utf-8"))
    note["sha256"] = "0" * 64
    (root / e3_source.NOTE_RECORD).write_text(json.dumps(note))
    commit_all(root, "note altered")
    with pytest.raises(gates.GateClosed, match="another file or hash"):
        e3_source.check_data_note(root)
    (root / e3_source.NOTE_RECORD).unlink()
    commit_all(root, "note removed; manifest note kept")
    with pytest.raises(records.RecordExists, match="already carries"):
        e3_source.record_data_note(root)


def _tool(name):
    from e_official_artificial import PACKAGE
    spec = importlib.util.spec_from_file_location(f"tool_{name}", PACKAGE / f"tools/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_command_line_sequence_prints_no_value(root, tmp_path, capsys):
    tool = _tool("acquire_e1")
    passed_x3(root)
    content = artificial_workbook()
    (tmp_path / "artificial.xlsx").write_bytes(content)
    base = ["--root", str(root)]
    assert tool.main([*base, "acquire", "--downloaded-file", str(tmp_path / "artificial.xlsx"), "--retrieved-utc",
                      AFTER, "--licence", "artificial", "--licence-url", "https://example.invalid/licence"]) == 0
    commit_all(root, "acquired")
    assert tool.main([*base, "select"]) == 0
    (tmp_path / "territory.json").write_text(json.dumps(TERRITORY))
    assert tool.main([*base, "territory", "--record", str(tmp_path / "territory.json")]) == 0
    commit_all(root, "records")
    assert tool.main([*base, "extract"]) == 0
    printed = capsys.readouterr()
    record = json.loads((root / s.ACQUISITION_RECORD).read_text(encoding="utf-8"))
    assert "browser download" in record["retrieval_method"] and "Selected: sheet" in printed.out
    from uc_ext_official.workbook import Workbook
    wb = Workbook(content)
    levels = {cell.text for cell in wb.cells(wb.sheet("A1 Headline series (artificial)"), numbers=True,
                                               columns={2, 3, 4, 5}) if cell.kind == "number"}
    assert not [value for value in levels if value in printed.out or value in printed.err]


def test_command_line_version_stop_lists_the_statements(root, tmp_path, capsys):
    tool = _tool("acquire_e1")
    acquired(root, artificial_workbook(version_text="Version 3.0 (artificial)"))
    with pytest.raises(SystemExit, match=r"Stopped \(version\)"):
        tool.main(["--root", str(root), "select"])
    assert "Cover (artificial)!A2: Version 3.0 (artificial)" in capsys.readouterr().err


# ------------------------------------------------------- the workbook is kept out of git (D-041)

def test_the_workbook_is_ignored_while_its_record_and_manifest_row_are_committed(root):
    passed_x3(root)
    record = acquire(root)
    assert record["repository_copy"].startswith(s.NOT_DISTRIBUTED)
    commit_all(root, "acquired")
    tracked = git(root, "ls-files").splitlines()
    assert s.ACQUISITION_RECORD in tracked and s.RAW_FILE not in tracked and (root / s.RAW_FILE).is_file()
    assert manifest_rows(root)[-1]["notes"].startswith(s.NOT_DISTRIBUTED)
    s.select(root)
    s.record_territory(root, TERRITORY)
    commit_all(root, "records")
    s.extract(root)
    assert manifest_rows(root)[-1]["notes"].startswith(s.NOT_DISTRIBUTED)      # still marked once completed
    commit_all(root, "extraction")
    assert s.RAW_FILE not in git(root, "ls-files").splitlines()
    assert len(s.load_registered_growth(root)["growth"]) == 316


def test_acquire_refuses_a_workbook_path_that_git_would_track(root):
    passed_x3(root)
    with (root / ".gitignore").open("a", encoding="utf-8") as output:
        output.write(f"!{s.RAW_FILE}\n")
    commit_all(root, "an exception for the workbook")
    with pytest.raises(gates.GateClosed, match="would not be ignored by git"):
        acquire(root)
    assert not (root / s.RAW_FILE).exists() and len(manifest_rows(root)) == 1


def test_a_tracked_workbook_stops_every_stage_that_reads_it(root):
    acquired(root)
    git(root, "add", "-f", s.RAW_FILE)
    commit_all(root, "the workbook committed against D-041")
    with pytest.raises(gates.GateClosed, match="tracked by git"):
        s.select(root)
    assert not (root / s.SELECTION_RECORD).exists() and not (root / s.ATTEMPTS_LOG).exists()


def test_a_missing_workbook_is_reported_with_its_hash(root):
    acquired(root)
    expected = json.loads((root / s.ACQUISITION_RECORD).read_text(encoding="utf-8"))["sha256"]
    raw = root / s.RAW_FILE
    os.chmod(raw, stat.S_IWUSR | stat.S_IRUSR)
    raw.unlink()
    with pytest.raises(gates.GateClosed, match="is missing") as stop:
        s.select(root)
    assert expected in str(stop.value) and not (root / s.ATTEMPTS_LOG).exists()


def test_a_manifest_row_of_a_file_kept_out_of_git_may_be_absent_but_never_wrong(root):
    assert check_data_module(root).NOT_DISTRIBUTED == s.NOT_DISTRIBUTED
    passed_x3(root)
    acquire(root)
    raw = root / s.RAW_FILE
    assert check_data(root) == (2, [])
    os.chmod(raw, stat.S_IWUSR | stat.S_IRUSR)
    raw.write_bytes(raw.read_bytes() + b"\0")
    assert check_data(root) == (2, [f"hash differs: {s.RAW_FILE}"])
    raw.unlink()
    assert check_data(root) == (1, [])                       # marked and absent: not reported
    manifest = root / "DATA_MANIFEST.csv"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(s.NOT_DISTRIBUTED, "Kept elsewhere"),
                        encoding="utf-8")
    assert check_data(root) == (1, [f"missing: {s.RAW_FILE}"])
