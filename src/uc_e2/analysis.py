"""E2 X.4: the single real run assembled in memory (sections 8 to 10) and its reporting quantities.

The caller (the X.4 tool) supplies the 195 x 2 values and sets allow_registered=True only after its gates.
"""
from __future__ import annotations

import numpy as np

from uc_core import surrogate as s
from uc_core.constants import MASTER_SEED
from uc_core.recession import episodes, pre_onset_changes
from uc_core.rolling import max_modulus as ar2_max_modulus
from uc_core.secondary import episode_percentile_interval
from uc_ext import common as c

from .constants import (EPISODE_RESAMPLES, K, LOOKBACK, MERGE, MINIMUM_RUN, N_OBS, SENSITIVITY_WINDOWS,
                        SURROGATE_ATTEMPTS, WINDOW)
from .procedure import csd_test, primary_with_comparators, statistic
from .streams import check_seed, stream_ids, stream_rng
from .var import _observations, max_modulus, rolling_var2
from .variables import imposed_onsets, quarter_label


# ------------------------------------------------------------------------ X.4: the single real run

def _ar2_deltas(series, onsets):
    """W = 40 AR(2) pre-onset changes (uc_core) of one series at the given onsets; failures are recorded."""
    try:
        result = pre_onset_changes(ar2_max_modulus(np.asarray(series, dtype=float), WINDOW), onsets,
                                   lookback=LOOKBACK)
    except c.NUMERIC_ERRORS as error:
        return dict(status="failed", deltas=None, error=f"{type(error).__name__}: {error}")
    return dict(status="ok", deltas=dict(zip(result.eligible_onsets, result.changes)), error=None)


def episode_record(values, h1_frozen_deltas=None):
    """Every merged episode of g with its runs, quarters, eligibility at 32/40/48 and its E2 Delta at W = 40,
    and, for the W = 40 eligible episodes, the section 10 descriptive columns:

    - the AR(2) Delta on g at W = 40 recomputed from these values (for eligible E2 onsets both windows lie
      inside 1971Q2-2019Q4, so it is H1's Delta for that onset if H1 has the same onset);
    - R5: H1's own Delta from the h1-frozen record, when the X.4 tool supplies it as
      h1_frozen_deltas = {E2 onset position: Delta}; the row records whether the two agree exactly;
    - the AR(2) Delta on du alone at W = 40.
    """
    x = _observations(values)
    merged = episodes(x[:, 0], minimum_run=MINIMUM_RUN, merge=MERGE)
    onsets = [e.onset for e in merged]
    var_result = pre_onset_changes(max_modulus(x, WINDOW), onsets, lookback=LOOKBACK)
    e2_deltas = dict(zip(var_result.eligible_onsets, var_result.changes))
    on_g = _ar2_deltas(x[:, 0], var_result.eligible_onsets)
    on_du = _ar2_deltas(x[:, 1], var_result.eligible_onsets) if x.shape[1] > 1 else None
    rows = []
    for e in merged:
        eligible = e.onset in e2_deltas
        row = dict(onset=e.onset, end=e.end, onset_quarter=quarter_label(e.onset), end_quarter=quarter_label(e.end),
                   runs=[(run.onset, run.end) for run in e.runs],
                   eligible={w: e.onset >= w + LOOKBACK for w in (32, WINDOW, 48)},
                   e2_delta=e2_deltas.get(e.onset))
        if eligible:
            recomputed = on_g["deltas"].get(e.onset) if on_g["status"] == "ok" else None
            frozen = None if h1_frozen_deltas is None else h1_frozen_deltas.get(e.onset)
            row.update(ar2_delta_g_recomputed=recomputed, h1_frozen_delta=frozen,
                       h1_frozen_agrees=None if frozen is None else frozen == recomputed,
                       ar2_delta_du=(on_du["deltas"].get(e.onset) if on_du and on_du["status"] == "ok" else None))
        rows.append(row)
    return dict(rows=rows, ar2_g_status=on_g, ar2_du_status=on_du)



def analyze(values, *, master_seed=MASTER_SEED, allow_registered=False, B=SURROGATE_ATTEMPTS,
            interval_B=EPISODE_RESAMPLES, h1_frozen_deltas=None, registered_onsets=None):
    """The single real run (X.4) assembled in memory, as uc_core.h1.analyze_h1: every section 8-10 output.

    Requires exactly 195 x 2 observations. The registered seed 1927 runs only with allow_registered=True,
    which the caller sets after verifying registration, tag and the X.3 record (Annex B), and with the
    section 7 onsets (registered_onsets, from ONSETS_RECORD) for the R8 check. Retains the fitted coefficient
    matrices of every window (W = 32, 40, 48) and the null with its residual matrix.
    """
    master_seed = check_seed(master_seed, allow_registered)
    B = s._integer(B, "B")
    interval_B = s._integer(interval_B, "interval_B")
    x = _observations(values)
    if x.shape != (N_OBS, K):
        raise ValueError(f"E2 uses exactly {N_OBS} observations of (g, du) (1971Q2-2019Q4)")
    expected_onsets = (imposed_onsets(master_seed, registered_onsets)
                       if master_seed == MASTER_SEED or registered_onsets is not None else None)

    ids = stream_ids(master_seed)

    def rng(name):
        return stream_rng(master_seed, ids[name], allow_registered=allow_registered)

    joint = primary_with_comparators(x, B=B, rng=rng("primary"))

    def sensitivity(name, **kwargs):
        window = kwargs.pop("window", WINDOW)
        try:
            return csd_test(x, B=B, rng=rng(name), window=window, **kwargs)
        except s.NullModelError as error:
            return dict(status="null_model_failed", p_value=None, observed=statistic(x, window=window),
                        requested=B, attempted=0, error=str(error))
        except c.NUMERIC_ERRORS as error:
            return dict(status="observed_statistic_failed", p_value=None, requested=B, attempted=0,
                        error=f"{type(error).__name__}: {error}")

    rolling = {}
    for window in (SENSITIVITY_WINDOWS[0], WINDOW, SENSITIVITY_WINDOWS[1]):
        try:
            rolling[window] = rolling_var2(x, window)
        except c.NUMERIC_ERRORS as error:
            rolling[window] = dict(status="failed", error=f"{type(error).__name__}: {error}")
    try:
        episodes_table = episode_record(x, h1_frozen_deltas)
    except c.NUMERIC_ERRORS as error:
        episodes_table = dict(status="failed", error=f"{type(error).__name__}: {error}")
    # R8: with the section 7 onsets (always under the registered seed), record whether the observed W = 40
    # eligible onsets are that list.
    observed_onsets = joint.primary.observed.eligible_onsets
    onset_check = None if expected_onsets is None else dict(
        registered=list(expected_onsets), observed=list(observed_onsets),
        agrees=tuple(observed_onsets) == expected_onsets)
    result = dict(
        master_seed=master_seed,
        input_sha256=c.sha256_values(x),
        episodes=episodes_table,
        rolling_fits=rolling,
        onset_check=onset_check,
        joint=joint,
        window32=sensitivity("window32", window=32),
        window48=sensitivity("window48", window=48),
        fixed=sensitivity("fixed", onset_mode="fixed"),
        wild=sensitivity("wild", innovation_mode="wild"),
        episode_interval=(dict(status="observed_statistic_failed", interval=None, error=joint.primary.observed.error)
                          if joint.primary.observed.status == "failed" else
                          episode_percentile_interval(joint.primary.observed.components, B=interval_B,
                                                      rng=rng("interval"))),
    )
    result["report"] = report(result)
    return result


def report(result):
    """Sections 8-10 reporting quantities for every comparison of analyze(): m, k = count(Delta > 0), K, B',
    q = K/B' with its Wilson interval, and the raw p labelled "raw, not family-adjusted"."""
    sources = [("primary", result["joint"].primary, WINDOW), ("window32", result["window32"], 32),
               ("window48", result["window48"], 48), ("fixed", result["fixed"], WINDOW),
               ("wild", result["wild"], WINDOW), ("trend", result["joint"].trend, WINDOW),
               ("lag1", result["joint"].lag1, WINDOW)]
    return dict(p_label=c.RAW_P_LABEL, decision="DR-E2 uses the Holm-adjusted p at family closure (section 9)",
                rows=[c.comparison_row(name, source, window) for name, source, window in sources])
