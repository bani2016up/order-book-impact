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
            input: input.clone(),
            next_id: 0,
            midnight,
            previous: None,
            _spool: spool,
        })
    }
    fn next(&mut self) -> Result<Option<RawRow>> {
        let (mut m, mut b) = (csv::StringRecord::new(), csv::StringRecord::new());
        let has_m = self.messages.read_record(&mut m).map_err(malformed)?;
        let has_b = self.books.read_record(&mut b).map_err(malformed)?;
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
        if m.len() != 6 || b.is_empty() || b.len() % 4 != 0 || b.len() > 20 {
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
        let mut book = Vec::new();
        for i in 0..b.len() / 4 {
            book.push(Level {
                ask: integer(&b, i * 4)?,
                ask_size: integer(&b, i * 4 + 1)?,
                bid: integer(&b, i * 4 + 2)?,
                bid_size: integer(&b, i * 4 + 3)?,
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
            event_type: integer(&m, 1)?,
            size: integer(&m, 3)?,
            price: integer(&m, 4)?,
            direction: integer(&m, 5)?,
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
}
