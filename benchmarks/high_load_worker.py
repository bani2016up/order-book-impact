"""Fresh-process native measurement; no NumPy, pandas or PyArrow imports."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import resource
import time

from ofi_pipeline import InputPaths, PipelineConfig, RawInput, run_pipeline
from ofi_pipeline import _native
from benchmarks.high_load_rss import RSSSampler


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str) + "\n")
    temporary.replace(path)


def native_identity():
    path = Path(_native.__file__)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "sha256": digest.hexdigest(), "version": _native.version()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--phase", type=Path, required=True)
    parser.add_argument("--rss", type=Path, required=True)
    parser.add_argument("--sample-interval", type=float, required=True)
    parser.add_argument("--threads", type=int, required=True)
    parser.add_argument("--chunk-rows", type=int, required=True)
    parser.add_argument("--bucket-seconds", type=int, default=10)
    parser.add_argument("--signing", choices=["lobster_direction", "quote_test"], required=True)
    args = parser.parse_args()
    fixture = json.loads((args.fixture / "fixture.json").read_text())
    raw = tuple(RawInput(item["symbol"], item["date"],
                         message=args.fixture / item["message"],
                         orderbook=args.fixture / item["orderbook"])
                for item in fixture["raw_inputs"]) if args.signing == "quote_test" else ()
    inputs = InputPaths(
        *(args.fixture / fixture["inputs"][kind]["path"]
          for kind in ("events", "trades", "quality")), raw=raw,
    )
    config = PipelineConfig(
        threads=args.threads, chunk_rows=args.chunk_rows, trade_signing=args.signing,
        bucket_seconds=args.bucket_seconds, levels=5, session_close=fixture["session_close"],
    )
    native = native_identity()
    start = time.perf_counter()
    write_json(args.phase, {"phase": "running", "native_started_monotonic": start})
    # A fixed-interval self RSS thread runs while Rust detaches from Python.
    # Its small instrumentation cost is included, identically for every case.
    with RSSSampler(args.rss, args.sample_interval) as sampler:
        before = resource.getrusage(resource.RUSAGE_SELF)
        start = time.perf_counter()
        sampler.phase = ("running", start)
        try:
            report = run_pipeline(output_dir=args.output, inputs=inputs, config=config)
        except Exception as error:
            write_json(args.result, {"status": "failed", "error": repr(error), "native": native})
            write_json(args.phase, {"phase": "failed"})
            raise
        elapsed = time.perf_counter() - start
        after = resource.getrusage(resource.RUSAGE_SELF)
    peak = after.ru_maxrss * (1 if platform.system() == "Darwin" else 1024)
    rows = sum(p.original_rows for p in report.partitions)
    value = {
        "status": "ok", "wall_seconds": elapsed, "native_seconds": report.elapsed_seconds,
        "cpu_seconds": after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
        "major_page_faults": after.ru_majflt - before.ru_majflt,
        "minor_page_faults": after.ru_minflt - before.ru_minflt,
        "peak_process_rss_bytes": peak, "original_rows": rows,
        "original_events_per_second": rows / elapsed, "accepted_rows": report.feature_rows,
        "peak_partition_workers": report.peak_partition_workers,
        "config": asdict(config), "partitions": [asdict(p) for p in report.partitions],
        "native": native, "python": platform.python_version(),
        "sampled_rss_peak_bytes": sampler.peak, "rss_sample_count": sampler.count,
        "snapshot_method": sampler.method, "sample_interval_seconds": args.sample_interval,
        "rss_scope": "OS high-water RSS up to native-call completion, including imports and "
                     "the fixed-interval self RSS sampling thread",
        "timing_scope": "Public native-backed run_pipeline call: source hashing, input decoding, "
                        "computation, temporary partition assembly and final publication. "
                        "Build, fixture generation, verification and parent startup excluded.",
    }
    write_json(args.result, value)
    write_json(args.phase, {"phase": "finished", "wall_seconds": elapsed})


if __name__ == "__main__":
    main()
