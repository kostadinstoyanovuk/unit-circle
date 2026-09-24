PYTHON ?= python

.PHONY: audit test
audit:
	$(PYTHON) tools/verify_m0.py

test:
	$(PYTHON) -m pytest -q

# The original `make all` research rebuild is intentionally not yet defined.
# M0 is an audit baseline, not a completed paper or real-data pipeline.
