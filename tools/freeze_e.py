"""Freeze the registered E1, E3 or E4 outputs into the repository (Annex B, X.5).

  python tools/freeze_e.py e1
  python tools/freeze_e.py e3
  python tools/freeze_e.py e4

Verifies the completed registered run against its own recorded hashes (run log, analysis files,
report manifest and every report file), copies them into audit/ek/ and the figures into
figures/ek_*, verifies every copy, and writes audit/Ek_RESULT.json with the outcome in the addendum's
wording and the raw p labelled "raw, not family-adjusted". It never reruns anything and refuses a
rehearsal or a recomputation. The ek-frozen tag is created by hand after review (printed below). For E4 the
figures are figures/e4_realtime.* and figures/e4_surrogates.*, and m_E4 = 0 or a failed comparison is recorded
as failed with Holm input 1 (prereg/E4.md sections 7 and 11).
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uc_ext_official import gates, x4  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("extension", choices=gates.EXTENSIONS)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    run = args.run or args.root / x4.REGISTERED_OUTPUT[args.extension]
    try:
        result = x4.freeze(args.root, run, args.extension)
    except (gates.GateClosed, x4.records.RecordExists) as error:
        raise SystemExit(f"Refused: {error}") from None
    print(json.dumps(dict(conclusion=result["interpretation"]["conclusion"], S=result["primary"]["S"],
                          raw_p=result["primary"]["raw_p"], p_label=result["primary"]["p_label"],
                          files=len(result["frozen_files"])), indent=2))
    print(x4.tag_instructions(args.extension))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
