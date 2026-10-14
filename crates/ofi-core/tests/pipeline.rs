use ofi_core::{
    config::Config,
    error::ErrorCode,
    pipeline::{Inputs, run},
};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use std::{fs, path::Path};

fn fixture(dir: &Path) -> Inputs {
    let quality = "symbol,event_id,timestamp,time_ns,quote_accepted,reject_reason\n";
    let events = "symbol,date,event_id,timestamp,time_ns,segment_id,prev_state_available,is_quote_update,bid_price_1,ask_price_1,bid_size_1,ask_size_1,event_type,event_size,event_price,direction\n";
    let (mut quality, mut events) = (quality.to_owned(), events.to_owned());
    for (id, sec, size, update) in [
        (0, 1, 100, true),
        (1, 10, 100, false),
        (2, 11, 130, true),
        (3, 20, 130, false),
    ] {
        let stamp = format!("2012-06-21T13:30:{sec:02}Z");
        let time = 34_200_000_000_000_i64 + i64::from(sec) * 1_000_000_000;
        quality.push_str(&format!("A,{id},{stamp},{time},True,\n"));
        let (kind, size_event, price, direction) = if id == 3 {
            (4, 7, 1.01, -1)
        } else {
            (1, 1, 1.0, 1)
        };
        events.push_str(
            &format!(
                "A,2012-06-21,{id},{stamp},{time},1,{},{} ,1,1.01,{size},120,{kind},{size_event},{price},{direction}\n",
                id > 0,
                update
            )
            .replace("true ", "true")
            .replace("false ", "false"),
        );
    }
    let inputs = Inputs {
        events: dir.join("e.csv"),
        trades: dir.join("t.csv"),
        quality: dir.join("q.csv"),
        raw: vec![],
    };
    fs::write(&inputs.events, events).unwrap();
    fs::write(&inputs.quality, quality).unwrap();
    fs::write(&inputs.trades,"symbol,date,event_id,timestamp,time_ns,event_type,event_size,event_price,direction,quote_accepted\nA,2012-06-21,3,2012-06-21T13:30:20Z,34220000000000,4,7,1.01,-1,True\n").unwrap();
    inputs
}
fn config() -> Config {
    Config {
        levels: 1,
        threads: 1,
        chunk_rows: 1,
        session_close: "09:30:30".into(),
        ..Config::default()
    }
}

#[test]
fn core_file_set_output_and_owned_overwrite() {
    let dir = tempfile::tempdir().unwrap();
    let inputs = fixture(dir.path());
    let output = dir.path().join("results");
    let report = run(inputs.clone(), output.clone(), config()).unwrap();
    assert_eq!(report.partitions[0].feature_rows, 2);
    assert_eq!(report.partitions[0].signing.volume, 7);
    assert!(report.warnings.iter().any(|w| w.contains("rounding flags")));
    let reader =
        ParquetRecordBatchReaderBuilder::try_new(fs::File::open(&report.features_path).unwrap())
            .unwrap();
    assert_eq!(reader.metadata().file_metadata().num_rows(), 2);
    assert_eq!(
        reader
            .schema()
            .field_with_name("ofi_l1")
            .unwrap()
            .data_type(),
        &arrow_schema::DataType::Int64
    );
    // Release the Parquet file handle before replacing/removing its directory on Windows.
    drop(reader);
    assert_eq!(
        run(inputs.clone(), output.clone(), config())
            .unwrap_err()
            .code,
        ErrorCode::Io
    );
    let c = Config {
        overwrite: true,
        ..config()
    };
    let rewritten = run(inputs.clone(), output.clone(), c.clone()).unwrap();
    {
        let reader = ParquetRecordBatchReaderBuilder::try_new(
            fs::File::open(&rewritten.features_path).unwrap(),
        )
        .unwrap();
        assert_eq!(reader.metadata().file_metadata().num_rows(), 2);
    }
    assert!(!fs::read_dir(dir.path()).unwrap().any(|entry| {
        let name = entry.unwrap().file_name();
        let name = name.to_string_lossy();
        name.starts_with(".ofi-stage-") || name.starts_with(".ofi-backup-")
    }));
    fs::write(output.join("mine.txt"), "keep").unwrap();
    assert!(run(inputs.clone(), output.clone(), c.clone()).is_err());
    assert_eq!(fs::read_to_string(output.join("mine.txt")).unwrap(), "keep");
    assert_eq!(
        run(inputs.clone(), dir.path().into(), c).unwrap_err().code,
        ErrorCode::Config
    );
}

#[test]
fn failed_computation_does_not_publish() {
    let dir = tempfile::tempdir().unwrap();
    let inputs = fixture(dir.path());
    let source = fs::read_to_string(&inputs.events).unwrap();
    fs::write(
        &inputs.events,
        source.replace("A,2012-06-21,2,", "A,2012-06-21,4,"),
    )
    .unwrap();
    let output = dir.path().join("failed");
    assert!(run(inputs, output.clone(), config()).is_err());
    assert!(!output.exists());
    assert!(!fs::read_dir(dir.path()).unwrap().any(|e| {
        e.unwrap()
            .file_name()
            .to_string_lossy()
            .starts_with(".ofi-stage-")
    }));
}
