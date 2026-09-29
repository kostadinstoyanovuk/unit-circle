"""E3 X.2: no download. The H1-registered ABMI file is re-verified and a manifest note is added.

prereg/E3.md section 4 and Annex B X.2: "After ABMI is acquired under H1, re-verify its hash and add a
manifest note for E3." The note step hashes the raw bytes only; it parses no value. The one-shot run
later loads the registered growth through uc_core.h1_official.load_registered_growth, which verifies
the bytes again and applies H1's stop rules.
"""
from __future__ import annotations

from pathlib import Path

from . import gates, records

H1_ACQUISITION_RECORD = "data/raw/ABMI_acquisition.json"
NOTE_RECORD = "audit/e3_source/data-note.json"
NOTE_MARK = "E3 (prereg-E3"


def record_data_note(root) -> dict:
    """G4 for E3, then the hash re-verification, the note record and the manifest note, once."""
    root = Path(root)
    gate = gates.check_registration(root, "e3")
    if (root / NOTE_RECORD).exists():
        raise records.RecordExists(f"{NOTE_RECORD} already exists; the E3 data note is written once")
    path = root / H1_ACQUISITION_RECORD
    if not path.is_file():
        raise gates.GateClosed("The ABMI file has not been acquired under H1; E3 X.2 waits for it")
    acquisition = records.read_json(path)
    content = (root / acquisition["file"]).read_bytes()
    if gates.sha256_bytes(content) != acquisition["sha256"] or len(content) != acquisition["bytes"]:
        raise gates.GateClosed("The ABMI file's bytes differ from its H1 acquisition record")
    row = records.manifest_row(root, acquisition["file"])
    if row is None or row["sha256"] != acquisition["sha256"]:
        raise gates.GateClosed("DATA_MANIFEST.csv does not list the ABMI file with its recorded SHA-256")
    if NOTE_MARK in row["notes"]:
        raise records.RecordExists("DATA_MANIFEST.csv already carries the E3 note")
    verified = gates.now_utc()
    record = dict(record_type="E3 data note (prereg/E3.md section 4; Annex B, X.2): no download",
                  file=acquisition["file"], sha256=acquisition["sha256"], bytes=acquisition["bytes"],
                  h1_acquisition_record=H1_ACQUISITION_RECORD,
                  h1_acquisition_record_sha256=gates.sha256_file(path),
                  release_title=acquisition.get("release_title"), hash_reverified_utc=verified,
                  registration=gate, statement=("E3 uses the H1-registered ABMI file unchanged; no further data "
                                                "and no other vintage."))
    records.write_once(root / NOTE_RECORD, records.pretty(record))
    records.replace_manifest_row(root, acquisition["file"], acquisition["sha256"], notes=(
        f"{row['notes']}; {NOTE_MARK}, OSF {gate.get('registration_id')}) uses this file unchanged: SHA-256 "
        f"re-verified {verified}; record {NOTE_RECORD}"))
    return record


def check_data_note(root) -> dict:
    """The E3 note exists, is committed, and names the current ABMI acquisition."""
    root = Path(root)
    if not (root / NOTE_RECORD).is_file():
        raise gates.GateClosed(f"{NOTE_RECORD} is missing: E3 X.2 (hash re-verification and manifest note) "
                               "has not been done")
    gates.check_committed(root, NOTE_RECORD)
    note = records.read_json(root / NOTE_RECORD)
    acquisition = records.read_json(root / H1_ACQUISITION_RECORD)
    if note.get("sha256") != acquisition.get("sha256") or note.get("file") != acquisition.get("file"):
        raise gates.GateClosed("The E3 data note names another file or hash than the H1 acquisition record")
    return dict(note, record_sha256=gates.sha256_file(root / NOTE_RECORD))
