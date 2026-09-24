# M1b: rolling and episode conventions

All positional indices below are zero-based. Date labels are preserved separately, so position 48 means the 49th observation.

## Rolling AR(2)

`rolling_ar2` fits one complete within-window model ending at each t. With W=40, the first output is at t=39, using observations 0..39 and 38 regression rows. Its first two observations are only lags. A later fit uses exactly t-W+1..t. Both full-sample and prefix calls must yield the same earlier outputs.

The reference implementation loops over independent stable least-squares solves. It is deliberately easy to check. This is not yet the accelerated simulation engine: future vectorization must reproduce its results, including rank failures and endpoint conventions.

`max_modulus` returns a pandas Series with the input Series index (or a RangeIndex for arrays). The first W-1 rows are NaN with explicit warm-up status in the full table. A sample shorter than W yields only warm-up. All non-finite inputs, nonidentifiable windows, duplicate/reversed indices or missing PeriodIndex periods raise; none is imputed or silently dropped. Generic numeric/datetime indices must be chronologically ordered; the ingestion layer must additionally verify the intended calendar frequency. An unstable fitted model is retained.

## Recessions

`episodes` identifies runs of at least two strictly negative values by default. Zero or positive growth interrupts a run. The last two observations can form a qualifying terminal run. A terminal singleton does not qualify.

End indices are inclusive. If new_onset - previous_qualifying_run_end <= 8, merge and retain the episode's FIRST onset; update its end to the latest qualifying run's end. This supports chained merging. Isolated negative observations cannot reset the merging clock. The retained `runs` tuple makes merging inspectable.

Examples: runs [48,49] and [57,58] merge (gap 8); [48,49] and [58,59] do not (gap 9). Adding [66,67] to the first example extends its existing episode because 66-58=8. Merging is retrospective episode bookkeeping, not a real-time recession forecast.

## Pre-onset statistic

With lookback=8, Delta at onset t is M[t-1]-M[t-9]. The onset quarter is excluded. Under W=40, t=48 is the first eligible onset: earlier window 0..39 and later window 8..47. t=47 is ineligible because M[38] is warm-up. If a later qualifying run merges into an ineligible first onset, the entire episode retains that first onset and remains ineligible.

`pre_onset_changes` accepts unique, increasing integer onset positions inside the observed series. Moduli must be nonnegative and finite after a contiguous leading warm-up prefix. An internal missing value is an error, not grounds to selectively omit a recession. It reports eligible and ineligible onsets separately, preserves signed changes, and averages over eligible episodes. With no eligible episode its mean is `None`, not zero. It does not calculate a p-value or infer a scientific conclusion.

## Evidence and remaining scope

Independent hand-checkable fixtures cover merge boundaries, chain merging, zeros/singletons, terminal runs, first eligibility, onset-quarter exclusion and signed averaging. Causality is tested both by a prefix fit and by perturbing future observations. The end-to-end demonstration uses explicitly synthetic data with planted negative runs.

Surrogates, bootstrap inference, synthetic size/power studies, metadata ingestion and the preregistration remain M1c/M2. No UK observations or registered C3 cells were used. Original gates remain pending.
