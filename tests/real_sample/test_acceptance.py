"""Explicit external-delivery acceptance. No real data in Git."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ofi_pipeline import PipelineConfig, run_pipeline

FLOAT_TOLERANCES = {"mid_price_change": 1e-10, "mid_price_change_ticks": 1e-8, "avg_depth": 1e-10}
INTEGER_COLUMNS = [
    *(f"ofi_l{i}" for i in range(1, 6)),
    "trade_imbalance",
    "volume",
    "event_count",
    "quote_update_count",
]


@pytest.fixture(scope="module")
def sample():
    path = os.environ.get("OFI_SAMPLE_DIR")
    if not path:
        pytest.skip("OFI_SAMPLE_DIR missing: real-sample acceptance has not run")
    root = Path(path)
    for line in (root / "SHA256SUMS.txt").read_text().splitlines():
        expected, relative = line.split(maxsplit=1)
        digest = hashlib.sha256()
        with (root / relative.strip().lstrip("*")).open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        assert digest.hexdigest() == expected, f"delivery hash mismatch: {relative}"
    for name, rows in [
        ("data/events_clean.parquet", 887810),
        ("data/trades_clean.parquet", 68404),
        ("reports/event_quality.parquet", 897387),
        ("reports/bucket_quality_10s.parquet", 4680),
        ("data/features_10s.parquet", 4390),
    ]:
        f = pq.ParquetFile(root / name)
        assert f.metadata.num_rows == rows
        assert f.schema_arrow.field("timestamp").type == pa.timestamp("ns", "UTC")
        for batch in f.iter_batches(batch_size=4096):
            # Reference all-bucket features legitimately contain nulls; primary inputs do not.
            if "bucket_quality" not in name:
                assert all(c.null_count == 0 for c in batch.columns)
    for source in json.loads((root / "reports/sources.json").read_text()):
        path = root / "raw" / f"LOBSTER_SampleFile_{source['symbol']}_2012-06-21_5.zip"
        assert path.stat().st_size == source["size_bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
    return root


def keyed(table):
    table = table.select(["symbol", "date", "timestamp", *INTEGER_COLUMNS, *FLOAT_TOLERANCES])
    table = table.set_column(
        table.schema.get_field_index("timestamp"), "timestamp", table["timestamp"].cast(pa.int64())
    )
    return {(r["symbol"], r["date"], r["timestamp"]): r for r in table.to_pylist()}


def reconcile(computed, reference):
    a, b = keyed(computed), keyed(reference)
    result = {
        "missing_keys": [list(k) for k in sorted(b.keys() - a.keys())],
        "extra_keys": [list(k) for k in sorted(a.keys() - b.keys())],
        "max_abs_error": {},
        "mismatches": {},
    }
    for column in [*INTEGER_COLUMNS, *FLOAT_TOLERANCES]:
        errors = [(k, abs(a[k][column] - b[k][column])) for k in sorted(a.keys() & b.keys())]
        result["max_abs_error"][column] = max((e for _, e in errors), default=0)
        tolerance = FLOAT_TOLERANCES.get(column, 0)
        mismatches = [
            {"key": list(k), "computed": a[k][column], "reference": b[k][column]}
            for k, error in errors
            if error > tolerance
        ]
        result["mismatches"][column] = {"count": len(mismatches), "first": mismatches[:5]}
    return result


def quality_flags(table, flag):
    return {
        (symbol, date, stamp): accepted
        for symbol, date, stamp, accepted in zip(
            table["symbol"].to_pylist(),
            table["date"].to_pylist(),
            table["timestamp"].cast(pa.int64()).to_pylist(),
            table[flag].to_pylist(),
        )
    }


def test_exact_delivered_10s(sample, tmp_path):
    report = run_pipeline(sample, tmp_path / "10s", PipelineConfig(threads=1, chunk_rows=4096))
    computed = pq.read_table(report.features_path)
    result = reconcile(computed, pq.read_table(sample / "data/features_10s.parquet"))
    a = quality_flags(pq.read_table(report.bucket_quality_path), "accepted")
    b = quality_flags(
        pq.read_table(sample / "reports/bucket_quality_10s.parquet"), "valid_for_regression"
    )
    result["quality_mismatches"] = [
        list(k) for k in sorted(a.keys() | b.keys()) if a.get(k) != b.get(k)
    ]
    result["partitions"] = [
        {
            "symbol": p.symbol,
            "original_rows": p.original_rows,
            "clean_events": p.clean_events,
            "feature_rows": p.feature_rows,
            "rejected_buckets": p.rejected_buckets,
            "rounded_event_timestamps": p.rounded_event_timestamps,
        }
        for p in report.partitions
    ]
    result["float_tolerances"] = FLOAT_TOLERANCES
    (tmp_path / "reconciliation-10s.json").write_text(json.dumps(result, indent=2))
    assert (
        not result["missing_keys"] and not result["extra_keys"] and not result["quality_mismatches"]
    )
    assert all(v["count"] == 0 for v in result["mismatches"].values())
    assert (computed.num_rows, len(a), sum(not flag for flag in a.values())) == (4390, 4680, 290)
    assert {p.symbol: p.feature_rows for p in report.partitions} == {"AAPL": 2060, "MSFT": 2330}
    assert sum(p.rounded_event_timestamps for p in report.partitions) == 3
    assert all(p.missing_precision_flag_rows == 0 for p in report.partitions)


@pytest.mark.parametrize("width", [1, 5, 30, 60])
def test_independently_rebuilt_other_widths(sample, tmp_path, width, monkeypatch):
    if os.environ.get("OFI_REBUILD_REFERENCE") != "1":
        pytest.skip(
            "set OFI_REBUILD_REFERENCE=1 to run inspected preparation code as validation oracle"
        )
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "matplotlib"))
    spec = importlib.util.spec_from_file_location("lev_reference", sample / "src/prepare_sample.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Test-only reference implementation reads raw rows; production never imports it.
    references = []
    for symbol in ["AAPL", "MSFT"]:
        x = module.load_archive(
            sample / "raw" / f"LOBSTER_SampleFile_{symbol}_2012-06-21_5.zip", symbol
        )
        kept, trades, stats = module.clean(x)
        assert len(kept) == {"AAPL": 292337, "MSFT": 595473}[symbol]
        assert len(trades) == {"AAPL": 34990, "MSFT": 33414}[symbol]
        references.append(
            pa.Table.from_pandas(module.aggregate_reference(x, width), preserve_index=False)
        )
    full_reference = pa.concat_tables(references)
    reference = full_reference.filter(full_reference["valid_for_regression"])
    report = run_pipeline(
        sample,
        tmp_path / f"{width}s",
        PipelineConfig(bucket_seconds=width, threads=1, chunk_rows=2048),
    )
    result = reconcile(pq.read_table(report.features_path), reference)
    result["quality_equal"] = quality_flags(
        pq.read_table(report.bucket_quality_path), "accepted"
    ) == quality_flags(full_reference, "valid_for_regression")
    result["accepted_rows"] = report.feature_rows
    (tmp_path / f"reconciliation-{width}s.json").write_text(json.dumps(result, indent=2))
    assert not result["missing_keys"] and not result["extra_keys"] and result["quality_equal"]
    assert all(v["count"] == 0 for v in result["mismatches"].values())
