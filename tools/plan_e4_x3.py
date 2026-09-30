"""The registered split of E4's X.3 checks (prereg/E4.md section 11) into parts, one process each.

  python tools/plan_e4_x3.py [--parts-per-cell 8] [--root .] [--out-dir runs/extensions/E4]

Prints JSON: every part with its name, check, cells, replicate range (half-open, zero-based), output file and
the argument vector of tools/run_e4_checks.py in registered mode, to be run from the research root with the
registered interpreter; the thread settings under which the parts are run; and the two summarize argument
vectors. By default there are 40 parts of 25 series: eight size parts (x3_size_r000-025.jsonl to
x3_size_r175-200.jsonl) and eight parts for each of the four power cells (x3_power_c0_r000-025.jsonl to
x3_power_c3_r175-200.jsonl). The parts tile the registered coordinates exactly once: 200 size series and
4 x 200 power series. A registered argument vector carries no size, B, seed or stream option: the runner
takes the registered design itself. Nothing is run, and no file is read or written.
"""
import argparse
import json
import sys

RUNNER = "tools/run_e4_checks.py"
SERIES_PER_CELL = 200
POWER_CELLS = (0, 1, 2, 3)                 # kappa indices: kappa 1.0, 1.2, 1.4, 1.6
THREADS = dict(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
OUT_DIR = "runs/extensions/E4"             # git-ignored in the research root (runs/)


def bounds(parts, total=SERIES_PER_CELL):
    """Half-open replicate ranges of `parts` slices of 0..total whose sizes differ by at most one."""
    if isinstance(parts, bool) or not isinstance(parts, int) or not 1 <= parts <= total:
        raise ValueError(f"The number of parts per cell must be an integer from 1 to {total}")
    edges = [total * k // parts for k in range(parts + 1)]
    return list(zip(edges, edges[1:]))


def plan(parts_per_cell=8, *, root=".", out_dir=OUT_DIR):
    """The parts of the registered X.3 run, in the order size, then power cells 0 to 3, by replicate range."""
    parts = []
    for check, cell in [("size", 0)] + [("power", cell) for cell in POWER_CELLS]:
        for first, last in bounds(parts_per_cell):
            name = f"{check}_{'' if check == 'size' else f'c{cell}_'}r{first:03d}-{last:03d}"
            out = f"{out_dir}/x3_{name}.jsonl"
            argv = ["e4", check, "--registered", "--root", root, *(["--cells", str(cell)] if check == "power" else []),
                    "--replicates", f"{first}:{last}", "--out", out]
            parts.append(dict(name=name, check=check, cells=[cell], replicates=[first, last], series=last - first,
                              out=out, argv=argv))
    summarize = {check: ["e4", "summarize", "--registered", "--root", root,
                         *[value for part in parts if part["check"] == check for value in ("--out", part["out"])]]
                 for check in ("size", "power")}
    return dict(extension="e4", runner=RUNNER, parts_per_cell=parts_per_cell, series_per_cell=SERIES_PER_CELL,
                power_cells=list(POWER_CELLS), threads=dict(THREADS), parts=parts, summarize=summarize)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--parts-per-cell", type=int, default=8, help="slices of the 200 series of every cell")
    parser.add_argument("--root", default=".", help="the research root as the runner is given it (--root)")
    parser.add_argument("--out-dir", default=OUT_DIR, help="directory of the part files (git-ignored)")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        value = plan(args.parts_per_cell, root=args.root, out_dir=args.out_dir)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print(json.dumps(value, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
