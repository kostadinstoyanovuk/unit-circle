"""Shared helpers for the E1 and E3 synthetic checks and the DR-2 family adjustment.

Importing this module runs no experiment and reads no data. Every random number
comes from Generator(PCG64(SeedSequence([master_seed, stream_id, cell, replicate]))).
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import math

import numpy as np

from uc_core import surrogate as s
from uc_core.constants import MASTER_SEED
from uc_core.h1_reporting import _validated_accounting
from uc_core.validation_design import wilson_interval
from uc_core.validation_runner import serial

NUMERIC_ERRORS = (ValueError, FloatingPointError, np.linalg.LinAlgError)
# Development runs reuse the registered stream ids under a different master seed, as the
# H1 runner does (uc_core.validation_runner.DEVELOPMENT_MASTER_SEED = 20260926).
DEVELOPMENT_MASTER_SEED = 20260928
REJECTION_LEVEL = .05
D80_TARGET = .80
DECREASE_Z = 1.96
RAW_P_LABEL = "raw, not family-adjusted"      # E1/E3 section 9: the label of every reported raw p


class RegisteredRunRefused(RuntimeError):
    """The registered master seed was requested without the caller's explicit gate flag."""


def check_seed(master_seed, allow_registered):
    """Registered coordinates run only when the caller has verified the gate (G4) itself."""
    if isinstance(master_seed, (bool, np.bool_)) or not isinstance(master_seed, (int, np.integer)) or master_seed < 0:
        raise ValueError("master_seed must be a nonnegative integer")
    if int(master_seed) == MASTER_SEED and allow_registered is not True:
        raise RegisteredRunRefused("Master seed 1927 is the registered seed; pass allow_registered=True "
                                   "only after the extension's public registration and tag are verified")
    return int(master_seed)


def stream_rng(master_seed, stream_id, cell=0, replicate=0) -> np.random.Generator:
    for value in (master_seed, stream_id, cell, replicate):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 0:
            raise ValueError("Seed coordinates must be nonnegative integers")
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(
        [int(master_seed), int(stream_id), int(cell), int(replicate)])))


def sha256_values(values) -> str:
    return hashlib.sha256(np.asarray(values, dtype=float).astype('<f8').tobytes()).hexdigest()


def compute_record(*, cell_name, cell_index, replicate, generation_rng, analysis_rng, generate, observe,
                   compare, requested):
    """One synthetic replicate, recorded as uc_core.validation_runner.compute_replicate records H1's.

    generate(rng) -> series; observe(series) -> PreOnsetResult-like object with mean_change;
    compare(series, rng) -> uc_core.surrogate.Comparison-like object. Failures are recorded, not raised.
    """
    result = dict(cell=cell_name, cell_index=cell_index, replicate=replicate, status='generation_failed',
                  input=None, input_sha256=None,
                  generation_rng_before=deepcopy(generation_rng.bit_generator.state),
                  analysis_rng_before=deepcopy(analysis_rng.bit_generator.state),
                  S=None, p_value=None, observed=None, comparison=None, error=None,
                  surrogate_requested=requested, surrogate_attempted=0, surrogate_retained=0,
                  surrogate_no_episode=0, surrogate_failed=0, surrogate_exceedances=None,
                  surrogate_exceedance_rate=None, surrogate_exceedance_wilson=None)
    try:
        values = generate(generation_rng)
        result.update(input=np.asarray(values).tolist(), input_sha256=sha256_values(values))
        result['status'] = 'observed_statistic_failed'
        observed = observe(values)
        result.update(S=observed.mean_change, observed=serial(observed))
        result['status'] = 'comparison_failed'
        comparison = compare(values, analysis_rng)
        result.update(status=comparison.status, p_value=comparison.p_value, comparison=serial(comparison),
                      surrogate_attempted=comparison.attempted, surrogate_retained=comparison.retained,
                      surrogate_no_episode=comparison.no_episode, surrogate_failed=comparison.failed,
                      surrogate_exceedances=comparison.exceedances)
        if comparison.retained:
            result.update(surrogate_exceedance_rate=comparison.exceedances / comparison.retained,
                          surrogate_exceedance_wilson=wilson_interval(comparison.exceedances, comparison.retained))
    except s.NullModelError as error:
        result.update(status='null_model_failed', error=f'{type(error).__name__}: {error}')
    except NUMERIC_ERRORS as error:
        result['error'] = f'{type(error).__name__}: {error}'
    result['generation_rng_after'] = deepcopy(generation_rng.bit_generator.state)
    result['analysis_rng_after'] = deepcopy(analysis_rng.bit_generator.state)
    return serial(result)


def comparison_row(analysis, source, window):
    """One reporting row of a single-run comparison (S10; E1/E3 sections 8-9, as H1 section 6).

    The fields of uc_core.h1_reporting.comparison_rows, whose ledger validation it reuses, plus:
    m = eligible episodes; k = count of positive components (Delta > 0 for change statistics, tau > 0 for
    the Kendall trend); K = exceedances; B' = retained draws; q = K/B' with its 95% Wilson interval; and
    the raw p labelled "raw, not family-adjusted" (DR-2 adjusts only at family closure). A row whose
    accounting fails validation is kept with status 'report_failed' and the reason.
    """
    source = serial(source)
    observed = source.get("observed") or {}
    value = observed.get("value", observed.get("mean_change"))
    components = observed.get("components", observed.get("changes"))
    onsets = observed.get("eligible_onsets")
    row = dict(analysis=analysis, window=window, status=source.get("status"), value=value,
               m=len(onsets) if onsets is not None else None,
               k=sum(v > 0 for v in components) if components is not None else None,
               p_value=None, p_label=RAW_P_LABEL, requested=source.get("requested"), attempted=None,
               retained=None, no_eligible=None, failed=None, exceedances=None, B_prime=None,
               p_grid_spacing=source.get("p_grid_spacing"), q=None, q_wilson=None,
               error=source.get("error") or observed.get("error"))
    try:
        if onsets is not None and components is not None and len(onsets) != len(components):
            raise ValueError("Observed components and eligible episodes disagree")
        attempted, retained, empty, failed, p, count = _validated_accounting(source, value)
    except (ValueError, KeyError, TypeError) as error:
        return row | dict(status="report_failed", error=f"{type(error).__name__}: {error}")
    row.update(p_value=p, attempted=attempted, retained=retained, no_eligible=empty, failed=failed,
               exceedances=count, B_prime=retained)
    if retained and count is not None:
        row.update(q=count / retained, q_wilson=wilson_interval(count, retained))
    return row


def design_series(rng, *, kappa, n, onsets, signal_length):
    """H1 section 9 generating process for any length, onsets and planted-signal length.

    One standard_normal(2) and one normal(0, 3.5, size=n-2) call, in that order; no burn-in. The
    coefficients (kappa*0.3, kappa^2*0.1) and mean-preserving intercept apply only in the
    signal_length positions before each onset. With n=259, H1's onsets and signal_length=8 this is
    uc_core.validation_design.h1_design_series bit for bit (tested). Unlike that function, kappa
    outside the registered set is accepted, for development fixtures only.
    """
    s._generator(rng)
    kappa = float(kappa)
    if not math.isfinite(kappa) or kappa <= 0:
        raise ValueError("kappa must be finite and positive")
    n = s._integer(n, "n", 5)
    signal_length = s._integer(signal_length, "signal_length")
    onsets = tuple(int(t) for t in onsets)
    if any(t - signal_length < 2 or t >= n for t in onsets) or any(
            b - signal_length <= a for a, b in zip(onsets, onsets[1:])):
        raise ValueError("Onsets must be increasing, inside the series, with non-overlapping signals after position 1")
    variance = 1225 / 88
    covariance = variance / 3
    z = rng.standard_normal(2)
    values = np.empty(n)
    values[0] = 2.5 + math.sqrt(variance) * z[0]
    values[1] = 2.5 + covariance / math.sqrt(variance) * z[0] + math.sqrt(variance - covariance ** 2 / variance) * z[1]
    noise = rng.normal(0, 3.5, size=n - 2)
    active = np.zeros(n, dtype=bool)
    for onset in onsets:
        active[onset - signal_length:onset] = True
    for t in range(2, n):
        scale = kappa if active[t] else 1.
        a, b = .3 * scale, .1 * scale ** 2
        intercept = 2.5 * (1 - a - b) if scale != 1. else 1.5
        values[t] = intercept + a * values[t - 1] + b * values[t - 2] + noise[t - 2]
    return values


def _valid(record):
    p, value = record.get('p_value'), record.get('S')
    return (record.get('status') == 'ok' and isinstance(p, (int, float)) and isinstance(value, (int, float))
            and math.isfinite(p) and math.isfinite(value) and 0 <= p <= 1)


def summarize_cell(records, requested):
    """Accounting for one cell with its nominal denominator, as H1 section 9 reports a cell."""
    if isinstance(requested, bool) or not isinstance(requested, int) or requested < 1:
        raise ValueError("requested must be a positive integer")
    replicates = [r['replicate'] for r in records]
    if len(set(replicates)) != len(replicates) or any(not 0 <= r < requested for r in replicates):
        raise ValueError("Records must have unique replicate numbers inside the requested range")
    valid = [r for r in records if _valid(r)]
    rejected = sum(r['p_value'] <= REJECTION_LEVEL for r in valid)
    missing = requested - len(valid)
    failures = {}
    for record in records:
        if not _valid(record):
            failures[record['status']] = failures.get(record['status'], 0) + 1
    complete = missing == 0
    statistics = [r['S'] for r in sorted(valid, key=lambda r: r['replicate'])]
    rate = rejected / requested if complete else None
    return dict(requested=requested, attempted=len(records), valid=len(valid), rejected=rejected,
                unfinished=requested - len(records), failures=failures,
                accounting_bounds=(rejected / requested, (rejected + missing) / requested),
                valid_only_rate=rejected / len(valid) if valid else None,
                rate=rate, rate_se=math.sqrt(rate * (1 - rate) / requested) if complete else None,
                rate_wilson=wilson_interval(rejected, requested) if complete else None,
                mean_S=float(np.mean(statistics)) if complete else None,
                mean_S_se=(float(np.std(statistics, ddof=1) / math.sqrt(requested))
                           if complete and requested > 1 else None))


def summarize_size(records, *, requested, bounds, registered):
    cell = summarize_cell(records, requested)
    passed = bool(registered and cell['rate'] is not None and bounds[0] <= cell['rate'] <= bounds[1])
    return dict(cell=cell, bounds=tuple(bounds), registered_design=bool(registered), passed=passed,
                scope='Development runs cannot pass; a pass needs the registered seed, sizes and all replicates valid.')


def summarize_power_cells(cells, kappas, *, registered):
    """Adjacent-difference flags and first-raw-crossing D80 (H1 section 9) for any requested size.

    `cells` are summarize_cell outputs in kappa order. At 200 requested per cell and four cells this
    reproduces uc_core.validation_design.summarize_power (tested).
    """
    if len(cells) != len(kappas) or len(kappas) < 1:
        raise ValueError("One summarized cell per kappa is required")
    rows = [dict(kappa=k, **cell) for k, cell in zip(kappas, cells)]
    result = dict(cells=rows, D80=None, kappa80=None, crossing=None, adjacent_comparisons=[],
                  decrease_flags=[], registered_design=bool(registered), passed=False)
    if any(row['rate'] is None for row in rows):
        return result
    for previous, current in zip(rows, rows[1:]):
        se = math.hypot(previous['rate_se'], current['rate_se'])
        difference = current['rate'] - previous['rate']
        flag = difference < -DECREASE_Z * se
        result['adjacent_comparisons'].append(dict(left_kappa=previous['kappa'], right_kappa=current['kappa'],
                                                   difference=difference, standard_error=se,
                                                   decrease_flag=flag))
        result['decrease_flags'].append(flag)
    result['passed'] = bool(registered and not any(result['decrease_flags']))
    for index, row in enumerate(rows):
        if row['rate'] < D80_TARGET:
            continue
        if index == 0:
            result.update(D80=row['mean_S'], kappa80=row['kappa'], crossing=dict(left=0, right=0, weight=0.))
        else:
            left = rows[index - 1]
            weight = (D80_TARGET - left['rate']) / (row['rate'] - left['rate'])
            result.update(D80=left['mean_S'] + weight * (row['mean_S'] - left['mean_S']),
                          kappa80=left['kappa'] + weight * (row['kappa'] - left['kappa']),
                          crossing=dict(left=index - 1, right=index, weight=weight))
        break
    return result


def branch_b_diagnostic(adjusted_p, d80, interval):
    """H1 section 10 Branch B condition with the Holm-adjusted p; a labelled diagnostic only."""
    if adjusted_p is None or d80 is None or interval is None:
        return dict(status='unavailable', condition=None)
    return dict(status='ok', condition=bool(adjusted_p > REJECTION_LEVEL and interval[1] < d80))


def holm_adjust(members):
    """DR-2 (H1 section 11): members maps extension number -> raw p, or None for never run/failed.

    None enters with Holm input 1. Ties are broken by extension number. Returns
    {number: dict(raw_p, holm_input, adjusted_p)}.
    """
    if not members:
        raise ValueError("The family needs at least one member")
    inputs = {}
    for number, p in members.items():
        if isinstance(number, bool) or not isinstance(number, int):
            raise ValueError("Members are keyed by integer extension number")
        if p is not None and (not math.isfinite(p) or not 0 < p <= 1):
            raise ValueError("Raw p-values must lie in (0, 1] or be None")
        inputs[number] = 1.0 if p is None else float(p)
    order = sorted(inputs, key=lambda k: (inputs[k], k))
    h = len(order)
    result, running = {}, 0.0
    for rank, number in enumerate(order, start=1):
        running = max(running, (h - rank + 1) * inputs[number])
        result[number] = dict(raw_p=members[number], holm_input=inputs[number], adjusted_p=min(1.0, running))
    return dict(sorted(result.items()))
