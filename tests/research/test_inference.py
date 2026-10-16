"""HC3 and wild bootstrap-t against statsmodels and against known-size simulations."""

import numpy as np
import pytest
import statsmodels.api as sm

from research.baseline.inference import _hc3_t, bootstrap_entropy, wild_bootstrap_p_values


def heavy_tailed_design(rng, n=60):
    x = rng.standard_t(3, n)
    return x, np.column_stack([np.ones(n), x, x * np.abs(x)])


def test_hc3_statistic_matches_statsmodels_for_every_coefficient():
    rng = np.random.default_rng(3)
    x, design = heavy_tailed_design(rng)
    response = 1 + 0.5 * x + rng.standard_normal(len(x)) * (0.5 + np.abs(x))
    inverse = np.linalg.inv(design.T @ design)
    leverage = np.einsum("ij,jk,ik->i", design, inverse, design)
    expected = sm.OLS(response, design).fit(cov_type="HC3", use_t=False).tvalues
    for column in range(3):
        mine = _hc3_t(design, inverse, leverage, response[None, :], column)[0]
        assert mine == pytest.approx(expected[column], rel=1e-9)
    stacked = _hc3_t(design, inverse, leverage, np.vstack([response, response]), 2)
    assert stacked[0] == pytest.approx(expected[2]) and stacked[1] == pytest.approx(expected[2])


def test_bootstrap_is_deterministic_and_respects_its_floor():
    rng = np.random.default_rng(4)
    x, design = heavy_tailed_design(rng)
    response = 1 + 2.0 * x + rng.standard_normal(len(x))
    entropy = bootstrap_entropy(11, "AAPL", "2012-06-21", "13:30", "ofi_l1")
    first = wild_bootstrap_p_values(design, response, 199, entropy)
    again = wild_bootstrap_p_values(design, response, 199, list(entropy))
    assert first.tolist() == again.tolist()
    other = wild_bootstrap_p_values(design, response, 199, bootstrap_entropy(12, "AAPL"))
    assert other.tolist() != first.tolist()
    assert first[1] == pytest.approx(1 / 200)  # a strong true slope: no draw is as extreme
    assert ((first > 0) & (first <= 1)).all()
    assert bootstrap_entropy(1, "a") == bootstrap_entropy(1, "a") != bootstrap_entropy(1, "b")


def test_bootstrap_detects_a_real_quadratic_effect_and_not_an_absent_one():
    rng = np.random.default_rng(5)
    x, design = heavy_tailed_design(rng, n=120)
    noise = rng.standard_normal(len(x))
    real = wild_bootstrap_p_values(design, 1 + 0.5 * x + 0.8 * design[:, 2] + noise, 499, [1])
    absent = wild_bootstrap_p_values(design, 1 + 0.5 * x + noise, 499, [1])
    assert real[2] < 0.01 and absent[2] > 0.05


def test_bootstrap_and_hc3_control_the_size_that_hc0_loses_with_heavy_tails():
    rng = np.random.default_rng(5)
    reps, rejections = 400, {"hc0": 0, "hc3": 0, "bootstrap": 0}
    for replication in range(reps):
        x, design = heavy_tailed_design(rng)
        response = 1 + 0.5 * x + rng.standard_normal(len(x)) * (0.5 + np.abs(x))  # gamma = 0
        model = sm.OLS(response, design)
        rejections["hc0"] += model.fit(cov_type="HC0", use_t=False).pvalues[2] < 0.05
        rejections["hc3"] += model.fit(cov_type="HC3", use_t=False).pvalues[2] < 0.05
        p = wild_bootstrap_p_values(design, response, 199, bootstrap_entropy(7, replication))
        rejections["bootstrap"] += p[2] < 0.05
    size = {name: count / reps for name, count in rejections.items()}
    # The paper's HC0 z-test rejects a true null about a third of the time here.
    assert size["hc0"] > 0.25
    assert size["hc3"] < 0.16 and size["bootstrap"] < 0.16


def test_undefined_statistics_give_nan_and_bad_draws_are_rejected():
    rng = np.random.default_rng(6)
    n = 30
    x = rng.standard_normal(n)
    dummy = np.zeros(n)
    dummy[0] = 1.0  # one observation owns its regressor: leverage one, HC3 undefined
    design = np.column_stack([np.ones(n), x, dummy])
    response = 1 + x + rng.standard_normal(n)
    assert np.isnan(wild_bootstrap_p_values(design, response, 99, [1])).all()
    for draws in (0, -1, 1.5, True):
        with pytest.raises(ValueError, match="draws"):
            wild_bootstrap_p_values(design, response, draws, [1])
