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
    assert p.signing.complete_trade_imbalance == -5
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


def test_decimal_rounding_flags_and_precision_failures(bundle, tmp_path):
    path = bundle / "data/events_clean.parquet"
    table = pq.read_table(path)
    text = table["time_seconds_text"].to_pylist()
    # Decimal half-up gives exactly the already-delivered first timestamp.
    text[0] = "34200.999999999500"
    flags = [True] + [False] * (len(text) - 1)
    table = table.set_column(
        table.schema.get_field_index("time_seconds_text"), "time_seconds_text", pa.array(text)
    )
    table = table.set_column(
        table.schema.get_field_index("timestamp_subnanosecond_rounded"),
        "timestamp_subnanosecond_rounded",
        pa.array(flags),
    )
    pq.write_table(table, path)
    report = run_pipeline(bundle, tmp_path / "rounded", config())
    assert report.partitions[0].rounded_event_timestamps == 1
    assert report.partitions[0].missing_precision_flag_rows == 0
    from ofi_pipeline import MalformedDataError

    flags[0] = False
    pq.write_table(
        table.set_column(
            table.schema.get_field_index("timestamp_subnanosecond_rounded"),
            "timestamp_subnanosecond_rounded",
            pa.array(flags),
        ),
        path,
    )
    with pytest.raises(MalformedDataError, match="rounding flag"):
        run_pipeline(bundle, tmp_path / "wrong-flag", config())


@pytest.mark.parametrize(
    "change", ["missing_trade", "different_trade_size", "invalid_event_type", "wrong_raw_scaling"]
)
def test_accepted_messages_and_execution_correspondence(bundle, tmp_path, change):
    from ofi_pipeline import MalformedDataError

    tpath = bundle / "data/trades_clean.parquet"
    epath = bundle / "data/events_clean.parquet"
    if change == "missing_trade":
        pq.write_table(pq.read_table(tpath).slice(1), tpath)
    elif change == "different_trade_size":
        table = pq.read_table(tpath)
        sizes = table["event_size"].to_pylist()
        sizes[0] = 8
        table = table.drop(["signed_volume", "aggressor_side"])
        pq.write_table(
            table.set_column(
                table.schema.get_field_index("event_size"), "event_size", pa.array(sizes)
            ),
            tpath,
        )
    elif change == "invalid_event_type":
        table = pq.read_table(epath)
        kinds = table["event_type"].to_pylist()
        kinds[0] = 6
        pq.write_table(
            table.set_column(
                table.schema.get_field_index("event_type"), "event_type", pa.array(kinds)
            ),
            epath,
        )
    else:
        table = pq.read_table(epath)
        table = table.append_column("event_price_raw", pa.array([1] * table.num_rows))
        pq.write_table(table, epath)
    exception = QualityEvidenceError if "trade" in change else MalformedDataError
    with pytest.raises(exception):
        run_pipeline(bundle, tmp_path / "invalid", config())


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "quality_ends",
        "bad_trade_sign",
        "bad_trade_direction",
        "timestamp_units",
        "missing_message_field",
        "duplicate_columns",
        "outside_session",
    ],
)
def test_file_set_failure_branches(bundle, tmp_path, case):
    from ofi_pipeline import PipelineError

    events = bundle / "data/events_clean.parquet"
    trades = bundle / "data/trades_clean.parquet"
    quality = bundle / "reports/event_quality.parquet"
    cfg = config(chunk_rows=1)
    if case == "empty":
        for path in [events, trades, quality]:
            pq.write_table(pq.read_table(path).slice(0, 0), path)
    elif case == "quality_ends":
        pq.write_table(pq.read_table(quality).slice(0, 5), quality)
    elif case == "bad_trade_sign":
        table = pq.read_table(trades)
        pq.write_table(
            table.set_column(
                table.schema.get_field_index("signed_volume"), "signed_volume", pa.array([0, 0, 0])
            ),
            trades,
        )
    elif case == "bad_trade_direction":
        table = pq.read_table(trades)
        pq.write_table(
            table.set_column(
                table.schema.get_field_index("direction"), "direction", pa.array([0, 1, 1])
            ),
            trades,
        )
    elif case == "timestamp_units":
        table = pq.read_table(events)
        table = table.set_column(
            table.schema.get_field_index("timestamp"),
            "timestamp",
            table["timestamp"].cast(pa.timestamp("us", "UTC")),
        )
        pq.write_table(table, events)
    elif case == "missing_message_field":
        pq.write_table(pq.read_table(events).drop(["event_type"]), events)
    elif case == "duplicate_columns":
        csv = tmp_path / "duplicated.csv"
        csv.write_text(
            "symbol,event_id,timestamp,time_ns,quote_accepted,reject_reason,extra,extra\n"
        )
        from ofi_pipeline import InputPaths

        with pytest.raises(PipelineError):
            run_pipeline(
                output_dir=tmp_path / "bad", config=cfg, inputs=InputPaths(events, trades, csv)
            )
        return
    else:
        cfg = PipelineConfig(session_close="09:30:10", chunk_rows=1)
    with pytest.raises(PipelineError):
        run_pipeline(bundle, tmp_path / "bad", cfg)
    assert not (tmp_path / "bad").exists()
