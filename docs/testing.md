# Reproducible checks

Run from the repository with a Python 3.10+ environment. Install the `test` and
`dev` extras or their pinned tools. Production computation has no Python data
library dependencies. Build a fresh extension whenever native contracts change.

```sh
PYO3_PYTHON="$PWD/.venv/bin/python" cargo test --workspace --locked
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --locked
.venv/bin/python -m pytest -q tests/python tests/integration
.venv/bin/ruff check python tests
.venv/bin/mypy
```

Fixtures are authored and synthetic; their provenance and independent numerical
expectations are in `tests/fixtures/PROVENANCE.md`. Compiled integration asserts
that `_native` is a shared library, poisons oracle files, and checks actual
Rust-produced Parquet and JSON. Chunk sizes 1/2/3/100 split ties, gaps, execution
matches and boundaries. Input formats must give identical decoded outputs.

Real acceptance is opt-in and skips explicitly without the owner-provided bundle:

```sh
OFI_SAMPLE_DIR=/path/to/order_book_sample .venv/bin/python -m pytest -q tests/real_sample
OFI_SAMPLE_DIR=/path/to/order_book_sample OFI_REBUILD_REFERENCE=1 \
  .venv/bin/python -m pytest -q tests/real_sample --basetemp outputs/acceptance
OFI_SAMPLE_DIR=/path/to/order_book_sample \
  cargo test -p ofi-core --test sample_ingestion -- --ignored
```

Install `real-test` extras for the rebuilt references. The sample fixture verifies
all delivery hashes, archive source hashes/sizes, actual row counts/types/nulls
before acceptance. Production recomputation precedes reading feature/mask oracles.
Reference preparation is imported in tests only, never production. The inspected
source runs its original raw-row book/quality computation; tests compare all
accepted keys, all quality flags, all five ranks, TI, volume, event/L1 counts,
USD/tick price changes and depth. Integer values/keys must match exactly.
Absolute float tolerances: USD 1e-10, ticks 1e-8, depth 1e-10 shares. Mismatch
reports retain missing/extra keys, counts, first mismatches and max errors.

`docs/reconciliation.json` records observed acceptance on 2026-10-14. This is
actual real-data evidence, not a count inferred from the description. Default
self-contained tests do not substitute for external acceptance.

Coverage, isolated-wheel checks and platform CI commands are being added in M11.
