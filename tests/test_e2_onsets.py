"""The X.1 onsets tool on a constructed ABMI-layout file in a temporary repository (no real observation)."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from e2_artificial import RELEASE, ons_csv
from uc_core import h1_official
from uc_e2 import constants, variables

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location("e2_onsets_tool", ROOT / "tools/e2_onsets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(root, *args):
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args], cwd=root,
                   check=True, capture_output=True)


def _repository(tmp_path, negative, tag=True):
    (tmp_path / "DATA_MANIFEST.csv").write_text("file,source_url,series_id,retrieved_utc,sha256,licence,notes\n")
    h1_official.record_acquisition(tmp_path, ons_csv(negative), RELEASE, [], retrieved_utc="2026-09-28T07:00:00Z",
                                   raw_name="ABMI_QNA.csv", retrieval_method="test")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "constructed")
    if tag:
        _git(tmp_path, "tag", "h1-frozen")
    return tmp_path


def test_onsets_tool_writes_the_section_7_record_once(tmp_path, capsys):
    root = _repository(tmp_path, negative=(77, 78, 79, 148, 149, 30, 31))
    assert _tool().main(["--root", str(root)]) == 0
    record = json.loads((root / constants.ONSETS_RECORD).read_text(encoding="utf-8"))
    _, labels, growth = h1_official.load_registered_growth(root)
    expected = json.loads(json.dumps(variables.onset_record(growth, labels)))
    assert {key: record[key] for key in expected} == expected
    assert record["power_onsets"] == [77, 148] and record["m_E2"] == 2
    assert [row["onset"] for row in record["episodes"]] == [30, 77, 148]
    assert variables.read_onsets_record(root / constants.ONSETS_RECORD) == (77, 148)
    assert "| 2 | 1990 Q3 | 77 |" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="never overwritten"):
        _tool().main(["--root", str(root)])


def test_onsets_tool_refuses_without_the_h1_frozen_tag(tmp_path):
    root = _repository(tmp_path, negative=(77, 78), tag=False)
    with pytest.raises(SystemExit, match="h1-frozen"):
        _tool().main(["--root", str(root)])
    assert not (root / constants.ONSETS_RECORD).exists()
