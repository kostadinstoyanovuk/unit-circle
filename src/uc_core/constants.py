"""Protocol parameters and explicit stream allocation; no mutable global RNG."""
from types import MappingProxyType
import numpy as np

MASTER_SEED = 1927
SURROGATE_ATTEMPTS = 1000
EPISODE_RESAMPLES = 10000
ALPHA = .05
POWER_KAPPAS = (1., 1.2, 1.4, 1.6)
POWER_ONSETS = (49, 99, 149, 199, 249)  # Original one-based quarters 50,...,250.
STREAM_IDS = MappingProxyType({
    "primary": 100, "window32": 101, "window48": 102,
    "fixed": 103, "wild": 104, "interval": 105,
    "size_generation": 200, "size_null": 201,
    "power_generation": 300, "power_null": 301,
    "white_noise_n30": 400, "white_noise_n1000": 401,
})


def analysis_rng(name, *, cell=0, replicate=0):
    if name not in STREAM_IDS:
        raise ValueError("Unknown registered stream name")
    for value in (cell, replicate):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 0:
            raise ValueError("Stream coordinates must be nonnegative integers")
    return np.random.Generator(np.random.PCG64(
        np.random.SeedSequence([MASTER_SEED, STREAM_IDS[name], int(cell), int(replicate)])))
