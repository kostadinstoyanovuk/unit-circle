"""The E4 code identity (tools/run_e4_checks.py, e4_sources) hashes the top-level uc_e4/*.py files only.

A subpackage or a data file in src/uc_e4 would fall outside the identity, so none may exist.
"""
from pathlib import Path

import uc_e4


def test_uc_e4_holds_only_top_level_python_sources():
    directory = Path(uc_e4.__file__).resolve().parent
    stray = sorted(p.name for p in directory.iterdir()
                   if p.name != "__pycache__" and not (p.is_file() and p.suffix == ".py"))
    assert stray == []
