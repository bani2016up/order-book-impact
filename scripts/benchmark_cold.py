"""macOS file-targeted, verified low-residency input benchmarks.

The unchanged high-load worker owns timing. Neither physical-device cache state
nor cold decoding is claimed: source hashing is inside its public-call window.
"""

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import stat
import sys
import time

from benchmarks import high_load

ROOT = high_load.ROOT
CACHE_PROTOCOL = {
    "version": 1,
    "preparation": "read-only MAP_SHARED; msync(MS_SYNC | MS_INVALIDATE), file-targeted",
    "gate": "independent fresh-child mincore; zero MINCORE_INCORE pages in every input",
    "state": "verified-zero-input-page-residency-before-worker-setup",
    "physical_device_cache": "unverified",
    "scope": "full unchanged public call; source hashing can warm inputs before decoding",
    "startup": "fresh Python process; startup and cache preparation excluded from timing",
}


class FilePages:
    """Read-only file mapping; residency queries never touch mapped input bytes."""

    def __init__(self, path):
        if platform.system() != "Darwin":
            raise RuntimeError("Verified file-targeted protocol currently supports macOS only")
        self.path = Path(path).resolve()
        self.lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        self.lib.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
        self.lib.mmap.restype = ctypes.c_void_p
        self.lib.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
        self.lib.msync.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        self.lib.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        for name in ("mincore", "msync", "munmap"):
            getattr(self.lib, name).restype = ctypes.c_int

    def __enter__(self):
        self.fd = os.open(self.path, os.O_RDONLY)
        try:
            self.identity = os.fstat(self.fd)
            if not stat.S_ISREG(self.identity.st_mode) or self.identity.st_size <= 0:
                raise ValueError("Cache protocol requires a nonempty regular file")
            self.size = self.identity.st_size
            self.page_size = os.sysconf("SC_PAGE_SIZE")
            self.pages = (self.size + self.page_size - 1) // self.page_size
            # Darwin constants: PROT_READ=1, MAP_SHARED=1. No writable mapping.
            self.address = self.lib.mmap(None, self.size, 1, 1, self.fd, 0)
            if self.address == ctypes.c_void_p(-1).value:
                raise OSError(ctypes.get_errno(), "Read-only mmap failed")
            return self
        except BaseException:
            os.close(self.fd)
            raise

    def residency(self):
        vector = (ctypes.c_ubyte * self.pages)()
        if self.lib.mincore(self.address, self.size, vector):
            raise OSError(ctypes.get_errno(), "mincore failed")
        resident = sum(bool(value & 1) for value in vector)
        return {"path": str(self.path), "size_bytes": self.size,
                "device": self.identity.st_dev, "inode": self.identity.st_ino,
                "mtime_ns": self.identity.st_mtime_ns, "page_size": self.page_size,
                "pages": self.pages, "resident_pages": resident,
                "resident_fraction": resident / self.pages,
                "monotonic_seconds": time.perf_counter(),
                "method": "untouched read-only MAP_SHARED; mincore MINCORE_INCORE bit"}

    def invalidate(self):
        # Public Darwin constants: MS_SYNC=0x10, MS_INVALIDATE=0x2.
        if self.lib.msync(self.address, self.size, 0x10 | 0x2):
            raise OSError(ctypes.get_errno(), "File-targeted msync invalidation failed")

    def __exit__(self, *_):
        code = self.lib.munmap(self.address, self.size)
        error = ctypes.get_errno()
        os.close(self.fd)
        if code:
            raise OSError(error, "munmap failed")


def input_files(fixture, metadata, signing):
    items = list(metadata["inputs"].values())
    if signing == "quote_test":
        items.extend(metadata["raw_sources"])
    paths = []
    for item in items:
        path = (fixture / item["path"]).resolve()
        if not path.is_relative_to(fixture.resolve()):
            raise ValueError("Input path escapes its fixture")
        paths.append(path)
    return paths


def probe_inputs(paths):
    points = []
    for path in paths:
        with FilePages(path) as mapping:
            points.append(mapping.residency())
    return points


def require_zero(points):
    if not points or any(point["resident_pages"] for point in points):
        raise ValueError("Input residency is not verified zero; refusing a cold-input claim")


def prepare_inputs(paths):
    before = probe_inputs(paths)
    for path in paths:
        with FilePages(path) as mapping:
            mapping.invalidate()
    # New mappings independently observe the result of the request.
    after = probe_inputs(paths)
    return {"before": before, "after": after, "request": CACHE_PROTOCOL["preparation"]}


def worker(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--cache-state", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--signing", required=True)
    args, _ = parser.parse_known_args(argv)
    # Complete imports before observing pre-read state; no PyArrow/NumPy here.
    from benchmarks import high_load_worker
    metadata = json.loads((args.fixture / "fixture.json").read_text())
    points = probe_inputs(input_files(args.fixture, metadata, args.signing))
    evidence = {"protocol": CACHE_PROTOCOL, "pid": os.getpid(), "inputs": points,
                "helper_sha256": high_load.sha256(__file__),
                "recorded_monotonic_seconds": time.perf_counter(),
                "status": "verified-zero" if points and all(
                    point["resident_pages"] == 0 for point in points) else "rejected"}
    high_load.write_json(args.cache_state, evidence)
    require_zero(points)
    remaining = list(argv)
    remaining.remove("--worker")
    index = remaining.index("--cache-state")
    del remaining[index:index + 2]
    sys.argv = ["benchmarks.high_load_worker", *remaining]
    high_load_worker.main()


def validate_reference(reference, snapshot):
    if reference["status"] != "complete" or reference["build"]["profile"] != "release":
        raise ValueError("Normal reference must be complete with verified release provenance")
    for field in ("platform", "machine", "python", "cpu_count", "host_id"):
        if reference["source_before"][field] != snapshot[field]:
            raise ValueError(f"Normal reference host/runtime differs: {field}")
    if reference["source_before"]["native_sha256"] != snapshot["native_sha256"]:
        raise ValueError("Installed binary differs from normal release reference")
    old = reference["source_before"]["source_hashes"]
    if old != snapshot["source_hashes"]:
        raise ValueError("Engine or unchanged benchmark source identity differs from normal reference")


def compare_cold(summary, path):
    prior = json.loads(path.read_text())
    if prior["helper_sha256"] != summary["helper_sha256"]:
        raise ValueError("Cold helper source identity differs from cold baseline")
    return high_load.compare_baseline(summary, path)


def run_suite(args):
    reference = json.loads(args.normal_reference.read_text())
    before = high_load.snapshot()
    validate_reference(reference, before)
    root = args.root.resolve()
    if root.exists():
        raise FileExistsError("Result root exists; use a new root")
    if not root.is_relative_to((ROOT / "benchmarks/results").resolve()):
        raise ValueError("Large evidence must remain under ignored benchmarks/results")
    root.mkdir(parents=True)
    helper_hash = high_load.sha256(__file__)
    protocol = {**reference["protocol"], "cache": CACHE_PROTOCOL}
    output_root = ROOT / "outputs/features/cold-input" / (
        root.name + "-" + hashlib.sha256(str(root).encode()).hexdigest()[:12])
    summary = {"schema_version": 1, "status": "running", "protocol": protocol,
               "normal_reference": str(args.normal_reference.resolve()),
               "normal_reference_sha256": high_load.sha256(args.normal_reference),
               "helper_sha256": helper_hash, "source_before": before,
               "build": {"profile": "release", "method": "binary and source identity matched "
                         "complete normal release reference", "reference": reference["build"]},
               "fixtures": {}, "runs": [], "output_root": str(output_root),
               "started_utc": datetime.now(timezone.utc).isoformat()}
    high_load.write_json(root / "summary.json", summary)
    try:
        expected = {row["case_id"]: row for row in reference["aggregates"]}
        for size in protocol["sizes"]:
            wanted = reference["fixtures"][str(size)]
            fixture = args.fixture_root.resolve() / (
                f"n{size}-p{protocol['partitions']}-s{wanted['spec']['seed']}")
            metadata = high_load.verify_fixture(fixture, wanted["spec"])
            actual = {key: metadata[key] for key in wanted}
            if actual != wanted:
                raise ValueError("Fixture metadata differs from normal reference")
            summary["fixtures"][str(size)] = actual
            for signing in protocol["signings"]:
                for case in protocol["cases"]:
                    threads, chunk = high_load.CASES[case]
                    case_id = f"n{size}-{signing}-{case}"
                    for index in range(protocol["warmups"] + protocol["repetitions"]):
                        warmup = index < protocol["warmups"]
                        number = index + 1 if warmup else index - protocol["warmups"] + 1
                        name = f"{case_id}-{'warmup' if warmup else 'run'}-{number}"
                        run_dir = root / name
                        run_dir.mkdir()
                        paths = input_files(fixture, metadata, signing)
                        preparation = prepare_inputs(paths)
                        high_load.write_json(run_dir / "cache-preparation.json", preparation)
                        require_zero(preparation["after"])
                        command = [sys.executable, "-m", "scripts.benchmark_cold", "--worker",
                                   "--cache-state", str(run_dir / "cache-state.json"),
                                   "--fixture", str(fixture), "--threads", str(threads),
                                   "--chunk-rows", str(chunk), "--bucket-seconds",
                                   str(protocol["bucket_seconds"]), "--signing", signing]
                        print(f"{name}: verified zero parent residency; starting child", flush=True)
                        result = high_load.measure(command, run_dir, output_root / name,
                                                   metadata, before,
                                                   protocol["sample_interval_seconds"], args.timeout)
                        state = json.loads((run_dir / "cache-state.json").read_text())
                        require_zero(state["inputs"])
                        if state["helper_sha256"] != helper_hash:
                            raise ValueError("Child helper identity differs")
                        if result["verification"] != expected[case_id]["verification"]:
                            raise ValueError("Decoded output differs from normal reference")
                        if result["peak_partition_workers"] > threads:
                            raise ValueError("Worker bound exceeded")
                        phase = json.loads((run_dir / "phase.json").read_text())
                        result.update({"case_id": case_id, "warmup": warmup,
                                       "cache_state": state, "cache_preparation": preparation,
                                       "finished_phase": phase})
                        summary["runs"].append(result)
                        high_load.write_json(root / "summary.json", summary)
                        print(f"{name}: {result['wall_seconds']:.3f}s; output verified", flush=True)
            high_load.verify_fixture(fixture, wanted["spec"])
        after = high_load.snapshot()
        summary["source_after"] = after
        if before["source_hashes"] != after["source_hashes"] or (
            before["native_sha256"] != after["native_sha256"]
        ) or high_load.sha256(__file__) != helper_hash:
            raise ValueError("Source, binary or helper changed during suite")
        summary["aggregates"] = high_load.aggregate(summary["runs"])
        summary.update({"status": "complete", "finished_utc": datetime.now(timezone.utc).isoformat()})
        if args.compare_to:
            summary["comparison"] = compare_cold(summary, args.compare_to)
        high_load.write_json(root / "summary.json", summary)
        (root / "report.md").write_text(
            "# Verified low-residency input benchmark\n\n"
            "Every fresh child verified zero resident input pages before unchanged worker setup. "
            "Physical-device cache is unverified. Source hashing can warm decoding within the "
            "timed public call. Complete protocol, provenance and repeated output verification "
            "are in summary.json.\n")
    except BaseException as error:
        summary.update({"status": "failed", "error": repr(error)})
        high_load.write_json(root / "summary.json", summary)
        raise


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--worker" in argv:
        return worker(argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--normal-reference", type=Path, required=True)
    parser.add_argument("--fixture-root", type=Path, default=ROOT / "data/high_load")
    parser.add_argument("--compare-to", type=Path)
    parser.add_argument("--timeout", type=float, default=3600)
    args = parser.parse_args(argv)
    if platform.system() != "Darwin":
        parser.error("This verified low-residency protocol requires macOS")
    if args.timeout <= 0 or not math.isfinite(args.timeout):
        parser.error("Timeout must be finite and positive")
    run_suite(args)


if __name__ == "__main__":
    main()
