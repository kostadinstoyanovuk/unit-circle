"""The Schur-Cohn recursion for complex polynomials (plan section 14, Figure 4).

Coefficients are ascending: coefficient k multiplies z**k. A polynomial is
stable when every root lies strictly inside the unit disc. Comparisons are
exact floating-point comparisons with no tolerance (D-019).
"""
from __future__ import annotations

import numpy as np


def _coefficients(coefficients) -> np.ndarray:
    array = np.asarray(coefficients, dtype=complex)
    if array.ndim != 1 or array.size == 0 or not np.isfinite(array).all():
        raise ValueError('Expected a non-empty one-dimensional finite coefficient vector')
    return array


def conjugate_reciprocal(coefficients, degree: int | None = None) -> np.ndarray:
    """p*(z) = z**n conj(p(1/conj z)) at the given formal degree n (default: the vector's length - 1)."""
    a = _coefficients(coefficients)
    n = len(a) - 1 if degree is None else int(degree)
    if n < len(a) - 1:
        raise ValueError('Formal degree is below the coefficient vector length')
    padded = np.zeros(n + 1, dtype=complex)
    padded[:len(a)] = a
    return np.conj(padded[::-1])


def schur_transform(coefficients) -> np.ndarray:
    """q with z q(z) = conj(a_n) p(z) - a_0 p*(z); degree n-1, leading coefficient |a_n|^2 - |a_0|^2."""
    a = _coefficients(coefficients)
    if len(a) < 2 or a[-1] == 0:
        raise ValueError('Degree at least one with a non-zero leading coefficient is required')
    combined = np.conj(a[-1]) * a - a[0] * conjugate_reciprocal(a)
    return combined[1:]


def schur_cohn_stable(coefficients) -> bool:
    """True when every root of the polynomial lies strictly inside the unit disc."""
    a = _coefficients(coefficients)
    if a[-1] == 0:
        raise ValueError('Leading coefficient must be non-zero')
    while len(a) > 1:
        if not abs(a[0]) < abs(a[-1]):
            return False
        a = schur_transform(a)
    return True


def roots_stable(coefficients) -> tuple[bool, float]:
    """Reference classification from numpy.roots, with the smallest distance of a root to the circle."""
    a = _coefficients(coefficients)
    roots = np.roots(a[::-1])
    moduli = np.abs(roots)
    return bool((moduli < 1).all()), float(np.min(np.abs(moduli - 1))) if moduli.size else float('inf')


def at8(count_per_degree: int = 20_000, degrees=range(1, 9), seed=(1927, 2008), margin: float = 1e-7) -> dict:
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(list(seed))))
    rows = []
    for degree in degrees:
        compared = skipped = mismatches = stable = 0
        for _ in range(count_per_degree):
            coefficients = rng.standard_normal(degree + 1) + 1j * rng.standard_normal(degree + 1)
            truth, distance = roots_stable(coefficients)
            if distance < margin:
                skipped += 1
                continue
            compared += 1
            stable += truth
            mismatches += schur_cohn_stable(coefficients) != truth
        rows.append(dict(degree=degree, drawn=count_per_degree, compared=compared, skipped=skipped,
                         stable=stable, mismatches=mismatches))
    total = {key: sum(row[key] for row in rows) for key in ('drawn', 'compared', 'skipped', 'stable', 'mismatches')}
    return dict(by_degree=rows, total=total, passed=total['mismatches'] == 0 and total['compared'] >= 100_000)
