#!/usr/bin/env python3
"""verify_e_x3.py - an independent check of the official E1 and E3 synthetic (X.3) size and power outputs.

Written from the registered texts (prereg/E1.md section 11; prereg/E3.md sections 6 and 11; prereg/H1.md
sections 4-6 and 9, which the addenda incorporate) and from the output formats of tools/run_e_checks.py
and the operational driver. It imports nothing from uc_core, uc_ext or uc_verify: Python's standard
library and NumPy only, so that it does not rest on the code it checks.

    python -B verify_e_x3.py --extension e1 --dir <clone>/runs/extensions [--report out.json]

It opens every input read-only, streams the part files line by line (never a whole file), writes nothing
inside the directory it reads (it prints a report to stdout and, with --report, writes a JSON report that
must lie outside the research clone), and consumes no random numbers.

What it does:
  1. integrity of every part file: each line valid JSON with a trailing newline (a truncated last line is
     reported), one manifest first, session and replicate lines only; record coordinates (kind, cell,
     replicate) unique and complete over the registered design, no extra records; every record's status;
     per-record consistency (accounting identity, stored input against its SHA-256, the p-value recomputed
     from the stored surrogate statistics, the observed S recomputed from the stored input by a separate
     implementation of the rolling AR(2) (E1) or of the Kalman filter at the stored variances (E3));
  2. recomputes from the records: the size rejection rate (raw p <= 0.05, valid records only, explicit
     denominators), the four power rates with 95% Wilson intervals, adjacent differences and 1.96-SE
     decrease flags, mean S and its standard error per cell, and D80 by the first raw crossing;
  3. applies the registered pass rule, printing PASS or FAIL per clause with the numbers and the clause's
     registered wording;
  4. recomputes the SHA-256 of every file listed in OUTPUT_SHA256.json and reports unlisted files;
  5. compares every figure with the runner's own x3_*_summary.json (counts exactly; floating point within
     |a-b| <= 1e-12 + 1e-9*|b|, see FLOAT_ABS/FLOAT_REL) and with the driver's stage marker.

Exit status: 0 no integrity problem and full agreement with the runner; 1 problems or disagreements;
2 usage or input error. The registered pass or fail is reported, not encoded in the exit status.
"""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import sys
import time

import numpy as np

TOOL_VERSION = "1.1 (29 September 2026)"
Z_WILSON = 1.959963984540054          # H1 section 6
DECREASE_Z = Fraction(196, 100)       # H1 section 9: "exceeds 1.96 times that standard error"
ALPHA = Fraction(5, 100)              # raw p <= 0.05
BAND = (Fraction(2, 100), Fraction(9, 100))
TARGET = Fraction(80, 100)            # D80: first raw crossing of 0.80
KAPPAS = (1.0, 1.2, 1.4, 1.6)
REGISTERED_SEED = 1927
N_SERIES = 200
B_ATTEMPTS = 1000
# Floating-point comparison with the runner. Counts and rates of counts are compared exactly. Means and
# standard errors differ only by summation order (NumPy pairwise sums against math.fsum here), which for
# 200 values of order 0.1 moves the result by well under 1e-14; one record more or less moves a mean S by
# about 1e-3. The tolerance sits far from both.
FLOAT_ABS, FLOAT_REL = 1e-12, 1e-9
# Recomputing S by another numerical route (closed-form centred least squares here, scaled lstsq in the
# pipeline; a separately written square-root filter here) agrees to rounding, not bit for bit.
S_TOL_E1 = 1e-9
S_TOL_E3 = 1e-6                        # E3 section 6 allows 1e-8 in states and 1e-6 in l(r) between filters
LOGLIK_TOL_E3 = 1e-6
STATE_TOL_E3 = 1e-8
STAT_TOL = 1e-12                       # a stored statistic against the mean of its stored components
GRID = (0.0,) + tuple(10.0 ** (k / 2) for k in range(-16, -1))
DIFFUSE = 1e8

DESIGNS = {
    "e1": dict(name="E1", n_growth=316, window=30, lookback=2, minimum_run=1, merge=2, first_year=1701,
               exogenous=frozenset(list(range(1914, 1919)) + list(range(1939, 1946)) + [2020]),
               first_eligible=32, first_indicator=29, power_onsets=(34, 74, 114, 154, 194, 234, 274),
               tag="prereg-E1", registration_id="mjg9w", settings={}),
    "e3": dict(name="E3", n_growth=259, window=None, lookback=8, minimum_run=2, merge=8, first_year=None,
               exogenous=frozenset(), first_eligible=48, first_indicator=39,
               power_onsets=(49, 99, 149, 199, 249), tag="prereg-E3", registration_id="rhzsm",
               settings=dict(engine="batched", check_agreement=True, grid_point_failure="discard",
                             retention="all_fits")),
}

# Registered wording, quoted exactly (file, section, line at research commit 6ea0245).
CLAUSES = {
    "e1": dict(
        size=("prereg/E1.md", "section 11, Size (AT-15 adapted), line 211",
              "Pass: an empirical rejection rate (raw p ≤ 0.05) between **0.02 and 0.09 inclusive**, with "
              "all 200 replicates valid. Failure accounting and uncertainty reporting follow H1 §9."),
        power=("prereg/E1.md", "section 11, Power (AT-16 adapted), line 218",
               "Report every cell as H1 §9: rates, Wilson intervals, adjacent differences with the 1.96-SE "
               "decrease flag, mean S and its standard error."),
        d80=("prereg/E1.md", "section 11, line 219",
             "**D80.** As H1 §9: the first raw crossing of 0.80, interpolated linearly in κ; undefined if "
             "any cell is invalid or no κ ≤ 1.6 reaches 0.80."),
        incorporation=("prereg/E1.md", "Relation to the registered H1 protocol, line 9",
                       "**Every H1 rule applies unchanged unless this addendum states a replacement.**"),
    ),
    "e3": dict(
        size=("prereg/E3.md", "section 11, Size (AT-15 adapted), line 193",
              "Pass: rejection rate between **0.02 and 0.09** inclusive, with all 200 valid."),
        power=("prereg/E3.md", "section 11, Reporting and D80, line 201",
               "**Reporting and D80.** As H1 §9, including the 1.96-SE decrease flag and the "
               "first-raw-crossing D80."),
        d80=("prereg/E3.md", "section 11, Reporting and D80, line 201",
             "**Reporting and D80.** As H1 §9, including the 1.96-SE decrease flag and the "
             "first-raw-crossing D80."),
        incorporation=("prereg/E3.md", "Relation to the registered H1 protocol, line 7",
                       "**Every H1 rule applies unchanged unless replaced here.**"),
        prereq_f2=("prereg/E3.md", "section 11, Prerequisites, line 178",
                   "F2 (plan p. 7) and AT-11 on the implementation used."),
        prereq_r0=("prereg/E3.md", "section 11, Prerequisites, line 179",
                   "With r1 = r2 = 0 and the §6 prior, the final filtered state equals the full-sample OLS "
                   "estimate to 1e−6 on one base synthetic series, generated from stream 5320, cell 1, "
                   "replicate 0."),
        prereq_agreement=("prereg/E3.md", "section 11, Prerequisites, line 180",
                          "The §6 agreement test for any batched filter."),
        agreement_rule=("prereg/E3.md", "section 6, Filter implementation, line 85",
                        "A batched or re-implemented filter may be used only if, on every X.3 fixture of §11 "
                        "and on AT-11's fixture, it agrees with that reference to **1e−8** in every "
                        "filtered state and **1e−6** in l(r)."),
    ),
    "h1": dict(
        valid_cell=("prereg/H1.md", "section 9, Cell reporting",
                    "A cell is complete and valid only when all 200 provide finite S and valid p."),
        flag=("prereg/H1.md", "section 9, Cell reporting",
              "Flag a decrease whose magnitude exceeds **1.96** times that standard error."),
        at16=("prereg/H1.md", "section 9, Cell reporting",
              "If any cell is invalid/incomplete or a decrease exceeds this threshold, AT-16 does not pass and "
              "G2 remains pending."),
        size_valid=("prereg/H1.md", "section 9, Size cell: AT-15",
                    "Count a rejection only for a valid p≤0.05."),
    ),
}

PART_PATTERNS = (re.compile(r"^x3_size_r(\d+)-(\d+)\.jsonl$"), re.compile(r"^x3_power_c(\d+)_r(\d+)-(\d+)\.jsonl$"))


# ------------------------------------------------------------------------------------------ arithmetic

def close(a, b, abs_tol=FLOAT_ABS, rel_tol=FLOAT_REL):
    if a is None or b is None:
        return a is None and b is None
    a, b = float(a), float(b)
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return abs(a - b) <= abs_tol + rel_tol * abs(b)


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def finite(value):
    return is_number(value) and math.isfinite(value)


def wilson(successes, total, z=Z_WILSON):
    """H1 section 6: centre (q+z^2/(2n))/(1+z^2/n), half-width z*sqrt(q(1-q)/n+z^2/(4n^2))/(1+z^2/n)."""
    q = successes / total
    d = 1 + z * z / total
    centre = (q + z * z / (2 * total)) / d
    half = z * math.sqrt(q * (1 - q) / total + z * z / (4 * total * total)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def exceeds_threshold(p_prev, p_cur, n):
    """H1 section 9, exactly: the decrease m = p_prev - p_cur exceeds 1.96*sqrt(p_prev(1-p_prev)/n + p_cur(1-p_cur)/n).
    Both sides are compared as rationals (m^2 against 1.96^2 times the variance), so there is no rounding;
    "exceeds" is strict, so a decrease exactly at the threshold is not flagged."""
    p1, p2 = Fraction(p_prev), Fraction(p_cur)
    m = p1 - p2
    variance = (p1 * (1 - p1) + p2 * (1 - p2)) / n
    return bool(m > 0 and m * m > DECREASE_Z * DECREASE_Z * variance)


def decrease_flag(r_prev, r_cur, n):
    """Returns (exact flag, the flag as the runner computes it in floating point, difference, standard error)."""
    exact = exceeds_threshold(Fraction(r_prev, n), Fraction(r_cur, n), n)
    f1, f2 = r_prev / n, r_cur / n
    se = math.hypot(math.sqrt(f1 * (1 - f1) / n), math.sqrt(f2 * (1 - f2) / n))
    difference = f2 - f1
    return exact, bool(difference < -1.96 * se), difference, se


def cell_figures(entries, requested, kappa=None):
    """H1 section 9 accounting for one cell. entries: one dict per record present (replicate, status,
    valid, rejected, S). Rates use the nominal denominator `requested`."""
    valid = [e for e in entries if e["valid"]]
    rejected = sum(1 for e in valid if e["rejected"])
    missing = requested - len(valid)
    failures = {}
    for e in entries:
        if not e["valid"]:
            failures[str(e["status"])] = failures.get(str(e["status"]), 0) + 1
    complete = missing == 0 and len(entries) == requested
    out = dict(kappa=kappa, requested=requested, attempted=len(entries), valid=len(valid), rejected=rejected,
               unfinished=requested - len(entries), failures=failures,
               accounting_bounds=(rejected / requested, (rejected + missing) / requested),
               valid_only_rate=(rejected / len(valid)) if valid else None, complete=complete,
               rate=None, rate_exact=None, rate_se=None, rate_wilson=None, mean_S=None, mean_S_se=None)
    if complete:
        values = [e["S"] for e in sorted(valid, key=lambda e: e["replicate"])]
        mean = math.fsum(values) / requested
        rate = rejected / requested
        out.update(rate=rate, rate_exact="%d/%d" % (rejected, requested),
                   rate_se=math.sqrt(rate * (1 - rate) / requested), rate_wilson=wilson(rejected, requested),
                   mean_S=mean,
                   mean_S_se=(math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (requested - 1))
                              / math.sqrt(requested)) if requested > 1 else None)
    return out


def power_figures(cells):
    """Adjacent differences, decrease flags (exact and as the runner computes them) and D80 (H1 section 9)."""
    result = dict(adjacent=[], flags_exact=[], flags_float=[], D80=None, kappa80=None, crossing=None,
                  d80_status=None, all_valid=all(c["complete"] for c in cells))
    if not result["all_valid"]:
        result["d80_status"] = "undefined: a cell is invalid or incomplete"
        return result
    for prev, cur in zip(cells, cells[1:]):
        exact, flt, difference, se = decrease_flag(prev["rejected"], cur["rejected"], cur["requested"])
        margin = -difference - 1.96 * se
        result["adjacent"].append(dict(left_kappa=prev["kappa"], right_kappa=cur["kappa"], difference=difference,
                                       standard_error=se, threshold=1.96 * se, decrease_flag=exact,
                                       decrease_flag_float=flt, margin=margin))
        result["flags_exact"].append(exact)
        result["flags_float"].append(flt)
    for index, cell in enumerate(cells):
        rate = Fraction(cell["rejected"], cell["requested"])
        if rate < TARGET:
            continue
        if index == 0:
            result.update(D80=cell["mean_S"], kappa80=cell["kappa"], crossing=dict(left=0, right=0, weight=0.0))
        else:
            left = cells[index - 1]
            left_rate = Fraction(left["rejected"], left["requested"])
            weight = (TARGET - left_rate) / (rate - left_rate)
            w = float(weight)
            result.update(D80=left["mean_S"] + w * (cell["mean_S"] - left["mean_S"]),
                          kappa80=left["kappa"] + w * (cell["kappa"] - left["kappa"]),
                          crossing=dict(left=index - 1, right=index, weight=w))
        result["d80_status"] = "defined"
        break
    else:
        result["d80_status"] = "undefined: no kappa <= 1.6 reaches 0.80"
    return result


def size_rule(cell, n):
    """E1/E3 section 11 size clauses: the rate R/n in [0.02, 0.09] inclusive (exact rationals) with all n valid."""
    band = bool(cell["complete"] and BAND[0] <= Fraction(cell["rejected"], n) <= BAND[1])
    all_valid = bool(cell["valid"] == n and cell["attempted"] == n)
    return dict(band=band, all_valid=all_valid, passed=band and all_valid)


def power_rule(power):
    """H1 section 9 (AT-16) as incorporated: every cell complete and valid, and no flagged decrease."""
    cells_valid = bool(power["all_valid"])
    no_flag = bool(cells_valid and not any(power["flags_exact"]))
    return dict(cells_valid=cells_valid, no_flag=no_flag, passed=no_flag)


# ------------------------------------------------------------------ independent statistic (H1 sections 4-5)

def companion_modulus(phi1, phi2):
    """H1 section 4: M = sqrt(-phi2) for D < 0; otherwise the larger-magnitude real root by copysign and the
    other by the root product -phi2."""
    phi1 = np.asarray(phi1, dtype=float)
    phi2 = np.asarray(phi2, dtype=float)
    d = phi1 * phi1 + 4 * phi2
    out = np.empty_like(phi1)
    negative = d < 0
    out[negative] = np.sqrt(-phi2[negative])
    real = ~negative
    big = (phi1[real] + np.copysign(np.sqrt(d[real]), phi1[real])) / 2
    safe = np.where(big != 0, big, 1.0)
    small = np.where(big != 0, -phi2[real] / safe, 0.0)
    out[real] = np.maximum(np.abs(big), np.abs(small))
    return out


def rolling_modulus(x, window):
    """M(t) for t >= window-1 by intercept-inclusive least squares in closed form on centred columns (a
    different numerical route from the pipeline's scaled lstsq); NaN before. Raises on a singular window."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    modulus = np.full(n, np.nan)
    if n < window:
        return modulus
    w = np.lib.stride_tricks.sliding_window_view(x, window)
    y, l1, l2 = w[:, 2:], w[:, 1:-1], w[:, :-2]
    yc = y - y.mean(axis=1)[:, None]
    c1 = l1 - l1.mean(axis=1)[:, None]
    c2 = l2 - l2.mean(axis=1)[:, None]
    s11, s22, s12 = (c1 * c1).sum(1), (c2 * c2).sum(1), (c1 * c2).sum(1)
    s1y, s2y = (c1 * yc).sum(1), (c2 * yc).sum(1)
    det = s11 * s22 - s12 * s12
    if not np.all(np.isfinite(det)) or np.any(det <= 0):
        raise ValueError("singular or non-finite window")
    phi1 = (s22 * s1y - s12 * s2y) / det
    phi2 = (s11 * s2y - s12 * s1y) / det
    modulus[window - 1:] = companion_modulus(phi1, phi2)
    return modulus


def ols_ar2(x):
    """Full-sample intercept-inclusive AR(2) in closed form; returns (phi1, phi2, intercept, residuals)."""
    x = np.asarray(x, dtype=float)
    y, l1, l2 = x[2:], x[1:-1], x[:-2]
    my, m1, m2 = y.mean(), l1.mean(), l2.mean()
    yc, c1, c2 = y - my, l1 - m1, l2 - m2
    s11, s22, s12 = float(c1 @ c1), float(c2 @ c2), float(c1 @ c2)
    s1y, s2y = float(c1 @ yc), float(c2 @ yc)
    det = s11 * s22 - s12 * s12
    phi1 = (s22 * s1y - s12 * s2y) / det
    phi2 = (s11 * s2y - s12 * s1y) / det
    intercept = my - phi1 * m1 - phi2 * m2
    return phi1, phi2, intercept, y - intercept - phi1 * l1 - phi2 * l2


def episodes(g, minimum_run, merge):
    """Runs of strictly negative values of at least minimum_run, merged when onset - previous end <= merge."""
    negative = np.asarray(g) < 0
    runs, t, n = [], 0, len(negative)
    while t < n:
        if negative[t]:
            start = t
            while t + 1 < n and negative[t + 1]:
                t += 1
            if t - start + 1 >= minimum_run:
                runs.append((start, t))
        t += 1
    merged = []
    for start, end in runs:
        if merged and start - merged[-1][1] <= merge:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def pre_onset(modulus, onsets, lookback):
    """(eligible, ineligible, changes): Delta = M(r-1) - M(r-lookback-1) where both are finite."""
    eligible, ineligible, changes = [], [], []
    for r in onsets:
        earlier, later = r - lookback - 1, r - 1
        if earlier < 0 or later >= len(modulus) or not (math.isfinite(modulus[earlier]) and math.isfinite(modulus[later])):
            ineligible.append(r)
            continue
        eligible.append(r)
        changes.append(float(modulus[later] - modulus[earlier]))
    return eligible, ineligible, changes


def filtered_states(x, r1, r2):
    """Kalman filter of the E3 section 6 state space at sigma2 = 1 (the filtered states do not depend on
    sigma2, which scales every variance): square-root (array) covariance form, written here from the text of
    section 6, prior N(0, 1e8 I3), measurement update then time update with diag(0, r1, r2).
    Returns (states a(t|t) for t = 2..n-1, prediction errors v, variances F)."""
    x = np.asarray(x, dtype=float)
    y = x[2:]
    n = len(y)
    Z = np.column_stack((np.ones(n), x[1:-1], x[:-2]))
    a = np.zeros(3)
    root = math.sqrt(DIFFUSE) * np.eye(3)                  # P = root @ root.T
    root_q = np.diag([0.0, math.sqrt(r1), math.sqrt(r2)])
    states, errors, variances = np.empty((n, 3)), np.empty(n), np.empty(n)
    pre = np.zeros((4, 4))
    for t in range(n):
        z = Z[t]
        v = y[t] - z @ a
        pre[0, 0] = 1.0                                      # sqrt(H), H = 1
        pre[0, 1:] = z @ root
        pre[1:, 0] = 0.0
        pre[1:, 1:] = root
        post = np.linalg.qr(pre.T, mode="r").T               # pre = post @ (orthogonal), post lower triangular
        if post[0, 0] < 0:
            post[:, 0] = -post[:, 0]
        root_f = post[0, 0]
        a = a + post[1:, 0] * (v / root_f)
        root = post[1:, 1:]
        states[t], errors[t], variances[t] = a, v, root_f * root_f
        root = np.linalg.qr(np.concatenate((root, root_q), axis=1).T, mode="r").T
    return states, errors, variances


def concentrated_loglik(errors, variances, excluded=3):
    v, F = np.asarray(errors[excluded:]), np.asarray(variances[excluded:])
    if not (np.all(np.isfinite(v)) and np.all(np.isfinite(F)) and np.all(F > 0)):
        return math.nan, math.nan
    n_star = len(v)
    sigma2 = math.fsum(v * v / F) / n_star
    loglik = -(n_star / 2) * (math.log(2 * math.pi) + 1 + math.log(sigma2)) - 0.5 * math.fsum(np.log(F))
    return loglik, sigma2


def grid_choice(grid):
    """E3 section 6 step 1: maximum over finite values, ties by smaller r1 + r2, then smaller r1."""
    best = None
    for i, r1 in enumerate(GRID):
        for j, r2 in enumerate(GRID):
            value = grid[i][j]
            if not finite(value):
                continue
            key = (-value, r1 + r2, r1)
            if best is None or key < best[0]:
                best = (key, i, j)
    return None if best is None else (best[1], best[2])


def independent_statistic(extension, kind, x, observed_fit=None):
    """S recomputed from the stored input: (eligible onsets, ineligible onsets, changes, S, extra)."""
    design = DESIGNS[extension]
    extra = {}
    if extension == "e1":
        modulus = rolling_modulus(x, design["window"])
    else:
        fit = observed_fit or {}
        r1, r2 = fit.get("r1"), fit.get("r2")
        if not (finite(r1) and finite(r2)):
            raise ValueError("no usable observed fit")
        states, errors, variances = filtered_states(x, r1, r2)
        loglik, sigma2 = concentrated_loglik(errors, variances)
        extra.update(loglik=loglik, sigma2=sigma2)
        modulus = np.full(len(x), np.nan)
        start = design["first_indicator"]
        modulus[start:] = companion_modulus(states[start - 2:, 1], states[start - 2:, 2])
    if kind == "power":
        onsets = list(design["power_onsets"])
    else:
        onsets = [s for s, _ in episodes(x, design["minimum_run"], design["merge"])]
        if design["first_year"] is not None:
            onsets = [s for s in onsets if design["first_year"] + s not in design["exogenous"]]
    eligible, ineligible, changes = pre_onset(modulus, onsets, design["lookback"])
    S = math.fsum(changes) / len(changes) if changes else None
    return eligible, ineligible, changes, S, extra


# ------------------------------------------------------------------------------------------ reporting

class Report:
    def __init__(self, max_print=25):
        self.problems = []           # integrity problems and disagreements (exit status 1)
        self.notes = []
        self.max_print = max_print
        self.lines = []

    def problem(self, where, message):
        self.problems.append(dict(where=where, message=message))

    def say(self, text=""):
        self.lines.append(text)
        print(text, flush=True)


def sha256_file(path, chunk=1 << 20):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def read_json(path):
    with open(path, "rb") as handle:
        return json.loads(handle.read())


def fmt(value, digits=6):
    if value is None:
        return "undefined"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return ("%." + str(digits) + "g") % value
    return str(value)


# ------------------------------------------------------------------------------------------ parsing

def part_kind(name):
    if name.startswith("x3_size"):
        return "size"
    if name.startswith("x3_power"):
        return "power"
    return None


def declared_coordinates(name):
    match = PART_PATTERNS[0].match(name)
    if match:
        first, last = int(match.group(1)), int(match.group(2))
        return {(0, r) for r in range(first, last)}
    match = PART_PATTERNS[1].match(name)
    if match:
        cell, first, last = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return {(cell, r) for r in range(first, last)}
    return None


def fingerprint(manifest):
    identity = manifest.get("identity") or {}
    return dict(schema=manifest.get("schema"), extension=manifest.get("extension"), mode=manifest.get("mode"),
                master_seed=manifest.get("master_seed"), n_series=manifest.get("n_series"), B=manifest.get("B"),
                settings=manifest.get("settings"), code_sha256=manifest.get("code_sha256"),
                commit=identity.get("commit"), ext_commit=(manifest.get("imported") or {}).get("ext_commit"),
                python=identity.get("python"), packages=identity.get("packages"), gate=manifest.get("gate"),
                prerequisite=(manifest.get("prerequisite") or {}).get("sha256"))


class Context:
    def __init__(self, extension, development, report):
        self.extension = extension
        self.design = DESIGNS[extension]
        self.development = development
        self.report = report
        self.expected_n = N_SERIES
        self.expected_B = B_ATTEMPTS
        self.manifests = {}          # file name -> manifest
        self.entries = []            # one small summary per replicate record
        self.coordinates = {}        # (kind, cell, replicate) -> [file names]
        self.file_rows = []
        self.fits_expected = {}      # relative fits path -> (sha256, where)
        self.record_issue_count = 0
        self.max_s_difference = 0.0
        self.max_loglik_difference = 0.0
        self.max_null_difference = 0.0
        self.s_recomputed = 0
        self.p_recomputed = 0
        self.b_prime = []
        self.prerequisite_sha = set()


def check_manifest(ctx, name, manifest, kind):
    rep, design = ctx.report, ctx.design
    where = name + " manifest"
    if manifest.get("record_type") != "manifest":
        rep.problem(where, "first line is not a manifest")
        return
    expected = dict(extension=ctx.extension, check=kind)
    for key, value in expected.items():
        if manifest.get(key) != value:
            rep.problem(where, "%s is %r, expected %r" % (key, manifest.get(key), value))
    if ctx.development:
        if manifest.get("mode") != "development" or manifest.get("master_seed") == REGISTERED_SEED:
            rep.problem(where, "development verification needs a development manifest (not seed 1927)")
    else:
        checks = dict(mode="registered", master_seed=REGISTERED_SEED, n_series=N_SERIES, B=B_ATTEMPTS,
                      settings=design["settings"], kappas=list(KAPPAS) if kind == "power" else None)
        for key, value in checks.items():
            if manifest.get(key) != value:
                rep.problem(where, "%s is %r, registered design needs %r" % (key, manifest.get(key), value))
        identity = manifest.get("identity") or {}
        if identity.get("python") != "3.12.14":
            rep.problem(where, "interpreter %r, registered runs need 3.12.14" % identity.get("python"))
        if identity.get("dirty") is not False:
            rep.problem(where, "research tree not recorded clean")
        if (manifest.get("lock") or {}).get("satisfied") is not True:
            rep.problem(where, "research lock not recorded as satisfied")
        gate = manifest.get("gate") or {}
        if gate.get("tag") != design["tag"] or gate.get("registration_id") != design["registration_id"]:
            rep.problem(where, "gate record names %r/%r, expected %s/%s" % (
                gate.get("tag"), gate.get("registration_id"), design["tag"], design["registration_id"]))
        if ctx.extension == "e3" and not (manifest.get("prerequisite") or {}).get("sha256"):
            rep.problem(where, "no prerequisite record in the manifest")
    if ctx.extension == "e3" and (manifest.get("prerequisite") or {}).get("sha256"):
        ctx.prerequisite_sha.add(manifest["prerequisite"]["sha256"])


def check_replicate(ctx, name, manifest, kind, record, line_number):
    """Per-record checks; returns the small entry used for the summaries."""
    design, extension = ctx.design, ctx.extension
    issues = []
    cell, replicate = record.get("cell_index"), record.get("replicate")
    where = "%s line %d (cell %r, replicate %r)" % (name, line_number, cell, replicate)
    if type(cell) is not int or type(replicate) is not int:
        issues.append("coordinates are not integers")
    expected_name = "size" if kind == "size" else "power_%s" % cell
    if record.get("cell") != expected_name:
        issues.append("cell name %r, expected %r" % (record.get("cell"), expected_name))
    for field in ("mode", "master_seed", "B", "settings", "code_sha256"):
        if record.get(field) != manifest.get(field):
            issues.append("%s differs from the file's manifest" % field)
    if record.get("registered") is not (not ctx.development):
        issues.append("registered flag is %r" % record.get("registered"))
    kappas = manifest.get("kappas") or list(KAPPAS)
    if kind == "power" and type(cell) is int and 0 <= cell < len(kappas) and record.get("kappa") != kappas[cell]:
        issues.append("kappa %r does not match cell %d" % (record.get("kappa"), cell))
    status = record.get("status")
    S, p = record.get("S"), record.get("p_value")
    runner_valid = (status == "ok" and isinstance(p, (int, float)) and isinstance(S, (int, float))
                    and math.isfinite(p) and math.isfinite(S) and 0 <= p <= 1)
    B = ctx.expected_B
    values = record.get("input")
    x = None
    if values is None:
        if status != "generation_failed" or record.get("input_sha256") is not None:
            issues.append("no input but not a generation failure")
    else:
        try:
            x = np.asarray(values, dtype=float)
        except (TypeError, ValueError):
            issues.append("input is not numeric")
        if x is not None:
            if x.ndim != 1 or len(x) != design["n_growth"] or not np.all(np.isfinite(x)):
                issues.append("input has length %s or non-finite values (expected %d)" % (x.shape, design["n_growth"]))
            elif hashlib.sha256(x.astype("<f8").tobytes()).hexdigest() != record.get("input_sha256"):
                issues.append("stored input does not match input_sha256")
    comparison = record.get("comparison")
    p_exact = None
    if comparison is None:
        if status == "ok":
            issues.append("status ok without a comparison")
    else:
        attempts = comparison.get("attempts") or []
        statuses = [a.get("status") for a in attempts]
        counts = dict(retained=statuses.count("retained"), no_episode=statuses.count("no_eligible_episode"),
                      failed=statuses.count("failed"))
        other = len(statuses) - sum(counts.values())
        if other:
            issues.append("%d attempts with an unknown status" % other)
        if [a.get("number") for a in attempts] != list(range(len(attempts))):
            issues.append("attempt numbers are not 0..%d in order" % (len(attempts) - 1))
        if comparison.get("requested") != B or record.get("surrogate_requested") != B:
            issues.append("requested %r, expected %d" % (comparison.get("requested"), B))
        if comparison.get("attempted") != len(attempts):
            issues.append("attempted %r but %d attempts stored" % (comparison.get("attempted"), len(attempts)))
        if (comparison.get("retained"), comparison.get("no_episode"), comparison.get("failed")) != (
                counts["retained"], counts["no_episode"], counts["failed"]):
            issues.append("stored retained/no_episode/failed differ from the attempts")
        if comparison.get("attempted") != (comparison.get("retained") or 0) + (comparison.get("no_episode") or 0) + (
                comparison.get("failed") or 0):
            issues.append("attempted != retained + no_eligible + failed")
        for field, key in (("surrogate_attempted", "attempted"), ("surrogate_retained", "retained"),
                           ("surrogate_no_episode", "no_episode"), ("surrogate_failed", "failed"),
                           ("surrogate_exceedances", "exceedances")):
            if record.get(field) != comparison.get(key):
                issues.append("%s differs from the comparison" % field)
        observed = comparison.get("observed") or {}
        s_obs = observed.get("mean_change")
        changes = observed.get("changes") or []
        eligible = observed.get("eligible_onsets") or []
        if comparison.get("status") != "observed_not_estimable":
            if len(changes) != len(eligible) or not changes:
                issues.append("observed changes and eligible onsets disagree")
            elif not (finite(s_obs) and abs(math.fsum(changes) / len(changes) - s_obs) <= STAT_TOL):
                issues.append("observed S is not the mean of its changes")
            if kind == "power" and list(eligible) != list(design["power_onsets"]):
                issues.append("observed eligible onsets %r differ from the imposed onsets" % (eligible,))
            if kind == "size":
                bad = [r for r in eligible if r < design["first_eligible"] or (
                    design["first_year"] is not None and design["first_year"] + r in design["exogenous"])]
                if bad:
                    issues.append("observed eligible onsets break the rules: %r" % bad)
        if status == "ok" and not (S == s_obs and p == comparison.get("p_value")):
            issues.append("record S/p differ from the comparison")
        if extension == "e3" and status == "filter_agreement_failed":
            pass
        elif status != comparison.get("status"):
            issues.append("record status %r differs from comparison status %r" % (status, comparison.get("status")))
        retained = [a for a in attempts if a.get("status") == "retained"]
        for a in retained:
            stat, parts, dates = a.get("statistic"), a.get("changes") or [], a.get("eligible_onsets") or []
            if not finite(stat) or not parts or len(parts) != len(dates) or abs(
                    math.fsum(parts) / len(parts) - stat) > STAT_TOL:
                issues.append("attempt %r: statistic is not the mean of its changes" % a.get("number"))
                break
            if kind == "power":
                if list(dates) != list(design["power_onsets"]):
                    issues.append("attempt %r: onsets differ from the imposed onsets" % a.get("number"))
                    break
            elif any(r < design["first_eligible"] or (design["first_year"] is not None and
                                                        design["first_year"] + r in design["exogenous"])
                     for r in dates):
                issues.append("attempt %r: an eligible onset breaks the rules" % a.get("number"))
                break
        if kind == "power" and counts["no_episode"]:
            issues.append("fixed-date comparison with %d no-episode draws" % counts["no_episode"])
        if comparison.get("status") in ("ok", "invalid_surrogate_failure", "no_retained_surrogates"):
            if counts["failed"]:
                if comparison.get("p_value") is not None or comparison.get("status") != "invalid_surrogate_failure":
                    issues.append("a surrogate failure did not invalidate p")
            elif not retained:
                if comparison.get("p_value") is not None or comparison.get("status") != "no_retained_surrogates":
                    issues.append("no retained draws but p or status set")
            else:
                if len(attempts) != B:
                    issues.append("%d attempts, expected %d" % (len(attempts), B))
                K = sum(1 for a in retained if a["statistic"] >= s_obs)
                p_exact = Fraction(1 + K, len(retained) + 1)
                ctx.p_recomputed += 1
                ctx.b_prime.append(len(retained))
                if comparison.get("exceedances") != K:
                    issues.append("exceedances %r, recomputed %d" % (comparison.get("exceedances"), K))
                if comparison.get("p_value") != float(p_exact):
                    issues.append("p %r, recomputed (1+K)/(B'+1) = %d/%d" % (
                        comparison.get("p_value"), p_exact.numerator, p_exact.denominator))
                if not close(comparison.get("p_grid_spacing"), 1 / (len(retained) + 1)):
                    issues.append("grid spacing differs from 1/(B'+1)")
                if not close(record.get("surrogate_exceedance_rate"), K / len(retained)):
                    issues.append("surrogate_exceedance_rate differs from K/B'")
                wil = record.get("surrogate_exceedance_wilson") or [None, None]
                lo, hi = wilson(K, len(retained))
                if not (close(wil[0], lo) and close(wil[1], hi)):
                    issues.append("surrogate_exceedance_wilson differs from Wilson(K, B')")
        null = comparison.get("null_model")
        if x is not None and null and len(x) == design["n_growth"]:
            phi1, phi2, intercept, residuals = ols_ar2(x)
            coefficients = null.get("coefficients") or [None, None]
            diff = max(abs(phi1 - coefficients[0]), abs(phi2 - coefficients[1]), abs(intercept - null.get("intercept")))
            ctx.max_null_difference = max(ctx.max_null_difference, diff)
            if diff > 1e-9:
                issues.append("fitted null differs from the full-sample OLS by %.3g" % diff)
            if list(null.get("initial") or []) != [float(x[0]), float(x[1])]:
                issues.append("fitted null does not start from the observed first pair")
            stored = null.get("residuals") or []
            if len(stored) != len(x) - 2 or abs(math.fsum(stored)) > 1e-9 * len(stored):
                issues.append("residuals are not the %d centred residuals" % (len(x) - 2))
            if not (finite(null.get("modulus")) and null["modulus"] < 1):
                issues.append("fitted null is not strictly stable")
        # independent recomputation of the observed statistic from the stored input
        if x is not None and comparison.get("status") != "observed_not_estimable" and len(x) == design["n_growth"]:
            try:
                fit = record.get("observed_fit") if extension == "e3" else None
                mine_eligible, mine_ineligible, mine_changes, mine_S, extra = independent_statistic(
                    extension, kind, x, fit)
                ctx.s_recomputed += 1
                tolerance = S_TOL_E1 if extension == "e1" else S_TOL_E3
                if list(mine_eligible) != list(eligible):
                    issues.append("recomputed eligible onsets %r differ from stored %r" % (mine_eligible, eligible))
                elif mine_S is None or not finite(s_obs):
                    issues.append("recomputed S not estimable")
                else:
                    diff = max([abs(mine_S - s_obs)] + [abs(a - b) for a, b in zip(mine_changes, changes)])
                    ctx.max_s_difference = max(ctx.max_s_difference, diff)
                    if diff > tolerance:
                        issues.append("recomputed S differs by %.3g (tolerance %g)" % (diff, tolerance))
                if kind == "size" and list(mine_ineligible) != list(observed.get("ineligible_onsets") or []):
                    issues.append("recomputed ineligible onsets differ")
                if extension == "e3" and fit:
                    if not close(extra.get("loglik"), fit.get("loglik"), LOGLIK_TOL_E3, 0.0):
                        issues.append("l(r) at the accepted estimate differs by %.3g" % abs(
                            extra.get("loglik") - fit.get("loglik")))
                    else:
                        ctx.max_loglik_difference = max(ctx.max_loglik_difference,
                                                        abs(extra["loglik"] - fit["loglik"]))
                    if not close(extra.get("sigma2"), fit.get("sigma2"), 0.0, 1e-6):
                        issues.append("sigma2_hat differs from the recomputed value")
            except (ValueError, FloatingPointError, np.linalg.LinAlgError, TypeError, KeyError) as error:
                issues.append("independent recomputation failed: %s" % error)
    if extension == "e3":
        issues += check_e3_record(ctx, name, manifest, record, kind)
    # validity readings
    strict_valid = bool(runner_valid and not issues and p_exact is not None and float(p_exact) == p)
    rejected = bool(runner_valid and p <= 0.05)
    rejected_exact = bool(strict_valid and p_exact <= ALPHA)
    if issues:
        ctx.record_issue_count += 1
        for issue in issues:
            ctx.report.problem(where, issue)
    return dict(kind=kind, cell=cell, replicate=replicate, status=status, S=S if runner_valid else None, p=p,
                registered_flag=record.get("registered"),
                valid=runner_valid, strict_valid=strict_valid, rejected=rejected, rejected_exact=rejected_exact,
                file=name, issues=len(issues))


def check_e3_record(ctx, name, manifest, record, kind):
    """E3 extras: agreement test on this fixture, the observed fit record, retained fits."""
    issues = []
    agreement = record.get("filter_agreement")
    settings = manifest.get("settings") or {}
    if settings.get("check_agreement"):
        if not agreement:
            issues.append("no filter agreement record")
        else:
            if not (agreement.get("passed") is True and finite(agreement.get("max_state_difference"))
                    and agreement["max_state_difference"] <= STATE_TOL_E3
                    and finite(agreement.get("max_loglik_difference"))
                    and agreement["max_loglik_difference"] <= LOGLIK_TOL_E3
                    and agreement.get("mismatched_failures") == 0 and agreement.get("points") == 256):
                issues.append("section 6 agreement test not met on this fixture: %r" % {
                    k: agreement.get(k) for k in ("points", "max_state_difference", "max_loglik_difference",
                                                  "mismatched_failures", "passed")})
    fit = record.get("observed_fit")
    if record.get("status") == "ok":
        if not fit or fit.get("status") != "ok":
            issues.append("status ok without an ok observed fit")
        else:
            grid = fit.get("grid_loglik")
            if not grid or len(grid) != 16 or any(len(row) != 16 for row in grid):
                issues.append("observed fit grid is not 16 x 16")
            else:
                choice = grid_choice(grid)
                gm = fit.get("grid_max") or {}
                if choice is None or list(gm.get("index") or []) != list(choice):
                    issues.append("grid maximum %r, recomputed %r" % (gm.get("index"), choice))
                elif list(gm.get("r") or []) != [GRID[choice[0]], GRID[choice[1]]]:
                    issues.append("grid maximum r differs from the grid values")
            refinement = fit.get("refinement")
            gm = fit.get("grid_max") or {}
            if refinement is None:
                expected, r_hat = "grid", list(gm.get("r") or [])
            else:
                ref_l, grid_ref = refinement.get("loglik"), gm.get("loglik_reference")
                better = finite(ref_l) and (grid_ref is None or ref_l >= grid_ref)
                expected = "refined" if better else "grid"
                r_hat = list(refinement.get("r") or []) if better else list(gm.get("r") or [])
                if [v for v in refinement.get("log10") or [] if not (-10.0 <= v <= 0.0)]:
                    issues.append("refined point outside the log10 bounds [-10, 0]")
            if fit.get("accepted") != expected or [fit.get("r1"), fit.get("r2")] != r_hat:
                issues.append("accepted %r at %r; the acceptance rule gives %r at %r" % (
                    fit.get("accepted"), [fit.get("r1"), fit.get("r2")], expected, r_hat))
            if finite(fit.get("sigma2")) and finite(fit.get("r1")) and finite(fit.get("r2")):
                if fit.get("q1") != fit["sigma2"] * fit["r1"] or fit.get("q2") != fit["sigma2"] * fit["r2"]:
                    issues.append("q_hat is not sigma2_hat * r_hat")
            if fit.get("grid_point_failure") != settings.get("grid_point_failure"):
                issues.append("observed fit made under another S6 reading")
    retention = settings.get("retention")
    if retention == "all_fits" and record.get("comparison") is not None:
        path, digest = record.get("surrogate_fits_file"), record.get("surrogate_fits_sha256")
        if record.get("surrogate_fits") is not None or not path or not digest:
            issues.append("retained fits not stored as a compressed file")
        else:
            ctx.fits_expected[path] = (digest, name, record.get("cell"), record.get("replicate"),
                                       record.get("surrogate_fits_count"), record.get("input_sha256"))
            if record.get("surrogate_fits_count") != ctx.expected_B:
                issues.append("surrogate_fits_count %r, expected %d" % (record.get("surrogate_fits_count"),
                                                                        ctx.expected_B))
    if manifest.get("prerequisite") and record.get("prerequisite_sha256") != manifest["prerequisite"].get("sha256"):
        issues.append("prerequisite_sha256 differs from the manifest")
    return issues


def parse_part(ctx, path):
    """Stream one part file: hash it, check every line, return its row for the report."""
    rep = ctx.report
    name = path.name
    kind = part_kind(name)
    digest = hashlib.sha256()
    row = dict(file=name, kind=kind, bytes=0, lines=0, manifest=False, sessions=0, replicates=0, problems=0,
               truncated=False, sha256=None)
    before = len(rep.problems)
    manifest = None
    declared = declared_coordinates(name)
    seen = set()
    with open(path, "rb") as handle:
        number = 0
        for raw in handle:
            number += 1
            digest.update(raw)
            row["bytes"] += len(raw)
            complete = raw.endswith(b"\n")
            if not raw.strip():
                rep.problem("%s line %d" % (name, number), "blank line")
                continue
            try:
                obj = json.loads(raw)
            except ValueError as error:
                if not complete:
                    row["truncated"] = True
                    rep.problem("%s line %d" % (name, number), "truncated last line (no newline, not valid JSON)")
                else:
                    rep.problem("%s line %d" % (name, number), "not valid JSON: %s" % str(error)[:120])
                continue
            if not complete:
                row["truncated"] = True
                rep.problem("%s line %d" % (name, number), "last line has no trailing newline")
            if not isinstance(obj, dict):
                rep.problem("%s line %d" % (name, number), "line is not a JSON object")
                continue
            kind_of_line = obj.get("record_type")
            if number == 1:
                if kind_of_line != "manifest":
                    rep.problem(name, "does not start with a manifest line")
                else:
                    manifest = obj
                    row["manifest"] = True
                    ctx.manifests[name] = manifest
                    check_manifest(ctx, name, manifest, kind)
                    if ctx.development:
                        ctx.expected_n, ctx.expected_B = manifest.get("n_series"), manifest.get("B")
                continue
            if kind_of_line == "session":
                row["sessions"] += 1
                continue
            if kind_of_line != "replicate":
                rep.problem("%s line %d" % (name, number), "unexpected record type %r" % kind_of_line)
                continue
            if manifest is None:
                rep.problem("%s line %d" % (name, number), "replicate record before any manifest")
                continue
            row["replicates"] += 1
            entry = check_replicate(ctx, name, manifest, kind, obj, number)
            key = (kind, entry["cell"], entry["replicate"])
            ctx.coordinates.setdefault(key, []).append(name)
            seen.add((entry["cell"], entry["replicate"]))
            ctx.entries.append(entry)
    row["lines"] = number
    row["sha256"] = digest.hexdigest()
    if declared is not None and seen != declared:
        rep.problem(name, "records do not match the file name's range: %d missing, %d outside" % (
            len(declared - seen), len(seen - declared)))
    row["problems"] = len(rep.problems) - before
    return row


# ------------------------------------------------------------------------------------ whole-directory checks

def coverage(ctx, kinds=("size", "power")):
    rep = ctx.report
    n = ctx.expected_n
    expected = ({("size", 0, r) for r in range(n)} if "size" in kinds else set()) | (
        {("power", c, r) for c in range(len(KAPPAS)) for r in range(n)} if "power" in kinds else set())
    present = set(ctx.coordinates)
    duplicates = sorted(k for k, files in ctx.coordinates.items() if len(files) > 1)
    missing = sorted(expected - present)
    extra = sorted(present - expected, key=str)
    for key in duplicates:
        rep.problem("coordinates", "%s cell %s replicate %s appears %d times (%s)" % (
            key[0], key[1], key[2], len(ctx.coordinates[key]), ", ".join(ctx.coordinates[key])))
    if missing:
        rep.problem("coordinates", "%d registered coordinates missing, first %s" % (len(missing), missing[:5]))
    if extra:
        rep.problem("coordinates", "%d records outside the registered design, first %s" % (len(extra), extra[:5]))
    return dict(expected=len(expected), present=len(present), missing=len(missing), duplicates=len(duplicates),
                extra=len(extra))


def compare_manifests(ctx):
    rep = ctx.report
    prints = {}
    for name, manifest in ctx.manifests.items():
        prints.setdefault(part_kind(name), []).append((name, fingerprint(manifest)))
    reference = None
    for kind, items in prints.items():
        for name, fp in items:
            if reference is None:
                reference = (name, fp)
                continue
            differing = sorted(k for k in fp if fp[k] != reference[1][k])
            if differing:
                rep.problem(name, "manifest differs from %s in %s" % (reference[0], ", ".join(differing)))
    return reference[1] if reference else None


def hash_directory(ctx, root_ext, known, include=None):
    """SHA-256 of every file under <dir>/<EXT> (part files reuse their parse-time hash). `include` (interim
    runs) limits hashing to the files of the parts read, so that no file another process is still writing
    is opened; temporary *.tmp files are never opened."""
    hashes = {}
    for folder, _, files in os.walk(root_ext):
        for file in files:
            path = Path(folder) / file
            relative = path.relative_to(root_ext).as_posix()
            if file.endswith(".tmp") or (include is not None and not include(relative)):
                continue
            if relative in known:
                hashes[relative] = known[relative]
            else:
                hashes[relative] = sha256_file(path)
    return hashes


def check_output_hashes(ctx, directory, root_ext, hashes, include=None):
    rep = ctx.report
    ext = ctx.design["name"]
    listing_path = root_ext / "OUTPUT_SHA256.json"
    result = dict(listed=0, matched=0, mismatched=[], missing=[], unlisted=[], txt_consistent=None,
                  total_bytes_listed=None, present=listing_path.is_file())
    if not listing_path.is_file():
        rep.problem("OUTPUT_SHA256.json", "absent")
        return result
    listing = read_json(listing_path)
    outputs = listing.get("outputs") or []
    result.update(listed=len(outputs), total_bytes_listed=listing.get("total_bytes"),
                  created_utc=listing.get("created_utc"))
    if listing.get("files") != len(outputs):
        rep.problem("OUTPUT_SHA256.json", "files = %r but %d outputs listed" % (listing.get("files"), len(outputs)))
    if listing.get("total_bytes") != sum(o.get("bytes", 0) for o in outputs):
        rep.problem("OUTPUT_SHA256.json", "total_bytes differs from the sum of the listed sizes")
    prefix = "runs/extensions/%s/" % ext
    listed_relative = set()
    for output in outputs:
        path = output.get("path", "")
        relative = path[len(prefix):] if path.startswith(prefix) else None
        if relative is None:
            rep.problem("OUTPUT_SHA256.json", "path outside %s: %s" % (prefix, path))
            continue
        listed_relative.add(relative)
        if include is not None and not include(relative):
            result["not_checked"] = result.get("not_checked", 0) + 1
            continue
        if relative not in hashes:
            result["missing"].append(path)
            rep.problem("OUTPUT_SHA256.json", "listed file absent: %s" % path)
            continue
        digest, size = hashes[relative]
        if digest != output.get("sha256") or size != output.get("bytes"):
            result["mismatched"].append(path)
            rep.problem("OUTPUT_SHA256.json", "hash or size differs now: %s" % path)
        else:
            result["matched"] += 1
    for relative in sorted(hashes):
        if relative in ("OUTPUT_SHA256.json", "OUTPUT_SHA256.txt"):
            continue
        if relative not in listed_relative:
            result["unlisted"].append(relative)
            rep.problem("OUTPUT_SHA256.json", "file present but not listed: %s" % relative)
    text_path = root_ext / "OUTPUT_SHA256.txt"
    if text_path.is_file():
        with open(text_path, "rb") as handle:
            text = handle.read().decode("utf-8")
        expected = "".join("%s  %s\n" % (o.get("sha256"), o.get("path")) for o in outputs)
        result["txt_consistent"] = text.replace("\r\n", "\n") == expected
        if not result["txt_consistent"]:
            rep.problem("OUTPUT_SHA256.txt", "does not list the same hashes as OUTPUT_SHA256.json")
    else:
        rep.problem("OUTPUT_SHA256.txt", "absent")
    return result


def check_fits(ctx, root_ext, hashes, deep):
    rep = ctx.report
    result = dict(expected=len(ctx.fits_expected), present=0, matched=0, deep_checked=0)
    for relative, (digest, where, cell, replicate, count, input_sha) in sorted(ctx.fits_expected.items()):
        if relative not in hashes:
            rep.problem(where, "compressed fits file absent: %s" % relative)
            continue
        result["present"] += 1
        if hashes[relative][0] != digest:
            rep.problem(where, "compressed fits file differs from its recorded SHA-256: %s" % relative)
            continue
        result["matched"] += 1
        if deep:
            with gzip.open(root_ext / relative, "rb") as handle:
                payload = json.loads(handle.read())
            fits = payload.get("surrogate_fits") or {}
            if (payload.get("cell"), payload.get("replicate"), payload.get("input_sha256")) != (cell, replicate, input_sha) \
                    or len(fits) != count or payload.get("manifest") != ctx.manifests.get(where):
                rep.problem(where, "compressed fits content does not match its record: %s" % relative)
            result["deep_checked"] += 1
    return result


def check_prerequisite(ctx, root_ext, hashes, reference):
    """E3 section 11 prerequisites, from the record the driver made (numbers checked against tolerances)."""
    rep = ctx.report
    path = root_ext / "x3_prerequisite.jsonl"
    out = dict(present=path.is_file(), clauses={})
    if not path.is_file():
        rep.problem("x3_prerequisite.jsonl", "absent")
        return out
    lines = []
    with open(path, "rb") as handle:
        for raw in handle:
            if raw.strip():
                lines.append(json.loads(raw))
    manifest = lines[0] if lines else {}
    records = [l for l in lines[1:] if l.get("record_type") == "prerequisite"]
    digest = hashes.get("x3_prerequisite.jsonl", (None, None))[0]
    out["sha256"] = digest
    if manifest.get("record_type") != "manifest" or manifest.get("check") != "prerequisite" or len(records) != 1:
        rep.problem("x3_prerequisite.jsonl", "must hold one manifest and exactly one prerequisite record")
        return out
    record = records[0]
    if ctx.prerequisite_sha and ctx.prerequisite_sha != {digest}:
        rep.problem("x3_prerequisite.jsonl", "its SHA-256 differs from the one the part manifests record")
    if reference and (manifest.get("code_sha256"), (manifest.get("identity") or {}).get("commit")) != (
            reference.get("code_sha256"), reference.get("commit")):
        rep.problem("x3_prerequisite.jsonl", "made by other code or at another commit than the parts")
    if not ctx.development and (manifest.get("mode"), manifest.get("master_seed"), record.get("registered")) != (
            "registered", REGISTERED_SEED, True):
        rep.problem("x3_prerequisite.jsonl", "not a registered prerequisite record")

    def max_difference(block):
        try:
            return max(abs(a - b) for a, b in zip(block["final_state"], block["least_squares"]))
        except (KeyError, TypeError, ValueError):
            return None

    r0 = record.get("r0") or {}
    d0 = max_difference(r0)
    r0_pass = bool(d0 is not None and d0 <= 1e-6 and r0.get("passed") is True)
    out["clauses"]["r0"] = dict(max_abs_difference=d0, recorded=r0.get("max_abs_difference"),
                                prior_variance=r0.get("prior_variance"), passed=r0_pass)

    def agreement_ok(block):
        return bool(block and block.get("points") == 256 and finite(block.get("max_state_difference"))
                    and block["max_state_difference"] <= STATE_TOL_E3 and finite(block.get("max_loglik_difference"))
                    and block["max_loglik_difference"] <= LOGLIK_TOL_E3 and block.get("mismatched_failures") == 0
                    and block.get("passed") is True)

    agreement = record.get("agreement") or {}
    at11 = record.get("at11") or {}
    reference_at11, batched_at11 = at11.get("reference_at11") or {}, at11.get("batched_at11") or {}
    dr, db = max_difference(reference_at11), max_difference(batched_at11)
    out["clauses"]["agreement_prerequisite_series"] = dict(
        max_state_difference=agreement.get("max_state_difference"),
        max_loglik_difference=agreement.get("max_loglik_difference"),
        mismatched_failures=agreement.get("mismatched_failures"), points=agreement.get("points"),
        passed=agreement_ok(agreement))
    out["clauses"]["agreement_at11_fixture"] = dict(
        max_state_difference=(at11.get("agreement") or {}).get("max_state_difference"),
        max_loglik_difference=(at11.get("agreement") or {}).get("max_loglik_difference"),
        passed=agreement_ok(at11.get("agreement")))
    out["clauses"]["at11"] = dict(reference_max_abs_difference=dr, batched_max_abs_difference=db,
                                  fixture=(at11.get("fixture") or {}).get("year_value_sha256"),
                                  passed=bool(dr is not None and db is not None and dr <= 1e-6 and db <= 1e-6
                                              and reference_at11.get("passed") is True
                                              and batched_at11.get("passed") is True))
    recorded_all = record.get("passed") is True
    recomputed_all = all(c["passed"] for c in out["clauses"].values())
    out["recorded_passed"], out["recomputed_passed"] = recorded_all, recomputed_all
    if recorded_all != recomputed_all:
        rep.problem("x3_prerequisite.jsonl", "recorded passed=%r but the numbers give %r" % (recorded_all,
                                                                                            recomputed_all))
    return out


def check_f2(directory):
    stage = directory / "stages" / "E3_F2.json"
    log = directory / "logs" / "e3_F2_test_foundations.stdout.txt"
    out = dict(stage_marker=stage.is_file(), log=None, passed=None)
    if log.is_file():
        with open(log, "rb") as handle:
            text = handle.read().decode("utf-8", "replace")
        tail = [line for line in text.splitlines() if line.strip()][-1:] or [""]
        out["log"] = tail[0][:200]
        out["passed"] = bool(re.search(r"\b\d+ passed\b", text)) and not re.search(r"\b\d+ (failed|error)", text)
    return out


def compare_runner(ctx, root_ext, kind, mine, power, part_rows):
    """Every figure of the runner's x3_<kind>_summary.json against the recomputation."""
    rep = ctx.report
    path = root_ext / ("x3_%s_summary.json" % kind)
    out = dict(file=path.name, present=path.is_file(), compared=0, differences=[], max_float_difference=0.0)
    if not path.is_file():
        rep.problem(path.name, "absent")
        return out
    data = read_json(path)
    summary = data.get("summary") or {}

    def same(label, theirs, ours, exact):
        out["compared"] += 1
        if exact:
            ok = theirs == ours
        elif isinstance(theirs, (list, tuple)) and isinstance(ours, (list, tuple)):
            ok = len(theirs) == len(ours) and all(close(a, b) for a, b in zip(theirs, ours))
            if ok:
                for a, b in zip(theirs, ours):
                    if a is not None and b is not None:
                        out["max_float_difference"] = max(out["max_float_difference"], abs(a - b))
        else:
            ok = close(theirs, ours)
            if ok and theirs is not None and ours is not None:
                out["max_float_difference"] = max(out["max_float_difference"], abs(theirs - ours))
        if not ok:
            out["differences"].append(dict(field=label, runner=theirs, verifier=ours))
            rep.problem(path.name, "%s: runner %r, verifier %r" % (label, theirs, ours))

    exact_fields = ("requested", "attempted", "valid", "rejected", "unfinished", "failures")
    float_fields = ("accounting_bounds", "valid_only_rate", "rate", "rate_se", "rate_wilson", "mean_S", "mean_S_se")
    cells = [summary.get("cell") or {}] if kind == "size" else list(summary.get("cells") or [])
    if len(cells) != len(mine):
        rep.problem(path.name, "%d cells, verifier has %d" % (len(cells), len(mine)))
    for index, (theirs, ours) in enumerate(zip(cells, mine)):
        label = "cell" if kind == "size" else "cells[%d]" % index
        for field in exact_fields:
            same("%s.%s" % (label, field), theirs.get(field), ours[field], True)
        for field in float_fields:
            same("%s.%s" % (label, field), theirs.get(field), ours[field], False)
        if kind == "power":
            same("%s.kappa" % label, theirs.get("kappa"), ours["kappa"], True)
    registered = ctx.registered_design
    if kind == "size":
        same("bounds", list(summary.get("bounds") or []), [0.02, 0.09], True)
        same("registered_design", summary.get("registered_design"), registered, True)
        same("passed", summary.get("passed"), bool(registered and ctx.size_clause_pass), True)
    else:
        adjacent = summary.get("adjacent_comparisons") or []
        if len(adjacent) != len(power["adjacent"]):
            rep.problem(path.name, "%d adjacent comparisons, verifier has %d" % (len(adjacent), len(power["adjacent"])))
        for index, (theirs, ours) in enumerate(zip(adjacent, power["adjacent"])):
            for field in ("left_kappa", "right_kappa"):
                same("adjacent[%d].%s" % (index, field), theirs.get(field), ours[field], True)
            for field in ("difference", "standard_error"):
                same("adjacent[%d].%s" % (index, field), theirs.get(field), ours[field], False)
            same("adjacent[%d].decrease_flag" % index, theirs.get("decrease_flag"), ours["decrease_flag"], True)
        same("decrease_flags", summary.get("decrease_flags"), power["flags_exact"], True)
        same("D80", summary.get("D80"), power["D80"], False)
        same("kappa80", summary.get("kappa80"), power["kappa80"], False)
        crossing = summary.get("crossing")
        mine_crossing = power["crossing"]
        if (crossing is None) != (mine_crossing is None) or (crossing and (
                crossing.get("left"), crossing.get("right")) != (mine_crossing["left"], mine_crossing["right"])):
            same("crossing", crossing, mine_crossing, True)
        elif crossing:
            same("crossing.weight", crossing.get("weight"), mine_crossing["weight"], False)
        same("registered_design", summary.get("registered_design"), registered, True)
        same("passed", summary.get("passed"), bool(registered and power["all_valid"] and not any(power["flags_exact"])),
             True)
    inputs = data.get("inputs") or []
    by_name = {row["file"]: row for row in part_rows if row["kind"] == kind}
    names = set()
    for item in inputs:
        base = Path(str(item.get("path", ""))).name
        names.add(base)
        row = by_name.get(base)
        if row is None:
            rep.problem(path.name, "summarises a file the verifier did not read: %s" % base)
            continue
        same("inputs[%s].sha256" % base, item.get("sha256"), row["sha256"], True)
        same("inputs[%s].records" % base, item.get("records"), row["replicates"], True)
    for base in sorted(set(by_name) - names):
        rep.problem(path.name, "does not summarise the part file %s" % base)
    manifest = data.get("manifest") or {}
    out["runner_manifest"] = dict(created_utc=manifest.get("created_utc"), mode=manifest.get("mode"),
                                  commit=(manifest.get("identity") or {}).get("commit"),
                                  python=(manifest.get("identity") or {}).get("python"))
    return out


def check_stage_and_log(ctx, directory, size, power_cells, power):
    rep = ctx.report
    ext = ctx.design["name"]
    out = dict(headline=None, log=None)
    marker = directory / "stages" / ("%s_summaries.json" % ext)
    if marker.is_file():
        headline = read_json(marker).get("headline") or {}
        ours = dict(size_rate=size["rate"], size_valid=size["valid"], size_failures=size["failures"],
                    power_rates=[c["rate"] for c in power_cells], power_valid=[c["valid"] for c in power_cells],
                    decrease_flags=power["flags_exact"], D80=power["D80"],
                    size_passed=bool(ctx.registered_design and ctx.size_clause_pass),
                    power_passed=bool(ctx.registered_design and power["all_valid"] and not any(power["flags_exact"])))
        differences = []
        for key, value in ours.items():
            theirs = headline.get(key)
            ok = close(theirs, value) if isinstance(value, float) else theirs == value
            if not ok:
                differences.append(key)
                rep.problem(marker.name, "%s: runner %r, verifier %r" % (key, theirs, value))
        out["headline"] = dict(file=marker.name, compared=len(ours), differences=differences)
    else:
        rep.problem("stages", "%s absent" % marker.name)
    for name in ("parts", "hashes"):
        path = directory / "stages" / ("%s_%s.json" % (ext, name))
        out["stage_%s" % name] = read_json(path) if path.is_file() else None
    log = directory / "logs" / "run_log.jsonl"
    if log.is_file():
        parts, other = {}, {}
        with open(log, "rb") as handle:
            for raw in handle:
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                part = str(event.get("part", ""))
                if part.startswith(ctx.extension + "/") and event.get("event") in ("start", "end"):
                    info = parts.setdefault(part, dict(starts=0, exits=[]))
                    if event["event"] == "start":
                        info["starts"] += 1
                    else:
                        info["exits"].append(event.get("exit"))
                elif part.startswith(ctx.extension + "_") and event.get("event") == "end":
                    other[part] = event.get("exit")
                elif event.get("event") == "hashed" and event.get("extension") == ctx.extension:
                    other["hashed"] = dict(files=event.get("files"), total_bytes=event.get("total_bytes"))
        failed = sorted(p for p, info in parts.items() if not info["exits"] or info["exits"][-1] != 0)
        out["log"] = dict(parts=len(parts), attempts=sum(i["starts"] for i in parts.values()),
                          all_final_exits_zero=not failed, other=other,
                          resumed=sorted(p for p, info in parts.items() if info["starts"] > 1))
        if failed:
            rep.problem("run_log.jsonl", "parts whose last attempt did not exit 0: %s" % failed)
    return out


# ------------------------------------------------------------------------------------------ prereg quotes

def verify_quotes(clone):
    out = {}
    for group in CLAUSES.values():
        for key, (file, section, text) in group.items():
            path = clone / file
            if not path.is_file():
                out[file + ": " + key] = None
                continue
            with open(path, "rb") as handle:
                content = handle.read().decode("utf-8")
            out[file + ": " + key] = text in content
    return out


# ------------------------------------------------------------------------------------------ main

def main(argv=None):
    try:
        payload = verify(argv)
    except UsageError as error:
        print(str(error), file=sys.stderr)
        return 2
    return payload["exit_status"]


class UsageError(Exception):
    pass


def verify(argv=None):
    """Run every check; print the report; return the JSON payload (also written to --report)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--extension", required=True, choices=["e1", "e3"])
    parser.add_argument("--dir", required=True, help="the runs/extensions directory of the research clone")
    parser.add_argument("--report", help="write a JSON report here (outside the research clone)")
    parser.add_argument("--development", action="store_true",
                        help="verify a development run (sizes from its manifest; the registered seed is refused)")
    parser.add_argument("--deep-fits", action="store_true", help="E3: also decompress every retained-fits file")
    parser.add_argument("--max-print", type=int, default=25, help="problems printed in full (all go to --report)")
    parser.add_argument("--only", choices=["size", "power"],
                        help="interim use while the other check still runs: read only these part files; the other "
                             "check, the runner's summaries of it and the stage marker are reported as not checked")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    started = time.time()
    directory = Path(args.dir).resolve()
    ctx = Context(args.extension, args.development, Report(args.max_print))
    rep = ctx.report
    root_ext = directory / ctx.design["name"]
    clone = directory.parent.parent
    if not root_ext.is_dir():
        raise UsageError("No directory %s" % root_ext)
    if args.report:
        target = Path(args.report).resolve()
        guard = clone if (clone / ".git").exists() else directory
        if guard == target or guard in target.parents:
            raise UsageError("Refused: --report must lie outside %s" % guard)
    ext = ctx.design["name"]
    rep.say("verify_e_x3.py %s - independent check of the %s X.3 outputs" % (TOOL_VERSION, ext))
    rep.say("directory: %s" % root_ext)
    rep.say("started (UTC): %s; Python %s; NumPy %s; %s" % (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                             platform.python_version(), np.__version__,
                                                             platform.platform()))
    rep.say("mode: %s" % ("development (sizes from the manifests)" if args.development else
                          "registered design (200 series per cell, 1,000 attempts, seed 1927 as recorded)"))
    # 1. integrity
    parts = sorted(p for p in root_ext.iterdir() if p.is_file() and p.suffix == ".jsonl" and part_kind(p.name)
                   and (args.only is None or part_kind(p.name) == args.only))
    kinds = ("size", "power") if args.only is None else (args.only,)
    if args.only:
        rep.say("INTERIM (--only %s): only the %s part files are read; the rest is not checked" % (args.only, args.only))
    rep.say("")
    rep.say("[1] INTEGRITY OF THE PART FILES")
    rows = []
    for path in parts:
        row = parse_part(ctx, path)
        rows.append(row)
        rep.say("  %-28s %11d bytes %5d lines %4d records %d session(s) %s%s" % (
            row["file"], row["bytes"], row["lines"], row["replicates"], row["sessions"],
            "OK" if not row["problems"] else "%d PROBLEM(S)" % row["problems"],
            " TRUNCATED" if row["truncated"] else ""))
    reference = compare_manifests(ctx)
    cover = coverage(ctx, kinds)
    statuses = {}
    for entry in ctx.entries:
        key = "%s/%s" % (entry["kind"], entry["status"])
        statuses[key] = statuses.get(key, 0) + 1
    rep.say("  part files: %d (%d size, %d power); records %d; coordinates expected %d, present %d, missing %d, "
            "duplicated %d, outside the design %d" % (len(rows), sum(r["kind"] == "size" for r in rows),
                                                      sum(r["kind"] == "power" for r in rows), len(ctx.entries),
                                                      cover["expected"], cover["present"], cover["missing"],
                                                      cover["duplicates"], cover["extra"]))
    rep.say("  status counts: %s" % json.dumps(statuses, sort_keys=True))
    rep.say("  per-record checks: p recomputed from the stored surrogate statistics for %d records; observed S "
            "recomputed from the stored input for %d records (max |difference| %.3g); fitted null recomputed "
            "(max |difference| %.3g); records with a problem: %d" % (
                ctx.p_recomputed, ctx.s_recomputed, ctx.max_s_difference, ctx.max_null_difference,
                ctx.record_issue_count))
    if ctx.b_prime:
        rep.say("  retained draws B' per record: min %d, max %d, records with B' < %d: %d" % (
            min(ctx.b_prime), max(ctx.b_prime), ctx.expected_B, sum(b < ctx.expected_B for b in ctx.b_prime)))
    if ctx.extension == "e3" and ctx.s_recomputed:
        rep.say("  E3: l(r) at the accepted estimate recomputed by this tool's square-root filter: max |difference| %.3g" %
                ctx.max_loglik_difference)
    if reference:
        rep.say("  manifests: %d, one fingerprint (commit %s, Python %s, code %s..., mode %s, seed %s)" % (
            len(ctx.manifests), reference.get("commit"), reference.get("python"),
            str(reference.get("code_sha256"))[:12], reference.get("mode"), reference.get("master_seed")))
    ctx.registered_design = bool(
        not args.development and reference and ctx.manifests
        and all(m.get("mode") == "registered" and m.get("master_seed") == REGISTERED_SEED
                and m.get("n_series") == N_SERIES and m.get("B") == B_ATTEMPTS
                and (part_kind(name) == "size" or m.get("kappas") == list(KAPPAS))
                for name, m in ctx.manifests.items())
        and all(e["registered_flag"] is True for e in ctx.entries))
    # 2. recomputation
    n = ctx.expected_n
    size_entries = [e for e in ctx.entries if e["kind"] == "size"]
    size = cell_figures(size_entries, n)
    strict_size = cell_figures([dict(e, valid=e["strict_valid"], rejected=e["rejected_exact"]) for e in size_entries], n)
    power_cells = [cell_figures([e for e in ctx.entries if e["kind"] == "power" and e["cell"] == c], n, KAPPAS[c])
                   for c in range(len(KAPPAS))]
    power = power_figures(power_cells)
    rep.say("")
    rep.say("[2] RECOMPUTED FROM THE RECORDS (denominator = %d requested per cell; raw p <= 0.05 counted only "
            "for valid records)" % n)
    if "size" in kinds:
      rep.say("  size: rejections R = %d of %d; valid %d; invalid or unfinished %d; rate %s; Wilson 95%% %s; MC s.e. %s;"
            " accounting bounds [%s, %s]" % (size["rejected"], n, size["valid"], n - size["valid"],
                                             size["rate_exact"] or "undefined", fmt_interval(size["rate_wilson"]),
                                             fmt(size["rate_se"]), fmt(size["accounting_bounds"][0]),
                                             fmt(size["accounting_bounds"][1])))
      rep.say("        mean S %s (s.e. %s); failures by status %s" % (fmt(size["mean_S"], 8), fmt(size["mean_S_se"]),
                                                                     json.dumps(size["failures"])))
    for cell in (power_cells if "power" in kinds else []):
        rep.say("  power kappa %.1f: R = %d of %d; valid %d; rate %s; Wilson 95%% %s; MC s.e. %s; mean S %s (s.e. %s)" % (
            cell["kappa"], cell["rejected"], n, cell["valid"], cell["rate_exact"] or "undefined",
            fmt_interval(cell["rate_wilson"]), fmt(cell["rate_se"]), fmt(cell["mean_S"], 8), fmt(cell["mean_S_se"])))
    for adj in (power["adjacent"] if "power" in kinds else []):
        rep.say("  kappa %.1f -> %.1f: difference %+.4f; s.e. %.5f; 1.96 s.e. %.5f; decrease flag %s" % (
            adj["left_kappa"], adj["right_kappa"], adj["difference"], adj["standard_error"], adj["threshold"],
            adj["decrease_flag"]) + ("" if adj["decrease_flag"] == adj["decrease_flag_float"] else
                                     " (float reading %s: at the threshold)" % adj["decrease_flag_float"]))
    if "power" in kinds:
      rep.say("  D80: %s%s" % (power["d80_status"], "" if power["D80"] is None else " = %s at kappa80 = %s (cells %s)" % (
        fmt(power["D80"], 8), fmt(power["kappa80"]), power["crossing"])))
    if strict_size["rejected"] != size["rejected"] or strict_size["valid"] != size["valid"]:
        rep.say("  NOTE: under the strict reading (a record is valid only if it also passes every per-record check) "
                "size has R = %d, valid %d" % (strict_size["rejected"], strict_size["valid"]))
    # 3. pass rule
    rep.say("")
    rep.say("[3] THE REGISTERED PASS RULE, CLAUSE BY CLAUSE")
    clauses = CLAUSES[ctx.extension]
    h1 = CLAUSES["h1"]
    rule = size_rule(size, n)
    band_ok, all_valid = rule["band"], rule["all_valid"]
    ctx.size_clause_pass = rule["passed"]
    verdicts = []

    def clause(label, source, passed, numbers):
        file, section, text = source
        rep.say("  %s: %s" % (label, "PASS" if passed else "FAIL"))
        rep.say("    registered (%s, %s): \"%s\"" % (file, section, text))
        rep.say("    numbers: %s" % numbers)
        verdicts.append(dict(clause=label, source="%s, %s" % (file, section), text=text, passed=bool(passed),
                             numbers=numbers))

    rep.say("  precondition - registered design recorded in every manifest and record (mode registered, seed 1927, "
            "200 series, B = 1,000, kappa 1.0-1.6): %s" % ("yes" if ctx.registered_design else
                                                          "NO (development run or a mismatch)"))
    if "size" in kinds:
        clause("SIZE, rate in band", clauses["size"], band_ok,
               "R/N = %d/%d = %s; band [0.02, 0.09] inclusive, i.e. %d <= R <= %d%s" % (
                   size["rejected"], n, fmt(size["rejected"] / n), math.ceil(BAND[0] * n), math.floor(BAND[1] * n),
                   "" if size["complete"] else " (rate undefined: the cell is incomplete)"))
        clause("SIZE, all replicates valid", clauses["size"], all_valid,
               "valid %d of %d requested (records present %d)" % (size["valid"], n, size["attempted"]))
    else:
        rep.say("  SIZE: not checked (--only power)")
    prule = power_rule(power)
    no_flag = prule["no_flag"]
    if "power" in kinds:
        cells_valid = prule["cells_valid"]
        clause("POWER, every cell complete and valid (H1 section 9 as incorporated)", h1["valid_cell"], cells_valid,
               "valid per cell %s of %d" % ([c["valid"] for c in power_cells], n))
        no_flag = prule["no_flag"]
        clause("POWER, no flagged decrease (H1 section 9, AT-16 as incorporated)", h1["at16"], no_flag,
               "adjacent differences %s; 1.96 s.e. %s; flags %s" % (
                   [round(a["difference"], 4) for a in power["adjacent"]],
                   [round(a["threshold"], 4) for a in power["adjacent"]], power["flags_exact"]))
        rep.say("  POWER, reporting (%s, %s): rates, Wilson intervals, adjacent differences with flags, mean S and s.e. "
                "are all computed above; they are reports, not pass conditions." % clauses["power"][:2])
        rep.say("  D80 (%s): %s" % (clauses["d80"][1], power["d80_status"]))
    else:
        rep.say("  POWER: not checked (--only size)")
    prerequisite = None
    if ctx.extension == "e3":
        hashes_pre = {}
        path = root_ext / "x3_prerequisite.jsonl"
        if path.is_file():
            hashes_pre["x3_prerequisite.jsonl"] = sha256_file(path)
        prerequisite = check_prerequisite(ctx, root_ext, hashes_pre, reference)
        f2 = check_f2(directory)
        prerequisite["F2"] = f2
        cl = prerequisite.get("clauses", {})
        if cl:
            clause("E3 PREREQUISITE, r = 0 fixture", clauses["prereq_r0"], cl["r0"]["passed"],
                   "max |final filtered state - OLS| = %s (recorded %s); tolerance 1e-6" % (
                       fmt(cl["r0"]["max_abs_difference"]), fmt(cl["r0"]["recorded"])))
            agreement_all = bool(cl["agreement_prerequisite_series"]["passed"] and cl["agreement_at11_fixture"]["passed"])
            clause("E3 PREREQUISITE, section 6 agreement test (prerequisite series and AT-11 fixture)",
                   clauses["prereq_agreement"], agreement_all,
                   "states %s / %s, l(r) %s / %s (tolerances 1e-8, 1e-6); every X.3 fixture: see per-record checks" % (
                       fmt(cl["agreement_prerequisite_series"]["max_state_difference"]),
                       fmt(cl["agreement_at11_fixture"]["max_state_difference"]),
                       fmt(cl["agreement_prerequisite_series"]["max_loglik_difference"]),
                       fmt(cl["agreement_at11_fixture"]["max_loglik_difference"])))
            clause("E3 PREREQUISITE, F2 and AT-11", clauses["prereq_f2"],
                   bool(cl["at11"]["passed"] and f2.get("passed")),
                   "AT-11 reference %s, batched %s (tolerance 1e-6); F2 stage marker %s, log \"%s\"" % (
                       fmt(cl["at11"]["reference_max_abs_difference"]), fmt(cl["at11"]["batched_max_abs_difference"]),
                       f2["stage_marker"], f2["log"]))
    # 4. hashes
    rep.say("")
    rep.say("[4] OUTPUT HASHES")
    known = {row["file"]: (row["sha256"], row["bytes"]) for row in rows}
    names = tuple(row["file"] for row in rows)
    include = None if args.only is None else (
        lambda relative: relative == "x3_prerequisite.jsonl" or relative.split("/")[0] in names
        or relative.split("/")[0] in tuple(name + ".fits" for name in names))
    hashes = hash_directory(ctx, root_ext, known, include)
    hash_result = check_output_hashes(ctx, directory, root_ext, hashes, include)
    rep.say("  OUTPUT_SHA256.json lists %d files (created %s); SHA-256 and size recomputed: %d match, %d differ, "
            "%d missing; files present but not listed: %d; OUTPUT_SHA256.txt consistent: %s" % (
                hash_result["listed"], hash_result.get("created_utc"), hash_result["matched"],
                len(hash_result["mismatched"]), len(hash_result["missing"]), len(hash_result["unlisted"]),
                hash_result["txt_consistent"]))
    fits_result = None
    if ctx.extension == "e3":
        fits_result = check_fits(ctx, root_ext, hashes, args.deep_fits)
        rep.say("  retained-fits files: %d expected by the records, %d present, %d with the recorded SHA-256%s" % (
            fits_result["expected"], fits_result["present"], fits_result["matched"],
            "; %d decompressed and checked" % fits_result["deep_checked"] if args.deep_fits else ""))
    # 5. runner comparison
    rep.say("")
    rep.say("[5] COMPARISON WITH THE RUNNER'S SUMMARIES")
    skipped = dict(present=None, compared=0, differences=[], max_float_difference=0.0, skipped=True)
    size_cmp = compare_runner(ctx, root_ext, "size", [size], power, rows) if "size" in kinds else dict(
        skipped, file="x3_size_summary.json")
    power_cmp = compare_runner(ctx, root_ext, "power", power_cells, power, rows) if "power" in kinds else dict(
        skipped, file="x3_power_summary.json")
    for item in (size_cmp, power_cmp):
        rep.say("  %s: %d fields compared; %d differ; max |float difference| %.3g" % (
            item["file"], item["compared"], len(item["differences"]), item["max_float_difference"]))
    stage = check_stage_and_log(ctx, directory, size, power_cells, power) if args.only is None else dict(
        headline=None, log=None, skipped="interim run (--only): stage marker and run log not checked")
    if stage["headline"]:
        rep.say("  stages/%s: %d headline fields compared; %d differ" % (
            stage["headline"]["file"], stage["headline"]["compared"], len(stage["headline"]["differences"])))
    if stage["log"]:
        rep.say("  run_log.jsonl: %d %s parts, %d attempts, last attempt of every part exited 0: %s; resumed parts: %s" % (
            stage["log"]["parts"], ext, stage["log"]["attempts"], stage["log"]["all_final_exits_zero"],
            stage["log"]["resumed"] or "none"))
    quotes = verify_quotes(clone) if (clone / "prereg").is_dir() else {}
    if quotes:
        rep.say("  registered wording quoted here found verbatim in the clone's prereg files: %d of %d" % (
            sum(1 for v in quotes.values() if v), len(quotes)))
        for key, value in quotes.items():
            if value is not True:
                rep.problem("quotes", "not found verbatim: %s" % key)
    # verdict
    rep.say("")
    rep.say("[6] RESULT")
    rep.say("  problems found (integrity, hashes, disagreements with the runner): %d" % len(rep.problems))
    for item in rep.problems[:args.max_print]:
        rep.say("    - %s: %s" % (item["where"], item["message"]))
    if len(rep.problems) > args.max_print:
        rep.say("    ... %d more in the JSON report" % (len(rep.problems) - args.max_print))
    size_verdict = ("PASS" if (ctx.registered_design and ctx.size_clause_pass) else "FAIL") if "size" in kinds \
        else "not checked"
    power_verdict = ("PASS" if (ctx.registered_design and no_flag) else "FAIL") if "power" in kinds else "not checked"
    rep.say("  registered rule on these numbers: SIZE %s; POWER (AT-16 as incorporated) %s; D80 %s" % (
        size_verdict, power_verdict, "undefined" if power["D80"] is None else fmt(power["D80"], 8)))
    agree = all(not item["differences"] and (item["present"] or item.get("skipped")) for item in (size_cmp, power_cmp))
    rep.say("  runner's summaries and this recomputation agree: %s" % ("YES" if agree else "NO"))
    elapsed = time.time() - started
    rep.say("  finished in %.1f s" % elapsed)
    status = 0 if not rep.problems else 1
    payload = dict(tool="verify_e_x3.py", version=TOOL_VERSION, extension=args.extension, directory=str(root_ext),
                   development=args.development, python=platform.python_version(), numpy=np.__version__,
                   platform=platform.platform(), elapsed_seconds=elapsed, files=rows, coverage=cover,
                   statuses=statuses, registered_design=ctx.registered_design,
                   per_record=dict(p_recomputed=ctx.p_recomputed, s_recomputed=ctx.s_recomputed,
                                   max_s_difference=ctx.max_s_difference,
                                   max_null_difference=ctx.max_null_difference,
                                   max_loglik_difference=ctx.max_loglik_difference,
                                   records_with_problems=ctx.record_issue_count,
                                   b_prime_min=min(ctx.b_prime) if ctx.b_prime else None,
                                   b_prime_below_B=sum(b < ctx.expected_B for b in ctx.b_prime)),
                   size=size, size_strict=strict_size, power_cells=power_cells, power=power, clauses=verdicts,
                   prerequisite=prerequisite, hashes=hash_result, fits=fits_result, runner_size=size_cmp,
                   runner_power=power_cmp, stage=stage, quotes=quotes,
                   verdict=dict(size=size_verdict, power=power_verdict, D80=power["D80"], agree_with_runner=agree),
                   problems=rep.problems, exit_status=status)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1, default=str)
    return payload


def fmt_interval(interval):
    if interval is None:
        return "undefined"
    return "[%.4f, %.4f]" % (interval[0], interval[1])


if __name__ == "__main__":
    sys.exit(main())
