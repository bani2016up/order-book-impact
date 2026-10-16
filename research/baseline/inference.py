"""Small-sample robust inference for the baseline OLS fits.

HC0 standard errors (the paper's White errors) over-reject when a window holds only ~180
buckets and a regressor such as OFI*|OFI| is dominated by a few high-leverage points. The
functions here give HC3 statistics and a wild bootstrap-t p-value, which are far less
liberal in that situation. They are checked against statsmodels in ``tests/research``.
"""

import zlib

import numpy as np

# An observation with leverage this close to one fits itself exactly: its HC3 weight
# 1 / (1 - h) divides one rounding error by another, so the statistic is meaningless.
LEVERAGE_LIMIT = 1.0 - 1e-8


def leverage_values(design: np.ndarray) -> np.ndarray:
    """Diagonal of the hat matrix of ``design`` (n x k)."""
    design = np.asarray(design, dtype=float)
    inverse = np.linalg.inv(design.T @ design)
    return np.einsum("ij,jk,ik->i", design, inverse, design)


def _hc3_t(
    design: np.ndarray,
    inverse: np.ndarray,
    leverage: np.ndarray,
    responses: np.ndarray,
    column: int,
) -> np.ndarray:
    """HC3 t-statistics of one coefficient for every row of ``responses`` (draws x n)."""
    # A point of leverage one makes the statistic undefined (NaN/inf), which callers handle.
    # NumPy on macOS also raises spurious floating-point warnings from matmul, so all are
    # silenced here; the result is checked against statsmodels in the tests.
    with np.errstate(all="ignore"):
        coefficients = responses @ design @ inverse
        residuals = responses - coefficients @ design.T
        loadings = design @ inverse[:, column]
        variance = ((residuals / (1.0 - leverage)) ** 2) @ loadings**2
        return coefficients[:, column] / np.sqrt(variance)


def bootstrap_entropy(seed: int, *labels: object) -> list[int]:
    """Stable seed material for one test: the base seed plus a checksum of its labels.

    The checksum depends only on the labels, so adding windows or models does not change
    the draws of the others.
    """
    return [seed, zlib.crc32("|".join(str(label) for label in labels).encode())]


def wild_bootstrap_p_values(
    design: np.ndarray, response: np.ndarray, draws: int, entropy: list[int]
) -> np.ndarray:
    """Two-sided wild bootstrap-t p-value of every coefficient (null imposed, HC3 t).

    For coefficient ``j`` the response is refit without column ``j`` (so the null is true),
    its residuals are multiplied by Rademacher weights, and the HC3 t-statistic of ``j`` is
    recomputed on each simulated response. The p-value is ``(1 + #{|t*| >= |t|}) / (1 + B)``
    over draws with a finite statistic. The weights are shared across coefficients. Every
    p-value is NaN when some observation has leverage of one (see ``LEVERAGE_LIMIT``).
    """
    design = np.asarray(design, dtype=float)
    response = np.asarray(response, dtype=float)
    if type(draws) is not int or draws < 1:
        raise ValueError("draws must be a positive integer")
    n, k = design.shape
    p_values = np.full(k, np.nan)
    leverage = leverage_values(design)
    if leverage.max() >= LEVERAGE_LIMIT:
        return p_values
    inverse = np.linalg.inv(design.T @ design)
    weights = np.random.default_rng(entropy).choice([-1.0, 1.0], size=(draws, n))
    for column in range(k):
        observed = _hc3_t(design, inverse, leverage, response[None, :], column)[0]
        if not np.isfinite(observed):
            continue
        restricted = np.delete(design, column, axis=1)
        fitted = restricted @ np.linalg.lstsq(restricted, response, rcond=None)[0]
        simulated = _hc3_t(
            design, inverse, leverage, fitted + weights * (response - fitted), column
        )
        finite = np.isfinite(simulated)
        extreme = int(np.count_nonzero(np.abs(simulated[finite]) >= abs(observed)))
        p_values[column] = (1 + extreme) / (1 + int(np.count_nonzero(finite)))
    return p_values
