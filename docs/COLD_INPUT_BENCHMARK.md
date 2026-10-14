# Verified low-residency input benchmark

`scripts/benchmark_cold.py` adds a separate macOS protocol around the unchanged
`benchmarks.high_load_worker` and `benchmarks.high_load.measure` APIs. Existing
normal benchmark sources and baselines, including ignored Python files recursively
inside `benchmarks/results`, must remain byte-identical for paired comparisons.
Production interfaces, computations and input fixtures are unchanged.

## Cache-state claims

The measurement starts from **verified zero resident input pages before worker
setup**, observed independently with `mincore` in every fresh child. This is a
file-cache observation at a recorded instant. It is neither a physical-device
cold-cache measurement nor evidence that every later input read reaches storage.
The unchanged timed public call hashes its sources before decoding, which can
warm the input pages during that call. OS activity can also change residency
between the observation and the public call. Process startup, configuration,
native binary identity reads, cache preparation and parent verification remain
outside the timed call.

The protocol distinguishes these states explicitly:

| State | Evidence |
| --- | --- |
| Verified zero input-page residency | Every input's fresh-child `mincore` vector has zero `MINCORE_INCORE` bits. Required for a successful run. |
| Eviction requested | File-targeted `msync` succeeded. This alone is insufficient; a nonzero residency result rejects the run. |
| Fresh process | New Python child for every warmup/repetition. This alone is insufficient for any cache claim. |
| Physical-device cache | Unverified and uncontrolled, including storage-controller, filesystem and lower-layer caches. |

No global purge, privileged operations, unrelated-process manipulation, cache
deletion, or cache-thrashing allocation is used. `MAP_SHARED` is read-only and is
never touched; the residency vector consumes one byte per file page. Preparation
targets only immutable, SHA-256-verified authored fixture inputs. A writable
mapping is never created. `msync` can synchronize dirty pages, so these fixtures
must not have concurrent writers.

## Targeted preparation and independent verification

1. Verify source bytes/settings against the completed normal reference outside
   timing. Require the installed binary and all normal source hashes to match
   its release-build provenance and host/runtime.
2. Observe each input through an untouched read-only mapping and `mincore`.
3. Apply `msync(MS_SYNC | MS_INVALIDATE)` only to each input's mapping, then unmap.
4. Independently remap all inputs and require zero resident pages. Save before/
   after observations, file identities, page sizes and monotonic timestamps.
5. Start a fresh child; finish importing the unchanged worker, independently
   remap/query all inputs, save pre-read observations, process ID and helper SHA,
   and reject any nonzero input before invoking the unchanged worker `main`.
6. Run the unchanged native-call timing, RSS/page-fault instrumentation and
   parent output verification. Require decoded fingerprints to match the saved
   normal reference for every warmup and repetition.
7. Reverify each fixture after all of its cases, and source/binary/helper hashes
   at suite completion. Changed identities fail completion.

On this macOS host, an initial feasibility probe used the exact 1M-row events
Parquet (33,899,419 bytes; 2,070 pages of 16,384 bytes). In three cycles an ordinary
read produced 2,070 resident pages; file-targeted synchronous invalidation then
produced zero resident pages in independent new mappings. `F_NOCACHE` sequential
reads left all 2,070 already-cached pages resident, including after 0.1 seconds,
so that advice was not accepted as eviction evidence. These are feasibility
observations, not pipeline performance measurements.

Apple's primary sources define [mincore residency](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/mincore.2.html),
[msync's file-range invalidation](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/msync.2.html)
and [F_NOCACHE advice](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/fcntl.2.html).
The current public XNU source maps `MS_INVALIDATE` to `VM_SYNC_INVALIDATE` in
[kern_mman.c](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_mman.c)
and describes cached/direct read behavior in
[vfs_cluster.c](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/vfs/vfs_cluster.c).
Those sources explain the API; the independent local observation determines
whether the requested state was actually achieved on the installed host.

## Baseline and candidate commands

Only one benchmark owner runs measurements at a time. Do not compile, run
CPU-heavy tests/profiles, or read large datasets concurrently. Build before the
normal suite; the cold wrapper reuses that exact installed binary by checking
its hash and release provenance. A new root is required for every invocation.

```sh
.venv/bin/python -m scripts.benchmark_cold \
  --root benchmarks/results/high-load/cold-input-baseline-20261014 \
  --normal-reference benchmarks/results/high-load/baseline-20261014/summary.json
```

This inherits the normal reference's exact 1M/10M/20M original-row fixtures,
four partitions, five levels, known-direction signing, 10-second buckets,
`t1-c4096` and `t4-c65536`, 0.5-second RSS interval, one excluded warmup and three
measured repeats per case. Each excluded warmup is also prepared and gated;
every measured repetition independently repeats preparation. There are six
cases, 24 verified native calls and 18 measured calls. Original timings suggest
approximately eleven minutes plus preparation and verification.

After a candidate's normal suite completes with release-build provenance:

```sh
.venv/bin/python -m scripts.benchmark_cold \
  --root benchmarks/results/high-load/cold-input-candidate \
  --normal-reference benchmarks/results/high-load/candidate/summary.json \
  --compare-to benchmarks/results/high-load/cold-input-baseline-20261014/summary.json
```

Cold-to-cold comparison requires identical helper SHA, normal benchmark source
hashes, full protocol, fixtures, host/runtime, release profile and decoded output.
Do not edit the helper between the paired runs. Normal-to-cold timings describe
different starting cache protocols and cannot isolate physical-storage cost.
Neither this authored synthetic fixture nor these measurements replace the real
sample acceptance contract.

Full evidence remains ignored under `benchmarks/results/`; native output remains
ignored under `outputs/features/cold-input/`. Each run saves cache preparation,
independent child cache state, command, phase, measurement, RSS snapshots,
stdout/stderr and post-run verification. Failed gates or children cannot create
a successful complete report. Only code, tests, documentation and an explicitly
identified compact report belong in Git.

Focused checks:

```sh
.venv/bin/python -m pytest -q tests/benchmarks/test_cold_input.py
.venv/bin/ruff check scripts/benchmark_cold.py tests/benchmarks/test_cold_input.py
```


## Completed baseline — 2026-10-14

Full ignored evidence: `benchmarks/results/high-load/cold-input-baseline-20261014/`.
The exact baseline command above completed from 15:12:22 to 15:23:31 UTC
(669.3 seconds including preparation/verification). Six cases contain one
excluded warmup plus three measured fresh children each: 24 verified calls,
18 measured calls. All 72 independent child file observations and all 72 parent
post-preparation observations recorded zero resident pages. Every decoded output
fingerprint, conservation check and native manifest source hash matched the
normal reference. Fixture bytes were reverified after each size; engine and
normal benchmark source hashes (including ignored recursive Python files),
native binary hash and helper hash stayed identical throughout.

| Original rows | Configuration | Wall median s (min–max; MAD) | Peak process MiB median (min–max) |
| ---: | --- | --- | --- |
| 1,000,000 | t1-c4096 | 2.677294 (2.632271–2.728508; 0.045022) | 133.219 (124.172–144.547) |
| 1,000,000 | t4-c65536 | 2.574657 (2.542365–2.640948; 0.032292) | 234.828 (224.969–242.703) |
| 10,000,000 | t1-c4096 | 26.680096 (26.444109–27.785564; 0.235987) | 113.188 (111.781–119.531) |
| 10,000,000 | t4-c65536 | 25.990904 (25.017099–26.290288; 0.299383) | 251.594 (248.062–364.938) |
| 20,000,000 | t1-c4096 | 52.696098 (52.541836–53.016113; 0.154263) | 109.797 (108.688–126.641) |
| 20,000,000 | t4-c65536 | 51.591414 (50.983572–51.668233; 0.076818) | 249.938 (233.891–336.250) |

Input residency in every child, by size:

| Original rows | Events resident/pages | Trades resident/pages | Quality resident/pages |
| ---: | ---: | ---: | ---: |
| 1,000,000 | 0/2,070 | 0/57 | 0/1,227 |
| 10,000,000 | 0/20,439 | 0/549 | 0/12,003 |
| 20,000,000 | 0/40,724 | 0/1,091 | 0/23,851 |

The measured worker peaks remain within configured limits (one worker for t1,
two observed for t4 across four partitions). RSS ranges include sizable t4
outliers; this baseline does not establish a memory reduction. Cold-wrapper
imports and preflight state contribute to whole-process high-water RSS, so
normal-versus-cold RSS differences cannot be attributed solely to cache state.
Physical-device cache and the observation-to-call race remain unverified;
source hashing warms inputs inside the timed public call. These limitations
apply equally to every later paired cold-protocol candidate.

Frozen helper SHA-256:
`9bf1590d6c6839eae1248d6a4981d36a7c3de869480a165a74a15db458ae31ee`.
Native SHA-256:
`6cf58dacbb60d5408e0d125321c973aa2cb298fc8b7a9fce7b2a0e52ddb63691`.
Complete baseline summary SHA-256:
`597a04f7d7c69cf832a6a636a54ea3bd132be30ec964d84ded24b6ea187a8f55`.
Instrumentation commit: `a910217`.

Focused checks passed: eight cold-protocol tests, Ruff and diff whitespace checks.
An independent post-suite audit checked completion/counts, every zero-residency
observation, identical fixture/source/binary/helper identities, all six aggregate
fingerprints, and a real cold self-comparison through the existing normal harness
guards. The separate regular five-case baseline was completed and independently
verified by the supervising root before granting this exclusive measurement
slot. No concurrent builds, CPU-heavy checks or benchmarks ran during this suite.
No production optimization or real-sample reconciliation was performed in this
instrumentation subtask; final acceptance and full per-row QC/manifest auditing
remain part of the supervised optimization task.
