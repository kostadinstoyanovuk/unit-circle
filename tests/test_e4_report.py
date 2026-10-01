"""The E4 report on constructed tables: the tables of sections 8 to 10 agree with each other and with the analysis,
the report refuses an analysis that disagrees with the rolling paths or the fitted nulls, the text states the
result with its label and limit, and both figures are byte-reproducible, also with no eligible episode. Every
computation is a small-B run on constructed data (development seed and streams, B = 20, 100 resamples)."""
import csv
import io
import math

import numpy as np
import pytest

from test_e4_run import H1, REGISTERED_ENDS, SMALL_B, SMALL_INTERVAL_B, constructed_tables
from uc_core.validation_runner import serial
from uc_e4 import analysis
from uc_e4.streams import DEVELOPMENT_SEED, DEVELOPMENT_STREAMS
from uc_e4.vintage import load_h1_episodes
from uc_ext_official import gates, records, report_e4, x4

TWO_EPISODES = ((1979, 4),) + REGISTERED_ENDS[1:]        # j = 0, 1 unavailable at step 7.2; j = 2, 3 eligible
FIGURES = [f"{name}.{suffix}" for name in ("realtime", "surrogates") for suffix in ("svg", "png", "pdf")]


def analysed(tables):
    return analysis.analyze(tables, load_h1_episodes(H1), master_seed=DEVELOPMENT_SEED, streams=DEVELOPMENT_STREAMS,
                            B=SMALL_B, interval_B=SMALL_INTERVAL_B)


def write(directory, tables, result, *, D80=None):
    return report_e4.write_report(directory, tables=tables, result=result, input_record=dict(note="constructed"),
                                  input_sha256="0" * 64, D80=D80, data_kind=report_e4.CONSTRUCTED_KIND,
                                  metadata=dict(B=SMALL_B))


def table(path):
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def number(text):
    return None if text == "" else float(text)


@pytest.fixture(scope="module")
def two(tmp_path_factory):
    directory = tmp_path_factory.mktemp("e4report")
    tables = constructed_tables(TWO_EPISODES)
    result = analysed(tables)
    write(directory / "first", tables, result, D80=0.3)
    write(directory / "second", tables, result, D80=0.3)
    return directory, tables, result


def test_the_episode_table_has_every_h1_episode_with_its_selection_and_signed_changes(two):
    directory, _, result = two
    rows = table(directory / "first/episodes.csv")
    assert [r["onset"] for r in rows] == ["1973Q3", "1980Q1", "1990Q3", "2008Q2"]
    assert [r["failed_step"] for r in rows] == ["7.2", "7.2", "", ""]
    assert all(r["data_kind"] == report_e4.CONSTRUCTED_KIND for r in rows)
    assert [r["vintage"] for r in rows] == ["Jan 2016", "Jan 2016", "Apr 2016", "May 2016"]
    for row in rows[2:]:
        rt, final, difference = number(row["delta_rt"]), number(row["delta_final"]), number(row["difference"])
        assert difference == rt - final and row["delta_rt_sign"] == ("positive" if rt > 0 else "negative")
        assert int(row["n_v"]) >= 48 and row["statistic"] == "ok"
    assert all(r["delta_rt"] == "" and r["statistic"] == "unavailable" for r in rows[:2])
    deltas = [number(r["delta_rt"]) for r in rows[2:]]
    assert result["S_rt"] == float(np.mean(deltas)) and result["k"] == sum(d > 0 for d in deltas)


def test_the_primary_and_secondary_table_and_the_primary_block_agree(two):
    directory, _, result = two
    report = records.read_json(directory / "first/report.json")["result"]
    rows = table(directory / "first/comparisons.csv")
    assert [r["analysis"] for r in rows] == ["primary (W = 40, fixed dates per vintage)", "W = 32", "W = 48",
                                            "wild signs (W = 40)", "Kendall trend (W = 40)",
                                            "lag-one comparator (W = 40)"]
    assert all(r["p_label"] == "raw, not family-adjusted" for r in rows)
    primary = report["primary"]
    head = report["comparisons"][0]
    assert primary["S_rt"] == head["value"] == result["S_rt"] and primary["m_E4"] == head["m"] == 2
    assert primary["raw_p"] == head["p_value"] == (1 + head["exceedances"]) / (head["B_prime"] + 1)
    assert head["B_prime"] == head["retained"] == SMALL_B and primary["q"] == head["exceedances"] / SMALL_B
    assert primary["k_over_m"] == f"{result['k']}/2" and primary["holm_input"] == primary["raw_p"]
    surrogates = table(directory / "first/primary-surrogates.csv")
    statistics = [number(r["statistic"]) for r in surrogates]
    assert len(surrogates) == SMALL_B and sum(s >= primary["S_rt"] for s in statistics) == head["exceedances"]
    for r in surrogates:
        assert math.isclose(number(r["statistic"]), (number(r["delta_j2"]) + number(r["delta_j3"])) / 2,
                            rel_tol=0, abs_tol=1e-15)
        assert r["delta_j0"] == "" and r["delta_j1"] == ""


def test_the_interval_and_the_descriptive_tables(two):
    directory, _, result = two
    interval = table(directory / "first/episode-interval.csv")[0]
    assert interval["status"] == "ok" and number(interval["lower"]) <= number(interval["upper"])
    assert int(interval["requested"]) == SMALL_INTERVAL_B and int(interval["episodes"]) == 2
    summary = table(directory / "first/real-time-summary.csv")[0]
    finals = [r["delta_final"] for r in result["real_time_against_final"]["rows"][2:]]
    assert number(summary["S_final_m"]) == float(np.mean(finals))
    assert number(summary["mean_difference"]) == number(summary["S_rt"]) - number(summary["S_final_m"])
    clocks = table(directory / "first/two-clocks.csv")
    assert [r["reference_quarter"] for r in clocks] == ["1973Q2", "1979Q4", "1990Q2", "2008Q1"]
    assert all(r["release_basis"] == "label month only" for r in clocks)
    assert clocks[2]["previous_vintage"] == "Mar 2016" and clocks[2]["months_since_previous"] == "1"
    selections = table(directory / "first/selections.csv")
    assert sorted({r["window"] for r in selections}) == ["32", "40", "48"] and len(selections) == 12
    counts = table(directory / "first/availability-counts.csv")
    assert [r["vintage"] for r in counts] == ["Jan 2016", "Feb 2016", "Mar 2016", "Apr 2016", "May 2016",
                                              "Jun 2016"]


def test_the_text_states_the_result_with_its_label_reference_and_limit(two):
    directory, _, result = two
    text = (directory / "first/report.txt").read_text(encoding="utf-8")
    report = records.read_json(directory / "first/report.json")["result"]
    assert "raw, not family-adjusted" in text and x4.E4_LIMIT in text and "m_E4 = 2 of 4" in text
    assert f"Outcome at freeze (section 11): {report['interpretation']['conclusion']}" in text
    for row in report["episodes"][2:]:
        assert f"Delta_rt = {row['delta_rt']:+.4f}" in text
    assert "unavailable at step 7.2" in text and "(D80 = 0.3)" in text and text.endswith("\n")


def test_the_report_and_its_figures_are_the_same_bytes_twice(two):
    directory, _, _ = two
    first = {p.name: p.read_bytes() for p in (directory / "first").iterdir()}
    second = {p.name: p.read_bytes() for p in (directory / "second").iterdir()}
    assert first == second and set(FIGURES) <= set(first)


def test_the_report_refuses_an_analysis_that_disagrees_with_its_paths_or_nulls(two, tmp_path):
    _, tables, result = two
    altered = serial(result)
    altered["comparisons"]["primary"]["primary"]["observed"]["value"] += 1e-12
    with pytest.raises(ValueError, match="does not match the rolling paths"):
        write(tmp_path / "a", tables, altered)
    altered = serial(result)
    altered["comparisons"]["wild"]["null_models"][2]["intercept"] += 1e-12
    with pytest.raises(ValueError, match="fitted null of episode 2"):
        write(tmp_path / "b", tables, altered)
    with pytest.raises(ValueError, match="Unknown E4 report kind"):
        report_e4.write_report(tmp_path / "c", tables=tables, result=result, input_record={}, input_sha256="0" * 64,
                               D80=None, data_kind=x4.REHEARSAL_KIND, metadata={})
    assert not any((tmp_path / name).exists() for name in "abc")


def test_with_no_eligible_episode_the_figures_are_drawn_and_say_so(tmp_path):
    tables = constructed_tables(((2019, 4),) * 6)
    result = analysed(tables)
    manifest = write(tmp_path / "one", tables, result)
    write(tmp_path / "two", tables, result)
    assert result["m_E4"] == 0 and manifest["interpretation"]["conclusion"] == "not_estimable"
    for name in FIGURES:
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()
    svg = (tmp_path / "one/realtime.svg").read_text(encoding="utf-8")
    assert "No E4-eligible episode" in svg and "m_E4 = 0" in (tmp_path / "one/surrogates.svg").read_text("utf-8")
    assert table(tmp_path / "one/primary-surrogates.csv") == []
    assert manifest["file_sha256"]["realtime.svg"] == gates.sha256_file(tmp_path / "one/realtime.svg")
