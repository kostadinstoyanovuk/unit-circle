"""E4 X.4 on constructed tables: the retained record is complete, byte-reproducible and verified against its own
hashes; every gate of the registered run fails closed and leaves nothing behind; m_E4 = 0 to 4 with the registered
onsets; a failed observed statistic. Every computation here is a small-B run on constructed data (development
seed and streams, B = 20 attempts, 100 episode resamples); no registered generator is ever built."""
import json
import math
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from e4_artificial import growth_series
from uc_e4 import analysis
from uc_e4.streams import DEVELOPMENT_SEED, DEVELOPMENT_STREAMS, REGISTERED_STREAMS
from uc_e4.table import RawPart, build_tables, quarter_from_index, quarter_index
from uc_e4.vintage import load_h1_episodes
from uc_ext_official import e4_run, e4_source, gates, records, report_e4, x4

RESEARCH = Path(__file__).resolve().parents[1]
H1 = RESEARCH / "audit/H1_RESULT.json"
SMALL_B, SMALL_INTERVAL_B = 20, 100
REGISTERED_ENDS = ((1972, 4), (1979, 3), (1990, 1), (2007, 4), (2019, 4), (2019, 4))
LABELS = ("Jan 2016", "Feb 2016", "Mar 2016", "Apr 2016", "May 2016", "Jun 2016")
EXPECTED_REPORT = {"availability-counts.csv", "availability-markers.csv", "availability.csv", "comparisons.csv",
                   "episode-interval.csv", "episodes.csv", "manifest.json", "null-models.json",
                   "primary-surrogates.csv", "real-time-against-final.csv", "real-time-summary.csv", "report.json",
                   "report.txt", "rolling.csv", "selections.csv", "two-clocks.csv", "vintage-series.json",
                   *{f"{figure}.{suffix}" for figure in ("realtime", "surrogates") for suffix in ("svg", "png", "pdf")}}


def constructed_tables(ends=REGISTERED_ENDS, *, flat=None):
    """Six constructed vintages from one synthetic AR(2) growth series (arbitrary numbers); vintage k has levels
    from 1955Q1 to ends[k]. With the registered ends the first vintage holding q_j - 1 is 1, 2, 3, 4 for the four
    onsets. `flat = (k, first, last)` holds the level of vintage k fixed, so that its growth is exactly zero at
    positions first..last."""
    g = growth_series(259, replicate=77)
    rows = [quarter_from_index(quarter_index((1955, 1)) + i) for i in range(260)]
    cells = [[None] * 6 for _ in rows]
    for k in range(6):
        growth = g.copy()
        if flat is not None and flat[0] == k:
            growth[flat[1]:flat[2] + 1] = 0.0
        logs = np.concatenate([[0.0], np.cumsum(growth) / 400.0])
        for i, q in enumerate(rows):
            if quarter_index(q) <= quarter_index(ends[k]):
                cells[i][k] = 100.0 * math.exp(logs[i] + (0.0 if flat else 0.0005 * k * math.sin(0.9 * i)))
    return build_tables([RawPart("T", LABELS, tuple(f"{y} Q{q}" for y, q in rows),
                                 tuple(tuple(row) for row in cells))])


def small_b_run(tables, output):
    return e4_run.small_b_run_e4(tables, load_h1_episodes(H1), output, B=SMALL_B, interval_B=SMALL_INTERVAL_B,
                                 h1_sha256=gates.sha256_file(H1))


def files_of(run: Path) -> dict:
    return {path.relative_to(run).as_posix(): path.read_bytes() for path in sorted(run.rglob("*")) if path.is_file()}


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """The same constructed inputs run twice (m_E4 = 4)."""
    directory = tmp_path_factory.mktemp("e4runs")
    tables = constructed_tables()
    small_b_run(tables, directory / "first")
    small_b_run(constructed_tables(), directory / "second")
    return directory, tables


# ------------------------------------------------------------------------- the retained record

def test_small_b_run_on_constructed_data_writes_the_complete_retained_record(runs):
    directory, _ = runs
    run = directory / "first"
    assert {p.name for p in run.iterdir()} == {"run-log.json", "analysis.json", "report", "RUN_COMPLETE.json"}
    assert {p.name for p in (run / "report").iterdir()} == EXPECTED_REPORT
    log, manifest, done = x4.verify_outputs(run)
    assert log["kind"] == e4_run.SMALL_B_RUN and manifest["data_kind"] == report_e4.CONSTRUCTED_KIND
    assert log["master_seed"] == DEVELOPMENT_SEED and log["B"] == SMALL_B and log["interval_B"] == SMALL_INTERVAL_B
    report = records.read_json(run / "report/report.json")
    assert report["data_kind"] == report_e4.CONSTRUCTED_KIND
    result = report["result"]
    assert result["m_E4"] == 4 and result["status"] == "ok" and len(result["comparisons"]) == 6
    assert [row["analysis"] for row in result["comparisons"]][0].startswith("primary")
    assert [s["vintage"] for s in result["selections"] if s["window"] == 40] == list(LABELS[1:5])
    nulls = records.read_json(run / "report/null-models.json")["null_models"]
    assert [n["j"] for n in nulls] == [0, 1, 2, 3] and all(len(n["residuals"]) == n["n_v"] - 2 for n in nulls)
    analysis_json = records.read_json(run / "analysis.json")
    assert set(analysis_json["comparisons"]) == {"primary", "window32", "window48", "wild"}
    attempts = analysis_json["comparisons"]["primary"]["primary"]["attempts"]
    assert len(attempts) == SMALL_B and all(len(a["changes"]) == 4 for a in attempts)
    surrogates = (run / "report/primary-surrogates.csv").read_text(encoding="utf-8").splitlines()
    assert surrogates[0].split(",")[:4] == ["data_kind", "number", "status", "statistic"] and len(surrogates) == 21
    for path in run.rglob("*"):
        # the records and tables are written with LF on every platform; the figure files are written by
        # matplotlib, whose SVG writer uses the line ends of the platform, so they are not tested here
        if path.is_file() and path.suffix in (".json", ".csv"):
            assert b"\r\n" not in path.read_bytes() and path.read_bytes().endswith(b"\n"), path


def test_no_level_is_written_and_each_series_is_tied_to_its_levels_by_hash(runs):
    directory, tables = runs
    run = directory / "first"
    series = records.read_json(run / "report/vintage-series.json")["series"]
    lv, av = tables.levels, tables.availability
    for record in series:
        assert "levels" not in record and len(record["growth"]) == record["n_v"]
        first, last = quarter_index(tuple(int(x) for x in record["first_quarter"].split("Q"))), quarter_index(
            tuple(int(x) for x in record["last_quarter"].split("Q")))
        levels = np.array([lv.level(record["vintage_number"], av.row(quarter_from_index(i)))
                           for i in range(first, last + 1)], dtype="<f8")
        assert record["levels_sha256"] == gates.sha256_bytes(levels.tobytes())
    sample = [repr(float(x)) for x in lv.levels[::17, 4] if np.isfinite(x)]
    text = b"".join(content for name, content in files_of(run).items() if not name.endswith((".png", ".pdf")))
    assert sample and not any(value.encode() in text for value in sample)


def test_the_same_inputs_give_the_same_bytes_except_the_times_of_the_run_log(runs):
    directory, _ = runs
    first, second = files_of(directory / "first"), files_of(directory / "second")
    assert set(first) == set(second)
    differing = {name for name in first if first[name] != second[name]}
    assert differing <= {"run-log.json", "RUN_COMPLETE.json"}
    one, two = (records.read_json(directory / name / "RUN_COMPLETE.json") for name in ("first", "second"))
    assert one["analysis_sha256"] == two["analysis_sha256"]
    assert one["report_manifest_sha256"] == two["report_manifest_sha256"]
    for name in first:
        if name.endswith(".json") and name != "run-log.json":
            assert b"started_utc" not in first[name] and b"finished_utc" not in first[name], name


def copy_run(runs, tmp_path):
    directory, _ = runs
    target = tmp_path / "copy"
    shutil.copytree(directory / "first", target)
    return target


@pytest.mark.parametrize("damage, message", [
    (lambda run: (run / "report/comparisons.csv").write_text("altered\n"), "Report file changed"),
    (lambda run: (run / "report/null-models.json").write_text("{}\n"), "Report file changed"),
    (lambda run: (run / "analysis.json").write_text("{}\n"), "Run output changed"),
    (lambda run: (run / "run-log.json").write_text("{}\n"), "Run output changed"),
    (lambda run: (run / "report/manifest.json").write_text("{}\n"), "Run output changed"),
    (lambda run: (run / "report/extra.csv").write_text("x\n"), "differ from the manifest list"),
    (lambda run: (run / "report/vintage-series.json").unlink(), "differ from the manifest list"),
    (lambda run: (run / "RUN_COMPLETE.json").unlink(), "did not complete"),
])
def test_the_manifest_detects_any_alteration_after_completion(runs, tmp_path, damage, message):
    target = copy_run(runs, tmp_path)
    x4.verify_outputs(target)
    damage(target)
    with pytest.raises(gates.GateClosed, match=message):
        x4.verify_outputs(target)


# ------------------------------------------------------------ eligibility and the observed statistic

@pytest.mark.parametrize("first_end, m", [((1973, 2), 3), ((1979, 4), 2), ((1990, 2), 1), ((2019, 4), 0)])
def test_m_E4_from_zero_to_three_with_the_registered_onsets(tmp_path, first_end, m):
    """Vintage 0 already holds q_j - 1 for the earliest onsets, so their first release is unverifiable (7.2)."""
    tables = constructed_tables(((first_end,) + REGISTERED_ENDS[1:]) if m else ((2019, 4),) * 6)
    manifest = small_b_run(tables, tmp_path / "run")
    result = records.read_json(tmp_path / "run/report/report.json")["result"]
    episodes = result["episodes"]
    assert result["m_E4"] == m and [e["onset"] for e in episodes] == ["1973Q3", "1980Q1", "1990Q3", "2008Q2"]
    assert [e["failed_step"] for e in episodes] == ["7.2"] * (4 - m) + [None] * m
    assert all(e["delta_rt"] is None for e in episodes[:4 - m]) and all(e["delta_rt"] is not None
                                                                        for e in episodes[4 - m:])
    interpretation = manifest["interpretation"]
    if m == 0:
        assert result["status"] == "not_estimable" and interpretation["conclusion"] == "not_estimable"
        assert interpretation["recorded_as"] == "failed" and interpretation["holm_input"] == 1.0
        assert "m_E4 = 0" in interpretation["text"] and result["primary"]["holm_input"] == 1.0
        assert result["episode_interval"]["status"] == "no_eligible_episode"
        assert records.read_json(tmp_path / "run/report/null-models.json")["null_models"] == []
    else:
        assert result["status"] == "ok" and interpretation["k_over_m"] == f"{result['primary']['k']}/{m}"
        assert [d["j"] for d in interpretation["deltas"]] == list(range(4 - m, 4))
        assert result["episode_interval"]["status"] == ("single_episode" if m == 1 else "ok")
    for figure in ("realtime", "surrogates"):
        assert all((tmp_path / f"run/report/{figure}.{suffix}").stat().st_size > 0 for suffix in ("svg", "png", "pdf"))
    x4.verify_outputs(tmp_path / "run")


def test_a_failed_observed_statistic_fails_the_run_and_is_recorded_with_holm_input_one(tmp_path):
    """Vintage 4 (the 2008Q2 episode) has exactly zero growth over 42 quarters: a rolling AR(2) window is not
    identifiable, so the observed statistic fails; the episode stays E4-eligible (section 7, step 4)."""
    tables = constructed_tables(flat=(4, 100, 141))
    manifest = small_b_run(tables, tmp_path / "run")
    result = records.read_json(tmp_path / "run/report/report.json")["result"]
    assert result["m_E4"] == 4 and result["status"] == "failed"
    primary = result["comparisons"][0]
    assert primary["status"] == "observed_statistic_failed" and primary["p_value"] is None
    assert result["episode_interval"]["status"] == "observed_statistic_failed"
    assert [e["statistic"] for e in result["episodes"]] == ["ok", "ok", "ok", "failed"]
    interpretation = manifest["interpretation"]
    assert interpretation["conclusion"] == "failed" and interpretation["recorded_as"] == "failed"
    assert interpretation["holm_input"] == 1.0 and result["primary"]["holm_input"] == 1.0
    assert any(f["j"] == 3 for f in result["rolling_failures"])
    x4.verify_outputs(tmp_path / "run")


# ------------------------------------------------------------------------- the registered path

def registered_root(tmp_path):
    root = tmp_path / "root"
    (root / "audit").mkdir(parents=True)
    shutil.copyfile(H1, root / "audit/H1_RESULT.json")
    return root


def open_gates(monkeypatch, root, tables, *, D80=0.3, refuse=None, calls=None):
    """Replace each gate by a stand-in that passes, except the one named in `refuse`, which closes."""
    calls = calls if calls is not None else []

    def gate(name, value):
        def check(*args, **kwargs):
            calls.append(name)
            if name == refuse:
                raise gates.GateClosed(f"closed: {name}")
            return value
        return check

    x3 = dict(record_path="audit/E4_X3.json", record_sha256="0" * 64, D80=D80, code_sha256="a" * 64)
    identity = dict(identity=dict(commit="c" * 40), code_sha256="a" * 64, imported={}, e1_code_sha256="b" * 64)
    hashes = e4_run.table_hashes(tables)
    summary = dict(kinds_sha256=hashes["kinds_sha256"], levels_sha256=hashes["levels_sha256"])

    def output_location(root_, path):
        calls.append("output")
        if refuse == "output":
            raise SystemExit("closed: output")

    monkeypatch.setattr(gates, "check_code_location", gate("location", {"uc_e4": "src/uc_e4"}))
    monkeypatch.setattr(gates, "check_registration", gate("registration", dict(doi="10.17605/OSF.IO/DPXQF")))
    monkeypatch.setattr(gates, "check_x3", gate("x3", x3))
    monkeypatch.setattr(gates, "check_code_frozen", gate("frozen", identity))
    monkeypatch.setattr(gates, "load_runner", lambda root_, extension: SimpleNamespace(
        verify_output_location=output_location))
    monkeypatch.setattr(e4_source, "read_level_tables", gate("data", dict(tables=tables, summary=summary)))
    monkeypatch.setattr(gates, "check_committed", gate("h1_record", None))
    return calls


def small_b_analysis(monkeypatch, seen):
    """analyze stand-in: checks that the registered run asks for exactly the registered computation, then
    computes a small-B run on constructed data with the development seed and streams."""
    original = analysis.analyze

    def analyze(tables, episodes, **kwargs):
        seen.append(kwargs)
        assert kwargs["master_seed"] == 1927 and kwargs["allow_registered"] is True
        assert kwargs["streams"] == REGISTERED_STREAMS and kwargs["B"] == 1000 and kwargs["interval_B"] == 10000
        return original(tables, episodes, master_seed=DEVELOPMENT_SEED, streams=DEVELOPMENT_STREAMS, B=SMALL_B,
                        interval_B=SMALL_INTERVAL_B, release_dates=kwargs["release_dates"])
    monkeypatch.setattr(analysis, "analyze", analyze)


GATES = ("location", "registration", "x3", "frozen", "output", "data", "h1_record")


@pytest.mark.parametrize("refuse", GATES)
def test_each_gate_of_the_registered_run_fails_closed_and_writes_nothing(tmp_path, monkeypatch, refuse):
    root = registered_root(tmp_path)
    before = files_of(root)
    seen = []
    small_b_analysis(monkeypatch, seen)
    calls = open_gates(monkeypatch, root, constructed_tables(), refuse=refuse)
    with pytest.raises(gates.GateClosed, match=f"closed: {refuse}"):
        e4_run.run_e4(root, root / x4.REGISTERED_OUTPUT["e4"])
    assert calls == list(GATES[:GATES.index(refuse) + 1]) and seen == []
    assert not (root / "runs").exists() and files_of(root) == before


def test_the_real_location_gate_refuses_a_root_whose_code_is_not_imported(tmp_path):
    root = registered_root(tmp_path)
    with pytest.raises(gates.GateClosed, match="not from"):
        e4_run.run_e4(root, root / x4.REGISTERED_OUTPUT["e4"])
    assert not (root / "runs").exists()


def test_the_registered_run_writes_only_its_path_and_refuses_an_existing_directory(tmp_path, monkeypatch):
    root = registered_root(tmp_path)
    small_b_analysis(monkeypatch, [])
    open_gates(monkeypatch, root, constructed_tables())
    with pytest.raises(gates.GateClosed, match="writes only to runs/e4-registered"):
        e4_run.run_e4(root, root / "runs/elsewhere")
    with pytest.raises(gates.GateClosed, match="needs its own output directory"):
        e4_run.run_e4(root, root / x4.REGISTERED_OUTPUT["e4"], recomputation=True)
    (root / x4.REGISTERED_OUTPUT["e4"]).mkdir(parents=True)
    with pytest.raises(gates.GateClosed, match="runs once into a new directory"):
        e4_run.run_e4(root, root / x4.REGISTERED_OUTPUT["e4"])
    assert list((root / x4.REGISTERED_OUTPUT["e4"]).iterdir()) == []


def registered_run(tmp_path, monkeypatch, *, tables=None, D80=0.3, recomputation=False, output=None,
                   release_dates=None):
    """A completed run through the registered path with every gate replaced and a small-B computation."""
    root = registered_root(tmp_path) if not (tmp_path / "root").exists() else tmp_path / "root"
    seen = []
    small_b_analysis(monkeypatch, seen)
    open_gates(monkeypatch, root, tables if tables is not None else constructed_tables(), D80=D80)
    output = root / (output or x4.REGISTERED_OUTPUT["e4"])
    manifest = e4_run.run_e4(root, output, recomputation=recomputation, release_dates=release_dates)
    assert len(seen) == 1
    return root, output, manifest


def test_after_every_gate_the_run_asks_for_the_registered_computation_and_records_it(tmp_path, monkeypatch):
    root, output, manifest = registered_run(tmp_path, monkeypatch, release_dates={"Mar 2016": "2016-03-30"})
    log, checked, done = x4.verify_outputs(output)
    assert log["kind"] == x4.PRIMARY_RUN and log["extension"] == "E4" and log["master_seed"] == 1927
    assert log["B"] == 1000 and log["interval_B"] == 10000 and log["streams"]["primary"] == 5400
    assert log["h1_record_sha256"] == gates.sha256_file(H1) and log["D80"] == 0.3
    assert checked["data_kind"] == x4.REGISTERED_KIND["e4"] == manifest["data_kind"]
    assert "started_utc" not in checked["metadata"] and log["started_utc"] <= log["finished_utc"]
    clocks = records.read_json(output / "report/report.json")["result"]["two_clocks"]["rows"]
    assert [row["release_basis"] for row in clocks][1] == "ONS metadata"
    assert manifest["interpretation"]["D80"] == 0.3


def test_a_run_that_does_not_finish_leaves_no_completion_record(tmp_path, monkeypatch):
    root = registered_root(tmp_path)
    open_gates(monkeypatch, root, constructed_tables())

    def broken(*args, **kwargs):
        raise MemoryError("stopped")
    monkeypatch.setattr(analysis, "analyze", broken)
    with pytest.raises(MemoryError):
        e4_run.run_e4(root, root / x4.REGISTERED_OUTPUT["e4"])
    run = root / x4.REGISTERED_OUTPUT["e4"]
    assert [p.name for p in run.iterdir()] == ["run-log.json"]
    with pytest.raises(gates.GateClosed, match="did not complete"):
        x4.verify_outputs(run)


def test_release_dates_are_dates_and_an_empty_mapping_means_label_months(tmp_path):
    assert e4_run.release_dates_from(None) == {}
    assert e4_run.release_dates_from({"Jan 2016": "2016-01-28"})["Jan 2016"].isoformat() == "2016-01-28"
    with pytest.raises(ValueError):
        e4_run.release_dates_from({"Jan 2016": "28 January 2016"})
    record, digest = e4_run.input_record(constructed_tables(), "0" * 64, {})
    assert record["release_dates"] == {} and len(digest) == 64
    assert json.dumps(record).find("levels_sha256") > 0


def test_the_command_refuses_without_the_gates_and_needs_a_directory_for_a_recomputation(tmp_path, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_e4_tool", RESEARCH / "tools/run_e4.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    root = registered_root(tmp_path)
    with pytest.raises(SystemExit, match="Refused: .*not from"):
        tool.main(["--registered", "--root", str(root)])
    with pytest.raises(SystemExit):
        tool.main(["--registered", "--root", str(root), "--recomputation"])
    assert "own --output-directory" in capsys.readouterr().err
    (tmp_path / "dates.json").write_text("[]\n")
    with pytest.raises(SystemExit):
        tool.main(["--registered", "--root", str(root), "--release-dates", str(tmp_path / "dates.json")])
    assert "JSON object" in capsys.readouterr().err
    assert not (root / "runs").exists()
