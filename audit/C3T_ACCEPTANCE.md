# Paper II theory (C3.T): acceptance record

Recorded 28 September 2026. This record covers plan work package C3.T (p. 14), items (a)–(e), each typed with its proof and checked numerically, and acceptance tests AT-9, AT-17 and AT-18 (Appendix A, p. 21). Decision: [D-029](../DECISIONS.md).

## Evidence

Two implementations that share no code:

| | What it is | Record (SHA-256) |
|---|---|---|
| A | The typed derivation of items (a)–(e), with proofs, and its own symbolic checks and Monte Carlo cells | derivation source `53c4e88e9894654b5d8db211acb943756bfb34fd973d4b99504a2c6d30e0465a`; PDF `783cafaf5f46fc5c617a52ccf6e093454cba9c79c60dae98f4281ef636ece1a3`; results `371edcfa0443b7ef87d407ad9679496809b92bd35a8033a1971d3a203f91d52a` |
| B | An independent review: exact symbolic re-derivation of every item, a comparison with each formula and number stated in A, and Monte Carlo checks with its own generators and seeds | results `5fe198d941576ba2a0a5f28247b3d37768819cab6d0c98e8a2b3ebb9e9853676` |

Reproduction:
- B re-ran A's complete check suite: 3,970 values, no difference outside timing fields.
- B's complete suite was re-run on 28 September 2026 on a different machine (2 CPUs; Python 3.11.15, NumPy 2.4.6, SciPy 1.17.1, SymPy 1.14.0, mpmath 1.3.0). All seven output files reproduced: 2,179 values, no difference outside timing fields.

The typed derivation and both check suites are kept in the programme's working records. They will be published with the Paper II materials.

## Results

**Exact checks.** B's exact derivations pass 28 of 28. All 29 of A's typed formulas and numbers that B tested agree with B's derivations.

**(a) Asymptotic covariance; AT-9.** B derives σ²Γ⁻¹ from the Yule–Walker equations and finds it equal to the plan's Σ. AT-9 compares n·Cov(φ̂) with Σ at φ = (0.5, −0.3), (1.3, −0.65) and (0.2, 0.5), with n = 3,000 and 1,500 runs. Each entry must lie within three Monte Carlo standard errors.
- A: 9 of 9 entries pass; largest |z| 1.59.
- B: 9 of 9 entries pass; largest |z| 2.03.

**(b) Delta method for D; AT-17.** σ_D² = 4(1 + φ2)[4(1 − φ2) − φ1²(3 + φ2)]. On the boundary φ2 = −φ1²/4 it becomes (4 − φ1²)³/4. AT-17 checks n·Var(D̂) on the boundary against 16.000, 9.483 and 2.122 at φ1 = 0, 0.8 and 1.4, with n = 4,000 and 1,500 runs.
- A: 3 of 3 pass; largest |z| 1.34.
- B: 3 of 3 pass, with 15.862, 9.880 and 2.097; largest |z| 1.15.

**(c) Bias to order 1/n; AT-18.** For least squares with an intercept, n·bias = (−(1 + φ1 + φ2), −(2 + 4φ2)). A transcribed this from Shaman and Stine (1988), and B derived it independently. AT-18 targets white noise with an intercept: n E φ̂1 ≈ −1 and n E φ̂2 ≈ −2. The target is a limit and names no sample size.
- A: 6 of 6 cells pass; largest |z| 1.81.
- B at n = 250: −1.012 ± 0.016 and −2.017 ± 0.016 (pass).
- B at n = 400: n E φ̂1 = −1.0125 ± 0.020 (pass).
- B at n = 1,000, four independent cells of 10⁶ to 2 × 10⁶ runs: each passes. The pooled value for φ1 is −0.994 ± 0.013.
- B at n = 100: n E φ̂1 = −1.044 ± 0.010 (z = −4.32) and n E φ̂2 = −2.026 ± 0.010 (z = −2.56). The φ1 departure is the next-order term: a fit of b + c/n over all of B's cells gives b = −0.991 ± 0.012 for φ1 (c = −5.4 ± 1.7) and b = −2.005 ± 0.012 for φ2.
- AT-18 is therefore recorded as holding for n ≥ 250.

**(d) The coin flip.** At φ = 0, both implementations confirm n E D̂ → −7 and n Var D̂ → 16. Evaluated exactly, Φ(7/(4√n)) is 0.6253 at n = 30 and 0.5221 at n = 1,000. The plan's simulated 0.630 and 0.520 were not re-simulated here, and no classification probability was simulated in either implementation.

**(e) The C_S analogue.** The following are derived and checked:
- σ_G² = (1 − φ2²)[(1 − φ2)² + (4 − a)(4 − 3a)] with a = |φ1|, which is even in φ1, and its boundary values;
- the bias of Ĝ, with its mirror differences;
- the non-normal limit on the line φ1 = 0;
- the kink probability 1/2 − arctan(1/4)/π = 0.422020869623, by exact integration in B.

A's cells for σ_G², the bias of Ĝ and the kink moments pass (8/8, 8/8, 6/6 and 2/2).

## Qualifications

- **Supplementary fixed-n comparisons.** 21 of A's supplementary fixed-n comparisons fail: 20 compare the Yule–Walker bias approximation at n = 250 and 1,000, and one compares the bias of D̂ at n = 200. A traces the Yule–Walker failures, reported at |φ1| = 1.6, by extrapolation to finite-n terms. These comparisons are not acceptance tests, and the registered Paper II design corrects least squares only (D-024, R3).
- **Heterogeneous n = 1,000 cells.** B's four n = 1,000 cells for φ1 are heterogeneous: χ² = 13.2 on 3 df (p ≈ 0.004). The cell that prompted B's declared follow-ups drives this; among the three follow-up replicates alone, χ² = 5.9 on 2 df. B's code checks exclude a simulation or estimator error, and no other cause was found.
- **Finite-n understatement of σ_D.** B finds σ_D understated by 1.1–1.8% at |φ1| = 1.6 with n = 1,000. This is a finite-n effect, noted as a design input for the Paper II simulation. No registered design was changed.
- **Standard results cited, not re-derived.** A labels standard results it cites without re-deriving them, and B did not verify those citations.
