"""E2 X.1: the section 7 onset table by rule from the H1-registered GDP file, and the record registered runs read.

Usage, at the research root after h1-frozen:  python tools/e2_onsets.py --root . [--out audit/E2_ONSETS.json]

Reads GDP only, through uc_core.h1_official.load_registered_growth, which verifies the raw ABMI file against
its acquisition record; no unemployment value is read. The rule is H1 section 5 applied to g at E2
positions 0-194 (H1 growth positions 64-258), with structural eligibility (uc_e2.variables.onset_table).
Refuses unless the tag h1-frozen exists, and never overwrites an existing record. Writes the record
(uc_e2.constants.ONSETS_RECORD by default) and prints the section 7 rows as Markdown for the addendum. If no
episode is eligible at W = 40, the record says so, and E2 is not registered (addendum section 0).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def _git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def markdown(record):
    lines = ["| Episode | Onset quarter | Onset position | End quarter | Eligible at W = 40 (32, 48) "
             "| Also an H1 episode with the same onset? |", "|---|---|---|---|---|---|"]
    for number, row in enumerate(record["episodes"], start=1):
        eligible = row["eligible"]
        flags = ["yes" if eligible[w] else "no" for w in (40, 32, 48)]
        lines.append(f"| {number} | {row['onset_quarter']} | {row['onset']} | {row['end_quarter']} "
                     f"| {flags[0]} ({flags[1]}, {flags[2]}) | {'yes' if row['also_h1_onset'] else 'no'} |")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="research checkout holding the H1-registered ABMI file")
    parser.add_argument("--out", help="record path (default: uc_e2.constants.ONSETS_RECORD under the root)")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.root).resolve()
    sys.path.insert(0, str(root / "src"))
    from uc_core import h1_official
    from uc_e2 import constants, variables
    try:
        frozen = _git(root, "rev-parse", "-q", "--verify", "refs/tags/h1-frozen^{commit}")
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit("The tag h1-frozen is absent: E2's onsets are listed only after H1 is frozen") from error
    out = Path(args.out) if args.out else root / constants.ONSETS_RECORD
    if out.exists():
        raise SystemExit(f"{out} exists: the onset record is written once and never overwritten")
    acquisition, labels, growth = h1_official.load_registered_growth(root)
    record = variables.onset_record(growth, labels)
    record.update(h1_frozen_commit=frozen, abmi_acquisition_record=h1_official.ACQUISITION_RECORD,
                  abmi_file=acquisition.get("file"), abmi_sha256=acquisition.get("sha256"))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, indent=1) + "\n")
    print(markdown(record))
    if record["m_E2"] == 0:
        print("No episode is eligible at W = 40: E2 is not registered (addendum section 0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
