"""Table 3 (impact against depth) on authored data whose true law is known."""

import json

import numpy as np
import pandas as pd
import pytest

from research.baseline.depth_impact import (
    AVERAGE_LABEL,
    TABLE3_COLUMNS,
    DepthImpactConfig,
    fit_depth_law,
    main,
    newey_west_lags,
    paper_table3,
    window_depth_betas,
)


def stock(symbol, law, windows=60, per_window=40, seed=1, noise=0.1):
    """Half-hour windows whose true impact is ``law(depth)``; 13 windows make a session."""
    rng = np.random.default_rng(seed)
    frames = []
    for index in range(windows):
        depth = float(np.exp(rng.uniform(np.log(20), np.log(400))))
        beta = law(depth)
        day, slot = divmod(index, 13)
        start = pd.Timestamp(f"2012-06-{day + 1:02d}T13:30:00Z") + pd.Timedelta(minutes=30 * slot)
        stamps = start + pd.to_timedelta(10 * (np.arange(per_window) + 1), unit="s")
        ofi = rng.normal(0, 50, per_window).round()
        frames.append(
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "date": f"2012-06-{day + 1:02d}",
                    "timestamp": stamps,
                    "interval_start": stamps - pd.Timedelta(seconds=10),
                    "accepted": True,
                    "ofi_l1": ofi,
                    "trade_imbalance": np.nan,
                    "avg_depth": depth,
                    "quote_update_count": 3,
                    "volume": 100,
                    "mid_price_change_ticks": beta * ofi
                    + rng.normal(0, noise * beta * 50, per_window),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_window_depth_is_weighted_by_quote_updates_and_ignores_rows_without_ofi():
    data = stock("A", lambda depth: 0.5, windows=1, per_window=24, noise=0.0)
    data["avg_depth"] = np.tile([100.0, 200.0, 400.0], 8)
    data["quote_update_count"] = np.tile([1, 1, 2], 8)
    data.loc[0, "ofi_l1"] = np.nan  # a 100-share bucket with weight 1 is not in the sample
    config = DepthImpactConfig(min_observations=10)
    windows = window_depth_betas(data, config)
    kept = data.dropna(subset=["ofi_l1"])
    expected = np.average(kept["avg_depth"], weights=kept["quote_update_count"])
    assert windows["avg_depth"].iloc[0] == pytest.approx(expected)
    assert windows["avg_depth"].iloc[0] != pytest.approx(kept["avg_depth"].mean())
    assert windows["beta"].iloc[0] == pytest.approx(0.5, abs=1e-9)
    assert windows["observations"].iloc[0] == 23
    unweighted = window_depth_betas(
        data, DepthImpactConfig(min_observations=10, weight_column=None)
    )
    assert unweighted["avg_depth"].iloc[0] == pytest.approx(kept["avg_depth"].mean())
    with pytest.raises(ValueError, match="Missing weight column"):
        window_depth_betas(data.drop(columns="quote_update_count"), config)
    with pytest.raises(ValueError, match="avg_depth"):
        window_depth_betas(data.drop(columns="avg_depth"), config)


def test_exact_power_law_gives_exact_parameters():
    depth = np.exp(np.linspace(np.log(20), np.log(400), 30))
    for lam, c in ((1.0, 50.0), (0.6, 7.0), (1.4, 400.0)):
        row = fit_depth_law(c / depth**lam, depth, DepthImpactConfig())
        assert row["lambda_hat"] == pytest.approx(lam, abs=1e-9)
        assert row["c"] == pytest.approx(c, rel=1e-9)
        assert row["r2_loglog"] == pytest.approx(1.0) and row["corr2_fitted"] == pytest.approx(1.0)


def test_recovers_the_depth_law_and_tests_lambda_equal_one():
    config = DepthImpactConfig()
    data = pd.concat(
        [
            stock("INVERSE", lambda depth: 50 / depth, seed=2),
            stock("SQRT", lambda depth: 5 / depth**0.5, seed=3),
        ],
        ignore_index=True,
    )
    table = paper_table3(window_depth_betas(data, config), config)
    assert list(table.columns) == ["symbol", *TABLE3_COLUMNS]
    assert table["symbol"].tolist() == ["INVERSE", "SQRT", AVERAGE_LABEL]
    inverse, sqrt = (table.set_index("symbol").loc[name] for name in ("INVERSE", "SQRT"))
    assert inverse["lambda_hat"] == pytest.approx(1.0, abs=0.03)
    assert inverse["c"] == pytest.approx(50.0, rel=0.05)
    assert inverse["lambda_low"] < 1.0 < inverse["lambda_high"]
    assert inverse["c_low"] < 50.0 < inverse["c_high"]
    assert inverse["corr2_fitted"] > 0.95 and inverse["corr2_inverse_depth"] > 0.95
    assert inverse["lambda_eq_1_not_rejected"] == 1.0
    assert sqrt["lambda_hat"] == pytest.approx(0.5, abs=0.03)
    assert sqrt["c"] == pytest.approx(5.0, rel=0.05)
    assert sqrt["p_lambda_eq_1"] < 0.001 and sqrt["lambda_eq_1_not_rejected"] == 0.0
    assert sqrt["corr2_fitted"] > sqrt["corr2_inverse_depth"]  # the fitted exponent matters
    average = table.set_index("symbol").loc[AVERAGE_LABEL]
    assert average["lambda_hat"] == pytest.approx((inverse["lambda_hat"] + sqrt["lambda_hat"]) / 2)
    assert average["lambda_eq_1_not_rejected"] == 0.5
    assert table.set_index("symbol")["windows"].tolist() == [60.0, 60.0, 60.0]


def test_no_relation_to_depth_means_lambda_near_zero_and_a_poor_fit():
    config = DepthImpactConfig()
    data = stock("FLAT", lambda depth: 0.3, windows=80, seed=4, noise=0.5)
    row = paper_table3(window_depth_betas(data, config), config).iloc[0]
    assert abs(row["lambda_hat"]) < 0.15 and row["r2_loglog"] < 0.05
    assert row["lambda_eq_1_not_rejected"] == 0.0 and row["lambda_low"] < 0.0 < row["lambda_high"]


def test_dropped_and_too_short_stocks_are_reported_not_hidden():
    config = DepthImpactConfig()
    depth = np.exp(np.linspace(np.log(20), np.log(400), 20))
    beta = 50 / depth
    beta[[3, 7]] = [-0.1, 0.0]  # no logarithm exists
    row = fit_depth_law(beta, depth, config, dropped=5)
    assert row["windows"] == 18 and row["dropped_windows"] == 7
    assert row["lambda_hat"] == pytest.approx(1.0, abs=1e-9)
    short = fit_depth_law(beta[:6], depth[:6], config)
    assert short["windows"] == 5 and np.isnan(short["lambda_hat"]) and np.isnan(short["c"])
    constant = fit_depth_law(beta, np.full(20, 100.0), config)
    assert constant["windows"] == 18 and np.isnan(constant["lambda_hat"])
    # A stock with some skipped windows keeps their count in the table.
    data = stock("A", lambda depth: 50 / depth, windows=13, per_window=40, seed=5)
    data = data[~((data["date"] == "2012-06-01") & (data["timestamp"].dt.minute < 30))]
    windows = window_depth_betas(data, config)
    sparse = pd.concat([windows, windows.assign(status="insufficient_observations")])
    row = paper_table3(sparse, DepthImpactConfig(min_windows=4)).set_index("symbol").loc["A"]
    assert row["dropped_windows"] == len(windows)


def test_newey_west_bandwidth_follows_the_automatic_rule():
    assert [newey_west_lags(t) for t in (1, 10, 100, 500, 1000)] == [1, 2, 4, 5, 6]
    depth = np.exp(np.linspace(np.log(20), np.log(400), 40))
    noisy = 50 / depth * np.exp(np.random.default_rng(1).normal(0, 0.3, 40))
    automatic = fit_depth_law(noisy, depth, DepthImpactConfig())
    explicit = fit_depth_law(noisy, depth, DepthImpactConfig(hac_lags=newey_west_lags(40)))
    wider = fit_depth_law(noisy, depth, DepthImpactConfig(hac_lags=10))
    assert automatic["t_lambda"] == pytest.approx(explicit["t_lambda"])
    assert automatic["lambda_hat"] == wider["lambda_hat"]
    assert automatic["t_lambda"] != pytest.approx(wider["t_lambda"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_minutes": 0},
        {"min_observations": False},
        {"min_windows": 3},
        {"hac_lags": -1},
        {"hac_lags": 1.5},
        {"level": 5},
        {"level": 1.5},
        {"target": ""},
        {"weight_column": 3},
    ],
)
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        DepthImpactConfig(**kwargs)


def test_cli_writes_table_windows_and_report_and_protects_existing_output(tmp_path):
    source = tmp_path / "features.parquet"
    stock("AAA", lambda depth: 50 / depth, seed=2).to_parquet(source, index=False)
    config = tmp_path / "depth.json"
    config.write_text("{}")
    output = tmp_path / "table3"
    args = ["--features", str(source), "--config", str(config), "--output-dir", str(output)]
    assert main(args) == 0
    table = pd.read_csv(output / "table3.csv")
    assert table["symbol"].tolist() == ["AAA", AVERAGE_LABEL]
    assert table.loc[0, "lambda_hat"] == pytest.approx(1.0, abs=0.03)
    windows = pd.read_csv(output / "window_betas.csv")
    assert list(windows.columns)[:3] == ["symbol", "date", "window_start"]
    assert len(windows) == 60 and windows["beta"].notna().all()
    report = json.loads((output / "run.json").read_text())
    assert report["windows_total"] == 60 and report["windows_fitted"] == 60
    assert report["symbols_with_fit"] == 1 and len(report["feature_sha256"]) == 64
    assert "Newey-West" in report["standard_errors"]
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    config.write_text(json.dumps({"min_windows": 2}))
    with pytest.raises(SystemExit) as error:
        main([*args[:-1], str(tmp_path / "other")])
    assert error.value.code == 2
