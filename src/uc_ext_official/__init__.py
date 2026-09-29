"""Execution tools for the registered extensions E1 and E3 (prereg/E1.md, prereg/E3.md, Annex B X.2-X.5).

X.2: the E1 workbook is acquired once and its series selected from header text only
(`e1_source`, `workbook`); E3 re-verifies the H1 file and records a manifest note (`e3_source`).
X.3 evidence: the official synthetic checks are summarised into a committed record (`x3`).
X.4: each extension's registered analysis runs once and its outputs are frozen (`x4`, `report_e1`,
`report_e3`). Every gate fails closed (`gates`).

The analysis itself is `uc_ext.e1.analyze` and `uc_ext.e3.analyze`, imported unchanged. Nothing in
this package is part of the X.3 code identity (run_e_checks.code_identity hashes uc_ext and uc_core
only), so an X.2 tool can be corrected before any value is read without touching the frozen code.
Importing this package reads no data.
"""
