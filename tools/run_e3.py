"""The registered E3 analysis, run once (prereg/E3.md sections 6-10; Annex B, X.4).

  python tools/run_e3.py --registered
  python tools/run_e3.py --registered --recomputation --output-directory runs/e3-recomputation-<date>
  python tools/run_e3.py --rehearsal-input artificial.csv --output-directory runs/e3-rehearsal

Registered mode is closed unless G4 for E3 verifies, audit/E3_X3.json records passed official synthetic
checks and prerequisites, the code identity equals the one that ran X.3 (with the lock and Python
3.12.14), the code is the research root's own, the E3 data note is committed, and the H1-registered
ABMI file matches its acquisition record and H1's stop rules. It uses the registered seed, counts and
streams (B = 1,000 attempts per comparison, each surrogate re-estimated by the section 6 procedure;
10,000 episode resamples) with no options, writes only runs/e3-registered, and refuses if that
directory exists. Every surrogate fit is kept in surrogate-fits.json.gz (Annex B). The run verifies
every file it wrote against the hashes it recorded.

Rehearsal mode runs the same pipeline on an artificial ONS-format file with a development seed and
shortened counts, labels every output artificial and touches no record.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uc_ext_official import gates, run, x4  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--registered", action="store_true")
    mode.add_argument("--rehearsal-input", type=Path, help="artificial ONS-format file")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--recomputation", action="store_true")
    parser.add_argument("--rehearsal-release-date", default="01-01-2000")
    parser.add_argument("--rehearsal-surrogates", type=int, default=5)
    parser.add_argument("--rehearsal-resamples", type=int, default=200)
    args = parser.parse_args(argv)
    try:
        if args.registered:
            output = args.output_directory or args.root / x4.REGISTERED_OUTPUT["e3"]
            manifest = run.run_e3(args.root, output, recomputation=args.recomputation)
        else:
            if args.recomputation or not args.output_directory:
                parser.error("A rehearsal takes its own --output-directory and no --recomputation")
            if args.output_directory.resolve() == (args.root / x4.REGISTERED_OUTPUT["e3"]).resolve():
                parser.error("A rehearsal needs its own --output-directory")
            manifest = run.rehearse_e3(args.rehearsal_input, args.rehearsal_release_date, args.output_directory,
                                       surrogates=args.rehearsal_surrogates, resamples=args.rehearsal_resamples)
    except (gates.GateClosed, x4.records.RecordExists) as error:
        raise SystemExit(f"Refused: {error}") from None
    interpretation = manifest["interpretation"]
    print(json.dumps(dict(data_kind=manifest["data_kind"], conclusion=interpretation["conclusion"],
                          raw_p=interpretation["raw_p"], p_label=interpretation["p_label"],
                          files=len(manifest["file_sha256"])), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
