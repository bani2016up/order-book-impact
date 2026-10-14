"""Known authored model relationships, common samples, and reproducible CLI output."""

import json

import numpy as np
import pandas as pd
import pytest

from research.baseline.run import BaselineConfig, fit_models, main


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
    assert metrics["observations"].tolist() == [23, 23, 23]
    assert metrics["dropped_incomplete_rows"].tolist() == [1, 1, 1]
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
    assert report["fitted_windows"] == 3 and report["common_complete_cases"]
    assert len(report["feature_sha256"]) == 64
    assert set(report["software_versions"]) == {"ofi-pipeline", "numpy", "pandas", "statsmodels"}
    assert pd.read_csv(output / "metrics.csv")["in_sample_r2"].notna().all()
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
