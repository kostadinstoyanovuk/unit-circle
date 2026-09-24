# C4 formal feasibility and source audit

Audit date: 2026-09-24. Milestone: M0, preparatory work only. Original specification: Unit_Circle_Programme_Plan.pdf, pp. 15–17, SHA-256 `85a594b0baf6d7b5a72d3ca1ec856f0df06b1106aaf3319e48f5b3967854dde7`.

## Assessment and evidence boundary

The complex Schur–Cohn proof on p. 15 is a credible basis for independent Lean development. Inspection found no fatal defect in the displayed algebra or the two implication arguments. This is mathematical review, not machine verification. The nonzero constant case, strict coefficient inequality and fixed reflection degree must remain explicit.

M0 verified primary source code and documentation. It did not install Lean, compile any project, check an axiom closure, contact third parties or prove a new theorem. Neither G6 nor G7 is passed. The PDF's simulation reports are not formal evidence. Source URLs, retrieval timestamps and SHA-256 hashes are recorded in `FORMAL_SOURCES.json`.

The default proposed route is an independently written proof of the supplied algebraic argument, with attribution and a precise comparison to Kamaguchi. No claim of novelty or permission to copy his implementation is established by this audit.

## Kamaguchi repository: verified comparison

The repository is [S-Kamaguchi/ar456-stationarity-lean](https://github.com/S-Kamaguchi/ar456-stationarity-lean). GitHub's primary API reports creation at `2026-09-20T03:30:12Z`, consistent with the plan's upload date. The inspected main-branch commit is [`da3605efdc3728e87f90284535083a4f1d588ce3`](https://github.com/S-Kamaguchi/ar456-stationarity-lean/commit/da3605efdc3728e87f90284535083a4f1d588ce3), dated 20 September. The API returned six commits; the initial uploaded files are in `415e789f649cfc0d0f994325541ffcfad41f072d`. These dates describe the inspected repository history.

The entire `StepDown.lean` and `AR2.lean` files were read. At the inspected commit:

| Item | Finding | Primary source |
|---|---|---|
| General theorem | `StTopology.isStationary_iff_stepDown_gen`, lines 433–444. Its parameter is `φ : Fin (n + 1) → ℝ` with `0 < n`: the equivalence covers degree at least two. | [StepDown.lean](https://github.com/S-Kamaguchi/ar456-stationarity-lean/blob/da3605efdc3728e87f90284535083a4f1d588ce3/StTopology/StepDown.lean#L433) |
| Step-down map | `phiDownGen`, lines 64–65, agrees with the plan after converting zero-based `Fin` indices to its one-based coefficients. | [Definition](https://github.com/S-Kamaguchi/ar456-stationarity-lean/blob/da3605efdc3728e87f90284535083a4f1d588ce3/StTopology/StepDown.lean#L64) |
| Meaning of stationarity | `IsStationary`, lines 75–76, universally quantifies complex roots of the displayed characteristic equation and requires norm below one. There is no stochastic process or probability space in this definition. | [StationarityRegions.lean](https://github.com/S-Kamaguchi/ar456-stationarity-lean/blob/da3605efdc3728e87f90284535083a4f1d588ce3/StTopology/StationarityRegions.lean#L75) |
| Proof method | Step-down and step-up use continuous coefficient paths and `isStationary_of_path_no_unit_root`; the step-down direction also uses openness. This supports the plan's topological-method comparison. | [Step-down path](https://github.com/S-Kamaguchi/ar456-stationarity-lean/blob/da3605efdc3728e87f90284535083a4f1d588ce3/StTopology/StepDown.lean#L227), [step-up](https://github.com/S-Kamaguchi/ar456-stationarity-lean/blob/da3605efdc3728e87f90284535083a4f1d588ce3/StTopology/StepDown.lean#L416) |
| AR(2) | Both `St2.isStationary` and `St2.of_isStationary` occur. The file's opening comment still calls necessity future work; the declarations supersede that stale comment. | [AR2.lean](https://github.com/S-Kamaguchi/ar456-stationarity-lean/blob/da3605efdc3728e87f90284535083a4f1d588ce3/StTopology/AR2.lean) |
| Build evidence | Upstream CI reports success for the inspected commit. Its workflow runs Lean Action and documentation generation. This is external build evidence, not our own fresh build or axiom audit. | [CI run](https://github.com/S-Kamaguchi/ar456-stationarity-lean/actions/runs/35505775626) |
| Versions | Lean `v4.32.2`; mathlib tag `v4.32.2`, resolved in the manifest to `905b95818eb32af7874a58b427f50c1711a5e96c`. | [Toolchain](https://github.com/S-Kamaguchi/ar456-stationarity-lean/blob/da3605efdc3728e87f90284535083a4f1d588ce3/lean-toolchain), [manifest](https://github.com/S-Kamaguchi/ar456-stationarity-lean/blob/da3605efdc3728e87f90284535083a4f1d588ce3/lake-manifest.json) |

GitHub reports `license: null`; the complete, non-truncated file tree contains no license-named file. The inspected Lean files have no license header. The README requests citation of the paper but does not provide code-reuse terms. Therefore copying or redistributing upstream implementation is postponed pending clear terms. Independent proof development and attributed mathematical comparison remain the proposed default; no legal conclusion beyond the observed metadata is claimed. The repository issue list returned no entries. Maintainer intentions, permission, upstream plans and coordination responses remain unverified.

## Current mathlib and Lean: what the APIs support

The inspected mathlib main-branch commit is [`045acef0f761280401116e3801cb78ed1b2e716b`](https://github.com/leanprover-community/mathlib4/commit/045acef0f761280401116e3801cb78ed1b2e716b), dated `2026-09-23T23:41:41Z`; its toolchain is `v4.35.0-rc2`. This differs from Kamaguchi's pinned environment. Neither version is silently selected for the future project: choose and pin a release-compatible environment at the formal milestone, then run the API probe there. Online documentation can advance independently.

- [Reverse.lean](https://github.com/leanprover-community/mathlib4/blob/045acef0f761280401116e3801cb78ed1b2e716b/Mathlib/Algebra/Polynomial/Reverse.lean) contains `reflect`, `coeff_reflect`, `reflect_reflect`, `reflect_map`, `reflect_mul` and evaluation lemmas. The PDF's fixed-degree approach is supported. Important detail: `reflect n` leaves exponents above `n` unchanged, so impose the degree bound wherever the intended reciprocal interpretation requires it. `reverse` reflects at the current natural degree and can lose leading zeros on reversal. Retain the given formal degree across conjugation and cancellation.
- [Inductions.lean](https://github.com/leanprover-community/mathlib4/blob/045acef0f761280401116e3801cb78ed1b2e716b/Mathlib/Algebra/Polynomial/Inductions.lean) supplies `divX`, its coefficient shift, `X_mul_divX_add` and a natural-degree subtraction lemma. These support the Schur transform without general polynomial division.
- [Splits.lean](https://github.com/leanprover-community/mathlib4/blob/045acef0f761280401116e3801cb78ed1b2e716b/Mathlib/Algebra/Polynomial/Splits.lean) provides factorisation and root-count APIs. [Complex polynomial basics](https://github.com/leanprover-community/mathlib4/blob/045acef0f761280401116e3801cb78ed1b2e716b/Mathlib/Analysis/Complex/Polynomial/Basic.lean) provides complex algebraic closedness. The current proof of complex root existence uses Liouville's theorem. Thus “algebraic proof” should mean the Schur argument is algebraic once complex factorisation is available, as the PDF explicitly permits; it cannot mean every transitive library dependency avoids analysis.
- `Polynomial.mirror` preserves degree but is a different operation; it is not a substitute for the specified reciprocal. See [Mirror.lean](https://github.com/leanprover-community/mathlib4/blob/045acef0f761280401116e3801cb78ed1b2e716b/Mathlib/Algebra/Polynomial/Mirror.lean).

The full mathlib filename tree was searched for Schur, Cohn, Jury, Hurwitz and Rouche. It returned unrelated Schur and Hurwitz files and no obvious criterion-named file. A filename search cannot establish theorem absence or originality. The PDF's broad negative prior-art statements remain unverified, and must not become a novelty claim without declaration-level and external literature checks.

[Lean's validation manual](https://lean-lang.org/doc/reference/latest/ValidatingProofs/) supports the intended kernel-only boundary. The axiom mechanism for native evaluation changes by version; use an allowlist of acceptable axioms rather than reject only one historical axiom name. Audit the main theorem, recurrence equivalence, every exported corollary, cast bridge and computed example. Allowed axioms are a subset of `propext`, `Classical.choice` and `Quot.sound`; needing fewer is fine. A text search for `sorry` is useful but cannot replace that audit. The manual describes possible reduction failures for well-founded recursion, not an absolute impossibility. Keep the PDF's conservative structurally recursive executable design. A shorter transformed list is not syntactically the original tail, so a natural-number fuel argument or equivalent structurally recursive architecture may be needed. This is a design detail to specify and prove, not a reason to switch to native evaluation.

## Proof scope and the stationarity bridge

Preserve the core C4 deliverable: complex-coefficient polynomial stability; fixed-degree conjugate reciprocal; Lemmas A–C; the Schur step; exact recursive testing on Gaussian rationals; the four stated corollaries; and an attributed real-coefficient compatibility theorem. The norm inequalities must include the zero constant coefficient, nonzero constant base case, repeated roots, equality on the circle, and degree-one reduction. The rounded sunspot example certifies its exact rational polynomial, not the unrounded fitted parameters or a physical property of the Sun.

For p. 17, propose two explicitly separated bridge statements:

1. **Required polynomial bridge:** define the monic characteristic polynomial and prove equivalence between its stability and Kamaguchi's root predicate, then recover the displayed step-down relation with correct indices and assumptions. This preserves the stated corollary without importing a probability theory project.
2. **Optional stochastic bridge:** if a theorem about random processes is intended, first specify a two-sided time index, finite-variance nondegenerate innovations, the precise innovation/causality assumptions, weak versus strict stationarity, and the existence/uniqueness sense. A causal weakly stationary solution theorem is a reasonable separately scoped target. Do not assert that unrestricted stationary solutions satisfy the same inside-root condition: noncausal AR solutions are a counterexample class. [Berkeley's causal AR(1) lecture](https://www.stat.berkeley.edu/~bartlett/courses/153-fall2010/lectures/5.pdf) documents the distinction.

Treat the second item as an unresolved scope choice, not an adopted deletion or expansion. A root-predicate compatibility theorem must never be presented as a formal stochastic existence proof.

## First bounded formal milestone and gates

**M5a: exact blueprint before code.** Produce the full statement/dependency graph from pp. 15–17, hypotheses for zero/degree cases, the executable representation contract and a declaration-level prior-art search log. Separate reusable mathlib facts from independent work and the attributed comparison. The original G6 also requires recorded external answers: it remains open until those answers exist or an explicit documented gate revision is adopted.

**M5b: first compiled feasibility slice, after G6 is satisfied or explicitly revised.** In the separate `schur-cohn` project, pin the environment, define stability and the fixed-degree reciprocal, prove its coefficient and involution laws, prove Lemma A using squared norms, and verify the `divX` cancellation identity. Include explicit constant/zero and degree-one examples. Capture build output and the axiom list for each completed declaration. Any incomplete proof obligation remains explicit; a weakened theorem cannot substitute for the intended result.

The next stage covers factorisation and the exterior norm inequality (Lemma B), the largest early integration risk. Its build evidence should inform the remaining formalisation schedule.

External acceptance is separate from technical completion. Independent source, proof statements, build records, the rational checker and contribution drafts require technical verification. Maintainer responses, acceptance and journal decisions require separate evidence. Preserve the PDF's checked-repository fallback for upstream rejection while recording G6's distinct coordination requirement.

## Unresolved items carried forward

- Fresh local rebuild and axiom audit of the upstream comparison, if it is to be relied upon as independently verified evidence.
- Code reuse terms; default remains independent implementation with attribution.
- Current declaration-level prior-art review across formal proof systems; no novelty claim yet.
- Selected Lean/mathlib pin and compiled compatibility of all cited names.
- Exact intended stochastic bridge scope.
- G6 coordination evidence or an explicitly adopted gate revision.

No original gate or acceptance test is marked passed by this report.
