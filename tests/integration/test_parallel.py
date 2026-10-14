import json

import pyarrow as pa
import pyarrow.parquet as pq

from ofi_pipeline import PipelineConfig, run_pipeline
from test_pipeline import records


def test_independent_symbols_and_dates_bounded_and_deterministic(bundle, tmp_path):
    for path in [
        bundle / "data/events_clean.parquet",
        bundle / "data/trades_clean.parquet",
        bundle / "reports/event_quality.parquet",
    ]:
        table = pq.read_table(path)
        partitions = []
        for symbol in ["AAA", "BBB"]:
            for day in range(2):
                t = table.set_column(
                    table.schema.get_field_index("symbol"),
                    "symbol",
                    pa.array([symbol] * table.num_rows),
                )
                timestamps = [
                    stamp + day * 86_400 * 10**9
                    for stamp in table["timestamp"].cast(pa.int64()).to_pylist()
                ]
                t = t.set_column(
                    t.schema.get_field_index("timestamp"),
                    "timestamp",
                    pa.array(timestamps, pa.timestamp("ns", "UTC")),
                )
                if "date" in t.column_names:
                    t = t.set_column(
                        t.schema.get_field_index("date"),
                        "date",
                        pa.array([f"2012-06-{21 + day}"] * table.num_rows),
                    )
                partitions.append(t)
        pq.write_table(pa.concat_tables(partitions), path, row_group_size=5)
    baseline = None
    for threads, chunk in [(1, 1), (2, 2), (4, 3), (2, 100)]:
        report = run_pipeline(
            bundle,
            tmp_path / f"t{threads}-c{chunk}",
            PipelineConfig(threads=threads, chunk_rows=chunk, session_close="09:31:00"),
        )
        assert 1 <= report.peak_partition_workers <= threads
        assert len(report.partitions) == 4 and report.feature_rows == 12
        assert all(p.signing.volume == 19 and p.original_rows == 10 for p in report.partitions)
        assert not report.warnings
        values = (records(report.features_path), records(report.bucket_quality_path))
        assert not list(report.output_dir.glob(".ofi-partition-*"))
        manifest = json.loads(report.manifest_path.read_text())
        for key in ["chunk_rows", "threads"]:
            manifest["config"].pop(key)
        if baseline is None:
            baseline = values, manifest
        else:
            assert (values, manifest) == baseline
