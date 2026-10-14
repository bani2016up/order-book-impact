# Implementation work log

Work on local `main`; do not push. This log replaces `docs/WORK_LOG.md` at the
owner's explicit request. The pre-existing deletions of that file and
`docs/IMPLEMENTATION_TASK.md` are preserved. The implementation specification is
the owner-provided attachment; `docs/DATASET_CONTRACT.md` remains normative.

## Checklist

- [x] M0: inspect repository, delivery integrity, physical schemas, preparation code.
- [x] M1: pure Rust workspace, compiled PyO3 extension, typed Python package.
- [x] M2: checked domain types, sessions, decimal time, configuration and ordering.
- [x] M3: streaming Parquet/gzip CSV and original quality alignment.
- [x] M4: gap-aware rank OFI, persistent state and L1 update classification.
- [x] M5: independent executions, known-direction signing and conservation.
- [x] M6: right-closed grids, original boundaries, depth and exclusions.
- [x] M7: atomic output, provenance/QC, typed errors, Python CLI.
- [x] M8: paired raw adapter and pre-execution Quote Test.
- [x] M9: full real sample integrity/parity and independently rebuilt other widths.
- [x] M10: bounded partition concurrency, chunk/thread invariance and benchmarks.
- [ ] M11: isolated wheel, coverage, CI, complete English handoff documentation.

Each completed subtask records files/design decisions, exact focused commands,
outcomes/evidence, data status, intended commit message, and remaining work. Final
commit hashes are authoritative in Git history, not self-referential log entries.

## Bootstrap inspection — 2026-10-14

- Verified repository root via `git rev-parse --show-toplevel` and local branch
  `main`. Initial history: `379d32a`, `768cc8c`; branch already one commit ahead
  of `origin/main`. Only pre-existing tracked changes are the two deletions above.
- Read `AGENTS.md`, complete dataset contract and attached implementation task.
  No production code exists initially. Created this log as requested.
- Tool inventory: Homebrew Rust/Cargo 1.98.0; system Python 3.12.0; uv 0.9.13.
  Dependency environments will live in ignored `.venv`; native builds in `target`.
- Owner provided `order_book_sample/`, which contains Parquet, gzip CSV, original
  ZIP archives, quality metadata, hashes and `src/prepare_sample.py`. Read the
  preparation code without executing it. Delivery hash/schema inspection remains
  pending a repository-local inspection environment.
- Confirmed raw decimal rounding is half-up at nanoseconds, quality includes all
  original row IDs/times, reference aggregation uses original boundary states,
  and supplied `is_quote_update` includes the first original observation.
- Design: explicit versioned Lev schema; integer price units of USD/10,000;
  half-unit mids; streaming merge by original ID of events/quality/trades; no
  timestamp join, hidden sorting, or recalibration. Arrow/Parquet owns native I/O.
- Focused checks: `git status --short --branch`, `git log -5 --oneline`,
  `git rev-parse --show-toplevel`, `git remote -v`, file inventory and tool versions
  all passed. A schema inspection attempt failed because the repo-selected
  Python lacked PyArrow; creating a dedicated environment resolves this next.
- Intended commit: `docs: record implementation checklist and repository inventory`.
- Remaining: verify delivery, implement M1–M11, test and measure coverage/performance.

## M0 completion and M1 — native skeleton

- Files: workspace/core/binding Cargo manifests and sources, `Cargo.lock`,
  `pyproject.toml`, `python/ofi_pipeline/{__init__.py,_native.pyi,py.typed}`,
  `tests/integration/test_native.py`, `docs/verified_schema.md`, this log.
- Pinned PyO3 0.27.2 with Python >=3.10 stable ABI; Rust >=1.90. Pure core has
  no Python dependency. A native smoke operation runs with `Python::detach`.
  Maturin mixed layout exposes `ofi_pipeline._native` and retains type markers.
- Native test checks the loaded filename against extension suffixes and invokes
  the actual compiled function. No fallback or subprocess implementation exists.
- Checks passed: `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test --workspace --offline`
  (one core test), `cargo fmt --all -- --check`,
  `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/integration/test_native.py` (one passed),
  `.venv/bin/ruff check python tests/integration/test_native.py`, `.venv/bin/mypy`.
- Delivery inspection: 24/24 SHA256SUMS entries verified from file bytes; physical
  Parquet counts 887,810 events, 68,404 trades, 897,387 original-quality rows,
  4,680 reference quality intervals, 4,390 accepted reference rows. Schema map
  records verified Arrow dtypes and missing fields. Real feature parity is unrun.
- Environment failures resolved: sandbox networking required authorized dependency
  downloads; uv crashed in macOS system configuration, so Python venv/pip was used.
  Disk exhaustion interrupted first build/install; removed only this task's build
  and download caches, disabled dev/test debug symbols and incremental artifacts.
  Free space subsequently increased to ~2.4 GiB. Relative PYO3_PYTHON failed from
  crate build directories; the absolute interpreter path fixed it. Arrow scalar
  inspection uses integer timestamp values (no lossy Python datetime conversion).
- Intended commit: `feat(bindings): bootstrap compiled Rust and Python workspace`.
- Remaining: M2–M11; the extension currently exposes version metadata only.

## M2 — domain, time and configuration

- Added Rust `config`, `domain`, `error`, `time` modules; native owned JSON
  configuration validation; typed frozen Python `PipelineConfig` and eight
  actionable exception categories. Updated manifests/lock, stubs/exports, and
  focused Python tests. No production numerical computation moved to Python.
- Prices use checked USD/10000 integers, preserve half-tick mids and reject
  nonfinite/overprecision values. Time uses UTC int64 ns, New York DST sessions,
  deterministic decimal half-up parsing, and delivered local-ns consistency.
  Ordering permits tied times with distinct IDs and rejects duplicates, decreasing
  time, partition reversal, and missing contiguous original-quality IDs.
- Checks passed: `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test --workspace --offline`
  (8 Rust tests), `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/python/test_config.py tests/integration/test_native.py`
  (30 passed), `.venv/bin/ruff check python tests/python tests/integration`,
  `.venv/bin/mypy`, `cargo clippy --workspace --all-targets --offline -- -D warnings`.
  Final defensive session-width guard: `cargo fmt --all && cargo test -p ofi-core config --offline`
  passed. Direct invalid widths cannot divide by zero or overflow before validation.
- Real sample schemas/hashes are verified; feature parity remains unrun.
- Intended commit: `feat(core): add checked domain and exact session configuration`.
- Remaining: M3–M11; input adapters and feature computation are next.

## M3 — native streaming sample ingestion

- Added `adapter.rs`, Rust adapter fixtures/tests and explicit external-sample
  ingestion test. Pinned Arrow/Parquet 60.0.0, CSV 1.4.0, flate2 1.1.5; committed
  exact transitive resolution in Cargo.lock. Parquet uses bounded record batches
  even for the sample's single large row groups; CSV records stream through gzip.
- Lev-v1 physical names/types are explicit. Invalid UTC units/timezones, local-ns
  disagreement, null required values, missing depth, malformed files, invalid
  books/trades and inconsistent supplied signs fail with typed errors. Preserves
  ties and IDs; quality must cover contiguous original IDs starting at zero.
  Original quality has no date, so derive its New York date from UTC timestamp.
- Focused checks passed: `cargo test -p ofi-core --test adapters --offline` (3),
  `cargo test -p ofi-core --offline` (8 units + 3 adapter tests),
  `cargo clippy -p ofi-core --all-targets --offline -- -D warnings`, `cargo fmt --all`.
  Initial Clippy findings (nested if/unused mut) were fixed before commit.
- Real native ingestion check passed:
  `OFI_SAMPLE_DIR="$PWD/order_book_sample" cargo test -p ofi-core --test sample_ingestion --offline -- --ignored`
  validated every event/trade/original-quality row, ordering and time/price types,
  with 887,810 accepted events, 68,404 trades, 897,387 original rows, 9,577 rejected
  quotes; 17.58 seconds debug/test runtime. This is ingestion, not feature parity.
- Disk now has ~41 GiB free. No dataset files staged, copied or altered.
- Intended commit: `feat(io): stream validated Lev Parquet and gzip CSV inputs`.
- Remaining: merge/alignment must prove accepted/rejected correspondence before
  computing; M4–M11 including real feature parity are pending.

## M4 — gap-aware rank OFI

- Added `ofi.rs` and exported it from the pure core. Computes each requested
  occupied rank independently with checked signed int64 output. Unknown first
  observations and segment resets return `None`, not a zero transition.
- Stateful observation consumes every original quality row, proves event/quality
  ID/time/presence alignment, validates predecessor/segment/L1-change markers,
  and clears the predecessor at every rejected quote. State persists independently
  of input batch boundaries; no transition crosses a rejected gap.
- Focused checks passed: `cargo test -p ofi-core ofi::` (5 tests, including 36
  symmetric/unchanged cases and hand-computed improve/worsen/equal size cases),
  `cargo clippy -p ofi-core --all-targets -- -D warnings`, `cargo fmt --all`.
  Final book validation guard rechecked with `cargo test -p ofi-core ofi:: --offline`.
- The Cargo cache disappeared during disk cleanup; offline resolution failed once.
  Refetched the same pinned versions; no source/lock versions changed.
- Dataset remains available and verified. OFI parity is not yet measured because
  bucket output is still under implementation.
- Intended commit: `feat(core): compute checked rank OFI across original quality rows`.
- Remaining: M5–M11; file-level merge/aggregation/output and Quote Test are pending.

## M5 — independent execution signing

- Added `trades.rs`: known LOBSTER aggressor sign is `-direction`, independent
  of post-execution quote acceptance. Trade sequence rejects duplicate or
  reversed original IDs, while tied times remain valid.
- Checked volume/TI/counts, classified and unclassified volume/counts; unknown
  signs remain explicit. Failed single-trade arithmetic leaves the accumulator
  intact. Separate trades input is the only source of execution volume.
- Checks passed: `cargo fmt --all`, `cargo test -p ofi-core trades:: --offline`
  (2 tests exercising both types/signs, rejected quotes, duplicate prevention,
  conservation and accumulation overflows),
  `cargo clippy -p ofi-core --all-targets --offline -- -D warnings`.
- Actual input integrity and ingestion are verified; TI/output parity is pending.
- Intended commit: `feat(core): sign independent executions and conserve volume`.
- Remaining: M6–M11; Quote Test matching will use the original pre-state adapter.

## M6 — streaming interval aggregation

- Added `buckets.rs`: one live bucket and original-boundary state per active
  symbol/session, checked OFI/depth/counts, all supported right-closed grids,
  UTC interval ends and contemporaneous USD/tick mid changes.
- Emits every grid row to a sink, with explicit reasons and nullable features
  for exclusions. First incomplete buckets, rejected events, missing/invalid
  boundaries and unknown segment transitions are excluded. Newer rejected
  originals invalidate carried boundary states until an accepted original arrives.
- Average depth uses supplied L1-update markers only; no-update valid intervals
  use right-boundary depth. Separate executions contribute even on rejected quotes.
- Checks passed: `cargo fmt --all`, `cargo test -p ofi-core buckets:: --offline`
  (4 tests covering all widths, exact-right boundaries, empty fallback, tied times,
  last grid boundary, L1 weighting, half ticks, rejected carry, missing books,
  independent rejected-quote trades and sink/order errors),
  `cargo clippy -p ofi-core --all-targets --offline -- -D warnings`.
  A test closure borrow error was fixed before checks passed.
- Real feature parity and file-level chunk invariance await the M7 runner/output.
- Intended commit: `feat(core): aggregate original boundaries on right-closed grids`.
- Remaining: M7–M11 including atomic Parquet publication and full integration.

## M7a — file-set core and atomic output

- Added Rust `pipeline.rs`, `output.rs`, core file-set integration tests and
  SHA-256 provenance. Merges quality/events/trades by original IDs, with one-row
  lookahead per stream and one active session engine. Bounded Parquet buffers
  write accepted-only features plus the full quality grid, manifest and QC.
- A new output directory is staged beside its destination and renamed after all
  computation/writes succeed. Overwrite is explicit and limited to owned output
  directories with no other user data. Collision checks resolve symlinks and
  protect inputs. Failed computation leaves existing results intact; if publication
  restoration fails, the old directory is preserved and its location reported.
- Source hashing is one explicit streaming pass, followed by one ordered compute
  pass; no reference feature/mask reads occur. Deterministic manifest provenance
  excludes runtime timing; QC records elapsed time separately. Output signed
  values/counts use int64, unavailable excluded features use Arrow nulls.
- Checks passed: `cargo test -p ofi-core --offline` (19 units + 3 adapter tests;
  external ingestion test explicitly ignored), `cargo test -p ofi-core --test pipeline --offline`
  (2), `cargo clippy --workspace --all-targets --offline -- -D warnings`, `cargo fmt --all`.
  A fixture timestamp literal inferred as i32 was corrected to i64 before commit.
- First real native 10-second run via the in-progress compiled Python API passed:
  `run_pipeline('order_book_sample','outputs/m7-real-10s',PipelineConfig(threads=1,chunk_rows=4096))`.
  Debug runtime 21.205259375 s; AAPL 2,060 accepted/280 rejected; MSFT 2,330/10.
  Compared actual computed output with reference **after** computation: 4,390 keys,
  no missing/extra keys; all 4,680 quality flags match; exact L1–L5 OFI, TI, volume,
  event/L1-update counts; max absolute USD delta error 2.0008994461306884e-13,
  tick delta error 2.000888343900442e-11, depth error 0. This preliminary evidence
  will become a repeatable M9 acceptance report/test.
- Intended commit: `feat(core): publish streamed Parquet features and provenance atomically`.
- Remaining: finish/stage Python API/CLI separately; Quote Test and bounded
  concurrency currently fail/warn explicitly; coverage/packaging/CI pending.

## M7b — typed native API, CLI and compiled fixture integration

- Added native file-set operation with owned inputs/config inside Python::detach;
  Python `InputPaths`, typed `RunReport`/partition/signing metadata, path/environment
  normalization and installed CLI. Updated exports/stubs, packaging entry point,
  README/usage, authored fixture provenance and compiled integration/error tests.
- Rust owns reading, merge, arithmetic and output. Python creates no per-tick
  objects in production. Poison reference files verify no production oracle reads.
  Inputs support strings/pathlib and explicit Parquet or headered gzip CSV files.
- Checks passed: `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/python tests/integration` (43 passed),
  `.venv/bin/ruff check python tests`, `.venv/bin/mypy`,
  `cargo clippy --workspace --all-targets --offline -- -D warnings`,
  `.venv/bin/ofi-pipeline --help` and `python -m ofi_pipeline --help` from a
  temporary cwd in the CLI test. No pure-Python fallback is accepted.
- Fixture comparisons cover chunks 1/2/3/100 versus 65536, tied IDs/time,
  gaps, interval boundaries, all five ranks, exact TI/volume/depth expectations,
  gzip CSV equivalence, empty intervals and failed-run/overwrite/collision behavior.
- Real 10-second evidence recorded in M7a; repeatable reconciliation is next.
- Intended commit: `feat(api): expose compiled file-set pipeline and typed Python CLI`.
- Remaining: M8–M11, including raw Quote Test, actual concurrency, release benchmark,
  full coverage/clean wheel/CI. Rebuilt extension uses current sources.

## M8 — original paired raw Quote Test

- Added `raw.rs`, ZIP 6.0.0 with minimal deflate support, explicit `RawInput`
  sources and sample vendor-archive discovery. Updated Rust pipeline, Python
  input API/exports, usage and compiled raw-pair/ZIP tests.
- Message/book pairing stays by row index. Valid original pre-quotes survive
  post-quote rejection; invalid/missing pre-quotes and inside-spread executions
  remain unknown. Raw/quality IDs/timestamps, accepted post-books and execution
  fields must agree. Same-time events and buffers preserve the preceding quote.
- ZIP payloads spool once to private temporary disk files with constant-size
  copying, then stream CSV pairs; no arbitrary archive pathname is extracted.
  Raw buffers keep one previous book. Spools are removed before publication.
  This extra disk pass/cost is explicit in the manifest and documentation.
- Checks passed: `cargo test -p ofi-core raw:: --offline` (2),
  `cargo clippy --workspace --all-targets --offline -- -D warnings`,
  `.venv/bin/ruff check python tests`, `.venv/bin/mypy`, `cargo fmt --all`,
  `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/integration/test_quote_test.py tests/integration/test_pipeline.py`
  (12 passed; chunks 1/2/3/100, pre/post distinction, hidden unknowns, ZIP discovery,
  missing originals and known-direction regression). Initial fixture lint errors
  were corrected before checks passed.
- Actual sample Quote Test run passed via `run_pipeline` with threads=1,
  chunk_rows=4096: 32.299725625 seconds debug runtime; accepted rows remain
  AAPL 2,060/MSFT 2,330. AAPL classified 1,847,216 / unclassified 1,002,924
  shares (23,665/11,325 executions); MSFT classified 9,887,669 / unclassified
  936,752 shares (29,798/3,616). Total execution volume is conserved, including
  rejected post-quotes. Quote Test TI is separately labeled, not parity TI.
- Intended commit: `feat(core): sign executions against original paired pre-quotes`.
- Remaining: M9 repeatable acceptance and precision provenance, M10 bounded
  concurrency/release measurements, M11 coverage/clean wheels/CI/handoff.

## M9a — exact precision provenance

- Retain delivered rounding flags as `Option<bool>` in the event domain; missing
  flags remain unknown and are counted/warned in QC. Added per-partition delivered
  and raw rounded-timestamp counts. When original decimal text is supplied,
  validate its deterministic rounded ns/flag against delivered values without
  changing the delivered timestamp. Clean CSV with >9 timestamp fractional
  digits is rejected rather than silently truncated by the RFC3339 parser.
- Updated domain/adapter/time/pipeline, typed Python partition metadata and focused
  precision fixture. Half-up carry from 34200.999999999500 -> 34201 seconds is
  verified; a contradictory delivered flag fails as malformed data.
- Checks passed: `cargo test -p ofi-core --offline` (21 unit + 3 adapter + 2
  pipeline tests, external ingestion explicitly ignored), `cargo fmt --all`,
  `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/integration/test_pipeline.py tests/integration/test_quote_test.py`
  (13 passed), `.venv/bin/ruff check python tests`, `.venv/bin/mypy`,
  `cargo clippy --workspace --all-targets --offline -- -D warnings`.
- Real reconciliation suites are running against the verified bundle; no real
  files are committed or modified. New QC distinguishes absent flags from false.
- Intended commit: `fix(io): validate and report delivered timestamp precision evidence`.
- Remaining: M9 acceptance report, M10 concurrency/performance, M11 distribution/coverage.

## M9b — repeatable real-sample acceptance at every width

- Added opt-in `tests/real_sample/test_acceptance.py`, validation-only dependency
  extras, reproducible testing documentation and `docs/reconciliation.json`.
  Integrity fixture checks all delivered hashes, vendor source SHA256/size,
  actual schema/counts/nulls before native acceptance. Missing sample skips
  explicitly; rebuilding reference widths is explicitly opted in.
- Focused check passed:
  `OFI_SAMPLE_DIR="$PWD/order_book_sample" OFI_REBUILD_REFERENCE=1 .venv/bin/python -m pytest -q tests/real_sample --basetemp outputs/m9-acceptance`
  (5 passed in 154.32 seconds). `.venv/bin/ruff check tests/real_sample` passed.
- At 10s: all 4,680 quality decisions, 4,390 accepted keys and 290 rejected
  intervals match; exact integer OFI L1–L5, TI, volume and event/L1-update counts;
  USD max abs error 2.0008994461306884e-13, ticks 2.000888343900442e-11,
  depth 0. Verified all three delivered rounded MSFT event timestamps in QC.
- At 1/5/30/60s: separately rebuilt reference from original archives using the
  fully inspected Lev preparation code as a **test-only oracle**, then compared
  native output and full-width quality. Exact keys/integers/quality all pass;
  float errors within declared tight tolerances. Full counts/error evidence is
  in reconciliation.json. No reference code or Python math enters production.
- Cargo metadata confirms no locked dependency declares an MSRV >1.90; actual
  minimum-toolchain build and platform matrix remain M11 checks.
- Intended commit: `test(sample): reconcile native features against all reference widths`.
- Remaining: M10 bounded concurrency/release measurements; M11 coverage, clean
  wheel installation, CI and final requirement audit. Real-sample acceptance is
  now passed, not pending.

## M10a — bounded independent-partition concurrency

- Added private Rust `worker.rs`, bounded synchronous queues and deterministic
  output assembly. Producer validates/merges inputs in order; each independent
  symbol/session is owned by one persistent worker. At most configured workers
  coexist; at most one chunk queues per worker. Failed workers propagate typed
  errors, close channels and are joined before temporary output is removed.
- Intermediate partition Parquet files are streamed once into final outputs in
  key order and removed before publication. This explicit extra output pass is
  documented in the manifest. No full-day input collectors or parallel chunk
  reinitialization. Uses std threads rather than an additional global Rayon pool.
- Added observed peak worker count to typed/native QC. Added compiled tests for
  two symbols on two dates with threads/chunks (1,1)/(2,2)/(4,3)/(2,100): identical
  decoded features/quality and stable semantic provenance, independent state,
  conserved volumes, configured worker bound and no temporary output leftovers.
- Checks passed: `cargo test -p ofi-core --offline` (21 units + 3 adapter + 2
  pipeline), `cargo clippy --workspace --all-targets --offline -- -D warnings`,
  `cargo fmt --all`, `.venv/bin/ruff check python tests`, `.venv/bin/mypy`,
  `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/integration/test_parallel.py tests/integration/test_pipeline.py tests/integration/test_quote_test.py`
  (14 passed). Current source rebuilt before compiled checks.
- All-width real parity passed before this orchestration change. Release real-data
  determinism/performance and final acceptance will validate the new runner next.
- Intended commit: `perf(core): bound partition workers and assemble deterministic output`.
- Remaining: M10b measured release performance; M11 coverage/distribution/CI/audit.

## M10b — release measurements and real chunk/thread invariance

- Added POSIX benchmark runner, authored 20,000-event/two-symbol generator,
  reproduction README and `docs/performance.json` with hardware, versions,
  formats/compression, cache/timing/RSS scopes and explicit limitations.
- Release build check passed:
  `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --release --offline`
  (53.96 seconds compile; excluded from run metrics). Initial measurements
  overlapped an MSRV compile and were discarded; final fresh-process measurements
  ran after that build ended. OS cache/other host activity remain uncontrolled.
- Commands passed: `benchmarks/run.py` under `.venv/bin/python` with real sample
  and configs threads/chunks 1/4096, 2/65536, 4/1, Quote Test 2/4096, and authored
  fixture 2/4096. Exact decoded `features.parquet` and `bucket_quality.parquet`
  equality across real known-direction runs; Quote Test accepted keys/quality
  match. No synthetic data is labeled real.
- Recorded M2 Pro/10 cores/16 GiB release real known-direction wall times:
  5.3354 s (~168k original events/s; 95.59 MiB peak process RSS), 4.5565 s
  (~197k/s; 155.05 MiB), 48.8275 s (~18k/s; 50.19 MiB) for those configs.
  Real Quote Test: 5.7227 s, 79.27 MiB; synthetic 20k: 0.1131 s, 63.41 MiB.
  Whole-process RSS includes Python/native runtime. Actual peak workers 1/2/2;
  only two real partitions exist, so threads=4 cannot invent more parallel work.
- Minimum-version check also passed:
  `CARGO_TARGET_DIR=target/msrv PYO3_PYTHON="$PWD/.venv/bin/python" /Users/daniilparfenov/.cargo/bin/cargo +1.90.0 test --workspace --locked --offline`
  (21 core units + 3 adapter + 2 pipeline; external ingestion explicitly ignored).
- Intended commit: `perf: record release sample throughput memory and determinism`.
- Remaining: M11 comprehensive coverage, clean wheel smoke, CI, English handoff
  and final requirement audit. Neither implementation nor CI has been pushed.

## M11a — acceptance-audit contract hardening

- Audited the attached requirements against current code. Accepted cleaned
  messages now validate type/size/price/direction and optional raw-price scaling;
  accepted type-4/type-5 executions must match independent trade fields exactly.
  Missing or contradictory executions fail, preventing plausible incomplete TI.
  Updated event domain/adapter/worker and authored fixtures accordingly.
- Full Quote Test TI is now null when any execution is unclassified; explicit
  `classified_trade_imbalance` and `trade_signing_complete` columns retain the
  partial evidence. Typed signing metadata exposes `complete_trade_imbalance`.
  This replaces a plausible zero/partial sum masquerading as full unknown TI.
- Added checked pre-book validation, contextual input/worker errors, and a small
  publication rename seam. Production still calls std::fs::rename; fault tests
  simulate second/third rename failures and verify actual original file contents
  are restored or preserved in a recoverable backup. No blanket coverage exclusion.
- Added focused malformed/empty/truncated evidence, bad units/signs, missing
  schema fields, duplicate headers, outside-session and atomic-publication tests.
- Checks passed: `cargo test -p ofi-core --offline` (21 units + 3 adapter + 2
  pipeline before added publication tests), `cargo test -p ofi-core output:: --offline`
  (2 publication/path tests), `cargo clippy --workspace --all-targets --offline -- -D warnings`,
  `cargo fmt --all`, `.venv/bin/ruff check python tests scripts benchmarks`,
  `.venv/bin/mypy`, `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/python tests/integration` (62 passed).
- Earlier Python measurement reached 100% production lines/branches (182 lines,
  30 branches); native-binding preliminary measurement covered all 42 authored
  lines. Rust/native profiles will be rebuilt from the frozen final sources and
  inspected for uncovered reachable code; preliminary coverage is not final.
- Intended commit: `fix(core): validate execution evidence and represent unknown TI explicitly`.
- Remaining: full final-source Rust/native/Python coverage, isolated wheel, CI
  docs/handoff, real parity and refreshed performance after this contract change.

## M11b — bounded metadata and final-boundary checks

- Added explicit `max_partitions` (default 1024, range 1..16384) to native/Python
  config and CLI, bounding returned metadata as well as live worker state.
  Lev-v1 quality reasons use a fixed validated vocabulary, so rejection-count
  maps cannot grow once per event. Unknown reasons require an explicit adapter
  change rather than hidden regrouping or recalibration.
- Fixed final bucket flushing near the int64 UTC-nanosecond limit: no unused
  next boundary is computed after session close. Added an extreme-range session
  regression, depth/trade mismatch guards, initial quality-ID validation,
  disappeared-source hashing and contained dependency-panic tests.
- Focused checks passed: `cargo test -p ofi-core --offline` (26 unit, 3 adapter,
  2 pipeline tests; external ingestion explicitly ignored),
  `.venv/bin/python -m pytest -q tests/python/test_config.py tests/integration/test_parallel.py tests/integration/test_pipeline.py`,
  `cargo fmt --all -- --check`, `.venv/bin/mypy`.
  Prior rebuild/check for these changes: maturin develop, Clippy and full
  Python/compiled fixture selection passed (65 tests). An extreme test initially
  chose a local clock beyond representable UTC; corrected its clock before pass.
- Real files remain unchanged and outside Git. Current final-source parity,
  coverage and wheel checks are next; earlier evidence is retained as historical.
- Intended commit: `fix(core): bound report metadata and stop at final session boundary`.
- Remaining: coverage gap audit, clean wheel/CI, refreshed real acceptance and
  performance, English final handoff. External `.gitignore` edit is preserved;
  Cargo.lock remains tracked and committed despite its added ignore rule.

## M11c — final measured coverage and error evidence

- Added `scripts/coverage.py`, `docs/coverage.{md,json}`. Matched Rust 1.90/LLVM
  instrumentation covers test executables plus the real Python-loaded native
  library; source SHA256 is frozen before/after. Raw reports remain in ignored
  target output, with a portable per-module summary committed. No blanket
  production exclusions; inline test bodies are outside the production scope.
- Added overflow tests in core time/raw modules; compiled error tests cover
  corrupt/unpaired original ZIP/CSV evidence, uneven CSV, invalid integer fields,
  missing original quality, and checked partition-volume overflow. Worker volume
  errors now retain original event/symbol/date/UTC ns context.
- Exact check passed: `.venv/bin/python scripts/coverage.py --toolchain 1.90.0`
  (28 Rust unit + 3 adapter + 2 pipeline; 74 Python/compiled integration tests).
  Core: 1756/1764 lines (99.5465%); binding 42/42 (100%); Python 187/187 and
  30/30 branches (100%). Eight missed core counters remain visible: six internal
  invariant guards, OS thread-spawn failure, and final QC-write device failure.
  Their precise limitations are documented, not reported as measured 100%.
- Additional checks passed: `cargo fmt --all -- --check`,
  `PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --workspace --all-targets --locked --offline -- -D warnings`,
  `.venv/bin/ruff check python tests scripts benchmarks`, `.venv/bin/mypy`,
  `git diff --check`.
- Real data remain available and unchanged. Coverage uses authored fixtures;
  final release real-sample acceptance is separate and next.
- Intended commit: `test: measure core native and Python coverage with error evidence`.
- Remaining: rebuild final release/wheel, complete distribution CI docs,
  final all-width parity/performance refresh and English handoff audit.
