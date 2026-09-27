"""Companion matrices and spectral radius (foundations F4, D-019)."""
from __future__ import annotations

import numpy as np

from .ar import root_summary


def companion(coefficients) -> np.ndarray:
    """AR(p) companion matrix: first row phi_1..phi_p, identity below the diagonal."""
    phi = np.asarray(coefficients, dtype=float)
    if phi.ndim != 1 or phi.size == 0 or not np.isfinite(phi).all():
        raise ValueError('Expected a non-empty finite coefficient vector')
    p = phi.size
    matrix = np.zeros((p, p))
    matrix[0] = phi
    matrix[1:, :-1] = np.eye(p - 1)
    return matrix


def var_companion(matrices) -> np.ndarray:
    """VAR(p) companion matrix from coefficient matrices A_1..A_p (each k x k)."""
    blocks = [np.atleast_2d(np.asarray(matrix, dtype=float)) for matrix in matrices]
    k = blocks[0].shape[0]
    p = len(blocks)
    result = np.zeros((k * p, k * p))
    result[:k] = np.hstack(blocks)
    result[k:, :-k] = np.eye(k * (p - 1))
    return result


def spectral_radius(matrix) -> float:
    return float(np.max(np.abs(np.linalg.eigvals(np.atleast_2d(np.asarray(matrix, dtype=float))))))


def at12(draws: int = 100_000, seed: int = 1927, stream: int = 2012) -> dict:
    diagonal_rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, stream, 0])))
    ab = diagonal_rng.uniform(-2, 2, size=(draws, 2))
    diagonal_error = max(abs(spectral_radius(np.diag(row)) - np.max(np.abs(row))) for row in ab)
    ar_rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([seed, stream, 1])))
    phi = np.column_stack((ar_rng.uniform(-3, 3, draws), ar_rng.uniform(-2, 2, draws)))
    ar_error, skipped = 0.0, 0
    for phi1, phi2 in phi:
        if abs(phi1 * phi1 + 4 * phi2) < 1e-8:
            skipped += 1
            continue
        ar_error = max(ar_error, abs(spectral_radius(companion([phi1, phi2])) - root_summary([phi1, phi2]).modulus))
    return dict(diagonal=dict(draws=draws, max_abs_error=float(diagonal_error), passed=diagonal_error <= 1e-12),
                ar2=dict(draws=draws, skipped=skipped, max_abs_error=float(ar_error), passed=ar_error <= 1e-9),
                passed=diagonal_error <= 1e-12 and ar_error <= 1e-9)
