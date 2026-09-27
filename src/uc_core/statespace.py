"""Linear Gaussian state space for univariate observations (foundations F2, D-019).

Observation  y_t = z_t' a_t + e_t,  e_t ~ N(0, H)
Transition   a_{t+1} = T a_t + w_t,  w_t ~ N(0, Q)

Version 2 (27 September 2026) propagates a square-root factor S of the state
covariance (P = S S') with orthogonal array updates. Version 1 used the Joseph
form P = (I - K z') P (I - K z')' + H K K'; with the diffuse prior P0 = 1e8 I its
rounding error reached 5.5e-6 in AT-11, above the 1e-6 target (D-019,
audit/FOUNDATIONS_REPORT.md). The log-likelihood is the prediction-error
decomposition over observations from index `burn` onwards.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy.optimize import minimize

from .ar import fit_ols


@dataclass(frozen=True)
class FilterResult:
    filtered_states: np.ndarray
    prediction_errors: np.ndarray
    prediction_variances: np.ndarray
    loglik: float


def _factor(matrix) -> np.ndarray:
    """A square-root factor of a symmetric positive semidefinite matrix."""
    matrix = np.atleast_2d(np.asarray(matrix, dtype=float))
    values, vectors = np.linalg.eigh((matrix + matrix.T) / 2)
    if values.min(initial=0.0) < -1e-12 * max(1.0, abs(values).max(initial=0.0)):
        raise ValueError('Covariance must be positive semidefinite')
    return vectors * np.sqrt(np.clip(values, 0, None))


def kalman_filter(y, Z, T, Q, H, a1, P1, *, burn: int = 0) -> FilterResult:
    y = np.asarray(y, dtype=float)
    Z = np.asarray(Z, dtype=float)
    if Z.ndim == 1:
        Z = Z[:, None]
    n, m = Z.shape
    if y.shape != (n,) or not np.isfinite(y).all() or not np.isfinite(Z).all():
        raise ValueError('Observations and loadings must be finite with matching length')
    H = float(H)
    if not H > 0:
        raise ValueError('Observation variance must be positive')
    T = np.atleast_2d(np.asarray(T, dtype=float))
    root_Q = _factor(Q)
    a = np.asarray(a1, dtype=float).reshape(m)
    S = _factor(P1)
    states = np.empty((n, m))
    errors, variances = np.empty(n), np.empty(n)
    loglik = 0.0
    for t in range(n):
        z = Z[t]
        v = y[t] - z @ a
        # Measurement update: lower-triangularise [[sqrt(H), z'S], [0, S]] by an orthogonal transformation.
        pre = np.zeros((m + 1, m + 1))
        pre[0, 0] = math.sqrt(H)
        pre[0, 1:] = z @ S
        pre[1:, 1:] = S
        post = np.linalg.qr(pre.T, mode='r').T
        if post[0, 0] < 0:
            post[:, 0] = -post[:, 0]
        root_F = post[0, 0]
        F = root_F * root_F
        if not F > 0:
            raise FloatingPointError('Non-positive prediction variance')
        a = a + post[1:, 0] * (v / root_F)
        S = post[1:, 1:]
        states[t], errors[t], variances[t] = a, v, F
        if t >= burn:
            loglik -= 0.5 * (math.log(2 * math.pi) + math.log(F) + v * v / F)
        # Time update: P <- T P T' + Q through a factor of [T S, sqrt(Q)].
        a = T @ a
        stacked = np.hstack((T @ S, root_Q))
        S = np.linalg.qr(stacked.T, mode='r').T[:, :m] if stacked.shape[1] >= m else stacked
    return FilterResult(states, errors, variances, loglik)


def regression_at11(values, *, observation_variance: float = 1.0, prior_variance: float = 1e8) -> dict:
    """AT-11: zero state noise and diffuse start reproduce intercept-inclusive least squares."""
    x = np.asarray(values, dtype=float)
    Z = np.column_stack((np.ones(len(x) - 2), x[1:-1], x[:-2]))
    result = kalman_filter(x[2:], Z, np.eye(3), np.zeros((3, 3)), observation_variance,
                           np.zeros(3), prior_variance * np.eye(3))
    ols = fit_ols(x)
    target = np.array([ols.intercept, *ols.coefficients])
    final = result.filtered_states[-1]
    difference = float(np.max(np.abs(final - target)))
    return dict(final_state=final.tolist(), least_squares=target.tolist(),
                max_abs_difference=difference, observation_variance=observation_variance,
                prior_variance=prior_variance, passed=difference <= 1e-6)


def local_level_loglik(y, irregular: float, level: float, *, diffuse: float = 1e10) -> float:
    y = np.asarray(y, dtype=float)
    return kalman_filter(y, np.ones((len(y), 1)), [[1.0]], [[level]], irregular,
                         [0.0], [[diffuse]], burn=1).loglik


def local_level_mle(y) -> dict:
    y = np.asarray(y, dtype=float)
    start = np.log(np.full(2, np.var(np.diff(y)) / 2))

    def objective(log_variances):
        return -local_level_loglik(y, *np.exp(log_variances))

    result = minimize(objective, start, method='L-BFGS-B')
    irregular, level = np.exp(result.x)
    return dict(irregular=float(irregular), level=float(level), loglik=float(-result.fun),
                converged=bool(result.success), iterations=int(result.nit))
