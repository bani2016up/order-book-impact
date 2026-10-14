"""Compute reusable features once; model runs consume the saved Parquet dataset."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from ofi_pipeline import PipelineConfig, run_pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-dir", default="data/order_book_sample")
    parser.add_argument("--output-dir", default="outputs/features/10s")
    parser.add_argument("--bucket-seconds", type=int, default=10)
    parser.add_argument("--levels", type=int, default=5)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    report = run_pipeline(
        Path(args.sample_dir),
        Path(args.output_dir),
        PipelineConfig(
            bucket_seconds=args.bucket_seconds, levels=args.levels, threads=args.threads
        ),
    )
    print(json.dumps(asdict(report), default=str, indent=2))


if __name__ == "__main__":
    main()
