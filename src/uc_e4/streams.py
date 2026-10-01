"""E4 Annex A: random streams as arguments, and the guard that keeps development runs off the registered ones.

`SeedSequence([master_seed, stream_id, cell, replicate])` with PCG64, all coordinates non-negative
integers (H1 section 8, E4 Annex A). The registered plan is master seed 1927 with the ids below; a
development run uses another seed and stream ids from 9000 upwards. A generator for a registered seed or id is
built only with the caller's gate flag (`allow_registered=True`), here and in `check_run`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from uc_core.constants import MASTER_SEED

DEVELOPMENT_SEED = 20260930
DEVELOPMENT_FLOOR = 9000
REGISTERED_IDS_TO_AVOID = (
    *range(100, 106), 200, 201, 300, 301, 400, 401, 1001, 1013, 2008, 2012, *range(5100, 5432))


class RegisteredRunRefused(RuntimeError):
    """A registered coordinate was requested outside a gated registered run, or a development run used one."""


@dataclass(frozen=True)
class Streams:
    """Stream ids of Annex A (stream 5403 is deliberately unused; the field is absent on purpose)."""
    primary: int          # 5400: per-vintage surrogates (primary, Kendall, lag-one), cell = j, replicate 0
    window32: int         # 5401
    window48: int         # 5402
    wild: int             # 5404
    interval: int         # 5405: cell 0, replicate 0
    size_generation: int  # 5420: cell 0, replicate i
    size_null: int        # 5421: cell j (synthetic vintage), replicate i
    power_generation: int  # 5430: cell = kappa index, replicate i
    power_null: int       # 5431: cell = 10 * kappa index + j, replicate i

    def ids(self):
        return tuple(getattr(self, name) for name in self.__dataclass_fields__)


REGISTERED_STREAMS = Streams(5400, 5401, 5402, 5404, 5405, 5420, 5421, 5430, 5431)
DEVELOPMENT_STREAMS = Streams(9400, 9401, 9402, 9404, 9405, 9420, 9421, 9430, 9431)


def check_run(master_seed, streams: Streams, allow_registered=False):
    """Registered coordinates only with the caller's explicit gate flag; development runs never touch them.

    The flag says that the caller has verified the gate itself (public registration, tag, X.3 record); this
    package cannot verify it. Returns True for a registered run, False for a development run.
    """
    if isinstance(master_seed, (bool, np.bool_)) or not isinstance(master_seed, (int, np.integer)) or master_seed < 0:
        raise ValueError("master_seed must be a non-negative integer")
    ids = streams.ids()
    if any(isinstance(i, (bool, np.bool_)) or not isinstance(i, (int, np.integer)) or i < 0 for i in ids):
        raise ValueError("stream ids must be non-negative integers")
    if int(master_seed) == MASTER_SEED:
        if allow_registered is not True:
            raise RegisteredRunRefused("Master seed 1927 is registered; pass allow_registered=True only after the "
                                       "public registration, the tag and the X.3 record have been verified")
        if streams != REGISTERED_STREAMS:
            raise RegisteredRunRefused("The registered seed is used only with the registered stream ids of Annex A")
        return True
    if any(i < DEVELOPMENT_FLOOR or i in REGISTERED_IDS_TO_AVOID for i in ids):
        raise RegisteredRunRefused("A development run uses stream ids from 9000 upwards, never a registered id")
    return False


def stream_rng(master_seed, stream_id, cell=0, replicate=0, *, allow_registered=False) -> np.random.Generator:
    """The generator of one stream coordinate. A registered seed or stream id needs the caller's gate flag."""
    for value in (master_seed, stream_id, cell, replicate):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 0:
            raise ValueError("Seed coordinates must be non-negative integers")
    if allow_registered is not True and (int(master_seed) == MASTER_SEED or int(stream_id) in REGISTERED_IDS_TO_AVOID):
        raise RegisteredRunRefused("A generator for the registered seed or a registered stream id is built only "
                                   "inside a gated registered run: pass allow_registered=True after the public "
                                   "registration, the tag and the X.3 record have been verified")
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(
        [int(master_seed), int(stream_id), int(cell), int(replicate)])))
