"""Diagnose the single G2 replay discrepancy: size cell, replicate 183, surrogate draw 256.

Read-only: opens the store with mode=ro and writes nothing into the repository or the run folder
except this script's own printed output. Uses the frozen uc_core modules (byte-identical to
da548d9 for ar.py, rolling.py, recession.py and surrogate.py) and the independent replay module.
"""
import json
import sqlite3
import sys
import zlib
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(r'C:\Users\user\Desktop\Unit Circle Programme\unit-circle')
RUN = Path(r'C:\Users\user\Desktop\Unit Circle Programme\Programme Records\M2-registered-validation')
sys.path.insert(0, str(REPO / 'src'))

import numpy as np  # noqa: E402
from uc_verify import replay  # noqa: E402
from uc_core import surrogate as frozen  # noqa: E402
from uc_core.recession import episodes as frozen_episodes  # noqa: E402

CELL, REPLICATE, DRAW = 'size', 183, 256

db = sqlite3.connect(f"file:{(RUN / 'registered.sqlite').as_posix()}?mode=ro", uri=True)
plan = json.loads(db.execute('SELECT payload FROM manifest WHERE id=1').fetchone()[0])['plan']
cell = next(c for c in plan['cells'] if c['name'] == CELL)
packed, = db.execute('SELECT payload FROM records WHERE cell=? AND replicate=?', (CELL, REPLICATE)).fetchone()
record = json.loads(zlib.decompress(packed))
comparison = record['comparison']
attempts = comparison['attempts']
B = plan['surrogate_attempts']
print('record status', record['status'], '| S', record['S'], '| p', record['p_value'],
      '| K', comparison['exceedances'], '| retained', comparison['retained'], '| no_episode', comparison['no_episode'])
print('stored status counts', dict(Counter(a['status'] for a in attempts)))
stored = attempts[DRAW]
print('stored draw', DRAW, json.dumps({k: stored[k] for k in ('number', 'status', 'statistic', 'eligible_onsets')}))

x = np.asarray(record['input'], float)
ours = replay.comparison(x, replay.generator(cell['surrogate_stream'], cell['cell_index'], REPLICATE, plan['master_seed']),
                         fixed_onsets=None, B=B)
mine = ours['attempts'][DRAW]
print('replay status counts', dict(Counter(a['status'] for a in ours['attempts'])))
print('replay draw', DRAW, json.dumps({k: mine[k] for k in ('number', 'status', 'statistic', 'eligible_onsets')}))
print('replay p', ours['p_value'], '| K', ours['exceedances'], '| retained', ours['retained'])

# Other draws: any further difference in status (after mapping the two status vocabularies) or onsets?
mapping = {'retained': 'retained', 'no_eligible_episode': 'no_episode'}
other = [a['number'] for a, b in zip(attempts, ours['attempts'])
         if mapping.get(a['status'], a['status']) != b['status']
         or (b['statistic'] is not None and a['eligible_onsets'] != b['eligible_onsets'])]
print('draws differing after vocabulary mapping', other)

# Regenerate draw DRAW's path with both implementations and compare signs near zero.
null_frozen = frozen.prepare_null(x)
rng = replay.generator(cell['surrogate_stream'], cell['cell_index'], REPLICATE, plan['master_seed'])
for _ in range(DRAW):
    frozen.draw_surrogate(null_frozen, rng)
path_frozen = frozen.draw_surrogate(null_frozen, rng)
null_replay = replay.fitted_null(x)
paths = replay.surrogates(x, null_replay, replay.generator(cell['surrogate_stream'], cell['cell_index'],
                                                           REPLICATE, plan['master_seed']), B)
path_replay = paths[DRAW]
print('max |path difference|', float(np.max(np.abs(path_frozen - path_replay))))
flips = np.flatnonzero((path_frozen < 0) != (path_replay < 0))
print('sign differences at positions', flips.tolist(),
      [(float(path_frozen[i]), float(path_replay[i])) for i in flips])
near = np.argsort(np.abs(path_frozen))[:5]
print('five values closest to zero (position, frozen, replay)',
      [(int(i), float(path_frozen[i]), float(path_replay[i])) for i in near])
print('frozen onsets', [e.onset for e in frozen_episodes(path_frozen, merge=8)])
print('replay onsets', [e[0] for e in replay.episodes(path_replay)])
