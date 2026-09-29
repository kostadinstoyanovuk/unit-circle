"""Write-once records and DATA_MANIFEST.csv rows for the E1 and E3 execution steps.

Records are written once: an existing file is never overwritten (the caller's step then refuses).
JSON records are UTF-8 with a trailing newline. Canonical JSON (sorted keys, no whitespace, no NaN)
is used where a file's hash is recorded. Non-finite floats are written as null by `json_safe`.
"""
from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path

import numpy as np

MANIFEST = "DATA_MANIFEST.csv"
MANIFEST_FIELDS = ("file", "source_url", "series_id", "retrieved_utc", "sha256", "licence", "notes")


class RecordExists(RuntimeError):
    """A write-once record already exists."""


def json_safe(value):
    """Plain JSON types; non-finite floats become None (NaN warm-up values, for example)."""
    if isinstance(value, dict):
        return {key if isinstance(key, str) else str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def canonical(value) -> bytes:
    return json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False,
                      ensure_ascii=True).encode("utf-8")


def pretty(value) -> bytes:
    return (json.dumps(json_safe(value), indent=2, allow_nan=False, ensure_ascii=False) + "\n").encode("utf-8")


def write_once(path, content: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as output:
            output.write(content)
    except FileExistsError:
        raise RecordExists(f"{path} already exists; it is written once") from None
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _manifest_rows(root):
    path = Path(root) / MANIFEST
    if not path.is_file():
        raise FileNotFoundError(f"{MANIFEST} is missing under {root}")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or next(csv.reader([lines[0]])) != list(MANIFEST_FIELDS):
        raise ValueError(f"{MANIFEST} does not have the expected header {MANIFEST_FIELDS}")
    if len(list(csv.DictReader(io.StringIO(text)))) != sum(1 for line in lines[1:] if line.strip()):
        raise ValueError(f"{MANIFEST} has a multi-line row; rows are edited only when each is one line")
    return path, text, lines


def _row_line(row: dict) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow([row[field] for field in MANIFEST_FIELDS])
    return buffer.getvalue()


def manifest_row(root, file: str) -> dict | None:
    _, text, _ = _manifest_rows(root)
    rows = [row for row in csv.DictReader(io.StringIO(text)) if row["file"] == file]
    if len(rows) > 1:
        raise ValueError(f"{MANIFEST} lists {file} more than once")
    return rows[0] if rows else None


def append_manifest_row(root, row: dict) -> None:
    """Append one row; refuse if the file is already listed."""
    path, text, _ = _manifest_rows(root)
    if manifest_row(root, row["file"]) is not None:
        raise RecordExists(f"{MANIFEST} already lists {row['file']}")
    prefix = "" if text.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8", newline="") as output:
        output.write(prefix + _row_line(row))


def replace_manifest_row(root, file: str, sha256: str, **changes) -> dict:
    """Rewrite the one line that lists `file` (whose recorded hash must be `sha256`); others stay byte for byte.

    Only the series_id and notes fields may change.
    """
    if set(changes) - {"series_id", "notes"}:
        raise ValueError("Only series_id and notes of a manifest row may be changed")
    path, _, lines = _manifest_rows(root)
    found = []
    buffer = []
    for number, line in enumerate(lines):
        record = next(csv.reader([line])) if number and line.strip() else None
        if record and record[0] == file:
            row = dict(zip(MANIFEST_FIELDS, record))
            if row["sha256"] != sha256:
                raise ValueError(f"{MANIFEST} lists {file} with another SHA-256")
            row.update(changes)
            found.append(row)
            buffer.append(_row_line(row))
        else:
            buffer.append(line)
    if len(found) != 1:
        raise ValueError(f"{MANIFEST} must list {file} exactly once (found {len(found)})")
    path.write_text("".join(buffer), encoding="utf-8", newline="")
    return found[0]
