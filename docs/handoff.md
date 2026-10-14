# Implementation handoff — 2026-10-14

All required local implementation milestones M0–M11 are complete. The pure Rust
engine owns streaming ingestion, validation, original-event sequencing, checked
L1–L5 rank OFI, independent execution signing, original-boundary right-closed
aggregation, depth/volume and Parquet/provenance/QC output. The imported PyO3
shared library releases the GIL around a coarse file-set call; the thin typed
Python API and installed CLI invoke that same core. No production Python feature
engine, per-event callback or subprocess facade exists. The optional standalone
Rust CLI was omitted; the installed Python CLI shares the required engine.

## Use and inspect

```python
from pathlib import Path
from ofi_pipeline import PipelineConfig, run_pipeline

report = run_pipeline(
    sample_dir=Path("/path/to/order_book_sample"),
    output_dir=Path("/new/generated/features"),
    config=PipelineConfig(bucket_seconds=10, levels=5, threads=2, chunk_rows=65536),
)
print(report.features_path, report.feature_rows)
```

The ignored final local wheel is
`dist/ofi_pipeline-0.1.0-cp310-abi3-macosx_11_0_arm64.whl` (SHA256 in
[acceptance.json](acceptance.json)). Install it with `python -m pip install
/path/to/that.whl`; coworkers need no Rust toolchain for this compatible wheel.
Source builds require Rust >=1.90, Python >=3.10 and pinned maturin 1.9.6.
`ofi-pipeline --sample-dir /path/to/sample --output-dir /new/output` calls the same
API. All generated datasets require a new directory unless explicit owned-output
replacement is enabled.

See [usage](usage.md), [architecture](architecture.md),
[output schema and interval examples](output_contract.md),
[verified input schemas](verified_schema.md) and the normative
[dataset contract](DATASET_CONTRACT.md). [CHANGELOG.md](../CHANGELOG.md) records
each milestone's changes, design decisions, exact checks, failures/fixes and
remaining work at that time. The owner-requested deleted task/work-log documents
remain absent.

## Final evidence

| Check | Observed result |
| --- | --- |
| Rust workspace | 28 core unit + 3 adapter + 2 pipeline tests passed; external ingestion skipped only in the default suite. |
| Explicit real Rust ingestion | 1 test passed: 887810 clean events, 68404 executions, 897387 original quality rows, 9577 rejected quotes. |
| Python and compiled integration | 79 passed in 54.98 s, including 74 self-contained tests and all five real-width acceptance tests. |
| Source/build checks | Rustfmt, all-target Clippy with denied warnings, Ruff, strict mypy and diff whitespace passed. Rust 1.90 minimum-version instrumented build/test passed. |
| Clean release wheel | Fresh Python 3.12 environment outside checkout imported its own compiled extension and passed API, CLI, Parquet, error and type-marker checks. |
| Rust core coverage | 1756/1764 measured production lines, 99.5465%; all eight missed lines documented. |
| Native binding coverage | 42/42 authored production lines, 100%, from instrumented native runtime profiles. |
| Python coverage | 187/187 production lines and 30/30 branches, 100%, zero excluded lines. |
| Platform CI | Linux/macOS/Windows Python 3.10/3.12 matrix and Linux coverage job configured; YAML parsed. Hosted CI has not run. |

Exact reproduction commands and instrumentation are in [testing.md](testing.md).
Portable source hashes and check outcomes are in [acceptance.json](acceptance.json),
with per-module measured counters and honest limitations in
[coverage.md](coverage.md) / [coverage.json](coverage.json). Raw local LLVM/Python
reports remain under ignored `target/coverage-report/`. The eight missing Rust
counters comprise six internal invariant guards and OS thread-spawn/final-QC-write
failure sites that were not fault-injected. No claim of measured 100% Rust core
coverage is made.

## Actual delivered sample reconciliation

All 24 SHA256SUMS entries, archive source hashes/sizes, physical schemas/counts
and primary-input nulls were verified before acceptance. Production uses only
clean events/trades plus original quality, with raw row-paired quotes when Quote
Test is selected. It never reads delivered feature tables or bucket masks; a
poisoned-oracle fixture enforces this. Validation reads the oracle afterward.

At 10 seconds the computed 4390 accepted keys, 4680 all-grid decisions and 290
exclusions match the delivered oracle: AAPL 2060 accepted / 280 excluded, MSFT
2330 / 10. All five OFI ranks, known-direction TI, volume and event/L1-update counts
match exactly. Other widths were independently rebuilt using the inspected
original raw preparation code only in validation: 1 s = 45966 accepted rows,
5 s = 8985, 30 s = 1382, 60 s = 650. Every width has zero missing/extra keys,
zero integer mismatches and identical quality decisions. Depth is exact; largest
midpoint differences are about 2.2e-13 USD / 2.2e-11 ticks, below declared absolute
tolerances 1e-10 USD, 1e-8 ticks, 1e-10 depth shares. Three delivered MSFT timestamp
rounding flags are retained and reported. See [reconciliation.json](reconciliation.json).

Quote Test uses original row n-1 pre-execution books, including filtered states,
not cleaned post-event quotes. Its signs are intentionally distinct from known
direction. Final real runs conserve AAPL 2850140 shares (1847216 classified,
1002924 unknown), MSFT 10824421 (9887669 classified, 936752 unknown). Full interval
TI is null if any trade is unclassified; partial signed TI is separately labeled.
Accepted quote keys/features/quality and total volumes/counts stay unchanged.

## Release performance and deterministic output

M2 Pro, 10 cores, 16 GiB, Rust 1.98 release, Python 3.12.0. Sequential fresh-process
measurements ran after project compilation/tests ended. Whole-process RSS includes
Python/native runtime; OS cache is uncontrolled and leans warm. Build/install and
fixture generation are excluded. One observed run per configuration establishes
neither a general performance guarantee nor a statistically estimated speedup.

| Input and workers/chunk rows | Public-call seconds | Peak process MiB |
| --- | ---: | ---: |
| Real known direction, 1 / 4096 | 4.0239 | 99.27 |
| Real known direction, 2 / 65536 | 3.9107 | 323.13 |
| Real known direction, 4 / 1 | 31.2190 | 54.77 |
| Real Quote Test, 2 / 4096 | 4.3259 | 102.00 |
| Authored 20000-event fixture, 2 / 4096 | 0.1029 | 62.31 |

The real sample has two independent partitions; observed peak workers are 1/2/2,
not four when configured threads=4. Known-direction decoded feature and full
quality tables are exactly equal across these chunks/workers, as is the manifest
after removing the deliberately different execution config fields. Compressed
file byte identity is not required. The bounded-queue worker tests also cover
multiple symbols/dates and initialization at chunk boundaries. Exact configs,
versions, throughput, compression, commands, scope and Quote Test conservation
are in [performance.json](performance.json) and [benchmarks](../benchmarks/README.md).

## Known scope and operational limits

The adapter covers the verified Lev-v1 five-level single-venue NASDAQ input, not
consolidated TAQ/NBBO. The two-symbol/one-day sample supports methodology checks,
not forecasting/profitability claims. Deep OFI is a rank-based extension; OLS,
Ridge, PCA, CatBoost, a GUI, database/server and live trading remain out of scope.
Supplied quality is honored; no silent sorting, timestamp deduplication, hidden
percentile recalibration or gap filling occurs. Insufficient original history,
unavailable levels and inconsistent evidence fail explicitly.

RAM is bounded by chunks, active workers and capped report metadata, plus native
reader page/footer metadata that depends on Parquet file layout. Temporary disk
scales with intermediate output and Quote Test archive payloads; ZIPs spool owned
paired files and are removed before publication. Inputs must remain unchanged
during a run. Output rename publishes only completed datasets; explicit overwrite
briefly moves an owned old result aside. This is not a transaction against
concurrent external mutations or sudden power failure. Publication fault tests
verify rollback/recoverable backups. Sparse intervals require real timestamp
adjacency checks before deriving lags.

Only macOS arm64/Python 3.12 was exercised locally. Other platforms/Python versions
are configured for hosted CI after the owner pushes; no hosted success is claimed.
Benchmark RSS tooling is POSIX-only; wheel/import CI is cross-platform.

## Ordered local commits and repository status

This is the authoritative ordered history ahead of the existing `origin/main`
reference before this final handoff commit. The first entry is the owner's
specification bootstrap; subsequent entries implement it. The final handoff
commit follows this table; resolve its hash with `git log -1 --oneline` (also
reported in the closing response). No history was rewritten by the implementation.

| Commit | Change |
| --- | --- |
| c634934 | docs: specify Rust-Python OFI pipeline implementation |
| 99a45f4 | docs: record implementation checklist and repository inventory |
| 66e34d3 | feat(bindings): bootstrap compiled Rust and Python workspace |
| a6a2452 | feat(core): add checked domain and exact session configuration |
| 05a4766 | feat(io): stream validated Lev Parquet and gzip CSV inputs |
| 9aa669d | feat(core): compute checked rank OFI across original quality rows |
| c0ced0b | feat(core): sign independent executions and conserve volume |
| c535886 | feat(core): aggregate original boundaries on right-closed grids |
| 763dc6f | feat(core): publish streamed Parquet features and provenance atomically |
| ded771e | feat(api): expose compiled file-set pipeline and typed Python CLI |
| ca9854b | feat(core): sign executions against original paired pre-quotes |
| 37e4162 | fix(io): validate and report delivered timestamp precision evidence |
| f4bd061 | test(sample): reconcile native features against all reference widths |
| 4299a50 | perf(core): bound partition workers and assemble deterministic output |
| 1548141 | perf: record release sample throughput memory and determinism |
| df02653 | fix(core): validate execution evidence and represent unknown TI explicitly |
| 506a782 | fix(core): bound report metadata and stop at final session boundary |
| 2105657 | test: measure core native and Python coverage with error evidence |
| 60124b9 | build: verify isolated wheels and define platform CI checks |
| 4c690ba | test: record final release acceptance and measured determinism |

Final local branch: `main`. All authored changes are committed. The only preserved
uncommitted change is the pre-existing `.gitignore` addition of `Cargo.lock`;
the lockfile remains tracked and committed. No sample, raw archives, generated
Parquet/output, environments or compiled binaries are tracked. No implementation
commits were pushed; no pull request, package, release or deployment was published.
The owner can review local history and choose when to publish it.
