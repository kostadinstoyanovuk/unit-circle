"""E1 (prereg/E1.md, fixed at research commit 5a26bfc): annual rolling AR(2), W = 30.

Changes from H1, and nothing else: 316 annual growth values 100*dln Y (1701-2016); W = 30
(sensitivity 25, 35); Delta = M(r-1) - M(r-3); a qualifying run is one or more negative years;
merge when onset - previous end <= 2; onsets in 1914-18, 1939-45 and 2020 are exogenous and
excluded from every statistic; Kendall over 4 years; streams 5100-5131.

Synthetic-only blind build. No function reads or downloads data: the caller supplies values.
Rolling fits, episodes, eligibility, the fitted null, surrogate draws, p-values, secondary
statistics and the episode interval are the registered uc_core functions, imported unchanged.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import math

import numpy as np

from uc_core import surrogate as s
from uc_core.constants import MASTER_SEED, POWER_KAPPAS
from uc_core.h1 import JointComparison, Observation, _comparison, _failed, _observation, fixed_date_test
from uc_core.recession import PreOnsetResult, episodes, pre_onset_changes
from uc_core.rolling import _observations_and_index, max_modulus
from uc_core.secondary import (episode_percentile_interval, mean_pre_onset_trend, rolling_lag1,
                               signed_pre_onset_changes)

from . import common as c

# Section 4-5: sample and growth.
FIRST_LEVEL_YEAR, LAST_YEAR = 1700, 2016
N_LEVELS = LAST_YEAR - FIRST_LEVEL_YEAR + 1          # 317
N_GROWTH = N_LEVELS - 1                               # 316
FIRST_GROWTH_YEAR = FIRST_LEVEL_YEAR + 1              # year(i) = 1701 + i
# Sections 6-8 and 10.
WINDOW = 30
SENSITIVITY_WINDOWS = (25, 35)
LOOKBACK = 2
MINIMUM_RUN = 1
MERGE = 2
TREND_SPAN = 4
EXOGENOUS_YEARS = frozenset([*range(1914, 1919), *range(1939, 1946), 2020])
SURROGATE_ATTEMPTS = 1000
EPISODE_RESAMPLES = 10000
# Annex A.
STREAM_IDS = dict(primary=5100, window25=5101, window35=5102, fixed=5103, wild=5104, interval=5105,
                  size_generation=5120, size_null=5121, power_generation=5130, power_null=5131)
# Section 11 (X.3).
SERIES_PER_CELL = 200
SIZE_BOUNDS = (.02, .09)
POWER_ONSETS = (34, 74, 114, 154, 194, 234, 274)      # one-based 35, 75, ..., 275
SIGNAL_LENGTH = 2
KAPPAS = POWER_KAPPAS                                 # (1.0, 1.2, 1.4, 1.6), as H1


@dataclass(frozen=True)
class Rules:
    """Episode and indicator rules. E1 values by default; H1_RULES reproduces H1 for agreement tests."""
    window: int = WINDOW
    lookback: int = LOOKBACK
    minimum_run: int = MINIMUM_RUN
    merge: int = MERGE
    first_year: int = FIRST_GROWTH_YEAR
    exogenous_years: frozenset = EXOGENOUS_YEARS
    trend_span: int = TREND_SPAN


E1_RULES = Rules()
H1_RULES = Rules(window=40, lookback=8, minimum_run=2, merge=8, first_year=0,
                 exogenous_years=frozenset(), trend_span=16)


def annual_growth(years, levels):
    """Section 4 stop rules and section 5 growth: 317 contiguous levels 1700-2016 -> 316 values.

    Rows outside 1700-2016 are dropped by year alone; their values are not inspected.
    Raises ValueError (stop and amend) on a missing, duplicated or unidentifiable year, or a
    non-positive, non-finite or non-numeric level. Returns (growth_years, growth).

    Years must be Python or NumPy integers. Spreadsheet readers often return float years such as
    1700.0; those stop here (the rule fails closed, review C4), so the X.2 extraction tool must convert
    the year column to int, after checking every value is integral, before calling this function.
    """
    years = list(years)
    levels = list(levels)
    if len(years) != len(levels):
        raise ValueError("Years and levels differ in length")
    for year in years:
        if isinstance(year, (bool, np.bool_)) or not isinstance(year, (int, np.integer)):
            raise ValueError(f"Year {year!r} cannot be identified unambiguously as an integer year")
    selected = [(int(y), v) for y, v in zip(years, levels) if FIRST_LEVEL_YEAR <= y <= LAST_YEAR]
    found = [y for y, _ in selected]
    if len(set(found)) != len(found):
        raise ValueError("A year in 1700-2016 is duplicated")
    if found != list(range(FIRST_LEVEL_YEAR, LAST_YEAR + 1)):
        raise ValueError("Years 1700-2016 are not exactly 317 contiguous increasing years")
    values = []
    for year, value in selected:
        if isinstance(value, (bool, np.bool_, str)) or value is None:
            raise ValueError(f"Non-numeric level in {year}")
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Non-numeric level in {year}") from error
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"Non-positive or non-finite level in {year}")
        values.append(number)
    level = np.asarray(values)
    growth = 100 * (np.log(level[1:]) - np.log(level[:-1]))
    return tuple(range(FIRST_GROWTH_YEAR, LAST_YEAR + 1)), growth


def design_series(rng, *, kappa=1., n=N_GROWTH, onsets=POWER_ONSETS, signal_length=SIGNAL_LENGTH):
    """Section 11 generating process: H1 section 9 recursion, length 316, planted signal at r-2, r-1.

    common.design_series with the E1 defaults (one standard_normal(2) and one normal(0, 3.5, size=314)
    call; coefficients (kappa*0.3, kappa^2*0.1) and the mean-preserving intercept at r-2 and r-1 only).
    """
    return c.design_series(rng, kappa=kappa, n=n, onsets=onsets, signal_length=signal_length)


def split_episodes(values, rules=E1_RULES):
    """Section 7: runs, merging (before classification), then the exogenous rule by onset year."""
    merged = episodes(values, minimum_run=rules.minimum_run, merge=rules.merge)
    exogenous = tuple(e for e in merged if rules.first_year + e.onset in rules.exogenous_years)
    endogenous = tuple(e for e in merged if rules.first_year + e.onset not in rules.exogenous_years)
    return endogenous, exogenous


def statistic(values, rules=E1_RULES, *, fixed_onsets=None):
    """S over eligible non-exogenous episodes (or supplied fixed onsets); mirrors uc_core.surrogate._statistic."""
    if fixed_onsets is None:
        onsets = tuple(e.onset for e in split_episodes(values, rules)[0])
    else:
        onsets = tuple(fixed_onsets)
    if not any(t >= rules.window + rules.lookback for t in onsets):
        return PreOnsetResult(None, (), (), onsets)
    return pre_onset_changes(max_modulus(values, rules.window), onsets, lookback=rules.lookback)


def _measure(values, rules):
    """uc_core.h1._measure with the E1 episode rules; exogenous episodes never enter a statistic."""
    onsets = tuple(e.onset for e in split_episodes(values, rules)[0])
    output = {name: Observation("no_eligible_episode", None, ineligible_onsets=onsets)
              for name in ("primary", "trend", "lag1")}
    primary_eligible = any(t >= rules.window + rules.lookback for t in onsets)
    trend_eligible = any(t >= rules.window + rules.trend_span - 1 for t in onsets)
    modulus, modulus_error = None, None
    if primary_eligible or trend_eligible:
        try:
            modulus = max_modulus(values, rules.window)
        except c.NUMERIC_ERRORS as error:
            modulus_error = error
    for name, eligible in (("primary", primary_eligible), ("trend", trend_eligible)):
        if not eligible:
            continue
        if modulus_error is not None:
            output[name] = _failed(modulus_error)
            continue
        try:
            result = (mean_pre_onset_trend(modulus, onsets, span=rules.trend_span) if name == "trend"
                      else pre_onset_changes(modulus, onsets, lookback=rules.lookback))
            output[name] = _observation(result, trend=name == "trend")
        except c.NUMERIC_ERRORS as error:
            output[name] = _failed(error)
    if primary_eligible:
        try:
            output["lag1"] = _observation(signed_pre_onset_changes(
                rolling_lag1(values, rules.window), onsets, lookback=rules.lookback))
        except c.NUMERIC_ERRORS as error:
            output["lag1"] = _failed(error)
    return output


def primary_with_comparators(values, *, B, rng, rules=E1_RULES):
    """Stream 5100 design: one set of residual paths for primary, Kendall and lag-one (section 10).

    Same control flow as uc_core.h1.primary_with_comparators; with H1_RULES it reproduces it.
    """
    B = s._integer(B, "B")
    s._generator(rng)
    x, _ = _observations_and_index(values)
    before = deepcopy(rng.bit_generator.state)
    observed = _measure(x, rules)
    model, null_error = None, None
    records = {name: [] for name in observed}
    generated = 0
    if any(o.status == "ok" for o in observed.values()):
        try:
            model = s.prepare_null(x)
        except s.NullModelError as error:
            null_error = str(error)
    if model is not None:
        for number in range(B):
            generated += 1
            try:
                path = s.draw_surrogate(model, rng)
                measures = _measure(path, rules)
            except c.NUMERIC_ERRORS as error:
                measures = {name: _failed(error) for name in observed}
            for name in observed:
                if observed[name].status != "ok":
                    continue
                value = measures[name]
                records[name].append(s.Attempt(number, "retained" if value.status == "ok" else value.status,
                                               value.value, value.eligible_onsets, value.components, value.error))
    comparisons = {name: _comparison(name, observed[name], records[name], B) for name in observed}
    if null_error:
        comparisons = {name: replace(result, status="null_model_failed") if observed[name].status == "ok"
                       else result for name, result in comparisons.items()}
    return JointComparison(**comparisons, null_model=model, rng_before=before,
                           rng_after=deepcopy(rng.bit_generator.state), generated_attempts=generated,
                           null_error=null_error)


def csd_test(values, *, B, rng, rules=E1_RULES, onset_mode="endogenous", innovation_mode="residual"):
    """uc_core.surrogate.csd_test with the E1 statistic (section 9 and the section 10 sensitivities).

    Exactly B attempts; only draws without an eligible non-exogenous episode are dropped; failures
    invalidate p. onset_mode='fixed' reuses the observed eligible onsets (stream 5103 analysis).
    """
    B = s._integer(B, "B")
    s._generator(rng)
    if onset_mode not in ("endogenous", "fixed") or innovation_mode not in ("residual", "wild"):
        raise ValueError("Unsupported onset or innovation mode")
    x, _ = _observations_and_index(values)
    before = deepcopy(rng.bit_generator.state)
    observed = statistic(x, rules)
    if observed.mean_change is None:
        return s.Comparison("observed_not_estimable", observed, None, B, 0, 0, 0, 0, None, None, (), None,
                            rules.window, rules.lookback, rules.merge, onset_mode, innovation_mode,
                            before, deepcopy(rng.bit_generator.state))
    model = s.prepare_null(x)
    fixed = observed.eligible_onsets if onset_mode == "fixed" else None
    records = []
    for number in range(B):
        try:
            simulated = s.draw_surrogate(model, rng, kind=innovation_mode)
            result = statistic(simulated, rules, fixed_onsets=fixed)
            if result.mean_change is None:
                records.append(s.Attempt(number, "no_eligible_episode", None))
            else:
                if not math.isfinite(result.mean_change):
                    raise FloatingPointError("Non-finite surrogate statistic")
                records.append(s.Attempt(number, "retained", result.mean_change,
                                         result.eligible_onsets, result.changes))
        except c.NUMERIC_ERRORS as error:
            records.append(s.Attempt(number, "failed", None, error=f"{type(error).__name__}: {error}"))
    kept = [r.statistic for r in records if r.status == "retained"]
    empty = sum(r.status == "no_eligible_episode" for r in records)
    failed = sum(r.status == "failed" for r in records)
    p = None if failed else s.monte_carlo_pvalue(observed.mean_change, kept)
    status = "invalid_surrogate_failure" if failed else ("no_retained_surrogates" if not kept else "ok")
    exceedances = sum(v >= observed.mean_change for v in kept) if kept else None
    return s.Comparison(status, observed, p, B, len(records), len(kept), empty, failed, exceedances,
                        1 / (len(kept) + 1) if kept else None, tuple(records), model, rules.window,
                        rules.lookback, rules.merge, onset_mode, innovation_mode, before,
                        deepcopy(rng.bit_generator.state))


def episode_record(values, rules=E1_RULES):
    """Every merged episode with its runs, years, classification and (where computable) Delta.

    Exogenous rows form the section 10 descriptive table; they never enter S.
    """
    endogenous, exogenous = split_episodes(values, rules)
    modulus = max_modulus(values, rules.window)
    rows = []
    for kind, group in (("endogenous", endogenous), ("exogenous", exogenous)):
        if not group:
            continue
        result = pre_onset_changes(modulus, [e.onset for e in group], lookback=rules.lookback)
        deltas = dict(zip(result.eligible_onsets, result.changes))
        for e in group:
            computable = e.onset in deltas
            rows.append(dict(onset=e.onset, end=e.end, onset_year=rules.first_year + e.onset,
                             end_year=rules.first_year + e.end,
                             runs=[(run.onset, run.end) for run in e.runs],
                             classification=("exogenous" if kind == "exogenous" else
                                             "eligible" if computable else "ineligible"),
                             delta=deltas.get(e.onset)))
    return sorted(rows, key=lambda row: row["onset"])


def territory_flags(rows, stretches, rules=E1_RULES):
    """Section 10 descriptive: the territory stretch(es) under each eligible episode's two windows.

    rows: episode_record output. stretches: [(first_level_year, last_level_year, territory), ...] from the
    X.2 territory record. The two windows use growth positions r-W-2..r-1; growth in year y uses the
    levels of years y-1 and y, so the levels involved are year(r-W-2)-1 .. year(r-1). An episode whose
    levels span more than one stretch is flagged, never excluded.
    """
    ordered = sorted(stretches)
    result = []
    for row in rows:
        if row["classification"] != "eligible":
            continue
        onset = row["onset"]
        first_level = rules.first_year + onset - rules.window - rules.lookback - 1
        last_level = rules.first_year + onset - 1
        touched = [name for start, stop, name in ordered if start <= last_level and stop >= first_level]
        result.append(dict(onset=onset, onset_year=row["onset_year"], level_years=(first_level, last_level),
                           territories=touched, crosses_boundary=len(touched) > 1))
    return result


def analyze(values, *, master_seed=MASTER_SEED, allow_registered=False, B=SURROGATE_ATTEMPTS,
            interval_B=EPISODE_RESAMPLES):
    """The single real run (X.4) assembled in memory, as uc_core.h1.analyze_h1: every section 9-10 output.

    Requires exactly 316 growth values. The registered seed 1927 runs only with allow_registered=True,
    which the caller sets after verifying registration, tag and the X.3 record (Annex B).
    """
    master_seed = c.check_seed(master_seed, allow_registered)
    B = s._integer(B, "B")
    interval_B = s._integer(interval_B, "interval_B")
    x, _ = _observations_and_index(values)
    if len(x) != N_GROWTH:
        raise ValueError(f"E1 uses exactly {N_GROWTH} growth values (1701-2016)")

    def rng(name):
        return c.stream_rng(master_seed, STREAM_IDS[name])

    joint = primary_with_comparators(x, B=B, rng=rng("primary"))

    def sensitivity(name, **kwargs):
        rules = replace(E1_RULES, window=kwargs.pop("window", WINDOW))
        try:
            return csd_test(x, B=B, rng=rng(name), rules=rules, **kwargs)
        except s.NullModelError as error:
            return dict(status="null_model_failed", p_value=None, observed=statistic(x, rules),
                        requested=B, attempted=0, error=str(error))
        except c.NUMERIC_ERRORS as error:
            return dict(status="observed_statistic_failed", p_value=None, requested=B, attempted=0,
                        error=f"{type(error).__name__}: {error}")

    try:
        episodes_table = episode_record(x)
    except c.NUMERIC_ERRORS as error:
        episodes_table = dict(status="failed", error=f"{type(error).__name__}: {error}")
    result = dict(
        master_seed=master_seed,
        input_sha256=c.sha256_values(x),
        episodes=episodes_table,
        joint=joint,
        window25=sensitivity("window25", window=25),
        window35=sensitivity("window35", window=35),
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
    """S10: sections 8-9 reporting quantities for every comparison of analyze(): m, k = count(Delta > 0),
    K, B', q = K/B' with its Wilson interval, and the raw p labelled "raw, not family-adjusted"."""
    sources = [("primary", result["joint"].primary, WINDOW), ("window25", result["window25"], 25),
               ("window35", result["window35"], 35), ("fixed", result["fixed"], WINDOW),
               ("wild", result["wild"], WINDOW), ("trend", result["joint"].trend, WINDOW),
               ("lag1", result["joint"].lag1, WINDOW)]
    return dict(p_label=c.RAW_P_LABEL, decision="DR-E1 uses the Holm-adjusted p at family closure (section 10)",
                rows=[c.comparison_row(name, source, window) for name, source, window in sources])


# ---------------------------------------------------------------- X.3 size and power checks (section 11)

def size_replicate(replicate, *, master_seed, B=SURROGATE_ATTEMPTS, allow_registered=False):
    """One AT-15-analogue replicate: stream 5120 generation, stream 5121 endogenous residual surrogates."""
    master_seed = c.check_seed(master_seed, allow_registered)
    return c.compute_record(
        cell_name="size", cell_index=0, replicate=replicate,
        generation_rng=c.stream_rng(master_seed, STREAM_IDS["size_generation"], 0, replicate),
        analysis_rng=c.stream_rng(master_seed, STREAM_IDS["size_null"], 0, replicate),
        generate=lambda g: design_series(g, kappa=1.),
        observe=lambda v: statistic(v),
        compare=lambda v, g: csd_test(v, B=B, rng=g),
        requested=B)


def power_replicate(cell, replicate, *, master_seed, B=SURROGATE_ATTEMPTS, kappas=KAPPAS,
                    allow_registered=False):
    """One AT-16-analogue replicate: stream 5130 generation, stream 5131 fixed-date surrogates.

    S is computed at the seven imposed positions with W = 30 (uc_core.h1.fixed_date_test).
    """
    master_seed = c.check_seed(master_seed, allow_registered)
    kappa = kappas[cell]
    return c.compute_record(
        cell_name=f"power_{cell}", cell_index=cell, replicate=replicate,
        generation_rng=c.stream_rng(master_seed, STREAM_IDS["power_generation"], cell, replicate),
        analysis_rng=c.stream_rng(master_seed, STREAM_IDS["power_null"], cell, replicate),
        generate=lambda g: design_series(g, kappa=kappa),
        observe=lambda v: s._statistic(v, window=WINDOW, lookback=LOOKBACK, merge=MERGE, fixed_onsets=POWER_ONSETS),
        compare=lambda v, g: fixed_date_test(v, POWER_ONSETS, B=B, rng=g, window=WINDOW, lookback=LOOKBACK),
        requested=B) | dict(kappa=kappa)


def x3_input(check, cell, replicate, *, master_seed, kappas=KAPPAS, allow_registered=False):
    """The generated series of one X.3 replicate, rebuilt from its seed coordinates alone.

    The runner uses it to re-verify saved records before resuming (H1 section 8: "verifying already
    saved output"). It draws exactly what size_replicate/power_replicate draw for generation.
    """
    master_seed = c.check_seed(master_seed, allow_registered)
    if check == "size" and cell == 0:
        return design_series(c.stream_rng(master_seed, STREAM_IDS["size_generation"], 0, replicate), kappa=1.)
    if check == "power":
        return design_series(c.stream_rng(master_seed, STREAM_IDS["power_generation"], cell, replicate),
                             kappa=kappas[cell])
    raise ValueError("Unknown X.3 check or cell")


def x3_settings(**_):
    """E1 has no run-time settings; recorded as an empty mapping in manifests and records."""
    return {}


def x3_arguments(settings):
    """No keyword arguments realise E1's (empty) settings."""
    return {}


def _registered(master_seed, n_series, B, kappas=KAPPAS):
    return master_seed == MASTER_SEED and n_series == SERIES_PER_CELL and B == SURROGATE_ATTEMPTS and tuple(kappas) == KAPPAS


def run_size_check(*, master_seed=c.DEVELOPMENT_MASTER_SEED, n_series=SERIES_PER_CELL, B=SURROGATE_ATTEMPTS,
                   replicates=None, allow_registered=False, progress=None):
    """AT-15 analogue. `replicates` (default all) lets a caller split or resume the cell by coordinates."""
    master_seed = c.check_seed(master_seed, allow_registered)
    n_series = s._integer(n_series, "n_series")
    chosen = range(n_series) if replicates is None else replicates
    records = []
    for replicate in chosen:
        records.append(size_replicate(replicate, master_seed=master_seed, B=B, allow_registered=allow_registered))
        if progress:
            progress(records[-1])
    summary = (c.summarize_size(records, requested=n_series, bounds=SIZE_BOUNDS,
                                registered=_registered(master_seed, n_series, B))
               if replicates is None else None)
    return dict(master_seed=master_seed, n_series=n_series, B=B, records=records, summary=summary)


def run_power_check(*, master_seed=c.DEVELOPMENT_MASTER_SEED, n_series=SERIES_PER_CELL, B=SURROGATE_ATTEMPTS,
                    kappas=KAPPAS, cells=None, replicates=None, allow_registered=False, progress=None):
    """AT-16 analogue with D80. `cells`/`replicates` (default all) select coordinates for splitting."""
    master_seed = c.check_seed(master_seed, allow_registered)
    n_series = s._integer(n_series, "n_series")
    kappas = tuple(float(k) for k in kappas)
    chosen_cells = range(len(kappas)) if cells is None else cells
    chosen = range(n_series) if replicates is None else replicates
    records = []
    for cell in chosen_cells:
        for replicate in chosen:
            records.append(power_replicate(cell, replicate, master_seed=master_seed, B=B, kappas=kappas,
                                           allow_registered=allow_registered))
            if progress:
                progress(records[-1])
    summary = (summarize_power(records, n_series=n_series, kappas=kappas,
                               registered=_registered(master_seed, n_series, B, kappas))
               if cells is None and replicates is None else None)
    return dict(master_seed=master_seed, n_series=n_series, B=B, kappas=kappas, records=records, summary=summary)


def summarize_power(records, *, n_series, kappas=KAPPAS, registered=False):
    cells = [c.summarize_cell([r for r in records if r["cell_index"] == index], n_series)
             for index in range(len(kappas))]
    return c.summarize_power_cells(cells, kappas, registered=registered)
