"""Load harness behavior using small fixtures and real compiled extension calls."""

import copy
from dataclasses import asdict
import json
from pathlib import Path
import platform
import subprocess
import sys

import pytest

from benchmarks.high_load import aggregate, compare_baseline, verify_fixture, verify_output
from benchmarks.high_load_fixture import FixtureSpec, generate
from ofi_pipeline import PipelineConfig, run_pipeline

ROOT = Path(__file__).resolve().parents[2]


def test_empty_accepted_features_remain_valid_verification_evidence(tmp_path):
    root = tmp_path / "fixture"
    fixture = generate(root, FixtureSpec(101, partitions=1, reject_every=7, session_seconds=60))
    report = run_pipeline(root, tmp_path / "out", PipelineConfig(session_close="09:31:00"))
    assert report.feature_rows == 0
    result = {"config": asdict(report.config), "accepted_rows": report.feature_rows,
              "partitions": [asdict(p) for p in report.partitions]}
    fingerprints = verify_output(tmp_path / "out", result, fixture)
    assert fingerprints["features.parquet"]["rows"] == 0
    assert fingerprints["bucket_quality.parquet"]["totals"]["event_count"] == 101


def test_reused_fixture_requires_matching_settings_and_hashes(tmp_path):
    root = tmp_path / "fixture"
    metadata = generate(root, FixtureSpec(20, session_seconds=60))
    verify_fixture(root, metadata["spec"])
    wrong = {**metadata["spec"], "seed": 123}
    with pytest.raises(ValueError, match="settings"):
        verify_fixture(root, wrong)
    source = root / metadata["inputs"]["quality"]["path"]
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="identity"):
        verify_fixture(root, metadata["spec"])


def test_warmups_are_excluded_and_baseline_requires_decoded_equivalence(tmp_path):
    def row(seconds, warmup):
        return {
            "case_id": "one", "warmup": warmup, "wall_seconds": seconds,
            "peak_process_rss_bytes": 10 * 1024**2,
            "original_rows": 100, "config": {"trade_signing": "lobster_direction",
                                           "threads": 1, "chunk_rows": 4096},
            "peak_partition_workers": 1, "verification": {"decoded": "same"},
        }
    result = aggregate([row(100, True), row(2, False), row(4, False)])
    assert result[0]["repetitions"] == 2 and result[0]["wall_seconds_median"] == 3
    assert result[0]["wall_seconds_mad"] == 1
    summary = {"status": "complete", "protocol": {"cases": ["one"]},
               "fixtures": {"100": "same input"}, "aggregates": result,
               "source_before": {"platform": "test", "machine": "test", "python": "test",
                                 "cpu_count": 1, "host_id": "test", "source_hashes": {}},
               "build": {"profile": "test"}}
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(summary))
    assert compare_baseline(summary, baseline)["equal_case_geometric_speedup"] == 1
    mutated = copy.deepcopy(summary)
    mutated["aggregates"][0]["verification"] = {"decoded": "changed"}
    with pytest.raises(ValueError, match="Decoded"):
        compare_baseline(mutated, baseline)
    mutated = copy.deepcopy(summary)
    mutated["fixtures"] = {"100": "different input"}
    with pytest.raises(ValueError, match="fixture"):
        compare_baseline(mutated, baseline)
    mutated = copy.deepcopy(summary)
    mutated["source_before"]["host_id"] = "another host"
    with pytest.raises(ValueError, match="host/runtime"):
        compare_baseline(mutated, baseline)
    for dependency in ("uv.lock", ".python-version"):
        mutated = copy.deepcopy(summary)
        mutated["source_before"]["source_hashes"][dependency] = "changed"
        with pytest.raises(ValueError, match="harness hashes"):
            compare_baseline(mutated, baseline)


@pytest.mark.skipif(platform.system() not in ("Darwin", "Linux"), reason="POSIX load instrumentation")
def test_fresh_native_suite_records_snapshots_and_checks_all_outputs(tmp_path):
    root = tmp_path / "run"
    command = [
        sys.executable, "-m", "benchmarks.high_load", "--root", str(root),
        "--fixture-root", str(tmp_path / "fixtures"), "--sizes", "303",
        "--partitions", "3", "--session-seconds", "60", "--trade-every", "3",
        "--reject-every", "41", "--batch-rows", "13", "--cases", "t1-c4096", "t4-c65536",
        "--signings", "lobster_direction", "quote_test",
        "--warmups", "1", "--repetitions", "2", "--sample-interval", "0.05",
        "--timeout", "30", "--no-build",
    ]
    child = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
    assert child.returncode == 0, child.stdout + child.stderr
    summary = json.loads((root / "summary.json").read_text())
    assert summary["status"] == "complete"
    assert len(summary["runs"]) == 12 and len(summary["aggregates"]) == 4
    assert all(row["repetitions"] == 2 for row in summary["aggregates"])
    assert summary["build"]["profile"] == "unverified-installed-extension"
    assert summary["source_before"]["native_sha256"] == summary["source_after"]["native_sha256"]
    assert {"uv.lock", ".python-version"} <= summary["source_before"]["source_hashes"].keys()
    for row in summary["runs"]:
        assert row["original_rows"] == 303
        assert row["accepted_rows"] > 0
        assert row["rss_sample_count"] > 0 and row["peak_process_rss_bytes"] > 0
        samples = [json.loads(line) for line in
                   (Path(row["artifact_dir"]) / "rss.jsonl").read_text().splitlines()]
        assert len(samples) >= row["rss_sample_count"]
        assert "verification" in json.loads(
            (Path(row["artifact_dir"]) / "verified.json").read_text())
    assert (root / "summary.csv").exists() and (root / "report.md").exists()
    reused = tmp_path / "rerun"
    rerun = command.copy()
    rerun[rerun.index(str(root))] = str(reused)
    rerun += ["--reuse-fixtures", "--compare-to", str(root / "summary.json")]
    child = subprocess.run(rerun, cwd=ROOT, capture_output=True, text=True, timeout=90)
    assert child.returncode == 0, child.stdout + child.stderr
    comparison = json.loads((reused / "summary.json").read_text())["comparison"]
    assert len(comparison["cases"]) == 4


@pytest.mark.skipif(platform.system() not in ("Darwin", "Linux"), reason="POSIX load instrumentation")
def test_failed_child_retains_logs_without_claiming_a_complete_suite(tmp_path):
    # Too few original rows cannot form the requested partitions.
    root = tmp_path / "failed"
    command = [sys.executable, "-m", "benchmarks.high_load", "--root", str(root),
               "--fixture-root", str(tmp_path / "fixtures"), "--sizes", "1", "--no-build"]
    child = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert child.returncode != 0
    result = json.loads((root / "summary.json").read_text())
    assert result["status"] == "failed" and "error" in result
    assert not (root / "report.md").exists()


@pytest.mark.skipif(platform.system() not in ("Darwin", "Linux"), reason="POSIX load instrumentation")
def test_timeout_terminates_only_the_owned_child_and_records_failure(tmp_path):
    root = tmp_path / "timeout"
    command = [sys.executable, "-m", "benchmarks.high_load", "--root", str(root),
               "--fixture-root", str(tmp_path / "fixtures"), "--sizes", "20", "--no-build",
               "--warmups", "0", "--repetitions", "1", "--timeout", "0.001"]
    child = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert child.returncode != 0
    result = json.loads((root / "summary.json").read_text())
    assert result["status"] == "failed" and "TimeoutError" in result["error"]
    assert list(root.glob("*/command.json")) and list(root.glob("*/stderr.log"))
