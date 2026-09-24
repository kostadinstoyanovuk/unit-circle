"""Inspectable fitted-null comparisons; calibration is a separate milestone."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
import numpy as np

from .ar import _real_vector, fit_ols
from .recession import PreOnsetResult, episodes, pre_onset_changes
from .rolling import _observations_and_index, max_modulus


class NullModelError(ValueError):
    """The full-sample null is not usable; no projection or replacement is made."""


@dataclass(frozen=True)
class NullModel:
    coefficients: tuple[float, float]
    intercept: float
    initial: tuple[float, float]
    residuals: tuple[float, ...]
    residual_mean_removed: float
    modulus: float


@dataclass(frozen=True)
class Attempt:
    number: int
    status: str
    statistic: float | None
    eligible_onsets: tuple[int, ...] = ()
    changes: tuple[float, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class Comparison:
    status: str
    observed: PreOnsetResult
    p_value: float | None
    requested: int
    attempted: int
    retained: int
    no_episode: int
    failed: int
    exceedances: int | None
    p_grid_spacing: float | None
    attempts: tuple[Attempt, ...]
    null_model: NullModel | None
    window: int
    lookback: int
    merge: int
    onset_mode: str
    innovation_mode: str
    rng_before: dict
    rng_after: dict


def _integer(value, name, minimum=1):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _generator(rng):
    if not isinstance(rng, np.random.Generator):
        raise ValueError("Supply an explicit numpy.random.Generator")


def prepare_null(values) -> NullModel:
    x, _ = _observations_and_index(values)
    try:
        fit = fit_ols(x)
    except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise NullModelError(f"Full-sample null fit failed: {error}") from error
    if not fit.diagnostics.stable or not math.isfinite(fit.diagnostics.modulus) or fit.diagnostics.modulus >= 1:
        raise NullModelError("Full-sample null must be strictly stable; coefficients were not projected")
    residuals = np.asarray(fit.residuals)
    mean = float(residuals.mean())
    residuals = residuals - mean
    return NullModel(fit.coefficients, fit.intercept, (float(x[0]), float(x[1])),
                     tuple(map(float, residuals)), mean, fit.diagnostics.modulus)


def simulate_ar2(coefficients, intercept, initial, innovations) -> np.ndarray:
    """Generate n=len(innovations)+2 values with exactly the supplied initial pair."""
    phi = _real_vector(coefficients, length=2)
    initial = _real_vector(initial, length=2)
    innovations = _real_vector(innovations)
    intercept = float(intercept)
    if not math.isfinite(intercept):
        raise ValueError("Intercept must be finite")
    x = np.empty(len(innovations) + 2)
    x[:2] = initial
    with np.errstate(over="raise", invalid="raise"):
        for position, noise in enumerate(innovations, start=2):
            x[position] = intercept + phi[0]*x[position-1] + phi[1]*x[position-2] + noise
    if not np.isfinite(x).all():
        raise FloatingPointError("Non-finite generated series")
    return x


def draw_surrogate(model: NullModel, rng: np.random.Generator, *, kind="residual") -> np.ndarray:
    _generator(rng)
    residuals = np.asarray(model.residuals, dtype=float)
    if kind == "residual":
        innovations = residuals[rng.integers(0, len(residuals), size=len(residuals))]
    elif kind == "wild":
        signs = 2*rng.integers(0, 2, size=len(residuals)) - 1
        innovations = residuals*signs
    else:
        raise ValueError("kind must be 'residual' or 'wild'")
    return simulate_ar2(model.coefficients, model.intercept, model.initial, innovations)


def monte_carlo_pvalue(observed: float, retained_statistics) -> float | None:
    """Upper tail with ties and plus-one convention; not a calibration theorem."""
    observed = float(observed)
    if not math.isfinite(observed):
        raise ValueError("Observed statistic must be finite")
    statistics = _real_vector(retained_statistics)
    if not len(statistics):
        return None
    return float((1 + np.count_nonzero(statistics >= observed))/(len(statistics) + 1))


def _statistic(values, *, window, lookback, merge, fixed_onsets=None):
    onsets = tuple(e.onset for e in episodes(values, merge=merge)) if fixed_onsets is None else tuple(fixed_onsets)
    # Eligibility can be established without fitting any window: first M is at W-1.
    if not any(t >= window + lookback for t in onsets):
        return PreOnsetResult(None, (), (), onsets)
    return pre_onset_changes(max_modulus(values, window), onsets, lookback=lookback)


def csd_test(values, *, B: int, rng: np.random.Generator, window=40, lookback=8,
             merge=8, onset_mode="endogenous", innovation_mode="residual") -> Comparison:
    """Run exactly B attempted surrogates; only empty episodes may be dropped.

    Numeric/fit failures are recorded and invalidate p. No retries, coefficient
    projection, skipped failed windows or automatic replacement draws occur.
    Requires a supplied Generator. Calls use no global RNG or source data IO.
    """
    B = _integer(B, "B")
    window = _integer(window, "window", 5)
    lookback = _integer(lookback, "lookback")
    merge = _integer(merge, "merge", 0)
    _generator(rng)
    if onset_mode not in ("endogenous", "fixed") or innovation_mode not in ("residual", "wild"):
        raise ValueError("Unsupported onset or innovation mode")
    x, _ = _observations_and_index(values)
    before = deepcopy(rng.bit_generator.state)
    observed = _statistic(x, window=window, lookback=lookback, merge=merge)
    if observed.mean_change is None:
        return Comparison("observed_not_estimable", observed, None, B, 0, 0, 0, 0,
                          None, None, (), None, window, lookback, merge, onset_mode,
                          innovation_mode, before, deepcopy(rng.bit_generator.state))
    model = prepare_null(x)
    fixed = observed.eligible_onsets if onset_mode == "fixed" else None
    records = []
    for number in range(B):
        try:
            simulated = draw_surrogate(model, rng, kind=innovation_mode)
            statistic = _statistic(simulated, window=window, lookback=lookback, merge=merge, fixed_onsets=fixed)
            if statistic.mean_change is None:
                records.append(Attempt(number, "no_eligible_episode", None))
            else:
                if not math.isfinite(statistic.mean_change):
                    raise FloatingPointError("Non-finite surrogate statistic")
                records.append(Attempt(number, "retained", statistic.mean_change,
                                       statistic.eligible_onsets, statistic.changes))
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
            records.append(Attempt(number, "failed", None, error=f"{type(error).__name__}: {error}"))
    kept = [r.statistic for r in records if r.status == "retained"]
    empty = sum(r.status == "no_eligible_episode" for r in records)
    failed = sum(r.status == "failed" for r in records)
    p = None if failed else monte_carlo_pvalue(observed.mean_change, kept)
    status = "invalid_surrogate_failure" if failed else ("no_retained_surrogates" if not kept else "ok")
    exceedances = sum(s >= observed.mean_change for s in kept) if kept else None
    return Comparison(status, observed, p, B, len(records), len(kept), empty, failed,
                      exceedances, 1/(len(kept)+1) if kept else None, tuple(records), model,
                      window, lookback, merge, onset_mode, innovation_mode,
                      before, deepcopy(rng.bit_generator.state))
