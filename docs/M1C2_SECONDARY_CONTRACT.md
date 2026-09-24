# M1c.2a secondary-method contract

Fixed on 2026-09-24 before implementation or UK data access. Extends the M1c.1 contract without changing the primary analysis. All secondary results are reported; none selects or replaces the primary.

## Statistics

- Window sensitivities: repeat the complete primary procedure separately at W=32 and W=48. Each uses its own null draws and its own window-specific eligibility. Fixed-date and wild-sign sensitivity analyses use W=40 and the already specified rules. Each requests B=1,000 attempts in the eventual registered run.
- Lag-one comparator: within each of the same W=40 growth windows, subtract that window's mean. Calculate sum(v[1:]*v[:-1])/sum(v*v), using the complete centered window in the denominator and no n/(n-1) correction. This defines the otherwise ambiguous sample-autocorrelation convention. Negative correlations are valid. A zero denominator is a fit failure, not zero correlation. Form the same eight-quarter signed change and average over the same endogenous recession rule and eligibility; use its own upper-tail p-value.
- Trend: Kendall tau-b between ordered positions 0,...,15 and the 16 modulus values at onset-16,...,onset-1; average over episodes whose first required modulus exists. For W=40, the earliest zero-based eligible onset is 55. Ties in modulus use tau-b's denominator; use the statistic only, not SciPy's asymptotic p-value. A constant 16-value segment makes tau-b undefined: explicitly fail that statistic rather than substitute zero or remove the episode. No eligible episodes is a distinct not-estimable outcome.
- The primary residual surrogates supply the primary, trend and lag-one statistics. Use the identical generated paths and repeated endogenous onset detection. Retention is statistic-specific: in particular, trend cannot inherit the primary denominator. Each statistic counts attempted, retained, no-eligible and failed outcomes; any numerical/undefined-statistic failure invalidates that statistic's p-value. A failure unique to one statistic does not invalidate another computable statistic. Null-generation failures affect all three. No replacement draws.

The joint reporting wrapper extends failure isolation to observed statistics: retain a failed primary result and continue a computable comparator, without claiming a primary conclusion. A statistic with no usable observed value receives zero statistic attempts even when paths are generated for another statistic. Record total generated paths separately. If the shared full-sample null is unusable, preserve observed statistics and return a null-model failure with zero draws. An interval whose observed primary statistic failed is also failed, not an empty-episode interval. The lower-level M1c.1 csd_test still raises observed/null failures; the reporting wrapper records them explicitly. Independent sensitivity failures remain rows in the output rather than aborting the remaining table.

## Episode interval

Resample the m observed eligible primary episode changes with replacement, m indices per resample, for exactly 10,000 resamples. Average each resample. Report the 5th and 95th percentiles using NumPy's linear quantile method. This is a conditional diagnostic interval, with no equivalence or calibrated absence claim. Use an independent explicit generator; one integers(0,m,size=(B,m)) call defines draw ordering. Save the draws' means and before/after states.

With m=0 return no interval and consume no randomness. With m=1 return the degenerate interval and flag its single-episode status; this does not establish precision. Reject nonfinite or nonvector input, invalid counts, and implicit/global random generators. Do not remove observed episode changes based on their signs or size.

## Verification and limits

Compare lag-one values to hand calculations and the established sample-ACF formula; compare trend to independent concordant/discordant pair counts including ties. Check warm-up, exact endpoints, first eligibility, negative correlations and failures. Verify interval quantile and draw ordering by reconstructing resamples with a separate generator. Exercise the joint surrogate route on a small fixed synthetic fixture, preserving primary outputs against the M1c.1 reference using identical generator states. These are engineering checks, not AT-15/AT-16 calibration runs.
