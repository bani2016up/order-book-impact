# order-book-impact-pipeline

Rust data-processing pipeline with a Python library interface through PyO3. The project supports methodological replication of Cont, Kukanov, and Stoikov's *The Price Impact of Order Book Events* using Lev's cleaned five-level LOBSTER sample.

## Current status

Implementation and local acceptance are complete: pure Rust core, compiled PyO3
Python API/CLI, streaming Parquet/gzip CSV adapters, known-direction and original
pre-execution Quote Test, bounded partition workers and atomic output.

All five bucket widths match the verified delivered/rebuilt sample references.
Final checks passed 79 Python/compiled tests, Rust suites, explicit real ingestion
and an isolated release-wheel install. Measured coverage: Rust core 99.5465%
(with eight documented missed guards/OS paths), native binding 100%, Python
100% lines/branches. Linux/macOS/Windows CI is configured but unrun remotely.

Read [the final handoff](docs/handoff.md), [usage](docs/usage.md),
[architecture](docs/architecture.md), [output columns and units](docs/output_contract.md),
[tests/coverage](docs/testing.md), and [the change log](CHANGELOG.md). The owner
requested keeping the earlier task/work-log documents deleted. All work is on
local `main`; nothing has been pushed or published.

## Usage

```python
from pathlib import Path
from ofi_pipeline import PipelineConfig, run_pipeline

report = run_pipeline(
    Path("/path/to/order_book_sample"),
    Path("/new/features"),
    PipelineConfig(bucket_seconds=10, levels=5, threads=2, chunk_rows=65536),
)
print(report.features_path, report.feature_rows)
```

Install a compatible prebuilt wheel with pip, or build from source with Python
>=3.10, Rust >=1.90 and maturin 1.9.6. The installed `ofi-pipeline` CLI calls the
same Rust core. Coworkers using a compatible wheel need no Rust compiler or
Python data libraries for production computation. See [installation](docs/usage.md).

## Sample and boundaries

Actual file inspection verified AAPL/MSFT on 2012-06-21, 09:30–16:00
America/New_York: 887810 clean events, 68404 executions and 897387 original
quality rows. Independent 10-second computation matches 4390 accepted intervals
out of 4680 (290 exclusions). All delivery hashes and five-level schemas were
checked; [reconciliation](docs/reconciliation.json) includes all five widths.

The sample is single-venue NASDAQ. OFI and price change are contemporaneous;
invalid gaps/intervals and unknown signing remain explicit. No forecasting or
profitability result is claimed. Real data and archives are ignored; select the
local `order_book_sample` directory or `OFI_SAMPLE_DIR`, and keep generated
outputs outside Git.

## References

- [Paper, March 2011 version](https://arxiv.org/pdf/1011.6402v3)
- [LOBSTER output structure](https://php.lobsterdata.com/info/DataStructure.php)
- [LOBSTER sample files](https://php.lobsterdata.com/info/DataSamples.php)
- [PyO3 guide](https://pyo3.rs/)
- [maturin mixed-project layout](https://www.maturin.rs/project_layout.html)
