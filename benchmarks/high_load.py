"""Serial, reproducible 1M/10M/20M load suite for the compiled Rust feature engine."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CASES = {"t1-c4096": (1, 4096), "t4-c65536": (4, 65536), "t4-c4096": (4, 4096)}
SIGNINGS = ("lobster_direction", "quote_test")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def snapshot():
    files = [ROOT / name for name in
             ("Cargo.toml", "Cargo.lock", "pyproject.toml", "uv.lock", ".python-version")]
    for folder, suffix in (("crates", "*.rs"), ("python/ofi_pipeline", "*.py"),
                           ("benchmarks", "*.py")):
        files.extend((ROOT / folder).rglob(suffix))
    files.extend((ROOT / "crates").rglob("Cargo.toml"))
    hashes = {str(p.relative_to(ROOT)): sha256(p) for p in sorted(set(files)) if p.is_file()}
    from ofi_pipeline import _native
    return {
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                               cwd=ROOT, text=True).strip(),
        "git_status": subprocess.check_output(["git", "status", "--porcelain"],
                                               cwd=ROOT, text=True).splitlines(),
        "source_hashes": hashes, "native_path": _native.__file__,
        "native_sha256": sha256(_native.__file__), "native_version": _native.version(),
        "platform": platform.platform(), "machine": platform.machine(),
        "host_id": hashlib.sha256(platform.node().encode()).hexdigest(),
        "python": platform.python_version(), "cpu_count": os.cpu_count(),
        "host_load_average": list(os.getloadavg()),
    }


def verify_fixture(path, expected_spec):
    metadata = json.loads((path / "fixture.json").read_text())
    if metadata.get("kind") != "authored-synthetic-high-load-fixture":
        raise ValueError("Expected an explicitly authored high-load fixture")
    if metadata.get("generator_version") != 1 or metadata["spec"] != expected_spec:
        raise ValueError("Fixture generator version/settings do not match; use a new directory")
    for item in [*metadata["inputs"].values(), *metadata["raw_sources"]]:
        source = path / item["path"]
        if source.stat().st_size != item["size_bytes"] or sha256(source) != item["sha256"]:
            raise ValueError(f"Fixture source identity changed: {source}")
    return metadata


def verify_output(output, result, fixture):
    """Outside the measured process: conservation and canonical decoded fingerprints."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    expected = fixture["expected_partitions"]
    if len(result["partitions"]) != len(expected):
        raise ValueError("Partition count changed")
    signing = result["config"]["trade_signing"]
    for actual, exp in zip(result["partitions"], expected):
        for field in ("symbol", "date", "original_rows", "clean_events", "rejected_events"):
            if actual[field] != exp[field]:
                raise ValueError(f"Partition evidence mismatch: {field}")
        totals = actual["signing"]
        if totals["trade_count"] != exp["trade_count"] or totals["volume"] != exp["volume"]:
            raise ValueError("Trade count/volume conservation failed")
        classified = exp["trade_count"] if signing == "lobster_direction" else (
            exp["quote_classified_count"])
        volume = exp["volume"] if signing == "lobster_direction" else (
            exp["quote_classified_volume"])
        ti = exp["known_trade_imbalance"] if signing == "lobster_direction" else (
            exp["quote_classified_imbalance"])
        if (totals["classified_count"], totals["classified_volume"],
            totals["trade_imbalance"]) != (classified, volume, ti):
            raise ValueError("Signing totals changed")
        if (totals["unclassified_count"], totals["unclassified_volume"]) != (
            exp["trade_count"] - classified, exp["volume"] - volume):
            raise ValueError("Unknown trade conservation failed")
    fingerprints = {}
    for name in ("features.parquet", "bucket_quality.parquet"):
        digest, last, row_count = hashlib.sha256(), None, 0
        sums = {"event_count": 0, "volume": 0, "trade_count": 0, "accepted": 0}
        source = pq.ParquetFile(output / name)
        for field in ("timestamp", "interval_start"):
            if source.schema_arrow.field(field).type != pa.timestamp("ns", tz="UTC"):
                raise ValueError("Output UTC nanosecond schema changed")
        for rank in range(1, 6):
            if f"ofi_l{rank}" not in source.schema_arrow.names:
                raise ValueError("Five-level output is missing")
        batches = source.iter_batches(batch_size=4096) if source.metadata.num_rows else ()
        for batch in batches:
            for field in ("timestamp", "interval_start"):
                batch = batch.set_column(
                    batch.schema.get_field_index(field), field, batch[field].cast(pa.int64())
                )
            for row in batch.to_pylist():
                key = (row["symbol"], row["date"], row["timestamp"])
                if last is not None and key <= last:
                    raise ValueError("Duplicate/unordered output key")
                last = key
                if name == "features.parquet" and not row["accepted"]:
                    raise ValueError("Feature file contains an excluded interval")
                for field in sums:
                    sums[field] += row[field]
                digest.update(json.dumps(row, sort_keys=True, allow_nan=False,
                                         separators=(",", ":")).encode() + b"\n")
                row_count += 1
        fingerprints[name] = {"decoded_sha256": digest.hexdigest(), "rows": row_count,
                              "totals": sums}
    all_buckets = fingerprints["bucket_quality.parquet"]
    totals = all_buckets["totals"]
    wanted = {field: sum(p[field if field != "event_count" else "original_rows"]
                         for p in expected) for field in ("event_count", "volume", "trade_count")}
    if any(totals[field] != value for field, value in wanted.items()):
        raise ValueError("Full-grid event/trade/volume conservation failed")
    total_grid = len(expected) * fixture["spec"]["session_seconds"] // (
        result["config"]["bucket_seconds"])
    if all_buckets["rows"] != total_grid:
        raise ValueError("Full session grid is incomplete")
    if fingerprints["features.parquet"]["rows"] != totals["accepted"] or (
        totals["accepted"] != result["accepted_rows"]):
        raise ValueError("Accepted feature and quality counts disagree")
    manifest = json.loads((output / "manifest.json").read_text())
    for kind, identity in fixture["inputs"].items():
        if manifest["dataset_identity"][kind]["sha256"] != identity["sha256"]:
            raise ValueError("Native manifest source hash differs from fixture identity")
    if signing == "quote_test":
        if [item["sha256"] for item in manifest["raw_sources"]] != [
            item["sha256"] for item in fixture["raw_sources"]
        ]:
            raise ValueError("Raw source hashes changed")
    return fingerprints


def measure(command, run_dir, output, fixture, before, interval, timeout):
    result_path, phase_path = run_dir / "measurement.json", run_dir / "phase.json"
    command += ["--output", str(output), "--result", str(result_path),
                "--phase", str(phase_path), "--rss", str(run_dir / "rss.jsonl"),
                "--sample-interval", str(interval)]
    write_json(run_dir / "command.json", command)
    start = time.perf_counter()
    with (run_dir / "stdout.log").open("w") as stdout, (
        run_dir / "stderr.log").open("w") as stderr:
        child = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr)
        try:
            while child.poll() is None:
                stamp = time.perf_counter()
                if stamp - start > timeout:
                    raise TimeoutError(f"Native child exceeded {timeout}s")
                time.sleep(interval)
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
    if child.returncode != 0:
        raise RuntimeError(f"Native child exited {child.returncode}; inspect {run_dir}/stderr.log")
    result = json.loads(result_path.read_text())
    if result["status"] != "ok" or result["native"]["sha256"] != before["native_sha256"]:
        raise ValueError("Native measurement failed or loaded extension changed")
    result["verification"] = verify_output(output, result, fixture)
    result.update({"output_dir": str(output), "artifact_dir": str(run_dir)})
    if result["rss_sample_count"] == 0:
        raise RuntimeError("No RSS snapshots could be captured")
    write_json(run_dir / "verified.json", result)
    return result


def aggregate(runs):
    groups = {}
    for row in runs:
        if row["warmup"]:
            continue
        groups.setdefault(row["case_id"], []).append(row)
    result = []
    for name, rows in groups.items():
        wall = [r["wall_seconds"] for r in rows]
        rss = [r["peak_process_rss_bytes"] for r in rows]
        median = statistics.median(wall)
        result.append({
            "case_id": name, "original_rows": rows[0]["original_rows"], "repetitions": len(rows),
            "signing": rows[0]["config"]["trade_signing"],
            "threads": rows[0]["config"]["threads"], "chunk_rows": rows[0]["config"]["chunk_rows"],
            "wall_seconds_median": median, "wall_seconds_min": min(wall),
            "wall_seconds_max": max(wall),
            "wall_seconds_mad": statistics.median(abs(x - median) for x in wall),
            "rows_per_second": rows[0]["original_rows"] / median,
            "peak_rss_mib_median": statistics.median(rss) / 1024**2,
            "peak_rss_mib_min": min(rss) / 1024**2, "peak_rss_mib_max": max(rss) / 1024**2,
            "peak_workers": max(r["peak_partition_workers"] for r in rows),
            "verification": rows[0]["verification"],
        })
    return result


def compare_baseline(summary, path):
    baseline = json.loads(path.read_text())
    for field in ("platform", "machine", "python", "cpu_count", "host_id"):
        if baseline["source_before"][field] != summary["source_before"][field]:
            raise ValueError(f"Baseline host/runtime differs: {field}")
    def tool_hashes(document):
        return {key: value for key, value in document["source_before"]["source_hashes"].items()
                if key.startswith("benchmarks/") or key in {"uv.lock", ".python-version"}}
    if tool_hashes(baseline) != tool_hashes(summary) or baseline["build"]["profile"] != (
        summary["build"]["profile"]):
        raise ValueError("Baseline harness hashes or build-profile provenance differ")
    if baseline["status"] != "complete" or baseline["protocol"] != summary["protocol"]:
        raise ValueError("Baseline is incomplete or benchmark protocols differ")
    if baseline["fixtures"] != summary["fixtures"]:
        raise ValueError("Baseline fixture specifications/hashes differ")
    old = {item["case_id"]: item for item in baseline["aggregates"]}
    new = {item["case_id"]: item for item in summary["aggregates"]}
    if old.keys() != new.keys():
        raise ValueError("Baseline case sets differ")
    changes = []
    for name, item in new.items():
        prior = old[name]
        if item["verification"] != prior["verification"]:
            raise ValueError(f"Decoded output/conservation differs from baseline: {name}")
        changes.append({"case_id": name, "speedup": prior["wall_seconds_median"] /
                        item["wall_seconds_median"],
                        "median_rss_ratio": item["peak_rss_mib_median"] /
                        prior["peak_rss_mib_median"]})
    return {"baseline": str(path), "cases": changes,
            "equal_case_geometric_speedup": math.exp(statistics.mean(
                math.log(item["speedup"]) for item in changes))}


def reports(root, summary):
    write_json(root / "summary.json", summary)
    fields = [key for key in summary["aggregates"][0] if key != "verification"]
    with (root / "summary.csv").open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in summary["aggregates"])
    text = "# Synthetic high-load measurements\n\n"
    text += "Authored workload, not market-data performance. OS cache is uncontrolled.\n"
    text += "Build, generation, startup and verification are excluded from native call timing.\n\n"
    text += "| Case | Runs | Median s (min–max) | Rows/s | Peak MiB median (min–max) |\n"
    text += "| --- | ---: | --- | ---: | --- |\n"
    for row in summary["aggregates"]:
        text += (f"| {row['case_id']} | {row['repetitions']} | "
                 f"{row['wall_seconds_median']:.3f} "
                 f"({row['wall_seconds_min']:.3f}–{row['wall_seconds_max']:.3f}) | "
                 f"{row['rows_per_second']:,.0f} | {row['peak_rss_mib_median']:.2f} "
                 f"({row['peak_rss_mib_min']:.2f}–{row['peak_rss_mib_max']:.2f}) |\n")
    text += "\nFull provenance/protocol is in summary.json. Each run retains measurement.json,\n"
    text += "verified.json, command.json, phase.json, rss.jsonl and stdout/stderr logs.\n"
    text += "Peak RSS uses OS high-water accounting; snapshots are sampled and may miss spikes.\n"
    text += "Only total original quality rows define the advertised workload size.\n"
    (root / "report.md").write_text(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--fixture-root", type=Path, default=ROOT / "data/high_load")
    parser.add_argument("--sizes", type=int, nargs="+", default=[1000000, 10000000, 20000000])
    parser.add_argument("--partitions", type=int, default=4)
    parser.add_argument("--cases", choices=list(CASES), nargs="+", default=["t1-c4096", "t4-c65536"])
    parser.add_argument("--signings", choices=SIGNINGS, nargs="+", default=["lobster_direction"])
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--sample-interval", type=float, default=0.5)
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--batch-rows", type=int, default=65536)
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--trade-every", type=int, default=25)
    parser.add_argument("--reject-every", type=int, default=100003)
    parser.add_argument("--session-seconds", type=int, default=23400)
    parser.add_argument("--bucket-seconds", type=int, choices=[1, 5, 10, 30, 60], default=10)
    parser.add_argument("--reuse-fixtures", action="store_true")
    parser.add_argument("--no-build", action="store_true",
                        help="Use installed extension; its release/debug profile is unverified")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--compare-to", type=Path)
    args = parser.parse_args(argv)
    if platform.system() not in ("Darwin", "Linux"):
        parser.error("Load RSS instrumentation currently supports macOS/Linux, like benchmarks/run.py")
    if args.repetitions < 1 or args.warmups < 0 or not 0.05 <= args.sample_interval <= 10:
        parser.error("Need repetitions >=1, warmups >=0 and sample interval 0.05..10 seconds")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("Timeout must be finite and positive")
    if len(set(args.sizes)) != len(args.sizes) or len(set(args.cases)) != len(args.cases) or (
        len(set(args.signings)) != len(args.signings)):
        parser.error("Duplicate sizes/cases/signings are not allowed")
    root = (args.root or ROOT / "benchmarks/results/high-load" /
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")).absolute()
    if root.exists():
        parser.error("Result root already exists; use a new root (no destructive reruns)")
    root.mkdir(parents=True)
    output_root = ROOT / "outputs/features/high-load" / (
        root.name + "-" + hashlib.sha256(str(root).encode()).hexdigest()[:12])
    summary = {
        "schema_version": 1, "status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": {"sizes": args.sizes, "partitions": args.partitions, "cases": args.cases,
                     "signings": args.signings, "repetitions": args.repetitions,
                     "warmups": args.warmups, "bucket_seconds": args.bucket_seconds,
                     "sample_interval_seconds": args.sample_interval,
                     "cache": "Uncontrolled OS cache; fixture generation/identity checks warm inputs; "
                              "one serial warmup per case by default; not cold-cache measurements"},
        "fixtures": {}, "runs": [], "output_root": str(output_root),
    }
    write_json(root / "summary.json", summary)
    try:
        if not args.no_build:
            command = [sys.executable, "-m", "maturin", "develop", "--release", "--locked", "--uv"]
            if args.offline:
                command.append("--offline")
            environment = {**os.environ, "PYO3_PYTHON": sys.executable}
            if sys.prefix != sys.base_prefix:
                environment["VIRTUAL_ENV"] = sys.prefix
            with (root / "build.log").open("w") as log:
                subprocess.run(command, cwd=ROOT, env=environment, stdout=log,
                               stderr=subprocess.STDOUT, check=True)
            summary["build"] = {"profile": "release", "command": command, "log": str(root / "build.log")}
        else:
            summary["build"] = {"profile": "unverified-installed-extension", "command": None}
        before = snapshot()
        summary["source_before"] = before
        for size in args.sizes:
            spec = {"total_rows": size, "partitions": args.partitions, "batch_rows": args.batch_rows,
                    "seed": args.seed, "trade_every": args.trade_every,
                    "reject_every": args.reject_every, "session_seconds": args.session_seconds,
                    "with_raw": "quote_test" in args.signings}
            fixture = args.fixture_root.absolute() / f"n{size}-p{args.partitions}-s{args.seed}"
            if fixture.exists() and not args.reuse_fixtures:
                raise FileExistsError(f"{fixture} exists; --reuse-fixtures checks its identity")
            if not fixture.exists():
                print(f"n{size}: generating bounded authored fixture", flush=True)
                command = [sys.executable, "-m", "benchmarks.high_load_fixture", str(fixture)]
                for key, value in spec.items():
                    if key != "with_raw":
                        command += ["--" + key.replace("_", "-"), str(value)]
                if spec["with_raw"]:
                    command.append("--with-raw")
                with (root / f"generate-{size}.log").open("w") as log:
                    subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
            metadata = verify_fixture(fixture, spec)
            summary["fixtures"][str(size)] = {
                key: metadata[key] for key in ("kind", "generator_version", "spec", "inputs",
                                               "raw_sources", "expected_partitions")}
            for signing in args.signings:
                for case in args.cases:
                    threads, chunk = CASES[case]
                    case_id = f"n{size}-{signing}-{case}"
                    reference = None
                    for index in range(args.warmups + args.repetitions):
                        warmup = index < args.warmups
                        name = f"{case_id}-{'warmup' if warmup else 'run'}-" + (
                            str(index + 1) if warmup else str(index - args.warmups + 1))
                        run_dir = root / name
                        run_dir.mkdir()
                        output = output_root / name
                        if output.exists():
                            raise FileExistsError(output)
                        print(f"{name}: starting fresh native process", flush=True)
                        command = [sys.executable, "-m", "benchmarks.high_load_worker",
                                   "--fixture", str(fixture), "--threads", str(threads),
                                   "--chunk-rows", str(chunk), "--bucket-seconds",
                                   str(args.bucket_seconds), "--signing", signing]
                        result = measure(command, run_dir, output, metadata, before,
                                         args.sample_interval, args.timeout)
                        if result["peak_partition_workers"] > threads:
                            raise ValueError("Configured worker bound exceeded")
                        key = f"{size}-{signing}"
                        reference = next((r["verification"] for r in summary["runs"]
                                          if r["comparison_key"] == key), reference)
                        if reference is not None and reference != result["verification"]:
                            raise ValueError("Decoded results differ across repeats/chunk/thread cases")
                        result.update({"case_id": case_id, "comparison_key": key, "warmup": warmup})
                        summary["runs"].append(result)
                        write_json(root / "summary.json", summary)
                        print(f"{name}: {result['wall_seconds']:.3f}s; "
                              f"{result['peak_process_rss_bytes']/1024**2:.2f} MiB peak; "
                              "decoded output verified", flush=True)
        after = snapshot()
        summary["source_after"] = after
        if before["source_hashes"] != after["source_hashes"] or (
            before["native_sha256"] != after["native_sha256"]):
            raise ValueError("Source or loaded extension changed during the benchmark")
        summary["aggregates"] = aggregate(summary["runs"])
        summary["status"] = "complete"
        summary["finished_utc"] = datetime.now(timezone.utc).isoformat()
        summary["disk_free_bytes_at_finish"] = shutil.disk_usage(root).free
        if args.compare_to:
            summary["comparison"] = compare_baseline(summary, args.compare_to)
        reports(root, summary)
    except BaseException as error:
        summary.update({"status": "failed", "error": repr(error)})
        write_json(root / "summary.json", summary)
        raise
    print(f"Completed: {root / 'report.md'}", flush=True)


if __name__ == "__main__":
    main()
