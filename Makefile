PYTHON ?= python

.PHONY: audit test check-data s1 s1-figures s2
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

# The complete `make all` research rebuild is defined when the core note exists.
# No target downloads or reads UK observations.
