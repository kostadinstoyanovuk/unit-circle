# M1 local infrastructure evidence

Prepared 2026-09-24. This preserves local preparation evidence for G0.
Publication and hosted-check results are recorded separately in
`GITHUB_PUBLICATION.json`. **G0 passed on 2026-09-25 with the current public repositories
and successful hosted checks.** Local builds do not establish hosted success.

## Separate Python package

`../unitcircle` is a separate Git repository with a `src/` layout, pinned
setuptools `84.0.0`, pip `25.0.1`, and a Python `3.12.14` workflow. Its development
version is `0.0.1.dev0`; it is not v1.0 and does not extract the research pipeline.
The sole API computes the companion roots of `z^2 - phi1*z - phi2`. A wheel was
built and installed in its own isolated environment; three installed-package
tests passed, including `roots(0.3, 0.1)` approximately `(0.5, -0.2)`, its polynomial
residuals, complex/zero examples and rejection of non-finite input. Logs and exact
commands are in `../unitcircle/evidence/`. Current public commits are recorded in `GITHUB_PUBLICATION.json`.

The cancellation-resistant real-root calculation shares the research prototype's
convention; this small infrastructure API does not replace the future M6
extraction and cross-validation of frozen research code. A licence has not yet
been selected.

## Separate Lean project

`../schur-cohn` contains independent arithmetic/polynomial setup examples, pinned
Lean `v4.32.2` and mathlib `905b95818eb32af7874a58b427f50c1711a5e96c`. The official
release metadata and mathlib's toolchain file were freshly retrieved and saved.
The 832,110,051-byte portable Windows archive's SHA-256 was verified against the
official release API before extraction and execution:
`369c2b480a2a6f8bfb727af42c333c894c4872a73b3503099abad7bef67549fa`.
`lean --version` reports release `4.32.2`, commit
`f3b06c705e6c85f5314019d5d3baab0fec5b580c`; Lake reports `5.0.0-src+f3b06c7`.

`lake update` succeeded, resolving the audited mathlib commit and recording all
transitive pins in `lake-manifest.json`. The initial selective-cache attempt built
the cache tool but failed because its `lean --print-prefix` subprocess could not
find Lean on PATH. The build script resolves the portable toolchain directory
through its process PATH and restores the prior value afterward.
Only `Mathlib.Algebra.Polynomial.Eval.Defs` and its dependency closure are requested,
with automatic full-cache download disabled. The second attempt downloaded and
decompressed all 1,166 requested cache files. `lake build` then completed
successfully (1,184 total jobs, including cached dependencies). The polynomial
example's axiom closure is `[propext, Classical.choice, Quot.sound]`; the arithmetic
example depends on no axioms. `evidence/lake-build.log` preserves both outputs.
The Lean checkpoint and evidence hashes are recorded in the accompanying JSON.

The examples do not define stability, a reciprocal polynomial, or any new
programme theorem. G6 and G7 remain open regardless of these setup results. No
comparison-repository implementation was copied.

## CI and reproducibility boundary

Both new repositories contain real GitHub Actions recipes: package installation
and tests, and selective mathlib cache followed by `lake build`. Action commits
were resolved from official repository metadata and pinned. These are local
workflow definitions; hosted execution is recorded separately in
`GITHUB_PUBLICATION.json`. See the JSON for the local checkpoint state, source records and
evidence hashes. Lean setup can be resumed with `../schur-cohn/tools/smoke.ps1`;
the verified portable installer is `tools/install-lean.ps1` in that repository.

The published evidence uses normalized line endings and replaces local workstation
paths with `<workspace>`. Build outcomes, toolchain identifiers and download digests
are preserved. `evidence_sha256` in the JSON identifies the distributed files;
these hashes can be checked directly in a clone.
