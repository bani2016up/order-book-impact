//! Original paired rows for Quote Test. ZIP payloads spool to owned temporary files.
use crate::{
    domain::{Book, Key, Level, Quality, Trade},
    error::{Error, ErrorCode, Result, checked_i64},
    time::{decimal_seconds_ns, local_timestamp},
};
use serde::{Deserialize, Serialize};
use std::{
    fs::File,
    io::{BufReader, Write},
    path::{Path, PathBuf},
};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RawInput {
    pub symbol: String,
    pub date: String,
    pub archive: Option<PathBuf>,
    pub message: Option<PathBuf>,
    pub orderbook: Option<PathBuf>,
}
impl RawInput {
    pub fn paths(&self) -> Result<Vec<&Path>> {
        match (&self.archive, &self.message, &self.orderbook) {
            (Some(archive), None, None) => Ok(vec![archive]),
            (None, Some(message), Some(book)) => Ok(vec![message, book]),
            _ => Err(Error::new(
                ErrorCode::Config,
                "raw input needs exactly archive or paired message/orderbook paths",
            )),
        }
    }
}

pub struct RawRow {
    pub key: Key,
    pub timestamp: i64,
    pub book: Option<Book>,
    pub event_type: i64,
    pub size: i64,
    pub price: i64,
    pub direction: i64,
    pub rounded: bool,
}
pub struct RawReader {
    messages: csv::Reader<BufReader<File>>,
    books: csv::Reader<BufReader<File>>,
    message_record: csv::StringRecord,
    book_record: csv::StringRecord,
    input: RawInput,
    next_id: i64,
    midnight: i64,
    previous: Option<Book>,
    _spool: Option<tempfile::TempDir>,
}
fn malformed(error: impl std::fmt::Display) -> Error {
    Error::new(ErrorCode::Malformed, error.to_string())
}
fn integer(record: &csv::StringRecord, index: usize) -> Result<i64> {
    record
        .get(index)
        .ok_or_else(|| malformed("missing raw field"))?
        .parse()
        .map_err(malformed)
}
impl RawReader {
    pub fn open(input: &RawInput, temporary_parent: &Path) -> Result<Self> {
        input.paths()?;
        let midnight = local_timestamp(&input.date, "00:00:00")?;
        let (message, orderbook, spool) = if let Some(archive) = &input.archive {
            let mut archive = zip::ZipArchive::new(File::open(archive)?).map_err(malformed)?;
            let names: Vec<String> = archive.file_names().map(str::to_owned).collect();
            let messages: Vec<_> = names
                .iter()
                .filter(|n| n.contains("_message_") && n.ends_with(".csv"))
                .collect();
            let books: Vec<_> = names
                .iter()
                .filter(|n| n.contains("_orderbook_") && n.ends_with(".csv"))
                .collect();
            if messages.len() != 1 || books.len() != 1 {
                return Err(Error::new(
                    ErrorCode::Schema,
                    "ZIP requires exactly one message and one orderbook CSV",
                ));
            }
            let spool = tempfile::Builder::new()
                .prefix(".raw-pair-")
                .tempdir_in(temporary_parent)?;
            let message = spool.path().join("message.csv");
            let orderbook = spool.path().join("orderbook.csv");
            for (name, path) in [(messages[0], &message), (books[0], &orderbook)] {
                let mut source = archive.by_name(name).map_err(malformed)?;
                let mut target = File::create(path)?;
                std::io::copy(&mut source, &mut target)?;
                target.flush()?;
            }
            (message, orderbook, Some(spool))
        } else {
            (
                input.message.clone().expect("validated pair"),
                input.orderbook.clone().expect("validated pair"),
                None,
            )
        };
        let reader = |path| -> Result<_> {
            Ok(csv::ReaderBuilder::new()
                .has_headers(false)
                .from_reader(BufReader::new(File::open(path)?)))
        };
        Ok(Self {
            messages: reader(message)?,
            books: reader(orderbook)?,
            message_record: csv::StringRecord::new(),
            book_record: csv::StringRecord::new(),
            input: input.clone(),
            next_id: 0,
            midnight,
            previous: None,
            _spool: spool,
        })
    }
    fn next(&mut self) -> Result<Option<RawRow>> {
        let has_m = self
            .messages
            .read_record(&mut self.message_record)
            .map_err(malformed)?;
        let has_b = self
            .books
            .read_record(&mut self.book_record)
            .map_err(malformed)?;
        let m = &self.message_record;
        let b = &self.book_record;
        if has_m != has_b {
            return Err(Error::new(
                ErrorCode::Quality,
                format!(
                    "raw message/orderbook row count mismatch for {} after row {}",
                    self.input.symbol, self.next_id
                ),
            ));
        }
        if !has_m {
            return Ok(None);
        }
        if m.len() != 6 || b.is_empty() || !b.len().is_multiple_of(4) || b.len() > 20 {
            return Err(Error::new(
                ErrorCode::Schema,
                "raw messages require six fields; book requires 1..5 four-column levels",
            ));
        }
        let (ns, rounded) = decimal_seconds_ns(m.get(0).expect("six message fields"))?;
        let timestamp = checked_i64(
            i128::from(self.midnight) + i128::from(ns),
            "raw UTC timestamp overflow",
        )?;
        let depth = b.len() / 4;
        let mut book = Vec::with_capacity(depth);
        for i in 0..depth {
            book.push(Level {
                ask: integer(b, i * 4)?,
                ask_size: integer(b, i * 4 + 1)?,
                bid: integer(b, i * 4 + 2)?,
                bid_size: integer(b, i * 4 + 3)?,
            });
        }
        let book = Book(book);
        let book = book.validate().ok().map(|()| book);
        let row = RawRow {
            key: Key {
                symbol: self.input.symbol.clone(),
                date: self.input.date.clone(),
                event_id: self.next_id,
            },
            timestamp,
            book,
            event_type: integer(m, 1)?,
            size: integer(m, 3)?,
            price: integer(m, 4)?,
            direction: integer(m, 5)?,
            rounded,
        };
        self.next_id = self
            .next_id
            .checked_add(1)
            .ok_or_else(|| Error::new(ErrorCode::Overflow, "raw event ID overflow"))?;
        Ok(Some(row))
    }
    pub fn observe(&mut self, q: &Quality) -> Result<(RawRow, Option<Book>)> {
        let row = self.next()?.ok_or_else(|| {
            Error::new(
                ErrorCode::Quality,
                "raw paired files ended before quality evidence",
            )
        })?;
        if row.key != q.key || row.timestamp != q.timestamp {
            return Err(Error::new(
                ErrorCode::Quality,
                format!("raw row/quality time or ID mismatch at {:?}", q.key),
            ));
        }
        let previous = self.previous.take();
        self.previous = row.book.clone();
        Ok((row, previous))
    }
    pub fn finish(&mut self) -> Result<()> {
        if self.next()?.is_some() {
            return Err(Error::new(
                ErrorCode::Quality,
                "raw rows remain after quality evidence ended",
            ));
        }
        Ok(())
    }
}

pub fn quote_test(trade: &Trade, row: &RawRow, pre: Option<&Book>) -> Result<Option<i64>> {
    trade.validate()?;
    if trade.key != row.key
        || trade.timestamp != row.timestamp
        || trade.event_type != row.event_type
        || trade.size != row.size
        || trade.price != row.price
        || trade.direction != row.direction
    {
        return Err(Error::new(
            ErrorCode::Quality,
            format!("execution differs from paired raw row {:?}", trade.key),
        ));
    }
    let Some(book) = pre else {
        return Ok(None);
    };
    book.validate()?;
    let l = book.0[0];
    Ok(if trade.price >= l.ask {
        Some(1)
    } else if trade.price <= l.bid {
        Some(-1)
    } else {
        None
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    fn q(id: i64, ns: i64) -> Quality {
        Quality {
            key: Key {
                symbol: "A".into(),
                date: "2012-06-21".into(),
                event_id: id,
            },
            timestamp: 1_340_285_400_000_000_000 + ns,
            accepted: false,
            reason: "spread".into(),
        }
    }
    fn input(dir: &Path) -> RawInput {
        RawInput {
            symbol: "A".into(),
            date: "2012-06-21".into(),
            archive: None,
            message: Some(dir.join("m.csv")),
            orderbook: Some(dir.join("b.csv")),
        }
    }
    #[test]
    fn paired_prestate_ties_inside_spread_and_end_alignment() {
        let dir = tempfile::tempdir().unwrap();
        let input = input(dir.path());
        fs::write(input.message.as_ref().unwrap(),"34200.000000001,1,1,1,10000,1\n34200.000000001,4,2,7,10100,-1\n34200.000000002,5,0,9,10200,1\n").unwrap();
        fs::write(
            input.orderbook.as_ref().unwrap(),
            "10100,120,10000,100\n10300,120,10100,100\n10300,120,10100,100\n",
        )
        .unwrap();
        let mut r = RawReader::open(&input, dir.path()).unwrap();
        let (_, pre) = r.observe(&q(0, 1)).unwrap();
        assert!(pre.is_none());
        let (row, pre) = r.observe(&q(1, 1)).unwrap();
        let t = Trade {
            key: row.key.clone(),
            timestamp: row.timestamp,
            size: 7,
            price: 10100,
            direction: -1,
            event_type: 4,
            quote_accepted: false,
        };
        assert_eq!(quote_test(&t, &row, pre.as_ref()).unwrap(), Some(1));
        assert_eq!(quote_test(&t, &row, row.book.as_ref()).unwrap(), Some(-1));
        assert_eq!(quote_test(&t, &row, None).unwrap(), None);
        assert!(quote_test(&Trade { size: 8, ..t }, &row, pre.as_ref()).is_err());
        let (row, pre) = r.observe(&q(2, 2)).unwrap();
        let t = Trade {
            key: row.key.clone(),
            timestamp: row.timestamp,
            size: 9,
            price: 10200,
            direction: 1,
            event_type: 5,
            quote_accepted: false,
        };
        assert_eq!(quote_test(&t, &row, pre.as_ref()).unwrap(), None);
        r.finish().unwrap();
        assert!(r.observe(&q(3, 3)).is_err());
    }
    #[test]
    fn raw_schema_and_quality_failures() {
        let dir = tempfile::tempdir().unwrap();
        let input = input(dir.path());
        assert!(
            RawReader::open(
                &RawInput {
                    archive: Some(dir.path().into()),
                    ..input.clone()
                },
                dir.path()
            )
            .is_err()
        );
        for (m, b) in [
            ("34200,1,1,1,10000,1\n", ""),
            ("34200,1,1,1,10000\n", "10100,120,10000,100\n"),
            ("bad,1,1,1,10000,1\n", "10100,120,10000,100\n"),
            ("34200,1,1,1,10000,1\n", "10100,120,10000\n"),
        ] {
            fs::write(input.message.as_ref().unwrap(), m).unwrap();
            fs::write(input.orderbook.as_ref().unwrap(), b).unwrap();
            let mut r = RawReader::open(&input, dir.path()).unwrap();
            assert!(r.observe(&q(0, 0)).is_err());
        }
        fs::write(input.message.as_ref().unwrap(), "34200,1,1,1,10000,1\n").unwrap();
        fs::write(input.orderbook.as_ref().unwrap(), "0,0,0,0\n").unwrap();
        let mut r = RawReader::open(&input, dir.path()).unwrap();
        assert!(r.observe(&q(0, 1)).is_err());
        let mut r = RawReader::open(&input, dir.path()).unwrap();
        let (row, _) = r.observe(&q(0, 0)).unwrap();
        assert!(row.book.is_none());
        let mut r = RawReader::open(&input, dir.path()).unwrap();
        assert!(r.finish().is_err());
    }
    #[test]
    fn reused_raw_records_keep_invalid_gaps_and_owned_books_at_every_depth() {
        let directory = tempfile::tempdir().unwrap();
        let input = input(directory.path());
        for depth in 1..=5 {
            fs::write(input.message.as_ref().unwrap(),
                "34200,1,1,1,10000,1\n34200.000000001,4,12345678901234567890,10,10100,-1\n34200.000000002,5,0,999,10050,1\n34200.000000003,1,2,1,10000,1\n").unwrap();
            let mut books = String::new();
            for id in 0..4 {
                let mut fields = Vec::new();
                for rank in 0..depth {
                    fields.extend([
                        if id == 1 {
                            "0".into()
                        } else {
                            (10100 + rank * 100).to_string()
                        },
                        "120".into(),
                        (10000 - rank * 100).to_string(),
                        (100 + id).to_string(),
                    ]);
                }
                books.push_str(&fields.join(","));
                books.push('\n');
            }
            fs::write(input.orderbook.as_ref().unwrap(), books).unwrap();
            let mut reader = RawReader::open(&input, directory.path()).unwrap();
            let (mut first, previous) = reader.observe(&q(0, 0)).unwrap();
            assert!(previous.is_none());
            assert_eq!(first.book.as_ref().unwrap().0.len(), depth);
            first.book.as_mut().unwrap().0[0].bid_size = 9999;
            let (invalid, mut previous) = reader.observe(&q(1, 1)).unwrap();
            assert!(invalid.book.is_none());
            assert_eq!(previous.as_ref().unwrap().0[0].bid_size, 100);
            previous.as_mut().unwrap().0[0].bid_size = 8888;
            let (mut third, previous) = reader.observe(&q(2, 2)).unwrap();
            assert!(previous.is_none());
            assert_eq!(third.size, 999);
            assert_eq!(third.book.as_ref().unwrap().0[0].bid_size, 102);
            third.book.as_mut().unwrap().0[0].bid_size = 7777;
            let (fourth, previous) = reader.observe(&q(3, 3)).unwrap();
            assert_eq!(previous.as_ref().unwrap().0[0].bid_size, 102);
            assert_eq!(fourth.book.as_ref().unwrap().0[0].bid_size, 103);
            assert_eq!(first.book.unwrap().0[0].bid_size, 9999);
            assert_eq!(third.book.unwrap().0[0].bid_size, 7777);
            reader.finish().unwrap();
        }
    }

    #[test]
    fn raw_record_reuse_preserves_alignment_and_parse_failure_consumption() {
        let directory = tempfile::tempdir().unwrap();
        let input = input(directory.path());
        fs::write(
            input.message.as_ref().unwrap(),
            "34200,1,1,1,10000,1\n34200.000000001,1,1,1,10000,1\n34200.000000002,1,1,1,10000,1\n",
        )
        .unwrap();
        fs::write(
            input.orderbook.as_ref().unwrap(),
            "10100,120,10000,100\n10100,120,10000,130\n10100,120,10000,160\n",
        )
        .unwrap();
        let mut reader = RawReader::open(&input, directory.path()).unwrap();
        reader.observe(&q(0, 0)).unwrap();
        assert_eq!(
            reader.observe(&q(1, 9)).err().unwrap().code,
            ErrorCode::Quality
        );
        let (row, prior) = reader.observe(&q(2, 2)).unwrap();
        assert_eq!(row.book.unwrap().0[0].bid_size, 160);
        // Alignment failure consumes its row without publishing its post-book.
        assert_eq!(prior.unwrap().0[0].bid_size, 100);
        reader.finish().unwrap();

        fs::write(input.message.as_ref().unwrap(),
            "34200,1,1,1,10000,1\n34200.000000001,1,1,bad_size,10000,1\n34200.000000002,1,1,1,10000,1\n").unwrap();
        let mut reader = RawReader::open(&input, directory.path()).unwrap();
        reader.observe(&q(0, 0)).unwrap();
        assert_eq!(
            reader.observe(&q(1, 1)).err().unwrap().code,
            ErrorCode::Malformed
        );
        // Field-conversion failure consumes both records but does not increment ID.
        let (row, prior) = reader.observe(&q(1, 2)).unwrap();
        assert_eq!(row.book.unwrap().0[0].bid_size, 160);
        assert_eq!(prior.unwrap().0[0].bid_size, 100);
        reader.finish().unwrap();

        for (messages, books) in [
            (
                "34200,1,1,1,10000,1\n34200.000000001,1,1,1,10000\n",
                "10100,120,10000,100\n10100,120,10000,130\n",
            ),
            (
                "34200,1,1,1,10000,1\n34200.000000001,1,1,1,10000,1\n",
                "10100,120,10000,100\n10100,120,10000,130,10200,120,9900,100\n",
            ),
        ] {
            fs::write(input.message.as_ref().unwrap(), messages).unwrap();
            fs::write(input.orderbook.as_ref().unwrap(), books).unwrap();
            let mut reader = RawReader::open(&input, directory.path()).unwrap();
            reader.observe(&q(0, 0)).unwrap();
            // CSV's existing fixed field-count enforcement remains in force.
            assert_eq!(
                reader.observe(&q(1, 1)).err().unwrap().code,
                ErrorCode::Malformed
            );
            assert_eq!(reader.previous.as_ref().unwrap().0[0].bid_size, 100);
            assert_eq!(reader.next_id, 1);
        }
    }
    #[test]
    fn raw_utc_addition_overflow_is_reported() {
        let dir = tempfile::tempdir().unwrap();
        let input = input(dir.path());
        fs::write(
            input.message.as_ref().unwrap(),
            "9223372036.854775807,1,1,1,10000,1\n",
        )
        .unwrap();
        fs::write(input.orderbook.as_ref().unwrap(), "10100,120,10000,100\n").unwrap();
        let mut reader = RawReader::open(&input, dir.path()).unwrap();
        assert_eq!(
            reader.observe(&q(0, 0)).err().unwrap().code,
            ErrorCode::Overflow
        );
    }
}
