# Supervised Rust pipeline optimization — 2026-10-14

The retained implementation is **1.619× faster** across the equally weighted regular benchmark families, **2.129×** across the six warm high-load cases, and **2.179×** across the six verified low-residency cases. These are geometric means of measured median speedups on one host, not universal guarantees.

Execution time was the first priority. **Overall memory reduction was not achieved:** final warm high-load RSS medians increased and the largest measured warm process peak was 609.48 MiB, versus 292.86 MiB in the warm baseline. The cold-series maximum increased from 364.94 to 615.14 MiB. No interface, schema, configuration default, feature semantics or operational worker/chunk bounds changed.

The [compact machine-readable evidence](optimization-results-20261014.json) retains every case median, range, MAD, throughput, RSS range, protocol, source/native identity and reference-summary SHA-256. The [original warm baseline](README.md) and [cold protocol/baseline](../COLD_INPUT_BENCHMARK.md) remain unchanged.

## Retained changes

| Local implementation commit | Change |
| --- | --- |
| `0516002` | Resolve the 39 canonical clean-input column indices once; private indexed access replaces repeated per-cell string/hash lookup. Public `Row` and `Reader` interfaces, arbitrary column order and lazy optional-field validation are preserved. |
| `3810fad` | Reuse owned validated key strings and retained book vectors in order guards, OFI and bucket state; retain only the previous book needed by OFI. Compare partition keys by borrowing, cloning only at a switch. |
| `75a619d` | Reuse the two raw CSV records and reserve the already validated book depth, reducing allocation work for Quote Test/raw input. |
| `2b53b01` | Drop exhausted clean-input readers after alignment/nonempty-input checks and before final handoff/assembly. |

All production changes are in `crates/ofi-core/`. Python, PyO3 bindings, research models, public Rust types/signatures, output publication, error precedence and row-consumption behavior remain compatible. Reused state remains independently owned; tests exercise caller mutations and failures. Key buffers can retain capacity for the largest previously seen symbol/date; no absolute memory bound is claimed. Raw buffer reuse and reader drops were measured jointly, so their individual effects cannot be separated.

## Baselines, supervision and measurement policy

Optimization and independent reviews used zero-context subagents with explicit English prompts. The supervisor granted one exclusive heavy measurement/build/test slot, checked evidence and compatibility, retained successful small commits, rejected unfavorable candidates, and completed final acceptance. No benchmark ran concurrently with a build, heavy test, profile or large-data inspection from this task. Other host activity remained uncontrolled.

The current-task regular baseline was freshly measured at `a662211`, not the older P0 baseline still embedded in historical regular summaries. The tables below deliberately compare the two summaries' `candidate` measurements. The preserved warm high-load baseline was made at `ecdaa97`, with the same production engine as `a662211`; the new cold helper baseline was frozen at `a910217`. Later log-only commits do not change the measured source closure.

Host: Apple M2 Pro, 10 logical CPUs, 16 GiB; macOS 26.5.1 arm64; Python 3.12.0; release native build with Rust 1.98.0 and unchanged lockfile/build profiles. Every measured call uses a fresh Python process. Input generation, compilation, process startup, output verification and plotting are outside the public-call timer. The timer includes source hashing, Python/PyO3 dispatch, Rust processing, assembly and publication.

Existing benchmark definitions, fixture bytes, dependencies, Cargo.lock and settings were frozen. Source snapshots also include the pre-existing ignored Python helpers under `benchmarks/results`; they were not edited or replaced. Matching this machine's archived comparison requires that complete source/input closure. A fresh clone or different machine should establish a fresh baseline rather than silently relaxing identity guards.

## Regular benchmark: five cases, 25 measured calls

One excluded warmup and five measured fresh-process repetitions per case, serially in rounds. Each table entry is median (min–max; median absolute deviation), in seconds. Cache is uncontrolled and warm leaning.

| Case | Before s (range; MAD) | After s (range; MAD) | Speedup | RSS median MiB before → after |
| --- | --- | --- | ---: | ---: |
| real-t1-c4096 | 2.377169 (2.325388–2.391985; 0.014816) | 1.227469 (1.210033–1.353651; 0.017436) | 1.937× | 117.11 → 114.73 |
| real-t2-c65536 | 2.327638 (2.298553–2.363010; 0.028670) | 1.143882 (1.094324–1.151189; 0.007308) | 2.035× | 356.75 → 245.88 |
| real-t4-c1 | 29.688308 (29.338581–30.544158; 0.264505) | 28.531394 (28.359381–28.926279; 0.172013) | 1.041× | 57.33 → 51.80 |
| quote-t2-c4096 | 3.056617 (2.967872–3.220844; 0.088745) | 1.689398 (1.594320–1.884494; 0.053021) | 1.809× | 106.06 → 113.91 |
| fixture-t2-c4096 | 0.072252 (0.071272–0.077444; 0.000980) | 0.049278 (0.048535–0.052941; 0.000390) | 1.466× | 63.27 → 58.66 |

Regular aggregate: first take a geometric mean within the three real-direction cases, then an equal-weight geometric mean of real-direction, real Quote Test and authored-fixture families. This avoids letting three related cases dominate the two other families.
Family speedups: real-direction **1.601×**, real-quote **1.809×**, authored **1.466×**; balanced **1.619×**, equivalent to **38.2% less elapsed time** under that weighting.

The one-row-chunk case improves modestly and remains dominated by tiny-batch decode/dispatch overhead; the gain is not uniform across all operating points. Quote Test improved substantially after raw record reuse. Regular RSS is mixed: the Quote Test median increased, while the other four medians fell. Full ranges are retained in the compact JSON.

## Warm / uncontrolled OS-cache high load

One excluded warmup and three measured repetitions for each size/configuration: 24 calls, 18 measured. Four synthetic symbol/session partitions, five ranks, known LOBSTER-direction signing, 10-second buckets, identical source-quality gaps and 0.5-second RSS sampling.

| Original rows | Configuration | Before s (range; MAD) | After s (range; MAD) | Speedup | After original rows/s |
| ---: | --- | --- | --- | ---: | ---: |
| 1,000,000 | t1-c4096 | 2.656249 (2.617256–2.901492; 0.038993) | 1.450639 (1.334261–1.508349; 0.057710) | 1.831× | 689,351 |
| 1,000,000 | t4-c65536 | 2.550925 (2.537621–2.551368; 0.000443) | 1.104540 (1.102191–1.437089; 0.002349) | 2.309× | 905,355 |
| 10,000,000 | t1-c4096 | 26.396015 (26.260072–26.615133; 0.135943) | 13.070798 (12.745940–13.073701; 0.002903) | 2.019× | 765,064 |
| 10,000,000 | t4-c65536 | 25.988424 (25.626000–26.055584; 0.067160) | 10.995942 (10.919063–11.158119; 0.076880) | 2.363× | 909,426 |
| 20,000,000 | t1-c4096 | 53.152608 (52.906668–53.773805; 0.245940) | 25.889944 (25.551659–26.087094; 0.197150) | 2.053× | 772,501 |
| 20,000,000 | t4-c65536 | 51.378437 (50.765905–52.438237; 0.612533) | 22.864259 (22.698686–24.038166; 0.165573) | 2.247× | 874,728 |

Equal-case geometric speedup: **2.129×**.

| Original rows | Configuration | Before peak RSS MiB median (range) | After peak RSS MiB median (range) | Median change |
| ---: | --- | --- | --- | ---: |
| 1,000,000 | t1-c4096 | 121.92 (113.64–126.36) | 131.62 (119.53–142.08) | +8.0% |
| 1,000,000 | t4-c65536 | 269.62 (250.09–292.12) | 306.05 (286.58–367.83) | +13.5% |
| 10,000,000 | t1-c4096 | 117.48 (109.09–120.05) | 152.66 (139.50–170.97) | +29.9% |
| 10,000,000 | t4-c65536 | 242.86 (226.06–270.27) | 317.67 (301.58–609.48) | +30.8% |
| 20,000,000 | t1-c4096 | 109.34 (105.53–110.66) | 135.05 (127.95–138.38) | +23.5% |
| 20,000,000 | t4-c65536 | 258.88 (241.28–292.86) | 336.97 (266.17–559.91) | +30.2% |

Largest measured OS process peak: **292.86 → 609.48 MiB**.

## Verified zero-input-page-residency high load

One excluded warmup and three measured repetitions for each size/configuration: 24 calls, 18 measured. Four synthetic symbol/session partitions, five ranks, known LOBSTER-direction signing, 10-second buckets, identical source-quality gaps and 0.5-second RSS sampling.

| Original rows | Configuration | Before s (range; MAD) | After s (range; MAD) | Speedup | After original rows/s |
| ---: | --- | --- | --- | ---: | ---: |
| 1,000,000 | t1-c4096 | 2.677294 (2.632271–2.728508; 0.045022) | 1.267088 (1.253416–1.357789; 0.013672) | 2.113× | 789,211 |
| 1,000,000 | t4-c65536 | 2.574657 (2.542365–2.640948; 0.032292) | 1.179824 (1.130055–1.191598; 0.011774) | 2.182× | 847,584 |
| 10,000,000 | t1-c4096 | 26.680096 (26.444109–27.785564; 0.235987) | 12.545615 (12.535152–12.552892; 0.007277) | 2.127× | 797,091 |
| 10,000,000 | t4-c65536 | 25.990904 (25.017099–26.290288; 0.299383) | 11.195504 (11.134544–11.511821; 0.060960) | 2.322× | 893,216 |
| 20,000,000 | t1-c4096 | 52.696098 (52.541836–53.016113; 0.154263) | 24.249449 (23.303677–24.359530; 0.110082) | 2.173× | 824,761 |
| 20,000,000 | t4-c65536 | 51.591414 (50.983572–51.668233; 0.076818) | 23.822834 (23.446321–24.144662; 0.321828) | 2.166× | 839,531 |

Equal-case geometric speedup: **2.179×**.

| Original rows | Configuration | Before peak RSS MiB median (range) | After peak RSS MiB median (range) | Median change |
| ---: | --- | --- | --- | ---: |
| 1,000,000 | t1-c4096 | 133.22 (124.17–144.55) | 127.31 (117.88–128.00) | -4.4% |
| 1,000,000 | t4-c65536 | 234.83 (224.97–242.70) | 379.86 (288.33–480.83) | +61.8% |
| 10,000,000 | t1-c4096 | 113.19 (111.78–119.53) | 150.88 (142.34–154.00) | +33.3% |
| 10,000,000 | t4-c65536 | 251.59 (248.06–364.94) | 299.81 (295.16–305.77) | +19.2% |
| 20,000,000 | t1-c4096 | 109.80 (108.69–126.64) | 141.25 (131.27–159.77) | +28.6% |
| 20,000,000 | t4-c65536 | 249.94 (233.89–336.25) | 375.95 (311.44–615.14) | +50.4% |

Largest measured OS process peak: **364.94 → 615.14 MiB**.

`t1-c4096` and `t4-c65536` change both the thread cap and chunk size; these tables cannot isolate thread scaling. One worker was observed in t1 and a maximum of two in t4 despite a cap of four. N counts original quality rows, not the sum of all physical input tables: the 20M case additionally has 19,999,804 accepted event rows and 800,000 execution rows. These authored stress-test states are not real market observations or repeated copies of a delivered day.

Cold means all input pages were independently observed nonresident in every fresh child **before worker setup**, after targeted read-only file-range invalidation. Each full cold suite has 72 child observations and 72 parent post-preparation observations; all were zero. Physical-device/controller/filesystem lower caches are unverified. Timed source hashing can warm inputs before decoding, and the OS can change residency after observation. No global purge, privileged cache operation or cache-thrashing allocation was used. Warm-versus-cold differences cannot isolate storage cost; wrapper preflight also contributes to whole-process peak RSS.

RSS is the OS process high-water mark; samples every 0.5 seconds supplement it but can miss spikes. Worker overlap, allocator retention and OS accounting can produce variable peaks. The 609.48 MiB warm observation was retained in the report, not removed as an outlier. Its cause was not established. Private allocation reuse is not evidence of an overall RSS reduction.

## Candidate selection and rejected experiments

| Stage | Regular balanced speedup vs this task baseline | Decision |
| --- | ---: | --- |
| Canonical indices (`indexed-highload-20261014`) | 1.194× | Retained; improves direction/fixture cases, Quote Test median initially 1.5% worse. |
| Owned key/book reuse (`copy-highload-20261014`) | 1.345× | Retained after compatible outputs and warm/cold 1M pilots. |
| Raw buffers + reader lifetime (`io-highload-20261014`) | 1.619× | Retained; strongest measured balanced regular result among accepted implementations. |
| Compact worker payload (`payload-highload-20261014`) | 1.560× | Rejected: balanced regular 0.963× vs retained I/O, one-row-chunk 0.935× and Quote Test 0.861×, despite smaller private inline payload. |
| Release consumed Arrow batch before replacement (`batch-highload-20261014`) | 1.626× | Rejected: negligible balanced regular benefit, cold 1M t4 0.940× vs retained I/O with separated time ranges; RSS mixed. |

Compact payload reduced the private inline row from 408 to 312 bytes, but whole-process performance did not justify retaining it. Early Arrow release attempted to reduce old/new batch overlap; this did not establish the cause of the larger warm RSS peak. Both complete tested patches remain ignored under `outputs/features/performance-experiments/`, source was restored, native/source hashes returned to the accepted version, and no rejected implementation commit was kept. Candidate 1M pilots used explicit references filtered from the original full baselines and are preliminary evidence, not full 10M/20M claims. Full per-stage tables, every unfavorable result and checks remain in `CHANGELOG.md` and ignored result roots.

## Final compatibility and acceptance

Final acceptance passed on local main at 8e2b70b, with production change 2b53b01 retained. Rust formatting, Clippy with warnings denied, 42 Rust workspace tests, the explicitly enabled real-sample ingestion test, and the same 42 workspace tests on Rust 1.90.0 passed. The standard workspace and MSRV commands each leave only the externally supplied sample test ignored; that test passed separately with the delivered sample. All 114 Python API, native integration, research, real-sample and benchmark tests passed without skips. Ruff, strict mypy over seven source files, `git diff --check`, locked offline release-wheel construction and a fresh isolated wheel installation outside the checkout passed. The isolated smoke exercised native Parquet I/O, typed error mapping, package typing files, CLI and installed research helpers.

At 1, 5, 10, 30 and 60 seconds, accepted row counts were respectively 45,966, 8,985, 4,390, 1,382 and 650. Keys, all nine integer columns, average depth and quality flags matched exactly. Maximum absolute price-change errors across all widths were 2.1827852025868566e-13 dollars and 2.1827872842550278e-11 ticks, below tolerances 1e-10 and 1e-8; average-depth error was zero against tolerance 1e-10.

All 24 delivery hashes, both raw ZIP archive hashes and sizes, paired raw CSV counts of 301,587 AAPL and 595,800 MSFT rows, and the delivered 887,810 clean-event/68,404 trade/897,387 quality-row counts were verified.

The installed compiled native extension remained a4bbe9c69622920b9e6f589ea73ff66f0ac8f497cb5993f54789eeba15507d35 before and after acceptance; all 39 source hashes remained identical to the regular, full warm and cold evidence. The wheel build did not replace the installed extension. The tracked working tree remained clean, and this validation created only ignored evidence files. No implementation commits were pushed.

The first isolated-wheel attempt failed because the sandbox could not reach the package index; the unchanged helper passed after network escalation.

An independent fresh-context read-only review of `a662211..8e2b70b` found no actionable correctness, API, error-order, ownership or MSRV regressions. Review was separate from executed tests.

All 30 retained regular outputs matched their reference exactly. The final root audit independently checked **48 warm/cold calls and 96 Parquet tables** for exact ordered values, all dtypes/schema metadata, exact manifest JSON and stable full QC. Only output paths, elapsed time and observed peak workers were excluded from QC equality. All native/harness/source/input identity and conservation guards passed. The final installed binary/source closure still matched both full measured suites.

Checks ran on the local macOS machine. No new hosted Windows/Linux CI result is claimed. Public packaging/Windows support configuration was preserved.

## Provenance, artifacts and reproduction

Retained production closure: `2b53b01`; full warm snapshot at log-only `b8ff8f6`, full cold at log-only `8e2b70b`. The regular I/O measurements were taken before the two I/O implementation commits with those reviewed changes present; all 39 recorded source hashes match the final retained closure. The compact JSON records before/after snapshots instead of relying only on commit labels.

Native SHA-256: `a4bbe9c69622920b9e6f589ea73ff66f0ac8f497cb5993f54789eeba15507d35`.

Frozen cold-helper SHA-256: `9bf1590d6c6839eae1248d6a4981d36a7c3de869480a165a74a15db458ae31ee`.

Original cold summary SHA-256: `597a04f7d7c69cf832a6a636a54ea3bd132be30ec964d84ded24b6ea187a8f55`.

Full local result roots remain ignored: `benchmarks/results/optimization/{highload-before,indexed-highload,copy-highload,io-highload,payload-highload,batch-highload}-20261014`, plus the named warm/cold roots in the compact JSON. They contain all per-run commands, measurements, RSS traces, identities, verification and candidate equivalence evidence. Generated inputs/native features and rejected patches stay out of Git. Final check logs and an English static comparison chart are under ignored `outputs/features/performance-experiments/`.

Recorded full final suite commands (use a new output root when repeating):

```sh
.venv/bin/python -m benchmarks.high_load \
  --root benchmarks/results/high-load/optimized-20261014 \
  --reuse-fixtures --offline --compare-to docs/high_load/results.json
.venv/bin/python -m scripts.benchmark_cold \
  --root benchmarks/results/high-load/optimized-cold-20261014 \
  --normal-reference benchmarks/results/high-load/optimized-20261014/summary.json \
  --compare-to benchmarks/results/high-load/cold-input-baseline-20261014/summary.json
```

Instrumentation/evidence local commits: `a910217`, `f9fa511`; retained implementation commits: `0516002`, `3810fad`, `75a619d`, `2b53b01`; rejected-candidate evidence/restoration commits: `b8ff8f6`, `8e2b70b`. The final report is committed separately. No push, PR, release/package upload, deployment, remote change or history rewrite was performed. The owner reviews and pushes the local commits.
