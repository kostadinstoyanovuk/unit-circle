"""Record helpers and the command-line tools' refusals (arguments and closed gates). No data are read."""
import importlib.util
import json

import pytest

from e_official_artificial import PACKAGE, artificial_workbook
from uc_ext_official import records

HEADER = "file,source_url,series_id,retrieved_utc,sha256,licence,notes\n"


def tool(name):
    spec = importlib.util.spec_from_file_location(f"tool_{name}", PACKAGE / f"tools/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(file, sha="a" * 64, notes="n"):
    return dict(file=file, source_url="https://example.invalid", series_id="artificial", retrieved_utc="t",
                sha256=sha, licence="artificial", notes=notes)


# ---------------------------------------------------------------------------------- records

def test_write_once_and_json_safety(tmp_path):
    path = records.write_once(tmp_path / "a/b.json", records.pretty(dict(x=float("nan"), y=[1.5, float("inf")])))
    assert json.loads(path.read_text(encoding="utf-8")) == dict(x=None, y=[1.5, None])
    with pytest.raises(records.RecordExists):
        records.write_once(path, b"{}")
    assert records.canonical({2: 1, "a": (1, 2)}) == b'{"2":1,"a":[1,2]}'


def test_manifest_rows_are_appended_once_and_replaced_in_place(tmp_path):
    (tmp_path / "DATA_MANIFEST.csv").write_text(HEADER + 'data/raw/x.csv,u,s,t,' + "b" * 64 + ',l,"a, b"\n')
    records.append_manifest_row(tmp_path, row("data/raw/y.xlsx"))
    with pytest.raises(records.RecordExists):
        records.append_manifest_row(tmp_path, row("data/raw/y.xlsx"))
    before = (tmp_path / "DATA_MANIFEST.csv").read_text(encoding="utf-8").splitlines()
    records.replace_manifest_row(tmp_path, "data/raw/y.xlsx", "a" * 64, notes="completed, with a comma")
    after = (tmp_path / "DATA_MANIFEST.csv").read_text(encoding="utf-8").splitlines()
    assert after[:2] == before[:2] and records.manifest_row(tmp_path, "data/raw/y.xlsx")["notes"] == \
        "completed, with a comma"
    with pytest.raises(ValueError, match="another SHA-256"):
        records.replace_manifest_row(tmp_path, "data/raw/y.xlsx", "c" * 64, notes="x")
    with pytest.raises(ValueError, match="Only series_id and notes"):
        records.replace_manifest_row(tmp_path, "data/raw/y.xlsx", "a" * 64, licence="other")
    with pytest.raises(ValueError, match="exactly once"):
        records.replace_manifest_row(tmp_path, "data/raw/z.csv", "a" * 64, notes="x")


def test_manifest_format_refusals(tmp_path):
    with pytest.raises(FileNotFoundError):
        records.manifest_row(tmp_path, "x")
    (tmp_path / "DATA_MANIFEST.csv").write_text("file,sha256\n")
    with pytest.raises(ValueError, match="expected header"):
        records.manifest_row(tmp_path, "x")
    (tmp_path / "DATA_MANIFEST.csv").write_text(HEADER + 'x,u,s,t,h,l,"two\nlines"\n')
    with pytest.raises(ValueError, match="multi-line"):
        records.manifest_row(tmp_path, "x")
    (tmp_path / "DATA_MANIFEST.csv").write_text(HEADER + "x,u,s,t,h,l,n\nx,u,s,t,h,l,n\n")
    with pytest.raises(ValueError, match="more than once"):
        records.manifest_row(tmp_path, "x")


# ---------------------------------------------------------------------------------- tools

def not_integrated(tmp_path):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    return ["--root", str(root)]


def test_record_e_x3_refuses_outside_an_integrated_root(tmp_path):
    with pytest.raises(SystemExit, match="Refused: .*not integrated"):
        tool("record_e_x3").main(["e1", "--size", "a", "--power", "b", *not_integrated(tmp_path)])
    with pytest.raises(SystemExit):
        tool("record_e_x3").main(["e2", "--size", "a", "--power", "b"])


def test_acquire_e1_arguments_and_refusals(tmp_path, capsys):
    acquire = tool("acquire_e1")
    (tmp_path / "artificial.xlsx").write_bytes(artificial_workbook())
    with pytest.raises(SystemExit) as error:
        acquire.main([*not_integrated(tmp_path), "acquire", "--downloaded-file", str(tmp_path / "artificial.xlsx"),
                      "--licence", "l", "--licence-url", "u"])
    assert error.value.code == 2                                  # --retrieved-utc is required with a file
    with pytest.raises(SystemExit, match="Refused: .*not integrated"):
        acquire.main([*not_integrated(tmp_path), "acquire", "--downloaded-file", str(tmp_path / "artificial.xlsx"),
                      "--retrieved-utc", "2026-09-29T01:00:00Z", "--licence", "l", "--licence-url", "u"])
    for stage in (["select"], ["territory", "--record", str(tmp_path / "t.json")], ["extract"]):
        (tmp_path / "t.json").write_text("{}")
        with pytest.raises(SystemExit, match="Refused"):
            acquire.main([*not_integrated(tmp_path), *stage])
    with pytest.raises(SystemExit) as error:
        acquire.main(["acquire", "--download"])                  # licence arguments are required
    assert error.value.code == 2
    capsys.readouterr()


def test_note_e3_data_and_freeze_refuse(tmp_path):
    with pytest.raises(SystemExit, match="Refused: .*not integrated"):
        tool("note_e3_data").main(not_integrated(tmp_path))
    with pytest.raises(SystemExit, match="Refused: .*did not complete"):
        tool("freeze_e").main(["e1", "--run", str(tmp_path / "absent"), *not_integrated(tmp_path)])


@pytest.mark.parametrize("name, rehearsal", [("run_e1", "--rehearsal-workbook"), ("run_e3", "--rehearsal-input")])
def test_run_tools_arguments_and_refusals(tmp_path, name, rehearsal, capsys):
    module = tool(name)
    root = not_integrated(tmp_path)
    with pytest.raises(SystemExit, match="Refused: .*imported from"):
        module.main(["--registered", *root])
    for arguments in ([rehearsal, "x"], [rehearsal, "x", "--output-directory", "y", "--recomputation"],
                      [rehearsal, "x", "--output-directory", str(tmp_path / f"root/runs/{name[-2:]}-registered")],
                      ["--registered", rehearsal, "x"], []):
        with pytest.raises(SystemExit) as error:
            module.main([*arguments, *root])
        assert error.value.code == 2
    capsys.readouterr()
