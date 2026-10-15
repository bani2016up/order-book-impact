"""Window summaries and paper-layout Tables 2 and 4 on authored synthetic results."""

import json

import numpy as np
import pandas as pd
import pytest

from research.baseline.run import BaselineConfig, fit_models, main
from research.baseline.tables import (
    AVERAGE_LABEL,
    MODEL_COLUMNS,
    TABLE2_COLUMNS,
    TABLE4_COLUMNS,
    TERM_COLUMNS,
    paper_table2,
    paper_table4,
    paper_tables,
    summarize_models,
    summarize_terms,
)

TERM_VALUE = {
    ("ofi_l1", "const"): 1,
    ("ofi_l1", "ofi_l1"): 2,
    ("ofi_quadratic", "const"): 3,
    ("ofi_quadratic", "ofi_l1"): 4,
    ("ofi_quadratic", "ofi_l1_signed_square"): 5,
    ("trade_imbalance", "const"): 6,
    ("trade_imbalance", "trade_imbalance"): 7,
    ("ofi_and_ti", "const"): 8,
    ("ofi_and_ti", "ofi_l1"): 9,
    ("ofi_and_ti", "trade_imbalance"): 10,
}
MODEL_R2 = {"ofi_l1": 0.1, "ofi_quadratic": 0.2, "trade_imbalance": 0.3, "ofi_and_ti": 0.4}
SYMBOL_OFFSET = {"AAA": 0.0, "BBB": 100.0}


def handmade_results():
    """Two symbols, two windows; every model/term pair has its own recognizable value.

    AAA is significant in the first window only and BBB in both.
    """
    coefficients, metrics = [], []
    for symbol, offset in SYMBOL_OFFSET.items():
        for window in range(2):
            start = pd.Timestamp("2012-06-21T13:30:00Z") + pd.Timedelta(minutes=30 * window)
            for (model, term), value in TERM_VALUE.items():
                coefficients.append(
                    {
                        "symbol": symbol,
                        "date": "2012-06-21",
                        "window_start": start,
                        "model": model,
                        "term": term,
                        "estimate": value + offset,
                        "hc0_standard_error": 1.0,
                        "z_statistic": 10.0 * value + offset,
                        "p_value": 0.01 if (symbol == "BBB" or window == 0) else 0.5,
                    }
                )
            for model, r2 in MODEL_R2.items():
                metrics.append(
                    {
                        "symbol": symbol,
                        "date": "2012-06-21",
                        "window_start": start,
                        "model": model,
                        "status": "ok",
                        "in_sample_r2": r2 + offset / 1000,
                        "f_statistic": 100 * r2 + offset,
                        "f_statistic_hc0": 100 * r2 + offset + 0.5,
                    }
                )
    return pd.DataFrame(metrics), pd.DataFrame(coefficients)


def test_term_summary_applies_the_strict_level_and_ignores_undefined_p_values():
    p_values = [0.01, 0.2, 0.049, 0.05, np.nan]
    coefficients = pd.DataFrame(
        {
            "symbol": "A",
            "model": "m",
            "term": "x",
            "estimate": [1.0, 2.0, 3.0, 4.0, 5.0],
            "z_statistic": [2.0, 4.0, 6.0, 8.0, 10.0],
            "p_value": p_values,
        }
    )
    summary = summarize_terms(coefficients)
    assert list(summary.columns) == TERM_COLUMNS
    row = summary.iloc[0]
    assert (row["windows"], row["mean_estimate"], row["mean_z_statistic"]) == (5, 3.0, 6.0)
    assert row["pct_significant"] == 50.0  # 0.01 and 0.049 pass; 0.05 itself does not
    for level, expected in ((0.02, 25.0), (0.1, 75.0), (0.3, 100.0)):
        assert summarize_terms(coefficients, level)["pct_significant"].iloc[0] == expected


def test_model_summary_separates_fitted_from_skipped_windows():
    metrics = pd.DataFrame(
        {
            "symbol": "A",
            "model": "m",
            "status": ["ok", "ok", "constant_target", "insufficient_observations"],
            "in_sample_r2": [0.2, 0.6, None, None],
            "f_statistic": [10.0, 30.0, None, None],
            "f_statistic_hc0": [11.0, 31.0, None, None],
        }
    )
    summary = summarize_models(metrics)
    assert list(summary.columns) == MODEL_COLUMNS
    row = summary.iloc[0]
    assert (row["fitted_windows"], row["skipped_windows"]) == (2, 2)
    assert row["mean_in_sample_r2"] == pytest.approx(0.4)
    assert (row["mean_f_statistic"], row["mean_f_statistic_hc0"]) == (20.0, 21.0)


def test_table2_maps_every_column_to_its_model_and_term():
    metrics, coefficients = handmade_results()
    table = paper_table2(metrics, coefficients)
    assert list(table.columns) == ["symbol", *TABLE2_COLUMNS]
    assert table["symbol"].tolist() == ["AAA", "BBB", AVERAGE_LABEL]
    aaa = table.set_index("symbol").loc["AAA"]
    assert aaa["windows"] == 2
    assert (aaa["alpha"], aaa["t_alpha"], aaa["pct_alpha_sig"]) == (1.0, 10.0, 50.0)
    assert (aaa["beta"], aaa["t_beta"], aaa["pct_beta_sig"]) == (2.0, 20.0, 50.0)
    assert (aaa["gamma_q"], aaa["t_gamma_q"], aaa["pct_gamma_q_sig"]) == (5.0, 50.0, 50.0)
    assert aaa["r2"] == pytest.approx(0.1)  # first (linear) regression, not the quadratic one
    bbb = table.set_index("symbol").loc["BBB"]
    assert (bbb["beta"], bbb["pct_beta_sig"], bbb["r2"]) == (102.0, 100.0, pytest.approx(0.2))
    average = table.set_index("symbol").loc[AVERAGE_LABEL]
    numbers = table.set_index("symbol").drop(index=AVERAGE_LABEL)
    assert average.to_dict() == pytest.approx(numbers.mean().to_dict())


def test_table4_maps_ofi_trade_and_joint_columns():
    metrics, coefficients = handmade_results()
    table = paper_table4(metrics, coefficients)
    assert list(table.columns) == ["symbol", *TABLE4_COLUMNS]
    aaa = table.set_index("symbol").loc["AAA"]
    assert aaa["windows"] == 2
    assert (aaa["ofi_r2"], aaa["ofi_t_beta"], aaa["ofi_pct_beta_sig"]) == (0.1, 20.0, 50.0)
    assert (aaa["ti_r2"], aaa["ti_t_beta"], aaa["ti_pct_beta_sig"]) == (0.3, 70.0, 50.0)
    assert (aaa["both_r2"], aaa["both_t_theta_ofi"], aaa["both_t_theta_ti"]) == (0.4, 90.0, 100.0)
    assert (aaa["ofi_f"], aaa["ti_f"], aaa["both_f"]) == (10.0, 30.0, 40.0)
    assert (aaa["both_pct_theta_ofi_sig"], aaa["both_pct_theta_ti_sig"]) == (50.0, 50.0)
    bbb = table.set_index("symbol").loc["BBB"]
    assert (bbb["ofi_f"], bbb["both_t_theta_ti"], bbb["both_pct_theta_ti_sig"]) == (
        110.0,
        200.0,
        100.0,
    )
    assert table["symbol"].iloc[-1] == AVERAGE_LABEL


def test_missing_models_are_reported_and_other_tables_are_omitted():
    metrics, coefficients = handmade_results()
    only_table4 = metrics[metrics["model"] != "ofi_quadratic"]
    assert sorted(paper_tables(only_table4, coefficients)) == ["table4"]
    assert sorted(paper_tables(metrics, coefficients)) == ["table2", "table4"]
    with pytest.raises(ValueError, match="table2 needs the models: ofi_quadratic"):
        paper_table2(only_table4, coefficients)
    only_ofi = metrics[metrics["model"] == "ofi_l1"]
    assert paper_tables(only_ofi, coefficients) == {}
    with pytest.raises(ValueError, match="table4 needs the models: ofi_and_ti, trade_imbalance"):
        paper_table4(only_ofi, coefficients)


def synthetic_features(windows=3, per_window=60, seed=11):
    """Trade imbalance is correlated with OFI, but only OFI drives the price change."""
    rng = np.random.default_rng(seed)
    frames = []
    for symbol, beta in (("AAA", 0.3), ("BBB", 0.05)):
        for k in range(windows):
            start = pd.Timestamp("2012-06-21T13:30:00Z") + pd.Timedelta(minutes=30 * k)
            stamps = start + pd.to_timedelta(10 * (np.arange(per_window) + 1), unit="s")
            ofi = rng.normal(0, 100, per_window).round()
            ti = (0.5 * ofi + rng.normal(0, 60, per_window)).round()
            frames.append(
                pd.DataFrame(
                    {
                        "symbol": symbol,
                        "date": "2012-06-21",
                        "timestamp": stamps,
                        "interval_start": stamps - pd.Timedelta(seconds=10),
                        "accepted": True,
                        "ofi_l1": ofi,
                        "trade_imbalance": ti,
                        "avg_depth": 100.0,
                        "volume": 100,
                        "mid_price_change_ticks": 0.1
                        + beta * ofi
                        + rng.normal(0, 60 * beta, per_window),
                    }
                )
            )
    return pd.concat(frames, ignore_index=True)


def test_ofi_absorbs_trade_imbalance_in_a_synthetic_replication():
    metrics, coefficients = fit_models(synthetic_features(), BaselineConfig())
    table2 = paper_table2(metrics, coefficients).set_index("symbol")
    assert table2.loc["AAA", "beta"] == pytest.approx(0.3, abs=0.03)
    assert table2.loc["BBB", "beta"] == pytest.approx(0.05, abs=0.01)
    assert (table2[["pct_beta_sig"]].iloc[:2] == 100.0).all().all()
    assert table2.loc["AAA", "windows"] == 3
    # The generator must really add noise: a near-perfect fit would make every test vacuous.
    assert (table2.loc[["AAA", "BBB"], "r2"].between(0.5, 0.9)).all()
    # The relation is linear by construction, so the curvature is tiny next to the slope.
    assert abs(table2.loc["AAA", "gamma_q"]) < 0.01 * table2.loc["AAA", "beta"]
    table4 = paper_table4(metrics, coefficients).set_index("symbol")
    for symbol in ("AAA", "BBB"):
        row = table4.loc[symbol]
        assert row["ofi_r2"] > row["ti_r2"]
        assert row["ti_t_beta"] > 3 > abs(row["both_t_theta_ti"])
        assert row["both_pct_theta_ofi_sig"] == 100.0
        assert row["both_pct_theta_ti_sig"] < 70.0


def test_all_skipped_windows_give_well_formed_empty_tables():
    metrics, coefficients = fit_models(synthetic_features(), BaselineConfig(min_observations=500))
    assert coefficients.empty
    assert list(summarize_terms(coefficients).columns) == TERM_COLUMNS
    assert summarize_models(metrics)["fitted_windows"].eq(0).all()
    table2, table4 = paper_table2(metrics, coefficients), paper_table4(metrics, coefficients)
    assert list(table2.columns) == ["symbol", *TABLE2_COLUMNS]
    assert list(table4.columns) == ["symbol", *TABLE4_COLUMNS]
    assert table2["symbol"].tolist() == ["AAA", "BBB", AVERAGE_LABEL]
    assert table2.drop(columns="symbol")["windows"].eq(0).all()
    assert table2.drop(columns=["symbol", "windows"]).isna().all().all()


def test_cli_writes_summaries_and_only_the_tables_its_models_allow(tmp_path):
    source = tmp_path / "features.parquet"
    synthetic_features().to_parquet(source, index=False)
    default = tmp_path / "default"
    configuration = tmp_path / "default.json"
    configuration.write_text("{}")
    arguments = ["--features", str(source), "--config", str(configuration)]
    assert main([*arguments, "--output-dir", str(default)]) == 0
    report = json.loads((default / "run.json").read_text())
    assert report["paper_tables"] == ["table2", "table4"]
    assert report["significance"] == {
        "level": 0.05,
        "test": "two-sided z-test on HC0 standard errors",
    }
    assert report["fitted_windows"] == 24 and report["skipped_windows"] == 0
    for name in ("table2", "table4", "summary_models", "summary_terms"):
        assert (default / f"{name}.csv").is_file()
    written = pd.read_csv(default / "table2.csv")
    assert written["symbol"].tolist() == ["AAA", "BBB", AVERAGE_LABEL]
    assert list(written.columns) == ["symbol", *TABLE2_COLUMNS]

    narrow = tmp_path / "narrow"
    configuration.write_text(json.dumps({"models": {"ofi_l1": ["ofi_l1"]}}))
    assert main([*arguments, "--output-dir", str(narrow)]) == 0
    assert json.loads((narrow / "run.json").read_text())["paper_tables"] == []
    assert not (narrow / "table2.csv").exists() and (narrow / "summary_terms.csv").is_file()
