"""Render report mechanics on one declared artificial input, never UK data."""
import argparse
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uc_core.h1 import analyze_h1
from uc_core.h1_reporting import write_development_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory', type=Path, required=True)
    args = parser.parse_args()
    rng = np.random.Generator(np.random.PCG64(2026092601))
    values = rng.uniform(1, 3, 259)
    for onset in (20, 48, 55, 132, 211):
        values[onset:onset+2] = [-1, -.6]
    # Existing H1 engineering interface; these are shortened development
    # comparisons on artificial input, not any official size/power cell.
    results = analyze_h1(values, B=24, interval_B=256)
    manifest = write_development_report(args.output_directory, values, results,
        fixture_metadata=dict(data_kind='artificial_development_fixture', generation_seed=2026092601,
                              length=259, surrogate_attempts_per_mode=24, episode_resamples=256,
                              analysis_interface='analyze_h1 shortened engineering fixture'))
    print(f"Development report saved: {len(manifest['file_sha256'])} checked output files; no empirical result.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
