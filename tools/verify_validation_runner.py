"""Small development-only recovery comparison and runtime measurement."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uc_core.validation_runner import compute_replicate, make_manifest, run_batch, summarize
from uc_core.validation_store import canonical, digest, ReplicateStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=False)
    manifest = make_manifest(ROOT, 'development')
    plan = manifest['plan']
    expected = sum(cell['requested'] for cell in plan['cells'])
    measurements = {c['name']: [] for c in plan['cells']}

    def measured(plan, cell, replicate):
        start = time.perf_counter()
        value = compute_replicate(plan, cell, replicate)
        measurements[cell['name']].append(time.perf_counter()-start)
        return value

    interrupted_path = args.output_directory/'resumed.sqlite'
    with ReplicateStore(interrupted_path, manifest, create=True) as store:
        def stop_at_size(plan, cell, replicate):
            if cell['name'] == 'size':
                raise KeyboardInterrupt('Development recovery fixture')
            return measured(plan, cell, replicate)
        try:
            run_batch(store, max_new=expected, compute=stop_at_size)
        except KeyboardInterrupt:
            pass
        assert store.verify() == 8
        checkpoint = store.backup(args.output_directory/'interrupted-backup.sqlite')
    with ReplicateStore(interrupted_path, manifest) as store:
        run_batch(store, max_new=expected, compute=measured)
        resumed = list(store.iter_records())
        assert len(resumed) == expected
        summary = summarize(store)
        assert run_batch(store, max_new=expected)['new_records'] == 0
        final_backup = store.backup(args.output_directory/'completed-backup.sqlite')
    with ReplicateStore(args.output_directory/'uninterrupted.sqlite', manifest, create=True) as store:
        run_batch(store, max_new=expected)
        uninterrupted = list(store.iter_records())
    assert canonical(resumed) == canonical(uninterrupted)
    assert not any(summary[k] for k in ('AT5_passed', 'AT15_passed', 'AT16_passed', 'G2_passed'))
    assert summary['power'] is None
    report = dict(
        checked_at_utc=datetime.now(timezone.utc).isoformat(), passed=True,
        scope='Development-only fixtures; no registered experiment or UK data acquisition.',
        plan=plan, completed_records=expected, interrupted_after_records=8,
        resumed_equals_uninterrupted=True, completed_resume_adds_zero_records=True,
        checkpoint_backup_records=checkpoint['records'],
        final_backup_records=final_backup['records'],
        final_backup_sha256=final_backup['sha256'],
        scientific_records_sha256=digest(canonical(resumed)),
        manifest_sha256=digest(canonical(manifest)),
        source_sha256=manifest['identity']['source_sha256'],
        python=manifest['identity']['python'],
        timing_seconds_by_cell={name: {'records': len(times), 'total': sum(times),
                                      'mean': sum(times)/len(times), 'maximum': max(times)}
                                for name, times in measurements.items()},
        database_bytes=interrupted_path.stat().st_size,
        official_experiments_run=False, raw_UK_data_acquired=False,
        acceptance_gates_passed=False,
        timing_limit='Single-process small fixtures include per-series setup and eight attempted surrogates; extrapolation is provisional and machine-dependent.'
    )
    with args.report.open('x', encoding='utf-8', newline='\n') as output:
        output.write(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(f'Development recovery verification: PASS; {expected} records match uninterrupted execution.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
