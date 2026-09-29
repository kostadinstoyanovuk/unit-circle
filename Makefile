PYTHON ?= python

.PHONY: all audit test check-data s1 s1-figures s2 note
audit:
	$(PYTHON) tools/verify_m0.py

test:
	$(PYTHON) -m pytest -q

check-data:
	$(PYTHON) tools/check_data.py

# S1 Yule centenary (D-018): fits, bootstrap bands, AT-13, then figures from the saved fits.
s1: check-data
	$(PYTHON) tools/build_s1.py
	$(PYTHON) tools/s1_table.py
	$(PYTHON) tools/build_yule1927.py

s1-figures: s1
	$(PYTHON) tools/plot_s1.py

# S2 Samuelson check (D-021): closed until G2 and the registered ABMI acquisition.
s2: check-data
	$(PYTHON) tools/build_s2.py

# Core note (plan W): every number is written from the evidence records; a result that does not
# exist yet is typeset as a visible placeholder.
note:
	$(PYTHON) tools/build_note.py --pdf

# Everything that can be rebuilt today. S2 and the frozen H1 record join after G2 and the registered acquisition.
all: test s1-figures note

# No target downloads data. Only tools/build_s2.py and the gated H1 tools read the registered UK file,
# and they stop until G2 has passed and the file has been acquired (docs/H1_EXECUTION.md).

# --- E1 and E3 pipelines (uc_ext; M4b, fixed by M13). Outputs go to runs/, which .gitignore ignores, so the
# tree stays clean: registered runs refuse a dirty tree and a non-ignored --out (tools/run_e_checks.py, S3).
.PHONY: test-e e1-x3 e3-prerequisites e3-x3 e-runtime
E_OUT ?= runs/extensions

# Synthetic-only tests of the E1/E3 pipelines (development seeds, small sizes, AT-11's sunspot fixture).
test-e:
	$(PYTHON) -m pytest -q tests/test_e_common.py tests/test_e1.py tests/test_e3.py tests/test_e_runner.py

# E1 X.3 (Annex B step 3). Fails closed unless run from this root on a clean tree, under the lock and
# Python 3.12.14, with prereg-E1 pushed and audit/E1_REGISTRATION.json public and approved. Resumable.
e1-x3:
	mkdir -p $(E_OUT)/E1
	$(PYTHON) tools/run_e_checks.py e1 size --registered --root . --out $(E_OUT)/E1/x3_size.jsonl
	$(PYTHON) tools/run_e_checks.py e1 power --registered --root . --out $(E_OUT)/E1/x3_power.jsonl
	$(PYTHON) tools/run_e_checks.py e1 summarize --registered --root . --out $(E_OUT)/E1/x3_size.jsonl > $(E_OUT)/E1/x3_size_summary.json
	$(PYTHON) tools/run_e_checks.py e1 summarize --registered --root . --out $(E_OUT)/E1/x3_power.jsonl > $(E_OUT)/E1/x3_power_summary.json

# E3 section 11 prerequisites on stream 5320/1/0 and AT-11's fixture. The record is never overwritten; the
# command exits non-zero unless every prerequisite passes, and E3 size and power refuse a record that did not.
e3-prerequisites: $(E_OUT)/E3/x3_prerequisite.jsonl
$(E_OUT)/E3/x3_prerequisite.jsonl:
	mkdir -p $(E_OUT)/E3
	$(PYTHON) tools/run_e_checks.py e3 prerequisite --registered --root . --out $@

# E3 X.3, only after a passed prerequisite record made by the same commit. Resumable.
e3-x3: e3-prerequisites
	$(PYTHON) tools/run_e_checks.py e3 size --registered --root . --prerequisite $(E_OUT)/E3/x3_prerequisite.jsonl --out $(E_OUT)/E3/x3_size.jsonl
	$(PYTHON) tools/run_e_checks.py e3 power --registered --root . --prerequisite $(E_OUT)/E3/x3_prerequisite.jsonl --out $(E_OUT)/E3/x3_power.jsonl
	$(PYTHON) tools/run_e_checks.py e3 summarize --registered --root . --out $(E_OUT)/E3/x3_size.jsonl > $(E_OUT)/E3/x3_size_summary.json
	$(PYTHON) tools/run_e_checks.py e3 summarize --registered --root . --out $(E_OUT)/E3/x3_power.jsonl > $(E_OUT)/E3/x3_power_summary.json

# Development-seed timing of the E1/E3 replicates (no registered seed, no registered size).
e-runtime:
	$(PYTHON) tools/measure_e_runtime.py

# --- E1 and E3 execution tools: X.2 data, the X.3 record, the X.4 one-shot run and the X.5 freeze
# (docs/E_EXECUTION.md; src/uc_ext_official). The tests use artificial workbooks and ONS-format files only.
.PHONY: test-e-official
test-e-official:
	$(PYTHON) -m pytest -q tests/test_e_official_workbook.py tests/test_e_official_e1_source.py \
		tests/test_e_official_gates_x3.py tests/test_e_official_x2_stages.py tests/test_e_official_x4.py \
		tests/test_e_official_registered_path.py tests/test_e_official_records_cli.py
