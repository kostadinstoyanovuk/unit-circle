"""Recompute SHA-256 hashes of raw files against DATA_MANIFEST.csv (make check-data)."""
import csv
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    problems, checked = [], 0
    with (root / "DATA_MANIFEST.csv").open(newline="", encoding="utf-8") as manifest:
        for row in csv.DictReader(manifest):
            path = root / row["file"]
            if not path.is_file():
                problems.append(f"missing: {row['file']}")
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != row["sha256"]:
                problems.append(f"hash differs: {row['file']}")
            checked += 1
    listed = {row["file"] for row in csv.DictReader((root / "DATA_MANIFEST.csv").open(encoding="utf-8"))}
    for path in sorted((root / "data/raw").glob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_file() and path.name not in {".gitkeep", "README.md"} and relative not in listed:
            problems.append(f"unlisted raw file: {relative}")
    return checked, problems


if __name__ == "__main__":
    checked, problems = check()
    for problem in problems:
        print(problem)
    print(f"{checked} manifest file(s) checked; {len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
