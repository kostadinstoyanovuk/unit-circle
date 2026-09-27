"""Freeze the registered H1 outputs into the repository (plan step H1.4).

Verifies the completed registered run against its own hashes, copies the
report, tables and figures into audit/h1/ and figures/, and writes
audit/H1_RESULT.json with the outcome in the registered wording. It never
reruns anything. The h1-frozen tag is created by hand after review.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uc_core.validation_store import digest  # noqa: E402

TABLES = ('report.json', 'comparisons.csv', 'episodes.csv', 'qualifying-runs.csv', 'rolling.csv',
          'primary-surrogates.csv', 'manifest.json')
FIGURES = ('persistence', 'surrogates')


def verify(run):
    complete = json.loads((run / 'RUN_COMPLETE.json').read_text(encoding='utf-8'))
    checks = {'run-log.json': complete['run_log_sha256'], 'analysis.json': complete['analysis_sha256'],
              'report/manifest.json': complete['report_manifest_sha256']}
    for name, expected in checks.items():
        if digest((run / name).read_bytes()) != expected:
            raise SystemExit(f'Run output changed after completion: {name}')
    manifest = json.loads((run / 'report/manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['file_sha256'].items():
        if digest((run / 'report' / name).read_bytes()) != expected:
            raise SystemExit(f'Report file changed after completion: {name}')
    log = json.loads((run / 'run-log.json').read_text(encoding='utf-8'))
    if log['kind'] != 'registered primary run' or manifest['data_kind'] != 'uk_abmi_registered':
        raise SystemExit('Only the registered primary run can be frozen')
    return log, manifest


def summary(run, log, manifest):
    report = json.loads((run / 'report/report.json').read_text(encoding='utf-8'))['result']
    primary = report['comparisons'][0]
    interval = report['episode_interval']
    return dict(record_type='H1 registered primary result', registration='https://doi.org/10.17605/OSF.IO/WCNBZ',
                run_log=log, interpretation=manifest['interpretation'],
                primary=dict(S=primary['value'], p_value=primary['p_value'], eligible_episodes=primary['eligible_episodes'],
                             positive_changes=primary['positive_components'], retained=primary['retained'],
                             attempted=primary['attempted'], exceedances=primary['exceedances'], status=primary['status']),
                episode_interval=interval.get('interval') if isinstance(interval, dict) else None,
                comparisons=report['comparisons'],
                episodes=[{k: e[k] for k in ('onset_quarter', 'end_quarter', 'statistic_available', 'change')}
                          for e in report['episodes']])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=ROOT / 'runs/h1-registered')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    run, root = args.run, args.root
    log, manifest = verify(run)
    target = root / 'audit/h1'
    target.mkdir(parents=True, exist_ok=False)
    for name in TABLES:
        shutil.copy2(run / 'report' / name, target / name)
    shutil.copy2(run / 'run-log.json', target / 'run-log.json')
    shutil.copy2(run / 'analysis.json', target / 'analysis.json')
    for name in FIGURES:
        for extension in ('svg', 'png'):
            shutil.copy2(run / 'report' / f'{name}.{extension}', root / 'figures' / f'h1_{name}.{extension}')
    result = summary(run, log, manifest)
    (root / 'audit/H1_RESULT.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(conclusion=result['interpretation']['conclusion'], S=result['primary']['S'],
                          p=result['primary']['p_value']), indent=2))
    print('Review, commit and push, then: git tag -a h1-frozen -m "H1 registered result frozen" && git push origin h1-frozen')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
