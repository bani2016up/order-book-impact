from zipfile import ZipFile, ZIP_DEFLATED

import pyarrow.parquet as pq
import pytest

from ofi_pipeline import InputPaths, RawInput, PipelineConfig, run_pipeline, QualityEvidenceError
from test_pipeline import records


def raw_fixture(bundle):
    events = pq.read_table(bundle / "data/events_clean.parquet").drop(["timestamp"]).to_pylist()
    by_id = {e["event_id"]: e for e in events}
    quality = (
        pq.read_table(bundle / "reports/event_quality.parquet").drop(["timestamp"]).to_pylist()
    )
    messages, books = [], []
    for q in quality:
        i = q["event_id"]
        e = by_id.get(i, by_id[4])
        size, direction, kind, price = {
            4: (7, -1, 4, 10100),
            5: (9, 1, 5, 10100),
            9: (3, 1, 4, 10100),
        }.get(i, (1, 1, 1, 10000))
        # Hidden ID 5 and close-boundary ID 9 execute inside their original pre-spreads.
        messages.append(f"{q['time_ns'] // 10**9}.000000000,{kind},0,{size},{price},{direction}\n")
        book = []
        for level in range(1, 6):
            book.extend(
                [
                    round(e[f"ask_price_{level}"] * 10000),
                    e[f"ask_size_{level}"],
                    round(e[f"bid_price_{level}"] * 10000),
                    e[f"bid_size_{level}"],
                ]
            )
        books.append(",".join(str(x) for x in book) + "\n")
    return "".join(messages), "".join(books)


@pytest.mark.parametrize("chunk", [1, 2, 3, 100])
def test_raw_pair_quote_test_chunk_matching(bundle, tmp_path, chunk):
    m, b = raw_fixture(bundle)
    # Make the hidden rejected-quote trade genuinely inside-spread before ID 5.
    # ID 4's state has ask=1.01, bid=1, so 1.005 is inside the pre-spread.
    m = m.replace(",5,0,9,10100,1", ",5,0,9,10050,1")
    tpath = bundle / "data/trades_clean.parquet"
    import pyarrow as pa

    t = pq.read_table(tpath)
    pq.write_table(
        t.set_column(
            t.schema.get_field_index("event_price"), "event_price", pa.array([1.01, 1.005, 1.01])
        ),
        tpath,
    )
    message, book = tmp_path / "message.csv", tmp_path / "orderbook.csv"
    message.write_text(m)
    book.write_text(b)
    inputs = InputPaths(
        bundle / "data/events_clean.parquet",
        tpath,
        bundle / "reports/event_quality.parquet",
        (RawInput("TEST", "2012-06-21", message=message, orderbook=book),),
    )
    c = PipelineConfig(trade_signing="quote_test", session_close="09:31:00", chunk_rows=chunk)
    report = run_pipeline(output_dir=tmp_path / "out", config=c, inputs=inputs)
    coverage = report.partitions[0].signing
    assert (coverage.classified_volume, coverage.unclassified_volume) == (7, 12)
    assert (coverage.classified_count, coverage.unclassified_count) == (1, 2)
    assert coverage.volume == 19 and coverage.trade_imbalance == 7
    assert coverage.complete_trade_imbalance is None
    rows = records(report.features_path)
    assert rows[0]["trade_imbalance"] == 7 and rows[2]["unclassified_volume"] == 3
    assert rows[2]["trade_imbalance"] is None
    assert rows[2]["classified_trade_imbalance"] == 0
    assert not rows[2]["trade_signing_complete"]
    assert not list((tmp_path / "out").glob(".raw-pair-*"))


def test_zip_discovery_and_missing_pair(bundle, tmp_path):
    m, b = raw_fixture(bundle)
    raw = bundle / "raw"
    raw.mkdir()
    (raw / "LOBSTER_SampleFile_invalid_5.zip").write_bytes(b"ignored invalid vendor naming")
    archive = raw / "LOBSTER_SampleFile_TEST_2012-06-21_5.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as z:
        z.writestr("TEST_message_5.csv", m)
        z.writestr("TEST_orderbook_5.csv", b)
    c = PipelineConfig(trade_signing="quote_test", session_close="09:31:00")
    report = run_pipeline(bundle, tmp_path / "zip", c)
    assert report.partitions[0].signing.volume == 19
    assert len(__import__("json").loads(report.manifest_path.read_text())["raw_sources"]) == 1
    archive.unlink()
    with pytest.raises(QualityEvidenceError, match="exactly one"):
        run_pipeline(bundle, tmp_path / "missing", c)


def test_public_itch_unknown_hidden_side_uses_quote_test(bundle, tmp_path):
    import pyarrow as pa
    from ofi_pipeline import ConfigurationError

    m, b = raw_fixture(bundle)
    # ID 9 is accepted and inside its pre-spread. ID 5 has a rejected post-quote.
    m = m.replace(",5,0,9,10100,1", ",5,0,9,10100,0")
    m = m.replace(",4,0,3,10100,1", ",5,0,3,10100,0")
    for filename in ["events_clean", "trades_clean"]:
        path = bundle / "data" / f"{filename}.parquet"
        table = pq.read_table(path)
        rows = table.drop(["timestamp"]).to_pylist()
        for row in rows:
            if row["event_id"] in [5, 9]:
                row["event_type"], row["direction"] = 5, 0
            row.pop("aggressor_side", None)
            row.pop("signed_volume", None)
        revised = pa.Table.from_pylist(rows)
        revised = revised.add_column(3, table.schema.field("timestamp"), table["timestamp"])
        pq.write_table(revised, path)
    message, book = tmp_path / "m.csv", tmp_path / "b.csv"
    message.write_text(m)
    book.write_text(b)
    inputs = InputPaths(
        bundle / "data/events_clean.parquet",
        bundle / "data/trades_clean.parquet",
        bundle / "reports/event_quality.parquet",
        (RawInput("TEST", "2012-06-21", message=message, orderbook=book),),
    )
    result = run_pipeline(
        inputs=inputs, output_dir=tmp_path / "quoted",
        config=PipelineConfig(trade_signing="quote_test", session_close="09:31:00"),
    )
    assert result.partitions[0].signing.volume == 19
    assert result.partitions[0].signing.unclassified_volume == 3
    assert records(result.features_path)[-1]["trade_imbalance"] is None
    with pytest.raises(ConfigurationError, match="requires quote_test"):
        run_pipeline(
            inputs=inputs, output_dir=tmp_path / "unsafe-known",
            config=PipelineConfig(session_close="09:31:00"),
        )
    from ofi_pipeline import PipelineError

    trades = pq.read_table(inputs.trades)
    trades = trades.append_column(
        "aggressor_side", pa.array([-v for v in trades["direction"].to_pylist()])
    )
    pq.write_table(trades, inputs.trades)
    with pytest.raises(PipelineError, match="unknown passive side cannot supply"):
        run_pipeline(
            inputs=inputs, output_dir=tmp_path / "fabricated-sign",
            config=PipelineConfig(trade_signing="quote_test", session_close="09:31:00"),
        )


@pytest.mark.parametrize(
    "case",
    ["invalid_post", "different_post", "invalid_integer", "unequal_fields", "bad_zip", "empty_zip"],
)
def test_raw_corruption_fails_without_publishing(bundle, tmp_path, case):
    from ofi_pipeline import PipelineError

    m, b = raw_fixture(bundle)
    if case in ("bad_zip", "empty_zip"):
        archive = tmp_path / "raw.zip"
        if case == "bad_zip":
            archive.write_bytes(b"malformed archive")
        else:
            with ZipFile(archive, "w"):
                pass
        raw = RawInput("TEST", "2012-06-21", archive=archive)
    else:
        lines = b.splitlines()
        first = lines[0].split(",")
        if case == "invalid_post":
            first[0] = "0"
        elif case == "different_post":
            first[3] = "101"
        elif case == "invalid_integer":
            first[0] = "not-an-integer"
        else:
            lines[1] = "1,2,3"
        lines[0] = ",".join(first)
        message, book = tmp_path / "m.csv", tmp_path / "b.csv"
        message.write_text(m)
        book.write_text("\n".join(lines) + "\n")
        raw = RawInput("TEST", "2012-06-21", message=message, orderbook=book)
    inputs = InputPaths(
        bundle / "data/events_clean.parquet",
        bundle / "data/trades_clean.parquet",
        bundle / "reports/event_quality.parquet",
        (raw,),
    )
    with pytest.raises(PipelineError):
        run_pipeline(
            output_dir=tmp_path / "failed",
            inputs=inputs,
            config=PipelineConfig(
                trade_signing="quote_test", session_close="09:31:00", chunk_rows=1
            ),
        )
    assert not (tmp_path / "failed").exists()
