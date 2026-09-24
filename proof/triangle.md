# The real AR(2) stability triangle

Unit Circle Programme | Mathematical foundations | 24 September 2026

This note establishes the real AR(2) stability criterion by an elementary proof and a Schur-step crosscheck, following the programme's S0.1 specification. Formal verification in Lean remains a separate programme deliverable.

Let

\[
p(z)=z^2-\phi_1z-\phi_2,\qquad \phi_1,\phi_2\in\mathbb R.
\]

Here **stable** means that both complex roots, counted with multiplicity, have modulus strictly below one. This concerns the displayed characteristic polynomial; a stochastic-process stationarity theorem requires additional assumptions.

**Theorem.** The polynomial is stable if and only if

\[
\boxed{\quad \phi_1+\phi_2<1,\qquad
\phi_2-\phi_1<1,\qquad \phi_2>-1.\quad}
\tag{T}
\]

These inequalities describe the open triangle with vertices \((-2,-1)\), \((2,-1)\) and \((0,1)\) in the \((\phi_1,\phi_2)\)-plane.

## Elementary proof in both directions

Write the roots as \(r,s\). The quadratic formula guarantees their existence, and factorisation gives

\[
r+s=\phi_1,\qquad rs=-\phi_2,\qquad
p(1)=1-\phi_1-\phi_2,\qquad
p(-1)=1+\phi_1-\phi_2.
\tag{1}
\]

Thus (T) is exactly \(p(1)>0\), \(p(-1)>0\), \(rs<1\).

**Necessity.** Suppose \(|r|,|s|<1\). If both roots are real, they belong to \((-1,1)\), so

\[
p(1)=(1-r)(1-s)>0,\qquad
p(-1)=(1+r)(1+s)>0,
\]

and \(rs\leq |r||s|<1\). If a root is nonreal, the real coefficients imply \(s=\overline r\). Consequently

\[
p(1)=|1-r|^2>0,\qquad
p(-1)=|1+r|^2>0,\qquad
rs=|r|^2<1.
\]

In either case (1) yields all three inequalities in (T).

**Sufficiency.** Suppose (T) holds. If the roots are nonreal, they are a conjugate pair, hence

\[
|r|^2=|s|^2=rs=-\phi_2<1,
\]

which proves stability. Otherwise order the real roots as \(r\leq s\). If \(s\geq1\), then \(p(1)>0\) rules out \(s=1\). Since \(1-s<0\), the identity \((1-r)(1-s)=p(1)>0\) forces \(r>1\). This implies \(rs>1\), contradicting \(rs=-\phi_2<1\). Therefore \(s<1\).

Similarly, if \(r\leq-1\), positivity of \(p(-1)\) rules out equality, and \((1+r)(1+s)>0\) forces \(s<-1\). Again \(rs>1\), a contradiction. Thus \(-1<r\leq s<1\), proving stability. No step requires the roots to be distinct. \(\square\)

## Schur-step crosscheck

The programme's general Schur theorem states that a positive-degree polynomial with leading coefficient \(a_n\), constant coefficient \(a_0\) and conjugate reciprocal \(p^*\) is stable exactly when \(|a_0|<|a_n|\) and its transform \(zq=\overline{a_n}p-a_0p^*\) is stable. Applying it here provides a second route to the same inequalities; the elementary proof above does not rely on that theorem.

At fixed formal degree two,

\[
p^*(z)=1-\phi_1z-\phi_2z^2,
\]

so

\[
zq(z)=p(z)+\phi_2p^*(z)
=(1-\phi_2^2)z^2-\phi_1(1+\phi_2)z.
\]

The first check is \(|\phi_2|<1\). Under that strict condition, \(1\pm\phi_2>0\) and the linear polynomial \(q\) has the single root

\[
\frac{\phi_1(1+\phi_2)}{1-\phi_2^2}
=\frac{\phi_1}{1-\phi_2}.
\]

The second check is therefore \(|\phi_1|<1-\phi_2\). Equivalently, the two checks require \(-1<\phi_2<1\) and the first two inequalities in (T). Conversely, those two inequalities add to \(2\phi_2<2\), so (T) already implies \(\phi_2<1\). Hence the checks and (T) are equivalent.

## Degeneracies and excluded boundary

- **Repeated roots:** when \(\phi_1^2+4\phi_2=0\), the repeated root is \(\phi_1/2\). It is stable exactly when \(|\phi_1|<2\), consistently with (T). Repetition inside the disc is allowed.
- **Zero constant coefficient:** when \(\phi_2=0\), \(p(z)=z(z-\phi_1)\); stability is exactly \(|\phi_1|<1\). At \(\phi_1=\phi_2=0\), zero is a stable double root. If instead \(\phi_1=0\), both roots have modulus \(\sqrt{|\phi_2|}\), so stability is exactly \(|\phi_2|<1\).
- **Upper sloping edges:** \(\phi_1+\phi_2=1\) gives a root at \(1\); \(\phi_2-\phi_1=1\) gives a root at \(-1\).
- **Lower edge:** at \(\phi_2=-1\), \(-2\leq\phi_1\leq2\), the polynomial is \(z^2-\phi_1z+1\). Its roots are a conjugate pair of modulus one, or a repeated root at \(1\) or \(-1\) at an endpoint. Thus every point on the triangle boundary fails strict stability. The Schur cancellation above was used only for \(|\phi_2|<1\); it makes no division at these excluded endpoints.
