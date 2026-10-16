"""Table 3 of Cont, Kukanov, Stoikov (2011): price impact against market depth.

Per stock, the half-hour price-impact coefficients ``beta_i`` (from ``dP = alpha + beta*OFI``)
are related to the window's average depth ``AD_i`` by ``beta_i = c / AD_i**lambda``:

* ``log beta_i = a - lambda * log AD_i + e_i``  (paper eq. 5), then
* ``beta_i = m + c * AD_i**(-lambda_hat) + e_i``  (paper eq. 6, ``lambda`` from eq. 5).

Standard errors are Newey-West (Bartlett kernel) over the stock's chronologically ordered
windows and confidence intervals use normal critical values, as in the paper. ``beta_i`` is
estimated on every accepted bucket with a known price change and OFI, independently of
trade imbalance, so unknown trade signs never shrink the sample. Windows with a
non-positive ``beta_i`` have no logarithm and are dropped and counted.
"""

import argparse
from dataclasses import asdict, dataclass
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from scipy.stats import norm
import statsmodels.api as sm

from ofi_pipeline.research import load_features
from research.baseline.run import BaselineConfig, fit_models

AVERAGE_LABEL = "Average"
KEYS = ["symbol", "date", "window_start"]
TABLE3_COLUMNS = [
    "windows",
    "dropped_windows",
    "c",
    "lambda_hat",
    "t_c",
    "t_lambda",
    "c_low",
    "c_high",
    "lambda_low",
    "lambda_high",
    "r2_loglog",
    "corr2_fitted",
    "corr2_inverse_depth",
    "p_lambda_eq_1",
    "lambda_eq_1_not_rejected",
]


@dataclass(frozen=True)
class DepthImpactConfig:
    target: str = "mid_price_change_ticks"
    window_minutes: int = 30
    min_observations: int = 20
    min_windows: int = 8
    hac_lags: int | None = None
    level: float = 0.05
    weight_column: str | None = "quote_update_count"

    def __post_init__(self):
        if not isinstance(self.target, str) or not self.target:
            raise ValueError("target must be a nonempty column name")
        for name in ("window_minutes", "min_observations"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.min_windows) is not int or self.min_windows < 4:
            raise ValueError("min_windows must be an integer of at least 4")
        if self.hac_lags is not None and (type(self.hac_lags) is not int or self.hac_lags < 0):
            raise ValueError("hac_lags must be null (automatic) or a nonnegative integer")
        if not isinstance(self.level, float) or not 0 < self.level < 1:
            raise ValueError("level must be a float strictly between 0 and 1")
        if self.weight_column is not None and not isinstance(self.weight_column, str):
            raise ValueError("weight_column must be a column name or null")


def newey_west_lags(windows: int) -> int:
    """Newey-West's automatic Bartlett bandwidth, floor(4 * (T / 100) ** (2 / 9))."""
    return max(1, int(np.floor(4 * (windows / 100) ** (2 / 9))))


def window_depth_betas(data: pd.DataFrame, config: DepthImpactConfig) -> pd.DataFrame:
    """One row per symbol/session/half-hour window: ``beta`` and the window's average depth.

    ``avg_depth`` is the mean of the buckets' L1 depth weighted by their number of quote
    updates (the paper averages over quote updates); without a weight column it is an
    unweighted mean of the buckets.
    """
    if "avg_depth" not in data:
        raise ValueError("Missing feature column: avg_depth")
    if config.weight_column is not None and config.weight_column not in data:
        raise ValueError(f"Missing weight column: {config.weight_column}")
    ofi_only = BaselineConfig(
        target=config.target,
        window_minutes=config.window_minutes,
        min_observations=config.min_observations,
        models={"ofi_l1": ["ofi_l1"]},
    )
    metrics, coefficients = fit_models(data, ofi_only)
    betas = coefficients[(coefficients["model"] == "ofi_l1") & (coefficients["term"] == "ofi_l1")]
    betas = betas[[*KEYS, "estimate"]].rename(columns={"estimate": "beta"})
    sample = data.dropna(subset=[config.target, "ofi_l1"]).copy()
    sample["window_start"] = sample["interval_start"].dt.floor(f"{config.window_minutes}min")
    if config.weight_column is None:
        sample["weight"] = 1.0
    else:
        sample["weight"] = sample[config.weight_column].astype(float)
    sample["weighted_depth"] = sample["avg_depth"].astype(float) * sample["weight"]
    grouped = sample.groupby(KEYS)
    total = grouped["weight"].sum()
    depth = (grouped["weighted_depth"].sum() / total).where(total > 0, grouped["avg_depth"].mean())
    depth = depth.rename("avg_depth").reset_index()
    fitted = metrics[metrics["model"] == "ofi_l1"][[*KEYS, "observations", "status"]]
    windows = fitted.merge(betas, on=KEYS, how="left").merge(depth, on=KEYS, how="left")
    return windows.sort_values(KEYS).reset_index(drop=True)


def _undefined_row(windows: int, dropped: int) -> dict:
    row = {name: np.nan for name in TABLE3_COLUMNS}
    return {**row, "windows": windows, "dropped_windows": dropped}


def fit_depth_law(
    beta: np.ndarray, depth: np.ndarray, config: DepthImpactConfig, dropped: int = 0
) -> dict:
    """Fit paper eqs. (5) and (6) for one stock; windows must be in chronological order."""
    beta, depth = np.asarray(beta, dtype=float), np.asarray(depth, dtype=float)
    keep = np.isfinite(beta) & np.isfinite(depth) & (beta > 0) & (depth > 0)
    dropped += int((~keep).sum())
    beta, depth = beta[keep], depth[keep]
    if len(beta) < config.min_windows or np.ptp(np.log(depth)) == 0:
        return _undefined_row(len(beta), dropped)
    lags = config.hac_lags if config.hac_lags is not None else newey_west_lags(len(beta))
    hac = {"cov_type": "HAC", "cov_kwds": {"maxlags": lags}, "use_t": False}
    loglog = sm.OLS(np.log(beta), sm.add_constant(np.log(depth))).fit(**hac)
    lam, lam_se = -np.float64(loglog.params[1]), np.float64(loglog.bse[1])
    inverse_power = depth ** (-lam)
    scale = sm.OLS(beta, sm.add_constant(inverse_power)).fit(**hac)
    c, c_se = np.float64(scale.params[1]), np.float64(scale.bse[1])
    critical = float(norm.ppf(1 - config.level / 2))
    with np.errstate(divide="ignore", invalid="ignore"):  # exact fits have zero standard errors
        z_lambda_one = abs(lam - 1) / lam_se
        t_c, t_lambda = c / c_se, lam / lam_se
    p_lambda_one = float(2 * norm.sf(z_lambda_one))
    return {
        "windows": len(beta),
        "dropped_windows": dropped,
        "c": float(c),
        "lambda_hat": float(lam),
        "t_c": float(t_c),
        "t_lambda": float(t_lambda),
        "c_low": float(c - critical * c_se),
        "c_high": float(c + critical * c_se),
        "lambda_low": float(lam - critical * lam_se),
        "lambda_high": float(lam + critical * lam_se),
        "r2_loglog": float(loglog.rsquared),
        "corr2_fitted": float(np.corrcoef(beta, inverse_power)[0, 1] ** 2),
        "corr2_inverse_depth": float(np.corrcoef(beta, 1.0 / depth)[0, 1] ** 2),
        "p_lambda_eq_1": p_lambda_one,
        "lambda_eq_1_not_rejected": float(p_lambda_one >= config.level),
    }


def paper_table3(windows: pd.DataFrame, config: DepthImpactConfig) -> pd.DataFrame:
    """Table 3: one row per symbol and a cross-symbol ``Average`` row.

    ``lambda_eq_1_not_rejected`` is 1.0/0.0 per stock (so the average row is the share of
    stocks for which lambda = 1 cannot be rejected, the paper's "35 out of 50").
    Fit measures: ``r2_loglog`` is the R-squared of eq. (5); ``corr2_fitted`` and
    ``corr2_inverse_depth`` are squared correlations of beta with ``AD**(-lambda_hat)`` and
    with ``1/AD`` (the lambda = 1 prediction). Symbols with too few windows keep NaN fits.
    """
    rows = {}
    usable = windows[windows["status"] == "ok"]
    for symbol, group in windows.groupby("symbol"):
        good = usable[usable["symbol"] == symbol]
        rows[symbol] = fit_depth_law(
            good["beta"].to_numpy(), good["avg_depth"].to_numpy(), config, len(group) - len(good)
        )
    table = pd.DataFrame.from_dict(rows, orient="index", columns=TABLE3_COLUMNS).sort_index()
    if table.empty:
        return table.rename_axis("symbol").reset_index()
    average = table.mean().to_frame(AVERAGE_LABEL).T
    return pd.concat([table, average]).rename_axis("symbol").reset_index()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", default="outputs/features/10s")
    parser.add_argument("--config", default="configs/depth_impact.json")
    parser.add_argument("--output-dir", default="outputs/baseline/table3")
    parser.add_argument("--symbols", nargs="+")
    args = parser.parse_args(argv)
    try:
        config = DepthImpactConfig(**json.loads(Path(args.config).read_text()))
        data = load_features(args.features, symbols=args.symbols)
        if data.empty:
            raise ValueError("No feature observations were selected")
        windows = window_depth_betas(data, config)
        table = paper_table3(windows, config)
        output = Path(args.output_dir)
        output.mkdir(parents=True, exist_ok=False)
        windows.to_csv(output / "window_betas.csv", index=False)
        table.to_csv(output / "table3.csv", index=False)
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
            "standard_errors": "Newey-West (Bartlett), automatic bandwidth unless hac_lags is set",
            "confidence_intervals": "normal critical values",
            "interpretation": "contemporaneous in-sample relation of impact to depth; no OOS claim",
            "windows_total": len(windows),
            "windows_fitted": int(windows["status"].eq("ok").sum()),
            "symbols_with_fit": int(table.loc[table["symbol"] != AVERAGE_LABEL, "c"].notna().sum()),
            "software_versions": {
                package: version(package)
                for package in ("ofi-pipeline", "numpy", "pandas", "statsmodels", "scipy")
            },
        }
        (output / "run.json").write_text(json.dumps(report, indent=2) + "\n")
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"depth_impact: {error}\n")
    print(json.dumps({"output_dir": str(output), **report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
