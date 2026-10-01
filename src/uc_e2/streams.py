"""E2 Annex A: random streams, and the guard that keeps development runs off the registered coordinates.

`SeedSequence([master_seed, stream_id, cell, replicate])` with PCG64, all coordinates non-negative integers
(H1 section 8, E2 Annex A). The registered plan is master seed 1927 with the ids 5200-5231 of Annex A and, for
the AT-12 prerequisite, uc_core.linalg.at12's own stream 2012. A development run uses another seed and stream
ids from 9000 upwards: each registered id of Annex A is mapped by the fixed offset DEVELOPMENT_OFFSET (5200 ->
9200, ..., 5231 -> 9231) and the AT-12 stream 2012 to 9012. A generator for the registered seed or a registered
id is built only with the caller's gate flag (`allow_registered=True`).
"""
from __future__ import annotations

import numpy as np

from uc_core.constants import MASTER_SEED
from uc_ext import common as c

from .constants import AT12_STREAM, STREAM_IDS

DEVELOPMENT_SEED = 20260930
DEVELOPMENT_FLOOR = 9000
DEVELOPMENT_OFFSET = 4000                              # registered Annex A id + 4000 = development id
DEVELOPMENT_AT12_STREAM = 9012                         # development counterpart of AT-12's stream 2012
REGISTERED_IDS_TO_AVOID = (
    *range(100, 106), 200, 201, 300, 301, 400, 401, 1001, 1013, 2008, 2012, *range(5100, 5432))
REGISTERED_STREAM_IDS = dict(STREAM_IDS)
DEVELOPMENT_STREAM_IDS = {name: stream + DEVELOPMENT_OFFSET for name, stream in STREAM_IDS.items()}


class RegisteredRunRefused(c.RegisteredRunRefused):
    """A registered coordinate was requested outside a gated registered run, or a development run used one."""


def check_seed(master_seed, allow_registered=False) -> int:
    """The master seed as an integer; the registered seed 1927 only with the caller's explicit gate flag."""
    if isinstance(master_seed, (bool, np.bool_)) or not isinstance(master_seed, (int, np.integer)) or master_seed < 0:
        raise ValueError("master_seed must be a nonnegative integer")
    if int(master_seed) == MASTER_SEED and allow_registered is not True:
        raise RegisteredRunRefused("Master seed 1927 is the registered seed; pass allow_registered=True only after "
                                   "the public registration, the tag and the X.3 record have been verified")
    return int(master_seed)


def is_registered(master_seed) -> bool:
    return int(master_seed) == MASTER_SEED


def stream_ids(master_seed) -> dict:
    """Annex A's ids under the registered seed; their development counterparts (id + 4000) under any other."""
    return dict(REGISTERED_STREAM_IDS if is_registered(master_seed) else DEVELOPMENT_STREAM_IDS)


def at12_stream(master_seed) -> int:
    return AT12_STREAM if is_registered(master_seed) else DEVELOPMENT_AT12_STREAM


def stream_rng(master_seed, stream_id, cell=0, replicate=0, *, allow_registered=False) -> np.random.Generator:
    """The generator of one stream coordinate.

    The registered seed or a registered stream id needs the caller's gate flag, and the registered seed is used
    only with registered ids; a development seed is used only with ids from 9000 upwards.
    """
    for value in (master_seed, stream_id, cell, replicate):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 0:
            raise ValueError("Seed coordinates must be nonnegative integers")
    registered_id = int(stream_id) in REGISTERED_IDS_TO_AVOID
    if is_registered(master_seed) or registered_id:
        if allow_registered is not True:
            raise RegisteredRunRefused("A generator for the registered seed or a registered stream id is built only "
                                       "inside a gated registered run: pass allow_registered=True after the public "
                                       "registration, the tag and the X.3 record have been verified")
        if not (is_registered(master_seed) and registered_id):
            raise RegisteredRunRefused("The registered seed is used only with registered stream ids, and a "
                                       "registered stream id only with the registered seed")
    elif int(stream_id) < DEVELOPMENT_FLOOR:
        raise RegisteredRunRefused("A development run uses stream ids from 9000 upwards")
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(
        [int(master_seed), int(stream_id), int(cell), int(replicate)])))
