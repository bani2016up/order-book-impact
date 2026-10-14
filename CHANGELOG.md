# Implementation work log

## Implementation diagrams — plan and overview milestone

- The owner requested documentation of the actual implementation: architecture,
  data flow, C4, PyO3 communication, Rust crates/modules and ofi-core internals.
- Plan: commit the overview/data-flow/C4 gallery first; then commit the detailed
  bridge/core/research views and documentation navigation. Production interfaces,
  code and repository layout remain unchanged except for docs/diagrams/.
- Added six editable Excalidraw scenes and portable SVG previews: architecture,
  data flow and C4 levels 1–4. Reviewed the current engine at commit 41962ab,
  public Python API, native binding, model entry point and filesystem contracts.
- Added an English gallery with code anchors, C4 scope/notation, element counts
  and edit instructions, plus a standard-library preview renderer/check command.
- Focused evidence: scenes parsed as JSON with unique IDs and Excalifont text;
  SVGs parsed as XML and rasterized with rsvg-convert; all six previews inspected.
  Renderer preview-freshness, Ruff, Markdown local links and diff-whitespace
  checks passed. No runtime code changed; engine acceptance was not rerun.
- Next: the four detailed views and README/architecture navigation.

Work on local `main`; do not push. This log replaces `docs/WORK_LOG.md` at the
owner's explicit request. The pre-existing deletions of that file and
`docs/IMPLEMENTATION_TASK.md` are preserved. The implementation specification is
the owner-provided attachment; `docs/DATASET_CONTRACT.md` remains normative.

## Research workspace — shared data helpers

- The owner authorized a same-repository research layer and a team-oriented README.
  Model code is explicitly allowed under `research/`; raw-event computation stays in Rust.
- Added optional research dependencies and the installed `ofi_pipeline.research` module.
  Feature loading validates accepted keys, UTC boundaries, finite numerical features,
  optional requested levels and preserved unknown TI. Lag helpers require all intervening
  intervals to be adjacent within a symbol/session and never mutate the input.
- Updated agent instructions for model locations, ignored result directories and the
  canonical `data/order_book_sample/` location. The separate Russian team-agent handoff
  requested by the owner will be delivered only in chat, not saved in this repository.
- Focused checks passed: `.venv/bin/python -m pytest -q tests/research/test_data.py`
  (10 tests, including compiled Rust output ingestion), Ruff for changed helpers/tests,
  and strict mypy (7 package source files). The sole pandas import annotation documents
  its missing bundled third-party stubs; production API checks remain enabled.
- This adds no change to Rust calculations or the core Python API.
- Intended commit: `feat(research): add validated feature loading and gap-safe lags`.

## Research workspace — runnable models and environment

- Added repository-local baseline, extension and notebook directories, JSON model
  configuration, a starter per-symbol/half-hour OFI/TI/joint OLS comparison with HC0
  covariance, common complete-case samples and explicit skipped-window reasons.
  Model runs record coefficients, metrics, source SHA256, configuration and versions.
- Added `scripts/setup.py` for source/native setup or current compatible wheel
  installation and `scripts/prepare_features.py` for one-time reusable feature output.
- Moved the unchanged ignored sample directory to `data/order_book_sample/`.
  Created new ignored feature/model outputs in the intended structured directories;
  old acceptance/benchmark outputs and historical evidence remain preserved.
- Extended CI/coverage selections for research tests and isolated wheel smoke checks
  for installed feature-loading/lag helpers. Hosted CI remains unrun; no push occurs.
- Passed: actual setup/native release compilation/import; 91 Python/integration/research
  tests; 17 focused research tests after model-metadata changes; Ruff over all Python,
  research, tests, scripts and benchmarks; strict package mypy; diff whitespace checks.
- Actual real-data workflow produced 4390 feature rows from the relocated bundle.
  The default baseline fitted 78 model/window combinations (26 windows x 3 models),
  with zero skipped fits. This is an in-sample starter, not OOS evidence or every
  paper table's full replication.
- Rebuilt the local release wheel and verified it in a fresh environment outside the
  repository: compiled native I/O, Python API/CLI, installed research loader and
  gap-safe lag helper passed. The wheel and all real/generated datasets remain ignored.
- No new full coverage measurement was made; previous engine evidence is historical.
- Intended commit: `feat(research): add reproducible baseline and shared setup`.
- Remaining: commit the team-facing README and current usage/testing navigation.

## Research workspace — team documentation

- Rewrote README as an English team entry point: installation/build, data placement,
  one-time feature computation, installed imports, starter baseline and explicit model,
  configuration, notebook, test and output locations for Fedya and Timur.
- Updated API/testing navigation for the research extra and canonical sample path.
  The README distinguishes historical engine acceptance from the new research layer;
  it does not recycle old coverage percentages as a new measurement.
- The separate Russian instructions requested for coworkers' AI agents are delivered
  only in the chat response. They are not written to a file or committed.
- Checks: reviewed README commands against actual setup, feature generation and model
  execution; reviewed local links; diff whitespace passed. No source behavior changed
  in this documentation step and no push was performed.
- Intended commit: `docs: explain the shared research workflow and model locations`.

## Original implementation checklist

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
- [x] M11: isolated wheel, coverage, CI, complete English handoff documentation.

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

## M11d — isolated wheel, CI and public contracts

- Added `scripts/wheel_check.py` and `.github/workflows/ci.yml`: isolated wheel
  API/CLI/error/Parquet/type-marker checks plus Linux/macOS/Windows Python
  3.10/3.12 build/import/test matrix and separate Linux instrumented coverage.
  Workflow YAML parses with both expected jobs. Hosted CI is unrun because
  commits remain local; no remote execution or publication was requested.
- Added English architecture and full output schema/interval contract;
  expanded usage/configuration/error/installation docs and reproducible checks.
  Updated verified schema with required execution price, precision-flag behavior
  and link to measured parity. Corrected AGENTS.md's obsolete deleted-document
  references to the owner-authorized attachment/CHANGELOG workflow.
- Final release checks passed:
  `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --release --locked --offline`
  (22.30 s compilation), `.venv/bin/maturin build --release --locked --offline --out dist`
  (21.71 s compilation; deployment target causes a separate artifact).
  `.venv/bin/python scripts/wheel_check.py 'dist/*.whl'` passed in a fresh temp
  Python 3.12 environment outside checkout; loaded native belongs to that venv.
  Hand fixture produced OFI [30,0], TI/volume [7,0], depth [125,125], quality
  [false,true,true]; installed CLI and typed missing-input error also passed.
- Wheel contains native shared library, Python API/CLI, _native.pyi and py.typed.
  No Rust compiler is used by the isolated installed-wheel test. Dependency
  download was limited to pinned inspection-only PyArrow in that temp venv.
- Checks passed: `ruby -e 'require "yaml"; p YAML.load_file(".github/workflows/ci.yml").fetch("jobs").keys'`,
  `.venv/bin/ruff check python tests benchmarks scripts`, `git diff --check`.
  Production source SHA256 still matches the committed coverage snapshot.
- Real data are unchanged and available. Final all-width acceptance is running
  against the current release. Removed only the task-generated stray profraw;
  canonical raw coverage evidence remains under ignored target output.
- Intended commit: `build: verify isolated wheels and define platform CI checks`.
- Remaining: final real acceptance, refreshed release metrics, handoff/status audit.

## M11e — final release acceptance and refreshed measurements

- Refreshed `docs/reconciliation.json` and `docs/performance.json` from current
  release output; added portable `docs/acceptance.json` with source SHA256,
  wheel hash and per-layer final checks. Dataset and generated tables remain
  ignored. All 24 delivered hashes and source archive hashes/sizes were checked.
- Exact final full check passed:
  `OFI_SAMPLE_DIR="$PWD/order_book_sample" OFI_REBUILD_REFERENCE=1 .venv/bin/python -m pytest -q tests/python tests/integration tests/real_sample --basetemp outputs/final-acceptance`
  (79 passed in 54.98 s; 74 self-contained and 5 actual real-width tests).
  Integer OFI L1..L5/TI/volume/counts, accepted keys and full quality agree at
  1/5/10/30/60 s. 10 s: 4390 accepted / 4680 total / 290 excluded, AAPL 2060,
  MSFT 2330; 3 delivered rounded MSFT timestamps. Float errors stay below
  declared USD 1e-10, ticks 1e-8, depth 1e-10 tolerances (depth exact).
- Rust final checks passed:
  `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test --workspace --locked --offline`
  (28 unit + 3 adapter + 2 pipeline; default external test explicitly ignored),
  `OFI_SAMPLE_DIR="$PWD/order_book_sample" cargo test -p ofi-core --test sample_ingestion --locked --offline -- --ignored`
  (1 passed in 21.99 s; 887810 events, 68404 trades, 897387 original rows,
  9577 rejected quotes). Rust 1.90/LLVM coverage tests also passed in M11c.
- Final release benchmarks ran sequential fresh processes after compiler/test
  jobs ended. Exact commands/configs/scopes are in `docs/performance.json`:
  real t1/c4096 4.0239 s, 99.27 MiB; t2/c65536 3.9107 s, 323.13 MiB;
  t4/c1 31.2190 s, 54.77 MiB; real Quote Test t2/c4096 4.3259 s, 102 MiB;
  authored 20k t2/c4096 0.1029 s, 62.31 MiB. Hardware M2 Pro/10 cores/16 GiB.
  Whole-process RSS, uncontrolled warm-leaning OS cache, one run per config;
  no general speedup or RSS guarantee. Compile/install excluded.
- PyArrow inspection asserted exact decoded features/full quality and stable
  manifest equality across known-direction chunks/threads. Quote Test quote
  features, accepted keys/quality and total trade volumes/counts are unchanged;
  classified/unclassified conservation is exact. Signing differences remain
  explicit unknown TI, not a parity claim against known direction.
- Intended commit: `test: record final release acceptance and measured determinism`.
- Remaining: English handoff/ordered local history, final repository audit.

## M11f — final English handoff and repository audit

- Added `docs/handoff.md` with API example, full final evidence, coverage limits,
  actual all-width parity, Quote Test conservation, measured release performance,
  operational limitations and ordered authoritative local commits. Updated README
  from bootstrap/pending language to verified completion. Marked M11 complete.
- Documentation points to reproducible commands, portable source/wheel hashes,
  schema/units and per-milestone evidence. Hosted platform CI remains explicitly
  unrun. No research model, GUI/server/database, TAQ claims or trading result
  was added. Optional standalone Rust CLI is omitted; installed Python CLI shares
  the engine. No real data or generated binary/output is committed.
- Final checks: docs/evidence consistency and link review, `git diff --check`,
  production SHA256 verification against measured coverage snapshot,
  `git status --short --branch`, `git ls-files order_book_sample raw data outputs dist`,
  and ordered `git log` audit. Functional/lint/type/coverage/wheel/real acceptance
  results are recorded in M11c–M11e; no production sources changed afterward.
- Repository status: all task changes committed after this entry; only the
  external `.gitignore` edit remains dirty. Cargo.lock is tracked despite its
  new ignore rule. Owner-requested docs deletions remain preserved. No push,
  release/package upload, PR or remote hosted execution occurred.
- Intended commit: `docs: hand off verified Rust pipeline and local acceptance`.
- Remaining required implementation work: none. Known limitations remain honest
  coverage/OS paths, unrun hosted platform matrix, scoped Lev-v1 data and
  documented filesystem/cache/temporary-disk behavior.

## Windows CI — close test-owned Parquet readers before overwrite

- Both supplied Windows/Python 3.10 and 3.12 logs successfully compiled the Rust
  workspace and passed core unit/adapter tests. They failed at the same owned-output
  overwrite in `crates/ofi-core/tests/pipeline.rs` with OS error 5 (access denied).
- The test retained its Parquet reader/file handle across directory replacement
  and backup cleanup. Explicitly drop that reader before overwrite, and scope the
  post-overwrite reader so it is also closed before later directory operations.
- Strengthened the existing cross-platform test: verify the rewritten Parquet is
  readable and both staging and backup directories are removed after success.
  No Windows test was disabled and the Windows CI matrix remains enabled.
- Production Rust, Python API, project structure and output semantics are unchanged;
  this avoids overlapping the separate optimization agent's implementation work.
- Checks passed on macOS: `cargo test -p ofi-core --test pipeline --locked --offline`
  (2 tests); `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test --workspace --locked --offline`
  (33 tests, 1 explicitly ignored external-sample test); `cargo fmt --all -- --check`;
  all-target workspace Clippy with `-D warnings`; diff whitespace review.
- Native Windows execution is unavailable on this host. The owner will push and
  verify both Windows jobs; local checks do not constitute a Windows CI pass.
- Intended local commit: `test: close Parquet readers before Windows overwrite`.
- No push, remote run, release or package publication was performed.

## Rust optimization P0 — baseline and measured plan (2026-10-14)

- Objective: improve execution speed/throughput first and memory second using only Rust implementation changes. Public interfaces, Python/research sources, numerical/quality/signing semantics, output/publication contracts, worker/chunk bounds and project layout are frozen. Work on local main; no push or publication.
- Verified nested repository root and clean working tree at `66e3978`. Read AGENTS.md, README.md, architecture, benchmark README/runner/generator, performance evidence, core/binding code and delivered reference preparation. Existing benchmark options were discovered with `--help`; benchmark workloads/configuration are unchanged.
- Inventory/grouping fixed before optimization: real known-direction family has t1/c4096, t2/c65536, t4/c1; real Quote Test has t2/c4096; authored 20,000-event/two-symbol family has t2/c4096. All cover hash/ingestion, OFI, aggregation, ordered Parquet assembly and publication. Known-direction covers independent execution signing; Quote Test additionally ZIP extraction, raw paired-row alignment, pre-book signing and unknown TI. The real input has rejected gaps/ties and two partitions; the fixture has alternating sizes and one execution per 100 rows. Chunk one stresses batch construction, queues and memory; t1/t2/t4 cover worker bounds; large chunks stress memory.
- Balanced aggregate: geometric mean of normalized case speedups within each family, then geometric mean of the three family means. Every per-case result remains primary; no raw-time averaging. Five serial fresh-process measured runs per case after one unmeasured warm-up per case, rounds in fixed case order. OS cache uncontrolled and warm leaning; no cold-cache measurements. No compilation, installation, fixture generation, profiling or test jobs overlap execution timings; other host activity is uncontrolled.
- Baseline current-source release rebuilt with `VIRTUAL_ENV="$PWD/.venv" PYO3_PYTHON="$PWD/.venv/bin/python" .venv/bin/maturin develop --release --locked --offline` (26.31s excluded). Rust/Cargo 1.98.0, LLVM 22.1.8, Python 3.12.0, macOS 26.5.1 arm64; Mac14,9 Apple M2 Pro, 10 cores (6 performance/4 efficiency), 16 GiB. Cargo.lock and build settings unchanged.
- Commands/evidence in existing ignored paths: `.venv/bin/python benchmarks/results/optimization_measure.py baseline` drives the unchanged `benchmarks/run.py` for every case; `benchmarks/results/optimization/baseline/metadata.json` stores full config definitions, input hashes/sizes, toolchain, commit and loaded-extension SHA256. Raw runs and complete outputs are retained alongside it. Fixture is the existing generator-authored `benchmarks/results/final-authored-fixture` (10,000 rows per symbol), not duplicated real data.
- `.venv/bin/python benchmarks/results/optimization_verify.py baseline` passed: all 30 decoded outputs have exact ordered values, schemas, floating values and nulls, exact manifests, and exact QC after excluding output paths/timing/observed worker peak. Known-direction chunk/thread invariance and Quote Test quote/quality/count/volume equality and classified/unclassified conservation passed.

| Existing case | Median seconds (min–max; MAD) | Median original rows/s | Median peak process MiB (min–max) |
| --- | --- | ---: | --- |
| real-t1-c4096 | 4.003722 (3.963808–4.299242; 0.039914) | 224,138 | 94.78 (89.55–102.58) |
| real-t2-c65536 | 4.259727 (3.950010–4.428237; 0.075049) | 210,668 | 242.22 (199.55–293.53) |
| real-t4-c1 | 33.139421 (32.214164–34.321532; 0.925257) | 27,079 | 51.92 (50.80–54.17) |
| quote-t2-c4096 | 4.358771 (4.347334–4.598869; 0.011438) | 205,881 | 98.25 (88.97–102.12) |
| fixture-t2-c4096 | 0.110453 (0.106891–0.119692; 0.003561) | 181,073 | 63.81 (59.05–67.28) |

- Source identities (SHA256; sizes in bytes):
  - `benchmarks/results/final-authored-fixture/data/events_clean.parquet`: `caf83a1859db44484a9f2e962771a00deed364eed211dfcb348dba32c7038146`, 190682.
  - `benchmarks/results/final-authored-fixture/data/trades_clean.parquet`: `1baa70fed833564919f98e2377e21ef142e80c27e75f4ef67e006de9205dc400`, 5790.
  - `benchmarks/results/final-authored-fixture/reports/event_quality.parquet`: `ac8fef7e0589fb219a23b4fe274335b6e3b416884a6074f00a5d2240d1de626c`, 182070.
  - `data/order_book_sample/data/events_clean.parquet`: `514dd1f6491ec99b2558054ccf0c3fb5add2c6d34e2d8e004b1ad0572a4cb2fa`, 25095171.
  - `data/order_book_sample/data/trades_clean.parquet`: `62db3864391b99accff35bbb734a5091d0df661fea3291f55e2037255cd02f3c`, 1306691.
  - `data/order_book_sample/reports/event_quality.parquet`: `fe0f0806b59f122c22bdcc74df01f4fbb85dc8e8a81a53fde5f1d1f51d230b13`, 8137742.
  - `data/order_book_sample/raw/LOBSTER_SampleFile_AAPL_2012-06-21_5.zip`: `46419dd0d6106be5fcf43600ccd08b2baa5d4cfb76284f1c58773537a3adac50`, 4791006.
  - `data/order_book_sample/raw/LOBSTER_SampleFile_MSFT_2012-06-21_5.zip`: `94e65c07786b8d54712fe9a12aee29d51f418d402e96b6e21b4af1d0bd44131d`, 7515038.
- Profiling: `/usr/bin/sample <own-benchmark-pid> 3 1 -mayDie -file <ignored-profile>` succeeded outside the sandbox for normal (t2/c65536), tiny (t4/c1) and Quote Test (t2/c4096). Sandbox-only attempts could not inspect the processes; they are not claimed as successful profiles. Profiling runs were separate from measured runs.
- Normal profile shows 303 inclusive samples in format_inner, 281 in Row::index and 123 in validate_local_ns plus 68 in date_for_timestamp, across 1473 sampled main-thread stacks. These inclusive counts can overlap and are diagnostic, not additive timing percentages. Tiny profile shows 1503 inclusive read_records samples among 2208 main-thread stacks; Arrow per-batch work dominates. Worker synchronization is present but less prominent. Profiles retained under `benchmarks/results/optimization/profile-*-authorized.txt`.
- Plan: independently test/measure metadata/allocation reductions in ingestion, bounded reuse of parsed calendar metadata with per-row checks preserved, and remaining measured allocation bottlenecks. Keep only supported improvements; investigate regressions. Each retained focused subtask gets Rust tests, rebuilt compiled integration checks, all affected benchmarks, diff review, log evidence and a local commit. Final handoff requires full correctness/research/real-width acceptance, isolated wheel and complete final benchmarks.

## Rust optimization P1 — avoid per-cell metadata allocation

- Hypothesis from baseline sampling: per-event book-column formatting, duplicated Parquet string-column lookup, and allocation of a timestamp type descriptor consume producer CPU. Replaced book-name formatting with fixed names for all five supported ranks, used one name lookup for Parquet text, and matched the timestamp type/timezone without allocating. All schema/type/null/price checks and required/optional fields remain in place; reader batch size, worker queues and output buffers are unchanged. No new dependency/build setting/unsafe code.
- Added a focused Rust adapter regression for every depth 1..5, reversed physical column ordering, chunks 1/2 and nonrepresentable last-rank prices. Existing Parquet null/schema/error and CSV/gzip tests remain unchanged.
- Passed `cargo fmt --all`; `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test -p ofi-core --test adapters --locked --offline` (4 tests); rebuilt release via the P0 maturin command (4.22s excluded); `.venv/bin/python -m pytest -q tests/integration/test_pipeline.py tests/integration/test_parallel.py tests/integration/test_native.py` (26 passed). Inspected the focused diff and ran `git diff --check`.
- Complete five-case, five-run measurements plus one warm-up: `.venv/bin/python benchmarks/results/optimization_measure.py columns`. `.venv/bin/python benchmarks/results/optimization_verify.py columns` passed exact decoded tables/schema/null/float/order/manifest/stable-QC parity for all 30 outputs, source identity equality, chunk/thread invariance and Quote Test conservation. Generated evidence stays ignored.
- Results below use P0 baseline and identical conditions. Real known-direction normal chunks and Quote Test ranges separate clearly from baseline; tiny-chunk improvement is smaller but ranges also separate. Authored fixture shows improvement in the median with overlapping/outlier ranges, so its precise magnitude remains noisy. RSS ranges overlap in all cases; the +4.0% t1 median is inconclusive rather than a memory improvement. Active workers stay 1/2/2/2/2. Retained for consistent execution improvements without expanded memory/worker bounds.

| Case | Median s (min–max; MAD) | Rows/s | Peak MiB (min–max) | Speedup vs baseline / previous |
| --- | --- | ---: | --- | --- |
| real-t1-c4096 | 2.988045 (2.925521–3.010416; 0.012983) | 300,326 | 98.59 (90.47–109.59) | 1.340x / 1.340x |
| real-t2-c65536 | 3.062198 (2.915328–3.128592; 0.066394) | 293,053 | 201.08 (185.31–282.55) | 1.391x / 1.391x |
| real-t4-c1 | 31.194508 (30.919520–31.516923; 0.274988) | 28,767 | 51.19 (49.84–53.91) | 1.062x / 1.062x |
| quote-t2-c4096 | 3.400197 (3.321258–3.455427; 0.047077) | 263,922 | 95.16 (90.25–99.31) | 1.282x / 1.282x |
| fixture-t2-c4096 | 0.090778 (0.086294–0.121728; 0.004485) | 220,317 | 62.44 (61.41–65.14) | 1.217x / 1.217x |
Family speedups: {"real-direction": 1.2557329911622168, "authored": 1.2167305691766097, "real-quote": 1.2819172856587175} balanced: 1.2511726503903464

- Decision: retain. Balanced family-weighted speedup 1.251x; all case median times improved. Next: remove repeated calendar parsing/formatting while retaining per-row validation.

## Rust optimization P2 — reuse bounded calendar metadata

- Hypothesis from P0 profiling: repeated date/clock parsing and formatting wastes producer CPU even though the parsed local midnight repeats across adjacent rows. Added one-entry calendar metadata per TableReader: parsed midnight and formatted quality date. Local New York date is still derived per quality row (no fixed 24-hour DST assumption); every row checks local-day range, checked midnight-plus-nanoseconds arithmetic and exact timestamp agreement. Date changes replace the entry; invalid/overflowing dates preserve existing errors. No event/output result caching, sorting or validation removal. Memory state stays constant per reader, independent of rows/partitions; all batch/queue/worker bounds remain unchanged.
- Added Rust regression coverage for date replacement/return, winter/summer and DST transition dates, repeated dates, invalid dates, nonrepresentable midnight, time range, timestamp mismatch and int64 extrema. Public time functions/signatures and Row enum remain unchanged.
- Passed `cargo fmt --all`; `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test -p ofi-core --locked --offline` (29 units + 4 adapters + 2 pipeline; external ingestion explicitly ignored pending final explicit run); rebuilt release via P0 command (4.87s excluded); `.venv/bin/python -m pytest -q tests/integration/test_pipeline.py tests/integration/test_parallel.py tests/integration/test_native.py tests/integration/test_quote_test.py` (37 passed). Inspected diff and passed `git diff --check`.
- Same complete benchmark protocol: `.venv/bin/python benchmarks/results/optimization_measure.py calendar`; `.venv/bin/python benchmarks/results/optimization_verify.py calendar` passed source identity plus all 30 complete outputs exactly, chunk/thread invariance and Quote Test conservation. `calendar/metadata.json` additionally records Rust source SHA256, lockfile SHA256 and working-tree changes; loaded extension hash is captured. These are final-source suite measurements if no further production edits are retained.
- Comparison below includes baseline and incremental P1 speedups. Normal real-input improvements are clearly beyond noise; incremental tiny-chunk and authored-fixture gains are less certain because ranges overlap. Every final case time range is below its baseline range. All median times improved; no execution regression was observed.
- RSS remains inconclusive: t1 median is +5.6% vs baseline, t2 -4.4%, tiny +0.7%, Quote Test +1.6%, fixture +0.1%; ranges overlap and t2 has a larger maximum. No memory reduction is claimed. Reviewed allocations/state/buffering: two small one-entry metadata values per reader are added; no larger input/output buffer, batch, queue or worker count. Faster producer/consumer scheduling can change occupancy/allocator peaks, which is an inference rather than a demonstrated cause. Prioritize measured execution gains while retaining the existing operational bounds.

| Case | Median s (min–max; MAD) | Rows/s | Peak MiB (min–max) | Speedup vs baseline / previous |
| --- | --- | ---: | --- | --- |
| real-t1-c4096 | 2.487382 (2.413924–2.512182; 0.024800) | 360,776 | 100.11 (94.33–101.06) | 1.610x / 1.201x |
| real-t2-c65536 | 2.422396 (2.371252–2.460587; 0.029998) | 370,454 | 231.53 (198.98–334.84) | 1.758x / 1.264x |
| real-t4-c1 | 30.477616 (30.403882–30.970772; 0.073734) | 29,444 | 52.27 (50.25–55.59) | 1.087x / 1.024x |
| quote-t2-c4096 | 3.162698 (3.118882–3.249435; 0.012279) | 283,741 | 99.83 (91.52–109.59) | 1.378x / 1.075x |
| fixture-t2-c4096 | 0.079602 (0.072534–0.090688; 0.006802) | 251,250 | 63.89 (59.16–66.91) | 1.388x / 1.140x |
Family speedups: {"authored": 1.387565515394952, "real-quote": 1.3781811460777311, "real-direction": 1.4545901845478582} balanced: 1.4063718069161835

- Decision: retain. Baseline-to-final balanced family-weighted speedup 1.406x. Remaining: complete workspace/compiled/research/real-width acceptance, explicit Rust real ingestion, isolated final wheel, final profiling and handoff audit.

## Rust optimization P3 — final acceptance and handoff

- Retained production changes are commits `39388ee` (per-cell metadata allocation) and `7bbe1aa` (bounded parsed local-day metadata); baseline protocol/evidence is `c4c2aba`. The independently authored `c0ce6a6` Rust test portability/log commit arrived during the profiling phase and was preserved. It changed no production implementation, inputs or benchmark workload. No unrelated change was reverted, staged or amended by this optimization task.
- Final-source correctness passed:
  - `cargo fmt --all -- --check`.
  - `PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --workspace --all-targets --locked --offline -- -D warnings`.
  - `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test --workspace --locked --offline`: 29 core units, 4 adapter tests and 2 pipeline tests passed. External sample test is ignored by the default suite, then explicitly executed below.
  - `OFI_SAMPLE_DIR="$PWD/data/order_book_sample" cargo test -p ofi-core --test sample_ingestion --locked --offline -- --ignored`: one real-data ingestion test passed (15.01s).
  - `CARGO_TARGET_DIR=target/msrv PYO3_PYTHON="$PWD/.venv/bin/python" /Users/daniilparfenov/.cargo/bin/cargo +1.90.0 test --workspace --locked --offline`: the same 35 self-contained Rust tests passed; opt-in external test is ignored on this toolchain, not claimed as run twice.
  - `OFI_SAMPLE_DIR="$PWD/data/order_book_sample" OFI_REBUILD_REFERENCE=1 .venv/bin/python -m pytest -q tests/python tests/integration tests/research tests/real_sample --basetemp outputs/features/optimization-acceptance`: 96 passed, no skips (55.07s). Actual newly rebuilt native-extension calls, CSV/gzip/Parquet, null/unknown TI, tied timestamps, gaps/sessions/incomplete buckets, chunk/thread invariance, typed errors and publication/overwrite fault protections are covered by these existing tests.
  - `.venv/bin/ruff check python research tests benchmarks scripts`; `.venv/bin/mypy` (7 package source files); `git diff --check`.
- All 24 delivered hashes and raw archive source identities passed real acceptance. Independently rebuilt reference widths 1/5/10/30/60s passed exact accepted keys/quality/integer OFI L1..L5/TI/volume/counts. Accepted counts are 45,966 / 8,985 / 4,390 / 1,382 / 650. Maximum midpoint-change error across widths is 2.183e-13 USD and 2.183e-11 ticks; depth exact, below existing 1e-10 USD / 1e-8 ticks / 1e-10 depth tolerances. Reconciliation reports are retained under ignored `outputs/features/optimization-acceptance`.
- Final wheel: `PYO3_PYTHON="$PWD/.venv/bin/python" .venv/bin/maturin build --release --locked --offline --out dist` passed (39.03s build excluded). `.venv/bin/python scripts/wheel_check.py 'dist/*.whl'` passed outside the checkout in a fresh Python 3.12 venv: local-wheel API/CLI invoke its installed native library, hand-calculated OFI/TI/volume/depth/quality, manifest, missing-input errors, research loader/lag helper and bundled stubs/type markers. No Rust compiler is used by the isolated installation. Log retained in `benchmarks/results/optimization/wheel-check.log`.
- Ignored local wheel SHA256: `d3b6cffa30e2ac1a1ce6bb5529acaf279047cee2003f2805d3d7dfe28d188919`. No wheel/package was published.
- Final benchmark evidence is the complete `calendar` suite, measured after the final production changes, with the same warm-up/five-run serial fresh-process policy as P0. Source, Cargo.lock and measured loaded-extension SHA256 were audited unchanged after full tests and wheel build. No extra favorable runs were substituted; compilation, profiling, fixture creation and correctness checks are outside all measured calls. Exact baseline/final decoded-equivalence evidence is in `baseline/equivalence.json` and `calendar/equivalence.json` (30 complete outputs each); all schema, ordered integers/floats/nulls, full quality, manifests and stable QC match exactly.

Baseline to final (B → F); time variability is median absolute deviation; process RSS variability is observed min–max, not a bound:

| Case | Median seconds B → F (MAD B → F) | Median original krows/s B → F | Median peak MiB B → F (range B → F) | Speedup |
| --- | --- | ---: | --- | ---: |
| real-t1-c4096 | 4.003722 → 2.487382 (0.039914 → 0.024800) | 224.138 → 360.776 | 94.78 → 100.11 (89.55–102.58 → 94.33–101.06) | 1.610x |
| real-t2-c65536 | 4.259727 → 2.422396 (0.075049 → 0.029998) | 210.668 → 370.454 | 242.22 → 231.53 (199.55–293.53 → 198.98–334.84) | 1.758x |
| real-t4-c1 | 33.139421 → 30.477616 (0.925257 → 0.073734) | 27.079 → 29.444 | 51.92 → 52.27 (50.80–54.17 → 50.25–55.59) | 1.087x |
| quote-t2-c4096 | 4.358771 → 3.162698 (0.011438 → 0.012279) | 205.881 → 283.741 | 98.25 → 99.83 (88.97–102.12 → 91.52–109.59) | 1.378x |
| fixture-t2-c4096 | 0.110453 → 0.079602 (0.003561 → 0.006802) | 181.073 → 251.250 | 63.81 → 63.89 (59.05–67.28 → 59.16–66.91) | 1.388x |

- Balanced aggregate: real-direction family 1.455x, real Quote Test 1.378x, authored family 1.388x; equal-family geometric mean **1.406x**. Every case median improved. Final execution ranges separate from baseline; exact magnitude, particularly short fixture runs, remains subject to uncontrolled host/cache variation. No cold-cache or universal speedup claim.
- No execution regressions observed. Memory benefit remains inconclusive: overlapping ranges, t1 median increased 5.6%, and t2 final maximum is 334.84 MiB vs baseline 293.53 MiB despite its lower median. Configured chunk/output buffers, queues and worker limits are unchanged; speed is the first priority. Peak workers remain within limits. These are whole-process fresh-process RSS observations, not guaranteed upper bounds.
- Final profiles: own-process `/usr/bin/sample` captures retained as `profile-final-tiny.txt`, `profile-final-quote.txt` and `profile-final-normal-loop.txt`. The initial final-normal process ended before useful stacks were captured (empty profile); repeated identical public calls in one diagnostic process captured 2199 main-thread samples. No profile elapsed time is benchmark evidence. In that normal diagnostic, book-name format_inner no longer appears; Row::index has 781 inclusive samples, hash_one 519 and read_records 591 (overlapping counts). One-row profile retains 1115 read_records samples and 95 synchronization samples. Remaining bottlenecks are per-batch Arrow materialization at tiny chunks, name hashing/downcasts, allocator/key/book copies and raw CSV/ZIP work in Quote Test. Larger decoder batches could change memory bounds, so no speculative batching rewrite was retained.
- Final audit: only existing Rust adapter/time files and Rust adapter tests changed in this task, plus allowed CHANGELOG updates. Python/research/binding sources, public signatures/config/defaults/supported values, benchmark sources/configurations, dependencies/Cargo.lock/build profiles and project structure are unchanged. OFI/signing/interval/gap/precision/quality/hash/publication contracts are preserved, supported by the checks above. Generated data/results/profiles/binaries stay in existing ignored locations. No new coverage percentage or hosted cross-platform CI result is claimed.
- Final working tree was clean after the implementation commits; this administrative evidence update is committed separately and status rechecked afterward. No push, PR, release/package upload, remote-setting change or deployment was performed. Owner reviews and pushes local commits. Required optimization and validation work is complete; remaining bottlenecks and inconclusive RSS effects are disclosed above.
