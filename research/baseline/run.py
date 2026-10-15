"""Starter contemporaneous OLS models, estimated per symbol/half-hour with HC0 errors."""

import argparse
from dataclasses import asdict, dataclass, field
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import statsmodels.api as sm

from ofi_pipeline.research import load_features
from research.baseline.tables import (
    SIGNIFICANCE_LEVEL,
    paper_tables,
    summarize_models,
    summarize_terms,
)


@dataclass(frozen=True)
class BaselineConfig:
    target: str = "mid_price_change_ticks"
    window_minutes: int = 30
    min_observations: int = 20
    models: dict[str, list[str]] = field(
        default_factory=lambda: {
            "ofi_l1": ["ofi_l1"],
            "trade_imbalance": ["trade_imbalance"],
            "ofi_and_ti": ["ofi_l1", "trade_imbalance"],
            "ofi_quadratic": ["ofi_l1", "ofi_l1_signed_square"],
        }
    )

    def __post_init__(self):
        if not isinstance(self.target, str) or not self.target:
            raise ValueError("target must be a nonempty column name")
        for name in ("window_minutes", "min_observations"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.models, dict) or not self.models:
            raise ValueError("models must be a nonempty mapping")
        for name, columns in self.models.items():
            if (
                not isinstance(name, str)
                or not name
                or not isinstance(columns, list)
                or not columns
            ):
                raise ValueError("every model needs a name and a nonempty column list")
            if any(not isinstance(column, str) or not column for column in columns):
                raise ValueError("model columns must be nonempty strings")
            if len(columns) != len(set(columns)) or self.target in columns or "const" in columns:
                raise ValueError("model columns must be unique and exclude the target/const")


SIGNED_SQUARE = "_signed_square"


def add_signed_squares(data: pd.DataFrame, columns) -> pd.DataFrame:
    """Return a copy with ``<x>_signed_square = x * |x|`` for each requested derived column.

    This is the paper's quadratic term OFI*|OFI|. A column that already exists is never
    replaced, and a name whose base column is absent is left for the caller to report.
    """
    frame = data.copy()
    for column in sorted(columns):
        base = column.removesuffix(SIGNED_SQUARE)
        if not column.endswith(SIGNED_SQUARE) or column in frame.columns or base not in frame:
            continue
        if not pd.api.types.is_numeric_dtype(frame[base]):
            raise ValueError(f"Model column must be numeric: {base}")
        values = frame[base].astype(float)
        frame[column] = values * values.abs()
    return frame


def fit_models(data: pd.DataFrame, config: BaselineConfig):
    """Compare models on common complete cases; skipped windows remain explicit.

    Besides ``in_sample_r2`` the metrics hold two overall F statistics: ``f_statistic`` is the
    classical homoskedastic F and ``f_statistic_hc0`` is statsmodels' HC0 Wald F. A model column
    named ``<x>_signed_square`` is derived as ``x * |x|`` when the data lack it.
    """
    required = {config.target, *(c for columns in config.models.values() for c in columns)}
    frame = add_signed_squares(data, required)
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing model columns: {', '.join(sorted(missing))}")
    for column in required:
        if not pd.api.types.is_numeric_dtype(frame[column]):
            raise ValueError(f"Model column must be numeric: {column}")
        if not np.isfinite(frame[column].dropna().to_numpy(dtype=float)).all():
            raise ValueError(f"Model column contains non-finite values: {column}")
    # This starter follows the paper's regular-session :00/:30 half-hour grid.
    frame["window_start"] = frame["interval_start"].dt.floor(f"{config.window_minutes}min")
    metrics, coefficients = [], []
    for (symbol, date, start), group in frame.groupby(
        ["symbol", "date", "window_start"], sort=True
    ):
        common = group.dropna(subset=sorted(required))
        for name, columns in config.models.items():
            row = {
                "symbol": symbol,
                "date": date,
                "window_start": start,
                "model": name,
                "total_rows": len(group),
                "observations": len(common),
                "dropped_incomplete_rows": len(group) - len(common),
                "status": "ok",
                "in_sample_r2": None,
                "f_statistic": None,
                "f_statistic_hc0": None,
            }
            if len(common) < max(config.min_observations, len(columns) + 2):
                row["status"] = "insufficient_observations"
            elif common[config.target].nunique() < 2:
                row["status"] = "constant_target"
            else:
                design = sm.add_constant(common[columns].astype(float), has_constant="add")
                if np.linalg.matrix_rank(design.to_numpy()) < design.shape[1]:
                    row["status"] = "rank_deficient"
                else:
                    result = sm.OLS(
                        common[config.target].astype(float), design, missing="raise"
                    ).fit(
                        cov_type="HC0",
                        use_t=False,
                    )
                    r2 = float(result.rsquared)
                    residual_share = (1.0 - r2) / (len(common) - len(columns) - 1)
                    row["in_sample_r2"] = r2
                    row["f_statistic"] = (
                        (r2 / len(columns)) / residual_share if residual_share > 0 else float("inf")
                    )
                    row["f_statistic_hc0"] = float(result.fvalue)
                    for term in result.params.index:
                        coefficients.append(
                            {
                                "symbol": symbol,
                                "date": date,
                                "window_start": start,
                                "model": name,
                                "term": term,
                                "estimate": result.params[term],
                                "hc0_standard_error": result.bse[term],
                                "z_statistic": result.tvalues[term],
                                "p_value": result.pvalues[term],
                            }
                        )
            metrics.append(row)
    return pd.DataFrame(metrics), pd.DataFrame(
        coefficients,
        columns=[
            "symbol",
            "date",
            "window_start",
            "model",
            "term",
            "estimate",
            "hc0_standard_error",
            "z_statistic",
            "p_value",
        ],
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", default="outputs/features/10s")
    parser.add_argument("--config", default="configs/baseline.json")
    parser.add_argument("--output-dir", default="outputs/baseline/run01")
    parser.add_argument("--symbols", nargs="+")
    args = parser.parse_args(argv)
    try:
        config = BaselineConfig(**json.loads(Path(args.config).read_text()))
        data = load_features(args.features, symbols=args.symbols)
        if data.empty:
            raise ValueError("No feature observations were selected")
        metrics, coefficients = fit_models(data, config)
        output = Path(args.output_dir)
        output.mkdir(parents=True, exist_ok=False)
        metrics.to_csv(output / "metrics.csv", index=False)
        coefficients.to_csv(output / "coefficients.csv", index=False)
        summarize_models(metrics).to_csv(output / "summary_models.csv", index=False)
        summarize_terms(coefficients).to_csv(output / "summary_terms.csv", index=False)
        tables = paper_tables(metrics, coefficients)
        for name, table in tables.items():
            table.to_csv(output / f"{name}.csv", index=False)
        source = Path(args.features)
        source = source / "features.parquet" if source.is_dir() else source
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        report = {
            "feature_file": str(source.resolve()),
            "feature_sha256": digest.hexdigest(),
            "config": asdict(config),
            "covariance": "HC0",
            "significance": {
                "level": SIGNIFICANCE_LEVEL,
                "test": "two-sided z-test on HC0 standard errors",
            },
            "paper_tables": sorted(tables),
            "paper_table_f_statistic": "classical homoskedastic overall F",
            "common_complete_cases": True,
            "interpretation": "contemporaneous in-sample explanation; no OOS claim",
            "fitted_windows": int(metrics["status"].eq("ok").sum()),
            "skipped_windows": int(metrics["status"].ne("ok").sum()),
            "selected_rows": len(data),
            "software_versions": {
                package: version(package)
                for package in ("ofi-pipeline", "numpy", "pandas", "statsmodels")
            },
        }
        (output / "run.json").write_text(json.dumps(report, indent=2) + "\n")
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"baseline: {error}\n")
    print(json.dumps({"output_dir": str(output), **report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
