"""Recovery and numerical wiring checks; never execute registered stream cells."""
from copy import deepcopy
from dataclasses import asdict
import sqlite3
import subprocess
import sys
import zlib

import numpy as np
import pytest

from uc_core import validation_runner as runner
from uc_core import surrogate as s
from uc_core.ar import fit_ols
from uc_core.constants import POWER_ONSETS
from uc_core.h1 import fixed_date_test
from uc_core.validation_store import ReplicateStore, IntegrityError, canonical, digest, read_manifest


@pytest.fixture
def manifest():
    return dict(plan=runner.make_plan('development'), identity={'fixture': 'constructed'},
                registration_receipt_sha256=None)


def fake_compute(plan, cell, replicate):
    """Constructed accounting records, never a calibration experiment."""
    return dict(cell=cell['name'], replicate=replicate, status='fit_failed', error='fixture')


def test_frozen_design_counts_coordinates_and_separate_development_namespace():
    plan = runner.make_plan('registered')
    assert [c['requested'] for c in plan['cells']] == [100000, 60000, 200, 200, 200, 200, 200]
    assert [c['generation_stream'] for c in plan['cells']] == [400, 401, 200, 300, 300, 300, 300]
    assert [c.get('surrogate_stream') for c in plan['cells']] == [None, None, 201, 301, 301, 301, 301]
    assert [c['cell_index'] for c in plan['cells']] == [0, 0, 0, 0, 1, 2, 3]
    assert plan['master_seed'] == 1927 and plan['surrogate_attempts'] == 1000
    assert runner.make_plan('development')['master_seed'] != 1927
    # No registered generator is constructed in this design inspection.


def test_white_noise_development_draw_and_fit_match_direct_reference():
    plan = runner.make_plan('development')
    cell = plan['cells'][0]
    actual = runner.compute_replicate(plan, cell, 0)
    reference = np.random.Generator(np.random.PCG64(np.random.SeedSequence(
        [20260926, 400, 0, 0])))
    before = deepcopy(reference.bit_generator.state)
    values = reference.standard_normal(30)
    fit = fit_ols(values)
    np.testing.assert_array_equal(actual['input'], values)
    assert actual['generation_rng_before'] == before
    assert actual['generation_rng_after'] == reference.bit_generator.state
    assert actual['coefficients'] == list(fit.coefficients)
    assert actual['discriminant'] == fit.diagnostics.discriminant
    assert actual['input_sha256'] == digest(values.astype('<f8').tobytes())
    assert actual['analysis_rng_after'] is None


@pytest.mark.parametrize('index', [2, 3, 5])
def test_development_size_power_wiring_matches_existing_methods(index):
    plan = runner.make_plan('development')
    cell = plan['cells'][index]
    actual = runner.compute_replicate(plan, cell, 0)
    reference = np.random.Generator(np.random.PCG64(np.random.SeedSequence(
        [20260926, cell['surrogate_stream'], cell['cell_index'], 0])))
    values = np.array(actual['input'])
    if cell['kind'] == 'size':
        expected = s.csd_test(values, B=8, rng=reference)
    else:
        expected = fixed_date_test(values, POWER_ONSETS, B=8, rng=reference)
        assert expected.observed.eligible_onsets == POWER_ONSETS
        assert all(a.eligible_onsets == POWER_ONSETS for a in expected.attempts)
    assert actual['comparison'] == runner.serial(asdict(expected))
    assert actual['analysis_rng_after'] == reference.bit_generator.state


def test_null_failure_preserves_statistic_and_no_draws(monkeypatch):
    plan = runner.make_plan('development')
    def fail(*args, **kwargs):
        raise s.NullModelError('constructed null failure')
    monkeypatch.setattr(s, 'prepare_null', fail)
    result = runner.compute_replicate(plan, plan['cells'][3], 0)
    assert result['status'] == 'null_model_failed' and result['S'] is not None
    assert result['surrogate_attempted'] == 0 and result['p_value'] is None
    assert result['analysis_rng_after'] == result['analysis_rng_before']


def test_fit_failure_is_saved_and_never_counted_as_real(monkeypatch):
    plan = runner.make_plan('development')
    def fail(values):
        raise ValueError('constructed unidentifiable fit')
    monkeypatch.setattr(runner, 'fit_ols', fail)
    result = runner.compute_replicate(plan, plan['cells'][0], 0)
    assert result['status'] == 'fit_failed' and result['input'] is not None
    assert 'complex_pair' not in result


def test_interrupt_resume_matches_uninterrupted_results_exactly(tmp_path, manifest):
    path = tmp_path/'resumed.sqlite'
    with ReplicateStore(path, manifest, create=True) as store:
        first = runner.run_batch(store, max_new=2)
        assert first['new_records'] == 2
        original = list(store.iter_records())
    with ReplicateStore(path, manifest) as store:
        assert runner.run_batch(store, max_new=2)['new_records'] == 2
        resumed = list(store.iter_records())
        assert resumed[:2] == original
    with ReplicateStore(tmp_path/'uninterrupted.sqlite', manifest, create=True) as other:
        runner.run_batch(other, max_new=4)
        assert list(other.iter_records()) == resumed


def test_keyboard_interrupt_keeps_committed_records_and_replays_only_unfinished(tmp_path, manifest):
    seen = []
    def interrupt(plan, cell, rep):
        seen.append(rep)
        if rep == 1:
            raise KeyboardInterrupt()
        return fake_compute(plan, cell, rep)
    path = tmp_path/'interrupted.sqlite'
    with ReplicateStore(path, manifest, create=True) as store:
        with pytest.raises(KeyboardInterrupt):
            runner.run_batch(store, max_new=4, compute=interrupt)
        assert store.verify() == 1
    with ReplicateStore(path, manifest) as store:
        called = []
        def resume(plan, cell, rep):
            called.append(rep)
            return fake_compute(plan, cell, rep)
        assert runner.run_batch(store, max_new=3, compute=resume)['new_records'] == 3
        assert called == [1, 2, 3] and seen == [0, 1]
        summary = runner.summarize(store)['cells']['white_noise_n30']
        assert summary['attempted'] == summary['failed'] == 4
        assert summary['valid'] == 0 and summary['rate'] is None
        assert summary['accounting_bounds'] == [0, 1]


def test_transaction_interruption_does_not_commit_or_count_record(tmp_path, manifest, monkeypatch):
    with ReplicateStore(tmp_path/'atomic.sqlite', manifest, create=True) as store:
        original = store.event
        def fail(kind, *args):
            if kind == 'record_committed':
                raise OSError('constructed disk write failure')
            return original(kind, *args)
        monkeypatch.setattr(store, 'event', fail)
        with pytest.raises(OSError):
            runner.run_batch(store, max_new=1, compute=fake_compute)
        assert store.verify() == 0
        monkeypatch.setattr(store, 'event', original)
        runner.run_batch(store, max_new=1, compute=fake_compute)
        assert store.verify() == 1


def test_hard_process_exit_rolls_back_uncommitted_record(tmp_path, manifest):
    path = tmp_path/'crash.sqlite'
    with ReplicateStore(path, manifest, create=True):
        pass
    script = '''import os, sqlite3, sys
db=sqlite3.connect(sys.argv[1], isolation_level=None)
db.execute('BEGIN IMMEDIATE')
db.execute("INSERT INTO records VALUES ('white_noise_n30',0,X'00','unfinished')")
os._exit(7)
'''
    proc = subprocess.run([sys.executable, '-c', script, str(path)])
    assert proc.returncode == 7
    with ReplicateStore(path, manifest) as store:
        assert store.verify() == 0
        runner.run_batch(store, max_new=1, compute=fake_compute)
        assert store.verify() == 1


@pytest.mark.parametrize('mutation', ['payload', 'deleted_record', 'deleted_event', 'duplicate_event', 'wrong_identity', 'null_event_hash'])
def test_corruption_or_missing_committed_record_stops_resume(tmp_path, manifest, mutation):
    path = tmp_path/'corrupt.sqlite'
    with ReplicateStore(path, manifest, create=True) as store:
        runner.run_batch(store, max_new=1, compute=fake_compute)
    with sqlite3.connect(path) as db:
        if mutation == 'payload':
            db.execute("UPDATE records SET payload=X'00'")
        elif mutation == 'deleted_record':
            db.execute('DELETE FROM records')
        elif mutation == 'deleted_event':
            db.execute("DELETE FROM events WHERE kind='record_committed'")
        elif mutation == 'duplicate_event':
            db.execute("INSERT INTO events(time_utc,kind,cell,replicate,sha256) SELECT time_utc,kind,cell,replicate,sha256 FROM events WHERE kind='record_committed'")
        elif mutation == 'null_event_hash':
            db.execute("UPDATE events SET sha256=NULL WHERE kind='record_committed'")
        else:
            value = fake_compute(manifest['plan'], manifest['plan']['cells'][0], 99)
            raw = canonical(value)
            db.execute('UPDATE records SET payload=?,sha256=?', (zlib.compress(raw), digest(raw)))
            db.execute("UPDATE events SET sha256=? WHERE kind='record_committed'", (digest(raw),))
    with pytest.raises(IntegrityError):
        ReplicateStore(path, manifest)


def test_changed_manifest_or_duplicate_creation_never_overwrites_prior_run(tmp_path, manifest):
    path = tmp_path/'saved.sqlite'
    with ReplicateStore(path, manifest, create=True):
        pass
    changed = deepcopy(manifest)
    changed['identity']['fixture'] = 'different-code-or-environment'
    with pytest.raises(IntegrityError, match='manifest'):
        ReplicateStore(path, changed)
    with pytest.raises(FileExistsError):
        ReplicateStore(path, manifest, create=True)
    assert read_manifest(path) == manifest
    with pytest.raises(FileNotFoundError):
        ReplicateStore(tmp_path/'missing.sqlite', manifest)
    assert not (tmp_path/'missing.sqlite').exists()


def test_duplicate_record_and_concurrent_writer_are_rejected(tmp_path, manifest):
    path = tmp_path/'exclusive.sqlite'
    with ReplicateStore(path, manifest, create=True) as first, ReplicateStore(path, manifest) as second:
        with first.transaction():
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                with second.transaction():
                    pytest.fail('Second writer acquired the lock')
            first.put('white_noise_n30', 0, fake_compute(manifest['plan'], manifest['plan']['cells'][0], 0))
        with pytest.raises(sqlite3.IntegrityError):
            with first.transaction():
                first.put('white_noise_n30', 0, fake_compute(manifest['plan'], manifest['plan']['cells'][0], 0))
        assert first.verify() == 1


def test_backup_is_verified_new_snapshot_and_resumable(tmp_path, manifest):
    path, copied = tmp_path/'active.sqlite', tmp_path/'backup.sqlite'
    with ReplicateStore(path, manifest, create=True) as store:
        runner.run_batch(store, max_new=1, compute=fake_compute)
        report = store.backup(copied)
        assert report['records'] == 1 and report['sha256'] == digest(copied.read_bytes())
        with pytest.raises(FileExistsError):
            store.backup(copied)
    with ReplicateStore(copied, manifest) as restored:
        runner.run_batch(restored, max_new=1, compute=fake_compute)
        assert restored.verify() == 2


def test_unfinished_and_failed_nominal_counts_remain_visible(tmp_path, manifest):
    with ReplicateStore(tmp_path/'counts.sqlite', manifest, create=True) as store:
        def mixed(plan, cell, rep):
            result = fake_compute(plan, cell, rep)
            if rep == 0:
                result.update(status='ok', complex_pair=True)
            return result
        runner.run_batch(store, max_new=2, compute=mixed)
        summary = runner.summarize(store)
        cell = summary['cells']['white_noise_n30']
        assert (cell['requested'], cell['attempted'], cell['valid'], cell['failed'], cell['unfinished']) == (4, 2, 1, 1, 2)
        assert cell['accounting_bounds'] == [.25, 1.]
        assert cell['valid_only_rate'] == 1 and cell['rate'] is None
        assert not any(summary[k] for k in ('AT5_passed', 'AT15_passed', 'AT16_passed', 'G2_passed'))
        assert summary['power'] is None


def test_development_never_passes_acceptance_even_with_constructed_complete_success(tmp_path, manifest):
    with ReplicateStore(tmp_path/'development.sqlite', manifest, create=True) as store:
        def all_valid(plan, cell, rep):
            return dict(cell=cell['name'], replicate=rep, status='ok',
                        complex_pair=True, p_value=.01, S=.3)
        runner.run_batch(store, max_new=100, compute=all_valid)
        summary = runner.summarize(store)
        assert all(c['unfinished'] == c['failed'] == 0 for c in summary['cells'].values())
        assert not summary['AT5_passed'] and not summary['AT15_passed'] and not summary['AT16_passed']
        assert summary['power'] is None


def test_registration_gate_prevents_rng_work_and_database_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'environment_identity', lambda root: pytest.fail('Pending gate got past registration check'))
    with pytest.raises(IntegrityError, match='G1'):
        runner.make_manifest(tmp_path, 'registered', {'G1': 'pending'})
    assert list(tmp_path.iterdir()) == []


def test_forged_official_plan_without_receipt_is_rejected_before_compute(tmp_path, manifest):
    manifest['plan'] = runner.make_plan('registered')
    with ReplicateStore(tmp_path/'gate.sqlite', manifest, create=True) as store:
        with pytest.raises(IntegrityError, match='receipt'):
            runner.run_batch(store, max_new=1, compute=lambda *args: pytest.fail('Official work ran'))


def test_changed_design_is_rejected_before_compute(tmp_path, manifest):
    manifest['plan']['surrogate_attempts'] = 9
    with ReplicateStore(tmp_path/'design.sqlite', manifest, create=True) as store:
        with pytest.raises(IntegrityError, match='frozen'):
            runner.run_batch(store, max_new=1, compute=lambda *args: pytest.fail('Changed design ran'))


def test_nonfinite_payload_rolls_back_without_erasing_prior_results(tmp_path, manifest):
    with ReplicateStore(tmp_path/'finite.sqlite', manifest, create=True) as store:
        runner.run_batch(store, max_new=1, compute=fake_compute)
        with pytest.raises(ValueError):
            with store.transaction():
                store.put('white_noise_n30', 1, dict(cell='white_noise_n30', replicate=1, value=float('nan')))
        assert store.verify() == 1


@pytest.mark.parametrize('issue', ['missing_archived_hashes', 'changed_hash', 'naive_timestamp', 'pending', 'api_401', 'not_immutable'])
def test_receipt_inconsistencies_fail_before_tag_or_generator_use(tmp_path, issue):
    expected = {name: '0'*64 for name in ['H1.md', 'H1_protocol.pdf', 'H1_OSF_responses.md',
                                        'H1_supporting_materials.zip', 'H1_submission_manifest.json']}
    receipt = dict(G1='passed', anonymous_api_check={'public_status_verified': True, 'status_code': 200},
                   public_immutable_verified=True, archived_attachment_bytes_verified=True,
                   expected_attachment_sha256=expected, archived_attachment_sha256=expected.copy(),
                   prereg_H1_tag='prereg-H1', public_registration_timestamp_utc='2026-09-26T10:00:00Z',
                   public_first_verified_at_utc='2026-09-26T10:01:00Z')
    if issue == 'missing_archived_hashes':
        receipt.pop('archived_attachment_sha256')
    elif issue == 'changed_hash':
        receipt['archived_attachment_sha256']['H1.md'] = 'f'*64
    elif issue == 'naive_timestamp':
        receipt['public_registration_timestamp_utc'] = '2026-09-26T10:00:00'
    elif issue == 'pending':
        receipt['G1'] = 'pending'
    elif issue == 'api_401':
        receipt['anonymous_api_check']['status_code'] = 401
    else:
        receipt['public_immutable_verified'] = False
    with pytest.raises(IntegrityError):
        runner.verify_registration(tmp_path, receipt)
