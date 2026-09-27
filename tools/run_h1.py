"""The registered H1 analysis, run once (H1 sections 4-10, plan step H1.2-H1.3).

Registered mode is closed unless G1 verifies, G2 is recorded as passed, the
raw ABMI file matches its acquisition record, the checkout is clean and the
environment matches the lock. It uses the registered counts and streams, with
no overrides, and refuses to run if its output directory exists. A later
recomputation for verification must use --recomputation and a new directory.

Rehearsal mode runs the same pipeline on an artificial ONS-format file with
shortened counts and labels every output as artificial. It touches no record.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uc_core import abmi, h1_official  # noqa: E402
from uc_core.h1 import analyze_h1  # noqa: E402
from uc_core.h1_reporting import write_registered_report  # noqa: E402
from uc_core.validation_runner import environment_identity, serial, verify_registration  # noqa: E402
from uc_core.validation_store import canonical, digest  # noqa: E402

REGISTERED_OUTPUT = ROOT / 'runs/h1-registered'


def rehearse(input_file, release_date, output, *, surrogates, resamples):
    parsed = abmi.parse_time_series_csv(Path(input_file).read_bytes())
    abmi.check_identity(parsed, release_date=release_date)
    labels, values = abmi.growth(*abmi.registered_sample(parsed))
    output = Path(output)
    started = time.perf_counter()
    results = analyze_h1(values, B=surrogates, interval_B=resamples)
    manifest = write_registered_report(output / 'report', values, labels, results, D80=None,
                                       data_kind='artificial_pipeline_rehearsal',
                                       metadata=dict(input_file=str(input_file), surrogates=surrogates,
                                                     episode_resamples=resamples,
                                                     seconds=round(time.perf_counter() - started, 1)))
    return manifest


def registered(output, *, recomputation):
    receipt = json.loads((ROOT / 'audit/H1_REGISTRATION.json').read_text(encoding='utf-8'))
    receipt_digest = verify_registration(ROOT, receipt)
    g2 = h1_official.check_g2(ROOT)
    identity = environment_identity(ROOT)
    if identity['dirty'] or identity['python'] != '3.12.14':
        raise h1_official.GateClosed('The registered run requires a clean checkout and Python 3.12.14')
    record, labels, values = h1_official.load_registered_growth(ROOT)
    output = Path(output)
    if not recomputation and output.resolve() != REGISTERED_OUTPUT.resolve():
        raise h1_official.GateClosed('The registered run writes only to runs/h1-registered')
    output.mkdir(parents=True, exist_ok=False)
    log = dict(kind='recomputation' if recomputation else 'registered primary run',
               started_utc=datetime.now(timezone.utc).isoformat(), commit=identity['commit'],
               registration_receipt_sha256=receipt_digest,
               g2_record_sha256=digest((ROOT / h1_official.G2_RECORD).read_bytes()),
               raw_file=record['file'], raw_sha256=record['sha256'], release=record['release_title'],
               growth_observations=len(values), first_quarter=labels[0], last_quarter=labels[-1],
               environment=identity)
    (output / 'run-log.json').write_bytes(canonical(log) + b'\n')
    started = time.perf_counter()
    results = analyze_h1(values)
    log.update(finished_utc=datetime.now(timezone.utc).isoformat(), seconds=round(time.perf_counter() - started, 1),
               input_sha256=results['input_sha256'])
    (output / 'run-log.json').write_bytes(canonical(log) + b'\n')
    (output / 'analysis.json').write_bytes(canonical(serial(results)) + b'\n')
    manifest = write_registered_report(output / 'report', values, labels, results, D80=g2['D80'],
                                       metadata=dict(run_log=log, D80_source=h1_official.G2_RECORD))
    complete = dict(run_log_sha256=digest((output / 'run-log.json').read_bytes()),
                    analysis_sha256=digest((output / 'analysis.json').read_bytes()),
                    report_manifest_sha256=digest((output / 'report/manifest.json').read_bytes()))
    (output / 'RUN_COMPLETE.json').write_bytes(canonical(complete) + b'\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--registered', action='store_true')
    mode.add_argument('--rehearsal-input', type=Path, help='artificial ONS-format file')
    parser.add_argument('--output-directory', type=Path, default=REGISTERED_OUTPUT)
    parser.add_argument('--recomputation', action='store_true')
    parser.add_argument('--rehearsal-release-date', default='01-01-2000')
    parser.add_argument('--rehearsal-surrogates', type=int, default=20)
    parser.add_argument('--rehearsal-resamples', type=int, default=200)
    args = parser.parse_args()
    if args.registered:
        manifest = registered(args.output_directory, recomputation=args.recomputation)
    else:
        if args.output_directory.resolve() == REGISTERED_OUTPUT.resolve():
            parser.error('A rehearsal needs its own --output-directory')
        manifest = rehearse(args.rehearsal_input, args.rehearsal_release_date, args.output_directory,
                            surrogates=args.rehearsal_surrogates, resamples=args.rehearsal_resamples)
    print(json.dumps(dict(data_kind=manifest['data_kind'], conclusion=manifest['interpretation']['conclusion'],
                          files=len(manifest['file_sha256'])), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
