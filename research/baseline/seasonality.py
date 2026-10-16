"""Figures 5 and 6 of Cont, Kukanov, Stoikov (2011): intraday seasonality of price impact.

Per stock and half-hour window the module takes the price-impact coefficient ``beta_i`` (an
OFI-only fit), the average depth ``AD_i`` and the sample variances of the price change and of
OFI. For every stock these are averaged over days within each half-hour slot of the New York
trading day (so winter and summer sessions line up) and divided by the stock's own average over
all windows. The figures show the cross-stock mean of these normalised patterns:

* Figure 5: ``beta`` and ``AD`` (impact is highest where depth is lowest, at the open);
* Figure 6: ``var[dP]``, ``beta**2 * var[OFI]``, ``var[OFI]`` and ``beta`` (paper eq. 7,
  ``var[dP] ~ beta**2 var[OFI]``). ``beta**2 var[OFI]`` is built from the average patterns of
  its factors, as in the paper, and divided by the same constant as ``var[dP]`` so the two
  curves share one scale.

A slot needs ``min_days`` windows for a stock to count, and a stock needs ``min_slots`` valid
slots and a positive average ``beta`` (otherwise it cannot be normalised) to enter the average.
Excluded stocks are listed with the reason. This describes the sample; it is not a test.
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
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from ofi_pipeline.research import load_features
from research.baseline.depth_impact import KEYS, DepthImpactConfig, window_depth_betas

SERIES = ["beta", "depth", "var_dp", "var_ofi", "beta2_var_ofi"]
STAT_COLUMNS = ["beta", "avg_depth", "var_dp", "var_ofi"]

# Validated categorical slots and chart chrome (light surface); see the dataviz palette notes.
SURFACE, INK, INK_2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"


@dataclass(frozen=True)
class SeasonalityConfig:
    target: str = "mid_price_change_ticks"
    window_minutes: int = 30
    min_observations: int = 20
    min_days: int = 3
    min_slots: int = 8
    weight_column: str | None = "quote_update_count"
    timezone: str = "America/New_York"

    def __post_init__(self):
        for name in ("window_minutes", "min_observations", "min_days", "min_slots"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.target, str) or not self.target:
            raise ValueError("target must be a nonempty column name")
        if self.weight_column is not None and not isinstance(self.weight_column, str):
            raise ValueError("weight_column must be a column name or null")
        try:
            pd.Timestamp("2020-01-02", tz=self.timezone)
        except Exception as error:
            raise ValueError(f"unknown timezone: {self.timezone}") from error


def window_statistics(data: pd.DataFrame, config: SeasonalityConfig) -> pd.DataFrame:
    """Per fitted window: ``beta``, ``avg_depth``, ``var_dp`` and ``var_ofi`` and its slot.

    ``slot`` is the window's start in the exchange's local time (``HH:MM``). Variances are
    sample variances (ddof = 1) of the price change and of OFI over the window's buckets.
    """
    depth_config = DepthImpactConfig(
        target=config.target,
        window_minutes=config.window_minutes,
        min_observations=config.min_observations,
        weight_column=config.weight_column,
    )
    windows = window_depth_betas(data, depth_config)
    sample = data.dropna(subset=[config.target, "ofi_l1"]).copy()
    sample["window_start"] = sample["interval_start"].dt.floor(f"{config.window_minutes}min")
    spread = sample.groupby(KEYS).agg(
        var_dp=(config.target, lambda values: values.astype(float).var(ddof=1)),
        var_ofi=("ofi_l1", lambda values: values.astype(float).var(ddof=1)),
    )
    stats = windows.merge(spread.reset_index(), on=KEYS, how="left")
    stats = stats[stats["status"] == "ok"].copy()
    local = stats["window_start"].dt.tz_convert(config.timezone)
    stats["slot"] = local.dt.strftime("%H:%M")
    columns = [*KEYS, "slot", "observations", "beta", "avg_depth", "var_dp", "var_ofi"]
    return stats[columns].reset_index(drop=True)


def stock_patterns(stats: pd.DataFrame, config: SeasonalityConfig):
    """Normalised per-stock slot patterns and the stocks left out (with reasons).

    Returns ``(patterns, excluded)``. ``patterns`` has one row per stock and slot with the
    columns in ``SERIES`` (each divided by the stock's average over all its windows;
    ``beta2_var_ofi`` by the average ``var_dp``) and ``days``, the windows behind the slot.
    """
    rows, excluded = [], {}
    for symbol, group in stats.groupby("symbol"):
        divisors = {name: group[name].mean() for name in STAT_COLUMNS}
        if not divisors["beta"] > 0:
            excluded[symbol] = "average beta is not positive, so it cannot be normalised"
            continue
        slots = group.groupby("slot").agg(
            days=("beta", "size"),
            beta=("beta", "mean"),
            depth=("avg_depth", "mean"),
            var_dp=("var_dp", "mean"),
            var_ofi=("var_ofi", "mean"),
        )
        slots.loc[slots["days"] < config.min_days, SERIES[:4]] = np.nan
        if slots["beta"].notna().sum() < config.min_slots:
            excluded[symbol] = (
                f"fewer than {config.min_slots} slots with at least {config.min_days} windows"
            )
            continue
        slots["beta2_var_ofi"] = slots["beta"] ** 2 * slots["var_ofi"]
        slots["beta"] /= divisors["beta"]
        slots["depth"] /= divisors["avg_depth"]
        slots["var_ofi"] /= divisors["var_ofi"]
        slots["beta2_var_ofi"] /= divisors["var_dp"]  # same scale as var_dp, see module docs
        slots["var_dp"] /= divisors["var_dp"]
        slots.insert(0, "symbol", symbol)
        rows.append(slots.reset_index())
    patterns = (
        pd.concat(rows, ignore_index=True)
        if rows
        else pd.DataFrame(columns=["symbol", "slot", "days", *SERIES])
    )
    return patterns, excluded


def cross_stock_average(patterns: pd.DataFrame) -> pd.DataFrame:
    """Per slot: mean and interquartile range of each series across stocks, and stock count."""
    grouped = patterns.groupby("slot")
    out = {"stocks": grouped["beta"].count()}
    for name in SERIES:
        out[f"{name}_mean"] = grouped[name].mean()
        out[f"{name}_q25"] = grouped[name].quantile(0.25)
        out[f"{name}_q75"] = grouped[name].quantile(0.75)
    return pd.DataFrame(out).rename_axis("slot").reset_index().sort_values("slot")


def seasonal_summary(average: pd.DataFrame) -> dict:
    """Numbers the paper quotes: open versus average and close, and the eq. (7) agreement."""
    if average.empty:
        return {}
    first, last = average.iloc[0], average.iloc[-1]
    mean_of = {name: average[f"{name}_mean"].mean() for name in SERIES}
    var_dp, product = average["var_dp_mean"], average["beta2_var_ofi_mean"]
    both = var_dp.notna() & product.notna()
    return {
        "first_slot": first["slot"],
        "last_slot": last["slot"],
        "beta_open_over_average": float(first["beta_mean"] / mean_of["beta"]),
        "depth_open_over_average": float(first["depth_mean"] / mean_of["depth"]),
        "beta_open_over_close": float(first["beta_mean"] / last["beta_mean"]),
        "var_dp_peak_slot": str(average.loc[var_dp.idxmax(), "slot"]),
        "var_ofi_peak_slot": str(average.loc[average["var_ofi_mean"].idxmax(), "slot"]),
        "corr_var_dp_vs_beta2_var_ofi": (
            float(np.corrcoef(var_dp[both], product[both])[0, 1]) if both.sum() > 2 else None
        ),
        "mean_beta2_var_ofi_over_var_dp": float(mean_of["beta2_var_ofi"] / mean_of["var_dp"]),
    }


def _prepare_axes(fig: Figure, slots: list[str]):
    ax = fig.subplots()
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.grid(axis="y", color=GRID, linewidth=1, linestyle="-")
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.set_xticks(range(len(slots)), slots)
    ax.set_xlim(-0.5, len(slots) - 0.5 + 0.35)  # room for the right-hand value label
    ax.axhline(1.0, color=AXIS, linewidth=1, zorder=1)
    return ax


def _add_series(ax, average, name, label, color, marker, band):
    x = np.arange(len(average))
    mean = average[f"{name}_mean"].to_numpy(dtype=float)
    if band:
        ax.fill_between(
            x,
            average[f"{name}_q25"].to_numpy(dtype=float),
            average[f"{name}_q75"].to_numpy(dtype=float),
            color=color,
            alpha=0.10,
            linewidth=0,
        )
    ax.plot(
        x, mean, color=color, linewidth=2, marker=marker, markersize=5.5,
        markeredgecolor=SURFACE, markeredgewidth=1.5, solid_capstyle="round", label=label,
    )  # fmt: skip
    return Line2D(
        [], [], color=color, linewidth=2, marker=marker, markersize=6,
        markeredgecolor=SURFACE, label=label,
    )  # fmt: skip


def _finish(fig: Figure, ax, title: str, subtitle: str, handles, ylabel: str, log: bool = False):
    fig.suptitle(title, x=0.01, ha="left", fontsize=13, fontweight="semibold", color=INK)
    ax.set_title(subtitle, loc="left", fontsize=9, color=INK_2, pad=10)
    ax.set_ylabel(ylabel, fontsize=9, color=INK_2)
    ax.set_xlabel("Half-hour slot, New York time (start of window)", fontsize=9, color=INK_2)
    if log:
        # Ratios to an average are multiplicative: one log axis keeps a 5x spike from
        # flattening everything else, and halving and doubling sit at equal distances.
        values = np.concatenate([line.get_ydata() for line in ax.get_lines()])
        values = values[np.isfinite(values) & (values > 0)]
        ticks = [
            t
            for t in (0.125, 0.25, 0.5, 1, 2, 4, 8, 16)
            if values.min() / 1.4 < t < values.max() * 1.4
        ]
        ax.set_yscale("log", base=2)
        ax.set_ylim(values.min() / 1.3, values.max() * 1.3)
        ax.set_yticks(ticks, [f"{t:g}" for t in ticks])
        ax.minorticks_off()
    else:
        ax.set_ylim(bottom=0)
    fig.legend(
        handles=handles, loc="outside lower center", ncol=len(handles), frameon=False,
        fontsize=9, labelcolor=INK_2,
    )  # fmt: skip


def _label(ax, x, y, text):
    ax.annotate(
        text, (x, y), textcoords="offset points", xytext=(7, 7), fontsize=8.5, color=INK,
        ha="left", va="bottom",
    )  # fmt: skip


def figure5(average: pd.DataFrame, subtitle: str) -> Figure:
    """Figure 5: price-impact coefficient and average depth over the trading day."""
    fig = Figure(figsize=(8.6, 5.0), facecolor=SURFACE, layout="constrained")
    subtitle += "\nShaded band = interquartile range across stocks"
    ax = _prepare_axes(fig, average["slot"].tolist())
    handles = [
        _add_series(ax, average, "beta", "Price impact β", BLUE, "o", band=True),
        _add_series(ax, average, "depth", "Average depth AD", ORANGE, "s", band=True),
    ]
    beta, depth = average["beta_mean"], average["depth_mean"]
    _label(ax, 0, beta.iloc[0], f"β {beta.iloc[0]:.1f}× its average")
    _label(ax, 0, depth.iloc[0], f"AD {depth.iloc[0]:.1f}×")
    _label(ax, len(average) - 1, beta.iloc[-1], f"{beta.iloc[-1]:.1f}×")
    _finish(
        fig, ax, "Intraday price impact β and average depth AD", subtitle, handles,
        "Share of the stock's own average (1 = average)",
    )  # fmt: skip
    return fig


def figure6(average: pd.DataFrame, subtitle: str) -> Figure:
    """Figure 6: variance of price changes against beta squared times the variance of OFI."""
    fig = Figure(figsize=(8.6, 5.0), facecolor=SURFACE, layout="constrained")
    ax = _prepare_axes(fig, average["slot"].tolist())
    handles = [
        _add_series(ax, average, "var_dp", "var[ΔP]", BLUE, "o", band=False),
        _add_series(ax, average, "beta2_var_ofi", "β² · var[OFI]", ORANGE, "s", band=False),
        _add_series(ax, average, "beta", "β", AQUA, "D", band=False),
        _add_series(ax, average, "var_ofi", "var[OFI]", YELLOW, "^", band=False),
    ]
    _finish(
        fig, ax, "Intraday variance of ΔP and OFI, with β and β²·var[OFI]", subtitle, handles,
        "Share of the stock's own average (1 = average, log scale)", log=True,
    )  # fmt: skip
    return fig


def sample_label(stats: pd.DataFrame, patterns: pd.DataFrame, average: pd.DataFrame, venue: str):
    stocks, days = patterns["symbol"].nunique(), stats["date"].nunique()
    low, high = int(average["stocks"].min()), int(average["stocks"].max())
    per_slot = f"{low}-{high}" if low != high else f"{low}"
    return (
        f"{venue}: mean of {stocks} stocks ({per_slot} per slot) over {days} days; each stock "
        "divided by its own average"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", default="outputs/features/10s")
    parser.add_argument("--config", default="configs/seasonality.json")
    parser.add_argument("--output-dir", default="outputs/baseline/seasonality")
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--venue", default="NASDAQ", help="label used in the figure subtitles")
    args = parser.parse_args(argv)
    try:
        config = SeasonalityConfig(**json.loads(Path(args.config).read_text()))
        data = load_features(args.features, symbols=args.symbols)
        if data.empty:
            raise ValueError("No feature observations were selected")
        stats = window_statistics(data, config)
        patterns, excluded = stock_patterns(stats, config)
        if patterns.empty:
            raise ValueError("No stock has enough windows for seasonal patterns")
        average = cross_stock_average(patterns)
        summary = seasonal_summary(average)
        output = Path(args.output_dir)
        output.mkdir(parents=True, exist_ok=False)
        stats.to_csv(output / "window_statistics.csv", index=False)
        patterns.to_csv(output / "patterns_by_stock.csv", index=False)
        average.to_csv(output / "pattern_average.csv", index=False)
        subtitle = sample_label(stats, patterns, average, args.venue)
        figure5(average, subtitle).savefig(output / "fig5_impact_and_depth.png", dpi=200)
        figure6(average, subtitle).savefig(output / "fig6_variance.png", dpi=200)
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
            "stocks_in_average": sorted(patterns["symbol"].unique()),
            "stocks_excluded": excluded,
            "windows_used": len(stats),
            "summary": summary,
            "interpretation": "descriptive intraday patterns; no inference or OOS claim",
            "software_versions": {
                package: version(package)
                for package in ("ofi-pipeline", "numpy", "pandas", "matplotlib", "statsmodels")
            },
        }
        (output / "run.json").write_text(json.dumps(report, indent=2) + "\n")
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"seasonality: {error}\n")
    print(json.dumps({"output_dir": str(output), **report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
