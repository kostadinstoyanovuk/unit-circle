"""Reference causal rolling AR(2) fits; optimize only against this contract."""
from __future__ import annotations

import numpy as np
import pandas as pd
from .ar import _real_vector, fit_ols


class RollingFitError(ValueError):
    """A non-warm-up window could not be fitted; it must not be dropped silently."""


def _observations_and_index(values):
    array = _real_vector(values)
    index = values.index.copy() if isinstance(values, pd.Series) else pd.RangeIndex(len(array))
    _validate_index(index)
    return array, index


def _validate_index(index):
    if not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError("Input index must be unique and chronologically increasing")
    if isinstance(index, pd.PeriodIndex) and len(index) > 1:
        if not np.all(np.diff(index.asi8) == index.freq.n):
            raise ValueError("PeriodIndex has a missing or irregular period; do not bridge it silently")


def rolling_ar2(values, window: int = 40) -> pd.DataFrame:
    """One within-window intercept-inclusive fit ending at each available t.

    The first window-1 rows are marked warmup; a sample shorter than window
    has only warmup rows. A window supplies window-2 regression outcomes.
    Failed fits raise with their endpoint. No future observations enter a fit.
    """
    if isinstance(window, bool) or not isinstance(window, (int, np.integer)) or window < 5:
        raise ValueError("window must be an integer of at least five observations")
    x, index = _observations_and_index(values)
    numbers = np.full((len(x), 4), np.nan)
    status = np.full(len(x), "warmup", dtype=object)
    for end in range(window - 1, len(x)):
        try:
            fit = fit_ols(x[end - window + 1:end + 1])
        except ValueError as error:
            raise RollingFitError(f"AR(2) window ending at position {end}, label {index[end]!r}: {error}") from error
        numbers[end] = [fit.intercept, *fit.coefficients, fit.diagnostics.modulus]
        status[end] = "ok"
    result = pd.DataFrame(numbers, index=index, columns=["intercept", "phi1", "phi2", "modulus"])
    result["status"] = status
    return result


def max_modulus(values, window: int = 40) -> pd.Series:
    """Return the causal root-modulus path, preserving the supplied index."""
    return rolling_ar2(values, window)["modulus"].rename("M")
