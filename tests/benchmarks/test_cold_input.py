"""File-targeted cache verification and honest claim guards."""

import copy
import json
from pathlib import Path
import platform
import subprocess
import sys

import pytest

from scripts.benchmark_cold import (
    FilePages, compare_cold, input_files, prepare_inputs, probe_inputs,
    require_zero, validate_reference,
)


def test_zero_gate_rejects_any_residency_or_missing_evidence():
    require_zero([{"resident_pages": 0}, {"resident_pages": 0}])
    for points in ([], [{"resident_pages": 1}],
                   [{"resident_pages": 0}, {"resident_pages": 1}]):
        with pytest.raises(ValueError, match="not verified zero"):
            require_zero(points)


def test_fixture_paths_cannot_escape_or_omit_raw_inputs(tmp_path):
    metadata = {"inputs": {"events": {"path": "data/events"}},
                "raw_sources": [{"path": "raw/messages"}, {"path": "raw/books"}]}
    assert len(input_files(tmp_path, metadata, "lobster_direction")) == 1
    assert len(input_files(tmp_path, metadata, "quote_test")) == 3
    metadata["inputs"]["events"]["path"] = "../outside"
    with pytest.raises(ValueError, match="escapes"):
        input_files(tmp_path, metadata, "lobster_direction")


@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin file-cache protocol")
def test_msync_evicts_warmed_authored_file_without_modifying_bytes(tmp_path):
    path = tmp_path / "authored.bin"
    content = bytes(range(256)) * 1024
    path.write_bytes(content)
    initial_stat = path.stat()
    assert path.read_bytes() == content
    warmed = probe_inputs([path])
    assert warmed[0]["resident_pages"] == warmed[0]["pages"]
    for _ in range(3):
        evidence = prepare_inputs([path])
        require_zero(evidence["after"])
        # An independent new mapping still observes the invalidation.
        require_zero(probe_inputs([path]))
        assert path.stat().st_mtime_ns == initial_stat.st_mtime_ns
        assert path.read_bytes() == content


@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin file-cache protocol")
def test_mapping_rejects_empty_file(tmp_path):
    path = tmp_path / "empty"
    path.touch()
    with pytest.raises(ValueError, match="nonempty"):
        with FilePages(path):
            pass


def test_release_reference_rejects_binary_source_and_host_changes():
    snapshot = {"platform": "test", "machine": "test", "python": "test",
                "cpu_count": 1, "host_id": "test", "native_sha256": "native",
                "source_hashes": {"benchmarks/results/ignored.py": "original"}}
    reference = {"status": "complete", "build": {"profile": "release"},
                 "source_before": snapshot}
    validate_reference(reference, copy.deepcopy(snapshot))
    for field in ("host_id", "native_sha256", "source_hashes"):
        changed = copy.deepcopy(snapshot)
        changed[field] = {} if field == "source_hashes" else "changed"
        with pytest.raises(ValueError):
            validate_reference(reference, changed)
    unverified = copy.deepcopy(reference)
    unverified["build"]["profile"] = "unverified-installed-extension"
    with pytest.raises(ValueError, match="release"):
        validate_reference(unverified, snapshot)


def test_cold_comparison_requires_identical_helper_hash(tmp_path):
    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps({"helper_sha256": "old"}))
    with pytest.raises(ValueError, match="helper source identity"):
        compare_cold({"helper_sha256": "new"}, reference)


def test_cold_comparison_checks_protocol_fixtures_and_decoded_output(tmp_path):
    summary = {
        "status": "complete", "helper_sha256": "same", "build": {"profile": "release"},
        "protocol": {"cache": "verified-zero", "repetitions": 3}, "fixtures": {"100": "same"},
        "source_before": {"platform": "test", "machine": "test", "python": "test",
                          "cpu_count": 1, "host_id": "test", "source_hashes": {}},
        "aggregates": [{"case_id": "one", "verification": {"decoded": "same"},
                        "wall_seconds_median": 2, "peak_rss_mib_median": 10}],
    }
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(summary))
    assert compare_cold(summary, path)["equal_case_geometric_speedup"] == 1
    for field, value in (("protocol", {"cache": "unverified"}),
                         ("fixtures", {"100": "different"})):
        changed = copy.deepcopy(summary)
        changed[field] = value
        with pytest.raises(ValueError):
            compare_cold(changed, path)
    changed = copy.deepcopy(summary)
    changed["aggregates"][0]["verification"] = {"decoded": "changed"}
    with pytest.raises(ValueError, match="Decoded"):
        compare_cold(changed, path)


@pytest.mark.skipif(platform.system() != "Darwin", reason="Darwin file-cache protocol")
def test_fresh_wrapper_verifies_output_and_refuses_warm_input(tmp_path):
    from benchmarks.high_load import measure, snapshot
    from benchmarks.high_load_fixture import FixtureSpec, generate

    fixture = tmp_path / "fixture"
    metadata = generate(fixture, FixtureSpec(2000, partitions=4, session_seconds=60))
    paths = input_files(fixture, metadata, "lobster_direction")
    before = snapshot()
    repository = Path(__file__).resolve().parents[2]
    fingerprints = []
    for index in range(2):
        run = tmp_path / f"run-{index}"
        run.mkdir()
        preparation = prepare_inputs(paths)
        require_zero(preparation["after"])
        command = [sys.executable, "-m", "scripts.benchmark_cold", "--worker",
                   "--cache-state", str(run / "cache-state.json"),
                   "--fixture", str(fixture), "--signing", "lobster_direction",
                   "--threads", "1", "--chunk-rows", "4096"]
        result = measure(command, run, tmp_path / f"output-{index}", metadata, before, 0.05, 30)
        state = json.loads((run / "cache-state.json").read_text())
        assert state["status"] == "verified-zero"
        assert state["protocol"]["physical_device_cache"] == "unverified"
        require_zero(state["inputs"])
        assert state["helper_sha256"]
        fingerprints.append(result["verification"])
    assert fingerprints[0] == fingerprints[1]
    # Ordinary reads deliberately restore residency before the refusal test.
    for path in paths:
        path.read_bytes()
    rejected = tmp_path / "rejected.json"
    command = [sys.executable, "-m", "scripts.benchmark_cold", "--worker",
               "--cache-state", str(rejected), "--fixture", str(fixture),
               "--signing", "lobster_direction", "--output", str(tmp_path / "refused"),
               "--result", str(tmp_path / "measurement.json"),
               "--phase", str(tmp_path / "phase.json"), "--rss", str(tmp_path / "rss.jsonl"),
               "--sample-interval", "0.05", "--threads", "1", "--chunk-rows", "4096"]
    child = subprocess.run(command, cwd=repository, capture_output=True, text=True, timeout=30)
    assert child.returncode != 0
    state = json.loads(rejected.read_text())
    assert state["status"] == "rejected"
    assert any(point["resident_pages"] > 0 for point in state["inputs"])
    assert not (tmp_path / "refused").exists()
    assert not (tmp_path / "measurement.json").exists()
