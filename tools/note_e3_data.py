"""E3 X.2: re-verify the H1-registered ABMI file's hash and add the E3 manifest note, once.

  python tools/note_e3_data.py

Closed until G4 for E3 verifies. No download and no value is read: the raw bytes are hashed against
data/raw/ABMI_acquisition.json; audit/e3_source/data-note.json is written and the ABMI row of
DATA_MANIFEST.csv gains a note that E3 uses the file unchanged (prereg/E3.md section 4; Annex B, X.2).
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uc_ext_official import e3_source, gates, records  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        record = e3_source.record_data_note(args.root)
    except (gates.GateClosed, records.RecordExists, ValueError) as error:
        raise SystemExit(f"Refused: {error}") from None
    print(json.dumps({k: record[k] for k in ("file", "sha256", "hash_reverified_utc")}, indent=2))
    print("Commit and push the note and DATA_MANIFEST.csv.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
