"""Foundations checks AT-8, AT-11, AT-12 and the local-level model (D-019).

Writes audit/foundations_verification.json. No network access and no UK data.
"""
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time
import warnings

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uc_core import linalg, schur, statespace  # noqa: E402
from uc_core.ar import fit_ols  # noqa: E402

OUTPUT = ROOT / 'audit/foundations_verification.json'
DURBIN_KOOPMAN = dict(irregular=15099.0, level=1469.1)


def main():
    import statsmodels.api as sm
    started = time.perf_counter()
    sunspots = sm.datasets.sunspots.load_pandas().data
    early = sunspots.SUNACTIVITY[(sunspots.YEAR >= 1749) & (sunspots.YEAR <= 1924)].to_numpy()
    at11 = statespace.regression_at11(early)
    residual_variance = float(np.sum(np.square(fit_ols(early).residuals)) / (len(early) - 2 - 3))
    at11_sensitivity = statespace.regression_at11(early, observation_variance=residual_variance)

    nile = sm.datasets.nile.load_pandas().data.volume.to_numpy(dtype=float)
    local = statespace.local_level_mle(nile)
    relative = {key: local[key] / DURBIN_KOOPMAN[key] - 1 for key in DURBIN_KOOPMAN}
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        uc = sm.tsa.UnobservedComponents(nile, 'local level').fit(disp=False)
    statsmodels_estimate = dict(zip(('irregular', 'level'), map(float, uc.params)))

    at8 = schur.at8()
    at12 = linalg.at12()
    record = dict(
        record_type='Foundations checks AT-8, AT-11, AT-12 and local-level model',
        decision='D-019',
        AT8=at8,
        AT11=dict(test=at11, sensitivity_residual_variance=at11_sensitivity),
        local_level=dict(series='statsmodels Nile volume, 1871-1970', estimate=local,
                         durbin_koopman=DURBIN_KOOPMAN, relative_difference=relative,
                         statsmodels_unobserved_components=statsmodels_estimate,
                         passed=all(abs(value) <= 0.005 for value in relative.values()) and local['converged']),
        AT12=at12,
        passed=dict(AT8=at8['passed'], AT11=at11['passed'],
                    local_level=all(abs(value) <= 0.005 for value in relative.values()) and local['converged'],
                    AT12=at12['passed']),
        environment=dict(python=platform.python_version(), numpy=importlib.metadata.version('numpy'),
                         scipy=importlib.metadata.version('scipy'),
                         statsmodels=importlib.metadata.version('statsmodels')),
        scope='Numerical foundations checks on synthetic, sunspot and Nile data; no UK observation.',
    )
    OUTPUT.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(passed=record['passed'], seconds=round(time.perf_counter() - started, 1)), indent=2))


if __name__ == '__main__':
    main()
