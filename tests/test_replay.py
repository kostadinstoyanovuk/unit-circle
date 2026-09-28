"""The independent replay agrees with the frozen implementation, and it notices a changed record."""
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import zlib

import numpy as np
import pytest

from uc_core import surrogate as s
from uc_core import validation_runner as runner
from uc_core.constants import POWER_ONSETS
from uc_core.validation_design import h1_design_series
from uc_core.validation_store import ReplicateStore, canonical, digest
from uc_verify import replay

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('review_g2', ROOT / 'tools/review_g2.py')
review_g2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review_g2)


def test_the_replay_shares_no_code_with_the_implementation_it_checks():
    source = (ROOT / 'src/uc_verify/replay.py').read_text(encoding='utf-8').splitlines()
    imports = [line for line in source if line.startswith(('import ', 'from '))]
    assert imports and not any('uc_core' in line for line in imports)


@pytest.mark.parametrize('kappa', (1.0, 1.2, 1.4, 1.6))
def test_generation_matches_the_frozen_design(kappa):
    frozen = h1_design_series(np.random.Generator(np.random.PCG64(2026)), kappa=kappa)
    ours = replay.design_series(np.random.Generator(np.random.PCG64(2026)), kappa, POWER_ONSETS)
    assert np.max(np.abs(frozen - ours)) < 1e-9


def test_modulus_cases():
    assert replay.modulus(0., 0.) == 0.
    assert replay.modulus(1.5, -0.56) == pytest.approx(0.8)
    assert replay.modulus(1.336, -0.65) == pytest.approx(0.65 ** .5)
    assert replay.modulus(-0.2, 0.35) == pytest.approx(0.7)


def test_episodes_follow_the_registered_rule():
    g = np.ones(40)
    g[[3, 4, 12, 13, 14, 30, 31, 35]] = -1
    # 12 - 4 = 8 merges; 30 - 14 = 16 starts a new episode; the single negative at 35 is not a run.
    assert replay.episodes(g) == [(3, 14), (30, 31)]


def test_statistic_matches_the_frozen_code():
    rng = np.random.default_rng(5)
    for _ in range(25):
        x = rng.normal(1, 3, 259)
        frozen = s._statistic(x, window=40, lookback=8, merge=8)
        S, eligible, _ = replay.statistic(replay.rolling_modulus(x), [e[0] for e in replay.episodes(x)])
        assert (frozen.mean_change is None) == (S is None)
        if S is not None:
            assert abs(frozen.mean_change - S) < 1e-10 and list(frozen.eligible_onsets) == eligible


def test_d80_first_raw_crossing_and_flags():
    cells = [dict(rate=r, mean_S=m) for r, m in ((.1, .01), (.5, .03), (.9, .05), (1., .07))]
    power = replay.power_summary(cells)
    assert power['crossing']['cells'] == [1, 2] and power['kappa80'] == pytest.approx(1.35)
    assert power['D80'] == pytest.approx(.045) and power['AT16_passed']
    first = replay.power_summary([dict(rate=r, mean_S=.02) for r in (.85, .9, .95, 1.)])
    assert first['kappa80'] == 1. and first['D80'] == .02
    falling = replay.power_summary([dict(rate=r, mean_S=.02) for r in (.5, .3, .6, .7)])
    assert falling['decrease_flags'] == [1] and not falling['AT16_passed'] and falling['D80'] is None


@pytest.fixture
def development_store(tmp_path):
    manifest = dict(plan=runner.make_plan('development'), identity={'fixture': 'constructed'},
                    registration_receipt_sha256=None)
    path = tmp_path / 'development.sqlite'
    with ReplicateStore(path, manifest, create=True) as store:
        runner.run_batch(store, max_new=18)
        summary = runner.summarize(store)
    (tmp_path / 'summary.json').write_bytes(canonical(summary) + b'\n')
    return path, tmp_path / 'summary.json'


def test_replay_agrees_with_every_development_record(development_store):
    database, summary = development_store
    result = review_g2.review(database, summary, log=lambda _: None)
    replayed = result['independent_replay']
    assert replayed['agrees'], replayed['problems'] + replayed['summary_differences']
    assert replayed['statistics']['records_checked'] == 18
    assert result['G2'] == 'not passed'  # development mode can never pass G2


def _rewrite(database, choose, change):
    """Change the first record that `choose` accepts, keeping every checksum and journal entry valid."""
    with sqlite3.connect(database) as db:
        for cell, replicate, packed in db.execute('SELECT cell, replicate, payload FROM records ORDER BY cell, replicate'):
            record = json.loads(zlib.decompress(packed))
            if choose(record):
                break
        else:
            raise AssertionError('no suitable record')
        change(record)
        raw = canonical(record)
        db.execute('UPDATE records SET payload=?, sha256=? WHERE cell=? AND replicate=?',
                   (zlib.compress(raw), digest(raw), cell, replicate))
        db.execute("UPDATE events SET sha256=? WHERE kind='record_committed' AND cell=? AND replicate=?",
                   (digest(raw), cell, replicate))


def _has_statistic(record):
    attempts = (record.get('comparison') or {}).get('attempts') or []
    return bool(attempts) and attempts[0].get('statistic') is not None


def test_replay_notices_a_consistently_rewritten_record(development_store, tmp_path):
    database, summary = development_store
    changed = tmp_path / 'changed.sqlite'
    shutil.copyfile(database, changed)
    _rewrite(changed, lambda r: r['cell'] == 'white_noise_n30' and r['status'] == 'ok',
             lambda r: r.update(complex_pair=not r['complex_pair']))
    _rewrite(changed, _has_statistic,
             lambda r: r['comparison']['attempts'][0].update(statistic=r['comparison']['attempts'][0]['statistic'] + 1e-3))
    replayed = review_g2.review(changed, summary, log=lambda _: None)['independent_replay']
    assert not replayed['agrees']
    assert replayed['integrity']['journal_consistent']  # the rewrite kept every checksum valid
    assert replayed['statistics']['white_noise_classification_mismatches'] == 1
    assert replayed['statistics']['surrogate_statistic_max_difference'] > 1e-4


def test_attempt_outcomes_are_compared_not_their_labels(development_store):
    """uc_core stores 'no_eligible_episode' where the replay says 'no_episode'; a real difference still counts."""
    database, summary = development_store
    work = review_g2.Review(database, json.loads(summary.read_bytes()))
    stored = dict(S=.5, observed=dict(eligible_onsets=[60]), p_value=.5,
                  comparison=dict(null_model=None, exceedances=0, attempts=[
                      dict(number=0, status='no_eligible_episode', statistic=None, eligible_onsets=[]),
                      dict(number=1, status='retained', statistic=.1, eligible_onsets=[60])]))
    ours = dict(S=.5, eligible_onsets=[60], stable=True, null=None, p_value=.5, exceedances=0, attempts=[
        dict(number=0, status='no_episode', statistic=None, eligible_onsets=[]),
        dict(number=1, status='retained', statistic=.1, eligible_onsets=[60])])
    work.compare('fixture', stored, ours)
    assert work.problems == [] and work.stats['surrogate_status_mismatches'] == 0
    ours['attempts'][0].update(status='retained', statistic=.2, eligible_onsets=[60])
    work.compare('fixture', stored, ours)
    assert work.stats['surrogate_status_mismatches'] == 1
    stored['comparison']['attempts'][0]['status'] = 'failed'
    ours['attempts'][0].update(status='no_episode', statistic=None, eligible_onsets=[])
    work.compare('fixture', stored, ours)
    assert work.stats['surrogate_status_mismatches'] == 2


def test_replay_notices_a_changed_summary(development_store, tmp_path):
    database, summary = development_store
    frozen = json.loads(summary.read_bytes())
    frozen['cells']['size']['positive'] += 1
    changed = tmp_path / 'changed-summary.json'
    changed.write_bytes(canonical(frozen))
    replayed = review_g2.review(database, changed, log=lambda _: None)['independent_replay']
    assert any(text.startswith('size positive') for text in replayed['summary_differences'])
