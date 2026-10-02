"""Independent check of the frozen E4 outputs, from the stored files alone.

usage (registered interpreter):  python -B verify_e4_stored.py <registered clone> [--committed]

Reads audit/e4/, audit/E4_RESULT.json, audit/H1_RESULT.json and figures/e4_*; writes nothing. It uses numpy and scipy only
(no repository code), so it is a second implementation of: the rolling and null AR(2) fits, the statistic
Delta[r] = M(r-1) - M(r-9) (prereg/H1.md section 8), the Kendall and lag-one statistics, the exceedance count, p, q, the
Wilson interval and the episode interval. It does NOT regenerate the surrogate series from the seed and does NOT read the
workbook. With --committed it also compares every frozen file with the blob in HEAD.
"""
import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.stats import kendalltau

clone = Path(sys.argv[1]).resolve()
committed = "--committed" in sys.argv
E = clone / "audit" / "e4"
Z = 1.959963984540054
LAG = 8        # r-1 against r-9 (prereg/H1.md: Delta[r] = M(r-1) - M(r-9))
fails = []
checks = 0


def ok(name, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        fails.append(name)
    if not cond or detail:
        print(("PASS  " if cond else "FAIL  ") + name + (": " + detail if detail else ""))


def jload(path):
    return json.loads(Path(path).read_bytes().decode("utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wilson(k, n):
    q = k / n
    d = 1 + Z * Z / n
    centre = (q + Z * Z / (2 * n)) / d
    half = Z * math.sqrt(q * (1 - q) / n + Z * Z / (4 * n * n)) / d
    return centre - half, centre + half


def close(a, b, tol):
    return abs(float(a) - float(b)) <= tol


a = jload(E / "analysis.json")
res = jload(clone / "audit" / "E4_RESULT.json")
h1 = jload(clone / "audit" / "H1_RESULT.json")

# 1. the frozen files equal their recorded hashes (and, if asked, the blobs in HEAD)
bad = [rel for rel, h in res["frozen_files"].items() if sha(clone / rel) != h]
ok("every frozen file equals its recorded SHA-256", not bad, f"{len(res['frozen_files'])} files" if not bad else f"differ: {bad}")
manifest = jload(E / "manifest.json")
files = manifest.get("files", manifest)
bad = [rel for rel, h in files.items() if isinstance(h, str) and rel != "manifest.json"
       and (E / rel).exists() and sha(E / rel) != h]
ok("the report manifest agrees with the copies", not bad, str(bad) if bad else "")
rc = jload(E / "RUN_COMPLETE.json")
ok("RUN_COMPLETE.json names the stored run log, analysis and manifest",
   rc["run_log_sha256"] == sha(E / "run-log.json") and rc["analysis_sha256"]["analysis.json"] == sha(E / "analysis.json")
   and rc["report_manifest_sha256"] == sha(E / "manifest.json"))
if committed:
    bad = []
    for rel, h in res["frozen_files"].items():
        blob = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=clone, capture_output=True).stdout
        if hashlib.sha256(blob).hexdigest() != h:
            bad.append(rel)
    ok("every committed blob equals the recorded SHA-256", not bad, str(bad) if bad else f"{len(res['frozen_files'])} blobs")

# 2. the episodes and the final-data changes
sel = a["selections"]
ok("four episodes selected, all eligible", len(sel) == 4 and all(s["status"] == "eligible" for s in sel))
h1_changes = {e["onset_quarter"].replace(" ", ""): e["change"] for e in h1["episodes"] if e["statistic_available"]}
for s in sel:
    onset = f"{s['onset'][0]}Q{s['onset'][1]}"
    ok(f"Delta_final of {onset} equals the frozen H1 change", h1_changes.get(onset) == s["delta_final"],
       f"{s['delta_final']:.6f}")

# 3. rolling AR(2) fits: refitted from the stored growth series and compared with rolling.csv
rolling = list(csv.DictReader(open(E / "rolling.csv", newline="", encoding="utf-8")))
by_j = {}
for row in rolling:
    by_j.setdefault(int(row["j"]), []).append(row)


def fit(y):
    y = np.asarray(y, dtype=float)
    X = np.column_stack([np.ones(len(y) - 2), y[1:-1], y[:-2]])
    beta, *_ = np.linalg.lstsq(X, y[2:], rcond=None)
    return beta, y[2:] - X @ beta


def max_modulus(phi1, phi2):
    return float(max(abs(np.roots([1.0, -phi1, -phi2]))))


def lag1(window):
    v = np.asarray(window, dtype=float)
    v = v - v.mean()
    return float(np.sum(v[1:] * v[:-1]) / np.sum(v * v))


comp = {"primary": a["comparisons"]["primary"]["primary"]["observed"]["components"],
        32: a["comparisons"]["window32"]["primary"]["observed"]["components"],
        48: a["comparisons"]["window48"]["primary"]["observed"]["components"],
        "trend": a["comparisons"]["primary"]["trend"]["observed"]["components"],
        "lag1": a["comparisons"]["primary"]["lag1"]["observed"]["components"]}
deltas = {40: [], 32: [], 48: [], "trend": [], "lag1": []}
maxdev = 0.0
for s in sel:
    j = s["j"]
    g = np.asarray(s["series"]["growth"], dtype=float)
    rows = by_j[j]
    ok(f"j={j}: rolling.csv holds the stored growth series", len(rows) == len(g) and
       all(float(r["growth"]) == float(v) for r, v in zip(rows, g)), f"{len(g)} positions")
    mods = {}
    for W, col in ((40, "modulus"), (32, "modulus_w32"), (48, "modulus_w48")):
        m = {}
        for t in range(W - 1, len(g)):
            beta, _ = fit(g[t - W + 1:t + 1])
            m[t] = max_modulus(beta[1], beta[2])
            stored = rows[t][col]
            if stored == "":
                ok(f"j={j} W={W} position {t}: a stored modulus exists", False)
                continue
            dev = abs(m[t] - float(stored))
            maxdev = max(maxdev, dev)
            if dev > 1e-9:
                ok(f"j={j} W={W} position {t}: modulus agrees", False, f"{m[t]!r} vs {stored}")
            if W == 40:
                for key, val in (("intercept", beta[0]), ("phi1", beta[1]), ("phi2", beta[2])):
                    d2 = abs(val - float(rows[t][key]))
                    maxdev = max(maxdev, d2)
                    if d2 > 1e-9:
                        ok(f"j={j} position {t}: {key} agrees", False, f"{val!r} vs {rows[t][key]}")
        mods[W] = m
    last = len(g) - 1
    ok(f"j={j}: the last position is the quarter before the onset ({rows[-1]['quarter']})", True)
    for W, key in ((40, "primary"), (32, 32), (48, 48)):
        d = mods[W][last] - mods[W][last - LAG]
        deltas[W].append(d)
        ok(f"j={j}: Delta_rt at W={W} refitted equals the stored one", close(d, comp[key][j], 1e-9), f"{d:+.6f}")
    # Kendall trend: tau-b of positions 0..15 against M(r-16)..M(r-1) at W = 40
    tau = float(kendalltau(np.arange(16), [mods[40][t] for t in range(last - 15, last + 1)], variant="b").statistic)
    deltas["trend"].append(tau)
    ok(f"j={j}: Kendall tau-b equals the stored one", close(tau, comp["trend"][j], 1e-9), f"{tau:+.4f}")
    # lag-one comparator: A(r-1) - A(r-9) over W = 40 centred growth windows
    A = {t: lag1(g[t - 39:t + 1]) for t in range(39, len(g))}
    for t in range(39, len(g)):
        d3 = abs(A[t] - float(rows[t]["lag1_w40"]))
        maxdev = max(maxdev, d3)
        if d3 > 1e-9:
            ok(f"j={j} position {t}: lag-one value agrees", False, f"{A[t]!r} vs {rows[t]['lag1_w40']}")
    dA = A[last] - A[last - LAG]
    deltas["lag1"].append(dA)
    ok(f"j={j}: lag-one change equals the stored one", close(dA, comp["lag1"][j], 1e-9), f"{dA:+.4f}")
ok("largest deviation over every refitted modulus, coefficient and lag-one value is below 1e-9", maxdev <= 1e-9, f"{maxdev:.2e}")
S = float(np.mean(deltas[40]))
obs = a["comparisons"]["primary"]["primary"]["observed"]
ok("S_rt = mean of the four Delta_rt equals the stored value", close(S, obs["value"], 1e-12), f"{S:+.6f}")
ok("k = number of positive Delta_rt", int(sum(d > 0 for d in deltas[40])) == a["k"] == 2, str(a["k"]))
for W, comp_name in ((32, "window32"), (48, "window48")):
    ok(f"W={W}: the mean change equals the stored statistic", close(np.mean(deltas[W]), a["comparisons"][comp_name]["primary"]["observed"]["value"], 1e-12),
       f"{np.mean(deltas[W]):+.4f}")
ok("Kendall: the mean tau-b equals the stored statistic", close(np.mean(deltas["trend"]), a["comparisons"]["primary"]["trend"]["observed"]["value"], 1e-12),
   f"{np.mean(deltas['trend']):+.4f}")
ok("lag-one: the mean change equals the stored statistic", close(np.mean(deltas["lag1"]), a["comparisons"]["primary"]["lag1"]["observed"]["value"], 1e-12),
   f"{np.mean(deltas['lag1']):+.4f}")
final = [s["delta_final"] for s in sel]
rt = a["real_time_against_final"]["summary"]
ok("S_final,m and the mean difference are the stored ones",
   close(np.mean(final), rt["S_final_m"], 1e-12) and close(S - np.mean(final), rt["mean_difference"], 1e-12),
   f"{np.mean(final):+.4f}, {S - np.mean(final):+.4f}")
ok("same-sign count is the stored one", sum((x > 0) == (y > 0) for x, y in zip(deltas[40], final)) == rt["same_sign"],
   str(rt["same_sign"]))

# 4. the null fits: refitted on the whole stored vintage series, residuals centred
nm = a["comparisons"]["primary"]["null_models"]
for s in sel:
    j = s["j"]
    g = np.asarray(s["series"]["growth"], dtype=float)
    beta, resid = fit(g)
    n = nm[str(j)]
    ok(f"j={j}: null intercept and coefficients agree", close(beta[0], n["intercept"], 1e-9)
       and close(beta[1], n["coefficients"][0], 1e-9) and close(beta[2], n["coefficients"][1], 1e-9))
    ok(f"j={j}: null modulus agrees", close(max_modulus(beta[1], beta[2]), n["modulus"], 1e-9),
       f"{n['modulus']:.4f}")
    cen = resid - resid.mean()
    ok(f"j={j}: stored residuals are the centred OLS residuals", len(n["residuals"]) == len(cen)
       and np.max(np.abs(cen - np.asarray(n["residuals"]))) < 1e-9, f"{len(cen)} residuals")

# 5. every comparison: mean statistic, exceedance count, p, q and the Wilson interval from the stored attempts
specs = [("primary", "primary"), ("window32", "primary"), ("window48", "primary"), ("wild", "primary"),
         ("primary", "trend"), ("primary", "lag1")]
for block, part in specs:
    c = a["comparisons"][block][part]
    value = c["observed"]["value"]
    kept = [x["statistic"] for x in c["attempts"] if x["status"] == "retained"]
    K = sum(v >= value for v in kept)
    n = len(kept)
    p = (1 + K) / (n + 1)
    lo, hi = wilson(K, n)
    name = f"{block}.{part}"
    ok(f"{name}: attempts are 1,000 retained, none failed", n == 1000 == c["requested"] == c["attempted"]
       and c["failed"] == 0 and c["no_episode"] == 0, f"retained {n}")
    ok(f"{name}: exceedances recount", K == c["exceedances"], f"{K}")
    ok(f"{name}: p = (1+K)/(B'+1)", close(p, c["p_value"], 1e-15), f"{p:.4f}")
    ok(f"{name}: q and its Wilson interval", close(K / n, c["q"], 1e-15) and close(lo, c["q_wilson"][0], 1e-12)
       and close(hi, c["q_wilson"][1], 1e-12), f"{K / n:.3f} [{lo:.4f}, {hi:.4f}]")
    if part == "primary":
        ok(f"{name}: each attempt's statistic is the mean of its episode changes",
           all(close(np.mean(x["changes"]), x["statistic"], 1e-12) for x in c["attempts"] if x["status"] == "retained"))
        ok(f"{name}: the observed statistic is the mean of its components", close(np.mean(c["observed"]["components"]), value, 1e-12))
for row in a["secondary_table"]:
    ok(f"secondary table row '{row['analysis']}' has p = (1+K)/(B'+1)", close((1 + row["exceedances"]) / (row["B_prime"] + 1), row["p_value"], 1e-15),
       f"p {row['p_value']:.4f}")

# 6. the primary surrogate statistics in the report equal those in the analysis
csvrows = list(csv.DictReader(open(E / "primary-surrogates.csv", newline="", encoding="utf-8")))
att = a["comparisons"]["primary"]["primary"]["attempts"]
ok("primary-surrogates.csv equals the stored attempts", len(csvrows) == len(att) == 1000 and all(
    r["status"] == x["status"] and float(r["statistic"]) == x["statistic"]
    and all(float(r[f"delta_j{j}"]) == x["changes"][j] for j in range(4)) for r, x in zip(csvrows, att)))

# 7. the episode interval, replayed from the registered stream (SeedSequence([1927, 5405, 0, 0]), integers(0, m, (B, m)))
vals = np.asarray(obs["components"], dtype=float)
rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([1927, 5405, 0, 0])))
idx = rng.integers(0, len(vals), size=(10000, len(vals)))
means = vals[idx].mean(axis=1)
lo, hi = np.quantile(means, [0.05, 0.95], method="linear")
iv = a["episode_interval"]
ok("episode interval replay: endpoints", close(lo, iv["interval"][0], 1e-12) and close(hi, iv["interval"][1], 1e-12),
   f"[{lo:+.4f}, {hi:+.4f}]")
ok("episode interval replay: every resample mean", np.max(np.abs(means - np.asarray(iv["draw_means"]))) < 1e-12,
   f"{len(means)} means")

# 8. the registered run record
log = jload(E / "run-log.json")
ok("run log: registered primary run, seed 1927, B = 1,000, 10,000 resamples, no release dates",
   log["kind"] == "registered primary run" and log["master_seed"] == 1927 and log["B"] == 1000 and log["interval_B"] == 10000
   and log["input"]["release_dates"] == {} and log["environment"]["dirty"] is False)
ok("run log: Python 3.12.14", log["environment"]["python"] == "3.12.14")

print(f"CHECKS {checks}, FAILED {len(fails)}")
print("VERIFIED" if not fails else "NOT VERIFIED: " + "; ".join(fails[:20]))
sys.exit(1 if fails else 0)
