"""Frozen synthetic design helpers; importing this module runs no experiment."""
import math
import numpy as np
from .constants import POWER_KAPPAS, POWER_ONSETS
from .surrogate import _generator


def h1_design_series(rng, *, kappa=1.):
    """One length259 Gaussian path. Caller supplies a generation-only stream."""
    _generator(rng)
    if kappa not in POWER_KAPPAS:
        raise ValueError("Use a prespecified kappa")
    variance = 1225/88
    covariance = variance/3
    z = rng.standard_normal(2)
    values = np.empty(259)
    values[0] = 2.5 + math.sqrt(variance)*z[0]
    values[1] = 2.5 + covariance/math.sqrt(variance)*z[0] + math.sqrt(variance-covariance**2/variance)*z[1]
    noise = rng.normal(0, 3.5, size=257)
    active = np.zeros(259, dtype=bool)
    for onset in POWER_ONSETS:
        active[onset-8:onset] = True
    for t in range(2, 259):
        scale = kappa if active[t] else 1.
        a, b = .3*scale, .1*scale**2
        c = 2.5*(1-a-b) if scale != 1. else 1.5
        values[t] = c + a*values[t-1] + b*values[t-2] + noise[t-2]
    return values


def wilson_interval(successes, total):
    """95% Monte Carlo proportion interval, not an economic-effect interval."""
    if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, np.integer)) for v in (successes,total)):
        raise ValueError("Counts must be integers")
    if total < 1 or not 0 <= successes <= total:
        raise ValueError("Invalid binomial counts")
    z = 1.959963984540054
    q, d = successes/total, 1+z*z/total
    center = (q+z*z/(2*total))/d
    half = z*math.sqrt(q*(1-q)/total+z*z/(4*total**2))/d
    return max(0., center-half), min(1., center+half)


def summarize_power(p_values, statistics):
    """Summarize four completed/requested200 cells; None means invalid/unfinished.

    No Monte Carlo fitting or smoothing. Synthetic tests of this arithmetic
    supply constructed tables; those tables are never scientific power evidence.
    """
    if len(p_values) != 4 or len(statistics) != 4 or any(len(row) != 200 for row in [*p_values,*statistics]):
        raise ValueError("Expected four cells of exactly200 requested outcomes")
    cells = []
    for kappa, ps, ss in zip(POWER_KAPPAS, p_values, statistics):
        for p in ps:
            if p is not None and (not math.isfinite(p) or not 0 <= p <= 1):
                raise ValueError("p-values must be finite in[0,1] or None")
        for value in ss:
            if value is not None and not math.isfinite(value):
                raise ValueError("Statistics must be finite or None")
        valid = [(p, value) for p, value in zip(ps, ss) if p is not None and value is not None]
        rejected = sum(p <= .05 for p, _ in valid)
        missing = 200-len(valid)
        rate = rejected/200 if missing == 0 else None
        cells.append({"kappa":kappa, "valid":len(valid), "invalid_or_unfinished":missing,
                      "rejected":rejected, "accounting_bounds":(rejected/200,(rejected+missing)/200),
                      "valid_only_rate":rejected/len(valid) if valid else None,
                      "rate":rate, "mean_S":float(np.mean(ss)) if missing == 0 else None,
                      "rate_se":math.sqrt(rate*(1-rate)/200) if rate is not None else None,
                      "rate_wilson":wilson_interval(rejected,200) if missing == 0 else None,
                      "mean_S_se":float(np.std(ss,ddof=1)/math.sqrt(200)) if missing == 0 else None})
    result = {"cells":cells, "D80":None, "kappa80":None, "crossing":None,
              "adjacent_comparisons":[], "decrease_flags":[], "AT16_passed":False}
    if any(c["rate"] is None for c in cells):
        return result
    for previous, current in zip(cells, cells[1:]):
        se = math.hypot(previous["rate_se"], current["rate_se"])
        difference = current["rate"]-previous["rate"]
        flag = difference < -1.96*se
        result["adjacent_comparisons"].append({"left_kappa":previous["kappa"],
                                             "right_kappa":current["kappa"],
                                             "difference":difference, "standard_error":se,
                                             "decrease_flag":flag})
        result["decrease_flags"].append(flag)
    result["AT16_passed"] = not any(result["decrease_flags"])
    for index, cell in enumerate(cells):
        if cell["rate"] < .8:
            continue
        if index == 0:
            result.update(D80=cell["mean_S"], kappa80=1., crossing={"left":0,"right":0,"weight":0.})
        else:
            left = cells[index-1]
            weight = (.8-left["rate"])/(cell["rate"]-left["rate"])
            result.update(D80=left["mean_S"]+weight*(cell["mean_S"]-left["mean_S"]),
                          kappa80=left["kappa"]+weight*(cell["kappa"]-left["kappa"]),
                          crossing={"left":index-1,"right":index,"weight":weight})
        break
    return result
