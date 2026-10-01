"""The registered E4 analysis, run once (prereg/E4.md sections 7 to 10; Annex B, X.4).

  python tools/run_e4.py --registered
  python tools/run_e4.py --registered --release-dates release-dates.json
  python tools/run_e4.py --registered --recomputation --output-directory runs/e4-recomputation-<date>

Registered mode is closed unless the code is the research root's own (uc_core, uc_ext, uc_ext_official, uc_e4),
G4 for E4 verifies, audit/E4_X3.json records passed official synthetic checks, the code identity equals the one
that ran X.3 (with the lock and Python 3.12.14) and its E1 part is E1's frozen code, the X.2 edition,
acquisition and mapping records are committed and the re-read availability equals the recorded one, and
audit/H1_RESULT.json is committed with the four registered onsets. Nothing is written before every gate has
passed. The run uses master seed 1927, the registered streams 5400 to 5405 (5403 unused), B = 1,000 attempts
per comparison and 10,000 episode resamples, with no option to change them; it writes only runs/e4-registered
and refuses if that directory exists. It verifies every file it wrote against the hashes it recorded.

--release-dates names a JSON object mapping vintage labels to ISO dates established from ONS metadata; without
it every release is stated by its label month (prereg/E4.md section 10; R-10.5). The dates are part of the
recorded input. A later recomputation uses --recomputation and a new directory, is labelled as such and is never
frozen.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uc_ext_official import e4_run, e4_source, gates, x4  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registered", action="store_true", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--recomputation", action="store_true")
    parser.add_argument("--release-dates", type=Path, help="JSON object: vintage label -> ISO release date")
    args = parser.parse_args(argv)
    if args.recomputation and not args.output_directory:
        parser.error("A recomputation takes its own --output-directory")
    dates = json.loads(args.release_dates.read_text(encoding="utf-8")) if args.release_dates else None
    if dates is not None and not isinstance(dates, dict):
        parser.error("--release-dates must name a JSON object")
    output = args.output_directory or args.root / x4.REGISTERED_OUTPUT["e4"]
    try:
        manifest = e4_run.run_e4(args.root, output, recomputation=args.recomputation, release_dates=dates)
    except (gates.GateClosed, x4.records.RecordExists, e4_source.SourceStop) as error:
        raise SystemExit(f"Refused: {error}") from None
    interpretation = manifest["interpretation"]
    print(json.dumps(dict(data_kind=manifest["data_kind"], conclusion=interpretation["conclusion"],
                          raw_p=interpretation["raw_p"], p_label=interpretation["p_label"],
                          holm_input=interpretation["holm_input"], files=len(manifest["file_sha256"])), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
