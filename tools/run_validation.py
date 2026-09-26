"""Bounded validation CLI. No data downloads, automatic reseeding or gate bypass."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uc_core.validation_runner import make_manifest, run_batch, summarize
from uc_core.validation_store import canonical, read_manifest, ReplicateStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'verify', 'summary'))
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--mode', choices=('development', 'registered'))
    parser.add_argument('--max-new', type=int, default=1)
    parser.add_argument('--create', action='store_true')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--summary-output', type=Path)
    args = parser.parse_args()
    if args.action == 'run':
        if not args.mode:
            parser.error('run requires an explicit --mode')
        receipt = json.loads((ROOT / 'audit/H1_REGISTRATION.json').read_text())
        manifest = make_manifest(ROOT, args.mode, receipt)
    else:
        if args.create or args.mode or args.backup:
            parser.error('create, mode and backup apply only to run')
        manifest = read_manifest(args.database)
    with ReplicateStore(args.database, manifest, create=args.create) as store:
        if args.action == 'run':
            print(json.dumps(run_batch(store, max_new=args.max_new)))
        summary = summarize(store)
        if args.summary_output:
            # A new named summary preserves earlier incomplete summaries.
            with args.summary_output.open('xb') as output:
                output.write(canonical(summary) + b'\n')
        if args.backup:
            print(json.dumps({'backup': store.backup(args.backup)}))
        print(json.dumps(summary, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
