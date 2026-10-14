# Implementation work log

Work on local `main`; do not push. This log replaces `docs/WORK_LOG.md` at the
owner's explicit request. The pre-existing deletions of that file and
`docs/IMPLEMENTATION_TASK.md` are preserved. The implementation specification is
the owner-provided attachment; `docs/DATASET_CONTRACT.md` remains normative.

## Checklist

- [x] M0: inspect repository, delivery integrity, physical schemas, preparation code.
- [x] M1: pure Rust workspace, compiled PyO3 extension, typed Python package.
- [ ] M2: checked domain types, sessions, decimal time, configuration and ordering.
- [ ] M3: streaming Parquet/gzip CSV and original quality alignment.
- [ ] M4: gap-aware rank OFI, persistent state and L1 update classification.
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
