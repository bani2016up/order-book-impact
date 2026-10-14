# Release measurements

For bounded 1M/10M/20M workloads, repeatable fresh-process measurements, RSS
snapshots and baseline comparison, use the [high-load protocol](HIGH_LOAD.md).
The original small fixture below keeps its existing workload unchanged and
is not intended for multi-million-row generation.

Build/install the current release extension first; exclude build/install from run
measurements. Run each command in a fresh Python process with no simultaneous
project compilation. Hardware and cache assumptions are in `docs/performance.json`.

```sh
VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --release --locked
.venv/bin/python benchmarks/run.py --sample-dir /path/to/order_book_sample \
  --output-dir /new/results --threads 2 --chunk-rows 65536 --label real-delivered
.venv/bin/python benchmarks/make_fixture.py /new/authored-fixture --rows-per-symbol 10000
.venv/bin/python benchmarks/run.py --sample-dir /new/authored-fixture \
  --output-dir /new/fixture-result --threads 2 --chunk-rows 4096 \
  --label authored-synthetic-20000-events
```

The generator authors two symbols with alternating sizes and one execution per
100 rows at 100ms spacing. It is not real market data or a duplicated sample day.
Fixture generation is outside the benchmark process/timing. PyArrow is an
inspection/generation dependency only; the measured process imports the API and
native core, not Python computation libraries. The runner uses POSIX `resource`
RSS reporting (macOS/Linux); Windows wheel/import correctness is tested in CI.

Measurements include input hashing, all computation, intermediate output assembly
and atomic publication. `wall_seconds` is the complete public-call elapsed time;
QC `native_seconds` is sampled just before final QC JSON/publication. Source and
output compression, config, rows/second, process RSS and peak worker count are
recorded. OS cache is not forcibly dropped; runs lean warm. One run per config is
an observed measurement, not a general throughput guarantee or statistically
estimated speedup. Compare decoded outputs, not compressed file bytes.
