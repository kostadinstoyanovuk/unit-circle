"""Analysis code for the registered E4 extension (prereg/E4.md, OSF dpxqf): real-time vintages of UK GDP.

Sections 4 to 11 of the registered addendum as functions that read no file and no data: the availability and
level tables of a vintage-by-quarter workbook (table), the vintage series and episode selection (vintage), the
rolling AR(2) statistic and the fixed-date surrogate comparison (procedure), the assembled analysis
(analysis), the descriptive tables (descriptive), the random streams of Annex A (streams) and the section 11
synthetic design (synthetic). The package imports uc_core and uc_ext and modifies neither. Importing it reads
no file and no data; every random number comes from a Generator built from an explicit
SeedSequence([seed, stream, cell, replicate]).
"""
__version__ = "1.0.0"
