use arrow_array::{
    ArrayRef, BooleanArray, Int64Array, RecordBatch, StringArray, TimestampNanosecondArray,
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
