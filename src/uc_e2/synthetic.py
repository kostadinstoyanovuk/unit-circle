"""E2 section 11 and Annex B: the synthetic design of the X.3 checks, its replicates and the prerequisites.

Every random number comes from a Generator built from SeedSequence([master_seed, stream, cell, replicate]).
"""
from __future__ import annotations

import math

import numpy as np

from uc_core import surrogate as s
from uc_core.ar import root_summary
from uc_core.constants import MASTER_SEED
from uc_core.rolling import max_modulus as ar2_max_modulus
from uc_core.validation_design import h1_design_series
from uc_ext import common as c

from .constants import (AT12_DRAWS, AT12_STREAM, DESIGN_A1, DESIGN_A2, DESIGN_INTERCEPT, DESIGN_MEAN, DESIGN_SCALE,
                        DESIGN_SIGMA, DESIGN_SIGMA_CHOLESKY, DESIGN_TIME_CORRELATION, DEVELOPMENT_POWER_ONSETS, K,
                        KAPPAS, N_OBS, PREREQUISITE_FIXTURE, REDUCTION_TOL, SENSITIVITY_WINDOWS,
                        SERIES_PER_CELL, SIGNAL_LENGTH, SIZE_BOUNDS, SURROGATE_ATTEMPTS, WINDOW,
                        X3_RETAIN_WINDOW_FITS)
from .procedure import csd_test, fixed_date_test, statistic
from .streams import DEVELOPMENT_SEED, at12_stream, check_seed, stream_ids, stream_rng
from .var import max_modulus, rolling_var2, spectral_radius
from .variables import check_power_onsets, imposed_onsets


def _pcg(*words):
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([int(w) for w in words])))


# ---------------------------------------------------------------- X.3: the section 11 synthetic design

def design_covariances():
    """(Sigma, its lower Cholesky factor, the 4 x 4 stationary covariance of (X0, X1), its Cholesky factor).

    R6: Sigma's factor is the literal of section 11 (numpy.linalg.cholesky(Sigma) gives the same numbers,
    tested); the 4 x 4 factor is numpy.linalg.cholesky of [[1, 1/3], [1/3, 1]] kron (100/88) Sigma.
    """
    sigma = np.asarray(DESIGN_SIGMA, dtype=float)
    initial = np.kron(np.asarray(DESIGN_TIME_CORRELATION), DESIGN_SCALE * sigma)
    return sigma, np.asarray(DESIGN_SIGMA_CHOLESKY, dtype=float), initial, np.linalg.cholesky(initial)


def design_series(rng, *, kappa=1., onsets=None, n=N_OBS):
    """Section 11 generating VAR: two copies of H1's AR(2), innovation correlation -0.5, no burn-in.

    One standard_normal(4) call (the stationary (g0, du0, g1, du1) through the lower Cholesky factor of its
    covariance, plus the means), then one standard_normal((n - 2, 2)) call whose rows are multiplied by the
    lower Cholesky factor of Sigma, then the recursion in order. With onsets, in the eight positions r-8..r-1
    before each onset the coefficients are kappa*A1, kappa^2*A2 and the intercept (I - kappa*A1 -
    kappa^2*A2) mu; elsewhere, and at kappa = 1, the base values (R7: at kappa = 1 the planted segments use
    the base intercept (1.5, 0) exactly, as uc_core.validation_design.h1_design_series does).
    """
    s._generator(rng)
    kappa = float(kappa)
    if not math.isfinite(kappa) or kappa <= 0:
        raise ValueError("kappa must be finite and positive")
    n = s._integer(n, "n", 5)
    onsets = () if onsets is None else tuple(onsets)
    if any(t - SIGNAL_LENGTH < 2 or t >= n for t in onsets) or any(
            b - SIGNAL_LENGTH <= a for a, b in zip(onsets, onsets[1:])):
        raise ValueError("Onsets must be increasing, inside the series, with non-overlapping signals after position 1")
    _, sigma_factor, _, initial_factor = design_covariances()
    a1, a2, mu = np.asarray(DESIGN_A1), np.asarray(DESIGN_A2), np.asarray(DESIGN_MEAN)
    base_intercept = np.asarray(DESIGN_INTERCEPT)
    planted_a1, planted_a2 = kappa * a1, kappa ** 2 * a2
    planted_intercept = (np.eye(K) - planted_a1 - planted_a2) @ mu
    start = np.tile(mu, 2) + initial_factor @ rng.standard_normal(2 * K)
    noise = rng.standard_normal((n - 2, K)) @ sigma_factor.T
    active = np.zeros(n, dtype=bool)
    for onset in onsets:
        active[onset - SIGNAL_LENGTH:onset] = True
    x = np.empty((n, K))
    x[0], x[1] = start[:K], start[K:]
    for t in range(2, n):
        if active[t] and kappa != 1.:
            x[t] = planted_intercept + planted_a1 @ x[t - 1] + planted_a2 @ x[t - 2] + noise[t - 2]
        else:
            x[t] = base_intercept + a1 @ x[t - 1] + a2 @ x[t - 2] + noise[t - 2]
    return x


def window_fits(values, window=WINDOW):
    """R9: the fitted intercepts, A1, A2 and M of every window from position W - 1 on, as plain lists."""
    try:
        fits = rolling_var2(values, window)
    except c.NUMERIC_ERRORS as error:
        return dict(window=window, first_position=window - 1, error=f"{type(error).__name__}: {error}")
    return dict(window=window, first_position=window - 1, error=None,
                **{name: fits[name][window - 1:].tolist() for name in ("modulus", "intercept", "A1", "A2")})


def _with_retention(record, settings):
    retained = None
    if settings["retain_window_fits"] and record.get("input") is not None:
        retained = window_fits(np.asarray(record["input"], dtype=float))
    return record | dict(settings=settings, window_fits=retained)


def size_replicate(replicate, *, master_seed, B=SURROGATE_ATTEMPTS, allow_registered=False, onsets=None):
    """One AT-15-analogue replicate: stream 5220 generation, stream 5221 joint residual-vector surrogates,
    E2 primary mode (W = 40, onsets from the synthetic g). `onsets` only enters the recorded settings."""
    master_seed = check_seed(master_seed, allow_registered)
    settings = x3_settings(master_seed=master_seed, power_onsets=onsets)
    return _with_retention(c.compute_record(
        cell_name="size", cell_index=0, replicate=replicate,
        generation_rng=stream_rng(master_seed, stream_ids(master_seed)["size_generation"], 0, replicate,
                                  allow_registered=allow_registered),
        analysis_rng=stream_rng(master_seed, stream_ids(master_seed)["size_null"], 0, replicate,
                                allow_registered=allow_registered),
        generate=lambda g: design_series(g, kappa=1.),
        observe=lambda v: statistic(v),
        compare=lambda v, g: csd_test(v, B=B, rng=g),
        requested=B), settings)


def power_replicate(cell, replicate, *, master_seed, B=SURROGATE_ATTEMPTS, kappas=KAPPAS, allow_registered=False,
                    onsets=None):
    """One AT-16-analogue replicate: stream 5230 generation, stream 5231 fixed-date surrogates at the imposed
    onsets (R1: required under the registered seed), W = 40."""
    master_seed = check_seed(master_seed, allow_registered)
    settings = x3_settings(master_seed=master_seed, power_onsets=onsets)
    onsets = tuple(settings["power_onsets"])
    kappa = kappas[cell]
    return _with_retention(c.compute_record(
        cell_name=f"power_{cell}", cell_index=cell, replicate=replicate,
        generation_rng=stream_rng(master_seed, stream_ids(master_seed)["power_generation"], cell, replicate,
                                  allow_registered=allow_registered),
        analysis_rng=stream_rng(master_seed, stream_ids(master_seed)["power_null"], cell, replicate,
                                allow_registered=allow_registered),
        generate=lambda g: design_series(g, kappa=kappa, onsets=onsets),
        observe=lambda v: statistic(v, fixed_onsets=onsets),
        compare=lambda v, g: fixed_date_test(v, onsets, B=B, rng=g),
        requested=B), settings) | dict(kappa=kappa)


def x3_input(check, cell, replicate, *, master_seed, kappas=KAPPAS, allow_registered=False, onsets=None):
    """The generated series of one X.3 replicate, rebuilt from its seed coordinates alone (resume checks)."""
    master_seed = check_seed(master_seed, allow_registered)
    if check == "size" and cell == 0:
        return design_series(stream_rng(master_seed, stream_ids(master_seed)["size_generation"], 0, replicate,
                                        allow_registered=allow_registered), kappa=1.)
    if check == "power":
        return design_series(stream_rng(master_seed, stream_ids(master_seed)["power_generation"], cell, replicate,
                                        allow_registered=allow_registered),
                             kappa=kappas[cell], onsets=imposed_onsets(master_seed, onsets))
    raise ValueError("Unknown X.3 check or cell")


def x3_settings(*, master_seed=None, power_onsets=None, **_):
    """The run-time settings of the E2 X.3 checks, recorded in every manifest and record: the imposed power
    onsets and their source (R1) and the window-fit retention (R9). Under the registered seed the onsets must
    be supplied (the runner reads them from ONSETS_RECORD); otherwise the development fixture is the default."""
    registered = master_seed is not None and int(master_seed) == MASTER_SEED
    onsets = imposed_onsets(MASTER_SEED if registered else DEVELOPMENT_SEED, power_onsets)
    source = ("registered_onsets_record" if registered else
              "development_fixture" if onsets == DEVELOPMENT_POWER_ONSETS else "development_supplied")
    return dict(power_onsets=list(onsets), power_onset_source=source, retain_window_fits=X3_RETAIN_WINDOW_FITS)


def x3_arguments(settings):
    """The size_replicate/power_replicate keyword arguments that realise x3_settings(...): the onsets."""
    if settings.get("power_onset_source") not in ("registered_onsets_record", "development_fixture",
                                                  "development_supplied"):
        raise ValueError("Unknown E2 power onset source")
    if settings.get("retain_window_fits") != X3_RETAIN_WINDOW_FITS:
        raise ValueError("The window-fit retention is the module setting X3_RETAIN_WINDOW_FITS")
    return dict(onsets=check_power_onsets(settings["power_onsets"]))


def x3_input_arguments(settings):
    """The x3_input keyword arguments for a saved file's settings (the runner's resume checks)."""
    return x3_arguments(settings)


def _registered(master_seed, n_series, B, kappas=KAPPAS):
    return (master_seed == MASTER_SEED and n_series == SERIES_PER_CELL and B == SURROGATE_ATTEMPTS
            and tuple(kappas) == KAPPAS)


def run_size_check(*, master_seed=DEVELOPMENT_SEED, n_series=SERIES_PER_CELL, B=SURROGATE_ATTEMPTS,
                   replicates=None, allow_registered=False, onsets=None, progress=None):
    """AT-15 analogue. `replicates` (default all) lets a caller split or resume the cell by coordinates."""
    master_seed = check_seed(master_seed, allow_registered)
    n_series = s._integer(n_series, "n_series")
    records = []
    for replicate in (range(n_series) if replicates is None else replicates):
        records.append(size_replicate(replicate, master_seed=master_seed, B=B, allow_registered=allow_registered,
                                      onsets=onsets))
        if progress:
            progress(records[-1])
    summary = (c.summarize_size(records, requested=n_series, bounds=SIZE_BOUNDS,
                                registered=_registered(master_seed, n_series, B))
               if replicates is None else None)
    return dict(master_seed=master_seed, n_series=n_series, B=B, records=records, summary=summary)


def run_power_check(*, master_seed=DEVELOPMENT_SEED, n_series=SERIES_PER_CELL, B=SURROGATE_ATTEMPTS,
                    kappas=KAPPAS, cells=None, replicates=None, allow_registered=False, onsets=None, progress=None):
    """AT-16 analogue with D80. `cells`/`replicates` (default all) select coordinates for splitting."""
    master_seed = check_seed(master_seed, allow_registered)
    n_series = s._integer(n_series, "n_series")
    kappas = tuple(float(k) for k in kappas)
    records = []
    for cell in (range(len(kappas)) if cells is None else cells):
        for replicate in (range(n_series) if replicates is None else replicates):
            records.append(power_replicate(cell, replicate, master_seed=master_seed, B=B, kappas=kappas,
                                           allow_registered=allow_registered, onsets=onsets))
            if progress:
                progress(records[-1])
    summary = None
    if cells is None and replicates is None:
        cell_summaries = [c.summarize_cell([r for r in records if r["cell_index"] == i], n_series)
                          for i in range(len(kappas))]
        summary = c.summarize_power_cells(cell_summaries, kappas,
                                          registered=_registered(master_seed, n_series, B, kappas))
    return dict(master_seed=master_seed, n_series=n_series, B=B, kappas=kappas, records=records, summary=summary)


# ------------------------------------------------------------------ X.3 prerequisites (Annex B, R2)

def at12(draws, seed, stream=AT12_STREAM):
    """AT-12 through spectral_radius: uc_core.linalg.at12's draws, skips and tolerances, E2's function.

    Diagonal part: spectral_radius([diag(a, b)]) against max(|a|, |b|), tolerance 1e-12. AR(2) part: the
    k = 1 VAR companion spectral_radius([[[phi1]], [[phi2]]]) against uc_core's root modulus, tolerance 1e-9,
    skipping |phi1^2 + 4 phi2| < 1e-8. With the same seed it is uc_core.linalg.at12 number for number (tested).
    """
    draws = s._integer(draws, "draws")
    ab = _pcg(seed, stream, 0).uniform(-2, 2, size=(draws, 2))
    diagonal_error = float(max(abs(spectral_radius([np.diag(row)]) - np.max(np.abs(row))) for row in ab))
    ar_rng = _pcg(seed, stream, 1)
    phi = np.column_stack((ar_rng.uniform(-3, 3, draws), ar_rng.uniform(-2, 2, draws)))
    ar_error, skipped = 0.0, 0
    for phi1, phi2 in phi:
        if abs(phi1 * phi1 + 4 * phi2) < 1e-8:
            skipped += 1
            continue
        ar_error = max(ar_error, float(abs(spectral_radius([[[phi1]], [[phi2]]]) - root_summary([phi1, phi2]).modulus)))
    return dict(diagonal=dict(draws=draws, max_abs_error=diagonal_error, passed=diagonal_error <= 1e-12),
                ar2=dict(draws=draws, skipped=skipped, max_abs_error=ar_error, passed=ar_error <= 1e-9),
                seed=[int(seed), int(stream)], passed=diagonal_error <= 1e-12 and ar_error <= 1e-9)


def reduction_check(values, windows=(SENSITIVITY_WINDOWS[0], WINDOW, SENSITIVITY_WINDOWS[1]), tolerance=REDUCTION_TOL):
    """Annex B: the VAR code restricted to one variable reproduces H1's rolling M(t) (uc_core.rolling) to 1e-10."""
    x = np.asarray(values, dtype=float)
    rows = []
    for window in windows:
        var_path = max_modulus(x, window)
        h1_path = np.asarray(ar2_max_modulus(x, window), dtype=float)
        warmup_same = bool(np.array_equal(np.isnan(var_path), np.isnan(h1_path)))
        fitted = ~np.isnan(h1_path)
        difference = float(np.max(np.abs(var_path[fitted] - h1_path[fitted]))) if fitted.any() else None
        rows.append(dict(window=window, fitted=int(fitted.sum()), max_abs_difference=difference,
                         warmup_same=warmup_same,
                         passed=bool(warmup_same and difference is not None and difference <= tolerance)))
    return dict(input_sha256=c.sha256_values(x), tolerance=tolerance, windows=rows,
                passed=all(row["passed"] for row in rows))


def prerequisite_fixture(*, master_seed, allow_registered=False):
    """The Annex B X.3 prerequisites: AT-12 through spectral_radius (AT-12's own draws under the registered
    seed, a smaller development count otherwise) and the reduction test on the synthetic H1-design series of
    stream 5220, cell 1, replicate 0. `passed` is true only when both pass."""
    master_seed = check_seed(master_seed, allow_registered)
    registered = master_seed == MASTER_SEED
    draws = AT12_DRAWS["registered" if registered else "development"]
    values = h1_design_series(stream_rng(master_seed, stream_ids(master_seed)[PREREQUISITE_FIXTURE["stream"]],
                                         PREREQUISITE_FIXTURE["cell"], PREREQUISITE_FIXTURE["replicate"],
                                         allow_registered=allow_registered))
    at12_result = at12(draws, master_seed, at12_stream(master_seed))
    reduction = reduction_check(values)
    return dict(input_sha256=c.sha256_values(values), at12=at12_result, reduction=reduction,
                passed=bool(at12_result["passed"] and reduction["passed"]))
