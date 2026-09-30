"""The plan of parts of E4's X.3 run (tools/plan_e4_x3.py): the parts tile the registered coordinates exactly
once, as the runner itself reads each part's arguments, and no registered argument vector carries a
development option. Nothing is run."""
from collections import Counter
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

TREE = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, TREE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


planner = load("plan_e4_x3_under_test", "tools/plan_e4_x3.py")
runner = load("run_e4_checks_for_plan", "tools/run_e4_checks.py")
DEVELOPMENT_OPTIONS = ("--n-series", "--B", "--seed", "--retention", "--prerequisite")


def test_default_plan_is_forty_parts_of_twenty_five_series():
    value = planner.plan()
    parts = value["parts"]
    assert len(parts) == 40 and all(part["series"] == 25 for part in parts)
    assert [p["name"] for p in parts[:8]] == [f"size_r{a:03d}-{a + 25:03d}" for a in range(0, 200, 25)]
    assert parts[0]["out"] == "runs/extensions/E4/x3_size_r000-025.jsonl"
    assert parts[7]["out"] == "runs/extensions/E4/x3_size_r175-200.jsonl"
    assert parts[8]["out"] == "runs/extensions/E4/x3_power_c0_r000-025.jsonl"
    assert parts[-1]["out"] == "runs/extensions/E4/x3_power_c3_r175-200.jsonl"
    assert Counter(p["check"] for p in parts) == dict(size=8, power=32)
    assert Counter(p["cells"][0] for p in parts if p["check"] == "power") == {0: 8, 1: 8, 2: 8, 3: 8}
    assert parts[8]["argv"] == ["e4", "power", "--registered", "--root", ".", "--cells", "0", "--replicates", "0:25",
                                "--out", "runs/extensions/E4/x3_power_c0_r000-025.jsonl"]
    assert value["threads"] == dict(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    assert len({p["out"] for p in parts}) == 40 and value["runner"] == "tools/run_e4_checks.py"


@pytest.mark.parametrize("parts_per_cell", [1, 3, 7, 8, 25, 200])
def test_parts_tile_every_registered_coordinate_exactly_once(parts_per_cell):
    value = planner.plan(parts_per_cell)
    seen = dict(size=Counter(), power=Counter())
    for part in value["parts"]:
        args = runner.build_parser().parse_args(part["argv"])       # the runner's own reading of the part
        coordinates = runner.work_coordinates(args.check, n_series=200, cells=args.cells, replicates=args.replicates)
        assert coordinates == [(part["cells"][0], r) for r in range(*part["replicates"])]
        seen[args.check].update(coordinates)
    assert seen["size"] == Counter((0, r) for r in range(200))
    assert seen["power"] == Counter((c, r) for c in range(4) for r in range(200))
    assert len(value["parts"]) == 5 * parts_per_cell


def test_registered_argument_vectors_carry_no_development_option():
    value = planner.plan()
    vectors = [part["argv"] for part in value["parts"]] + list(value["summarize"].values())
    for argv in vectors:
        assert argv[:2] in (["e4", "size"], ["e4", "power"], ["e4", "summarize"])
        assert "--registered" in argv and argv[argv.index("--root") + 1] == "."
        assert not [a for a in argv if a.split("=")[0] in DEVELOPMENT_OPTIONS]
        args = runner.build_parser().parse_args(argv)
        assert args.registered is True and args.n_series is None and args.B is None
    for check, argv in value["summarize"].items():
        outs = [argv[i + 1] for i, a in enumerate(argv) if a == "--out"]
        assert outs == [p["out"] for p in value["parts"] if p["check"] == check]


def test_default_outputs_are_git_ignored_in_the_research_root():
    out = planner.plan()["parts"][0]["out"]
    assert subprocess.run(["git", "check-ignore", "-q", out], cwd=TREE).returncode == 0


def test_command_line_prints_the_plan_and_refuses_impossible_splits(capsys):
    assert planner.main(["--parts-per-cell", "4", "--root", "/research", "--out-dir", "runs/E4"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert len(value["parts"]) == 20 and value["parts"][0]["out"] == "runs/E4/x3_size_r000-050.jsonl"
    assert all(p["argv"][p["argv"].index("--root") + 1] == "/research" for p in value["parts"])
    for bad in ("0", "201"):
        with pytest.raises(SystemExit):
            planner.main(["--parts-per-cell", bad])
    with pytest.raises(ValueError):
        planner.bounds(True)
