"""Tests of verify_e_x3.py: arithmetic against hand-computed values, and defect detection on small
self-consistent synthetic run directories (development mode; no registered seed or design size is used).

Run:  python -m pytest -q tests/test_verify_e_x3.py      (the tool is tools/verify_e_x3.py)

The expected Wilson bounds below were computed separately with 50-digit decimal arithmetic from the H1
section 6 formula (z = 1.959963984540054); the decrease-flag pairs were found by an exact rational search
over counts out of 200; the D80 values follow from the H1 section 9 interpolation by hand.
"""
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("verify_e_x3", HERE.parent / "tools" / "verify_e_x3.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

DEV_SEED = 20260928          # the runner's development master seed; never 1927
KAPPAS = (1.0, 1.2, 1.4, 1.6)


# ------------------------------------------------------------------------------------ arithmetic

@pytest.mark.parametrize("k, low, high", [
    (0, 0.0, 0.01884532637726657),
    (4, 0.00780442641634947, 0.05028708690582644),
    (13, 0.03837635464915298, 0.10801907929906894),
    (18, 0.05768744886219317, 0.13776571876716542),
    (200, 0.98115467362273345, 1.0),
])
def test_wilson_matches_hand_computed_values(k, low, high):
    lo, hi = v.wilson(k, 200)
    assert abs(lo - low) < 1e-15 and abs(hi - high) < 1e-15


def test_decrease_flag_either_side_of_1_96_standard_errors():
    # 86 -> 67 of 200: decrease 0.095 = 1.9641 s.e. (flagged); 87 -> 68: 0.095 = 1.9593 s.e. (not flagged)
    exact, as_float, difference, se = v.decrease_flag(86, 67, 200)
    assert exact and as_float and abs(difference + 0.095) < 1e-15 and abs(-difference / se - 1.964145620951911) < 1e-12
    exact, as_float, difference, se = v.decrease_flag(87, 68, 200)
    assert not exact and not as_float and abs(-difference / se - 1.959335631908563) < 1e-12
    assert not v.decrease_flag(10, 60, 200)[0]          # an increase is never flagged
    assert not v.decrease_flag(0, 0, 200)[0]            # equal rates, zero standard error
    assert v.decrease_flag(200, 0, 200)[0]              # zero standard error, any decrease exceeds it


def test_a_decrease_exactly_at_the_threshold_is_not_flagged():
    # p_prev = 2401/3026, p_cur = 0, n = 1: m^2 = 1.96^2 * p(1-p) exactly, since m = 1.96^2 (1-m)
    at = Fraction(2401, 3026)
    assert at * at == Fraction(196, 100) ** 2 * at * (1 - at)
    assert v.exceeds_threshold(at, 0, 1) is False
    assert v.exceeds_threshold(at + Fraction(1, 10 ** 12), 0, 1) is True


def cells(counts, means, n=200):
    out = []
    for kappa, r, m in zip(KAPPAS, counts, means):
        entries = [dict(replicate=i, status="ok", valid=True, rejected=i < r, S=m) for i in range(n)]
        out.append(v.cell_figures(entries, n, kappa))
    return out


def test_d80_interpolates_linearly_between_the_first_crossing_cells():
    # rates 0.5, 0.7, 0.9, 0.95: first crossing at kappa 1.4; w = (0.8-0.7)/(0.9-0.7) = 0.5
    power = v.power_figures(cells([100, 140, 180, 190], [0.1, 0.2, 0.3, 0.4]))
    assert power["crossing"] == dict(left=1, right=2, weight=0.5)
    assert abs(power["kappa80"] - 1.3) < 1e-15 and abs(power["D80"] - 0.25) < 1e-15


def test_d80_at_the_first_cell_and_at_exactly_0_80():
    power = v.power_figures(cells([170, 180, 190, 195], [0.11, 0.2, 0.3, 0.4]))
    assert power["kappa80"] == 1.0 and power["D80"] == pytest.approx(0.11, abs=1e-15)
    power = v.power_figures(cells([100, 160, 190, 195], [0.1, 0.2, 0.3, 0.4]))   # 160/200 = 0.80 crosses
    assert power["crossing"]["right"] == 1 and power["crossing"]["weight"] == 1.0
    assert power["D80"] == pytest.approx(0.2, abs=1e-15)


def test_d80_undefined_without_a_crossing_or_with_an_invalid_cell():
    power = v.power_figures(cells([9, 14, 16, 23], [0.0, 0.01, 0.02, 0.03]))
    assert power["D80"] is None and power["d80_status"].startswith("undefined: no kappa")
    broken = cells([170, 180, 190, 195], [0.1, 0.2, 0.3, 0.4])
    entries = [dict(replicate=i, status="ok", valid=i > 0, rejected=True, S=0.1) for i in range(200)]
    broken[2] = v.cell_figures(entries, 200, 1.4)
    power = v.power_figures(broken)
    assert power["D80"] is None and power["d80_status"].startswith("undefined: a cell")
    assert not v.power_rule(power)["passed"] and power["adjacent"] == []


def size_cell(rejected, n=200, invalid=0):
    entries = [dict(replicate=i, status="ok" if i >= invalid else "invalid_surrogate_failure", valid=i >= invalid,
                    rejected=invalid <= i < invalid + rejected, S=0.01 * i) for i in range(n)]
    return v.cell_figures(entries, n)


@pytest.mark.parametrize("rejected, passed", [(3, False), (4, True), (13, True), (18, True), (19, False)])
def test_size_band_edges(rejected, passed):
    cell = size_cell(rejected)
    assert v.size_rule(cell, 200)["passed"] is passed
    assert cell["rate"] == rejected / 200


def test_one_invalid_record_fails_the_all_valid_clause_and_leaves_the_rate_undefined():
    cell = size_cell(13, invalid=1)
    rule = v.size_rule(cell, 200)
    assert cell["valid"] == 199 and cell["rate"] is None and cell["failures"] == {"invalid_surrogate_failure": 1}
    assert rule == dict(band=False, all_valid=False, passed=False)
    assert cell["accounting_bounds"] == (13 / 200, 14 / 200)


def test_mean_s_and_its_standard_error_use_denominators_200_and_199():
    entries = [dict(replicate=i, status="ok", valid=True, rejected=False, S=float(i)) for i in range(200)]
    cell = v.cell_figures(entries, 200)
    assert cell["mean_S"] == 99.5
    assert cell["mean_S_se"] == pytest.approx(math.sqrt(sum((i - 99.5) ** 2 for i in range(200)) / 199) / math.sqrt(200))


def test_independent_modulus_follows_the_h1_section_4_formulas():
    # complex pair: sqrt(-phi2); real: larger root by copysign; product rule for the other
    got = v.companion_modulus(np.array([0.2, 0.3, -1.5, 0.0]), np.array([-0.5, 0.1, -0.56, 0.0]))
    assert got == pytest.approx([math.sqrt(0.5), 0.5, 0.8, 0.0], abs=1e-15)


def test_episode_rules_single_negative_year_and_merge_distance_2():
    g = np.ones(20)
    g[[3, 5, 9, 10, 15]] = -1          # runs {3}, {5}, {9,10}, {15}: 5-3 = 2 merges, 9-5 = 4 does not
    assert v.episodes(g, 1, 2) == [(3, 5), (9, 10), (15, 15)]
    assert v.episodes(g, 2, 8) == [(9, 10)]


# ------------------------------------------------------------------------ synthetic run directories

def _series(seed, n=316):
    rng = np.random.default_rng(seed)
    e = rng.normal(0, 3.5, n - 2)
    x = np.empty(n)
    x[:2] = 2.5
    for t in range(2, n):
        x[t] = 1.5 + 0.3 * x[t - 1] + 0.1 * x[t - 2] + e[t - 2]
    return x


def _record(kind, cell, replicate, B, exceed, status="ok"):
    x = _series(7000 + 100 * cell + replicate + (0 if kind == "size" else 50))
    eligible, ineligible, changes, S, _ = v.independent_statistic("e1", kind, x)
    attempts = []
    for i in range(B):
        stat = S + 0.5 if i < exceed else S - 0.5
        attempts.append(dict(number=i, status="retained", statistic=stat, eligible_onsets=list(eligible),
                             changes=[stat] * len(eligible), error=None))
    failed = 0
    if status == "invalid_surrogate_failure":
        attempts[-1] = dict(number=B - 1, status="failed", statistic=None, eligible_onsets=[], changes=[],
                            error="FloatingPointError: test")
        failed = 1
    retained = B - failed
    K = sum(1 for a in attempts if a["status"] == "retained" and a["statistic"] >= S)
    p = None if failed else (1 + K) / (retained + 1)
    phi1, phi2, c, residuals = v.ols_ar2(x)
    null = dict(coefficients=[phi1, phi2], intercept=c, initial=[float(x[0]), float(x[1])],
                residuals=(residuals - residuals.mean()).tolist(), residual_mean_removed=float(residuals.mean()),
                modulus=float(v.companion_modulus(np.array([phi1]), np.array([phi2]))[0]))
    observed = dict(mean_change=S, changes=changes, eligible_onsets=eligible, ineligible_onsets=ineligible)
    comparison = dict(status=status, observed=observed, p_value=p, requested=B, attempted=B, retained=retained,
                      no_episode=0, failed=failed, exceedances=K, p_grid_spacing=1 / (retained + 1),
                      attempts=attempts, null_model=null, window=30, lookback=2, merge=2,
                      onset_mode="endogenous" if kind == "size" else "external_fixed", innovation_mode="residual",
                      rng_before={}, rng_after={})
    record = dict(cell="size" if kind == "size" else "power_%d" % cell, cell_index=cell, replicate=replicate,
                  status=status, input=x.tolist(), input_sha256=hashlib.sha256(x.astype("<f8").tobytes()).hexdigest(),
                  S=S, p_value=p, observed=observed, comparison=comparison, error=None, surrogate_requested=B,
                  surrogate_attempted=B, surrogate_retained=retained, surrogate_no_episode=0, surrogate_failed=failed,
                  surrogate_exceedances=K, surrogate_exceedance_rate=K / retained,
                  surrogate_exceedance_wilson=list(v.wilson(K, retained)), record_type="replicate", registered=False,
                  mode="development", master_seed=DEV_SEED, B=B, settings={}, code_sha256="c" * 64)
    if kind == "power":
        record["kappa"] = KAPPAS[cell]
    return record


def _manifest(kind, n, B):
    return dict(record_type="manifest", schema=2, created_utc="2026-09-29T00:00:00+00:00", extension="e1", check=kind,
                mode="development", master_seed=DEV_SEED, n_series=n, B=B,
                kappas=list(KAPPAS) if kind == "power" else None, settings={}, code_sha256="c" * 64,
                identity=dict(commit="a" * 40, dirty=False, python="3.12.14", packages={}),
                imported=dict(ext_commit="a" * 40), lock=dict(satisfied=True), gate=None, prerequisite=None, argv=[])


def _entry(record):
    ok = record["status"] == "ok"
    return dict(replicate=record["replicate"], status=record["status"], valid=ok,
                rejected=ok and record["p_value"] <= 0.05, S=record["S"])


def build_run(tmp_path, n=2, B=4, invalid=()):
    """A development E1 run directory in the runner's and driver's formats, self-consistent throughout."""
    clone = tmp_path / "clone"
    (clone / ".git").mkdir(parents=True)
    root = clone / "runs" / "extensions"
    ext = root / "E1"
    ext.mkdir(parents=True)
    files = {}
    size_records = [_record("size", 0, r, B, exceed=0 if r == 0 else 2,
                            status="invalid_surrogate_failure" if (0, r) in invalid else "ok") for r in range(n)]
    files["x3_size_r000-%03d.jsonl" % n] = ("size", size_records)
    power_records = {}
    for c in range(4):
        power_records[c] = [_record("power", c, r, B, exceed=c % 2) for r in range(n)]
        files["x3_power_c%d_r000-%03d.jsonl" % (c, n)] = ("power", power_records[c])
    rows = {}
    for name, (kind, records) in files.items():
        lines = [_manifest(kind, n, B), dict(record_type="session", started_utc="2026-09-29T00:00:01+00:00")]
        text = "".join(json.dumps(line) + "\n" for line in lines + records)
        (ext / name).write_bytes(text.encode())           # bytes: the same on every platform
        rows[name] = (hashlib.sha256(text.encode()).hexdigest(), len(records))
    size = v.cell_figures([_entry(r) for r in size_records], n)
    power_cells = [v.cell_figures([_entry(r) for r in power_records[c]], n, KAPPAS[c]) for c in range(4)]
    power = v.power_figures(power_cells)
    keys = ("requested", "attempted", "valid", "rejected", "unfinished", "failures", "accounting_bounds",
            "valid_only_rate", "rate", "rate_se", "rate_wilson", "mean_S", "mean_S_se")

    def inputs(kind):
        return [dict(path="runs/extensions/E1/" + name, sha256=digest, manifest={}, records=count)
                for name, (digest, count) in rows.items() if name.startswith("x3_" + kind)]

    (ext / "x3_size_summary.json").write_text(json.dumps(dict(
        manifest={}, inputs=inputs("size"), summary=dict(cell={k: size[k] for k in keys}, bounds=[0.02, 0.09],
                                                         registered_design=False, passed=False))))
    (ext / "x3_power_summary.json").write_text(json.dumps(dict(
        manifest={}, inputs=inputs("power"), summary=dict(
            cells=[dict(kappa=c["kappa"], **{k: c[k] for k in keys}) for c in power_cells], D80=power["D80"],
            kappa80=power["kappa80"], crossing=power["crossing"],
            adjacent_comparisons=[dict(left_kappa=a["left_kappa"], right_kappa=a["right_kappa"],
                                       difference=a["difference"], standard_error=a["standard_error"],
                                       decrease_flag=a["decrease_flag"]) for a in power["adjacent"]],
            decrease_flags=power["flags_exact"], registered_design=False, passed=False))))
    write_hashes(root)
    (root / "stages").mkdir()
    (root / "stages" / "E1_summaries.json").write_text(json.dumps(dict(headline=dict(
        size_rate=size["rate"], size_valid=size["valid"], size_failures=size["failures"],
        power_rates=[c["rate"] for c in power_cells], power_valid=[c["valid"] for c in power_cells],
        decrease_flags=power["flags_exact"], D80=power["D80"], size_passed=False, power_passed=False))))
    (root / "logs").mkdir()
    (root / "logs" / "run_log.jsonl").write_text("".join(
        json.dumps(dict(event=e, part="e1/" + name[:-6], exit=0)) + "\n" for name in files for e in ("start", "end")))
    return root


def write_hashes(root):
    ext = root / "E1"
    outputs = []
    for path in sorted(p for p in ext.rglob("*") if p.is_file() and not p.name.startswith("OUTPUT_SHA256")):
        data = path.read_bytes()
        outputs.append(dict(path="runs/extensions/E1/" + path.relative_to(ext).as_posix(), bytes=len(data),
                            sha256=hashlib.sha256(data).hexdigest()))
    (ext / "OUTPUT_SHA256.json").write_text(json.dumps(dict(created_utc="x", extension="e1", files=len(outputs),
                                                             total_bytes=sum(o["bytes"] for o in outputs),
                                                             outputs=outputs)))
    (ext / "OUTPUT_SHA256.txt").write_text("".join("%s  %s\n" % (o["sha256"], o["path"]) for o in outputs))


def run(root, *extra):
    return v.verify(["--extension", "e1", "--dir", str(root), "--development", *extra])


def messages(payload):
    return [p["message"] for p in payload["problems"]]


def test_a_clean_synthetic_run_verifies_with_no_problem(tmp_path, capsys):
    payload = run(build_run(tmp_path))
    assert payload["exit_status"] == 0, messages(payload)
    assert payload["verdict"]["agree_with_runner"] is True
    assert payload["per_record"]["p_recomputed"] == 10 and payload["per_record"]["s_recomputed"] == 10
    assert payload["coverage"] == dict(expected=10, present=10, missing=0, duplicates=0, extra=0)


def _rewrite(path, change):
    lines = path.read_bytes().decode().splitlines(keepends=True)
    path.write_bytes("".join(change(lines)).encode())


def test_missing_duplicate_and_extra_records_are_reported(tmp_path, capsys):
    root = build_run(tmp_path)
    part = root / "E1" / "x3_size_r000-002.jsonl"
    original = part.read_bytes()
    _rewrite(part, lambda lines: lines[:-1])                          # replicate 1 missing
    assert any("missing" in m for m in messages(run(root)))
    part.write_bytes(original)
    _rewrite(part, lambda lines: lines + [lines[-1]])                 # replicate 1 twice
    assert any("appears 2 times" in m for m in messages(run(root)))
    part.write_bytes(original)
    extra = json.loads(original.decode().splitlines()[-1])
    extra["replicate"] = 2                                            # outside the design (n = 2)
    _rewrite(part, lambda lines: lines + [json.dumps(extra) + "\n"])
    found = messages(run(root))
    assert any("outside the registered design" in m for m in found)
    assert any("do not match the file name's range" in m for m in found)


def test_a_truncated_last_line_is_reported(tmp_path, capsys):
    root = build_run(tmp_path)
    part = root / "E1" / "x3_power_c2_r000-002.jsonl"
    _rewrite(part, lambda lines: lines[:-1] + [lines[-1][: len(lines[-1]) // 2]])
    found = messages(run(root))
    assert any("truncated last line" in m for m in found)
    assert any("missing" in m for m in found)


def test_hash_mismatch_and_unlisted_files_are_reported(tmp_path, capsys):
    root = build_run(tmp_path)
    part = root / "E1" / "x3_power_c0_r000-002.jsonl"
    _rewrite(part, lambda lines: lines + ['{"record_type": "session"}\n'])
    (root / "E1" / "stray.txt").write_text("x")
    found = messages(run(root))
    assert any("hash or size differs now: runs/extensions/E1/x3_power_c0_r000-002.jsonl" in m for m in found)
    assert any("present but not listed: stray.txt" in m for m in found)
    assert any("inputs[x3_power_c0_r000-002.jsonl].sha256" in m for m in found)   # the runner summarised other bytes


def test_an_invalid_record_fails_the_all_valid_clause(tmp_path, capsys):
    payload = run(build_run(tmp_path, invalid={(0, 1)}))
    assert payload["exit_status"] == 0, messages(payload)       # a consistent invalid record is no integrity problem
    clause = [c for c in payload["clauses"] if c["clause"] == "SIZE, all replicates valid"][0]
    assert clause["passed"] is False and payload["size"]["valid"] == 1 and payload["size"]["rate"] is None


def test_tampered_p_s_and_runner_figures_are_reported(tmp_path, capsys):
    root = build_run(tmp_path)
    part = root / "E1" / "x3_size_r000-002.jsonl"

    def tamper_p(lines):
        record = json.loads(lines[-1])
        record["p_value"] = record["comparison"]["p_value"] = 0.04
        return lines[:-1] + [json.dumps(record) + "\n"]

    original = part.read_bytes()
    _rewrite(part, tamper_p)
    write_hashes(root)
    assert any("recomputed (1+K)/(B'+1)" in m for m in messages(run(root)))
    part.write_bytes(original)

    def tamper_s(lines):
        record = json.loads(lines[-1])
        record["comparison"]["observed"]["changes"][0] += 1e-6
        return lines[:-1] + [json.dumps(record) + "\n"]

    _rewrite(part, tamper_s)
    write_hashes(root)
    found = messages(run(root))
    assert any("observed S is not the mean of its changes" in m or "recomputed S differs" in m for m in found)
    part.write_bytes(original)
    summary = root / "E1" / "x3_power_summary.json"
    data = json.loads(summary.read_text())
    data["summary"]["cells"][1]["rejected"] += 1
    summary.write_text(json.dumps(data))
    write_hashes(root)
    assert any("cells[1].rejected" in m for m in messages(run(root)))


def test_the_report_may_not_be_written_inside_the_clone(tmp_path, capsys):
    root = build_run(tmp_path)
    with pytest.raises(v.UsageError):
        run(root, "--report", str(root / "report.json"))
    assert not (root / "report.json").exists()
    payload = run(root, "--report", str(tmp_path / "report.json"))
    assert json.loads((tmp_path / "report.json").read_text())["exit_status"] == payload["exit_status"] == 0
