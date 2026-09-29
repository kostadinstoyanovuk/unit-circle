"""Measure per-series runtime of the E1 and E3 checks on development fixtures (development seed only).

Usage: UC_RESEARCH_ROOT=<research checkout> python tools/measure_runtime.py [--e1-B 100] [--e3-B 40]
Prints one JSON object. No data file is read; the registered seed 1927 is never used.
"""
import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE / "src"), str(Path(os.environ.get("UC_RESEARCH_ROOT", "/home/user/kostadinstoyanovuk/unit-circle")) / "src")]

import numpy as np  # noqa: E402
import scipy  # noqa: E402

from uc_ext import common as c, e1, e3  # noqa: E402

DEV = c.DEVELOPMENT_MASTER_SEED


def timed(function):
    start = time.perf_counter()
    value = function()
    return value, time.perf_counter() - start


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--e1-B", type=int, default=100)
    parser.add_argument("--e3-B", type=int, default=40)
    parser.add_argument("--replicates", type=int, default=3)
    args = parser.parse_args()
    out = dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
               machine=platform.machine(), processor=platform.processor(), cpu_count=os.cpu_count(),
               master_seed=DEV)
    rows = []
    for replicate in range(args.replicates):
        record, seconds = timed(lambda: e1.size_replicate(replicate, master_seed=DEV, B=args.e1_B))
        rows.append(dict(check="E1 size", replicate=replicate, B=args.e1_B, seconds=seconds, status=record["status"],
                         no_episode=record["surrogate_no_episode"]))
    for cell in range(4):
        record, seconds = timed(lambda: e1.power_replicate(cell, 0, master_seed=DEV, B=args.e1_B))
        rows.append(dict(check="E1 power", cell=cell, replicate=0, B=args.e1_B, seconds=seconds, status=record["status"]))
    values = e1.design_series(c.stream_rng(DEV, 9500))
    _, seconds = timed(lambda: e1.primary_with_comparators(values, B=args.e1_B, rng=c.stream_rng(DEV, 9501)))
    rows.append(dict(check="E1 joint (primary+Kendall+lag-one)", B=args.e1_B, seconds=seconds))
    for replicate in range(args.replicates):
        g = e3.h1_design_series(c.stream_rng(DEV, 5320, 0, replicate))
        agreement, seconds_agreement = timed(lambda: e3.filter_agreement(g))
        record, seconds = timed(lambda: e3.size_replicate(replicate, master_seed=DEV, B=args.e3_B, check_agreement=False))
        fits = [a for a in record["comparison"]["attempts"] if a["status"] != "no_eligible_episode"]
        rows.append(dict(check="E3 size", replicate=replicate, B=args.e3_B, seconds=seconds, status=record["status"],
                         fitted_surrogates=len(fits), agreement_seconds=seconds_agreement,
                         agreement_passed=agreement["passed"],
                         agreement_max_state=agreement["max_state_difference"],
                         agreement_max_loglik=agreement["max_loglik_difference"]))
    for cell in range(4):
        record, seconds = timed(lambda: e3.power_replicate(cell, 0, master_seed=DEV, B=args.e3_B, check_agreement=False))
        rows.append(dict(check="E3 power", cell=cell, replicate=0, B=args.e3_B, seconds=seconds, status=record["status"]))
    g = e3.h1_design_series(c.stream_rng(DEV, 9502))
    fits = []
    for replicate in range(10):
        path = c.design_series(c.stream_rng(DEV, 9503, 0, replicate), kappa=1., n=259, onsets=(49,), signal_length=8)
        fit, seconds = timed(lambda: e3.fit_ml(path))
        fits.append(dict(seconds=seconds, accepted=fit.accepted,
                         nfev=fit.refinement["nfev"] if fit.refinement else 0))
    _, grid_batched = timed(lambda: e3.batched_filter(*e3.state_space(g), e3.grid_points()))
    _, one_reference = timed(lambda: e3.reference_loglik(g, 1e-4, 1e-4))
    out.update(rows=rows, e3_single_fits=fits, e3_grid_batched_seconds=grid_batched,
               e3_reference_filter_seconds=one_reference)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
