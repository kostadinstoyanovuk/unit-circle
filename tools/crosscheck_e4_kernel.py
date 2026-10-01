#!/usr/bin/env python3
"""crosscheck_e4_kernel.py - compares the second implementation of the E4 procedure (verify_e4_x3.py, written
from the registered texts) with the research packages for the same seed coordinates, on constructed series.

    python -B tools/crosscheck_e4_kernel.py --root <research clone holding src/uc_core and src/uc_e4>
                                           [--B 50] [--sets 4] [--replicates 2] [--report out.json]

Development master seed and stream ids from 9000 only. For arbitrary vintage series made from a development
seed (AR(2) and standard-normal draws of several lengths, the shortest eligible n_v = 48, and a constant and an
explosive series that must fail), it compares:
  1. the observed Delta = M(n_v - 1) - M(n_v - 9) of each series with uc_core.rolling.max_modulus;
  2. the fitted null of each series (coefficients, intercept, initial pair, centred residuals, modulus) with
     uc_core.surrogate.prepare_null, and the failures of both;
  3. complete surrogate paths, drawn one attempt at a time from the episode's generator, with
     uc_core.surrogate.draw_surrogate;
  4. the complete comparison over the episodes of a set - status, S, every attempt's S_b and Delta_b, K, B', p,
     q and the Wilson interval - with uc_e4.procedure.compare;
  5. whole X.3 replicate records of uc_e4.synthetic (size and power), passed through every record check of
     verify_e4_x3.py in development mode.
Integers must agree exactly and floats within |a - b| <= 1e-12 + 1e-9*|b|. Every disagreement is printed with
the smallest example found. Exit status 0 when nothing disagrees, 1 otherwise, 2 for a usage error.
"""
import argparse
import dataclasses
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import time

import numpy as np

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("verify_e4_x3", HERE / "verify_e4_x3.py")
v = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = v
_spec.loader.exec_module(v)

SEED = 20260930
STREAMS = dict(primary=9400, window32=9401, window48=9402, wild=9404, interval=9405, size_generation=9420,
               size_null=9421, power_generation=9430, power_null=9431)
LENGTHS = (48, 55, 99, 160)


def plain(obj):
    """A dataclass, mapping or sequence as plain JSON-like data."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): plain(x) for k, x in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [plain(x) for x in obj]
    if isinstance(obj, np.ndarray):
        return [plain(x) for x in obj.tolist()]
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


class Findings:
    def __init__(self):
        self.disagreements = []
        self.compared = {}
        self.max_diff = {}

    def count(self, label, diff=None):
        self.compared[label] = self.compared.get(label, 0) + 1
        if diff is not None and math.isfinite(diff):
            self.max_diff[label] = max(self.max_diff.get(label, 0.0), diff)

    def disagree(self, label, example, size):
        self.disagreements.append(dict(label=label, example=example, size=size))


def arbitrary_sets(seed, sets):
    """Episode sets of constructed growth series (index k gives the set's own SeedSequence)."""
    out = []
    for k in range(sets):
        gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, 9910, k, 0])))
        series = []
        for j, n in enumerate(LENGTHS):
            if (k + j) % 2:
                series.append(gen.standard_normal(n) * 3.0 + 2.0)
            else:
                e = gen.normal(0, 3.5, size=n)
                x = np.empty(n)
                x[0], x[1] = 2.5 + e[0], 2.5 + e[1]
                for t in range(2, n):
                    x[t] = 1.5 + 0.3 * x[t - 1] + 0.1 * x[t - 2] + e[t]
                series.append(x)
        out.append(series)
    explosive = np.empty(60)
    explosive[0], explosive[1] = 1.0, 2.0
    for t in range(2, 60):
        explosive[t] = 1.35 * explosive[t - 1] - 0.315 * explosive[t - 2]
    special = [np.full(60, 2.5), explosive]
    return out, special


def check_series(found, pkg, s, label):
    rolling, surrogate = pkg["rolling"], pkg["surrogate"]
    n = len(s)
    mine_delta, reason = v.series_delta(s)
    try:
        modulus = np.asarray(rolling.max_modulus(s, 40), dtype=float)
        theirs = float(modulus[n - 1] - modulus[n - 9]) if len(modulus) == n else None
        if theirs is not None and not math.isfinite(theirs):
            theirs = None
        error = None if len(modulus) == n else "max_modulus returned %d values for %d" % (len(modulus), n)
    except Exception as exc:                    # the package's own failure type is part of the comparison
        theirs, error = None, "%s: %s" % (type(exc).__name__, exc)
    found.count("observed Delta", None if theirs is None or mine_delta is None else abs(theirs - mine_delta))
    if (theirs is None) != (mine_delta is None) or (theirs is not None and not v.close(mine_delta, theirs)):
        found.disagree("observed Delta", dict(series=label, n=n, mine=mine_delta, mine_reason=reason,
                                              package=theirs, package_error=error), n)
    try:
        null = surrogate.prepare_null(s)
        theirs_null = plain(null)
    except Exception as exc:
        theirs_null = dict(error="%s: %s" % (type(exc).__name__, exc))
    try:
        mine_null = v.fit_null(s)
    except v.NullFailure as exc:
        mine_null = dict(error=str(exc))
    found.count("null fit")
    if ("error" in theirs_null) != ("error" in mine_null):
        found.disagree("null fit failure", dict(series=label, n=n, mine=mine_null.get("error"),
                                                package=theirs_null.get("error")), n)
        return None, None
    if "error" in mine_null:
        return None, None
    pairs = [("phi1", mine_null["phi1"], theirs_null["coefficients"][0]),
             ("phi2", mine_null["phi2"], theirs_null["coefficients"][1]),
             ("intercept", mine_null["intercept"], theirs_null["intercept"]),
             ("modulus", mine_null["modulus"], theirs_null.get("modulus"))]
    for name, a, b in pairs:
        found.count("null " + name, None if b is None else abs(a - b))
        if b is not None and not v.close(a, b):
            found.disagree("null " + name, dict(series=label, n=n, mine=a, package=b), n)
    diff, ok = v.max_abs_difference(mine_null["residuals"], theirs_null["residuals"])
    found.count("null residuals", diff)
    if not ok:
        found.disagree("null residuals", dict(series=label, n=n, max_abs_difference=diff), n)
    if list(theirs_null["initial"]) != list(mine_null["initial"]):
        found.disagree("null initial pair", dict(series=label, mine=mine_null["initial"],
                                                 package=theirs_null["initial"]), n)
    return null, mine_null


def check_paths(found, pkg, null, mine_null, seed, stream, cell, attempts, label):
    """Paths of the first attempts, drawn one attempt at a time by the package from a fresh generator."""
    rng = pkg["streams"].stream_rng(seed, stream, cell, 0)
    mine_gen = v.generator(seed, stream, cell, 0)
    indices = v.draw_indices(mine_gen, mine_null["n"], attempts)
    mine_paths = v.regenerate(mine_null, indices)
    for b in range(attempts):
        theirs = np.asarray(pkg["surrogate"].draw_surrogate(null, rng, kind="residual"), dtype=float)
        diff, ok = v.max_abs_difference(mine_paths[b], theirs)
        found.count("surrogate path", diff)
        if not ok:
            found.disagree("surrogate path", dict(series=label, attempt=b, n=mine_null["n"], max_abs_difference=diff),
                           mine_null["n"])
            break
    found.count("generator state after the draws")
    if rng.bit_generator.state != mine_gen.bit_generator.state:
        found.disagree("generator state after the draws", dict(series=label, cell=cell), mine_null["n"])


def check_comparison(found, pkg, series, seed, stream, B, label):
    procedure = pkg["procedure"]
    episodes = [procedure.EpisodeInput(j, np.asarray(s, dtype=float)) for j, s in enumerate(series)]
    rngs = {j: pkg["streams"].stream_rng(seed, stream, j, 0) for j in range(len(series))}
    theirs = plain(procedure.compare(episodes, rngs, window=40, B=B, kind="residual").primary)
    mine = v.e4_comparison(series, seed, stream, list(range(len(series))), 0, B)
    size = sum(len(s) for s in series)
    found.count("comparison status")
    if theirs.get("status") != mine["status"]:
        found.disagree("comparison status", dict(set=label, mine=mine["status"], package=theirs.get("status")), size)
    observed = theirs.get("observed") or {}
    found.count("comparison S", None if mine["S"] is None or observed.get("value") is None else
                abs(mine["S"] - observed["value"]))
    if not v.close(mine["S"], observed.get("value")):
        found.disagree("comparison S", dict(set=label, mine=mine["S"], package=observed.get("value")), size)
    drawn = mine["statistics"] is not None          # no draw at all is recorded here as None, there as 0
    for key, ours in (("exceedances", mine["K"]), ("retained", mine["retained"]), ("failed", mine["failed"])):
        found.count("comparison " + key)
        if (theirs.get(key) != ours) if drawn else (theirs.get(key) not in (0, None)):
            found.disagree("comparison " + key, dict(set=label, mine=ours, package=theirs.get(key)), size)
    for key, ours in (("p_value", mine["p"]), ("q", mine["q"])):
        found.count("comparison " + key)
        if not v.close(theirs.get(key), ours):
            found.disagree("comparison " + key, dict(set=label, mine=ours, package=theirs.get(key)), size)
    attempts = theirs.get("attempts") or []
    if mine["statistics"] is not None and attempts:
        stat = np.array([a.get("statistic") if a.get("statistic") is not None else np.nan for a in attempts],
                        dtype=float)
        diff, ok = v.max_abs_difference(stat, mine["statistics"])
        found.count("attempt statistics S_b", diff)
        if not ok:
            found.disagree("attempt statistics S_b", dict(set=label, max_abs_difference=diff), size)


def check_records(found, pkg, seed, B, replicates, workdir):
    """Package-made X.3 records through the record checks of verify_e4_x3.py."""
    streams = pkg["streams"].Streams(**STREAMS)
    files = []
    for check, coordinates in (("size", [(0, r) for r in range(replicates)]),
                               ("power", [(c, r) for c in range(4) for r in range(min(replicates, 1))])):
        records = []
        for cell, replicate in coordinates:
            if check == "size":
                rec = pkg["synthetic"].size_replicate(replicate, master_seed=seed, streams=streams, B=B)
            else:
                rec = pkg["synthetic"].power_replicate(cell, replicate, master_seed=seed, streams=streams, B=B)
            rec = plain(rec)
            rec.update(record_type="replicate", registered=False, mode="development", master_seed=seed, B=B,
                       settings={}, code_sha256="0" * 64)
            records.append(rec)
        head = dict(record_type="manifest", schema=2, extension="e4", check=check, mode="development",
                    master_seed=seed, n_series=replicates, B=B, kappas=list(v.KAPPAS) if check == "power" else None,
                    settings={}, code_sha256="0" * 64, e1_code_sha256="0" * 64,
                    identity=dict(commit="cross-check", python=sys.version.split()[0]), lock=dict(satisfied=False),
                    gate=None, streams=STREAMS)
        path = Path(workdir) / ("x3_%s_crosscheck.jsonl" % check)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            for obj in [head] + records:
                handle.write(json.dumps(obj) + "\n")
        files.append(str(path))
    payload = v.verify(files + ["--development", "--partial", "--quiet"])
    found.count("X.3 records verified", None)
    for problem in payload["problems"]:
        found.disagree("X.3 record check", problem, 0)
    return dict(problems=len(payload["problems"]), missing_fields=payload["missing_fields"],
                maxima=payload["maxima"], records=len(payload["per_record"]),
                regeneration_identical=sum(bool(r["regeneration_identical"]) for r in payload["per_record"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="research clone or worktree holding src/uc_core and src/uc_e4")
    parser.add_argument("--seed", type=int, default=SEED, help="development master seed (never 1927)")
    parser.add_argument("--B", type=int, default=50, help="attempts per comparison")
    parser.add_argument("--sets", type=int, default=4, help="sets of constructed vintage series")
    parser.add_argument("--replicates", type=int, default=2, help="size replicates (power: one per cell)")
    parser.add_argument("--report", help="write the JSON findings here")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.seed == v.REGISTERED_SEED:
        print("master seed 1927 is refused here", file=sys.stderr)
        return 2
    if not (root / "src" / "uc_e4").is_dir() or not (root / "src" / "uc_core").is_dir():
        print("no src/uc_e4 and src/uc_core under %s" % root, file=sys.stderr)
        return 2
    sys.path[:0] = [str(root / "src"), str(root)]
    import uc_core.rolling
    import uc_core.surrogate
    import uc_e4.procedure
    import uc_e4.streams
    import uc_e4.synthetic
    pkg = dict(rolling=uc_core.rolling, surrogate=uc_core.surrogate, procedure=uc_e4.procedure,
               streams=uc_e4.streams, synthetic=uc_e4.synthetic)
    started = time.time()
    found = Findings()
    sets, special = arbitrary_sets(args.seed, args.sets)
    for k, series in enumerate(sets):
        for j, s in enumerate(series):
            null, mine_null = check_series(found, pkg, s, "set %d series %d" % (k, j))
            if null is not None and j == 0:
                check_paths(found, pkg, null, mine_null, args.seed, STREAMS["primary"], j, 5,
                            "set %d series %d" % (k, j))
        check_comparison(found, pkg, series, args.seed, STREAMS["primary"], args.B, "set %d" % k)
    for label, s in zip(("constant", "explosive"), special):
        check_series(found, pkg, s, label)
    check_comparison(found, pkg, [sets[0][0], special[0]], args.seed, STREAMS["primary"], 5, "with a constant series")
    check_comparison(found, pkg, [sets[0][0], special[1]], args.seed, STREAMS["primary"], 5,
                     "with an explosive series")
    with tempfile.TemporaryDirectory() as workdir:
        records = check_records(found, pkg, args.seed, args.B, args.replicates, workdir)
    elapsed = time.time() - started
    smallest = {}
    for item in found.disagreements:
        if item["label"] not in smallest or item["size"] < smallest[item["label"]]["size"]:
            smallest[item["label"]] = item
    print("crosscheck_e4_kernel.py: %s against %s (seed %d, B = %d)" % (Path(v.__file__).name, root, args.seed,
                                                                      args.B))
    for label in sorted(found.compared):
        print("  %-34s compared %4d; max |difference| %s" % (label, found.compared[label],
                                                             "%.3g" % found.max_diff[label]
                                                             if label in found.max_diff else "-"))
    print("  X.3 records of the package through the record checks: %s" % json.dumps(records, default=str))
    print("  disagreements: %d" % len(found.disagreements))
    for label, item in sorted(smallest.items()):
        print("    - %s (smallest example): %s" % (label, json.dumps(item["example"], default=str)[:400]))
    print("  finished in %.1f s" % elapsed)
    if args.report:
        with open(args.report, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(dict(root=str(root), seed=args.seed, B=args.B, compared=found.compared,
                           max_diff=found.max_diff, records=records, disagreements=found.disagreements,
                           elapsed_seconds=elapsed), handle, indent=1, default=str)
            handle.write("\n")
    return 0 if not found.disagreements else 1


if __name__ == "__main__":
    sys.exit(main())
