"""Installed CLI calls the same compiled file-level API."""

import argparse
from dataclasses import asdict
import json
from typing import Sequence

from .api import InputPaths, PipelineConfig, run_pipeline
from .errors import PipelineError


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute LOBSTER rank OFI with Rust")
    parser.add_argument("--sample-dir")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--events")
    parser.add_argument("--trades")
    parser.add_argument("--quality")
    parser.add_argument("--bucket-seconds", type=int, default=10)
    parser.add_argument("--levels", type=int, default=5)
    parser.add_argument("--chunk-rows", type=int, default=65536)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--max-partitions", type=int, default=1024)
    parser.add_argument(
        "--trade-signing", choices=["lobster_direction", "quote_test"], default="lobster_direction"
    )
    parser.add_argument("--session-date")
    parser.add_argument("--session-open", default="09:30:00")
    parser.add_argument("--session-close", default="16:00:00")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    explicit = (args.events, args.trades, args.quality)
    if any(explicit) and not all(explicit):
        parser.error("--events, --trades and --quality must be supplied together")
    try:
        config = PipelineConfig(
            bucket_seconds=args.bucket_seconds,
            levels=args.levels,
            chunk_rows=args.chunk_rows,
            threads=args.threads,
            max_partitions=args.max_partitions,
            trade_signing=args.trade_signing,
            session_date=args.session_date,
            session_open=args.session_open,
            session_close=args.session_close,
            overwrite=args.overwrite,
        )
        report = run_pipeline(
            args.sample_dir,
            args.output_dir,
            config,
            inputs=InputPaths(*explicit) if all(explicit) else None,
        )
    except PipelineError as error:
        parser.exit(2, f"ofi-pipeline: {error}\n")
    print(json.dumps(asdict(report), default=str, sort_keys=True))
    return 0
