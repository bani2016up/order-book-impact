"""Release native benchmark; run each configuration in a fresh process."""

import argparse
from dataclasses import asdict
import json
import platform
import resource
import time

from ofi_pipeline import PipelineConfig, run_pipeline

parser = argparse.ArgumentParser()
parser.add_argument("--sample-dir", required=True)
parser.add_argument("--output-dir", required=True)
parser.add_argument("--threads", type=int, default=1)
parser.add_argument("--chunk-rows", type=int, default=65536)
parser.add_argument(
    "--signing", choices=["lobster_direction", "quote_test"], default="lobster_direction"
)
parser.add_argument(
    "--label", required=True, help="real or authored-fixture label; never mislabel fixtures"
)
args = parser.parse_args()
start = time.perf_counter()
report = run_pipeline(
    args.sample_dir,
    args.output_dir,
    PipelineConfig(threads=args.threads, chunk_rows=args.chunk_rows, trade_signing=args.signing),
)
elapsed = time.perf_counter() - start
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if platform.system() != "Darwin":
    peak *= 1024
n = sum(p.original_rows for p in report.partitions)
print(
    json.dumps(
        {
            "label": args.label,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "wall_seconds": elapsed,
            "native_seconds": report.elapsed_seconds,
            "original_events_per_second": n / elapsed,
            "peak_process_rss_bytes": peak,
            "peak_partition_workers": report.peak_partition_workers,
            "original_rows": n,
            "accepted_rows": report.feature_rows,
            "config": asdict(report.config),
            "cache": "OS cache uncontrolled; same source files previously read; warm-cache leaning",
            "rss_scope": "whole fresh Python process; compiled native computation; no pandas/PyArrow imports",
            "input_format": "Parquet (ZSTD delivery)",
            "output_format": "Parquet ZSTD plus JSON",
            "timing_scope": "source hashing, computation, intermediate output assembly and atomic publication; excludes build/install",
        },
        indent=2,
    )
)
