"""Known authored model relationships, common samples, and reproducible CLI output."""

import json

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm

from research.baseline.run import BaselineConfig, add_signed_squares, fit_models, main


def observations():
    x = np.arange(24, dtype=float) - 12
    ti = np.tile([-2.0, 1.0, 3.0], 8)
    stamps = pd.date_range("2012-06-21T13:30:20Z", periods=24, freq="10s")
    return pd.DataFrame(
        {
            "symbol": "A",
            "date": "2012-06-21",
            "timestamp": stamps,
            "interval_start": stamps - pd.Timedelta(seconds=10),
            "accepted": True,
            "ofi_l1": x,
            "trade_imbalance": ti,
            "avg_depth": 100.0,
            "volume": 100,
            "mid_price_change_ticks": 1.25 + 0.3 * x + 0.2 * ti + 0.01 * np.sin(x),
        }
    )


def test_known_relationship_and_common_complete_cases():
    data = observations()
    data.loc[0, "trade_imbalance"] = np.nan
    metrics, coefficients = fit_models(data, BaselineConfig())
    assert metrics["observations"].tolist() == [23, 23, 23, 23]
    assert metrics["dropped_incomplete_rows"].tolist() == [1, 1, 1, 1]
    combined = coefficients[coefficients["model"] == "ofi_and_ti"].set_index("term")
    assert combined.loc["ofi_l1", "estimate"] == pytest.approx(0.3, abs=0.002)
    assert combined.loc["trade_imbalance", "estimate"] == pytest.approx(0.2, abs=0.002)
    assert combined["hc0_standard_error"].gt(0).all()
    assert metrics.loc[metrics["model"] == "ofi_and_ti", "in_sample_r2"].iloc[0] > 0.999


def test_small_constant_and_rank_deficient_windows_are_explicit():
    data = observations()
    metrics, coefficients = fit_models(data, BaselineConfig(min_observations=100))
    assert metrics["status"].eq("insufficient_observations").all() and coefficients.empty
    data["mid_price_change_ticks"] = 1.0
    metrics, _ = fit_models(data, BaselineConfig())
    assert metrics["status"].eq("constant_target").all()
    data = observations()
    data["ofi_l1"] = 1.0
    metrics, _ = fit_models(data, BaselineConfig())
    assert metrics.loc[metrics["model"] == "ofi_l1", "status"].iloc[0] == "rank_deficient"
    with pytest.raises(ValueError, match="Missing model columns"):
        fit_models(data.drop(columns="trade_imbalance"), BaselineConfig())


def test_signed_square_is_ofi_times_absolute_ofi_and_never_replaces_columns():
    data = observations()
    derived = add_signed_squares(data, {"ofi_l1_signed_square", "ofi_l1", "no_base_signed_square"})
    expected = data["ofi_l1"] * data["ofi_l1"].abs()
    assert derived["ofi_l1_signed_square"].tolist() == expected.tolist()
    assert (derived["ofi_l1_signed_square"][data["ofi_l1"] < 0] <= 0).all()
    assert "ofi_l1_signed_square" not in data and "no_base_signed_square" not in derived
    supplied = data.assign(ofi_l1_signed_square=7.0)
    assert (
        add_signed_squares(supplied, {"ofi_l1_signed_square"})["ofi_l1_signed_square"].eq(7).all()
    )
    with pytest.raises(ValueError, match="must be numeric: ofi_l1"):
        add_signed_squares(data.assign(ofi_l1="text"), {"ofi_l1_signed_square"})


def test_quadratic_model_recovers_known_curvature_and_keeps_input_unchanged():
    data = observations()
    x = data["ofi_l1"]
    data["mid_price_change_ticks"] = 0.5 + 0.3 * x + 0.01 * x * x.abs() + 0.05 * np.sin(1.7 * x)
    config = BaselineConfig(
        models={"linear": ["ofi_l1"], "quadratic": ["ofi_l1", "ofi_l1_signed_square"]}
    )
    metrics, coefficients = fit_models(data, config)
    assert "ofi_l1_signed_square" not in data
    quadratic = coefficients[coefficients["model"] == "quadratic"].set_index("term")
    assert quadratic.loc["ofi_l1_signed_square", "estimate"] == pytest.approx(0.01, abs=0.0015)
    assert quadratic.loc["ofi_l1_signed_square", "p_value"] < 0.05
    assert quadratic.loc["ofi_l1", "estimate"] == pytest.approx(0.3, abs=0.02)
    r2 = metrics.set_index("model")["in_sample_r2"]
    assert r2["quadratic"] > r2["linear"]
    with pytest.raises(ValueError, match="Missing model columns"):
        fit_models(data.drop(columns="ofi_l1"), config)


def test_f_statistics_match_statsmodels_and_unfitted_windows_stay_empty():
    data = observations()
    metrics, _ = fit_models(data, BaselineConfig())
    derived = add_signed_squares(data, {"ofi_l1_signed_square"})
    for _, row in metrics.iterrows():
        columns = BaselineConfig().models[row["model"]]
        design = sm.add_constant(derived[columns], has_constant="add")
        classical = sm.OLS(data["mid_price_change_ticks"], design).fit()
        robust = sm.OLS(data["mid_price_change_ticks"], design).fit(cov_type="HC0", use_t=False)
        assert row["f_statistic"] == pytest.approx(classical.fvalue)
        assert row["f_statistic_hc0"] == pytest.approx(robust.fvalue)
    skipped, _ = fit_models(data, BaselineConfig(min_observations=100))
    assert skipped["f_statistic"].isna().all() and skipped["f_statistic_hc0"].isna().all()
    perfect = data.assign(mid_price_change_ticks=1.0 + 2.0 * data["ofi_l1"])
    exact, _ = fit_models(perfect, BaselineConfig(models={"ofi_l1": ["ofi_l1"]}))
    assert exact["f_statistic"].iloc[0] > 1e12 or np.isinf(exact["f_statistic"].iloc[0])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_minutes": 0},
        {"min_observations": False},
        {"models": {}},
        {"models": {"bad": ["mid_price_change_ticks"]}},
    ],
)
def test_invalid_model_configuration(kwargs):
    with pytest.raises(ValueError):
        BaselineConfig(**kwargs)


def test_model_cli_saves_results_and_does_not_overwrite(tmp_path):
    source = tmp_path / "features.parquet"
    observations().to_parquet(source, index=False)
    config = tmp_path / "baseline.json"
    config.write_text("{}")
    output = tmp_path / "result"
    args = ["--features", str(source), "--config", str(config), "--output-dir", str(output)]
    assert main(args) == 0
    report = json.loads((output / "run.json").read_text())
    assert report["fitted_windows"] == 4 and report["common_complete_cases"]
    assert len(report["feature_sha256"]) == 64
    assert set(report["software_versions"]) == {"ofi-pipeline", "numpy", "pandas", "statsmodels"}
    assert pd.read_csv(output / "metrics.csv")["in_sample_r2"].notna().all()
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
