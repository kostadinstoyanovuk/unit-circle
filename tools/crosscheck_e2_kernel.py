#!/usr/bin/env python3
"""crosscheck_e2_kernel.py - compares the second implementation of the E2 procedure (verify_e2_x3.py, written
from the registered texts) with the research packages for the same seed coordinates, on constructed series.

    python -B tools/crosscheck_e2_kernel.py --root <research clone holding src/uc_core, src/uc_e2 and src/uc_ext>
                                           [--B 25] [--sets 4] [--replicates 2] [--report out.json]

Development master seed and stream ids from 9000 only. For constructed series (X.3 design series of the
development streams, with and without planted persistence, and a constant, an explosive and a non-finite series
that must fail) it compares:
  1. the rolling window fits of W = 32, 40 and 48 (the M(t) path, and intercept, A1, A2 and modulus of single
     windows) with uc_e2.var, and the failures of both;
  2. the merged episodes of g and the statistic S (Delta per episode, eligible and ineligible onsets), primary and
     fixed-date, with uc_e2.procedure.onsets_of and statistic;
  3. the fitted null of each series (intercept, coefficients, initial vectors, centred residuals, removed means,
     modulus) with uc_e2.procedure.prepare_null, and the failures of both;
  4. complete surrogate paths, drawn one attempt at a time from the comparison's generator, with draw_surrogate;
  5. the complete comparisons - status, S, every attempt's status, S_b and Delta_b, K, B', p and the generator
     states - with csd_test (size mode) and fixed_date_test (power mode);
  6. the AT-12 draws and the reduction test of Annex B with uc_e2.synthetic.at12 and reduction_check;
  7. whole X.3 replicate records of uc_e2.synthetic (size and power, development seed), passed through every
     record check of verify_e2_x3.py in development mode.
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
_spec = importlib.util.spec_from_file_location("verify_e2_x3", HERE / "verify_e2_x3.py")
v = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = v
_spec.loader.exec_module(v)

SEED = 20260930
STREAMS = dict(primary=9200, window32=9201, window48=9202, fixed=9203, wild=9204, interval=9205,
               size_generation=9220, size_null=9221, power_generation=9230, power_null=9231, at12=9012)
FAILED = ("null_model_failed", "observed_statistic_failed")   # what the package reports as an exception


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

    def arrays(self, label, mine, theirs, size, **context):
        """Two arrays within the stated tolerance, NaN only against NaN; returns whether they agree."""
        diff, ok = v.max_abs_difference(mine, theirs)
        self.count(label, diff)
        if not ok:
            self.disagree(label, dict(context, max_abs_difference=diff), size)
        return ok

    def numbers(self, label, mine, theirs, size, **context):
        if mine is None or theirs is None:
            self.count(label)
            if (mine is None) != (theirs is None):
                self.disagree(label, dict(context, mine=mine, package=theirs), size)
            return
        self.count(label, abs(mine - theirs))
        if not v.close(mine, theirs):
            self.disagree(label, dict(context, mine=mine, package=theirs), size)

    def exact(self, label, mine, theirs, size, **context):
        self.count(label)
        if mine != theirs:
            self.disagree(label, dict(context, mine=mine, package=theirs), size)


def failure(call):
    """(result, None) or (None, 'ExceptionType: message') for a package call."""
    try:
        return call(), None
    except Exception as exc:                    # the package's own failure type is part of the comparison
        return None, "%s: %s" % (type(exc).__name__, exc)


# ----------------------------------------------------------------------------------- constructed series

def constructed(seed, sets):
    """(label, series, fixed onsets or None): X.3 design series of the development streams."""
    out = [("size design %d" % k, v.design_series(seed, STREAMS["size_generation"], 0, k)[0], None)
           for k in range(sets)]
    for cell, kappa in enumerate(v.KAPPAS):
        for k in range(max(1, sets // 2)):
            series = v.design_series(seed, STREAMS["power_generation"], cell, k, kappa, v.POWER_ONSETS)[0]
            out.append(("power design cell %d replicate %d" % (cell, k), series, v.POWER_ONSETS))
    return out


def special_series(seed):
    gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, 9911, 0, 0])))
    noise = gen.standard_normal((195, 2))
    explosive = np.zeros((195, 2))
    for t in range(2, 195):
        explosive[t] = np.array([1.0, 0.0]) + np.diag([1.1, 0.5]) @ explosive[t - 1] + noise[t]
    broken = v.design_series(seed, STREAMS["size_generation"], 0, 0)[0].copy()
    broken[50, 1] = np.nan
    return [("constant", np.full((195, 2), 2.5), v.POWER_ONSETS), ("explosive", explosive, v.POWER_ONSETS),
            ("non-finite", broken, v.POWER_ONSETS)]


# ------------------------------------------------------------------------------------------------ checks

def check_windows(found, pkg, x, label):
    n = len(x)
    for window in (32, 40, 48):
        theirs, error = failure(lambda: np.asarray(pkg.var.max_modulus(x, window), dtype=float))
        modulus, ok, _ = v.rolling_modulus(x[None], window)
        found.count("rolling fit failure")
        if bool(ok.all()) != (error is None):
            found.disagree("rolling fit failure", dict(series=label, window=window, mine_ok=bool(ok.all()),
                                                       package_error=error), n)
            continue
        if error is None:
            if len(theirs) != n or not np.isnan(theirs[:window - 1]).all():
                found.disagree("M(t) warm-up", dict(series=label, window=window), n)
            else:
                found.arrays("M(t) path", modulus[0], theirs[window - 1:], n, series=label, window=window)
    for length in (32, 40, 48):
        for start in (0, 41, n - length):
            segment = x[start:start + length]
            fit, error = failure(lambda: pkg.var.fit_var2(segment))
            mine = v.fit_windows(segment, window=length)
            found.count("single-window fit failure")
            if bool(mine["ok"][0, 0]) != (error is None):
                found.disagree("single-window fit failure", dict(series=label, start=start, length=length,
                                                                 package_error=error), length)
                continue
            if error is not None:
                continue
            where = dict(series=label, start=start, length=length)
            found.arrays("window intercept", mine["intercept"][0, 0], fit.intercept, length, **where)
            found.arrays("window A1", mine["a1"][0, 0], fit.coefficients[0], length, **where)
            found.arrays("window A2", mine["a2"][0, 0], fit.coefficients[1], length, **where)
            found.numbers("window modulus", float(v.radius_of(mine["a1"][0, 0], mine["a2"][0, 0])), fit.modulus,
                          length, **where)


def check_statistic(found, pkg, x, fixed, label):
    n = len(x)
    onsets, error = failure(lambda: list(pkg.procedure.onsets_of(x)))
    if error is None:
        found.exact("episode onsets", [s for s, _ in v.merged_episodes(x[:, 0])], onsets, n, series=label)
    for kind, dates in (("primary", None), ("fixed", fixed)):
        if kind == "fixed" and fixed is None:
            continue
        theirs, error = failure(lambda: pkg.procedure.statistic(x, fixed_onsets=dates))
        mine = v.observed_result(x, fixed=dates)
        found.count("statistic failure")
        if (mine["status"] == "observed_statistic_failed") != (error is not None):
            found.disagree("statistic failure", dict(series=label, kind=kind, mine=mine["status"],
                                                     package_error=error), n)
            continue
        if error is not None:
            continue
        where = dict(series=label, kind=kind)
        found.numbers("statistic S", mine["S"], theirs.mean_change, n, **where)
        found.exact("eligible onsets", list(mine["eligible"]), list(theirs.eligible_onsets), n, **where)
        ineligible = getattr(theirs, "ineligible_onsets", None)
        if ineligible is not None:
            found.exact("ineligible onsets", list(mine["ineligible"]), list(ineligible), n, **where)
        found.arrays("Delta per episode", mine["changes"], list(theirs.changes), n, **where)


def check_null(found, pkg, x, label):
    n = len(x)
    model, error = failure(lambda: pkg.procedure.prepare_null(x))
    try:
        mine, mine_error = v.fit_null(x), None
    except v.NullFailure as exc:
        mine, mine_error = None, str(exc)
    found.count("null fit failure")
    if (error is None) != (mine_error is None):
        found.disagree("null fit failure", dict(series=label, mine=mine_error, package=error), n)
        return None, None
    if mine is None:
        return None, None
    theirs = plain(model)
    where = dict(series=label)
    found.arrays("null intercept", mine["intercept"], theirs["intercept"], n, **where)
    found.arrays("null A1", mine["a1"], theirs["coefficients"][0], n, **where)
    found.arrays("null A2", mine["a2"], theirs["coefficients"][1], n, **where)
    found.arrays("null initial vectors", np.array(mine["initial"]), theirs["initial"], n, **where)
    found.arrays("null residuals", mine["residuals"], theirs["residuals"], n, **where)
    found.arrays("null removed means", mine["residual_mean_removed"], theirs["residual_mean_removed"], n, **where)
    found.numbers("null modulus", mine["modulus"], theirs["modulus"], n, **where)
    return model, mine


def check_paths(found, pkg, model, mine, seed, stream, cell, replicate, attempts, label):
    """The first attempts' surrogate paths, drawn one attempt at a time by the package from a fresh generator."""
    rng = pkg.streams.stream_rng(seed, stream, cell, replicate)
    gen = v.generator(seed, stream, cell, replicate)
    paths = v.regenerate(mine, v.draw_indices(gen, mine["n"] - 2, attempts))
    for b in range(attempts):
        theirs = np.asarray(pkg.procedure.draw_surrogate(model, rng), dtype=float)
        if not found.arrays("surrogate path", paths[b], theirs, mine["n"], series=label, attempt=b):
            break
    found.exact("generator state after the draws", rng.bit_generator.state, gen.bit_generator.state, mine["n"],
                series=label)


def check_comparison(found, pkg, x, mode, fixed, stream, cell, replicate, B, label):
    n = len(x)
    rng = pkg.streams.stream_rng(SEED, stream, cell, replicate)
    if mode == "primary":
        result, error = failure(lambda: pkg.procedure.csd_test(x, B=B, rng=rng))
    else:
        result, error = failure(lambda: pkg.procedure.fixed_date_test(x, fixed, B=B, rng=rng))
    mine = v.e2_comparison(x, mode=mode, fixed=fixed, seed=SEED, stream=stream, cell=cell, replicate=replicate,
                           attempts=B)
    where = dict(series=label, mode=mode)
    found.count("comparison failure")
    if error is not None or mine["status"] in FAILED:
        if (error is None) or mine["status"] not in FAILED:
            found.disagree("comparison failure", dict(where, mine=mine["status"], package_error=error), n)
        return
    theirs = plain(result)
    found.exact("comparison status", mine["status"], theirs["status"], n, **where)
    found.numbers("comparison S", mine["observed"]["S"], (theirs["observed"] or {}).get("mean_change"), n, **where)
    for key in ("attempted", "retained", "no_episode", "failed"):
        found.exact("comparison " + key, mine[key] if mine[key] is not None else 0, theirs[key] or 0, n, **where)
    found.exact("comparison exceedances", mine["K"], theirs["exceedances"], n, **where)
    found.numbers("comparison p", mine["p"], theirs["p_value"], n, **where)
    found.numbers("comparison grid spacing", mine["grid"], theirs["p_grid_spacing"], n, **where)
    attempts = theirs["attempts"]
    if mine["statistics"] is not None and attempts:
        found.exact("attempt statuses", list(mine["attempt_status"]), [a["status"] for a in attempts], n, **where)
        found.arrays("attempt statistics S_b", mine["statistics"],
                     [a["statistic"] if a["statistic"] is not None else float("nan") for a in attempts], n, **where)
        found.exact("attempt eligible onsets", [list(e) for e in mine["eligible"]],
                    [list(a["eligible_onsets"]) for a in attempts], n, **where)
        found.arrays("attempt changes Delta_b", [x for row in mine["changes"] for x in row],
                     [x for a in attempts for x in a["changes"]], n, **where)
    before = mine["rng_before"] if mine["rng_before"] is not None else mine["rng_fresh"]
    after = mine["rng_after"] if mine["rng_after"] is not None else mine["rng_fresh"]
    found.exact("generator state before the draws", json.loads(json.dumps(before)),
                json.loads(json.dumps(theirs["rng_before"])), n, **where)
    found.exact("generator state after the draws", json.loads(json.dumps(after)),
                json.loads(json.dumps(theirs["rng_after"])), n, **where)


def check_prerequisites(found, pkg, seed):
    Y, R = pkg.synthetic, pkg.streams
    stream = R.at12_stream(seed)
    theirs, mine = Y.at12(2000, seed, stream), v.at12_recompute(seed, stream, 2000)
    found.exact("AT-12 skipped draws", mine["skipped"], theirs["ar2"]["skipped"], 2000)
    found.numbers("AT-12 diagonal error", mine["diagonal_error"], theirs["diagonal"]["max_abs_error"], 2000)
    found.numbers("AT-12 AR(2) error", mine["ar2_error"], theirs["ar2"]["max_abs_error"], 2000)
    from uc_core.validation_design import h1_design_series
    values = h1_design_series(R.stream_rng(seed, STREAMS["size_generation"], 1, 0))
    package = Y.reduction_check(values)
    rows = v.reduction_recompute(values)
    found.exact("reduction fixture hash",
                [v.input_sha256(v.h1_series(seed, STREAMS["size_generation"], 1, 0, form=f)) for f in
                 ("closed", "text")].count(package["input_sha256"]) >= 1, True, 259)
    for row, theirs_row in zip(rows, package["windows"]):
        where = dict(window=row["window"])
        found.exact("reduction fitted windows", row["fitted"], theirs_row["fitted"], 259, **where)
        found.exact("reduction warm-up positions", row["warmup_same"], theirs_row["warmup_same"], 259, **where)
        found.exact("reduction verdict", row["passed"], theirs_row["passed"], 259, **where)
        found.numbers("reduction max difference", row["max_abs_difference"], theirs_row["max_abs_difference"], 259,
                      **where)


def check_records(found, pkg, seed, B, replicates, workdir):
    """Package-made X.3 records through the record checks of verify_e2_x3.py."""
    Y, R = pkg.synthetic, pkg.streams
    settings = Y.x3_settings(master_seed=seed)
    arguments = Y.x3_arguments(settings)
    files = []
    for check, coordinates in (("size", [(0, r) for r in range(replicates)]),
                               ("power", [(c, r) for c in range(len(Y.KAPPAS)) for r in range(min(replicates, 1))])):
        records = []
        for cell, replicate in coordinates:
            if check == "size":
                rec = Y.size_replicate(replicate, master_seed=seed, B=B, **arguments)
            else:
                rec = Y.power_replicate(cell, replicate, master_seed=seed, B=B, kappas=Y.KAPPAS, **arguments)
            rec = dict(rec)
            rec.update(record_type="replicate", registered=False, mode="development", master_seed=seed, B=B,
                       settings=settings, code_sha256="0" * 64)
            records.append(rec)
        head = dict(record_type="manifest", schema=2, extension="e2", check=check, mode="development",
                    master_seed=seed, n_series=replicates, B=B, kappas=list(Y.KAPPAS) if check == "power" else None,
                    settings=settings, streams=dict(R.stream_ids(seed), at12=R.at12_stream(seed)),
                    code_sha256="0" * 64, e1_code_sha256="0" * 64, identity_option=v.IDENTITY_OPTION,
                    identity=dict(commit="cross-check", python=sys.version.split()[0]),
                    imported=dict(ext_commit="cross-check"), lock=dict(satisfied=False), gate=None,
                    prerequisite=None, argv=["cross-check"])
        path = Path(workdir) / ("x3_%s_crosscheck.jsonl" % check)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            for obj in [head] + records:
                handle.write(json.dumps(obj) + "\n")
        files.append(str(path))
    payload = v.verify(files + ["--development", "--partial", "--quiet"])
    found.count("X.3 records verified")
    for problem in payload["problems"]:
        found.disagree("X.3 record check", problem, 0)
    return dict(problems=len(payload["problems"]), missing_fields=payload["missing_fields"],
                maxima=payload["maxima"], records=len(payload["per_record"]),
                regeneration_identical=sum(bool(r["regeneration_identical"]) for r in payload["per_record"]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="research clone or worktree holding src/uc_core and src/uc_e2")
    parser.add_argument("--seed", type=int, default=SEED, help="development master seed (never 1927)")
    parser.add_argument("--B", type=int, default=25, help="attempts per comparison")
    parser.add_argument("--sets", type=int, default=4, help="constructed size-design series (power: sets // 2 per cell)")
    parser.add_argument("--replicates", type=int, default=2, help="size replicates of the record check")
    parser.add_argument("--report", help="write the JSON findings here")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.seed == v.REGISTERED_SEED:
        print("master seed 1927 is refused here", file=sys.stderr)
        return 2
    if args.seed != SEED:
        print("the stream ids of this check are those of the development seed %d" % SEED, file=sys.stderr)
        return 2
    if not (root / "src" / "uc_e2").is_dir() or not (root / "src" / "uc_core").is_dir():
        print("no src/uc_e2 and src/uc_core under %s" % root, file=sys.stderr)
        return 2
    sys.path[:0] = [str(root / "src"), str(root)]
    import uc_e2.procedure
    import uc_e2.streams
    import uc_e2.synthetic
    import uc_e2.var

    class Package:
        var, procedure, streams, synthetic = uc_e2.var, uc_e2.procedure, uc_e2.streams, uc_e2.synthetic

    pkg = Package
    started = time.time()
    found = Findings()
    for label, x, fixed in constructed(args.seed, args.sets) + special_series(args.seed):
        check_windows(found, pkg, x, label)
        check_statistic(found, pkg, x, fixed, label)
        model, mine = check_null(found, pkg, x, label)
        if model is not None:
            check_paths(found, pkg, model, mine, args.seed, STREAMS["size_null"], 0, 0, 5, label)
        primary = label.startswith("size design") or label in ("constant", "explosive", "non-finite")
        if primary:
            check_comparison(found, pkg, x, "primary", None, STREAMS["size_null"], 0, 0, args.B, label)
        if fixed is not None:
            check_comparison(found, pkg, x, "fixed", fixed, STREAMS["power_null"], 1, 0, args.B, label)
    check_prerequisites(found, pkg, args.seed)
    with tempfile.TemporaryDirectory() as workdir:
        records = check_records(found, pkg, args.seed, args.B, args.replicates, workdir)
    elapsed = time.time() - started
    smallest = {}
    for item in found.disagreements:
        if item["label"] not in smallest or item["size"] < smallest[item["label"]]["size"]:
            smallest[item["label"]] = item
    print("crosscheck_e2_kernel.py: %s against %s (seed %d, B = %d)" % (Path(v.__file__).name, root, args.seed,
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
