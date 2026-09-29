"""The registered E1 analysis, run once (prereg/E1.md sections 5-10; Annex B, X.4).

  python tools/run_e1.py --registered
  python tools/run_e1.py --registered --recomputation --output-directory runs/e1-recomputation-<date>
  python tools/run_e1.py --rehearsal-workbook artificial.xlsx --output-directory runs/e1-rehearsal

Registered mode is closed unless G4 for E1 verifies, audit/E1_X3.json records passed official synthetic
checks, the code identity equals the one that ran X.3 (with the lock and Python 3.12.14), the code is
the research root's own, and every E1 X.2 record is committed with the levels re-extracted identically.
It uses the registered seed, counts and streams (B = 1,000 attempts per comparison; 10,000 episode
resamples) with no options, writes only runs/e1-registered, and refuses if that directory exists. The
run verifies every file it wrote against the hashes it recorded. A later recomputation uses
--recomputation and a new directory and is labelled as such.

Rehearsal mode runs the same X.2 selection and extraction and the whole pipeline on an artificial
workbook with a development seed and shortened counts, labels every output artificial and touches no
record.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uc_ext_official import e1_source, gates, run, x4  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--registered", action="store_true")
    mode.add_argument("--rehearsal-workbook", type=Path, help="artificial workbook in the registered layout")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--recomputation", action="store_true")
    parser.add_argument("--rehearsal-surrogates", type=int, default=20)
    parser.add_argument("--rehearsal-resamples", type=int, default=200)
    parser.add_argument("--rehearsal-territory", type=Path)
    parser.add_argument("--rehearsal-version-location")
    args = parser.parse_args(argv)
    try:
        if args.registered:
            output = args.output_directory or args.root / x4.REGISTERED_OUTPUT["e1"]
            manifest = run.run_e1(args.root, output, recomputation=args.recomputation)
        else:
            if args.recomputation or not args.output_directory:
                parser.error("A rehearsal takes its own --output-directory and no --recomputation")
            if args.output_directory.resolve() == (args.root / x4.REGISTERED_OUTPUT["e1"]).resolve():
                parser.error("A rehearsal needs its own --output-directory")
            territory = (json.loads(args.rehearsal_territory.read_text(encoding="utf-8"))
                         if args.rehearsal_territory else None)
            manifest = run.rehearse_e1(args.rehearsal_workbook, args.output_directory,
                                       surrogates=args.rehearsal_surrogates, resamples=args.rehearsal_resamples,
                                       territory=territory, version_location=args.rehearsal_version_location)
    except e1_source.SourceStop as stop:
        raise SystemExit(f"Stopped ({stop.stage}): {stop}") from None
    except (gates.GateClosed, x4.records.RecordExists) as error:
        raise SystemExit(f"Refused: {error}") from None
    interpretation = manifest["interpretation"]
    print(json.dumps(dict(data_kind=manifest["data_kind"], conclusion=interpretation["conclusion"],
                          raw_p=interpretation["raw_p"], p_label=interpretation["p_label"],
                          files=len(manifest["file_sha256"])), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
