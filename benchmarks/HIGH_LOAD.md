# High-load benchmark protocol

This harness measures the **existing compiled Rust pipeline**, reached through
the public Python/PyO3 API. It does not optimize the engine or change its
interfaces. Workloads are explicitly authored synthetic data, not duplicated
LOBSTER days, market observations or a claim about production-market throughput.

## Quick start

Run from the repository root in the configured environment. The existing
`research` extra supplies NumPy, PyArrow and optional Matplotlib plotting.
RSS instrumentation currently supports **macOS/Linux**, as does the existing
`benchmarks/run.py`; this limitation does not change Windows package support.

A small smoke run, with a release build before measurements:

```sh
.venv/bin/python -m benchmarks.high_load \
  --root benchmarks/results/high-load/smoke \
  --sizes 10000 --partitions 4 --warmups 0 --repetitions 1
```

The default suite is **1M, 10M and 20M original events**, two configurations,
one warmup and three measured fresh processes per case:

```sh
.venv/bin/python -m benchmarks.high_load \
  --root benchmarks/results/high-load/baseline
.venv/bin/python -m benchmarks.high_load_plot \
  benchmarks/results/high-load/baseline
```

Use a new result root for every invocation. Existing outputs are never replaced.
The suite builds/installs with `maturin develop --release --locked` before fixture
generation and timing. Add `--offline` when dependencies are already cached.
`--no-build` is available for an installed wheel or smoke tests, but its build
profile is recorded as **unverified**, not assumed to be release.

## Workload semantics

- `--sizes` counts original quality rows. Accepted event rows and execution rows
  are separate tables; their combined physical row count is larger. Metadata
  records all counts. The standard sizes are exactly 1,000,000 / 10,000,000 /
  20,000,000 original rows.
- Default: four independent synthetic symbols on 2012-06-21, each covering the
  full 09:30–16:00 New York session. Integer timestamps stay strictly inside the
  session regardless of row count. Row IDs restart at zero per partition.
- All five ranks change, with deterministic varied prices, spreads and sizes.
  Type-4/type-5 executions occur every 25 rows; signs alternate. Type-5 executions
  lie inside the original pre-spread. Supplied quality gaps occur every 100,003
  rows, with correct segment/predecessor/L1-update evidence.
- These are stress-test states, not a calibrated market model. Rejections are
  authored supplied gaps labeled with the existing rejection vocabulary, not
  an estimated market spread percentile. No paper/reference features are generated.
- A stateless row-indexed construction makes decoded inputs invariant to generation
  batch size. `--batch-rows` (default 65,536) bounds generation memory; arrays and
  Parquet tables are written per batch, never collected for the entire dataset.
  Parquet footer metadata still grows with row-group count.
- Generation, SHA-256 verification and build time are excluded from measured
  pipeline calls. Generation writes to a private stage and publishes a completed
  fixture; it refuses to overwrite an existing directory.

Defaults exercise two useful operating points: `t1-c4096` (one worker, small
chunks) and `t4-c65536` (up to four workers, larger chunks). They differ in both
thread and chunk settings; their difference does not isolate thread scaling.
Add `t4-c4096` to isolate thread scaling at the small-chunk size.

## Additional scenarios

Many independent sessions, using a separate fixture root:

```sh
.venv/bin/python -m benchmarks.high_load \
  --root benchmarks/results/high-load/many-sessions \
  --fixture-root data/high_load_many \
  --sizes 10000000 20000000 --partitions 32 \
  --cases t1-c4096 t4-c4096 t4-c65536
```

One long partition exposes serial stateful processing; extra workers cannot
parallelize an arbitrary chunk of one session:

```sh
.venv/bin/python -m benchmarks.high_load \
  --root benchmarks/results/high-load/single-session \
  --fixture-root data/high_load_single \
  --sizes 10000000 20000000 --partitions 1
```

Optional Quote Test creates bounded original paired raw CSVs and tests both
signing paths. Use another fixture root because source identities/settings differ:

```sh
.venv/bin/python -m benchmarks.high_load \
  --root benchmarks/results/high-load/quote-test \
  --fixture-root data/high_load_raw \
  --sizes 10000000 20000000 --signings lobster_direction quote_test
```

Raw CSV generation takes extra time and disk; this scenario does not exercise ZIP
extraction. Start with a small size to validate the selected environment.
`--session-seconds 60` is for smoke tests; the standard load suite uses 23,400.
Bucket widths remain the existing supported 1/5/10/30/60 seconds.

## Measurements and snapshots

Each warmup/repeat runs serially in a **fresh Python process**. The measured child
imports the API, native extension and standard-library instrumentation; it does
not import NumPy, pandas or PyArrow. Rust owns all production computation.

The measured wall window is the complete public `run_pipeline` call: hashing,
input decoding, OFI/signing/buckets, private partition Parquet, ordered assembly
and final publication. Configuration construction, process startup, build,
generation, parent-side verification and plotting are outside that window.

RSS has two distinct measurements:

- OS high-water RSS via `resource.getrusage`, up to native-call completion,
  including imports and the sampler thread. This provides the reported peak.
- Current RSS snapshots every 0.5 seconds by default. A self-process thread reads
  Linux `/proc/self/status` or macOS
  [MACH_TASK_BASIC_INFO](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/mach/task_info.h).
  It works while PyO3 detaches from Python and needs no process-list permissions.
  Its small time/memory cost is included consistently in every measured run.
  The trace begins just before the native call, not at OS process launch.
  Sampling can miss short spikes; OS accounting methods can differ across platforms.

CPU time and major/minor page faults are also recorded. Summary statistics are
median, min/max and median absolute deviation; warmups are excluded. Cache state
is uncontrolled and leans warm after generation/identity reads and warmups.
There is no cold-cache, thermal-state or universal throughput guarantee.

Do not compile, run other benchmarks or execute CPU-heavy tests concurrently with
a measurement. Repeated processes and input/output equality are required before
comparing speed. Three repetitions are a starting protocol, not a statistical
proof; rerun a complete unchanged suite if variability obscures a decision.

## Evidence and correctness

The result root contains:

```text
summary.json / summary.csv / report.md   protocol, provenance, repetitions, aggregates
build.log                              release-build command and output
generate-<size>.log                     generator output, outside measured calls
<case>-warmup-*/                        excluded fresh-process warmups
<case>-run-*/
  command.json                         exact child command
  phase.json                           running / finished / failed state
  measurement.json                     raw native-call measurement and partition report
  verified.json                        measurement plus post-run correctness checks
  rss.jsonl                            current RSS / time / phase snapshots
  stdout.log / stderr.log               diagnostic output
scaling.png / scaling.svg               optional plots from high_load_plot
rss-traces.png                         first measured repeat per case; no cherry-picked run
```

Generated input is ignored under `data/high_load/`; native feature outputs are
ignored under `outputs/features/high-load/<suite-name-and-path-hash>/`. Keep them
for baseline comparisons. Full evidence is ignored under `benchmarks/results/`.
Only code, tests, instructions and a compact measured report belong in Git.

Outside the timed child, verification checks expected partition/event/trade/sign
counts, total volume, classified/unknown splits, complete bucket grid, UTC/schema,
accepted feature counts, key ordering and native source hashes. Canonical decoded
row fingerprints must match across repeats and chunk/thread cases for each signing
mode. Empty accepted output is valid and handled explicitly; it is not fabricated
as zero-valued features. These checks supplement existing small-formula and real
sample acceptance tests; they are not a second full Python OFI engine.

Snapshots include engine/harness source hashes, Git state, loaded extension path,
SHA-256/version, runtime/platform, host identity hash and build provenance. Source
and binary identities are checked again after the suite; changes during a run
invalidate completion. Failed/timeout runs retain partial evidence and logs and
never produce a successful complete report.

## Later Rust optimization

Reuse the exact fixtures, sizes, cases, signing modes, bucket width, repetitions,
warmups, snapshot interval, hardware/runtime and release build:

```sh
.venv/bin/python -m benchmarks.high_load \
  --root benchmarks/results/high-load/candidate \
  --reuse-fixtures \
  --compare-to benchmarks/results/high-load/baseline/summary.json
```

For a nondefault baseline, repeat its original CLI options. Reused fixtures must
match generation version/settings and every source SHA-256. Comparison refuses
different protocols, inputs, host/runtime, harness hashes or build provenance.
Every candidate decoded output must match the saved baseline. Reports expose
per-case speed/RSS ratios and an equal-case geometric speedup; inspect all cases
and variability before accepting an optimization. No production optimization is
part of this benchmark implementation.

## Focused checks

```sh
.venv/bin/python -m pytest -q tests/benchmarks
.venv/bin/ruff check benchmarks tests/benchmarks
```

CI runs small authored fixture/harness checks; it does not generate or process
10M/20M rows on every push. The macOS/Linux harness checks are skipped on Windows;
small fixture/native-signing checks remain cross-platform.
