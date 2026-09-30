"""E4 section 11: the X.3 synthetic design (AT-15 and AT-16 adapted), truncation-only vintages.

Generating process: H1 section 9 exactly (uc_core.validation_design.h1_design_series: 259 observations,
a = 0.3, b = 0.1, c = 1.5, s.d. 3.5, stationary initial pair, no burn-in; planted (kappa*0.3, kappa^2*0.1)
with the mean-preserving intercept in the eight positions before each onset). For each series the five H1
imposed onsets at zero-based positions 49, 99, 149, 199, 249 each define a vintage, positions 0..r-1 of the
same series, so n_v = r; there is no revision noise (disclosed in section 11: the check measures the
per-vintage fixed-date procedure, not the effect of revisions).

Streams (Annex A; ids are arguments): size generation (cell 0, replicate i); size surrogates (cell j = the
synthetic vintage 0-4, replicate i); power generation (cell = kappa index, replicate i); power surrogates
(cell = 10 * kappa index + j, replicate i). A rejection is a valid raw p <= 0.05. Development runs cannot
pass: only the registered seed, sizes and streams with every replicate valid can (uc_ext.common.summarize_*).
"""
from __future__ import annotations

from copy import deepcopy

import numpy as np

from uc_core import surrogate as s
from uc_core.constants import MASTER_SEED, POWER_KAPPAS, POWER_ONSETS
from uc_core.validation_design import h1_design_series, wilson_interval
from uc_core.validation_runner import serial
from uc_ext import common as c

from .procedure import EpisodeInput, NUMERIC_ERRORS, compare
from .streams import REGISTERED_STREAMS, Streams, check_run, stream_rng

ONSETS = tuple(POWER_ONSETS)                 # (49, 99, 149, 199, 249): n_v of the five synthetic vintages
KAPPAS = tuple(POWER_KAPPAS)
SERIES_PER_CELL = 200
SIZE_BOUNDS = (.02, .09)                     # AT-15 adapted: 0.02 to 0.09 inclusive, all 200 valid
SURROGATE_ATTEMPTS = 1000
WINDOW = 40


def truncation_vintages(series, onsets=ONSETS):
    """The synthetic vintages of one series: positions 0..r-1 for each onset r (n_v = r), views copied."""
    series = np.asarray(series, dtype=float)
    if any(r > len(series) for r in onsets):
        raise ValueError("an onset lies beyond the series")
    return [series[:r].copy() for r in onsets]


def _registered(master_seed, streams, n_series, B, kappas=KAPPAS):
    return (master_seed == MASTER_SEED and streams == REGISTERED_STREAMS and n_series == SERIES_PER_CELL
            and B == SURROGATE_ATTEMPTS and tuple(kappas) == KAPPAS)


def _record(*, cell_name, cell_index, replicate, generate_rng, null_rngs, kappa, B, window=WINDOW):
    """One synthetic replicate. Failures are recorded, not raised (as uc_ext.common.compute_record does)."""
    result = dict(cell=cell_name, cell_index=cell_index, replicate=replicate, status="generation_failed",
                  input=None, input_sha256=None, kappa=kappa, S=None, p_value=None, observed=None, comparison=None,
                  error=None, surrogate_requested=B, surrogate_attempted=0, surrogate_retained=0,
                  surrogate_no_episode=0, surrogate_failed=0, surrogate_exceedances=None,
                  surrogate_exceedance_rate=None, surrogate_exceedance_wilson=None,
                  generation_rng_before=deepcopy(generate_rng.bit_generator.state),
                  analysis_rng_before={j: deepcopy(r.bit_generator.state) for j, r in null_rngs.items()})
    try:
        series = h1_design_series(generate_rng, kappa=kappa)
        result.update(input=series.tolist(), input_sha256=c.sha256_values(series), status="comparison_failed")
        vintages = truncation_vintages(series)
        joint = compare([EpisodeInput(j, v) for j, v in enumerate(vintages)], null_rngs, window=window, B=B)
        comparison = joint.primary
        result.update(status=comparison.status, p_value=comparison.p_value, S=comparison.observed.value,
                      observed=serial(comparison.observed), comparison=serial(comparison),
                      surrogate_attempted=comparison.attempted, surrogate_retained=comparison.retained,
                      surrogate_no_episode=comparison.no_episode, surrogate_failed=comparison.failed,
                      surrogate_exceedances=comparison.exceedances)
        if comparison.retained:
            result.update(surrogate_exceedance_rate=comparison.exceedances / comparison.retained,
                          surrogate_exceedance_wilson=wilson_interval(comparison.exceedances, comparison.retained))
        result["analysis_rng_after"] = serial(joint.rng_after)
        if joint.null_error:
            result.update(status="null_model_failed", error=joint.null_error)
    except s.NullModelError as error:
        result.update(status="null_model_failed", error=f"{type(error).__name__}: {error}")
    except NUMERIC_ERRORS as error:
        result["error"] = f"{type(error).__name__}: {error}"
    result["generation_rng_after"] = deepcopy(generate_rng.bit_generator.state)
    return serial(result)


def size_replicate(replicate, *, master_seed, streams: Streams, B=SURROGATE_ATTEMPTS, allow_registered=False):
    """AT-15 adapted, one series: base process (kappa = 1), the E4 procedure at the five truncations."""
    check_run(master_seed, streams, allow_registered)
    return _record(cell_name="size", cell_index=0, replicate=replicate, kappa=1.0, B=B,
                   generate_rng=stream_rng(master_seed, streams.size_generation, 0, replicate),
                   null_rngs={j: stream_rng(master_seed, streams.size_null, j, replicate) for j in range(len(ONSETS))})


def power_replicate(cell, replicate, *, master_seed, streams: Streams, B=SURROGATE_ATTEMPTS, kappas=KAPPAS,
                    allow_registered=False):
    """AT-16 adapted, one series of power cell `cell` (kappa index): planted signal, five truncations."""
    check_run(master_seed, streams, allow_registered)
    return _record(cell_name=f"power_{cell}", cell_index=cell, replicate=replicate, kappa=kappas[cell], B=B,
                   generate_rng=stream_rng(master_seed, streams.power_generation, cell, replicate),
                   null_rngs={j: stream_rng(master_seed, streams.power_null, 10 * cell + j, replicate)
                              for j in range(len(ONSETS))})


def run_size_check(*, master_seed, streams, n_series=SERIES_PER_CELL, B=SURROGATE_ATTEMPTS, replicates=None,
                   allow_registered=False, progress=None):
    check_run(master_seed, streams, allow_registered)
    n_series = s._integer(n_series, "n_series")
    records = []
    for replicate in (range(n_series) if replicates is None else replicates):
        records.append(size_replicate(replicate, master_seed=master_seed, streams=streams, B=B,
                                      allow_registered=allow_registered))
        if progress:
            progress(records[-1])
    summary = (c.summarize_size(records, requested=n_series, bounds=SIZE_BOUNDS,
                                registered=_registered(master_seed, streams, n_series, B))
               if replicates is None else None)
    return dict(master_seed=master_seed, streams=serial(streams), n_series=n_series, B=B, records=records,
                summary=summary)


def summarize_power(records, *, n_series, kappas=KAPPAS, registered=False):
    cells = [c.summarize_cell([r for r in records if r["cell_index"] == i], n_series) for i in range(len(kappas))]
    return c.summarize_power_cells(cells, kappas, registered=registered)


def run_power_check(*, master_seed, streams, n_series=SERIES_PER_CELL, B=SURROGATE_ATTEMPTS, kappas=KAPPAS,
                    cells=None, replicates=None, allow_registered=False, progress=None):
    check_run(master_seed, streams, allow_registered)
    n_series = s._integer(n_series, "n_series")
    kappas = tuple(float(k) for k in kappas)
    records = []
    for cell in (range(len(kappas)) if cells is None else cells):
        for replicate in (range(n_series) if replicates is None else replicates):
            records.append(power_replicate(cell, replicate, master_seed=master_seed, streams=streams, B=B,
                                           kappas=kappas, allow_registered=allow_registered))
            if progress:
                progress(records[-1])
    summary = (summarize_power(records, n_series=n_series, kappas=kappas,
                               registered=_registered(master_seed, streams, n_series, B, kappas))
               if cells is None and replicates is None else None)
    return dict(master_seed=master_seed, streams=serial(streams), n_series=n_series, B=B, kappas=kappas,
                records=records, summary=summary)
