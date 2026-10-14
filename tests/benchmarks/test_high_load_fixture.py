"""Small synthetic-fixture correctness checks, not high-load performance assertions."""

import json

import pyarrow.parquet as pq
import pytest

from benchmarks.high_load_fixture import FixtureSpec, generate, sha256
from ofi_pipeline import InputPaths, PipelineConfig, RawInput, run_pipeline


def inputs(root, metadata):
    return InputPaths(
        *(root / metadata["inputs"][kind]["path"] for kind in ("events", "trades", "quality")),
        raw=tuple(RawInput(item["symbol"], item["date"],
                           message=root / item["message"], orderbook=root / item["orderbook"])
                  for item in metadata["raw_inputs"]),
    )


def test_generation_is_batch_invariant_and_bounded_to_the_session(tmp_path):
    roots = [tmp_path / "a", tmp_path / "b"]
    for root, batch_rows in zip(roots, (7, 11)):
        metadata = generate(root, FixtureSpec(103, partitions=3, batch_rows=batch_rows,
                                             reject_every=7, session_seconds=60))
        assert sum(p["original_rows"] for p in metadata["expected_partitions"]) == 103
        assert metadata["inputs"]["quality"]["rows"] == 103
        for source in metadata["inputs"].values():
            assert sha256(root / source["path"]) == source["sha256"]
        q = pq.read_table(root / "reports/event_quality.parquet").to_pydict()
        assert min(q["time_ns"]) > 34200 * 10**9
        assert max(q["time_ns"]) < 34260 * 10**9
        assert pq.ParquetFile(root / "data/events_clean.parquet").metadata.num_row_groups > 1
    for relative in ("data/events_clean.parquet", "data/trades_clean.parquet",
                     "reports/event_quality.parquet"):
        assert pq.read_table(roots[0] / relative).equals(pq.read_table(roots[1] / relative))


@pytest.mark.parametrize("signing", ["lobster_direction", "quote_test"])
def test_authored_fixture_crosses_the_real_native_boundary(tmp_path, signing):
    root = tmp_path / "fixture"
    metadata = generate(root, FixtureSpec(303, partitions=3, batch_rows=13, trade_every=3,
                                         reject_every=7, session_seconds=60, with_raw=True))
    report = run_pipeline(
        output_dir=tmp_path / "out", inputs=inputs(root, metadata),
        config=PipelineConfig(threads=2, chunk_rows=11, trade_signing=signing,
                              session_close=metadata["session_close"]),
    )
    for actual, expected in zip(report.partitions, metadata["expected_partitions"]):
        for field in ("original_rows", "clean_events", "rejected_events"):
            assert getattr(actual, field) == expected[field]
        assert actual.signing.volume == expected["volume"]
        assert actual.signing.trade_count == expected["trade_count"]
        if signing == "lobster_direction":
            assert actual.signing.unclassified_count == 0
            assert actual.signing.trade_imbalance == expected["known_trade_imbalance"]
        else:
            assert actual.signing.classified_count == expected["quote_classified_count"]
            assert actual.signing.classified_volume == expected["quote_classified_volume"]
            assert actual.signing.trade_imbalance == expected["quote_classified_imbalance"]
    quality = pq.read_table(report.bucket_quality_path)
    assert sum(quality["volume"].to_pylist()) == sum(
        p["volume"] for p in metadata["expected_partitions"]
    )
    features = pq.read_table(report.features_path)
    assert all(f"ofi_l{level}" in features.column_names for level in range(1, 6))
    assert json.loads((root / "fixture.json").read_text())["kind"].startswith("authored-synthetic")


def test_fixture_refuses_overwrite_and_invalid_sizes(tmp_path):
    root = tmp_path / "owned"
    generate(root, FixtureSpec(8, partitions=2, session_seconds=60))
    original = (root / "fixture.json").read_bytes()
    with pytest.raises(FileExistsError):
        generate(root, FixtureSpec(10))
    assert (root / "fixture.json").read_bytes() == original
    for spec in (FixtureSpec(1), FixtureSpec(10, batch_rows=0),
                 FixtureSpec(10, partitions=6), FixtureSpec(10, session_seconds=61),
                 FixtureSpec(10, reject_every=1)):
        with pytest.raises(ValueError):
            spec.validate()
