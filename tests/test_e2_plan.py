"""The plan of parts of E2's X.3 run (tools/plan_e2_x3.py): the parts tile the registered coordinates exactly
once, the runner's own parser reads each part's arguments, every part names the prerequisite record, and no
registered argument vector carries a development option. Nothing is run."""
from collections import Counter
import importlib.util
from pathlib import Path

import pytest

TREE = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, TREE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


planner = load("plan_e2_x3_under_test", "tools/plan_e2_x3.py")
runner = load("run_e2_checks_for_plan", "tools/run_e2_checks.py")
DEVELOPMENT_OPTIONS = ("--n-series", "--B")


def test_default_plan_is_forty_parts_of_twenty_five_series_after_the_prerequisite():
    value = planner.plan()
    parts = value["parts"]
    assert len(parts) == 40 and all(part["series"] == 25 for part in parts)
    assert Counter(p["check"] for p in parts) == dict(size=8, power=32)
    assert Counter(p["cells"][0] for p in parts if p["check"] == "power") == {0: 8, 1: 8, 2: 8, 3: 8}
    assert value["prerequisite"]["argv"] == ["e2", "prerequisite", "--registered", "--root", ".", "--out",
                                             "runs/extensions/E2/x3_prerequisite.jsonl"]
    assert parts[8]["argv"] == ["e2", "power", "--registered", "--root", ".", "--cells", "0", "--replicates", "0:25",
                                "--prerequisite", "runs/extensions/E2/x3_prerequisite.jsonl",
                                "--out", "runs/extensions/E2/x3_power_c0_r000-025.jsonl"]
    assert value["threads"] == dict(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")


@pytest.mark.parametrize("parts_per_cell", [1, 3, 8, 200])
def test_parts_tile_every_registered_coordinate_exactly_once(parts_per_cell):
    value = planner.plan(parts_per_cell)
    covered = Counter()
    for part in value["parts"]:
        args = runner.build_parser().parse_args(part["argv"])
        coordinates = runner.work_coordinates(args.check, n_series=200, cells=args.cells, replicates=args.replicates)
        covered.update((args.check, cell, replicate) for cell, replicate in coordinates)
    expected = {("size", 0, i) for i in range(200)} | {("power", c, i) for c in range(4) for i in range(200)}
    assert set(covered) == expected and set(covered.values()) == {1}


def test_registered_argument_vectors_carry_no_development_option():
    value = planner.plan()
    vectors = [value["prerequisite"]["argv"], *(part["argv"] for part in value["parts"]),
               *value["summarize"].values()]
    for argv in vectors:
        assert "--registered" in argv and not set(argv) & set(DEVELOPMENT_OPTIONS)
        args = runner.build_parser().parse_args(argv)
        assert args.registered and args.n_series is None and args.B is None
    assert all("--prerequisite" in part["argv"] for part in value["parts"])
    outs = [part["out"] for part in value["parts"]]
    assert value["summarize"]["size"].count("--out") == 8 and value["summarize"]["power"].count("--out") == 32
    assert len(set(outs)) == len(outs)


@pytest.mark.parametrize("bad", [0, 201, True, 2.5])
def test_impossible_splits_are_refused(bad):
    with pytest.raises(ValueError):
        planner.plan(bad)
