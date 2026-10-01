"""Analysis code for the E2 extension (VAR(2) on output growth and the change in the unemployment rate).

Sections 4 to 11 and Annexes A and B of the E2 addendum as functions that read no file and no data: the
constants (constants), the sample, the variables and the onsets table (variables), the VAR(2) estimator and the
companion spectral radius (var), the statistic, the fitted null and the surrogate comparisons (procedure), the
single real run and its reporting quantities (analysis) and the section 11 synthetic design with the X.3
prerequisites (synthetic). The package imports uc_core and uc_ext and modifies neither. Every random number
comes from a Generator built from an explicit SeedSequence([seed, stream, cell, replicate]).
"""
__version__ = "1.0.0"
