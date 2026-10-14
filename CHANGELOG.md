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
- [ ] M5: independent executions, known-direction signing and conservation.
- [ ] M6: right-closed grids, original boundaries, depth and exclusions.
- [ ] M7: atomic output, provenance/QC, typed errors, Python CLI.
- [ ] M8: paired raw adapter and pre-execution Quote Test.
- [ ] M9: full real sample integrity/parity and independently rebuilt other widths.
- [ ] M10: bounded partition concurrency, chunk/thread invariance and benchmarks.
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
