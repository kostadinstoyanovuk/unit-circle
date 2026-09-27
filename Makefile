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
