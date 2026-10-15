# Python API and installation

For the team workspace and one-command setup, start with [README](../README.md).
The canonical bundle is `data/order_book_sample/`; external paths remain supported.
Shared model data helpers are installed as `ofi_pipeline.research` with the optional
`research` dependency extra. Model entry points live in `research/baseline/` and
`research/extensions/` in the source checkout.

Supported: Python >=3.12, uv >=0.9.13, Rust >=1.90 for source builds. The extension
uses the stable Python ABI with a Python 3.12 minimum (`cp312-abi3`). A compatible
prebuilt wheel needs no Rust installation.
Production dependencies are compiled into the native library; Python does not
need PyArrow or pandas to compute features.

For development, sync the checked-in uv.lock from the repository root:

```sh
uv sync --locked --all-extras
uv run --no-sync python -c "from ofi_pipeline import version; print(version())"
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
Signed values are int64. With unclassified Quote Test executions, full
`trade_imbalance` is null; `classified_trade_imbalance` keeps the observed partial
sum and `trade_signing_complete` is false. `SigningCoverage.trade_imbalance` is the
classified sum, while `complete_trade_imbalance` returns None when incomplete.
Excluded intervals are only in `bucket_quality.parquet`,
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

`max_partitions` bounds report metadata (default 1024, maximum 16384). Split large
file sets or raise it explicitly; live workers still obey `threads`. Lev-v1
rejection reasons are `outside_session`, `invalid_book`, `invalid_event`, and
`spread_above_p95`. Original quality rows must cover the configured session;
unsupported schema/reason conventions fail explicitly. In excluded quality
rows, `quote_update_count` counts accepted L1 updates whose supplied markers are
available; valid feature rows have complete original L1-update counts.


## Configuration and errors

| Setting | Default and supported values |
| --- | --- |
| `bucket_seconds` | 10; one of 1, 5, 10, 30, 60. |
| `levels` | 5; 1..5, with required physical levels present. |
| `trade_signing` | `lobster_direction`; alternatively `quote_test` with original paired input. |
| `chunk_rows`, `threads` | 65536 and 2; ranges 1..1048576 and 1..64. |
| `max_partitions` | 1024; 1..16384. |
| `session_timezone`, `session_date` | `America/New_York`; optional date constrains every input partition. |
| `session_open`, `session_close` | `09:30:00`, `16:00:00`; increasing local clocks with duration divisible by width. |
| `tick_size` | 0.01 USD; positive value exactly representable in USD/10000 units. |
| `adapter_version`, `quality_policy` | `lev-v1`, `supplied-clean`. |
| `overwrite` | False; explicit replacement of owned result directories only. |

`RunReport` exposes four output paths, immutable configuration, per-partition
counts/signing/precision summaries, schema/algorithm versions, warnings, elapsed
seconds and observed peak workers. See [output_contract.md](output_contract.md)
for the full Parquet schema and examples of boundary/lag semantics.

All public errors derive from `PipelineError`: `ConfigurationError`,
`SchemaError`, `OrderingError`, `QualityEvidenceError`, `MissingInputError`,
`MalformedDataError`, `ArithmeticOverflowError`, and `PipelineIOError`.
Messages include source rows and symbol/event/session/bucket context when
available. CLI failures print an error and return a nonzero status. Fix the input
or configuration indicated by the exception; computation never silently sorts,
repairs or fills unavailable evidence.

To install a compatible local wheel without a compiler:

```sh
uv run --no-project --python 3.12 python scripts/setup.py --wheel /path/to/ofi_pipeline-0.1.0-compatible-platform.whl
uv run --no-sync ofi-pipeline --sample-dir /path/to/order_book_sample --output-dir /new/result \
  --bucket-seconds 10 --levels 5 --threads 2 --chunk-rows 65536
```

Use the actual platform-specific filename from the release build. Local testing
covers macOS arm64/Python 3.12 and 3.13; the committed CI matrix builds Linux/macOS/Windows
on Python 3.12/3.13 after the owner pushes. Those hosted builds are unrun here.
