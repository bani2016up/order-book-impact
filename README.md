# order-book-impact-pipeline

Rust data-processing pipeline with a Python library interface through PyO3. The project supports methodological replication of Cont, Kukanov, and Stoikov's *The Price Impact of Order Book Events* using Lev's cleaned five-level LOBSTER sample.

## Current status

The pure Rust engine, compiled Python API/CLI, streaming Parquet/gzip CSV
adapters and atomic output are implemented. Known-direction 10-second output
has been independently checked against the delivered sample. Quote Test,
parallelism, coverage and distribution acceptance are still in progress.

Read [usage](docs/usage.md), [the dataset contract](docs/DATASET_CONTRACT.md),
[verified physical schemas](docs/verified_schema.md), and
[the implementation work log](CHANGELOG.md). The owner requested keeping the
previous implementation-task/work-log documents deleted. Work on local `main`,
make tested local commits, and **do not push**.

## Sample and boundaries

The supplied dataset description covers AAPL and MSFT on 2012-06-21, 09:30-16:00 America/New_York, with five order-book levels. It reports 887,810 cleaned events, 68,404 execution messages, and 4,390 valid 10-second intervals. These counts require verification against the delivered files.

The data is a single-venue NASDAQ sample, not the original paper's consolidated NBBO dataset. Known aggressor direction is the default trade-signing method. Invalid quote gaps and incomplete intervals must remain explicit.

Keep the real dataset outside version control. Point the implementation to the local `order_book_sample` directory through a configurable path or `OFI_SAMPLE_DIR`. Do not commit raw archives, full real-data Parquet files, environments, or generated output.

## References

- [Paper, March 2011 version](https://arxiv.org/pdf/1011.6402v3)
- [LOBSTER output structure](https://php.lobsterdata.com/info/DataStructure.php)
- [LOBSTER sample files](https://php.lobsterdata.com/info/DataSamples.php)
- [PyO3 guide](https://pyo3.rs/)
- [maturin mixed-project layout](https://www.maturin.rs/project_layout.html)
