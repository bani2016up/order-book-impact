"""Optional research helpers for Rust-produced features, never raw-event computation.

Install the ``research`` extra before importing this module. Keep it separate
from the top-level API so production pipeline users need no pandas dependency.
"""

from os import PathLike
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd  # type: ignore[import-untyped]  # Optional pandas has no bundled stubs.

KEYS = ["symbol", "date", "timestamp"]
REQUIRED = {
    *KEYS,
    "interval_start",
    "accepted",
    "ofi_l1",
    "mid_price_change_ticks",
    "avg_depth",
    "trade_imbalance",
    "volume",
}


def _ordered(frame: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing feature columns: {', '.join(sorted(missing))}")
    for column in ("interval_start", "timestamp"):
        dtype = frame[column].dtype
        if not isinstance(dtype, pd.DatetimeTZDtype) or str(dtype.tz) != "UTC":
            raise ValueError(f"{column} must contain timezone-aware UTC timestamps")
        if frame[column].isna().any():
            raise ValueError(f"{column} contains missing timestamps")
    if frame[["symbol", "date"]].isna().any().any():
        raise ValueError("symbol/date keys contain missing values")
    if frame.duplicated(KEYS).any():
        raise ValueError("Duplicate symbol/date/timestamp feature keys")
    if (
        not pd.api.types.is_bool_dtype(frame["accepted"])
        or frame["accepted"].isna().any()
        or not frame["accepted"].eq(True).all()
    ):
        raise ValueError("Load accepted features.parquet, not the all-bucket quality table")
    if not frame["interval_start"].lt(frame["timestamp"]).all():
        raise ValueError("Every feature interval must have start < end")
    numeric = [
        "mid_price_change_ticks",
        "avg_depth",
        "volume",
        "trade_imbalance",
        *(column for column in frame.columns if column.startswith("ofi_l")
          and column.removeprefix("ofi_l").isdigit()),
    ]
    for column in numeric:
        values = frame[column]
        if not pd.api.types.is_numeric_dtype(values) or pd.api.types.is_bool_dtype(values):
            raise ValueError(f"{column} must be numeric")
        if column != "trade_imbalance" and values.isna().any():
            raise ValueError(f"Accepted feature {column} contains missing values")
        if not np.isfinite(values.dropna().to_numpy(dtype=float)).all():
            raise ValueError(f"{column} contains non-finite values")
    return frame.sort_values(KEYS, kind="stable").reset_index(drop=True)


def load_features(
    path: str | PathLike[str],
    *,
    required_columns: Sequence[str] = (),
    symbols: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Load and validate a features file or a pipeline output directory.

    Unknown Quote Test TI stays nullable. This function neither fills excluded
    intervals nor runs the event pipeline. Returned rows sort by session keys.
    """
    source = Path(path).expanduser()
    if source.is_dir():
        source = source / "features.parquet"
    if isinstance(required_columns, str) or isinstance(symbols, str):
        raise ValueError("required_columns and symbols must be sequences, not strings")
    frame = _ordered(pd.read_parquet(source))
    missing = set(required_columns).difference(frame.columns)
    if missing:
        raise ValueError(f"Missing requested model features: {', '.join(sorted(missing))}")
    if symbols is not None:
        absent = set(symbols).difference(frame["symbol"])
        if absent:
            raise ValueError(f"Unknown symbols: {', '.join(sorted(absent))}")
        frame = frame[frame["symbol"].isin(symbols)].reset_index(drop=True)
    return frame


def lag_feature(
    frame: pd.DataFrame,
    column: str,
    *,
    bucket_seconds: int,
    periods: int = 1,
    name: str | None = None,
) -> pd.DataFrame:
    """Add a lag only when every intervening interval is temporally adjacent.

    Never crosses a symbol/session or a missing bucket. Initial/unknown values
    remain missing; the input frame is not mutated.
    """
    if type(bucket_seconds) is not int or bucket_seconds <= 0:
        raise ValueError("bucket_seconds must be a positive integer")
    if type(periods) is not int or periods <= 0:
        raise ValueError("periods must be a positive integer")
    result = _ordered(frame)
    if column not in result:
        raise ValueError(f"Unknown lag column: {column}")
    target = name or f"{column}_lag{periods}"
    if target in result:
        raise ValueError(f"Lag output column already exists: {target}")
    width = pd.Timedelta(seconds=bucket_seconds)
    if not result["timestamp"].sub(result["interval_start"]).eq(width).all():
        raise ValueError("bucket_seconds disagrees with actual feature interval widths")
    group_keys = [result["symbol"], result["date"]]
    gaps = result.groupby(["symbol", "date"], sort=False)["timestamp"].diff()
    valid = pd.Series(True, index=result.index)
    for offset in range(periods):
        valid &= gaps.groupby(group_keys, sort=False).shift(offset).eq(width)
    shifted = result.groupby(["symbol", "date"], sort=False)[column].shift(periods)
    result[target] = shifted.where(valid)
    return result
