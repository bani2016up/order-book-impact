import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ofi_pipeline import (
    InputPaths,
    PipelineConfig,
    RunReport,
    run_pipeline,
    PipelineIOError,
    ConfigurationError,
    QualityEvidenceError,
    OrderingError,
    MissingInputError,
)
from conftest import make_bundle, OPEN


def config(**kwargs):
    return PipelineConfig(session_close="09:31:00", **kwargs)


def records(path):
    table = pq.read_table(path)
    for name in ["timestamp", "interval_start"]:
        table = table.set_column(
            table.schema.get_field_index(name), name, table[name].cast(pa.int64())
        )
    return table.to_pylist()


def test_hand_calculated_complete_rust_outputs(bundle, tmp_path):
    # Poison oracle files: production must never read either.
    (bundle / "data/features_10s.parquet").write_bytes(b"forbidden oracle")
    (bundle / "reports/bucket_quality_10s.parquet").write_bytes(b"forbidden mask")
    report = run_pipeline(bundle, tmp_path / "result", config(chunk_rows=1, threads=1))
    assert isinstance(report, RunReport)
    rows = records(report.features_path)
    assert report.feature_rows == 3
    assert [r["timestamp"] for r in rows] == [OPEN + s * 10**9 for s in (20, 50, 60)]
    r = rows[0]
    assert r["ofi_l1"] == 50 and all(r[f"ofi_l{i}"] == 0 for i in range(2, 6))
    assert r["trade_imbalance"] == r["volume"] == 7
    assert r["avg_depth"] == 120 and r["event_count"] == 3 and r["quote_update_count"] == 2
    assert rows[1]["ofi_l1"] == -20 and rows[1]["avg_depth"] == 105
    assert rows[2]["trade_imbalance"] == -3 and rows[2]["volume"] == 3
    quality = records(report.bucket_quality_path)
    assert [r["accepted"] for r in quality] == [False, True, False, False, True, True]
    assert quality[2]["volume"] == 9 and quality[2]["trade_imbalance"] == -9
    assert quality[2]["ofi_l1"] is None
    assert quality[3]["mid_price_change"] is None
    p = report.partitions[0]
    assert (p.original_rows, p.clean_events, p.rejected_events) == (10, 9, 1)
    assert p.signing.volume == 19 and p.signing.trade_imbalance == -5
    manifest = json.loads(report.manifest_path.read_text())
    assert manifest["units"]["timestamp"] == "UTC nanoseconds"
    assert manifest["dataset_identity"]["events"]["size_bytes"] > 0
    assert json.loads(report.quality_report_path.read_text())["partitions"][0]["feature_rows"] == 3


@pytest.mark.parametrize("chunk", [1, 2, 3, 100])
def test_chunk_invariance_and_explicit_csv(bundle, tmp_path, chunk):
    baseline = run_pipeline(bundle, tmp_path / "baseline", config(chunk_rows=65536, threads=1))
    candidate = run_pipeline(str(bundle), str(tmp_path / "chunk"), config(chunk_rows=chunk))
    assert records(candidate.features_path) == records(baseline.features_path)
    assert records(candidate.bucket_quality_path) == records(baseline.bucket_quality_path)
    csv = make_bundle(tmp_path / "csv", "csv.gz")
    inputs = InputPaths(
        csv / "data/events_clean.csv.gz",
        csv / "data/trades_clean.csv.gz",
        csv / "reports/event_quality.csv.gz",
    )
    result = run_pipeline(
        output_dir=tmp_path / "csv-result", config=config(chunk_rows=chunk), inputs=inputs
    )
    assert records(result.features_path) == records(baseline.features_path)
    assert records(result.bucket_quality_path) == records(baseline.bucket_quality_path)


def test_publication_overwrite_collision_and_failed_run(bundle, tmp_path):
    output = tmp_path / "result"
    run_pipeline(bundle, output, config())
    original = (output / "features.parquet").read_bytes()
    with pytest.raises(PipelineIOError, match="already exists"):
        run_pipeline(bundle, output, config())
    run_pipeline(bundle, output, config(overwrite=True))
    (output / "user.txt").write_text("keep")
    with pytest.raises(PipelineIOError, match="user data"):
        run_pipeline(bundle, output, config(overwrite=True))
    with pytest.raises(ConfigurationError, match="input"):
        run_pipeline(bundle, bundle, config(overwrite=True))
    quality_path = bundle / "reports/event_quality.parquet"
    table = pq.read_table(quality_path)
    # A contradictory accepted mask must fail before publishing, preserving existing results.
    table = table.set_column(
        table.schema.get_field_index("quote_accepted"), "quote_accepted", pa.array([True] * 10)
    )
    pq.write_table(table, quality_path)
    (output / "user.txt").unlink()
    with pytest.raises(QualityEvidenceError):
        run_pipeline(bundle, output, config(overwrite=True))
    assert (output / "features.parquet").read_bytes() == original
    with pytest.raises(QualityEvidenceError):
        run_pipeline(bundle, tmp_path / "failed", config())
    assert not (tmp_path / "failed").exists()
    assert not list(tmp_path.glob(".ofi-stage-*"))


def test_duplicate_input_and_missing_evidence(bundle, tmp_path):
    events = bundle / "data/events_clean.parquet"
    table = pq.read_table(events)
    pq.write_table(pa.concat_tables([table.slice(0, 1), table]), events)
    with pytest.raises(OrderingError):
        run_pipeline(bundle, tmp_path / "dup", config())
    (bundle / "reports/event_quality.parquet").unlink()
    with pytest.raises(MissingInputError):
        run_pipeline(bundle, tmp_path / "missing", config())
