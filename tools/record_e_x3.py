"""Record the E1 or E3 official synthetic checks (X.3) in audit/Ek_X3.json, once.

  python tools/record_e_x3.py e1 --size runs/extensions/E1/x3_size.jsonl --power runs/extensions/E1/x3_power.jsonl
  python tools/record_e_x3.py e3 --prerequisite runs/extensions/E3/x3_prerequisite.jsonl \
      --size runs/extensions/E3/x3_size.jsonl --power runs/extensions/E3/x3_power.jsonl

Give --size or --power once per file when a check was split across processes. --evidence (repeatable)
hashes supporting files into the record, such as the logs of the Annex B X.3 prerequisite tests (E1: F1,
AT-1 to AT-4 through uc_core.ar, the section 7 unit test; E3: F2 with AT-11 and the local-level check).
The outputs are summarised by tools/run_e_checks.py in registered mode (gate, lock, clean tree and every saved record
re-verified); they must form one registered run of one code identity with seed 1927, 200 series per
cell, B = 1000 and kappa 1.0-1.6. The record is written whether or not the checks passed, and is the
evidence the X.2 and X.4 gates read. Commit it before acquisition (E1) or the one-shot run.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uc_ext_official import gates, x3  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("extension", choices=gates.EXTENSIONS)
    parser.add_argument("--size", action="append", required=True, type=Path)
    parser.add_argument("--power", action="append", required=True, type=Path)
    parser.add_argument("--prerequisite", type=Path, help="E3 only: the registered prerequisite record")
    parser.add_argument("--evidence", action="append", type=Path, default=[],
                        help="supporting evidence to hash into the record, once per file (for example the logs of "
                             "the X.3 prerequisite tests); recorded, not evaluated")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        record = x3.record_x3(args.root, args.extension, size_files=args.size, power_files=args.power,
                              prerequisite_file=args.prerequisite, evidence_files=args.evidence)
    except (gates.GateClosed, x3.X3InputError, x3.records.RecordExists) as error:
        raise SystemExit(f"Refused: {error}") from None
    print(json.dumps({key: record.get(key) for key in ("extension", "X3", "size_passed", "power_passed",
                                                       "prerequisite_passed", "D80", "code_sha256")}, indent=2))
    print(f"Written {gates.x3_record_path(args.extension)}. Review, commit and push it before the next step.")
    return 0 if record["X3"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
