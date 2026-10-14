//! External acceptance evidence; no bundled real data in Git.
use ofi_core::adapter::{Kind, TableReader};
use std::path::Path;

#[test]
#[ignore = "requires owner-provided OFI_SAMPLE_DIR; run explicitly"]
fn delivered_sample_streams_and_counts() {
    let path = std::env::var("OFI_SAMPLE_DIR").expect("set OFI_SAMPLE_DIR to the delivered bundle");
    let root = Path::new(&path);
    let mut r = TableReader::open(
        &root.join("data/events_clean.parquet"),
        Kind::Events,
        5,
        4096,
    )
    .unwrap();
    let mut n = 0;
    while r.next_event().unwrap().is_some() {
        n += 1;
    }
    assert_eq!(n, 887810);
    let mut r = TableReader::open(
        &root.join("data/trades_clean.parquet"),
        Kind::Trades,
        5,
        4096,
    )
    .unwrap();
    let mut n = 0;
    while r.next_trade().unwrap().is_some() {
        n += 1;
    }
    assert_eq!(n, 68404);
    let mut r = TableReader::open(
        &root.join("reports/event_quality.parquet"),
        Kind::Quality,
        5,
        4096,
    )
    .unwrap();
    let (mut n, mut bad) = (0, 0);
    while let Some(q) = r.next_quality().unwrap() {
        n += 1;
        bad += u64::from(!q.accepted);
    }
    assert_eq!(n, 897387);
    assert_eq!(bad, 9577);
}
