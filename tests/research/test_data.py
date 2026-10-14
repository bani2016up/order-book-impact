"""Feature-loading and lag semantics on explicitly authored interval fixtures."""

import numpy as np
import pandas as pd
import pytest

from ofi_pipeline.research import lag_feature, load_features


def frame():
    timestamps = pd.to_datetime(
        ["2012-06-21T13:30:20Z", "2012-06-21T13:30:30Z", "2012-06-21T13:30:50Z", "2012-06-21T13:31:00Z"],
        utc=True,
    )
    return pd.DataFrame(
        {
            "symbol": ["A"] * 4,
            "date": ["2012-06-21"] * 4,
            "timestamp": timestamps,
            "interval_start": timestamps - pd.Timedelta(seconds=10),
            "accepted": [True] * 4,
            "ofi_l1": [10, 20, 30, 40],
            "mid_price_change_ticks": [0.1, 0.2, 0.3, 0.4],
            "avg_depth": [100.0] * 4,
            "volume": [10] * 4,
            "trade_imbalance": pd.array([1, None, 2, 3], dtype="Int64"),
        }
    )


def test_loader_orders_rows_preserves_unknown_ti_and_accepts_directory(tmp_path):
    source = frame().iloc[::-1]
    source.to_parquet(tmp_path / "features.parquet", index=False)
    loaded = load_features(tmp_path, symbols=["A"])
    assert loaded["ofi_l1"].tolist() == [10, 20, 30, 40]
    assert pd.isna(loaded.loc[1, "trade_imbalance"])
    for kwargs in [{"required_columns": ["ofi_l5"]}, {"symbols": ["B"]}, {"symbols": "A"}]:
        with pytest.raises(ValueError):
            load_features(tmp_path, **kwargs)


@pytest.mark.parametrize("issue", ["keys", "rejected", "unknown_acceptance", "timezone", "infinite", "missing"])
def test_loader_rejects_invalid_feature_contract(tmp_path, issue):
    data = frame()
    if issue == "keys":
        data = pd.concat([data, data.iloc[:1]], ignore_index=True)
    elif issue == "rejected":
        data.loc[1, "accepted"] = False
    elif issue == "unknown_acceptance":
        data["accepted"] = pd.array([True, None, True, True], dtype="boolean")
    elif issue == "timezone":
        data["timestamp"] = data["timestamp"].dt.tz_localize(None)
    elif issue == "infinite":
        data.loc[1, "avg_depth"] = np.inf
    else:
        data = data.drop(columns="ofi_l1")
    data.to_parquet(tmp_path / "features.parquet", index=False)
    with pytest.raises(ValueError):
        load_features(tmp_path)


def test_lag_does_not_cross_missing_intervals_or_sessions():
    data = frame()
    next_day = frame().iloc[:1].copy()
    next_day["date"] = "2012-06-22"
    for column in ("timestamp", "interval_start"):
        next_day[column] += pd.Timedelta(days=1)
    data = pd.concat([data, next_day], ignore_index=True)
    result = lag_feature(data, "ofi_l1", bucket_seconds=10)
    assert result["ofi_l1_lag1"].fillna(-1).tolist() == [-1, 10, -1, 30, -1]
    second = lag_feature(data, "ofi_l1", bucket_seconds=10, periods=2)
    assert second["ofi_l1_lag2"].isna().all()
    assert "ofi_l1_lag1" not in data
    chained = lag_feature(result, "ofi_l1", bucket_seconds=10, periods=2)
    assert chained["ofi_l1_lag2"].isna().all()


def test_lag_validates_width_and_configuration():
    for kwargs in [{"bucket_seconds": 5}, {"bucket_seconds": 0}, {"bucket_seconds": 10, "periods": 0}]:
        with pytest.raises(ValueError):
            lag_feature(frame(), "ofi_l1", **kwargs)


def test_loader_consumes_real_rust_outputs(bundle, tmp_path):
    from ofi_pipeline import PipelineConfig, run_pipeline

    report = run_pipeline(bundle, tmp_path / "computed", PipelineConfig(session_close="09:31:00"))
    data = load_features(report.features_path, required_columns=["ofi_l5"])
    assert len(data) == report.feature_rows == 3
    assert data["ofi_l1"].tolist() == [50, -20, 0]
