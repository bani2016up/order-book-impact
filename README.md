# Order-book impact: pipeline and research workspace

One repository for the Rust feature engine and the team's Python research.
Rust computes OFI, price changes, trade imbalance, depth and volume. Researchers
consume saved features to reproduce the paper baseline or develop new models.

**Fedya's models go in `research/baseline/`. Timur's models go in
`research/extensions/`. Their tests go in `tests/research/`.**

## Structure and ownership

```text
crates/ofi-core/                Rust ingestion, validation, features and output
crates/ofi-python/              PyO3 native extension
python/ofi_pipeline/            Installed Python API and CLI
  research.py                  Installed shared loader and gap-safe lag helper
research/
  baseline/run.py              Fedya: runnable starter OLS comparison
  extensions/                  Timur: new model modules and entry points
  notebooks/                   Exploratory notebooks
configs/baseline.json          Reproducible model settings
scripts/
  setup.py                     Sync uv.lock; build Rust or install a current wheel
  prepare_features.py          Compute reusable features once in Rust
  wheel_check.py               Verify a built wheel outside the checkout
  coverage.py                  Measure implementation-layer coverage
tests/research/                Feature-loader, lag and model checks
tests/python/, integration/    API and actual compiled-extension checks
tests/real_sample/             Explicit delivered-data acceptance
docs/                          Contracts and recorded engine evidence
  diagrams/                    Editable architecture, data-flow, C4 and detail views
benchmarks/                    Engine performance tools
data/order_book_sample/        Local supplied dataset, ignored by Git
outputs/features/<name>/       Rust feature datasets and QC
outputs/baseline/<run>/        Baseline metrics, coefficients and figures
outputs/extensions/<run>/      Extension models, metrics and figures
dist/, target/                 Wheels/build artifacts, ignored by Git
pyproject.toml, uv.lock         Python dependency declarations and locked resolution
.python-version                Default Python 3.12 interpreter
```

Danya maintains the Rust engine and pipeline API. Fedya and Timur work in Python
with the same feature contract and environment. Shared reusable loading/adjacency
helpers belong in `ofi_pipeline.research`; do not duplicate event-level feature
computation in notebooks. Generated artifacts, real data and environments stay
out of Git. Standard build/cache directories remain local and ignored.

Work from the checkout containing the reviewed research-layer commits. Current
changes are local; the initial GitHub README alone does not contain this work.
Do not push until the owner authorizes it.

## Quick start

Run commands from the repository root. Use **Python >=3.12**, **uv >=0.9.13** and
Rust >=1.90 for source builds. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
first. uv creates/reuses `.venv`, installs the locked research/dev/test dependencies
and builds the editable Rust/PyO3 package in release mode with Cargo.lock enforced.
The default interpreter is Python 3.12; Python 3.13 is also in the CI matrix.

### 1. Install

macOS/Linux and Windows PowerShell use the same installation command:

```sh
uv sync --locked --all-extras
uv run --no-sync python -c "from ofi_pipeline import version; print(version())"
```

Run commands with `uv run --no-sync` to use the already synced environment.
The existing examples also work after activation:

```sh
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\Activate.ps1     # Windows PowerShell
```

With a current compatible wheel, no Rust compiler is needed:

```sh
uv run --no-project --python 3.12 python scripts/setup.py --wheel /path/to/current-compatible.whl
```

The wheel setup syncs locked dependencies without building the project, then
installs the supplied wheel with uv. Keep `--no-project` in that bootstrap command
so uv does not attempt a source build before the script can select the wheel.
Wheels are OS/CPU-specific; the
macOS ARM64 wheel is not a Windows/Linux wheel. A current wheel must contain
the `research` extra and shared helper. Model entry points/notebooks come from
this repository; the shared helper comes from the installed package.

`uv sync` without extras installs only the production package, which has no
Python runtime dependencies. Use `--all-extras` for this shared research workspace.
Use `uv run --no-sync` after syncing all extras: an implicit sync without extras
can remove optional research/test packages or replace a wheel installation with
an editable source build. After Rust changes, `uv sync --locked --all-extras`
detects Rust-source cache keys and rebuilds the extension. Review dependency
updates through `uv lock`, commit both pyproject.toml and uv.lock, and use
`uv lock --check` to verify consistency. Use `uv add --optional research NAME`
for model dependencies and `uv add --optional dev NAME` for developer tools.

### 2. Locate the data

Unpack Lev's complete bundle under `data/order_book_sample/`:

```text
data/order_book_sample/data/events_clean.parquet
data/order_book_sample/data/trades_clean.parquet
data/order_book_sample/reports/event_quality.parquet
data/order_book_sample/raw/                    for optional Quote Test
```

Keep hashes and the rest of the bundle together. Another absolute/local path is
also supported through `--sample-dir` or `run_pipeline(sample_dir=...)`. The core
API/CLI additionally supports `OFI_SAMPLE_DIR`. Real data is not shipped in Git
or the wheel. Do not silently substitute a different dataset when it is missing.

### 3. Compute features once

```sh
python scripts/prepare_features.py \
  --sample-dir data/order_book_sample \
  --output-dir outputs/features/10s
```

Defaults are 10-second intervals and five levels. Other widths are 1, 5, 30 and
60 seconds. Give each configuration its own new output directory. Outputs are
`features.parquet`, `bucket_quality.parquet`, `manifest.json` and
`quality_report.json`. Model runs reuse these files.

The installed CLI invokes the same Rust engine:

```sh
ofi-pipeline --sample-dir data/order_book_sample \
  --output-dir outputs/features/another-10s-run --bucket-seconds 10 --levels 5
```

Existing outputs are protected. For another run, choose another directory or use
the core API's explicitly documented owned-output replacement behavior.

### 4. Load from Python

```python
from ofi_pipeline.research import load_features, lag_feature

features = load_features("outputs/features/10s", required_columns=["ofi_l5"])
print(features[["symbol", "timestamp", "ofi_l1", "mid_price_change_ticks"]].head())
features = lag_feature(features, "ofi_l1", bucket_seconds=10, periods=1)
```

The loader accepts an output directory or Parquet filename, validates accepted
keys/UTC boundaries/numerical columns, sorts by symbol/date/time and preserves
unknown TI. Pass `symbols=["AAPL"]` to select one symbol. Lags stay missing across
gaps or sessions. Use absolute paths inside notebooks with a different working
directory; the helper itself imports from anywhere after installation.

To invoke Rust directly through the Python API:

```python
from ofi_pipeline import PipelineConfig, run_pipeline
from ofi_pipeline.research import load_features

report = run_pipeline(
    sample_dir="data/order_book_sample",
    output_dir="outputs/features/library-run",
    config=PipelineConfig(bucket_seconds=10, levels=5, threads=2, chunk_rows=65536),
)
features = load_features(report.features_path)
```

### 5. Run Fedya's starter baseline

```sh
python -m research.baseline.run \
  --features outputs/features/10s \
  --config configs/baseline.json \
  --output-dir outputs/baseline/run01
```

It fits OFI-only, TI-only and OFI+TI OLS per symbol and 30-minute window with an
intercept and White HC0 covariance. Models share complete-case observations.
Dropped rows and skipped windows (insufficient data, constant target or deficient
rank) remain explicit.

Outputs: `metrics.csv`, `coefficients.csv`, and `run.json` with the config and input
hash. `in_sample_r2` describes contemporaneous explanatory fit, not OOS accuracy.
This is a working starter, not a finished replication of every paper table.

## Where to put models

| Work | Code and configuration | Tests and generated output |
| --- | --- | --- |
| Fedya: baseline, nonlinear/depth regressions, paper tables | `research/baseline/<model>.py`, `configs/<model>.json` | `tests/research/test_<model>.py`, `outputs/baseline/<run>/` |
| Timur: Ridge/PCA, deep OFI, temporal/model extensions | `research/extensions/<model>.py`, `configs/<model>.json` | `tests/research/test_<model>.py`, `outputs/extensions/<run>/` |
| Either: exploration | `research/notebooks/<name>.ipynb` | Save large figures/artifacts under the relevant `outputs/` folder |
| Either: shared loading/temporal utilities | `python/ofi_pipeline/research.py` | Focused helper tests in `tests/research/` |

Give a new module a `main()` so it runs as `python -m research.extensions.<model>`
or `python -m research.baseline.<model>` from the root. Accept explicit feature,
config and output paths. Reuse the loader; save the input identity, target, units,
split, parameters and metrics with every run. Keep reusable functions outside
notebook cells. New output directories protect other people's experiments.

Add extra model dependencies to the `research` extra in `pyproject.toml`.
Rerun setup after dependency or compiled-code changes. Ordinary model edits need
no Rust rebuild; a notebook kernel may need restarting after imported code edits.

## Research semantics

- Price change is available in USD and ticks; OFI/TI/volume/depth are shares.
- UTC intervals are `(interval_start, timestamp]`. Excluded buckets are recorded
  in the quality table and must not be replaced by zero observations.
- Current OFI and target describe the **same** interval. Forecasting needs a
  separately constructed, temporally aligned future target.
- Verify adjacency before creating lags; never shift sparse accepted rows blindly.
- Quote Test may leave TI unknown; the loader retains the missing value.
- Deep OFI follows level rank, not a fixed price. Label it as an extension.
- OOS work needs time-based splits and train-only scaling/PCA/tuning. Current
  descriptive whole-day filtering is not train-only preprocessing.
- Two NASDAQ stocks from one day support development and preliminary fits,
  not the paper's month-scale NBBO robustness or guaranteed improvement.

## Checks and builds

```sh
uv run --no-sync python -m pytest -q tests/research
uv run --no-sync python -m pytest -q tests/python tests/integration tests/benchmarks
cargo test --workspace --locked
uv build --wheel --out-dir dist/uv-py312
uv run --no-sync python scripts/wheel_check.py 'dist/uv-py312/*.whl'
```

Use focused tests for your change, then broader tests when cross-layer behavior
changes. CI includes research checks and a platform wheel matrix, but hosted jobs
have not run while commits remain local. Share wheels through an owner-authorized
distribution step; do not commit binaries to Git.

## Detailed documentation

- [High-load benchmark and measured baseline](docs/high_load/README.md): reproducible
  1M/10M/20M scenarios, RSS snapshots and a comparison reference for Rust optimization.
- [Supervised Rust optimization results](docs/high_load/optimization-20261014.md):
  before/after regular and cold-input timings, memory tradeoffs and final acceptance.
- [Implementation diagram gallery](docs/diagrams/README.md): architecture, data flow,
  C4 levels 1–4, PyO3 sequence, Rust crates, core workers and research extension points.
- [API usage/configuration](docs/usage.md)
- [Architecture](docs/architecture.md)
- [Output columns/units](docs/output_contract.md)
- [Verified input schemas](docs/verified_schema.md)
- [Dataset contract](docs/DATASET_CONTRACT.md)
- [Engine tests](docs/testing.md) and [recorded coverage](docs/coverage.md)
- [Original engine handoff](docs/handoff.md): historical evidence before the
  research layer, not fresh coverage of new helper code or a new wheel hash
- [Change log](CHANGELOG.md) and [agent instructions](AGENTS.md)

## References

- [Paper](https://arxiv.org/pdf/1011.6402v3)
- [LOBSTER format](https://php.lobsterdata.com/info/DataStructure.php)
- [PyO3](https://pyo3.rs/) and [maturin](https://www.maturin.rs/)
- [statsmodels OLS](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.OLS.html)
