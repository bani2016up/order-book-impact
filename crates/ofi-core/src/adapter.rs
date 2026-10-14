//! Bounded Lev-v1 Parquet and headered gzip CSV readers.
use crate::{
    domain::{Book, Event, Key, Level, OrderGuard, Quality, Trade, price_units},
    error::{Error, ErrorCode, Result},
    time::{LocalTimeValidator, decimal_seconds_ns, timestamp_from_text},
};
use arrow_array::{
    Array, BooleanArray, Float64Array, Int64Array, RecordBatch, StringArray,
    TimestampNanosecondArray,
};
use arrow_schema::{DataType, TimeUnit};
use flate2::read::GzDecoder;
use parquet::arrow::arrow_reader::{ParquetRecordBatchReader, ParquetRecordBatchReaderBuilder};
use std::{
    collections::HashMap,
    fs::File,
    io::{BufReader, Read},
    path::{Path, PathBuf},
};

#[derive(Clone, Copy, Debug)]
pub enum Kind {
    Events,
    Trades,
    Quality,
}

enum Source {
    Parquet {
        reader: Box<ParquetRecordBatchReader>,
        batch: Option<RecordBatch>,
        offset: usize,
    },
    Csv {
        reader: csv::Reader<Box<dyn Read + Send>>,
        record: csv::StringRecord,
    },
}

pub struct TableReader {
    source: Source,
    columns: HashMap<String, usize>,
    path: PathBuf,
    rows: u64,
    order: OrderGuard,
    levels: usize,
    local_time: LocalTimeValidator,
}

pub enum Row<'a> {
    Parquet(&'a RecordBatch, usize, &'a HashMap<String, usize>),
    Csv(&'a csv::StringRecord, &'a HashMap<String, usize>),
}

fn schema(message: impl Into<String>) -> Error {
    Error::new(ErrorCode::Schema, message)
}
fn malformed(error: impl std::fmt::Display) -> Error {
    Error::new(ErrorCode::Malformed, error.to_string())
}

const BOOK_COLUMNS: [[&str; 4]; 5] = [
    ["bid_price_1", "ask_price_1", "bid_size_1", "ask_size_1"],
    ["bid_price_2", "ask_price_2", "bid_size_2", "ask_size_2"],
    ["bid_price_3", "ask_price_3", "bid_size_3", "ask_size_3"],
    ["bid_price_4", "ask_price_4", "bid_size_4", "ask_size_4"],
    ["bid_price_5", "ask_price_5", "bid_size_5", "ask_size_5"],
];

impl Row<'_> {
    fn index(&self, name: &str) -> Result<usize> {
        let columns = match self {
            Self::Parquet(_, _, c) | Self::Csv(_, c) => c,
        };
        columns
            .get(name)
            .copied()
            .ok_or_else(|| schema(format!("missing required column {name}")))
    }
    pub fn has(&self, name: &str) -> bool {
        self.index(name).is_ok()
    }
    fn array(&self, name: &str) -> Result<(&dyn Array, usize)> {
        let index = self.index(name)?;
        let Self::Parquet(batch, row, _) = self else {
            return Err(schema("internal CSV array access"));
        };
        let array = batch.column(index).as_ref();
        if array.is_null(*row) {
            return Err(malformed(format!("null required value {name}")));
        }
        Ok((array, *row))
    }
    fn text(&self, name: &str) -> Result<&str> {
        match self {
            Self::Csv(record, _) => record
                .get(self.index(name)?)
                .ok_or_else(|| malformed(format!("missing CSV field {name}"))),
            Self::Parquet(_, _, _) => {
                let (array, row) = self.array(name)?;
                Ok(array
                    .as_any()
                    .downcast_ref::<StringArray>()
                    .ok_or_else(|| schema(format!("{name} requires UTF8 string")))?
                    .value(row))
            }
        }
    }
    fn integer(&self, name: &str) -> Result<i64> {
        match self {
            Self::Csv(_, _) => self.text(name)?.parse().map_err(malformed),
            Self::Parquet(_, _, _) => {
                let (array, row) = self.array(name)?;
                Ok(array
                    .as_any()
                    .downcast_ref::<Int64Array>()
                    .ok_or_else(|| schema(format!("{name} requires int64")))?
                    .value(row))
            }
        }
    }
    fn boolean(&self, name: &str) -> Result<bool> {
        match self {
            Self::Csv(_, _) => match self.text(name)? {
                "True" | "true" => Ok(true),
                "False" | "false" => Ok(false),
                value => Err(malformed(format!("{name} invalid bool {value}"))),
            },
            Self::Parquet(_, _, _) => {
                let (array, row) = self.array(name)?;
                Ok(array
                    .as_any()
                    .downcast_ref::<BooleanArray>()
                    .ok_or_else(|| schema(format!("{name} requires bool")))?
                    .value(row))
            }
        }
    }
    fn price(&self, name: &str) -> Result<i64> {
        let value = match self {
            Self::Csv(_, _) => self.text(name)?.parse::<f64>().map_err(malformed)?,
            Self::Parquet(_, _, _) => {
                let (array, row) = self.array(name)?;
                array
                    .as_any()
                    .downcast_ref::<Float64Array>()
                    .ok_or_else(|| schema(format!("{name} requires float64 USD")))?
                    .value(row)
            }
        };
        price_units(value)
    }
    fn timestamp(&self) -> Result<i64> {
        match self {
            Self::Csv(_, _) => timestamp_from_text(self.text("timestamp")?),
            Self::Parquet(_, _, _) => {
                let (array, row) = self.array("timestamp")?;
                if !matches!(array.data_type(), DataType::Timestamp(TimeUnit::Nanosecond, Some(tz)) if tz.as_ref() == "UTC")
                {
                    return Err(schema("timestamp requires nanoseconds and UTC timezone"));
                }
                Ok(array
                    .as_any()
                    .downcast_ref::<TimestampNanosecondArray>()
                    .ok_or_else(|| schema("timestamp requires timestamp[ns, UTC]"))?
                    .value(row))
            }
        }
    }
    fn key_time(&self, quality: bool, local_time: &mut LocalTimeValidator) -> Result<(Key, i64)> {
        let timestamp = self.timestamp()?;
        let date = if quality {
            local_time.date_for_timestamp(timestamp)
        } else {
            self.text("date")?.to_owned()
        };
        local_time.validate(&date, timestamp, self.integer("time_ns")?)?;
        Ok((
            Key {
                symbol: self.text("symbol")?.to_owned(),
                date,
                event_id: self.integer("event_id")?,
            },
            timestamp,
        ))
    }
}

fn required(kind: Kind, levels: usize) -> Vec<(String, DataType)> {
    let mut fields = vec![
        ("symbol".into(), DataType::Utf8),
        ("event_id".into(), DataType::Int64),
        (
            "timestamp".into(),
            DataType::Timestamp(TimeUnit::Nanosecond, Some("UTC".into())),
        ),
        ("time_ns".into(), DataType::Int64),
    ];
    match kind {
        Kind::Events => {
            fields.extend([
                ("date".into(), DataType::Utf8),
                ("segment_id".into(), DataType::Int64),
                ("prev_state_available".into(), DataType::Boolean),
                ("is_quote_update".into(), DataType::Boolean),
                ("event_type".into(), DataType::Int64),
                ("event_size".into(), DataType::Int64),
                ("event_price".into(), DataType::Float64),
                ("direction".into(), DataType::Int64),
            ]);
            for level in 1..=levels {
                for side in ["bid", "ask"] {
                    fields.push((format!("{side}_price_{level}"), DataType::Float64));
                    fields.push((format!("{side}_size_{level}"), DataType::Int64));
                }
            }
        }
        Kind::Trades => {
            fields.extend([
                ("date".into(), DataType::Utf8),
                ("event_type".into(), DataType::Int64),
                ("event_size".into(), DataType::Int64),
                ("event_price".into(), DataType::Float64),
                ("direction".into(), DataType::Int64),
                ("quote_accepted".into(), DataType::Boolean),
            ]);
        }
        Kind::Quality => fields.extend([
            ("quote_accepted".into(), DataType::Boolean),
            ("reject_reason".into(), DataType::Utf8),
        ]),
    }
    fields
}

impl TableReader {
    pub fn open(path: &Path, kind: Kind, levels: usize, chunk_rows: usize) -> Result<Self> {
        if !(1..=5).contains(&levels) || !(1..=1_048_576).contains(&chunk_rows) {
            return Err(Error::new(
                ErrorCode::Config,
                "invalid reader levels or chunk size",
            ));
        }
        let file = File::open(path).map_err(|e| {
            let e = Error::from(e);
            Error::new(e.code, format!("{}: {}", path.display(), e.message))
        })?;
        let (source, names) = if path.extension().is_some_and(|e| e == "parquet") {
            let builder = ParquetRecordBatchReaderBuilder::try_new(file).map_err(malformed)?;
            let schema_ref = builder.schema();
            for (name, dtype) in required(kind, levels) {
                let field = schema_ref
                    .field_with_name(&name)
                    .map_err(|_| schema(format!("{} missing {name}", path.display())))?;
                if field.data_type() != &dtype {
                    return Err(schema(format!(
                        "{}: {name} requires {dtype}, found {}",
                        path.display(),
                        field.data_type()
                    )));
                }
            }
            for (name, dtype) in [
                ("aggressor_side", DataType::Int64),
                ("signed_volume", DataType::Int64),
            ] {
                if let Ok(field) = schema_ref.field_with_name(name)
                    && field.data_type() != &dtype
                {
                    return Err(schema(format!("{name} requires int64")));
                }
            }
            let names = schema_ref
                .fields()
                .iter()
                .map(|f| f.name().clone())
                .collect::<Vec<_>>();
            let reader = builder
                .with_batch_size(chunk_rows)
                .build()
                .map_err(malformed)?;
            (
                Source::Parquet {
                    reader: Box::new(reader),
                    batch: None,
                    offset: 0,
                },
                names,
            )
        } else if path.extension().is_some_and(|e| e == "csv" || e == "gz") {
            let stream: Box<dyn Read + Send> = if path.extension().is_some_and(|e| e == "gz") {
                Box::new(GzDecoder::new(BufReader::new(file)))
            } else {
                Box::new(BufReader::new(file))
            };
            let mut reader = csv::ReaderBuilder::new().from_reader(stream);
            let names = reader
                .headers()
                .map_err(malformed)?
                .iter()
                .map(str::to_owned)
                .collect::<Vec<_>>();
            for (name, _) in required(kind, levels) {
                if !names.contains(&name) {
                    return Err(schema(format!("{} missing {name}", path.display())));
                }
            }
            (
                Source::Csv {
                    reader,
                    record: csv::StringRecord::new(),
                },
                names,
            )
        } else {
            return Err(schema(
                "input format must be .parquet, .csv or headered .csv.gz",
            ));
        };
        let columns: HashMap<_, _> = names
            .iter()
            .enumerate()
            .map(|(i, n)| (n.clone(), i))
            .collect();
        if columns.len() != names.len() {
            return Err(schema("duplicate input column names"));
        }
        Ok(Self {
            source,
            columns,
            path: path.to_owned(),
            rows: 0,
            order: OrderGuard::default(),
            levels,
            local_time: LocalTimeValidator::default(),
        })
    }
    fn next<T>(
        &mut self,
        parse: impl FnOnce(&Row<'_>, &mut LocalTimeValidator) -> Result<T>,
    ) -> Result<Option<T>> {
        let row = match &mut self.source {
            Source::Csv { reader, record } => {
                if !reader.read_record(record).map_err(malformed)? {
                    return Ok(None);
                }
                Row::Csv(record, &self.columns)
            }
            Source::Parquet {
                reader,
                batch,
                offset,
            } => {
                while batch.as_ref().is_none_or(|b| *offset >= b.num_rows()) {
                    *batch = match reader.next() {
                        Some(result) => Some(result.map_err(malformed)?),
                        None => return Ok(None),
                    };
                    *offset = 0;
                }
                let row = Row::Parquet(
                    batch.as_ref().expect("batch populated above"),
                    *offset,
                    &self.columns,
                );
                *offset += 1;
                row
            }
        };
        self.rows += 1;
        parse(&row, &mut self.local_time).map(Some).map_err(|e| {
            Error::new(
                e.code,
                format!("{} row {}: {}", self.path.display(), self.rows, e.message),
            )
        })
    }
    pub fn next_event(&mut self) -> Result<Option<Event>> {
        let levels = self.levels;
        let event = self.next(|r, local_time| {
            let (key, timestamp) = r.key_time(false, local_time)?;
            let mut book = Vec::with_capacity(levels);
            for [bid, ask, bid_size, ask_size] in &BOOK_COLUMNS[..levels] {
                book.push(Level {
                    bid: r.price(bid)?,
                    ask: r.price(ask)?,
                    bid_size: r.integer(bid_size)?,
                    ask_size: r.integer(ask_size)?,
                });
            }
            let book = Book(book);
            book.validate()?;
            let segment = r.integer("segment_id")?;
            if segment < 1 {
                return Err(malformed("accepted segment_id must be positive"));
            }
            let timestamp_rounded = if r.has("timestamp_subnanosecond_rounded") {
                Some(r.boolean("timestamp_subnanosecond_rounded")?)
            } else {
                None
            };
            if r.has("time_seconds_text") {
                let (ns, rounded) = decimal_seconds_ns(r.text("time_seconds_text")?)?;
                if ns != r.integer("time_ns")?
                    || timestamp_rounded.is_some_and(|flag| flag != rounded)
                {
                    return Err(malformed(
                        "original decimal time/rounding flag disagrees with delivered nanoseconds",
                    ));
                }
            }
            let event_type = r.integer("event_type")?;
            let event_size = r.integer("event_size")?;
            let event_price = r.price("event_price")?;
            let direction = r.integer("direction")?;
            if !(1..=5).contains(&event_type) || event_size <= 0 || ![-1, 1].contains(&direction) {
                return Err(malformed(format!("invalid accepted message {key:?}")));
            }
            if r.has("event_price_raw") && r.integer("event_price_raw")? != event_price {
                return Err(malformed(
                    "clean USD event price disagrees with raw USD/10000 price",
                ));
            }
            let execution = if [4, 5].contains(&event_type) {
                Some(Trade {
                    key: key.clone(),
                    timestamp,
                    size: event_size,
                    price: event_price,
                    direction,
                    event_type,
                    quote_accepted: true,
                })
            } else {
                None
            };
            Ok(Event {
                key,
                timestamp,
                book,
                segment,
                prev_available: r.boolean("prev_state_available")?,
                l1_update: r.boolean("is_quote_update")?,
                timestamp_rounded,
                execution,
            })
        })?;
        if let Some(e) = &event {
            self.order.observe(&e.key, e.timestamp, false)?;
        }
        Ok(event)
    }
    pub fn next_quality(&mut self) -> Result<Option<Quality>> {
        let q = self.next(|r, local_time| {
            let (key, timestamp) = r.key_time(true, local_time)?;
            let accepted = r.boolean("quote_accepted")?;
            let reason = r.text("reject_reason")?.to_owned();
            if !matches!(
                reason.as_str(),
                "" | "outside_session" | "invalid_book" | "invalid_event" | "spread_above_p95"
            ) {
                return Err(schema(format!(
                    "unsupported Lev-v1 reject_reason: {reason}"
                )));
            }
            if accepted != reason.is_empty() {
                return Err(Error::new(
                    ErrorCode::Quality,
                    "quote_accepted and reject_reason disagree",
                ));
            }
            Ok(Quality {
                key,
                timestamp,
                accepted,
                reason,
            })
        })?;
        if let Some(q) = &q {
            self.order.observe(&q.key, q.timestamp, true)?;
        }
        Ok(q)
    }
    pub fn next_trade(&mut self) -> Result<Option<Trade>> {
        let trade = self.next(|r, local_time| {
            let (key, timestamp) = r.key_time(false, local_time)?;
            let t = Trade {
                key,
                timestamp,
                size: r.integer("event_size")?,
                price: r.price("event_price")?,
                direction: r.integer("direction")?,
                event_type: r.integer("event_type")?,
                quote_accepted: r.boolean("quote_accepted")?,
            };
            t.validate()?;
            if (r.has("aggressor_side") && r.integer("aggressor_side")? != -t.direction)
                || (r.has("signed_volume") && r.integer("signed_volume")? != t.size * -t.direction)
            {
                return Err(malformed(format!(
                    "inconsistent supplied trade sign {:?}",
                    t.key
                )));
            }
            Ok(t)
        })?;
        if let Some(t) = &trade {
            self.order.observe(&t.key, t.timestamp, false)?;
        }
        Ok(trade)
    }
}
