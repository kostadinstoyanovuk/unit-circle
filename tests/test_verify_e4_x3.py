"""Tests of verify_e4_x3.py: its E4 kernel against hand-checkable cases and against direct NumPy computations
made here by the H1 section 4 recipe, its random-number protocol against NumPy calls made by hand, and its
detection of each kind of corruption in small development X.3 files made on constructed data (development
master seed 20260930, stream ids from 9000; no registered seed or stream is used except where a refusal is
proved).

Run:  python -m pytest -q tests/test_verify_e4_x3.py      (the script is tools/verify_e4_x3.py)
"""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("verify_e4_x3", HERE.parent / "tools" / "verify_e4_x3.py")
v = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v           # worker processes find the module's functions by name
spec.loader.exec_module(v)

DEV_SEED = 20260930
STREAMS = dict(primary=9400, window32=9401, window48=9402, wild=9404, interval=9405, size_generation=9420,
               size_null=9421, power_generation=9430, power_null=9431)
B_SMALL = 5
N_SMALL = 2


# ------------------------------------------------------------------------------------- kernel by hand

@pytest.mark.parametrize("phi1, phi2, expected", [
    (0.2, -0.5, math.sqrt(0.5)),     # complex pair: sqrt(-phi2)
    (0.3, 0.1, 0.5),                 # roots 0.5 and -0.2 (the H1 base process)
    (-1.5, -0.56, 0.8),              # roots -0.7 and -0.8: copysign picks -0.8
    (0.4, 0.45, 0.9),                # roots 0.9 and -0.5
    (1.0, 0.0, 1.0),                 # unit root, no clipping
    (0.0, 0.0, 0.0),                 # both roots vanish: zero
])
def test_companion_modulus_follows_h1_section_4(phi1, phi2, expected):
    assert float(v.companion_modulus(phi1, phi2)) == pytest.approx(expected, abs=1e-15)


def exact_ar2(c, phi1, phi2, first, n):
    x = np.empty(n)
    x[0], x[1] = first
    for t in range(2, n):
        x[t] = c + phi1 * x[t - 1] + phi2 * x[t - 2]
    return x


def test_rolling_fit_recovers_the_coefficients_of_an_exact_ar2_in_every_window():
    # x[t] = 1 + 0.5 x[t-1] - x[t-2]: complex roots on the unit circle, a sustained oscillation, so every
    # window of 40 holds an exact fit with phi1 = 0.5, phi2 = -1 and M = 1; Delta is zero.
    x = exact_ar2(1.0, 0.5, -1.0, (3.0, -2.0), 60)
    phi1, phi2, modulus, ok = v.rolling_fit(x, 40)
    assert ok.all() and modulus.shape == (21,)
    assert np.allclose(phi1, 0.5, atol=1e-9) and np.allclose(phi2, -1.0, atol=1e-9)
    assert np.allclose(modulus, 1.0, atol=1e-9)
    delta, reason = v.series_delta(x[:48])
    assert reason is None and abs(delta) < 1e-9
    # real roots 0.9 and -0.5, no intercept: M = 0.9 in each of the six windows of a 45-value series
    y = exact_ar2(0.0, 0.4, 0.45, (5.0, -4.0), 45)
    phi1, phi2, modulus, ok = v.rolling_fit(y, 40)
    assert ok.all() and np.allclose(phi1, 0.4, atol=1e-8) and np.allclose(phi2, 0.45, atol=1e-8)
    assert np.allclose(modulus, 0.9, atol=1e-8)


def h1_window_modulus(window_values):
    """The H1 section 4 recipe, written out here: centre each lag column, divide by its root mean square,
    lstsq(rcond=None), undo the scaling."""
    w = np.asarray(window_values, dtype=float)
    y, l1, l2 = w[2:], w[1:-1], w[:-2]
    columns = []
    for lag in (l1, l2):
        centred = lag - lag.mean()
        columns.append(centred / math.sqrt(np.mean(centred * centred)))
    beta, _, rank, _ = np.linalg.lstsq(np.column_stack(columns), y - y.mean(), rcond=None)
    assert rank == 2
    p1 = beta[0] / math.sqrt(np.mean((l1 - l1.mean()) ** 2))
    p2 = beta[1] / math.sqrt(np.mean((l2 - l2.mean()) ** 2))
    return float(v.companion_modulus(p1, p2))


def test_delta_uses_positions_n_minus_1_and_n_minus_9_as_the_h1_recipe_gives_them():
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, 9900, 0, 0])))
    x = rng.standard_normal(70)
    n = len(x)
    by_hand = h1_window_modulus(x[n - 40:n]) - h1_window_modulus(x[n - 48:n - 8])
    delta, reason = v.series_delta(x)
    assert reason is None and delta == pytest.approx(by_hand, abs=1e-13)
    modulus, ok = v.rolling_modulus(x)
    assert ok.all() and modulus[0] == pytest.approx(h1_window_modulus(x[:40]), abs=1e-13)   # position 39
    assert v.series_delta(x[:47])[0] is None and v.series_delta(x[:48])[0] is not None       # n_v >= 48


def test_nearly_collinear_windows_follow_the_h1_lstsq_rank_decision():
    # A noise-free explosive AR(2) (roots 1.05 and 0.3): late windows hold lag columns whose correlation is one
    # to rounding. The normal equations cannot decide their rank; lstsq(rcond=None) on the scaled columns, as
    # H1 section 4 prescribes, finds rank two, and the modulus is that of the H1 recipe.
    x = exact_ar2(0.0, 1.35, -0.315, (1.0, 2.0), 60)
    modulus, ok = v.rolling_modulus(x)
    assert ok.all()
    for end in (52, 53, 54, 59):
        assert modulus[end - 39] == pytest.approx(h1_window_modulus(x[end - 39:end + 1]), abs=1e-9)
    with pytest.raises(v.NullFailure, match="not strictly stable"):
        v.fit_null(x)


def test_a_constant_series_fails_every_window_and_its_null():
    x = np.full(60, 2.5)
    _, _, modulus, ok = v.rolling_fit(x)
    assert not ok.any() and np.isnan(modulus).all()
    delta, reason = v.series_delta(x)
    assert delta is None and "rolling fit failed" in reason
    with pytest.raises(v.NullFailure, match="not identified"):
        v.fit_null(x)
    result = v.e4_comparison([x], DEV_SEED, 9421, [0], 0, 3)
    assert result["status"] == "observed_statistic_failed" and result["indices"] is None


def test_one_failed_window_anywhere_fails_the_statistic():
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, 9901, 0, 0])))
    x = rng.standard_normal(80)
    x[5] = np.nan                                  # only early windows contain it; Delta's two windows do not
    delta, reason = v.series_delta(x)
    assert delta is None and reason.startswith("rolling fit failed at positions [39")


def test_a_unit_root_null_fails_strict_stability():
    # x[t] = 1 + x[t-2] in integers: roots +1 and -1. With 16 regression rows every sum is exact in binary,
    # so the fit is exactly phi1 = 0, phi2 = 1: phi2 - phi1 < 1 fails and M = 1 is not below 1.
    x = [0.0, 3.0]
    for t in range(2, 18):
        x.append(1.0 + x[t - 2])
    with pytest.raises(v.NullFailure, match="not strictly stable"):
        v.fit_null(x)
    # an explosive exact AR(2), roots 1.05 and 0.3, fails as well
    with pytest.raises(v.NullFailure, match="not strictly stable"):
        v.fit_null(exact_ar2(0.0, 1.35, -0.315, (1.0, 2.0), 30))
    # and a failed null fails the comparison before any draw, advancing no generator
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, 9902, 0, 0])))
    stable = rng.standard_normal(60)
    explosive = exact_ar2(0.0, 1.35, -0.315, (1.0, 2.0), 60)
    result = v.e4_comparison([stable, explosive], DEV_SEED, 9421, [0, 1], 0, 4)
    assert result["status"] in ("null_model_failed", "observed_statistic_failed")
    assert result["indices"] is None and result["rng_before"] == {}


def test_null_fit_is_the_intercept_ols_on_all_values_with_centred_residuals():
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, 9903, 0, 0])))
    x = exact_ar2(1.5, 0.3, 0.1, (2.0, 3.0), 99) + rng.standard_normal(99)
    null = v.fit_null(x)
    design = np.column_stack([np.ones(97), x[1:-1], x[:-2]])
    beta = np.linalg.lstsq(design, x[2:], rcond=None)[0]
    assert null["intercept"] == pytest.approx(beta[0], abs=1e-12)
    assert null["phi1"] == pytest.approx(beta[1], abs=1e-12) and null["phi2"] == pytest.approx(beta[2], abs=1e-12)
    raw = x[2:] - design @ beta
    assert np.allclose(null["residuals"], raw - raw.mean(), atol=1e-12) and abs(null["residuals"].mean()) < 1e-15
    assert null["initial"] == (x[0], x[1]) and null["n"] == 99


def test_growth_from_levels_is_400_log_differences_and_stops_on_a_bad_level():
    g = v.growth_from_levels([100.0, 101.0, 99.0])
    assert g == pytest.approx([400 * math.log(1.01), 400 * math.log(99 / 101)], abs=1e-12)
    for bad in ([100.0, 0.0, 99.0], [100.0, -1.0], [100.0, float("nan")], [100.0, float("inf")]):
        with pytest.raises(ValueError):
            v.growth_from_levels(bad)


# -------------------------------------------------------------------------- random-number protocol

def test_draws_and_surrogates_equal_numpy_calls_and_a_scalar_recursion_made_by_hand():
    x, _, _ = v.h1_series(DEV_SEED, 9420, 0, 3)
    series = v.synthetic_vintages(x)
    assert [len(s) for s in series] == [49, 99, 149, 199, 249] and all(np.array_equal(s, x[:len(s)]) for s in series)
    cells = v.surrogate_cells("power", 2)
    assert cells == [20, 21, 22, 23, 24] and v.surrogate_cells("size", 0) == [0, 1, 2, 3, 4]
    result = v.e4_comparison(series, DEV_SEED, 9431, cells, 3, 4)
    deltas = np.empty((4, 5))
    for j, s in enumerate(series):
        gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, 9431, cells[j], 3])))
        assert gen.bit_generator.state == result["rng_before"][str(j)]
        null = v.fit_null(s)
        for b in range(4):
            idx = gen.integers(0, len(s) - 2, size=len(s) - 2)
            assert np.array_equal(idx, result["indices"][j][b])
            path = np.empty(len(s))
            path[0], path[1] = s[0], s[1]
            for t in range(2, len(s)):
                path[t] = null["intercept"] + null["phi1"] * path[t - 1] + null["phi2"] * path[t - 2] + \
                    null["residuals"][idx[t - 2]]
            deltas[b, j] = v.series_delta(path)[0]
        assert gen.bit_generator.state == result["rng_after"][str(j)]
    assert np.allclose(result["changes"], deltas, rtol=0, atol=1e-13)
    assert np.allclose(result["statistics"], deltas.mean(axis=1), rtol=0, atol=1e-13)
    K = int(np.sum(result["statistics"] >= result["S"]))
    assert result["K"] == K and result["p"] == (1 + K) / 5 and result["q"] == K / 4
    assert result["wilson"] == v.wilson(K, 4)


def test_h1_generator_draw_order_initial_pair_and_planted_positions():
    x, before, after = v.h1_series(DEV_SEED, 9430, 1, 0, kappa=1.2)
    gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, 9430, 1, 0])))
    assert gen.bit_generator.state == before
    z = gen.standard_normal(2)
    e = gen.normal(0, 3.5, size=257)
    assert gen.bit_generator.state == after
    v_ = 1225 / 88
    h = v_ / 3
    assert x[0] == pytest.approx(2.5 + math.sqrt(v_) * z[0], abs=1e-14)
    assert x[1] == pytest.approx(2.5 + h / math.sqrt(v_) * z[0] + math.sqrt(v_ - h * h / v_) * z[1], abs=1e-14)
    base, _, _ = v.h1_series(DEV_SEED, 9430, 1, 0)
    first = int(np.flatnonzero(base != x)[0])
    assert first == 41 and np.array_equal(base[:41], x[:41])          # r - 8 = 41 for the onset at 49
    t = 45                                                             # a planted position
    expected = 2.5 * (1 - 1.2 * 0.3 - 1.2 ** 2 * 0.1) + 1.2 * 0.3 * x[t - 1] + 1.2 ** 2 * 0.1 * x[t - 2] + e[t - 2]
    assert x[t] == pytest.approx(expected, abs=1e-12)
    t = 49                                                             # the onset uses the base values
    assert x[t] == pytest.approx(1.5 + 0.3 * x[t - 1] + 0.1 * x[t - 2] + e[t - 2], abs=1e-12)


# ----------------------------------------------------------------------------------- summaries

@pytest.mark.parametrize("k, low, high", [(0, 0.0, 0.01884532637726657),
                                          (13, 0.03837635464915298, 0.10801907929906894)])
def test_wilson_matches_values_computed_with_50_digit_arithmetic(k, low, high):
    lo, hi = v.wilson(k, 200)
    assert abs(lo - low) < 1e-15 and abs(hi - high) < 1e-15


def cells(counts, means, n=200):
    return [v.cell_figures([dict(replicate=i, status="ok", valid=True, rejected=i < r, S=m) for i in range(n)],
                           n, kappa) for kappa, r, m in zip(v.KAPPAS, counts, means)]


def test_size_band_d80_and_decrease_flag():
    for rejected, passed in ((3, False), (4, True), (18, True), (19, False)):
        cell = v.cell_figures([dict(replicate=i, status="ok", valid=True, rejected=i < rejected, S=0.0)
                               for i in range(200)], 200)
        assert v.size_rule(cell, 200)["passed"] is passed
    power = v.power_figures(cells([100, 140, 180, 190], [0.1, 0.2, 0.3, 0.4]))
    assert power["crossing"] == dict(left=1, right=2, weight=0.5)
    assert power["kappa80"] == pytest.approx(1.3) and power["D80"] == pytest.approx(0.25)
    assert v.power_figures(cells([9, 14, 16, 23], [0, 0, 0, 0]))["D80"] is None
    assert v.decrease_flag(86, 67, 200) and not v.decrease_flag(87, 68, 200)     # 1.964 and 1.959 s.e.


# ------------------------------------------------------------------------- development files end to end

def manifest(check, code="a" * 64, seed=DEV_SEED):
    return dict(record_type="manifest", schema=2, created_utc="2026-09-30T00:00:00+00:00", extension="e4",
                check=check, mode="development", master_seed=seed, n_series=N_SMALL, B=B_SMALL,
                kappas=list(v.KAPPAS) if check == "power" else None, settings={}, code_sha256=code,
                e1_code_sha256="b" * 64, identity=dict(commit="constructed", python="3.12.3"),
                lock=dict(satisfied=False), gate=None, prerequisite=None, argv=["constructed"], streams=STREAMS)


def record(check, cell, replicate, seed=DEV_SEED, code="a" * 64):
    kappa = v.KAPPAS[cell] if check == "power" else None
    stream = STREAMS["power_generation" if check == "power" else "size_generation"]
    x, before, after = v.h1_series(seed, stream, cell, replicate, kappa)
    rec = v.build_record(x, seed=seed, streams=STREAMS, check=check, cell_index=cell, replicate=replicate,
                         attempts=B_SMALL, kappa=kappa, code_sha256=code)
    rec["generation_rng_before"], rec["generation_rng_after"] = before, after
    return rec


@pytest.fixture(scope="module")
def design():
    size = [record("size", 0, r) for r in range(N_SMALL)]
    power = [record("power", c, r) for c in range(4) for r in range(N_SMALL)]
    return dict(size=size, power=power)


def write(path, head, records):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for obj in [head, dict(record_type="session", started_utc="2026-09-30T00:00:00+00:00")] + records:
            handle.write(json.dumps(obj) + "\n")
    return path


def run(tmp_path, size, power, *extra, size_manifest=None, power_manifest=None):
    a = write(tmp_path / "x3_size_r0-2.jsonl", size_manifest or manifest("size"), size)
    b = write(tmp_path / "x3_power_c0-3.jsonl", power_manifest or manifest("power"), power)
    report = tmp_path / "report.json"
    payload = v.verify([str(a), str(b), "--development", "--quiet", "--report", str(report)] + list(extra))
    assert json.loads(report.read_text(encoding="utf-8"))["exit_status"] == payload["exit_status"]
    return payload


def messages(payload):
    return " | ".join("%s: %s" % (p["where"], p["message"]) for p in payload["problems"])


def test_a_consistent_development_design_agrees_in_every_check(tmp_path, design):
    payload = run(tmp_path, design["size"], design["power"])
    assert payload["exit_status"] == 0, messages(payload)
    assert payload["coverage"]["present"] == 10 and payload["coverage"]["missing"] == 0
    assert all(r["basis"] == "every attempt regenerated" for r in payload["per_record"])
    assert all(r["regeneration_identical"] for r in payload["per_record"])
    assert payload["size"]["valid"] == N_SMALL and len(payload["power_cells"]) == 4
    assert payload["maxima"]["statistics"] == 0.0 and payload["maxima"]["S"] == 0.0


def test_the_records_hold_each_vintages_fitted_null_and_the_verifier_compares_it(tmp_path, design):
    for rec in design["size"] + design["power"]:
        nulls = rec["null_models"]
        assert sorted(nulls) == [0, 1, 2, 3, 4]
        for j, n_v in enumerate(v.VINTAGES):
            item = nulls[j]
            assert len(item["residuals"]) == n_v - 2 and len(item["coefficients"]) == 2 and len(item["initial"]) == 2
            assert abs(sum(item["residuals"])) < 1e-9                       # centred as H1 section 6 requires
    payload = run(tmp_path, design["size"], design["power"])
    assert payload["exit_status"] == 0, messages(payload)
    assert "replicate.null_models" not in payload["missing_fields"]
    assert payload["maxima"]["nulls"] is not None and payload["maxima"]["nulls"] < 1e-12
    assert all(r["max_diff"]["nulls"] is not None for r in payload["per_record"])


@pytest.mark.parametrize("edit, expected", [
    (lambda item: item["residuals"].__setitem__(5, item["residuals"][5] + 1e-6), "residuals differ"),
    (lambda item: item["residuals"].pop(), "residuals differ"),
    (lambda item: item.update(intercept=item["intercept"] + 1e-6), "fitted null intercept"),
    (lambda item: item.update(coefficients=[item["coefficients"][0] + 1e-6, item["coefficients"][1]]),
     "fitted null phi1"),
    (lambda item: item.update(initial=[item["initial"][0] + 1e-6, item["initial"][1]]), "initial differ"),
    (lambda item: item.update(modulus=item["modulus"] + 1e-6), "fitted null modulus"),
    (lambda item: item.update(residuals=["x"] * len(item["residuals"])), "residuals differ"),
])
def test_an_altered_stored_null_is_found(tmp_path, design, edit, expected):
    size = copy.deepcopy(design["size"])
    edit(size[1]["null_models"][2])
    payload = run(tmp_path, size, design["power"])
    assert payload["exit_status"] == 1 and "vintage 2" in messages(payload) and expected in messages(payload)


def test_records_without_stored_nulls_are_listed_as_a_missing_field_not_a_disagreement(tmp_path, design):
    size = copy.deepcopy(design["size"])
    for rec in size:
        del rec["null_models"]
    payload = run(tmp_path, size, design["power"])
    assert payload["exit_status"] == 0, messages(payload)
    assert payload["missing_fields"] == {"replicate.null_models": len(size)}


def test_sample_and_workers_give_the_same_verdict(tmp_path, design):
    payload = run(tmp_path, design["size"], design["power"], "--sample", "3", "--sample-seed", "20260930",
                  "--workers", "2")
    assert payload["exit_status"] == 0, messages(payload)
    assert len(payload["sample"]["records"]) == 3 and payload["sample"]["seed"] == 20260930
    bases = [r["basis"] for r in payload["per_record"]]
    assert bases.count("every attempt regenerated") == 3 and bases.count("stored surrogate statistics") == 7


def test_an_altered_surrogate_statistic_is_found(tmp_path, design):
    size = copy.deepcopy(design["size"])
    attempt = size[1]["comparison"]["attempts"][3]
    attempt["changes"] = [c + 1e-6 for c in attempt["changes"]]       # consistent with its own mean
    attempt["statistic"] += 1e-6
    payload = run(tmp_path, size, design["power"])
    assert payload["exit_status"] == 1 and "surrogate statistics S_b differ" in messages(payload)


def test_an_altered_p_is_found(tmp_path, design):
    size = copy.deepcopy(design["size"])
    for holder in (size[0], size[0]["comparison"]):
        holder["p_value"] = 1 / (B_SMALL + 1)
    if design["size"][0]["p_value"] == 1 / (B_SMALL + 1):
        for holder in (size[0], size[0]["comparison"]):
            holder["p_value"] = 2 / (B_SMALL + 1)
    payload = run(tmp_path, size, design["power"])
    assert payload["exit_status"] == 1 and "recomputed (1 + K)/(B' + 1)" in messages(payload)


def test_an_altered_input_is_found_with_and_without_a_matching_hash(tmp_path, design):
    size = copy.deepcopy(design["size"])
    size[0]["input"][120] += 0.5
    payload = run(tmp_path, size, design["power"])
    assert payload["exit_status"] == 1 and "does not match input_sha256" in messages(payload)
    size[0]["input_sha256"] = v.input_sha256(size[0]["input"])
    payload = run(tmp_path, size, design["power"])
    text = messages(payload)
    assert payload["exit_status"] == 1 and "observed" in text and "generation coordinates" in text


def test_a_missing_or_duplicated_coordinate_is_found(tmp_path, design):
    payload = run(tmp_path, design["size"][:1], design["power"])
    assert payload["exit_status"] == 1 and "coordinates missing" in messages(payload)
    payload = run(tmp_path, design["size"] + design["size"][:1], design["power"])
    assert payload["exit_status"] == 1 and "appears 2 times" in messages(payload)


def test_mixed_code_hashes_are_found(tmp_path, design):
    power = [dict(r, code_sha256="c" * 64) for r in design["power"]]
    payload = run(tmp_path, design["size"], power, power_manifest=manifest("power", code="c" * 64))
    assert payload["exit_status"] == 1 and "code_sha256" in messages(payload)
    payload = run(tmp_path, design["size"], power)
    assert payload["exit_status"] == 1 and "code_sha256" in messages(payload)


def test_a_record_from_another_seed_is_found_whether_or_not_it_says_so(tmp_path, design):
    other = record("size", 0, 1, seed=DEV_SEED + 1)
    payload = run(tmp_path, [design["size"][0], other], design["power"])
    assert payload["exit_status"] == 1 and "master_seed" in messages(payload)
    relabelled = dict(other, master_seed=DEV_SEED)
    payload = run(tmp_path, [design["size"][0], relabelled], design["power"])
    text = messages(payload)
    assert payload["exit_status"] == 1 and "analysis_rng_before differs" in text
    assert "surrogate statistics S_b differ" in text


def test_a_truncated_attempt_list_is_found(tmp_path, design):
    power = copy.deepcopy(design["power"])
    power[5]["comparison"]["attempts"] = power[5]["comparison"]["attempts"][:-1]
    payload = run(tmp_path, design["size"], power)
    text = messages(payload)
    assert payload["exit_status"] == 1 and "attempts stored, the design needs B = 5" in text


def test_a_truncated_last_line_is_found(tmp_path, design):
    path = write(tmp_path / "x3_size_r0-2.jsonl", manifest("size"), design["size"])
    content = path.read_bytes()
    path.write_bytes(content[:-200])
    b = write(tmp_path / "x3_power_c0-3.jsonl", manifest("power"), design["power"])
    payload = v.verify([str(path), str(b), "--development", "--quiet"])
    assert payload["exit_status"] == 1 and "truncated last line" in messages(payload)


def test_near_ties_are_reported_not_silently_classified(design, monkeypatch):
    monkeypatch.setattr(v, "NEAR_TIE", 10.0)                     # every attempt is now a "near tie"
    rec = design["size"][0]
    result = v.e4_comparison(v.synthetic_vintages(rec["input"]), DEV_SEED, 9421, [0, 1, 2, 3, 4], 0, B_SMALL)
    assert len(result["near_ties"]) == B_SMALL
    assert {t["attempt"] for t in result["near_ties"]} == set(range(B_SMALL))


def test_development_verification_refuses_the_registered_seed_and_streams(tmp_path, design):
    registered = dict(manifest("size"), master_seed=1927)
    payload = run(tmp_path, design["size"], design["power"], size_manifest=registered)
    assert payload["exit_status"] == 1 and "not master seed 1927" in messages(payload)
    low = dict(manifest("size"), streams=dict(STREAMS, size_null=5421))
    payload = run(tmp_path, design["size"], design["power"], size_manifest=low)
    assert payload["exit_status"] == 1 and "registered or low stream ids" in messages(payload)
    assert v.main([str(tmp_path / "x3_size_r0-2.jsonl"), "--sample", "1", "--sample-seed", "1927"]) == 2


def test_a_registered_verification_of_a_development_file_fails(tmp_path, design):
    a = write(tmp_path / "x3_size_r0-2.jsonl", manifest("size"), design["size"])
    payload = v.verify([str(a), "--quiet", "--partial"])
    assert payload["exit_status"] == 1 and "the registered design needs" in messages(payload)


def test_runner_summaries_are_compared_field_by_field(tmp_path, design):
    payload = run(tmp_path, design["size"], design["power"])
    cell = payload["size"]
    summary = dict(summary=dict(cell=dict(cell, mean_S=cell["mean_S"]), bounds=[0.02, 0.09]))
    path = tmp_path / "x3_size_summary.json"
    path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
    good = run(tmp_path, design["size"], design["power"], "--summary", str(path))
    assert good["exit_status"] == 0, messages(good)
    assert good["runner"][0]["compared"] > 0 and not good["runner"][0]["differences"]
    summary["summary"]["cell"]["valid"] = cell["valid"] - 1
    path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
    bad = run(tmp_path, design["size"], design["power"], "--summary", str(path))
    assert bad["exit_status"] == 1 and "cell.valid" in messages(bad)


def test_stored_input_hash_is_the_float64_little_endian_bytes():
    values = [1.0, -2.5, 3.25]
    assert v.input_sha256(values) == hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()
