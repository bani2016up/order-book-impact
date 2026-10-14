# Measured coverage and limitations

Measured on 2026-10-14 against the source SHA256 snapshot in
[coverage.json](coverage.json). Rust 1.90.0 and its matching LLVM tools instrumented
both unit executables and the actual PyO3 shared library. Python invoked that
library during 74 unit/compiled integration tests. The Rust suites passed 28 core
unit, 3 adapter integration and 2 pipeline integration tests. The external sample
ingestion test is separate from this self-contained coverage selection.

| Layer | Covered / measured production lines | Measured coverage |
| --- | --- | --- |
| Rust core | 1756 / 1764 | 99.5465% |
| PyO3 native binding | 42 / 42 | 100% |
| Python wrapper and CLI | 187 / 187, 30 / 30 branches | 100% |

Every authored production module is measured. Raw LLVM export/show and Python
JSON reports remain in ignored `target/coverage-report/`; the portable committed
summary retains all source hashes, per-file denominators and missed line numbers.
Only inline Rust `cfg(test)` bodies are removed from the production denominator.
No production error paths are excluded, and Python has zero excluded lines.
These are measured line counters, not a claim of complete branch/path correctness.

Eight Rust production lines remain uncovered; they are retained in the 99.5465%
denominator. Six guards cannot be reached through validated production inputs:

| Source location | Why no valid input can execute the error exit |
| --- | --- |
| `adapter.rs:77` | Private array accessor is called only from Parquet match arms; CSV has its own typed accessors. |
| `adapter.rs:153` | Required Parquet timestamp schema was already validated as `timestamp[ns, UTC]` when opening the reader. Wrong-schema inputs fail there first. |
| `buckets.rs:74` | Validated session endpoints fit int64, and duration is a positive multiple of width; first end is at or before close. |
| `buckets.rs:217` | Advancing occurs only before close on that aligned integer grid; the next end cannot exceed validated close. The int64-limit final-boundary regression exercises the enclosing behavior. |
| `output.rs:359`, `output.rs:369` | The private batch builder receives the writer's own schema and identically sized typed arrays for validated levels. `RecordBatch::try_new` cannot fail without an internal programming defect. |

Two OS-dependent failure sites were not fault-injected:

- `pipeline.rs:175`: operating-system failure to spawn a partition thread. A
  resource-exhaustion trigger is not portable or isolated on a shared host.
- `pipeline.rs:262`: final QC JSON write failure after earlier writes succeeded.
  A disk/device failure precisely at that site was not simulated.

Both propagate typed errors before publication. Other actual missing-file,
malformed I/O, output collision and publication errors are exercised. Publication
rename fault tests verify restoration of previous contents and retention of a
recoverable backup if restoration also fails. Worker dependency panics are
contained. These tests do not establish coverage of the two specific OS sites.

Reproduce with the commands in [testing.md](testing.md). The runner snapshots
production sources before/after measurement, obtains current executable objects
from Cargo JSON, merges runtime profiles and rejects missing core/native mappings.
Profiles from a Python-only coverage run would not measure the Rust library.
