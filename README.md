# Unit Circle Programme

Research on autoregressive persistence, recession-onset diagnostics and polynomial stability.

The programme combines a preregistered empirical study of UK recessions, reproducible statistical software and a formal treatment of stability criteria. Its first phase establishes the mathematical conventions, analysis methods and verification framework before confirmatory experiments and UK data analysis begin.

## Research status

M1 Foundations and Registration Preparation is complete. The methods are implemented, the H1 protocol is registered and all three repositories have passing hosted checks. The research suite contains 302 passing tests covering estimation, companion roots, rolling calculations, episode identification, surrogate comparisons, secondary analyses, validation-run recovery, reporting integrity, registration-timestamp evidence, the S1 sunspot comparison and Yule transcription, and the foundations checks for the Schur-Cohn recursion, spectral radius and Kalman filter. A one-page paper proof establishes the real AR(2) stability triangle. The [resumable validation runner](docs/VALIDATION_RUNNER.md) and [development reporting layer](docs/H1_REPORTING.md) have passed their development checks; official experiments remain gated.

The H1 registration was submitted on 25 September 2026 under **CC BY 4.0** and approved by the registry on 27 September; it is **public**: [OSF registration](https://doi.org/10.17605/OSF.IO/WCNBZ). All five archived attachments match the submitted bytes, the [registration timestamp](audit/H1_REGISTRATION_TIMESTAMP.md) is documented and the annotated `prereg-H1` tag identifies the registered protocol, so gate G1 has passed. No raw UK research series has been acquired or analysed, and the official size and power experiments have not run. Software checks establish implementation behaviour; they do not establish an empirical finding, statistical calibration or a completed formal theorem. Current milestone and gate evidence is recorded in [STATUS.md](STATUS.md); the [programme review](audit/PROGRAMME_REVIEW_2026-09-27.md) checks those claims against the original scope.

## Repositories

| Repository | Purpose |
|---|---|
| [unit-circle](https://github.com/kostadinstoyanovuk/unit-circle) | Research methods, protocol, mathematical notes and verification |
| [unitcircle](https://github.com/kostadinstoyanovuk/unitcircle) | Installable Python package in development |
| [schur-cohn](https://github.com/kostadinstoyanovuk/schur-cohn) | Pinned Lean and mathlib foundation for formalisation |

## Read the work

- [H1 protocol submitted to OSF](prereg/H1.md): research question, data rule, statistics, random streams, validation design and reporting. Its preparation-time status is preserved; the separate [registration record](audit/H1_REGISTRATION.json) tracks submission and verification.
- [Stability triangle](proof/triangle.pdf): one-page mathematical proof; [source](proof/triangle.md).
- [S1 sunspot fits](audit/S1_TABLE.md): Yule's AR(2) on SILSO Versions 1 and 2, with bootstrap bands and [figures](figures/); rebuilt by `make s1-figures`.
- [Yule (1927) transcription](audit/YULE1927_TRANSCRIPTION.md): his sample, equations and period, checked against his own printed arithmetic.
- [Foundations checks](audit/FOUNDATIONS_REPORT.md): AT-8, AT-11, AT-12, the local-level model and Lemma A in Lean, including a recorded correction.
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
