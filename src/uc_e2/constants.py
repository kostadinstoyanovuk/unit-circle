"""E2 constants: sections 4 to 11 and Annex A of the addendum, and the named readings R1, R2 and R9.

Importing this module reads no file and no data.
"""
from __future__ import annotations

import re

from uc_core.constants import POWER_KAPPAS


# Sections 4-5: sample and variables.
FIRST_LEVEL_QUARTER, LAST_QUARTER = (1971, 1), (2019, 4)
N_LEVELS = 196                                       # 1971Q1-2019Q4, both series
N_OBS = N_LEVELS - 1                                 # 195 vectors X[t], 1971Q2-2019Q4
K = 2                                                # (g, du)
H1_OFFSET = 64                                       # E2 position p is H1 growth position p + 64 (1955Q2 + 64 = 1971Q2)
QUARTER_LABEL = re.compile(r"^(\d{4}) Q([1-4])$")
# Sections 6-10.
WINDOW = 40
SENSITIVITY_WINDOWS = (32, 48)
LOOKBACK = 8
MINIMUM_RUN = 2
MERGE = 8
TREND_SPAN = 16
SURROGATE_ATTEMPTS = 1000
EPISODE_RESAMPLES = 10000
# Annex A.
STREAM_IDS = dict(primary=5200, window32=5201, window48=5202, fixed=5203, wild=5204, interval=5205,
                  size_generation=5220, size_null=5221, power_generation=5230, power_null=5231)
# Section 11 (X.3).
SERIES_PER_CELL = 200
SIZE_BOUNDS = (.02, .09)
KAPPAS = POWER_KAPPAS                                # (1.0, 1.2, 1.4, 1.6), as H1
DESIGN_A1 = ((.3, 0.), (0., .3))
DESIGN_A2 = ((.1, 0.), (0., .1))
DESIGN_MEAN = (2.5, 0.)
DESIGN_INTERCEPT = (1.5, 0.)                          # c = (I - A1 - A2) mu, as printed (H1's literal 1.5)
SIGNAL_LENGTH = 8                                     # planted positions r-8, ..., r-1
DESIGN_CORRELATION = -.5                              # E2-4
DESIGN_SIGMA = ((3.5 ** 2, DESIGN_CORRELATION * 3.5 * 1.), (DESIGN_CORRELATION * 3.5 * 1., 1. ** 2))
DESIGN_SIGMA_CHOLESKY = ((3.5, 0.), (-.5, 0.8660254037844386))      # as printed in section 11
DESIGN_TIME_CORRELATION = ((1., 1 / 3), (1 / 3, 1.))                   # stationary lag-one structure, H1's AR(2)
DESIGN_SCALE = 100 / 88                                                # H1's v = 3.5^2 * 100/88

# R1. The power check plants its signal at the section 7 W = 40 eligible onset positions, which exist only
# once the addendum's table is completed from the H1-registered file (E2-3). They are not code: registered
# runs read them from the record ONSETS_RECORD (written at X.1 by tools/e2_onsets.py, by rule, from the
# H1-registered file), so no uc_ext file changes after E2's registration. Without that record every
# registered E2 check refuses to start. Development runs use a fixed coverage fixture (one-based quarters
# 50, 100 and 150, the alternative design of E2-3 (b)) unless onsets are supplied; it is not derived from data.
ONSETS_RECORD = "audit/E2_ONSETS.json"
DEVELOPMENT_POWER_ONSETS = (49, 99, 149)
MINIMUM_ONSET_GAP = 10                              # section 11: distinct episode onsets are >= 10 apart

# R2. X.3 prerequisites (Annex B): AT-12 through spectral_radius (AT-12's own draws and tolerances) and the
# reduction test (the VAR code with k = 1 reproduces H1's rolling M(t) to 1e-10) on one synthetic H1-design
# series drawn from stream 5220, cell 1, replicate 0 (a cell the size check does not use), W = 32, 40, 48.
PREREQUISITE_PARTS = ("at12", "reduction")
PREREQUISITE_FIXTURE = dict(stream="size_generation", cell=1, replicate=0)
AT12_STREAM = 2012                                  # uc_core.linalg.at12's own stream
AT12_DRAWS = dict(registered=100_000, development=2_000)
REDUCTION_TOL = 1e-10

# R9. Annex B retains "fitted coefficient matrices per window and the null, the 193 x 2 residual matrix, and
# each surrogate's status and S_b". Every X.3 record keeps the null (with its residual matrix) and every
# attempt's status and S_b, as H1's X.3 records do, and also the W = 40 window fits of its base series.
X3_RETAIN_WINDOW_FITS = True
