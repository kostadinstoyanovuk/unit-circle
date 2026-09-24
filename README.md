# Unit Circle Programme

Research on autoregressive persistence, recession-onset diagnostics and polynomial stability.

The programme combines a preregistered empirical study of UK recessions, reproducible statistical software and a formal treatment of stability criteria. Its first phase establishes the mathematical conventions, analysis methods and verification framework before confirmatory experiments and UK data analysis begin.

## Research status

M1 Foundations and Registration Preparation is complete. The methods are implemented, the H1 protocol is drafted and all three repositories have passing hosted checks. The research suite contains 204 passing tests covering estimation, companion roots, rolling calculations, episode identification, surrogate comparisons and secondary analyses. A one-page paper proof establishes the real AR(2) stability triangle.

The H1 protocol is **unregistered**. No raw UK research series has been acquired or analysed, and the official size and power experiments have not run. Software checks establish implementation behaviour; they do not establish an empirical finding, statistical calibration or a completed formal theorem. Current milestone and gate evidence is recorded in [STATUS.md](STATUS.md).

## Repositories

| Repository | Purpose |
|---|---|
| [unit-circle](https://github.com/kostadinstoyanovuk/unit-circle) | Research methods, protocol, mathematical notes and verification |
| [unitcircle](https://github.com/kostadinstoyanovuk/unitcircle) | Installable Python package in development |
| [schur-cohn](https://github.com/kostadinstoyanovuk/schur-cohn) | Pinned Lean and mathlib foundation for formalisation |

## Read the work

- [H1 protocol draft](prereg/H1.md): research question, data rule, statistics, random streams, validation design and reporting.
- [Stability triangle](proof/triangle.pdf): one-page mathematical proof; [source](proof/triangle.md).
- [Methodological decisions](DECISIONS.md): adopted conventions and interpretation limits.
- [Research roadmap](MILESTONES.md): milestones and completion criteria.
- [Verification records](audit/): numerical checks, source review and build evidence.

## Reproduce the checks

Use Python **3.12.14** in an isolated environment. Install the exact dependency versions in `requirements.lock`, then run:

```text
python -m pip install -r requirements.lock
python -m pytest -q
python tools/verify_m1c2.py
```

The verification scripts use bundled sunspot data and artificial series. They do not download UK observations. The M0 script checks the specification and baseline; M1a checks the mathematical and estimator foundation; subsequent scripts check the assembled analysis components. Each evidence record identifies its scope and limits.

The original design document is identified by SHA-256 `85a594b0baf6d7b5a72d3ca1ec856f0df06b1106aaf3319e48f5b3967854dde7`. It is not distributed here. Verification distinguishes an available matching source from a clone in which that document is unavailable.
