use arrow_array::{
    ArrayRef, BooleanArray, Float64Array, Int64Array, RecordBatch, StringArray,
    TimestampNanosecondArray,
};
use arrow_schema::{DataType, Field, Schema, TimeUnit};
use flate2::{Compression, write::GzEncoder};
use ofi_core::{
    adapter::{Kind, TableReader},
    error::ErrorCode,
};
use parquet::arrow::ArrowWriter;
use std::{
    fs::{self, File},
    io::Write,
    sync::Arc,
};

const QUALITY: &str = "symbol,event_id,timestamp,time_ns,quote_accepted,reject_reason\nA,0,2012-06-21 13:30:00.000000001+00:00,34200000000001,False,spread_above_p95\nA,1,2012-06-21 13:30:00.000000001+00:00,34200000000001,True,\n";
const EVENT: &str = "symbol,date,event_id,timestamp,time_ns,segment_id,prev_state_available,is_quote_update,bid_price_1,ask_price_1,bid_size_1,ask_size_1,event_type,event_size,event_price,direction\nA,2012-06-21,1,2012-06-21T13:30:00.000000001Z,34200000000001,1,False,True,1,1.01,100,120,1,1,1,1\n";
const TRADE: &str = "symbol,date,event_id,timestamp,time_ns,event_type,event_size,event_price,direction,quote_accepted,aggressor_side,signed_volume\nA,2012-06-21,0,2012-06-21T13:30:00.000000001Z,34200000000001,4,10,1.01,-1,False,1,10\n";

#[test]
fn every_depth_resolves_reordered_columns_and_checks_prices() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("events.csv");
    for levels in 1..=5 {
        let mut columns: Vec<String> = EVENT
            .lines()
            .next()
            .unwrap()
            .split(',')
            .map(str::to_owned)
            .collect();
        let mut values: Vec<String> = EVENT
            .lines()
            .nth(1)
            .unwrap()
            .split(',')
            .map(str::to_owned)
            .collect();
        for level in 2..=levels {
            columns.extend([
                format!("bid_price_{level}"),
                format!("ask_price_{level}"),
                format!("bid_size_{level}"),
                format!("ask_size_{level}"),
            ]);
            values.extend([
                format!("{:.2}", 1.0 - (level - 1) as f64 * 0.01),
                format!("{:.2}", 1.01 + (level - 1) as f64 * 0.01),
                (100 + level).to_string(),
                (120 + level).to_string(),
            ]);
        }
        columns.reverse();
        values.reverse();
        let csv = |values: &[String]| format!("{}\n{}\n", columns.join(","), values.join(","));
        fs::write(&path, csv(&values)).unwrap();
        for chunk in [1, 2] {
            let event = TableReader::open(&path, Kind::Events, levels, chunk)
                .unwrap()
                .next_event()
                .unwrap()
                .unwrap();
            assert_eq!(event.book.0.len(), levels);
            for (rank, level) in event.book.0.iter().enumerate() {
                assert_eq!(level.bid, 10000 - rank as i64 * 100);
                assert_eq!(level.ask, 10100 + rank as i64 * 100);
            }
        }
        let last_bid = columns
            .iter()
            .position(|c| c == &format!("bid_price_{levels}"))
            .unwrap();
        values[last_bid] = "0.00001".into();
        fs::write(&path, csv(&values)).unwrap();
        assert_eq!(
            TableReader::open(&path, Kind::Events, levels, 1)
                .unwrap()
                .next_event()
                .unwrap_err()
                .code,
            ErrorCode::Malformed
        );
    }
}

#[test]
fn csv_gzip_ties_signs_levels_and_eof() {
    let dir = tempfile::tempdir().unwrap();
    let q = dir.path().join("quality.csv.gz");
    let mut gz = GzEncoder::new(File::create(&q).unwrap(), Compression::default());
    gz.write_all(QUALITY.as_bytes()).unwrap();
    gz.finish().unwrap();
    let mut r = TableReader::open(&q, Kind::Quality, 1, 1).unwrap();
    let first = r.next_quality().unwrap().unwrap();
    let second = r.next_quality().unwrap().unwrap();
    assert!(!first.accepted);
    assert!(second.accepted);
    assert_eq!(first.timestamp, second.timestamp);
    assert!(r.next_quality().unwrap().is_none());
    let e = dir.path().join("event.csv");
    fs::write(&e, EVENT).unwrap();
    assert_eq!(
        TableReader::open(&e, Kind::Events, 2, 1)
            .err()
            .unwrap()
            .code,
        ErrorCode::Schema
    );
    let mut r = TableReader::open(&e, Kind::Events, 1, 1).unwrap();
    let event = r.next_event().unwrap().unwrap();
    assert_eq!(event.book.mid_units_twice(), 20100);
    assert!(!event.prev_available);
    assert!(event.l1_update);
    assert_eq!(event.segment, 1);
    assert!(r.next_event().unwrap().is_none());
    let t = dir.path().join("trade.csv");
    fs::write(&t, TRADE).unwrap();
    let mut r = TableReader::open(&t, Kind::Trades, 1, 1).unwrap();
    let trade = r.next_trade().unwrap().unwrap();
    assert_eq!(trade.direction, -1);
    assert!(!trade.quote_accepted);
    assert!(r.next_trade().unwrap().is_none());
}

#[test]
fn schema_nulls_and_parquet_batches() {
    let dir = tempfile::tempdir().unwrap();
    let p = dir.path().join("q.parquet");
    let schema = Arc::new(Schema::new(vec![
        Field::new("symbol", DataType::Utf8, false),
        Field::new("event_id", DataType::Int64, false),
        Field::new(
            "timestamp",
            DataType::Timestamp(TimeUnit::Nanosecond, Some("UTC".into())),
            false,
        ),
        Field::new("time_ns", DataType::Int64, false),
        Field::new("quote_accepted", DataType::Boolean, false),
        Field::new("reject_reason", DataType::Utf8, true),
    ]));
    let arrays: Vec<ArrayRef> = vec![
        Arc::new(StringArray::from(vec!["A", "A"])),
        Arc::new(Int64Array::from(vec![0, 1])),
        Arc::new(
            TimestampNanosecondArray::from(vec![1_340_285_400_000_000_001; 2]).with_timezone("UTC"),
        ),
        Arc::new(Int64Array::from(vec![34_200_000_000_001; 2])),
        Arc::new(BooleanArray::from(vec![true, true])),
        Arc::new(StringArray::from(vec![Some(""), None])),
    ];
    let batch = RecordBatch::try_new(schema.clone(), arrays).unwrap();
    let mut w = ArrowWriter::try_new(File::create(&p).unwrap(), schema, None).unwrap();
    w.write(&batch).unwrap();
    w.close().unwrap();
    let mut r = TableReader::open(&p, Kind::Quality, 1, 1).unwrap();
    assert!(r.next_quality().unwrap().unwrap().accepted);
    assert_eq!(r.next_quality().unwrap_err().code, ErrorCode::Malformed);
    assert_eq!(
        TableReader::open(&p, Kind::Events, 1, 1)
            .err()
            .unwrap()
            .code,
        ErrorCode::Schema
    );
    let wrong = dir.path().join("bad.parquet");
    let schema = Arc::new(Schema::new(vec![Field::new(
        "symbol",
        DataType::Int64,
        false,
    )]));
    let w = ArrowWriter::try_new(File::create(&wrong).unwrap(), schema, None).unwrap();
    w.close().unwrap();
    assert_eq!(
        TableReader::open(&wrong, Kind::Quality, 1, 1)
            .err()
            .unwrap()
            .code,
        ErrorCode::Schema
    );
}

#[test]
fn malformed_missing_inconsistent_and_order_failures() {
    let dir = tempfile::tempdir().unwrap();
    let p = dir.path().join("test.csv");
    for (input, kind) in [
        (
            QUALITY.replace("False,spread_above_p95", "False,"),
            Kind::Quality,
        ),
        (QUALITY.replace("A,1,", "A,0,"), Kind::Quality),
        (QUALITY.replace("A,1,", "A,3,"), Kind::Quality),
        (
            QUALITY.replace("34200000000001", "34200000000002"),
            Kind::Quality,
        ),
        (QUALITY.replace("True,", "unknown,"), Kind::Quality),
        (
            EVENT.replace(",1,False,True", ",0,False,True"),
            Kind::Events,
        ),
        (EVENT.replace(",100,120", ",0,120"), Kind::Events),
        (TRADE.replace(",False,1,10", ",False,-1,10"), Kind::Trades),
        (TRADE.replace(",False,1,10", ",False,1,-10"), Kind::Trades),
        (TRADE.replace(",4,10,", ",1,10,"), Kind::Trades),
        (EVENT.replace(",1,1.01,", ",0.00001,1.01,"), Kind::Events),
    ] {
        fs::write(&p, input).unwrap();
        let mut r = TableReader::open(&p, kind, 1, 1).unwrap();
        let mut failed = false;
        for _ in 0..3 {
            let result = match kind {
                Kind::Events => r.next_event().map(|x| x.is_some()),
                Kind::Trades => r.next_trade().map(|x| x.is_some()),
                Kind::Quality => r.next_quality().map(|x| x.is_some()),
            };
            if result.is_err() {
                failed = true;
                break;
            }
        }
        assert!(failed);
    }
    fs::write(&p, "symbol,symbol\nA,A\n").unwrap();
    assert!(TableReader::open(&p, Kind::Quality, 1, 1).is_err());
    fs::write(&p, QUALITY.replace("A,1,2012", "A,1")).unwrap();
    let mut r = TableReader::open(&p, Kind::Quality, 1, 1).unwrap();
    r.next_quality().unwrap();
    assert!(r.next_quality().is_err());
    fs::write(&p, QUALITY.replace("A,0,", "A,not_integer,")).unwrap();
    assert!(TableReader::open(&p, Kind::Quality, 1, 0).is_err());
    assert!(TableReader::open(&p, Kind::Quality, 0, 1).is_err());
    assert!(
        TableReader::open(&p, Kind::Quality, 1, 1)
            .unwrap()
            .next_quality()
            .is_err()
    );
    assert_eq!(
        TableReader::open(&dir.path().join("missing.csv"), Kind::Quality, 1, 1)
            .err()
            .unwrap()
            .code,
        ErrorCode::MissingFile
    );
    let bad = dir.path().join("bad.parquet");
    fs::write(&bad, "not parquet").unwrap();
    assert!(TableReader::open(&bad, Kind::Quality, 1, 1).is_err());
    let bad = dir.path().join("bad.txt");
    fs::write(&bad, QUALITY).unwrap();
    assert!(TableReader::open(&bad, Kind::Quality, 1, 1).is_err());
    let bad = dir.path().join("bad.csv.gz");
    fs::write(&bad, "invalid gzip").unwrap();
    assert!(TableReader::open(&bad, Kind::Quality, 1, 1).is_err());
}

// Authored rows exercise column mapping and row/batch validation, not market data.
fn event_batch(levels: usize) -> RecordBatch {
    let mut columns: Vec<(&str, ArrayRef)> = vec![
        ("symbol", Arc::new(StringArray::from(vec!["A"; 5]))),
        ("date", Arc::new(StringArray::from(vec!["2012-06-21"; 5]))),
        ("event_id", Arc::new(Int64Array::from(vec![0, 1, 2, 3, 4]))),
        (
            "timestamp",
            Arc::new(
                TimestampNanosecondArray::from(vec![1_340_285_400_000_000_001; 5])
                    .with_timezone("UTC"),
            ),
        ),
        (
            "time_ns",
            Arc::new(Int64Array::from(vec![34_200_000_000_001; 5])),
        ),
        ("segment_id", Arc::new(Int64Array::from(vec![1; 5]))),
        (
            "prev_state_available",
            Arc::new(BooleanArray::from(vec![false, true, true, true, true])),
        ),
        (
            "is_quote_update",
            Arc::new(BooleanArray::from(vec![true; 5])),
        ),
        ("event_type", Arc::new(Int64Array::from(vec![4; 5]))),
        ("event_size", Arc::new(Int64Array::from(vec![10; 5]))),
        ("event_price", Arc::new(Float64Array::from(vec![1.01; 5]))),
        ("direction", Arc::new(Int64Array::from(vec![-1; 5]))),
        (
            "quote_accepted",
            Arc::new(BooleanArray::from(vec![true; 5])),
        ),
        ("reject_reason", Arc::new(StringArray::from(vec![""; 5]))),
    ];
    let mut names = Vec::new();
    let mut arrays = Vec::new();
    for level in 1..=levels {
        names.extend([
            format!("bid_price_{level}"),
            format!("ask_price_{level}"),
            format!("bid_size_{level}"),
            format!("ask_size_{level}"),
        ]);
        arrays.extend([
            Arc::new(Float64Array::from(vec![1.0 - (level - 1) as f64 * 0.01; 5])) as ArrayRef,
            Arc::new(Float64Array::from(vec![
                1.01 + (level - 1) as f64 * 0.01;
                5
            ])),
            Arc::new(Int64Array::from(vec![100 + level as i64; 5])),
            Arc::new(Int64Array::from(vec![120 + level as i64; 5])),
        ]);
    }
    columns.extend(names.iter().map(String::as_str).zip(arrays));
    columns.reverse();
    let schema = Arc::new(Schema::new(
        columns
            .iter()
            .map(|(name, array)| Field::new(*name, array.data_type().clone(), true))
            .collect::<Vec<_>>(),
    ));
    RecordBatch::try_new(
        schema,
        columns.into_iter().map(|(_, array)| array).collect(),
    )
    .unwrap()
}

fn with_column(batch: &RecordBatch, name: &str, array: ArrayRef) -> RecordBatch {
    let mut fields = batch.schema().fields().to_vec();
    let mut arrays = batch.columns().to_vec();
    let field = Arc::new(Field::new(name, array.data_type().clone(), true));
    if let Ok(index) = batch.schema().index_of(name) {
        fields[index] = field;
        arrays[index] = array;
    } else {
        fields.push(field);
        arrays.push(array);
    }
    RecordBatch::try_new(Arc::new(Schema::new(fields)), arrays).unwrap()
}

fn write_batch(path: &std::path::Path, batch: &RecordBatch) {
    let properties = parquet::file::properties::WriterProperties::builder()
        .set_max_row_group_row_count(Some(2))
        .build();
    let mut writer = ArrowWriter::try_new(
        File::create(path).unwrap(),
        batch.schema(),
        Some(properties),
    )
    .unwrap();
    writer.write(batch).unwrap();
    writer.close().unwrap();
}

#[test]
fn parquet_column_mapping_survives_all_depths_batches_and_row_groups() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("events.parquet");
    for levels in 1..=5 {
        let batch = event_batch(levels);
        // Unrequested deeper columns remain irrelevant even with another dtype.
        let batch = if levels < 5 {
            with_column(
                &batch,
                "bid_price_5",
                Arc::new(StringArray::from(vec!["ignored"; 5])),
            )
        } else {
            batch
        };
        write_batch(&path, &batch);
        for chunk in [1, 2, 4, 8] {
            let mut reader = TableReader::open(&path, Kind::Events, levels, chunk).unwrap();
            for id in 0..5 {
                let event = reader.next_event().unwrap().unwrap();
                assert_eq!(event.key.event_id, id);
                assert_eq!(event.book.0.len(), levels);
                for (rank, level) in event.book.0.iter().enumerate() {
                    assert_eq!(level.bid, 10000 - rank as i64 * 100);
                    assert_eq!(level.ask, 10100 + rank as i64 * 100);
                    assert_eq!(level.bid_size, 101 + rank as i64);
                    assert_eq!(level.ask_size, 121 + rank as i64);
                }
                assert_eq!(event.execution.unwrap().direction, -1);
            }
            assert!(reader.next_event().unwrap().is_none());
            // Methods retain their historical lack of Kind enforcement.
            let mut reader = TableReader::open(&path, Kind::Events, levels, chunk).unwrap();
            assert!(reader.next_quality().unwrap().unwrap().accepted);
            let mut reader = TableReader::open(&path, Kind::Events, levels, chunk).unwrap();
            assert_eq!(reader.next_trade().unwrap().unwrap().size, 10);
        }
    }
}

#[test]
fn indexed_optional_fields_preserve_lazy_types_nulls_and_error_precedence() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("optional.parquet");
    let base = event_batch(1);
    for (name, expected) in [
        ("timestamp_subnanosecond_rounded", "requires bool"),
        ("time_seconds_text", "requires UTF8 string"),
        ("event_price_raw", "requires int64"),
    ] {
        let wrong: ArrayRef = if name == "event_price_raw" {
            Arc::new(Float64Array::from(vec![1.01; 5]))
        } else {
            Arc::new(Int64Array::from(vec![0; 5]))
        };
        let batch = with_column(&base, name, wrong);
        write_batch(&path, &batch);
        let mut reader = TableReader::open(&path, Kind::Events, 1, 2).unwrap();
        let error = reader.next_event().unwrap_err();
        assert_eq!(error.code, ErrorCode::Schema);
        assert!(
            error.message.contains(&format!("row 1: {name} {expected}")),
            "{}",
            error.message
        );
        // A null is rejected before its optional dtype is inspected.
        let batch = with_column(
            &base,
            name,
            Arc::new(StringArray::from(vec![None::<&str>; 5])),
        );
        write_batch(&path, &batch);
        let mut reader = TableReader::open(&path, Kind::Events, 1, 2).unwrap();
        let error = reader.next_event().unwrap_err();
        assert_eq!(error.code, ErrorCode::Malformed);
        assert!(
            error
                .message
                .contains(&format!("row 1: null required value {name}"))
        );
        // Parsing errors consume the row; the next attempt carries the next row number.
        assert!(reader.next_event().unwrap_err().message.contains("row 2:"));
        let batch = with_column(&batch, "segment_id", Arc::new(Int64Array::from(vec![0; 5])));
        write_batch(&path, &batch);
        let error = TableReader::open(&path, Kind::Events, 1, 2)
            .unwrap()
            .next_event()
            .unwrap_err();
        assert!(
            error
                .message
                .contains("accepted segment_id must be positive")
        );
    }
    // Optional supplied sign types are validated at open for every Kind.
    for name in ["aggressor_side", "signed_volume"] {
        let batch = with_column(&base, name, Arc::new(Float64Array::from(vec![1.0; 5])));
        write_batch(&path, &batch);
        for kind in [Kind::Events, Kind::Trades, Kind::Quality] {
            let error = TableReader::open(&path, kind, 1, 1).err().unwrap();
            assert_eq!(error.code, ErrorCode::Schema);
            assert_eq!(error.message, format!("{name} requires int64"));
        }
    }
    let batch = with_column(
        &base,
        "aggressor_side",
        Arc::new(Int64Array::from(vec![-1; 5])),
    );
    let batch = with_column(
        &batch,
        "signed_volume",
        Arc::new(Int64Array::from(vec![None; 5])),
    );
    write_batch(&path, &batch);
    let error = TableReader::open(&path, Kind::Trades, 1, 1)
        .unwrap()
        .next_trade()
        .unwrap_err();
    assert!(error.message.contains("inconsistent supplied trade sign"));
    // Trade validation runs before either supplied sign is accessed.
    let batch = with_column(&batch, "event_size", Arc::new(Int64Array::from(vec![0; 5])));
    write_batch(&path, &batch);
    let error = TableReader::open(&path, Kind::Trades, 1, 1)
        .unwrap()
        .next_trade()
        .unwrap_err();
    assert!(error.message.contains("invalid execution"));
}
