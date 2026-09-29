"""X.4 and X.5 on artificial data: outcome wording, rehearsals with byte-reproducible reports, and the
run's own hash verification that the freeze relies on. Development seed and shortened counts only."""
import csv
import json
import shutil

import pytest

from e_official_artificial import TERRITORY, artificial_levels, artificial_ons_csv, artificial_workbook
from uc_ext_official import gates, records, run, x4

ROW = dict(status="ok", value=0.02, p_value=0.3, m=4, k=3, error=None)
INTERVAL = dict(status="ok", interval=(-0.01, 0.05))


# ------------------------------------------------------------------------------- wording

def test_raw_p_above_level_fixes_the_inconclusive_branch_with_the_branch_b_diagnostic():
    result = x4.interpretation("e1", ROW, INTERVAL, D80=None)
    assert result["conclusion"] == "inconclusive" and result["text"] == x4.STATEMENTS["e1"]["inconclusive"]
    assert result["p_label"] == "raw, not family-adjusted" and result["adjusted_p"] is None
    assert result["branch_B"]["status"] == "unavailable" and "never below" in result["basis"]
    assert x4.interpretation("e1", ROW, INTERVAL, D80=0.2)["branch_B"]["condition"] is True
    assert x4.interpretation("e1", ROW, INTERVAL, D80=0.05)["branch_B"]["condition"] is False
    assert x4.interpretation("e1", ROW, INTERVAL, D80=0.04)["branch_B"]["condition"] is False
    assert x4.interpretation("e1", ROW, dict(status="no_eligible_episode", interval=None),
                             D80=0.2)["branch_B"]["status"] == "unavailable"


def test_raw_p_at_or_below_level_leaves_the_decision_to_family_closure():
    result = x4.interpretation("e3", dict(ROW, p_value=0.05), INTERVAL, D80=0.2)
    assert result["conclusion"] == "pending_family_closure" and result["text"] is None
    assert result["branch_B"]["status"] == "pending_family_closure"
    assert "No rejection is declared from the raw p" in result["basis"]
    assert result["statements"]["reject"].endswith("with a re-estimated time-varying AR(2).")


def test_unavailable_and_failed_comparisons_and_the_nonpositive_note():
    missing = x4.interpretation("e1", dict(ROW, status="observed_not_estimable", p_value=None, value=None), None, None)
    assert missing["conclusion"] == "not_estimable" and "Holm input 1" in missing["basis"]
    failed = x4.interpretation("e1", dict(ROW, status="invalid_surrogate_failure", p_value=None,
                                          error="FloatingPointError: x"), INTERVAL, None)
    assert failed["conclusion"] == "failed" and "FloatingPointError" in failed["text"]
    assert "nonpositive_note" in x4.interpretation("e1", dict(ROW, value=-0.1), INTERVAL, None)
    assert "nonpositive_note" not in x4.interpretation("e1", ROW, INTERVAL, None)
    for bad in (dict(ROW, value=float("nan")), dict(ROW, p_value=1.5)):
        with pytest.raises(ValueError):
            x4.interpretation("e1", bad, INTERVAL, None)
    with pytest.raises(ValueError):
        x4.interpretation("e1", ROW, INTERVAL, D80=float("inf"))


# ---------------------------------------------------------------------------- rehearsals

@pytest.fixture(scope="module")
def e1_rehearsal(tmp_path_factory):
    directory = tmp_path_factory.mktemp("e1")
    levels = artificial_levels()
    base = levels[1907]
    for step, year in enumerate(range(1908, 1915), start=1):      # growth positive 1908-1914 ...
        levels[year] = base * 1.01 ** step
    levels[1915] = levels[1914] * 0.95                             # ... and negative in 1915: an exogenous onset
    (directory / "workbook.xlsx").write_bytes(artificial_workbook(levels=levels))
    runs = [run.rehearse_e1(directory / "workbook.xlsx", directory / name, surrogates=4, resamples=40,
                            territory=TERRITORY) for name in ("first", "second")]
    return directory, runs


def test_e1_rehearsal_reports_every_registered_output(e1_rehearsal):
    directory, (manifest, again) = e1_rehearsal
    assert manifest["data_kind"] == x4.REHEARSAL_KIND and manifest["interpretation"]["extension"] == "E1"
    assert again["file_sha256"] == manifest["file_sha256"], "report, tables and figures must be byte-reproducible"
    report = directory / "first/report"
    comparisons = list(csv.DictReader((report / "comparisons.csv").open(encoding="utf-8")))
    assert [r["analysis"] for r in comparisons] == ["primary", "window25", "window35", "fixed", "wild", "trend", "lag1"]
    assert all(r["data_kind"] == x4.REHEARSAL_KIND and r["p_label"] == "raw, not family-adjusted" for r in comparisons)
    exogenous = list(csv.DictReader((report / "exogenous.csv").open(encoding="utf-8")))
    assert [(r["onset_year"], r["classification"]) for r in exogenous] == [("1915", "exogenous")]
    rolling = list(csv.DictReader((report / "rolling.csv").open(encoding="utf-8")))
    assert len(rolling) == 316 and rolling[0]["year"] == "1701" and rolling[29]["status"] == "ok"
    flags = list(csv.DictReader((report / "territory-flags.csv").open(encoding="utf-8")))
    assert flags and {"crosses_boundary", "territories"} <= set(flags[0])
    assert all(json.loads(r["territories"]) for r in flags)
    assert any(r["crosses_boundary"] == "True" for r in flags)          # flagged, never excluded
    log = json.loads((directory / "first/run-log.json").read_text(encoding="utf-8"))
    assert log["kind"] == "artificial pipeline rehearsal" and log["master_seed"] != 1927
    assert log["selection"]["column"] == "C"
    x4.verify_outputs(directory / "first")


def test_e3_rehearsal(tmp_path):
    (tmp_path / "abmi.csv").write_bytes(artificial_ons_csv())
    manifest = run.rehearse_e3(tmp_path / "abmi.csv", "30-06-2026", tmp_path / "run", surrogates=2, resamples=40)
    assert manifest["data_kind"] == x4.REHEARSAL_KIND
    report = tmp_path / "run/report"
    assert [r["analysis"] for r in csv.DictReader((report / "comparisons.csv").open(encoding="utf-8"))] == [
        "primary", "held_fixed", "fixed", "wild", "trend"]
    filtered = list(csv.DictReader((report / "filtered.csv").open(encoding="utf-8")))
    assert len(filtered) == 259 and filtered[39]["status"] == "indicator" and filtered[38]["status"] == "warm-up"
    assert len(list(csv.DictReader((report / "likelihood-grid.csv").open(encoding="utf-8")))) == 256
    log, _, done = x4.verify_outputs(tmp_path / "run")
    assert set(done["analysis_sha256"]) == {"analysis.json", "surrogate-fits.json.gz"}
    with pytest.raises(Exception, match="Release date"):
        run.rehearse_e3(tmp_path / "abmi.csv", "31-03-2026", tmp_path / "other", surrogates=2, resamples=40)


def test_rehearsal_stops_on_the_x2_rules(tmp_path):
    from uc_ext_official import e1_source
    (tmp_path / "workbook.xlsx").write_bytes(artificial_workbook(version_text="Version 3.0 (artificial)"))
    with pytest.raises(e1_source.SourceStop, match="version 3.1"):
        run.rehearse_e1(tmp_path / "workbook.xlsx", tmp_path / "run", surrogates=2, resamples=10)
    assert not (tmp_path / "run").exists()


# ------------------------------------------------------------- the run's own hash checks

def copy_run(e1_rehearsal, tmp_path):
    directory, _ = e1_rehearsal
    target = tmp_path / "run"
    shutil.copytree(directory / "first", target)
    return target


@pytest.mark.parametrize("damage, message", [
    (lambda run: (run / "report/comparisons.csv").write_text("altered"), "Report file changed"),
    (lambda run: (run / "analysis.json").write_text("{}"), "Run output changed"),
    (lambda run: (run / "run-log.json").write_text("{}"), "Run output changed"),
    (lambda run: (run / "report/manifest.json").write_text("{}"), "Run output changed"),
    (lambda run: (run / "report/extra.csv").write_text("x"), "differ from the manifest list"),
    (lambda run: (run / "report/rolling.csv").unlink(), "differ from the manifest list"),
    (lambda run: (run / "RUN_COMPLETE.json").unlink(), "did not complete"),
])
def test_verification_refuses_any_change_after_completion(e1_rehearsal, tmp_path, damage, message):
    target = copy_run(e1_rehearsal, tmp_path)
    damage(target)
    with pytest.raises(gates.GateClosed, match=message):
        x4.verify_outputs(target)


def test_freeze_refuses_anything_but_the_registered_primary_run(e1_rehearsal, tmp_path):
    target = copy_run(e1_rehearsal, tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(gates.GateClosed, match="Only the registered E1 primary run"):
        x4.freeze(root, target, "e1")
    log = json.loads((target / "run-log.json").read_text(encoding="utf-8"))
    log.update(kind=x4.PRIMARY_RUN)                     # a relabelled log still carries the artificial data kind
    (target / "run-log.json").write_bytes(records.canonical(log) + b"\n")
    done = json.loads((target / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
    done["run_log_sha256"] = gates.sha256_file(target / "run-log.json")
    (target / "RUN_COMPLETE.json").write_text(json.dumps(done))
    with pytest.raises(gates.GateClosed, match="Only the registered E1 primary run"):
        x4.freeze(root, target, "e1")
    with pytest.raises(gates.GateClosed, match="Only the registered E3 primary run"):
        x4.freeze(root, target, "e3")
    assert not (root / "audit").exists()


def test_tag_is_named_in_instructions_only():
    text = x4.tag_instructions("e1")
    assert "git tag -a e1-frozen" in text and "git push origin e1-frozen" in text
