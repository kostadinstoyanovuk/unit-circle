"""E4 X.5 on constructed tables: the freeze copies only the registered primary run, verifies every copy, writes
audit/E4_RESULT.json once and refuses a recomputation, a second freeze, an altered output and a missing file; the
statement of the result for each branch of prereg/E4.md section 11; E1's and E3's wording unchanged. The runs are
small-B runs on constructed data through the registered path with every gate replaced (see test_e4_run)."""
import json

import pytest

from test_e4_run import REGISTERED_ENDS, constructed_tables, registered_run, small_b_run
from uc_ext_official import gates, records, x4

ONE_EPISODE = ((1990, 2),) + REGISTERED_ENDS[1:]          # m_E4 = 1: a short run on constructed data
ROW = dict(status="ok", value=0.02, p_value=0.3, m=2, k=1, error=None)
INTERVAL = dict(status="ok", interval=(-0.01, 0.05))
DELTAS = dict(deltas=[dict(j=2, onset="1990Q3", delta_rt=-0.02), dict(j=3, onset="2008Q2", delta_rt=0.06)])


def frozen_files(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")
                  if p.is_file() and (p.relative_to(root).parts[0] in ("audit", "figures"))
                  and p.name != "H1_RESULT.json")


# ------------------------------------------------------------------------------------- freeze

def test_the_freeze_copies_the_registered_run_verifies_the_copies_and_writes_the_result(tmp_path, monkeypatch):
    root, output, manifest = registered_run(tmp_path, monkeypatch, tables=constructed_tables(ONE_EPISODE), D80=0.3)
    record = x4.freeze(root, output, "e4")
    assert record["record_type"] == "E4 registered primary result" and record["protocol"] == "prereg/E4.md"
    figures = {f"figures/e4_{name}.{suffix}" for name in ("realtime", "surrogates") for suffix in ("svg", "png", "pdf")}
    report_files = set(manifest["file_sha256"]) - {f.split("_", 1)[1] for f in figures}
    expected = {"audit/E4_RESULT.json", *figures,
                *{f"audit/e4/{name}" for name in ("run-log.json", "RUN_COMPLETE.json", "analysis.json",
                                                  "manifest.json", *report_files)}}
    assert set(frozen_files(root)) == expected
    for path, digest in record["frozen_files"].items():
        assert gates.sha256_file(root / path) == digest
    assert record["frozen_files"]["audit/e4/vintage-series.json"] == manifest["file_sha256"]["vintage-series.json"]
    interpretation = record["interpretation"]
    assert interpretation == manifest["interpretation"] and interpretation["recorded_as"] == interpretation["conclusion"]
    assert record["primary"]["eligible_episodes"] == 1 and record["primary"]["p_label"] == "raw, not family-adjusted"
    assert record["family"]["holm_input"] == record["primary"]["raw_p"] == interpretation["holm_input"]
    assert record["family"]["adjusted_p"] is None
    for key in ("selections", "real_time_against_final", "two_clocks", "availability_summary"):
        assert key in record
    assert json.loads((root / "audit/E4_RESULT.json").read_text(encoding="utf-8"))["interpretation"]["D80"] == 0.3
    assert "git tag -a e4-frozen" in x4.tag_instructions("e4")


def test_a_second_freeze_is_refused_whatever_part_of_the_first_exists(tmp_path, monkeypatch):
    root, output, _ = registered_run(tmp_path, monkeypatch, tables=constructed_tables(ONE_EPISODE))
    x4.freeze(root, output, "e4")
    before = {path: (root / path).read_bytes() for path in frozen_files(root)}
    with pytest.raises(records.RecordExists, match="frozen once"):
        x4.freeze(root, output, "e4")
    (root / "audit/E4_RESULT.json").unlink()
    with pytest.raises(records.RecordExists, match="frozen once"):
        x4.freeze(root, output, "e4")
    for path in [p for p in before if p.startswith("audit/e4/")]:
        (root / path).unlink()
    (root / "audit/e4").rmdir()
    with pytest.raises(records.RecordExists, match="figures/e4_realtime"):
        x4.freeze(root, output, "e4")
    assert not (root / "audit/e4").exists() and not (root / "audit/E4_RESULT.json").exists()


def test_the_freeze_refuses_a_recomputation_and_a_small_b_run(tmp_path, monkeypatch):
    small_b_run(constructed_tables(ONE_EPISODE), tmp_path / "small")      # before the registered path is replaced
    root, output, _ = registered_run(tmp_path, monkeypatch, tables=constructed_tables(ONE_EPISODE),
                                     recomputation=True, output="runs/e4-recomputation")
    with pytest.raises(gates.GateClosed, match="Only the registered E4 primary run"):
        x4.freeze(root, output, "e4")
    with pytest.raises(gates.GateClosed, match="Only the registered E4 primary run"):
        x4.freeze(root, tmp_path / "small", "e4")
    with pytest.raises(gates.GateClosed, match="Only the registered E1 primary run"):
        x4.freeze(root, tmp_path / "small", "e1")
    assert frozen_files(root) == []


@pytest.mark.parametrize("damage, message", [
    (lambda run: (run / "report/report.txt").write_text("altered\n"), "Report file changed"),
    (lambda run: (run / "report/realtime.svg").write_text("<svg/>\n"), "Report file changed"),
    (lambda run: (run / "analysis.json").write_text("{}\n"), "Run output changed"),
    (lambda run: (run / "report/null-models.json").unlink(), "differ from the manifest list"),
    (lambda run: (run / "RUN_COMPLETE.json").unlink(), "did not complete"),
])
def test_the_freeze_refuses_an_altered_or_missing_output(tmp_path, monkeypatch, damage, message):
    root, output, _ = registered_run(tmp_path, monkeypatch, tables=constructed_tables(ONE_EPISODE))
    damage(output)
    with pytest.raises(gates.GateClosed, match=message):
        x4.freeze(root, output, "e4")
    assert frozen_files(root) == []


def test_the_freeze_tool_accepts_e4_and_refuses_a_second_freeze(tmp_path, monkeypatch, capsys):
    import importlib.util
    from test_e4_run import RESEARCH
    spec = importlib.util.spec_from_file_location("freeze_e_tool", RESEARCH / "tools/freeze_e.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    root, output, _ = registered_run(tmp_path, monkeypatch, tables=constructed_tables(ONE_EPISODE))
    assert tool.main(["e4", "--root", str(root)]) == 0
    assert "git tag -a e4-frozen" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="Refused"):
        tool.main(["e4", "--root", str(root)])


# ------------------------------------------------------------------------------ the statements

def test_raw_p_above_005_is_inconclusive_with_the_reference_the_limit_and_branch_b():
    result = x4.interpretation("e4", ROW, INTERVAL, D80=None, details=DELTAS)
    assert result["conclusion"] == "inconclusive" and result["text"] == x4.STATEMENTS["e4"]["inconclusive"]
    assert result["p_label"] == "raw, not family-adjusted" and result["adjusted_p"] is None
    assert x4.E4_REFERENCE in result["text"] and "revision sensitivity" in result["text"]
    assert "not warning available before the onset quarter began" in result["text"]
    assert result["reference"] == ("fixed-date AR(2) surrogates fitted to each episode's first vintage containing "
                                   "the quarter before onset")
    assert "revision sensitivity" in result["limit"] and "onset dates come from final data" in result["limit"]
    assert result["deltas"] == DELTAS["deltas"] and result["k_over_m"] == "1/2"
    assert result["holm_input"] == 0.3 and result["recorded_as"] == "inconclusive"
    assert result["branch_B"]["status"] == "unavailable"                         # D80 null
    assert x4.interpretation("e4", ROW, INTERVAL, D80=0.2, details=DELTAS)["branch_B"]["condition"] is True
    assert x4.interpretation("e4", ROW, INTERVAL, D80=0.05, details=DELTAS)["branch_B"]["condition"] is False
    single = dict(status="single_episode", interval=(0.06, 0.06))
    assert x4.interpretation("e4", ROW, single, D80=0.2)["branch_B"]["condition"] is True
    assert x4.interpretation("e4", ROW, dict(status="observed_statistic_failed", interval=None),
                             D80=0.2)["branch_B"]["status"] == "unavailable"


def test_raw_p_at_or_below_005_is_pending_the_family_adjustment():
    for p in (0.05, 0.001):
        result = x4.interpretation("e4", dict(ROW, p_value=p), INTERVAL, D80=0.2, details=DELTAS)
        assert result["conclusion"] == "pending_family_closure" and result["text"] is None
        assert "No rejection is declared from the raw p" in result["basis"] and result["holm_input"] == p
        assert result["statements"]["reject"].startswith("The observed mean real-time pre-onset change was "
                                                         "unusually large relative to fixed-date AR(2) surrogates")
        assert "not warning available before the onset quarter began" in result["statements"]["reject"]


def test_a_failure_and_m_E4_zero_are_recorded_as_failed_with_holm_input_one():
    failed = x4.interpretation("e4", dict(ROW, status="invalid_surrogate_failure", p_value=None,
                                          error="FloatingPointError: x"), INTERVAL, D80=0.2, details=DELTAS)
    assert failed["conclusion"] == "failed" and failed["recorded_as"] == "failed" and failed["holm_input"] == 1.0
    assert "FloatingPointError" in failed["text"]
    observed = x4.interpretation("e4", dict(ROW, status="observed_statistic_failed", p_value=None, value=None,
                                            error="episode 3: LinAlgError"), None, D80=None)
    assert observed["conclusion"] == "failed" and observed["holm_input"] == 1.0 and observed["deltas"] == []
    empty = x4.interpretation("e4", dict(ROW, status="observed_not_estimable", p_value=None, value=None, m=0,
                                         k=None), dict(status="no_eligible_episode", interval=None), D80=0.2)
    assert empty["conclusion"] == "not_estimable" and empty["recorded_as"] == "failed"
    assert empty["holm_input"] == 1.0 and "m_E4 = 0" in empty["text"] and "Holm input 1" in empty["basis"]
    assert empty["k_over_m"] is None and empty["raw_p"] is None


def test_e1_and_e3_wording_is_unchanged():
    assert x4.STATEMENTS["e1"] == dict(
        reject=("The observed mean pre-onset change in annual data was unusually large relative to the registered "
                "fitted constant-AR(2) surrogate procedure."),
        inconclusive="The E1 comparison did not detect an unusually large pre-onset change under the registered "
                     "surrogate model.")
    assert x4.STATEMENTS["e3"] == dict(
        reject=("The observed mean pre-onset change was unusually large relative to the registered fitted "
                "constant-AR(2) surrogate procedure with a re-estimated time-varying AR(2)."),
        inconclusive="The primary comparison did not detect an unusually large pre-onset change under the "
                     "registered surrogate model.")
    for extension in ("e1", "e3"):
        result = x4.interpretation(extension, ROW, INTERVAL, D80=0.2)
        assert not {"reference", "limit", "deltas", "holm_input", "recorded_as"} & set(result)
        assert result == x4.interpretation(extension, ROW, INTERVAL, D80=0.2, details=DELTAS)
    assert x4.FIGURES == ("persistence", "surrogates")
    assert x4.REGISTERED_OUTPUT["e1"] == "runs/e1-registered" and x4.REGISTERED_OUTPUT["e3"] == "runs/e3-registered"
