"""Tests of verify_e2_x3.py: its VAR kernel against hand-checkable cases and against direct NumPy computations
made here by the E2 section 6 recipe, its episode rules and statistic against the section 7 and 8 text, its
random-number protocol and surrogate chain against NumPy calls and a scalar recursion made by hand, the X.3
generator against the section 11 text, and its detection of each kind of corruption in small development X.3 files
(development master seed 20260930, stream ids from 9000; no registered seed or stream is used except where a
refusal is proved). One test runs the research runner in development mode on tiny sizes and checks that this
verifier agrees with its records, its prerequisite record and its summaries.

Run:  python -m pytest -q tests/test_verify_e2_x3.py      (the script is tools/verify_e2_x3.py)
"""
import ast
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
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "tools"))   # worker processes started by "spawn" (Windows) import it by name


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module           # worker processes forked from this one find the functions by name
    spec.loader.exec_module(module)
    return module


v = load("verify_e2_x3", "tools/verify_e2_x3.py")

DEV_SEED = 20260930
STREAMS = dict(primary=9200, window32=9201, window48=9202, fixed=9203, wild=9204, interval=9205,
               size_generation=9220, size_null=9221, power_generation=9230, power_null=9231, at12=9012)
SETTINGS = dict(power_onsets=[77, 148], power_onset_source="development_fixture", retain_window_fits=True)
B_SMALL = 5
N_SMALL = 2
A1_EXACT, A2_EXACT, C_EXACT = np.diag([0.5, -0.8]), -np.eye(2), np.array([1.0, 0.5])


# ------------------------------------------------------------------------------ the verifier stands alone

def test_the_verifier_imports_nothing_from_the_research_packages():
    tree = ast.parse((ROOT / "tools" / "verify_e2_x3.py").read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names <= set(sys.stdlib_module_names) | {"numpy"}, sorted(names - set(sys.stdlib_module_names))


def test_close_and_max_abs_difference_follow_their_stated_tolerance():
    assert v.close(1.0, 1.0 + 5e-10) and not v.close(1.0, 1.0 + 1e-6)
    assert v.close(0.0, 5e-13) and not v.close(0.0, 1e-9)
    assert v.close(None, None) and not v.close(None, 1.0) and v.close(float("nan"), float("nan"))
    assert not v.close(True, 1.0) and not v.close("1", 1.0)
    diff, agree = v.max_abs_difference([1.0, float("nan")], [1.0 + 1e-13, float("nan")])
    assert agree and diff == pytest.approx(1e-13, abs=1e-15)
    assert v.max_abs_difference([1.0, 2.0], [1.0]) == (None, False)
    assert v.max_abs_difference([1.0, float("nan")], [1.0, 2.0]) == (None, False)
    assert v.max_abs_difference(["x"], [1.0]) == (None, False)


def test_the_stored_input_hash_is_the_float64_little_endian_bytes():
    values = [[1.0, -2.5], [3.25, 0.5]]
    assert v.input_sha256(values) == hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


# ------------------------------------------------------------------------------------- kernel by hand

def exact_var2(c, a1, a2, first, n):
    x = np.empty((n, 2))
    x[0], x[1] = first
    for t in range(2, n):
        x[t] = c + a1 @ x[t - 1] + a2 @ x[t - 2]
    return x


def section6_fit(window):
    """The section 6 recipe, written out here: centre each lag column, divide it by its root-mean-square
    magnitude, solve both responses with lstsq(rcond=None), undo the scaling, intercepts from the means."""
    w = np.asarray(window, dtype=float)
    response = w[2:]
    lags = np.hstack((w[1:-1], w[:-2]))
    centred = lags - lags.mean(axis=0)
    scale = np.sqrt(np.mean(centred ** 2, axis=0))
    solution, _, rank, _ = np.linalg.lstsq(centred / scale, response - response.mean(axis=0), rcond=None)
    assert rank == 4
    beta = solution / scale[:, None]
    intercept = response.mean(axis=0) - lags.mean(axis=0) @ beta
    return intercept, beta[:2].T, beta[2:].T


def companion_radius(a1, a2):
    companion = np.block([[a1, a2], [np.eye(2), np.zeros((2, 2))]])
    return float(np.max(np.abs(np.linalg.eigvals(companion))))


def normal_series(*key, n=195):
    gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, *key])))
    return gen.standard_normal((n, 2))


@pytest.mark.parametrize("a1, a2, expected", [
    (np.diag([0.5, -0.8]), np.zeros((2, 2)), 0.8),                        # diagonal VAR(1): max |a_i|
    (np.array([[0.5, 0.2], [0.1, 0.4]]), np.zeros((2, 2)), 0.6),          # coupled VAR(1): eigenvalues 0.6, 0.3
    (np.diag([0.2, 0.0]), np.diag([-0.5, 0.0]), math.sqrt(0.5)),          # complex pair of the first variable
    (np.diag([0.3, 0.4]), np.diag([0.1, 0.45]), 0.9),                     # roots (0.5, -0.2) and (0.9, -0.5)
    (np.eye(2), np.zeros((2, 2)), 1.0),                                   # unit roots are not clipped
])
def test_the_companion_spectral_radius_follows_section_6(a1, a2, expected):
    assert float(v.radius_of(a1, a2)) == pytest.approx(expected, abs=1e-12)


def test_the_spectral_radius_of_a_stack_is_taken_matrix_by_matrix():
    a1 = np.stack([np.diag([0.5, -0.8]), np.diag([0.2, 0.1]), np.diag([-0.9, 0.3])])
    a2 = np.zeros_like(a1)
    out = v.radius_of(a1, a2)
    assert out.shape == (3,) and np.allclose(out, [0.8, 0.2, 0.9], atol=1e-12)
    assert v.radius_of(np.empty((0, 2, 2)), np.empty((0, 2, 2))).shape == (0,)


@pytest.mark.parametrize("phi1, phi2, expected", [
    (0.2, -0.5, math.sqrt(0.5)),     # complex pair: sqrt(-phi2)
    (0.3, 0.1, 0.5),                 # roots 0.5 and -0.2 (H1's base process)
    (-1.5, -0.56, 0.8),              # roots -0.7 and -0.8
    (0.4, 0.45, 0.9),                # roots 0.9 and -0.5
    (1.0, 0.0, 1.0),                 # unit root
    (0.0, 0.0, 0.0),                 # both roots vanish
])
def test_the_closed_form_ar2_modulus_used_by_the_prerequisite_checks(phi1, phi2, expected):
    assert float(v.ar2_closed_modulus(phi1, phi2)) == pytest.approx(expected, abs=1e-15)


@pytest.mark.parametrize("window", [32, 40, 48])
def test_the_rolling_fit_recovers_the_coefficients_of_an_exact_var2_in_every_window(window):
    # x[t] = c + A1 x[t-1] - x[t-2] with A1 = diag(0.5, -0.8): complex roots on the unit circle in each variable,
    # two different frequencies, so every window holds an exact fit of rank four with spectral radius one.
    x = exact_var2(C_EXACT, A1_EXACT, A2_EXACT, ((3.0, -2.0), (1.0, 4.0)), 60)
    fits = v.fit_windows(x, window)
    assert fits["ok"].shape == (1, 60 - window + 1) and fits["ok"].all() and fits["fallbacks"] == 0
    assert np.allclose(fits["intercept"][0], C_EXACT, atol=1e-8)
    assert np.allclose(fits["a1"][0], A1_EXACT, atol=1e-8) and np.allclose(fits["a2"][0], A2_EXACT, atol=1e-8)
    modulus, ok, _ = v.rolling_modulus(x[None], window)
    assert ok.all() and np.allclose(modulus, 1.0, atol=1e-8)


def test_every_window_equals_the_section_6_recipe_made_by_hand():
    x = normal_series(9900, 0, n=70)
    fits = v.fit_windows(x)
    assert fits["ok"].all() and fits["fallbacks"] == 0
    for w in (0, 9, 30):                                      # window w holds positions w, ..., w + 39
        intercept, a1, a2 = section6_fit(x[w:w + 40])
        assert np.allclose(fits["intercept"][0, w], intercept, rtol=0, atol=1e-11)
        assert np.allclose(fits["a1"][0, w], a1, rtol=0, atol=1e-11)
        assert np.allclose(fits["a2"][0, w], a2, rtol=0, atol=1e-11)
    modulus, _, _ = v.rolling_modulus(x[None])
    assert modulus[0, 9] == pytest.approx(companion_radius(*section6_fit(x[9:49])[1:]), abs=1e-12)
    fallback = v.lstsq_fit(x[9:49])                           # the recipe itself, used where the closed form fails
    for mine, theirs in zip(fallback, section6_fit(x[9:49])):
        assert np.allclose(mine, theirs, rtol=0, atol=1e-12)


def test_several_series_are_fitted_at_once_in_chunks_with_the_same_numbers():
    stack = np.stack([normal_series(9901, i, n=60) for i in range(5)])
    together = v.fit_windows(stack, chunk=2)
    for i in range(5):
        alone = v.fit_windows(stack[i])
        assert np.array_equal(together["ok"][i], alone["ok"][0])
        assert np.allclose(together["a1"][i], alone["a1"][0], rtol=0, atol=1e-13)
        assert np.allclose(together["intercept"][i], alone["intercept"][0], rtol=0, atol=1e-13)


def test_collinear_constant_and_non_finite_windows_fail():
    first = normal_series(9902, 0, n=60)[:, 0]
    collinear = np.column_stack([first, 2 * first])           # lag block of rank two, not four
    fits = v.fit_windows(collinear)
    assert not fits["ok"].any() and fits["fallbacks"] == 21 and np.isnan(fits["a1"]).all()
    fits = v.fit_windows(np.full((60, 2), 2.5))               # zero scale: nothing is attempted
    assert not fits["ok"].any() and fits["fallbacks"] == 0
    x = normal_series(9902, 1, n=60)
    x[5, 0] = np.nan                                          # only the windows that contain position 5 fail
    fits = v.fit_windows(x)
    assert not fits["ok"][0, :6].any() and fits["ok"][0, 6:].all()
    modulus, ok, _ = v.rolling_modulus(x[None])
    assert np.isnan(modulus[0, :6]).all() and np.isfinite(modulus[0, 6:]).all()


def test_nearly_collinear_windows_follow_the_section_6_lstsq_rank_decision():
    base = normal_series(9903, 0, n=60)
    x = np.column_stack([base[:, 0], 2 * base[:, 0] + 1e-6 * base[:, 1]])
    fits = v.fit_windows(x)
    assert fits["ok"].all() and fits["fallbacks"] == 21       # the closed form is not trusted: lstsq decides
    for w in (0, 7, 20):
        intercept, a1, a2 = section6_fit(x[w:w + 40])
        assert np.allclose(fits["a1"][0, w], a1, rtol=1e-6, atol=1e-6)
        assert np.allclose(fits["a2"][0, w], a2, rtol=1e-6, atol=1e-6)


# --------------------------------------------------------------- episodes and the statistic (sections 7-8)

def hand_onsets(g):
    """Section 7 written out here: runs of two or more quarters with g < 0, merged when onset - previous end <= 8
    (chained, the first onset kept); returns the onsets."""
    runs, start = [], None
    for t, value in enumerate(list(g) + [1.0]):               # a sentinel closes a run that reaches the end
        if value < 0 and start is None:
            start = t
        elif not value < 0 and start is not None:
            if t - start >= 2:
                runs.append([start, t - 1])
            start = None
    merged = []
    for run in runs:
        if merged and run[0] - merged[-1][1] <= 8:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    return [run[0] for run in merged]


def test_runs_and_merged_episodes_follow_section_7():
    g = np.ones(90)
    for start, end in ((10, 11), (19, 20), (29, 30), (40, 40), (48, 50), (58, 59), (67, 68), (78, 79)):
        g[start:end + 1] = -1.0
    g[85] = 0.0                                               # a zero is not negative
    assert v.negative_runs(g) == [(10, 11), (19, 20), (29, 30), (48, 50), (58, 59), (67, 68), (78, 79)]
    # 19 - 11 = 8 merges; 29 - 20 = 9 does not; 58 - 50 = 8 and 67 - 59 = 8 chain; the run of 78 is 10 after 68
    assert v.merged_episodes(g) == [(10, 20), (29, 30), (48, 68), (78, 79)]
    assert [start for start, _ in v.merged_episodes(g)] == hand_onsets(g)
    assert v.negative_runs([-1.0, 0.0, -1.0, -1.0]) == [(2, 3)]
    assert v.negative_runs([-1.0, 1.0, -1.0]) == []
    assert v.negative_runs([1.0, -1.0, -1.0]) == [(1, 2)]     # a run that reaches the end of the series counts


def test_the_two_implementations_of_the_episode_rule_agree_on_design_series():
    for replicate in range(8):
        g = v.design_series(DEV_SEED, 9220, 0, replicate)[0][:, 0]
        assert [start for start, _ in v.merged_episodes(g)] == hand_onsets(g)


def test_pre_onset_changes_use_positions_r_minus_1_and_r_minus_9():
    modulus_row = [float((t - 39) ** 2) for t in range(39, 195)]          # M(t) = (t - 39)^2 for t = 39, ..., 194
    eligible, ineligible, changes = v.pre_onset_values(modulus_row, [47, 48, 100])
    assert (eligible, ineligible) == ([48, 100], [47])                    # onset 47 needs M(38), which does not exist
    assert changes == [(47 - 39) ** 2 - (39 - 39) ** 2, (99 - 39) ** 2 - (91 - 39) ** 2]
    assert v.mean_of([1.0, 2.0, 4.5]) == pytest.approx(7.5 / 3)


def hand_deltas(path, onsets):
    """M(r - 1) - M(r - 9) for each onset r >= 48, the two windows fitted by the section 6 recipe and the
    eigenvalues of the companion matrix taken by hand."""
    out = []
    for r in onsets:
        if r - 9 < 39:
            continue
        later = companion_radius(*section6_fit(path[r - 40:r])[1:])           # the window ending at r - 1
        earlier = companion_radius(*section6_fit(path[r - 48:r - 8])[1:])     # the window ending at r - 9
        out.append(later - earlier)
    return out


def test_the_observed_statistic_is_the_mean_of_the_pre_onset_changes_as_section_8_gives_them():
    x = v.design_series(DEV_SEED, 9220, 0, 3)[0]
    result = v.observed_result(x, fixed=(47, 60, 100, 150))
    assert result["status"] == "ok" and result["eligible"] == [60, 100, 150] and result["ineligible"] == [47]
    by_hand = hand_deltas(x, [60, 100, 150])
    assert result["changes"] == pytest.approx(by_hand, abs=1e-12)
    assert result["S"] == pytest.approx(math.fsum(by_hand) / 3, abs=1e-12)


def test_no_eligible_onset_means_not_estimable_without_fitting_anything():
    constant = np.full((195, 2), 2.5)                         # every window would fail, but none is needed
    result = v.observed_result(constant, fixed=(30, 47))
    assert result["status"] == "observed_not_estimable" and result["S"] is None
    assert result["ineligible"] == [30, 47] and result["eligible"] == []
    assert v.observed_result(constant)["status"] == "observed_not_estimable"      # no episode at all


def test_one_failed_window_anywhere_fails_the_statistic_as_reading_16_has_it():
    x = v.design_series(DEV_SEED, 9220, 0, 4)[0].copy()
    x[5, 0] = np.nan                                          # the windows of the onset's own pair are fine
    result = v.observed_result(x, fixed=(77,))
    assert result["status"] == "observed_statistic_failed" and result["S"] is None
    assert result["error"].startswith("window fit failed at positions [39, 40, 41, 42, 43]")
    paths = np.stack([v.design_series(DEV_SEED, 9220, 0, 5)[0], x])
    outcome = v.attempt_results(paths, "fixed", (77,))
    assert outcome["status"] == ["retained", "failed"]


def test_surrogate_paths_are_retained_dropped_or_failed_as_section_9_has_it():
    good = v.design_series(DEV_SEED, 9220, 0, 6)[0]
    positive = np.abs(good) + 1.0                             # g > 0 everywhere: no episode in primary mode
    with_nan = good.copy()
    with_nan[100, 1] = np.nan
    constant = np.full((195, 2), 1.0)
    paths = np.stack([good, positive, with_nan, constant])
    primary = v.attempt_results(paths, "primary")
    assert primary["status"][1:] == ["no_eligible_episode", "failed", "no_eligible_episode"]
    assert primary["status"][0] in ("retained", "no_eligible_episode")
    fixed = v.attempt_results(paths, "fixed", (77, 148))
    assert fixed["status"] == ["retained", "retained", "failed", "failed"]
    assert fixed["eligible"][0] == (77, 148) and len(fixed["changes"][0]) == 2
    assert fixed["statistic"][0] == pytest.approx(math.fsum(hand_deltas(good, [77, 148])) / 2, abs=1e-12)
    assert np.isnan(fixed["statistic"][2:]).all()


# ------------------------------------------------------------------------------------------- the null

def hand_null(x):
    design = np.column_stack([np.ones(len(x) - 2), x[1:-1], x[:-2]])      # 1, X[t-1], X[t-2]
    beta = np.linalg.lstsq(design, x[2:], rcond=None)[0]                  # (5, 2)
    residuals = x[2:] - design @ beta
    return beta[0], beta[1:3].T, beta[3:5].T, residuals - residuals.mean(axis=0)


def test_the_null_fit_is_the_intercept_ols_on_all_observations_with_centred_residuals():
    x = v.design_series(DEV_SEED, 9220, 0, 7)[0]
    null = v.fit_null(x)
    c, a1, a2, e = hand_null(x)
    assert np.allclose(null["intercept"], c, atol=1e-11)
    assert np.allclose(null["a1"], a1, atol=1e-11) and np.allclose(null["a2"], a2, atol=1e-11)
    assert null["residuals"].shape == (193, 2) and np.allclose(null["residuals"], e, atol=1e-11)
    assert np.abs(null["residuals"].mean(axis=0)).max() < 1e-14
    assert np.array_equal(null["initial"][0], x[0]) and np.array_equal(null["initial"][1], x[1]) and null["n"] == 195
    assert null["modulus"] == pytest.approx(companion_radius(a1, a2), abs=1e-11) and null["modulus"] < 1
    # the raw residuals are exactly orthogonal to the regressors, so removing their mean changes only the intercept
    raw = x[2:] - null["intercept"] - x[1:-1] @ null["a1"].T - x[:-2] @ null["a2"].T
    assert np.allclose(raw - raw.mean(axis=0), null["residuals"], atol=1e-12)


def test_a_null_that_is_not_strictly_stable_or_not_identified_fails_before_any_draw():
    gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, 9904, 0])))
    noise = gen.standard_normal((195, 2))
    explosive = np.zeros((195, 2))
    for t in range(2, 195):
        explosive[t] = np.array([1.0, 0.0]) + np.diag([1.1, 0.5]) @ explosive[t - 1] + noise[t]
    explosive = explosive[:60]
    with pytest.raises(v.NullFailure, match="not strictly stable"):
        v.fit_null(explosive)
    with pytest.raises(v.NullFailure, match="not identified"):
        v.fit_null(np.full((195, 2), 2.5))
    nan = v.design_series(DEV_SEED, 9220, 0, 8)[0].copy()
    nan[3, 1] = np.nan
    with pytest.raises(v.NullFailure, match="non-finite value"):
        v.fit_null(nan)
    with pytest.raises(v.NullFailure, match="too few"):
        v.fit_null(np.zeros((5, 2)))
    # a failed null fails the comparison before any draw: the generator is not advanced
    result = v.e2_comparison(explosive, mode="fixed", fixed=(48,), seed=DEV_SEED, stream=9231, cell=0,
                             replicate=0, attempts=3)
    assert result["status"] in ("null_model_failed", "observed_statistic_failed") and result["indices"] is None
    assert result["rng_before"] is None and result["rng_after"] is None


def test_a_spectral_radius_of_exactly_one_is_not_strictly_stable(monkeypatch):
    x = v.design_series(DEV_SEED, 9220, 0, 7)[0]
    monkeypatch.setattr(v, "radius_of", lambda a1, a2: np.float64(1.0))
    with pytest.raises(v.NullFailure, match="not strictly stable"):
        v.fit_null(x)
    monkeypatch.setattr(v, "radius_of", lambda a1, a2: np.float64(np.nextafter(1.0, 0.0)))
    assert v.fit_null(x)["modulus"] < 1


# -------------------------------------------------------------------------- random-number protocol

def series_with_eligible_episode():
    """The first size-design series (development streams) whose observed episodes include an eligible onset."""
    for replicate in range(40):
        x = v.design_series(DEV_SEED, 9220, 0, replicate)[0]
        if any(o >= 48 for o in hand_onsets(x[:, 0])):
            try:
                v.fit_null(x)
            except v.NullFailure:
                continue
            return replicate, x
    raise AssertionError("no series with an eligible episode among 40")


def hand_comparison(x, mode, fixed, stream, cell, replicate, attempts):
    """The whole comparison written out here: NumPy calls for the draws, the scalar recursion of section 9, the
    windows fitted by lstsq, the eigenvalues taken by hand."""
    onsets = list(fixed) if mode == "fixed" else hand_onsets(x[:, 0])
    observed = hand_deltas(x, onsets)
    assert observed
    S = math.fsum(observed) / len(observed)
    c, a1, a2, e = hand_null(x)
    gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, stream, cell, replicate])))
    before = copy.deepcopy(gen.bit_generator.state)
    draws, statistics = [], []
    for b in range(attempts):
        idx = gen.integers(0, 193, size=193)
        draws.append(idx)
        path = np.empty_like(x)
        path[0], path[1] = x[0], x[1]
        for t in range(2, 195):
            path[t] = c + a1 @ path[t - 1] + a2 @ path[t - 2] + e[idx[t - 2]]
        path_onsets = list(fixed) if mode == "fixed" else hand_onsets(path[:, 0])
        deltas = hand_deltas(path, path_onsets)
        statistics.append(math.fsum(deltas) / len(deltas) if deltas else None)
    return dict(S=S, draws=np.array(draws), statistics=statistics, before=before, after=gen.bit_generator.state)


@pytest.mark.parametrize("mode", ["primary", "fixed"])
def test_draws_regenerations_and_p_equal_numpy_calls_and_a_scalar_recursion_made_by_hand(mode):
    if mode == "primary":
        replicate, x = series_with_eligible_episode()
        stream, cell, fixed = 9221, 0, None
    else:
        replicate, cell = 2, 3
        x = v.design_series(DEV_SEED, 9230, cell, replicate, 1.6, v.POWER_ONSETS)[0]
        stream, fixed = 9231, v.POWER_ONSETS
    attempts = 6
    mine = v.e2_comparison(x, mode=mode, fixed=fixed, seed=DEV_SEED, stream=stream, cell=cell, replicate=replicate,
                           attempts=attempts)
    by_hand = hand_comparison(x, mode, fixed, stream, cell, replicate, attempts)
    assert mine["rng_before"] == by_hand["before"] and mine["rng_after"] == by_hand["after"]
    assert mine["rng_fresh"] == by_hand["before"]             # nothing is drawn before the first attempt
    assert np.array_equal(mine["indices"], by_hand["draws"])
    assert mine["observed"]["S"] == pytest.approx(by_hand["S"], abs=1e-12)
    kinds = ["no_eligible_episode" if s is None else "retained" for s in by_hand["statistics"]]
    assert mine["attempt_status"] == kinds
    kept = [s for s in by_hand["statistics"] if s is not None]
    assert mine["retained"] == len(kept) and mine["no_episode"] == attempts - len(kept) and mine["failed"] == 0
    assert np.allclose(mine["statistics"][[k == "retained" for k in kinds]], kept, rtol=0, atol=1e-11)
    exceed = sum(1 for s in kept if s >= by_hand["S"])
    assert mine["status"] == "ok" and mine["K"] == exceed and mine["attempted"] == attempts
    assert mine["p"] == (1 + exceed) / (len(kept) + 1) and mine["q"] == exceed / len(kept)
    assert mine["wilson"] == v.wilson(exceed, len(kept)) and mine["grid"] == 1 / (len(kept) + 1)


def test_regeneration_is_the_scalar_recursion_with_the_selected_residual_rows():
    x = v.design_series(DEV_SEED, 9220, 0, 7)[0]
    null = v.fit_null(x)
    gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, 9221, 0, 7])))
    indices = v.draw_indices(gen, 193, 3)
    assert indices.shape == (3, 193)
    again = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, 9221, 0, 7])))
    assert all(np.array_equal(indices[b], again.integers(0, 193, size=193)) for b in range(3))
    paths = v.regenerate(null, indices)
    assert paths.shape == (3, 195, 2)
    for b in range(3):
        path = np.empty((195, 2))
        path[0], path[1] = null["initial"]
        for t in range(2, 195):
            path[t] = null["intercept"] + null["a1"] @ path[t - 1] + null["a2"] @ path[t - 2] + \
                null["residuals"][indices[b, t - 2]]
        assert np.allclose(paths[b], path, rtol=0, atol=1e-12)


def test_the_random_number_streams_are_those_of_annex_a_and_the_generator_is_numpys_pcg64():
    assert v.REGISTERED_STREAMS == dict(primary=5200, window32=5201, window48=5202, fixed=5203, wild=5204,
                                        interval=5205, size_generation=5220, size_null=5221, power_generation=5230,
                                        power_null=5231, at12=2012)
    gen = v.generator(1927, 5221, 0, 7)
    twin = np.random.Generator(np.random.PCG64(np.random.SeedSequence([1927, 5221, 0, 7])))
    assert np.array_equal(gen.integers(0, 193, size=193), twin.integers(0, 193, size=193))


# ---------------------------------------------------------------------------- the X.3 generator (section 11)

def test_the_design_constants_are_those_of_the_generating_var():
    sigma = np.array(v.SIGMA)
    factor = np.array(v.SIGMA_FACTOR)
    assert np.allclose(factor @ factor.T, sigma, atol=1e-15) and sigma[0, 1] / math.sqrt(sigma[0, 0] * sigma[1, 1]) \
        == pytest.approx(-0.5)
    # the stationary AR(2) with a = 0.3, b = 0.1: variance sigma^2 (1 - b)/((1 + b)((1 - b)^2 - a^2)) = sigma^2 100/88
    # and first autocorrelation a/(1 - b) = 1/3
    assert v.DESIGN_SCALE == pytest.approx(0.9 / (1.1 * (0.81 - 0.09)), abs=1e-15) == pytest.approx(100 / 88)
    assert v.TIME_CORRELATION[0][1] == pytest.approx(0.3 / 0.9, abs=1e-15)
    assert v.MU == (2.5, 0.0) and v.BASE_INTERCEPT == pytest.approx((2.5 * (1 - 0.3 - 0.1), 0.0))


def test_the_generator_draw_order_initial_vectors_and_planted_positions_follow_section_11():
    x, before, after = v.design_series(DEV_SEED, 9230, 1, 0, 1.2, v.POWER_ONSETS)
    gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, 9230, 1, 0])))
    assert gen.bit_generator.state == before
    z = gen.standard_normal(4)
    noise = gen.standard_normal((193, 2))
    assert gen.bit_generator.state == after
    factor = np.array([[3.5, 0.0], [-0.5, math.sqrt(0.75)]])
    e = noise @ factor.T
    chol = np.linalg.cholesky(np.kron(np.array([[1.0, 1 / 3], [1 / 3, 1.0]]),
                                      (100 / 88) * np.array([[12.25, -1.75], [-1.75, 1.0]])))
    start = np.array([2.5, 0.0, 2.5, 0.0]) + chol @ z
    assert np.allclose(x[0], start[:2], atol=1e-13) and np.allclose(x[1], start[2:], atol=1e-13)
    base = v.design_series(DEV_SEED, 9230, 1, 0, 1.0, v.POWER_ONSETS)[0]
    assert np.array_equal(base, v.design_series(DEV_SEED, 9230, 1, 0, 1.0, ())[0])     # kappa = 1: base values
    first = int(np.flatnonzero((base != x).any(axis=1))[0])
    assert first == 69 and np.array_equal(base[:69], x[:69])                          # r - 8 = 69 for the onset 77
    kappa = 1.2
    for t in (69, 72, 76, 140, 147):                          # planted positions r - 8, ..., r - 1
        a, b = kappa * 0.3, kappa ** 2 * 0.1
        expected = np.array([(1 - a - b) * 2.5, 0.0]) + a * x[t - 1] + b * x[t - 2] + e[t - 2]
        assert np.allclose(x[t], expected, atol=1e-12), t
    for t in (77, 148, 68, 100):                              # the onset itself and unplanted positions: base values
        expected = np.array([1.5, 0.0]) + 0.3 * x[t - 1] + 0.1 * x[t - 2] + e[t - 2]
        assert np.allclose(x[t], expected, atol=1e-12), t


def test_the_h1_generator_forms_of_the_reduction_fixture_agree_to_rounding():
    text = v.h1_series(DEV_SEED, 9220, 1, 0, form="text")
    closed = v.h1_series(DEV_SEED, 9220, 1, 0, form="closed")
    assert text.shape == (259,) and np.max(np.abs(text - closed)) < 1e-12
    gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, 9220, 1, 0])))
    z = gen.standard_normal(2)
    e = gen.normal(0, 3.5, size=257)
    v_ = 1225 / 88
    h = v_ / 3
    assert closed[0] == pytest.approx(2.5 + math.sqrt(v_) * z[0], abs=1e-13)
    assert closed[1] == pytest.approx(2.5 + h / math.sqrt(v_) * z[0] + math.sqrt(v_ - h * h / v_) * z[1], abs=1e-13)
    assert closed[2] == pytest.approx(1.5 + 0.3 * closed[1] + 0.1 * closed[0] + e[0], abs=1e-12)


def test_the_prerequisite_computations_hold_on_constructed_inputs():
    result = v.at12_recompute(DEV_SEED, 9012, 3000)
    gen = np.random.Generator(np.random.PCG64(np.random.SeedSequence([DEV_SEED, 9012, 1])))
    phi1 = gen.uniform(-3, 3, 3000)
    phi2 = gen.uniform(-2, 2, 3000)
    assert result["draws"] == 3000 and result["skipped"] == int(np.sum(np.abs(phi1 ** 2 + 4 * phi2) < 1e-8))
    assert result["diagonal_passed"] and result["ar2_passed"] and result["ar2_error"] < 1e-9
    rows = v.reduction_recompute(v.h1_series(DEV_SEED, 9220, 1, 0, form="closed"))
    assert [row["window"] for row in rows] == [32, 40, 48] and [row["fitted"] for row in rows] == [228, 220, 212]
    assert all(row["passed"] and row["warmup_same"] and row["max_abs_difference"] < 1e-10 for row in rows)


# ----------------------------------------------------------------------------------- summaries

@pytest.mark.parametrize("k, low, high", [(0, 0.0, 0.01884532637726657),
                                          (13, 0.03837635464915298, 0.10801907929906894)])
def test_wilson_matches_values_computed_with_50_digit_arithmetic(k, low, high):
    lo, hi = v.wilson(k, 200)
    assert abs(lo - low) < 1e-15 and abs(hi - high) < 1e-15


def entries(rejected, n=200, valid=None, mean=0.0):
    valid = n if valid is None else valid
    return [dict(replicate=i, status="ok" if i < valid else "observed_not_estimable", valid=i < valid,
                 rejected=i < rejected, S=mean if i < valid else None) for i in range(n)]


def power_cells(counts, means, n=200):
    return [v.cell_figures(entries(r, n, mean=m), n, kappa) for kappa, r, m in zip(v.KAPPAS, counts, means)]


def test_size_band_is_exact_and_needs_every_replicate_valid():
    for rejected, passed in ((3, False), (4, True), (18, True), (19, False)):      # 0.02 and 0.09 inclusive
        cell = v.cell_figures(entries(rejected), 200)
        assert v.size_rule(cell, 200) == dict(band=passed, all_valid=True, passed=passed)
    cell = v.cell_figures(entries(10, valid=199), 200)                              # one invalid replicate
    rule = v.size_rule(cell, 200)
    assert cell["valid"] == 199 and cell["failures"] == {"observed_not_estimable": 1} and not cell["complete"]
    assert cell["accounting_bounds"] == [10 / 200, 11 / 200] and cell["rate"] is None
    assert rule["passed"] is False and rule["all_valid"] is False and rule["band"] is False


def test_a_rejection_is_a_valid_raw_p_at_most_one_twentieth():
    assert v.ALPHA == v.Fraction(1, 20) and v.Fraction(1 + 49, 999 + 1) <= v.ALPHA < v.Fraction(1 + 50, 999 + 1)


def test_d80_is_the_first_raw_crossing_and_may_be_undefined():
    power = v.power_figures(power_cells([100, 140, 180, 190], [0.1, 0.2, 0.3, 0.4]))
    assert power["crossing"] == dict(left=1, right=2, weight=0.5) and power["d80_status"] == "defined"
    assert power["kappa80"] == pytest.approx(1.3) and power["D80"] == pytest.approx(0.25)
    first = v.power_figures(power_cells([170, 180, 190, 195], [0.1, 0.2, 0.3, 0.4]))
    assert first["crossing"] == dict(left=0, right=0, weight=0.0) and first["D80"] == pytest.approx(0.1)
    undefined = v.power_figures(power_cells([9, 14, 16, 23], [0, 0, 0, 0]))
    assert undefined["D80"] is None and "no kappa <= 1.6 reaches 0.80" in undefined["d80_status"]
    incomplete = [v.cell_figures(entries(10, valid=199), 200, 1.0)] + power_cells([9, 14, 16], [0, 0, 0])[1:]
    assert v.power_figures(incomplete)["d80_status"].startswith("undefined: a cell is invalid")


def test_the_adjacent_decrease_flag_is_decided_in_exact_rationals():
    assert v.decrease_flag(86, 67, 200) and not v.decrease_flag(87, 68, 200)        # 1.964 and 1.959 s.e.
    assert not v.decrease_flag(67, 86, 200) and not v.decrease_flag(50, 50, 200)    # an increase is never flagged
    power = v.power_figures(power_cells([86, 67, 100, 120], [0, 0, 0, 0]))
    assert power["decrease_flags"] == [True, False, False] and power["all_valid"]
    assert [round(a["difference"], 3) for a in power["adjacent"]] == [-0.095, 0.165, 0.1]


# ------------------------------------------------------------------------- development files end to end

def manifest(check, code="a" * 64, seed=DEV_SEED):
    return dict(record_type="manifest", schema=2, created_utc="2026-09-30T00:00:00+00:00", extension="e2",
                check=check, mode="development", master_seed=seed, n_series=N_SMALL, B=B_SMALL,
                kappas=list(v.KAPPAS) if check == "power" else None, settings=copy.deepcopy(SETTINGS),
                code_sha256=code, e1_code_sha256="b" * 64, identity_option=v.IDENTITY_OPTION,
                identity=dict(commit="constructed", python="3.12.3", dirty=False),
                imported=dict(ext_commit="constructed", ext_dirty=False), lock=dict(satisfied=False), gate=None,
                prerequisite=None, argv=["constructed"], streams=dict(STREAMS))


def record(check, cell, replicate, seed=DEV_SEED, code="a" * 64):
    if check == "power":
        kappa, stream, onsets = v.KAPPAS[cell], STREAMS["power_generation"], v.POWER_ONSETS
    else:
        kappa, stream, onsets = None, STREAMS["size_generation"], ()
    x, before, after = v.design_series(seed, stream, cell, replicate, 1.0 if kappa is None else kappa, onsets)
    return v.build_record(x, seed=seed, streams=STREAMS, check=check, cell_index=cell, replicate=replicate,
                          attempts=B_SMALL, kappa=kappa, onsets=v.POWER_ONSETS, mode="development", code_sha256=code,
                          settings=copy.deepcopy(SETTINGS), generation_states=(before, after))


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


def test_the_constructed_design_is_what_the_corruption_tests_assume(design):
    assert [r["status"] for r in design["size"]] == ["ok"] * N_SMALL
    assert [r["status"] for r in design["power"]] == ["ok"] * (4 * N_SMALL)
    assert [r["kappa"] for r in design["power"]] == [1.0, 1.0, 1.2, 1.2, 1.4, 1.4, 1.6, 1.6]
    assert all("kappa" not in r for r in design["size"])
    assert all(len(r["comparison"]["attempts"]) == B_SMALL for r in design["size"] + design["power"])


def test_a_consistent_development_design_agrees_in_every_check(tmp_path, design):
    payload = run(tmp_path, design["size"], design["power"])
    assert payload["exit_status"] == 0, messages(payload)
    assert payload["coverage"]["present"] == 10 and payload["coverage"]["missing"] == 0
    assert all(r["basis"] == "every attempt regenerated" for r in payload["per_record"])
    assert all(r["regeneration_identical"] for r in payload["per_record"])
    assert payload["size"]["valid"] == N_SMALL and len(payload["power_cells"]) == 4
    assert payload["maxima"]["statistics"] == 0.0 and payload["maxima"]["S"] == 0.0
    assert payload["maxima"]["regeneration"] == 0.0 and payload["maxima"]["fits"] < 1e-12
    assert payload["verdicts"]["size"]["registered"] is False and payload["verdicts"]["size"]["passed"] is False


def test_the_records_hold_each_windows_fit_and_the_fitted_null_and_the_verifier_compares_them(tmp_path, design):
    for rec in design["size"] + design["power"]:
        fits, null = rec["window_fits"], rec["comparison"]["null_model"]
        assert (fits["window"], fits["first_position"], len(fits["modulus"])) == (40, 39, 156)
        assert np.array(fits["A1"]).shape == (156, 2, 2) and np.array(fits["intercept"]).shape == (156, 2)
        assert np.array(null["residuals"]).shape == (193, 2) and np.abs(np.sum(null["residuals"], axis=0)).max() < 1e-9
        assert np.array(null["coefficients"]).shape == (2, 2, 2) and np.array(null["initial"]).shape == (2, 2)
    payload = run(tmp_path, design["size"], design["power"])
    assert payload["exit_status"] == 0, messages(payload)
    assert payload["missing_fields"] == {} and payload["maxima"]["nulls"] < 1e-12
    assert all(r["max_diff"]["nulls"] is not None and r["max_diff"]["fits"] is not None
               for r in payload["per_record"])


@pytest.mark.parametrize("edit, expected", [
    (lambda item: item["residuals"][5].__setitem__(1, item["residuals"][5][1] + 1e-6), "fitted null residuals differ"),
    (lambda item: item["residuals"].pop(), "fitted null residuals differ"),
    (lambda item: item["intercept"].__setitem__(0, item["intercept"][0] + 1e-6), "fitted null intercept differ"),
    (lambda item: item["coefficients"][0][0].__setitem__(0, item["coefficients"][0][0][0] + 1e-6),
     "fitted null a1 differ"),
    (lambda item: item["coefficients"][1][1].__setitem__(1, item["coefficients"][1][1][1] + 1e-6),
     "fitted null a2 differ"),
    (lambda item: item["initial"][0].__setitem__(0, item["initial"][0][0] + 1e-6), "fitted null initial0 differ"),
    (lambda item: item["residual_mean_removed"].__setitem__(0, item["residual_mean_removed"][0] + 1e-6),
     "fitted null residual_mean_removed differ"),
    (lambda item: item.update(modulus=item["modulus"] + 1e-6), "fitted null modulus"),
    (lambda item: item.update(residuals=[["x", "y"]] * 193), "fitted null residuals differ"),
])
def test_an_altered_stored_null_is_found(tmp_path, design, edit, expected):
    power = copy.deepcopy(design["power"])
    edit(power[5]["comparison"]["null_model"])
    payload = run(tmp_path, design["size"], power)
    assert payload["exit_status"] == 1 and "power cell 2, replicate 1" in messages(payload)
    assert expected in messages(payload)


@pytest.mark.parametrize("edit, expected", [
    (lambda fits: fits["modulus"].__setitem__(10, fits["modulus"][10] + 1e-6), "window_fits modulus differ"),
    (lambda fits: fits["A1"][7][0].__setitem__(1, fits["A1"][7][0][1] + 1e-6), "window_fits A1 differ"),
    (lambda fits: fits["A2"].pop(), "window_fits A2 differ"),
    (lambda fits: fits["intercept"][100].__setitem__(1, fits["intercept"][100][1] - 1e-6),
     "window_fits intercept differ"),
    (lambda fits: fits.update(first_position=40), "first position 40; expected 40 and 39"),
    (lambda fits: fits.update(error="ValueError: constructed"), "records an error (ValueError: constructed)"),
])
def test_altered_window_fits_are_found(tmp_path, design, edit, expected):
    size = copy.deepcopy(design["size"])
    edit(size[1]["window_fits"])
    payload = run(tmp_path, size, design["power"])
    assert payload["exit_status"] == 1 and "size cell 0, replicate 1" in messages(payload)
    assert expected in messages(payload)


def test_records_without_stored_nulls_or_window_fits_are_listed_as_missing_fields_not_disagreements(tmp_path, design):
    size = copy.deepcopy(design["size"])
    for rec in size:
        rec["window_fits"] = None
        rec["comparison"]["null_model"] = None
    payload = run(tmp_path, size, design["power"])
    assert payload["exit_status"] == 0, messages(payload)
    assert payload["missing_fields"] == {"replicate.window_fits": N_SMALL, "replicate.comparison.null_model": N_SMALL}


def test_sample_and_workers_give_the_same_verdict(tmp_path, design):
    payload = run(tmp_path, design["size"], design["power"], "--sample", "3", "--sample-seed", "20260930",
                  "--workers", "2")
    assert payload["exit_status"] == 0, messages(payload)
    assert len(payload["sample"]["records"]) == 3 and payload["sample"]["seed"] == 20260930
    bases = [r["basis"] for r in payload["per_record"]]
    assert bases.count("every attempt regenerated") == 3 and bases.count("stored surrogate statistics") == 7
    assert all(r["valid"] for r in payload["per_record"])
    again = run(tmp_path, design["size"], design["power"], "--sample", "3", "--sample-seed", "20260930")
    assert again["sample"]["records"] == payload["sample"]["records"]
    whole = run(tmp_path, design["size"], design["power"], "--workers", "2")
    assert whole["exit_status"] == 0 and [r["p"] for r in whole["per_record"]] == [r["p"] for r in payload["per_record"]]


def alter_observed(rec, delta):
    """Shift the first Delta of a record's observed statistic, keeping S consistent with its own components."""
    for holder in (rec["observed"], rec["comparison"]["observed"]):
        holder["changes"][0] += delta
        holder["mean_change"] = math.fsum(holder["changes"]) / len(holder["changes"])
    rec["S"] = rec["observed"]["mean_change"]


def test_an_altered_observed_statistic_is_found(tmp_path, design):
    size = copy.deepcopy(design["size"])
    alter_observed(size[0], 1e-6)
    payload = run(tmp_path, size, design["power"])
    text = messages(payload)
    assert payload["exit_status"] == 1 and "observed Delta per episode" in text and "observed S" in text
    assert "record S" in text


def test_an_altered_surrogate_statistic_is_found(tmp_path, design):
    size = copy.deepcopy(design["size"])
    attempt = next(a for a in size[1]["comparison"]["attempts"] if a["status"] == "retained")
    attempt["changes"] = [c + 1e-6 for c in attempt["changes"]]            # consistent with its own mean
    attempt["statistic"] += 1e-6
    payload = run(tmp_path, size, design["power"])
    assert payload["exit_status"] == 1 and "surrogate statistics S_b differ" in messages(payload)


def test_an_altered_p_is_found(tmp_path, design):
    size = copy.deepcopy(design["size"])
    other = 1 / (B_SMALL + 1) if design["size"][0]["p_value"] != 1 / (B_SMALL + 1) else 2 / (B_SMALL + 1)
    for holder in (size[0], size[0]["comparison"]):
        holder["p_value"] = other
    payload = run(tmp_path, size, design["power"])
    assert payload["exit_status"] == 1 and "recomputed (1 + K)/(B' + 1)" in messages(payload)


def test_an_altered_exceedance_count_or_interval_is_found(tmp_path, design):
    size = copy.deepcopy(design["size"])
    size[0]["comparison"]["exceedances"] += 1
    size[0]["surrogate_exceedances"] += 1
    payload = run(tmp_path, size, design["power"])
    assert payload["exit_status"] == 1 and "exceedances" in messages(payload)
    size = copy.deepcopy(design["size"])
    size[1]["surrogate_exceedance_wilson"] = [0.0, 1.0]
    payload = run(tmp_path, size, design["power"])
    assert payload["exit_status"] == 1 and "Wilson interval" in messages(payload)


def test_an_altered_input_is_found_with_and_without_a_matching_hash(tmp_path, design):
    size = copy.deepcopy(design["size"])
    size[0]["input"][120][0] += 0.5
    payload = run(tmp_path, size, design["power"])
    assert payload["exit_status"] == 1 and "does not match input_sha256" in messages(payload)
    size[0]["input_sha256"] = v.input_sha256(size[0]["input"])
    payload = run(tmp_path, size, design["power"])
    text = messages(payload)
    assert payload["exit_status"] == 1 and "window_fits" in text and "generation coordinates" in text


def test_a_missing_or_duplicated_coordinate_is_found(tmp_path, design):
    payload = run(tmp_path, design["size"][:1], design["power"])
    assert payload["exit_status"] == 1 and "coordinates missing" in messages(payload)
    payload = run(tmp_path, design["size"] + design["size"][:1], design["power"])
    assert payload["exit_status"] == 1 and "appears 2 times" in messages(payload)
    extra = dict(copy.deepcopy(design["size"][0]), replicate=7)
    payload = run(tmp_path, design["size"] + [extra], design["power"])
    assert payload["exit_status"] == 1 and "outside the design" in messages(payload)


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
    assert "generation coordinates" in text


def test_altered_random_number_states_are_found(tmp_path, design):
    for edit, expected in (
            (lambda r: r.update(generation_rng_before=dict(r["generation_rng_after"])),
             "generation_rng_before differs"),
            (lambda r: r.update(analysis_rng_after=dict(r["analysis_rng_before"])), "analysis_rng_after differs"),
            (lambda r: r["comparison"].update(rng_before=dict(r["comparison"]["rng_after"])),
             "comparison rng_before differs")):
        power = copy.deepcopy(design["power"])
        edit(power[3])
        payload = run(tmp_path, design["size"], power)
        assert payload["exit_status"] == 1 and expected in messages(payload)


def test_a_wrong_kappa_or_cell_name_is_found(tmp_path, design):
    power = copy.deepcopy(design["power"])
    power[5]["kappa"] = 1.2
    payload = run(tmp_path, design["size"], power)
    assert payload["exit_status"] == 1 and "does not belong to cell 2" in messages(payload)
    power = copy.deepcopy(design["power"])
    power[5]["cell"] = "power_3"
    payload = run(tmp_path, design["size"], power)
    assert payload["exit_status"] == 1 and "cell name 'power_3', expected 'power_2'" in messages(payload)
    power = copy.deepcopy(design["power"])
    del power[5]["kappa"]
    payload = run(tmp_path, design["size"], power)
    assert payload["exit_status"] == 1 and "kappa None does not belong to cell 2" in messages(payload)


def test_a_status_that_disagrees_with_the_comparison_is_found(tmp_path, design):
    power = copy.deepcopy(design["power"])
    power[2]["status"] = "no_retained_surrogates"
    payload = run(tmp_path, design["size"], power)
    assert payload["exit_status"] == 1 and "differs from comparison status" in messages(payload)


def test_a_surrogate_failure_must_invalidate_p(tmp_path, design):
    power = copy.deepcopy(design["power"])
    comparison = power[4]["comparison"]
    comparison["attempts"][0] = dict(number=0, status="failed", statistic=None, eligible_onsets=[], changes=[],
                                     error="FloatingPointError: constructed")
    comparison["failed"], comparison["retained"] = 1, B_SMALL - 1
    comparison["exceedances"] = sum(1 for a in comparison["attempts"] if a["status"] == "retained"
                                    and a["statistic"] >= comparison["observed"]["mean_change"])
    payload = run(tmp_path, design["size"], power)
    text = messages(payload)
    assert payload["exit_status"] == 1 and "a surrogate failure did not invalidate p" in text
    assert "attempt statuses differ at attempts [0]" in text


def test_malformed_attempt_lists_are_found(tmp_path, design):
    power = copy.deepcopy(design["power"])
    power[1]["comparison"]["attempts"][2]["status"] = "unknown"
    payload = run(tmp_path, design["size"], power)
    assert payload["exit_status"] == 1 and "attempts with an unknown status: [2]" in messages(payload)
    power = copy.deepcopy(design["power"])
    power[1]["comparison"]["attempts"][3]["number"] = 7
    payload = run(tmp_path, design["size"], power)
    assert payload["exit_status"] == 1 and "attempt numbers are not 0..4 in order" in messages(payload)
    power = copy.deepcopy(design["power"])
    attempt = power[1]["comparison"]["attempts"][0]
    attempt["eligible_onsets"], attempt["changes"] = [77], attempt["changes"][:1]
    attempt["statistic"] = attempt["changes"][0]
    payload = run(tmp_path, design["size"], power)
    assert payload["exit_status"] == 1 and "not the observed eligible onsets" in messages(payload)


def test_a_truncated_attempt_list_is_found(tmp_path, design):
    power = copy.deepcopy(design["power"])
    power[5]["comparison"]["attempts"] = power[5]["comparison"]["attempts"][:-1]
    payload = run(tmp_path, design["size"], power)
    assert payload["exit_status"] == 1 and "attempts stored, the design needs 5" in messages(payload)


def test_a_truncated_last_line_is_found(tmp_path, design):
    path = write(tmp_path / "x3_size_r0-2.jsonl", manifest("size"), design["size"])
    content = path.read_bytes()
    path.write_bytes(content[:-200])
    b = write(tmp_path / "x3_power_c0-3.jsonl", manifest("power"), design["power"])
    payload = v.verify([str(path), str(b), "--development", "--quiet"])
    assert payload["exit_status"] == 1 and "truncated last line" in messages(payload)


def test_near_ties_are_reported_not_silently_classified(design, monkeypatch):
    monkeypatch.setattr(v, "NEAR_TIE", 10.0)                     # every retained attempt is now a "near tie"
    rec = design["power"][0]
    x = np.array(rec["input"])
    result = v.e2_comparison(x, mode="fixed", fixed=v.POWER_ONSETS, seed=DEV_SEED, stream=9231, cell=0,
                             replicate=0, attempts=B_SMALL)
    assert len(result["near_ties"]) == B_SMALL
    assert {t["attempt"] for t in result["near_ties"]} == set(range(B_SMALL))


def test_development_verification_refuses_the_registered_seed_and_streams(tmp_path, design):
    registered = dict(manifest("size"), master_seed=1927)
    payload = run(tmp_path, design["size"], design["power"], size_manifest=registered)
    assert payload["exit_status"] == 1 and "not master seed 1927" in messages(payload)
    low = dict(manifest("size"), streams=dict(STREAMS, size_null=5221))
    payload = run(tmp_path, design["size"], design["power"], size_manifest=low)
    assert payload["exit_status"] == 1 and "registered or low stream ids" in messages(payload)
    assert v.main([str(tmp_path / "x3_size_r0-2.jsonl"), "--sample", "1", "--sample-seed", "1927"]) == 2
    assert v.main([str(tmp_path / "does_not_exist.jsonl")]) == 2
    assert v.main([str(tmp_path / "x3_size_r0-2.jsonl"), "--workers", "0"]) == 2


def test_a_registered_verification_of_a_development_file_fails(tmp_path, design):
    a = write(tmp_path / "x3_size_r0-2.jsonl", manifest("size"), design["size"])
    payload = v.verify([str(a), "--quiet", "--partial"])
    text = messages(payload)
    assert payload["exit_status"] == 1 and "the registered design needs" in text
    assert payload["verdicts"]["size"]["registered"] is False and payload["verdicts"]["size"]["passed"] is False
    payload = v.verify([str(a), "--quiet"])                      # and without --partial it also needs a prerequisite
    assert "needs the prerequisite record" in messages(payload)


def test_manifests_that_disagree_are_found(tmp_path, design):
    other = manifest("power")
    other["settings"] = dict(SETTINGS, power_onsets=[77, 150])
    payload = run(tmp_path, design["size"], design["power"], power_manifest=other)
    text = messages(payload)
    assert payload["exit_status"] == 1 and "manifest differs from x3_size_r0-2.jsonl in settings" in text
    other = manifest("power")
    other["streams"] = dict(STREAMS, power_null=9232)
    payload = run(tmp_path, design["size"], design["power"], power_manifest=other)
    assert payload["exit_status"] == 1 and "in streams" in messages(payload)


def test_runner_summaries_are_compared_field_by_field(tmp_path, design):
    payload = run(tmp_path, design["size"], design["power"])
    cell = payload["size"]
    summary = dict(summary=dict(cell=dict(cell), bounds=[0.02, 0.09]))
    path = tmp_path / "x3_size_summary.json"
    path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
    good = run(tmp_path, design["size"], design["power"], "--summary", str(path))
    assert good["exit_status"] == 0, messages(good)
    assert good["runner"][0]["compared"] > 0 and not good["runner"][0]["differences"]
    summary["summary"]["cell"]["valid"] = cell["valid"] - 1
    path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
    bad = run(tmp_path, design["size"], design["power"], "--summary", str(path))
    assert bad["exit_status"] == 1 and "cell.valid" in messages(bad)
    summary["summary"]["cell"]["valid"] = cell["valid"]
    summary["summary"]["passed"] = True                          # the runner says pass; the recomputation does not
    path.write_text(json.dumps(summary) + "\n", encoding="utf-8")
    bad = run(tmp_path, design["size"], design["power"], "--summary", str(path))
    assert bad["exit_status"] == 1 and "passed: runner True, recomputed False" in messages(bad)


# --------------------------------------------------------------------- the research runner, end to end

RUNNER = load("run_e2_checks_under_test", "tools/run_e2_checks.py")


@pytest.fixture(scope="module")
def runner_output(tmp_path_factory):
    """A development run of the research runner on tiny sizes: the prerequisite record, size and power parts that
    name it, and the runner's own summaries."""
    base = tmp_path_factory.mktemp("runner")
    prerequisite, size, power = base / "x3_prerequisite.jsonl", base / "x3_size_r0-2.jsonl", base / "x3_power_c0-3.jsonl"
    assert RUNNER.main(["e2", "prerequisite", "--out", str(prerequisite)]) == 0
    for check, path in (("size", size), ("power", power)):
        assert RUNNER.main(["e2", check, "--out", str(path), "--n-series", "2", "--B", "9",
                            "--prerequisite", str(prerequisite)]) == 0
    return dict(base=base, prerequisite=prerequisite, size=size, power=power)


def runner_summary(runner_output, check, capsys):
    capsys.readouterr()
    assert RUNNER.main(["e2", "summarize", "--out", str(runner_output[check])]) == 0
    path = runner_output["base"] / ("x3_%s_summary.json" % check)
    path.write_text(capsys.readouterr().out, encoding="utf-8")
    return path


def test_the_verifier_agrees_with_every_record_of_a_development_run_of_the_research_runner(runner_output, tmp_path,
                                                                                         capsys):
    summaries = [runner_summary(runner_output, check, capsys) for check in ("size", "power")]
    payload = v.verify([str(runner_output["size"]), str(runner_output["power"]), "--development", "--quiet",
                        "--prerequisite", str(runner_output["prerequisite"]),
                        "--summary", str(summaries[0]), "--summary", str(summaries[1]),
                        "--report", str(tmp_path / "report.json")])
    assert payload["exit_status"] == 0, messages(payload)
    assert payload["coverage"]["present"] == 10 and payload["coverage"]["missing"] == 0
    assert all(r["basis"] == "every attempt regenerated" and r["regeneration_identical"]
               for r in payload["per_record"])
    assert payload["maxima"]["statistics"] < 1e-12 and payload["maxima"]["fits"] < 1e-12
    assert payload["maxima"]["nulls"] < 1e-12 and payload["maxima"]["regeneration"] == 0.0
    assert payload["missing_fields"] == {}
    assert [len(r["differences"]) for r in payload["runner"]] == [0, 0]
    assert all(r["compared"] > 10 for r in payload["runner"])
    prerequisite = payload["prerequisite"]
    assert prerequisite["passed_recorded"] is True and prerequisite["passed_recomputed"] is True
    assert prerequisite["fixture_form"] in ("closed", "text")


def test_a_runner_summary_that_disagrees_with_the_files_is_found(runner_output, tmp_path, capsys):
    path = runner_summary(runner_output, "power", capsys)
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["summary"]["cells"][2]["rejected"] += 1
    summary["inputs"][0]["records"] += 1
    altered = tmp_path / "x3_power_summary.json"
    altered.write_text(json.dumps(summary), encoding="utf-8")
    payload = v.verify([str(runner_output["size"]), str(runner_output["power"]), "--development", "--quiet",
                        "--summary", str(altered)])
    text = messages(payload)
    assert payload["exit_status"] == 1 and "cells[2].rejected" in text and ".records" in text


def test_an_altered_prerequisite_record_is_found(runner_output, tmp_path):
    lines = [json.loads(line) for line in runner_output["prerequisite"].read_text(encoding="utf-8").splitlines()]
    lines[1]["at12"]["ar2"]["max_abs_error"] = 1.0
    altered = tmp_path / "x3_prerequisite.jsonl"
    altered.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    payload = v.verify([str(runner_output["size"]), str(runner_output["power"]), "--development", "--quiet",
                        "--prerequisite", str(altered)])
    text = messages(payload)
    assert payload["exit_status"] == 1 and "recorded max error 1.0 exceeds 1e-09" in text
    assert "is not the one the parts' manifests name" in text                       # its hash changed as well
    lines = [json.loads(line) for line in runner_output["prerequisite"].read_text(encoding="utf-8").splitlines()]
    lines[1]["reduction"]["windows"][1]["fitted"] += 1
    altered.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    payload = v.verify([str(runner_output["size"]), str(runner_output["power"]), "--development", "--quiet",
                        "--prerequisite", str(altered)])
    assert payload["exit_status"] == 1 and "reduction W = 40: fitted windows" in messages(payload)
