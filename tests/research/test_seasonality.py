"""Figures 5 and 6: slot patterns, normalisation, cross-stock averages and the plots."""

import json

import numpy as np
import pandas as pd
import pytest

from research.baseline.seasonality import (
    BLUE,
    ORANGE,
    SeasonalityConfig,
    cross_stock_average,
    figure5,
    figure6,
    main,
    seasonal_summary,
    stock_patterns,
    window_statistics,
)

DEPTH = np.array([0.5] + [1.0] * 11 + [1.5])  # shallow at the open, deep at the close
SLOTS = [f"{9 + (30 + 30 * i) // 60:02d}:{(30 + 30 * i) % 60:02d}" for i in range(13)]


def sessions(symbol, dates, per_window=30, seed=1, noise=0.05):
    """Real-time sessions whose depth, impact (c / depth) and OFI scale have known profiles."""
    rng = np.random.default_rng(seed)
    frames = []
    for date in dates:
        opening = pd.Timestamp(f"{date} 09:30", tz="America/New_York").tz_convert("UTC")
        for slot in range(13):
            start = opening + pd.Timedelta(minutes=30 * slot)
            stamps = start + pd.to_timedelta(10 * (np.arange(per_window) + 1), unit="s")
            beta, depth = 40 / (100 * DEPTH[slot]), 100 * DEPTH[slot]
            ofi = rng.normal(0, 50 * (1 + (slot == 12)), per_window).round()
            frames.append(
                pd.DataFrame(
                    {
                        "symbol": symbol,
                        "date": date,
                        "timestamp": stamps,
                        "interval_start": stamps - pd.Timedelta(seconds=10),
                        "accepted": True,
                        "ofi_l1": ofi,
                        "trade_imbalance": np.nan,
                        "avg_depth": depth,
                        "quote_update_count": 2,
                        "volume": 100,
                        "mid_price_change_ticks": beta * ofi
                        + rng.normal(0, noise * beta * 50, per_window),
                    }
                )
            )
    return pd.concat(frames, ignore_index=True)


WINTER_AND_SUMMER = ["2019-01-30", "2019-03-27", "2019-05-30", "2019-07-30", "2019-10-30"]


def test_slots_are_local_exchange_time_in_winter_and_summer():
    data = sessions("A", ["2019-01-30", "2019-07-30"])  # EST (14:30Z open) and EDT (13:30Z open)
    stats = window_statistics(data, SeasonalityConfig())
    assert len(stats) == 26
    assert sorted(stats["slot"].unique()) == SLOTS
    first = stats[stats["slot"] == "09:30"].sort_values("date")
    assert [t.hour for t in first["window_start"]] == [14, 13]
    assert stats.groupby("date")["slot"].nunique().eq(13).all()


def test_window_statistics_hold_beta_depth_and_sample_variances():
    data = sessions("A", ["2019-07-30"], seed=3, noise=0.0)
    stats = window_statistics(data, SeasonalityConfig()).set_index("slot")
    window = data[
        data["interval_start"].dt.floor("30min") == data["interval_start"].iloc[0].floor("30min")
    ]
    assert stats.loc["09:30", "var_dp"] == pytest.approx(
        window["mid_price_change_ticks"].var(ddof=1)
    )
    assert stats.loc["09:30", "var_ofi"] == pytest.approx(window["ofi_l1"].var(ddof=1))
    assert stats.loc["09:30", "beta"] == pytest.approx(0.8, abs=1e-9)  # 40 / (100 * 0.5)
    assert stats.loc["09:30", "avg_depth"] == pytest.approx(50.0)
    assert stats.loc["15:30", "avg_depth"] == pytest.approx(150.0)
    short = window_statistics(data.iloc[:25], SeasonalityConfig(min_observations=30))
    assert short.empty  # a window below the observation minimum is not used


def test_patterns_are_normalised_by_each_stocks_own_average():
    stats = window_statistics(sessions("A", WINTER_AND_SUMMER, noise=0.02), SeasonalityConfig())
    patterns, excluded = stock_patterns(stats, SeasonalityConfig())
    assert excluded == {} and len(patterns) == 13 and patterns["days"].eq(5).all()
    by_slot = patterns.set_index("slot")
    depth = by_slot["depth"]
    assert depth.tolist() == pytest.approx((DEPTH / DEPTH.mean()).tolist())  # exact: no noise
    inverse = 1 / DEPTH
    assert by_slot["beta"].tolist() == pytest.approx((inverse / inverse.mean()).tolist(), rel=0.03)
    # beta**2 * var[OFI] is built from the average patterns and scaled like var[dP].
    raw = stats.groupby("slot")[["beta", "var_ofi"]].mean()
    expected = raw["beta"] ** 2 * raw["var_ofi"] / stats["var_dp"].mean()
    assert by_slot["beta2_var_ofi"].tolist() == pytest.approx(expected.tolist())
    assert by_slot["var_dp"].mean() == pytest.approx(1.0, rel=0.05)
    assert by_slot.loc["15:30", "var_ofi"] > 2 * by_slot.loc["10:30", "var_ofi"]


def test_stocks_without_enough_data_are_excluded_with_a_reason():
    config = SeasonalityConfig(min_days=3, min_slots=8)
    good = sessions("GOOD", WINTER_AND_SUMMER)
    thin = sessions("THIN", WINTER_AND_SUMMER[:2], seed=2)  # two days: no slot reaches 3 windows
    negative = sessions("NEG", WINTER_AND_SUMMER, seed=4)
    negative["mid_price_change_ticks"] = -negative["mid_price_change_ticks"]
    stats = window_statistics(pd.concat([good, thin, negative], ignore_index=True), config)
    patterns, excluded = stock_patterns(stats, config)
    assert sorted(patterns["symbol"].unique()) == ["GOOD"]
    assert "slots with at least 3 windows" in excluded["THIN"]
    assert "not positive" in excluded["NEG"]
    sparse = stats[
        ~((stats["symbol"] == "GOOD") & (stats["slot"] == "10:00") & (stats["date"] > "2019-01-30"))
    ]
    patterns, _ = stock_patterns(sparse, config)
    assert (
        patterns.set_index("slot").loc["10:00", ["beta", "depth", "var_dp", "var_ofi"]].isna().all()
    )
    assert patterns["beta"].notna().sum() == 12


def test_cross_stock_average_reports_mean_quartiles_and_counts():
    patterns = pd.DataFrame(
        {
            "symbol": ["A", "B", "C", "A", "B"],
            "slot": ["09:30", "09:30", "09:30", "10:00", "10:00"],
            "days": 5,
            "beta": [1.0, 2.0, 4.0, 1.0, np.nan],
            "depth": [1.0, 1.0, 1.0, 2.0, 2.0],
            "var_dp": 1.0,
            "var_ofi": 1.0,
            "beta2_var_ofi": 1.0,
        }
    )
    average = cross_stock_average(patterns).set_index("slot")
    assert average.loc["09:30", "stocks"] == 3 and average.loc["10:00", "stocks"] == 1
    assert average.loc["09:30", "beta_mean"] == pytest.approx(7 / 3)
    assert average.loc["09:30", ["beta_q25", "beta_q75"]].tolist() == [1.5, 3.0]
    assert average.loc["10:00", "beta_mean"] == 1.0  # the missing stock-slot is skipped
    assert average.loc["10:00", "depth_mean"] == 2.0


def test_summary_quotes_the_papers_open_close_and_variance_checks():
    stats = window_statistics(sessions("A", WINTER_AND_SUMMER, noise=0.02), SeasonalityConfig())
    patterns, _ = stock_patterns(stats, SeasonalityConfig())
    summary = seasonal_summary(cross_stock_average(patterns))
    assert (summary["first_slot"], summary["last_slot"]) == ("09:30", "15:30")
    assert summary["depth_open_over_average"] < 0.6 < 0.8 < summary["beta_open_over_average"]
    assert summary["beta_open_over_close"] == pytest.approx(3.0, rel=0.1)  # 1/0.5 against 1/1.5
    assert summary["var_ofi_peak_slot"] == "15:30"
    assert -1 <= summary["corr_var_dp_vs_beta2_var_ofi"] <= 1
    assert seasonal_summary(cross_stock_average(patterns.iloc[0:0])) == {}


def test_figures_plot_the_averages_with_the_validated_encodings():
    stats = window_statistics(sessions("A", WINTER_AND_SUMMER), SeasonalityConfig())
    patterns, _ = stock_patterns(stats, SeasonalityConfig())
    average = cross_stock_average(patterns)
    five = figure5(average, "subtitle")
    lines = five.axes[0].get_lines()
    labels = [line.get_label() for line in lines]
    assert [label for label in labels if not label.startswith("_")] == [
        "Price impact β",
        "Average depth AD",
    ]
    by_label = {line.get_label(): line for line in lines if not line.get_label().startswith("_")}
    assert by_label["Price impact β"].get_ydata().tolist() == average["beta_mean"].tolist()
    assert by_label["Average depth AD"].get_ydata().tolist() == average["depth_mean"].tolist()
    assert by_label["Price impact β"].get_color() == BLUE
    assert by_label["Average depth AD"].get_color() == ORANGE
    assert by_label["Price impact β"].get_marker() != by_label["Average depth AD"].get_marker()
    assert by_label["Price impact β"].get_linewidth() == 2
    assert [t.get_text() for t in five.axes[0].get_xticklabels()] == SLOTS
    assert five.legends and len(five.legends[0].get_texts()) == 2
    six = figure6(average, "subtitle")
    assert six.axes[0].get_yscale() == "log"
    names = [t.get_text() for t in six.legends[0].get_texts()]
    assert names == ["var[ΔP]", "β² · var[OFI]", "β", "var[OFI]"]
    markers = {line.get_marker() for line in six.axes[0].get_lines() if line.get_label() in names}
    assert len(markers) == 4  # shape is a second channel next to colour


def test_invalid_configuration():
    for kwargs in ({"min_days": 0}, {"min_slots": False}, {"window_minutes": -5}, {"target": ""},
                   {"weight_column": 3}, {"timezone": "Nowhere/City"}):  # fmt: skip
        with pytest.raises(ValueError):
            SeasonalityConfig(**kwargs)


def test_cli_writes_tables_figures_and_report_and_protects_existing_output(tmp_path):
    source = tmp_path / "features.parquet"
    data = pd.concat(
        [
            sessions("AAA", WINTER_AND_SUMMER, seed=2),
            sessions("BBB", WINTER_AND_SUMMER, seed=3),
            sessions("SPARSE", WINTER_AND_SUMMER[:1], seed=4),
        ],
        ignore_index=True,
    )
    data.to_parquet(source, index=False)
    config = tmp_path / "seasonality.json"
    config.write_text("{}")
    output = tmp_path / "result"
    args = ["--features", str(source), "--config", str(config), "--output-dir", str(output)]
    assert main([*args, "--venue", "TEST"]) == 0
    for name in ("fig5_impact_and_depth.png", "fig6_variance.png"):
        assert (output / name).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    for name in ("window_statistics.csv", "patterns_by_stock.csv", "pattern_average.csv"):
        assert (output / name).is_file()
    average = pd.read_csv(output / "pattern_average.csv")
    assert average["slot"].tolist() == SLOTS and average["stocks"].eq(2).all()
    report = json.loads((output / "run.json").read_text())
    assert report["stocks_in_average"] == ["AAA", "BBB"]
    assert list(report["stocks_excluded"]) == ["SPARSE"]
    assert report["summary"]["depth_open_over_average"] < 0.7
    assert report["windows_used"] == 5 * 13 * 2 + 13
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    single_day = tmp_path / "one_day.parquet"
    sessions("ONE", ["2019-07-30"]).to_parquet(single_day, index=False)
    with pytest.raises(SystemExit) as error:
        main(
            [
                "--features",
                str(single_day),
                "--config",
                str(config),
                "--output-dir",
                str(tmp_path / "x"),
            ]
        )
    assert error.value.code == 2
