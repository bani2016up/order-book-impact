# Python API and installation

Supported: Python >=3.10, Rust >=1.90 for source builds. The extension uses the
stable Python ABI. A compatible prebuilt wheel needs no Rust installation.
Production dependencies are compiled into the native library; Python does not
need PyArrow or pandas to compute features.

For development, create a Python environment, install maturin, then:

```sh
VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --locked
```

```python
from pathlib import Path
from ofi_pipeline import PipelineConfig, run_pipeline

report = run_pipeline(
    sample_dir=Path("/path/to/order_book_sample"),
    output_dir=Path("/path/to/new/features"),
    config=PipelineConfig(bucket_seconds=10, levels=5, chunk_rows=65536, threads=1),
)
print(report.features_path, report.feature_rows)
```

Use `InputPaths(events=..., trades=..., quality=...)` with the keyword `inputs`
for explicit file layouts. `sample_dir` and `inputs` are mutually exclusive. If
both are absent, `OFI_SAMPLE_DIR` supplies the directory. Parquet is preferred;
headered gzip CSV preserves UTC nanoseconds and integer local `time_ns` exactly.
Physical column names/types follow the explicit Lev-v1 schema in
[verified_schema.md](verified_schema.md). Unsupported aliases fail validation.

The installed `ofi-pipeline --sample-dir /path/to/sample --output-dir /new/output`
and `python -m ofi_pipeline` call the same API. The return value is typed metadata,
never event rows. Larger outputs stay on disk.

The output directory must be new. `overwrite=True` replaces an existing owned
pipeline dataset only; directories containing other user files are protected.
Files are staged and the completed directory is published by rename. Existing
results are retained on computation failure. Explicit overwrite briefly moves
old output aside during publication; this is not a database transaction against
external simultaneous directory mutations.

Feature intervals are contemporaneous, right-closed `(interval_start, timestamp]`.
Timestamp columns are UTC nanoseconds; date is the New York session date. Prices
are USD, price changes also include ticks, and OFI/TI/volume/depth are shares.
Signed values are int64. Excluded intervals are only in `bucket_quality.parquet`,
with reasons and null computed features. Verify actual temporal adjacency and
session before creating lags from sparse accepted rows. Deep OFI is a rank-based
research extension. The data is single-venue NASDAQ, not consolidated NBBO.

`trade_signing="quote_test"` uses original pre-execution quotes. Sample-directory
mode discovers vendor ZIP names; explicit mode accepts
`InputPaths(..., raw=(RawInput(symbol="AAPL", date="2012-06-21", archive=...),))`
or a `RawInput` with `message` and `orderbook` CSV paths. Pairing is by original
row index. Inside-spread trades and missing/invalid pre-quotes remain unclassified;
QC exposes their counts/volume. Quote Test TI is not the known-direction oracle.
ZIP contents spool once to owned temporary disk files, then stream by paired rows;
RAM stays bounded, while temporary disk usage scales with archive payload size.
Spools are removed before publication. No filtering is recalibrated.

`threads` bounds independent symbol/session workers. The input producer validates
and merges the ordered streams once; each worker receives chunks through a queue
with capacity one and keeps its own persistent state. Partition outputs are
staged and assembled in deterministic key order. A session is never divided
between independently initialized workers. QC records the observed peak worker
count. Memory scales with chunk size and the configured worker bound, not event
count; temporary disk contains per-partition output (and raw ZIP spools for Quote
Test). Output assembly reads those small intermediate Parquet files once.
