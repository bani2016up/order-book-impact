# Model extensions: Timur

Put new model modules here, for example `ridge.py`, `pca.py`, or a named model
subdirectory. Run them from the repository root with `python -m research.extensions.<module>`.
Keep experiment settings in `configs/<model>.json`, tests in `tests/research/`, and
generated weights, metrics, plots, and run metadata in `outputs/extensions/<run-name>/`.

Consume the same Rust-produced feature table as the baseline:

```python
from ofi_pipeline.research import load_features, lag_feature

features = load_features("outputs/features/10s", required_columns=["ofi_l5"])
features = lag_feature(features, "ofi_l1", bucket_seconds=10)
```

`ofi_l1` through `ofi_l5` are rank-based contemporaneous order-flow features.
Use the baseline's sample, target, units, and split when comparing models.
Fit scalers/PCA/hyperparameters on train only and split by time, not random rows.
For next-interval forecasting, explicitly construct a future target with correct
time adjacency; the existing `mid_price_change_ticks` is for the same interval.
The helper preserves null lags across gaps and sessions; do not fill them with
zero. Unknown Quote Test TI is nullable, not a true zero.

The one-day sample is a development dataset, not evidence of month-scale
robustness or guaranteed OOS improvement. Current p95 cleaning was calibrated
on the full descriptive day; a forecasting claim needs train-only preprocessing
and a larger independent time history.

This directory contains no trained extension or claimed improvement yet.
