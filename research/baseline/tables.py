"""Window-level summaries and paper-layout Tables 2 and 4 (Cont, Kukanov, Stoikov, 2011).

The inputs are the ``metrics`` and ``coefficients`` frames produced by
``research.baseline.run.fit_models``: one OLS fit per symbol/session/half-hour window.
Averages are taken over fitted windows only. A coefficient counts as significant when its
two-sided p-value is below the level; undefined p-values are ignored rather than counted
either way. Skipped windows stay visible in the model summary.

``inference`` chooses how significance is judged: ``hc0`` is the paper's z-test on White
(HC0) errors; ``hc3`` uses HC3 errors, which are far less liberal with ~180 observations
and heavy-tailed regressors; ``bootstrap`` uses the wild bootstrap-t p-value and reports
the mean HC3 z-statistic. ``hc0`` stays the default so the paper's tables are reproduced.
"""

import pandas as pd

SIGNIFICANCE_LEVEL = 0.05
AVERAGE_LABEL = "Average"
# inference -> (z-statistic column, p-value column) in the coefficients frame
INFERENCE_COLUMNS = {
    "hc0": ("z_statistic", "p_value"),
    "hc3": ("hc3_z_statistic", "hc3_p_value"),
    "bootstrap": ("hc3_z_statistic", "bootstrap_p_value"),
}

OFI_COLUMN = "ofi_l1"
QUADRATIC_COLUMN = "ofi_l1_signed_square"
TI_COLUMN = "trade_imbalance"
# Model names that the paper-layout tables look for in the fitted results.
TABLE_MODELS = {
    "table2": ("ofi_l1", "ofi_quadratic"),
    "table4": ("ofi_l1", "trade_imbalance", "ofi_and_ti"),
}

TERM_COLUMNS = [
    "symbol",
    "model",
    "term",
    "windows",
    "mean_estimate",
    "mean_z_statistic",
    "pct_significant",
]
MODEL_COLUMNS = [
    "symbol",
    "model",
    "fitted_windows",
    "skipped_windows",
    "mean_in_sample_r2",
    "mean_f_statistic",
    "mean_f_statistic_hc0",
]
TABLE2_COLUMNS = [
    "windows",
    "alpha",
    "t_alpha",
    "beta",
    "t_beta",
    "gamma_q",
    "t_gamma_q",
    "r2",
    "pct_alpha_sig",
    "pct_beta_sig",
    "pct_gamma_q_sig",
]
TABLE4_COLUMNS = [
    "windows",
    "ofi_r2",
    "ofi_t_beta",
    "ofi_pct_beta_sig",
    "ofi_f",
    "ti_r2",
    "ti_t_beta",
    "ti_pct_beta_sig",
    "ti_f",
    "both_r2",
    "both_t_theta_ofi",
    "both_t_theta_ti",
    "both_pct_theta_ofi_sig",
    "both_pct_theta_ti_sig",
    "both_f",
]


def _pct_significant(p_values: pd.Series, level: float) -> float:
    defined = p_values.dropna().astype(float)
    return float(100.0 * (defined < level).mean()) if len(defined) else float("nan")


def summarize_terms(
    coefficients: pd.DataFrame, level: float = SIGNIFICANCE_LEVEL, inference: str = "hc0"
) -> pd.DataFrame:
    """Per symbol/model/term: mean estimate, mean z-statistic and percent significant windows."""
    if inference not in INFERENCE_COLUMNS:
        raise ValueError(f"inference must be one of: {', '.join(INFERENCE_COLUMNS)}")
    z_column, p_column = INFERENCE_COLUMNS[inference]
    missing = {z_column, p_column}.difference(coefficients.columns)
    if missing:
        raise ValueError(f"coefficients lack columns for {inference}: {', '.join(sorted(missing))}")
    rows = []
    for (symbol, model, term), group in coefficients.groupby(["symbol", "model", "term"]):
        rows.append(
            {
                "symbol": symbol,
                "model": model,
                "term": term,
                "windows": len(group),
                "mean_estimate": float(group["estimate"].astype(float).mean()),
                "mean_z_statistic": float(group[z_column].astype(float).mean()),
                "pct_significant": _pct_significant(group[p_column], level),
            }
        )
    return pd.DataFrame(rows, columns=TERM_COLUMNS)


def summarize_models(metrics: pd.DataFrame) -> pd.DataFrame:
    """Per symbol/model: fitted and skipped windows and mean R-squared and F statistics."""
    rows = []
    for (symbol, model), group in metrics.groupby(["symbol", "model"]):
        fitted = group[group["status"] == "ok"]
        rows.append(
            {
                "symbol": symbol,
                "model": model,
                "fitted_windows": len(fitted),
                "skipped_windows": len(group) - len(fitted),
                "mean_in_sample_r2": float(fitted["in_sample_r2"].astype(float).mean()),
                "mean_f_statistic": float(fitted["f_statistic"].astype(float).mean()),
                "mean_f_statistic_hc0": float(fitted["f_statistic_hc0"].astype(float).mean()),
            }
        )
    return pd.DataFrame(rows, columns=MODEL_COLUMNS)


def _require(metrics: pd.DataFrame, table: str) -> None:
    missing = set(TABLE_MODELS[table]).difference(metrics["model"].unique())
    if missing:
        raise ValueError(f"{table} needs the models: {', '.join(sorted(missing))}")


def _term(terms: pd.DataFrame, model: str, term: str) -> pd.DataFrame:
    chosen = terms[(terms["model"] == model) & (terms["term"] == term)]
    return chosen.set_index("symbol")


def _fit(models: pd.DataFrame, model: str) -> pd.DataFrame:
    return models[models["model"] == model].set_index("symbol")


def _with_average(table: pd.DataFrame) -> pd.DataFrame:
    """Sort by symbol and append the cross-symbol mean row, as in the paper's last row."""
    table = table.sort_index()
    if table.empty:
        return table.rename_axis("symbol").reset_index()
    average = table.mean().to_frame(AVERAGE_LABEL).T
    return pd.concat([table, average]).rename_axis("symbol").reset_index()


def paper_table2(
    metrics: pd.DataFrame,
    coefficients: pd.DataFrame,
    level: float = SIGNIFICANCE_LEVEL,
    inference: str = "hc0",
) -> pd.DataFrame:
    """Table 2: price change on OFI, plus the quadratic OFI*|OFI| term.

    ``alpha``, ``beta`` and ``r2`` come from the linear ``ofi_l1`` model; ``gamma_q`` comes
    from the ``ofi_quadratic`` model. Columns prefixed ``t_`` are mean z-statistics and
    ``pct_*_sig`` are percent of windows significant at ``level`` under ``inference``.
    """
    _require(metrics, "table2")
    terms, models = summarize_terms(coefficients, level, inference), summarize_models(metrics)
    alpha = _term(terms, "ofi_l1", "const")
    beta = _term(terms, "ofi_l1", OFI_COLUMN)
    gamma = _term(terms, "ofi_quadratic", QUADRATIC_COLUMN)
    fit = _fit(models, "ofi_l1")
    table = pd.DataFrame(
        {
            "windows": fit["fitted_windows"],
            "alpha": alpha["mean_estimate"],
            "t_alpha": alpha["mean_z_statistic"],
            "beta": beta["mean_estimate"],
            "t_beta": beta["mean_z_statistic"],
            "gamma_q": gamma["mean_estimate"],
            "t_gamma_q": gamma["mean_z_statistic"],
            "r2": fit["mean_in_sample_r2"],
            "pct_alpha_sig": alpha["pct_significant"],
            "pct_beta_sig": beta["pct_significant"],
            "pct_gamma_q_sig": gamma["pct_significant"],
        }
    )
    return _with_average(table[TABLE2_COLUMNS])


def paper_table4(
    metrics: pd.DataFrame,
    coefficients: pd.DataFrame,
    level: float = SIGNIFICANCE_LEVEL,
    inference: str = "hc0",
) -> pd.DataFrame:
    """Table 4, Panel A: OFI alone, trade imbalance alone and both in one regression.

    ``ofi_*`` and ``ti_*`` come from the single-regressor models; ``both_*`` from
    ``ofi_and_ti`` (``theta`` coefficients). ``*_f`` is the mean classical overall F.
    ``windows`` counts fitted windows of the joint model.
    """
    _require(metrics, "table4")
    terms, models = summarize_terms(coefficients, level, inference), summarize_models(metrics)
    ofi = _term(terms, "ofi_l1", OFI_COLUMN)
    ti = _term(terms, "trade_imbalance", TI_COLUMN)
    theta_ofi = _term(terms, "ofi_and_ti", OFI_COLUMN)
    theta_ti = _term(terms, "ofi_and_ti", TI_COLUMN)
    fit_ofi, fit_ti = _fit(models, "ofi_l1"), _fit(models, "trade_imbalance")
    fit_both = _fit(models, "ofi_and_ti")
    table = pd.DataFrame(
        {
            "windows": fit_both["fitted_windows"],
            "ofi_r2": fit_ofi["mean_in_sample_r2"],
            "ofi_t_beta": ofi["mean_z_statistic"],
            "ofi_pct_beta_sig": ofi["pct_significant"],
            "ofi_f": fit_ofi["mean_f_statistic"],
            "ti_r2": fit_ti["mean_in_sample_r2"],
            "ti_t_beta": ti["mean_z_statistic"],
            "ti_pct_beta_sig": ti["pct_significant"],
            "ti_f": fit_ti["mean_f_statistic"],
            "both_r2": fit_both["mean_in_sample_r2"],
            "both_t_theta_ofi": theta_ofi["mean_z_statistic"],
            "both_t_theta_ti": theta_ti["mean_z_statistic"],
            "both_pct_theta_ofi_sig": theta_ofi["pct_significant"],
            "both_pct_theta_ti_sig": theta_ti["pct_significant"],
            "both_f": fit_both["mean_f_statistic"],
        }
    )
    return _with_average(table[TABLE4_COLUMNS])


def paper_tables(
    metrics: pd.DataFrame,
    coefficients: pd.DataFrame,
    level: float = SIGNIFICANCE_LEVEL,
    inference: str = "hc0",
) -> dict[str, pd.DataFrame]:
    """Every paper-layout table whose required models were fitted; others are omitted."""
    builders = {"table2": paper_table2, "table4": paper_table4}
    available = set(metrics["model"].unique())
    return {
        name: builders[name](metrics, coefficients, level, inference)
        for name, required in TABLE_MODELS.items()
        if set(required) <= available
    }
