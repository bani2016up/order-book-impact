//! Bounded Parquet writers and whole-directory publication.
use crate::{
    buckets::BucketRow,
    error::{Error, ErrorCode, Result},
};
use arrow_array::{
    ArrayRef, BooleanArray, Float64Array, Int64Array, RecordBatch, StringArray,
    TimestampNanosecondArray,
};
use arrow_schema::{DataType, Field, Schema, TimeUnit};
use parquet::{arrow::ArrowWriter, basic::Compression, file::properties::WriterProperties};
use std::{
    fs::{self, File},
    path::{Path, PathBuf},
    sync::Arc,
};

pub const OUTPUT_FILES: [&str; 4] = [
    "features.parquet",
    "bucket_quality.parquet",
    "manifest.json",
    "quality_report.json",
];
fn io(error: impl std::fmt::Display) -> Error {
    Error::new(ErrorCode::Io, error.to_string())
}

pub struct Transaction {
    pub stage: tempfile::TempDir,
    pub destination: PathBuf,
    overwrite: bool,
}
impl Transaction {
    pub fn new(destination: &Path, inputs: &[&Path], overwrite: bool) -> Result<Self> {
        let absolute = if destination.is_absolute() {
            destination.to_owned()
        } else {
            std::env::current_dir()?.join(destination)
        };
        let parent = absolute
            .parent()
            .ok_or_else(|| Error::new(ErrorCode::Config, "output directory needs a parent"))?;
        // Resolve the nearest existing ancestor before mkdir, including symlinks.
        let mut ancestor = parent;
        let mut suffix = Vec::new();
        while !ancestor.exists() {
            suffix.push(
                ancestor
                    .file_name()
                    .ok_or_else(|| Error::new(ErrorCode::Config, "invalid output parent"))?
                    .to_owned(),
            );
            ancestor = ancestor
                .parent()
                .ok_or_else(|| Error::new(ErrorCode::Config, "invalid output ancestor"))?;
        }
        let mut canonical_parent = ancestor.canonicalize()?;
        for part in suffix.into_iter().rev() {
            canonical_parent.push(part);
        }
        let target = if absolute.exists() {
            absolute.canonicalize()?
        } else {
            canonical_parent.join(
                absolute
                    .file_name()
                    .ok_or_else(|| Error::new(ErrorCode::Config, "output name missing"))?,
            )
        };
        for input in inputs {
            let source = input.canonicalize().map_err(|error| {
                let error = Error::from(error);
                Error::new(
                    error.code,
                    format!("{}: {}", input.display(), error.message),
                )
            })?;
            if source.starts_with(&target) {
                return Err(Error::new(
                    ErrorCode::Config,
                    format!(
                        "output {} would contain/replace input {}",
                        target.display(),
                        source.display()
                    ),
                ));
            }
        }
        if target.exists() {
            Self::validate_existing(&target, overwrite)?;
        }
        fs::create_dir_all(&canonical_parent)?;
        let stage = tempfile::Builder::new()
            .prefix(".ofi-stage-")
            .tempdir_in(&canonical_parent)?;
        Ok(Self {
            stage,
            destination: target,
            overwrite,
        })
    }
    fn validate_existing(target: &Path, overwrite: bool) -> Result<()> {
        if !overwrite {
            return Err(Error::new(
                ErrorCode::Io,
                format!(
                    "output {} already exists; use overwrite=True for an owned pipeline dataset",
                    target.display()
                ),
            ));
        }
        if !target.is_dir() {
            return Err(Error::new(ErrorCode::Io, "output must be a directory"));
        }
        let manifest: serde_json::Value =
            serde_json::from_reader(File::open(target.join("manifest.json"))?).map_err(io)?;
        if manifest.get("producer").and_then(|v| v.as_str()) != Some("ofi-pipeline") {
            return Err(Error::new(
                ErrorCode::Io,
                "overwrite requires an ofi-pipeline manifest",
            ));
        }
        for entry in fs::read_dir(target)? {
            let entry = entry?;
            if !OUTPUT_FILES.iter().any(|name| entry.file_name() == *name)
                || !entry.file_type()?.is_file()
            {
                return Err(Error::new(
                    ErrorCode::Io,
                    "refusing to overwrite a directory containing other user data",
                ));
            }
        }
        Ok(())
    }
    pub fn publish(self) -> Result<PathBuf> {
        self.publish_with(|source, destination| fs::rename(source, destination))
    }
    fn publish_with(
        self,
        mut rename: impl FnMut(&Path, &Path) -> std::io::Result<()>,
    ) -> Result<PathBuf> {
        if self.destination.exists() {
            Self::validate_existing(&self.destination, self.overwrite)?;
            let backup = tempfile::Builder::new()
                .prefix(".ofi-backup-")
                .tempdir_in(self.destination.parent().expect("validated output parent"))?;
            fs::remove_dir(backup.path())?;
            rename(&self.destination, backup.path())?;
            if let Err(error) = rename(self.stage.path(), &self.destination) {
                if let Err(restore) = rename(backup.path(), &self.destination) {
                    let preserved = backup.keep();
                    return Err(io(format!(
                        "publication failed: {error}; restore failed: {restore}; original results preserved at {}",
                        preserved.display()
                    )));
                }
                return Err(error.into());
            }
            backup.close()?;
        } else {
            rename(self.stage.path(), &self.destination)?;
        }
        Ok(self.destination)
    }
}

pub fn write_json(path: &Path, value: &impl serde::Serialize) -> Result<()> {
    let mut f = File::create(path)?;
    serde_json::to_writer_pretty(&mut f, value).map_err(io)?;
    f.sync_all()?;
    Ok(())
}

fn schema(levels: usize) -> Arc<Schema> {
    let mut fields = vec![
        Field::new("symbol", DataType::Utf8, false),
        Field::new("date", DataType::Utf8, false),
        Field::new(
            "interval_start",
            DataType::Timestamp(TimeUnit::Nanosecond, Some("UTC".into())),
            false,
        ),
        Field::new(
            "timestamp",
            DataType::Timestamp(TimeUnit::Nanosecond, Some("UTC".into())),
            false,
        ),
        Field::new("accepted", DataType::Boolean, false),
        Field::new("rejection_reasons", DataType::Utf8, false),
    ];
    for name in [
        "event_count",
        "rejected_events",
        "quote_update_count",
        "volume",
        "trade_imbalance",
        "trade_count",
        "classified_count",
        "unclassified_count",
        "classified_volume",
        "unclassified_volume",
    ] {
        fields.push(Field::new(name, DataType::Int64, name == "trade_imbalance"));
    }
    fields.push(Field::new(
        "classified_trade_imbalance",
        DataType::Int64,
        false,
    ));
    fields.push(Field::new(
        "trade_signing_complete",
        DataType::Boolean,
        false,
    ));
    for name in [
        "mid_price_start",
        "mid_price_end",
        "mid_price_change",
        "mid_price_change_ticks",
        "avg_depth",
    ] {
        fields.push(Field::new(name, DataType::Float64, true));
    }
    for level in 1..=levels {
        fields.push(Field::new(format!("ofi_l{level}"), DataType::Int64, true));
    }
    Arc::new(Schema::new(fields))
}
fn batch(rows: &[BucketRow], schema: Arc<Schema>, levels: usize) -> Result<RecordBatch> {
    let mut arrays: Vec<ArrayRef> = vec![
        Arc::new(StringArray::from(
            rows.iter().map(|r| r.symbol.as_str()).collect::<Vec<_>>(),
        )),
        Arc::new(StringArray::from(
            rows.iter().map(|r| r.date.as_str()).collect::<Vec<_>>(),
        )),
        Arc::new(
            TimestampNanosecondArray::from(
                rows.iter().map(|r| r.interval_start).collect::<Vec<_>>(),
            )
            .with_timezone("UTC"),
        ),
        Arc::new(
            TimestampNanosecondArray::from(rows.iter().map(|r| r.timestamp).collect::<Vec<_>>())
                .with_timezone("UTC"),
        ),
        Arc::new(BooleanArray::from(
            rows.iter().map(|r| r.accepted).collect::<Vec<_>>(),
        )),
        Arc::new(StringArray::from(
            rows.iter()
                .map(|r| r.rejection_reasons.as_str())
                .collect::<Vec<_>>(),
        )),
    ];
    macro_rules! integers {($($value:expr),+) => {$(arrays.push(Arc::new(Int64Array::from(rows.iter().map($value).collect::<Vec<_>>())));)+};}
    integers!(
        |r: &BucketRow| r.event_count,
        |r: &BucketRow| r.rejected_events,
        |r: &BucketRow| r.quote_update_count,
        |r: &BucketRow| r.trades.volume
    );
    arrays.push(Arc::new(Int64Array::from(
        rows.iter()
            .map(|r| {
                if r.trades.unclassified_count == 0 {
                    Some(r.trades.trade_imbalance)
                } else {
                    None
                }
            })
            .collect::<Vec<_>>(),
    )));
    integers!(
        |r: &BucketRow| r.trades.trade_count,
        |r: &BucketRow| r.trades.classified_count,
        |r: &BucketRow| r.trades.unclassified_count,
        |r: &BucketRow| r.trades.classified_volume,
        |r: &BucketRow| r.trades.unclassified_volume,
        |r: &BucketRow| r.trades.trade_imbalance
    );
    arrays.push(Arc::new(BooleanArray::from(
        rows.iter()
            .map(|r| r.trades.unclassified_count == 0)
            .collect::<Vec<_>>(),
    )));
    macro_rules! floats {($($field:ident),+) => {$(arrays.push(Arc::new(Float64Array::from(rows.iter().map(|r|r.features.as_ref().map(|f|f.$field)).collect::<Vec<_>>())));)+};}
    floats!(
        mid_price_start,
        mid_price_end,
        mid_price_change,
        mid_price_change_ticks,
        avg_depth
    );
    for level in 0..levels {
        arrays.push(Arc::new(Int64Array::from(
            rows.iter()
                .map(|r| r.features.as_ref().map(|f| f.ofi[level]))
                .collect::<Vec<_>>(),
        )));
    }
    RecordBatch::try_new(schema, arrays).map_err(io)
}

pub struct Writer {
    features: ArrowWriter<File>,
    quality: ArrowWriter<File>,
    feature_rows: Vec<BucketRow>,
    quality_rows: Vec<BucketRow>,
    schema: Arc<Schema>,
    levels: usize,
    batch_rows: usize,
}
impl Writer {
    pub fn new(directory: &Path, levels: usize, chunk_rows: usize) -> Result<Self> {
        let schema = schema(levels);
        let props = WriterProperties::builder()
            .set_compression(Compression::ZSTD(Default::default()))
            .set_max_row_group_row_count(Some(4096))
            .build();
        Ok(Self {
            features: ArrowWriter::try_new(
                File::create(directory.join("features.parquet"))?,
                schema.clone(),
                Some(props.clone()),
            )
            .map_err(io)?,
            quality: ArrowWriter::try_new(
                File::create(directory.join("bucket_quality.parquet"))?,
                schema.clone(),
                Some(props),
            )
            .map_err(io)?,
            feature_rows: Vec::new(),
            quality_rows: Vec::new(),
            schema,
            levels,
            batch_rows: chunk_rows.min(4096),
        })
    }
    pub fn write(&mut self, row: BucketRow) -> Result<()> {
        if row.accepted {
            self.feature_rows.push(row.clone());
        }
        self.quality_rows.push(row);
        if self.quality_rows.len() >= self.batch_rows {
            self.flush()?;
        }
        Ok(())
    }
    fn flush(&mut self) -> Result<()> {
        if !self.feature_rows.is_empty() {
            self.features
                .write(&batch(
                    &self.feature_rows,
                    self.schema.clone(),
                    self.levels,
                )?)
                .map_err(io)?;
            self.feature_rows.clear();
        }
        if !self.quality_rows.is_empty() {
            self.quality
                .write(&batch(
                    &self.quality_rows,
                    self.schema.clone(),
                    self.levels,
                )?)
                .map_err(io)?;
            self.quality_rows.clear();
        }
        Ok(())
    }
    pub fn append_partition(&mut self, directory: &Path) -> Result<()> {
        use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
        self.flush()?;
        for (name, writer) in [
            ("features.parquet", &mut self.features),
            ("bucket_quality.parquet", &mut self.quality),
        ] {
            let reader =
                ParquetRecordBatchReaderBuilder::try_new(File::open(directory.join(name))?)
                    .map_err(io)?
                    .with_batch_size(self.batch_rows)
                    .build()
                    .map_err(io)?;
            for batch in reader {
                writer.write(&batch.map_err(io)?).map_err(io)?;
            }
        }
        Ok(())
    }
    pub fn finish(mut self) -> Result<()> {
        self.flush()?;
        self.features.close().map_err(io)?;
        self.quality.close().map_err(io)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn owned(path: &Path) {
        fs::create_dir_all(path).unwrap();
        write_json(
            &path.join("manifest.json"),
            &serde_json::json!({"producer":"ofi-pipeline"}),
        )
        .unwrap();
        fs::write(path.join("features.parquet"), "original").unwrap();
    }
    #[test]
    fn publication_failures_restore_or_preserve_original_data() {
        for restore_fails in [false, true] {
            let dir = tempfile::tempdir().unwrap();
            let target = dir.path().join("result");
            owned(&target);
            let tx = Transaction::new(&target, &[], true).unwrap();
            fs::write(tx.stage.path().join("features.parquet"), "new").unwrap();
            let mut calls = 0;
            let error = tx
                .publish_with(|source, destination| {
                    calls += 1;
                    if calls == 2 || (restore_fails && calls == 3) {
                        Err(std::io::Error::from(std::io::ErrorKind::PermissionDenied))
                    } else {
                        fs::rename(source, destination)
                    }
                })
                .unwrap_err();
            assert_eq!(error.code, ErrorCode::Io);
            if restore_fails {
                assert!(error.message.contains("original results preserved"));
                let backups: Vec<_> = fs::read_dir(dir.path())
                    .unwrap()
                    .map(|e| e.unwrap().path())
                    .filter(|p| {
                        p.file_name()
                            .unwrap()
                            .to_string_lossy()
                            .starts_with(".ofi-backup-")
                    })
                    .collect();
                assert_eq!(backups.len(), 1);
                assert_eq!(
                    fs::read_to_string(backups[0].join("features.parquet")).unwrap(),
                    "original"
                );
            } else {
                assert_eq!(
                    fs::read_to_string(target.join("features.parquet")).unwrap(),
                    "original"
                );
            }
        }
    }
    #[test]
    fn paths_nested_parents_ownership_and_writer_io_errors() {
        let dir = tempfile::tempdir().unwrap();
        let tx = Transaction::new(&dir.path().join("a/b/result"), &[], false).unwrap();
        assert!(tx.stage.path().is_dir());
        drop(tx);
        let relative = PathBuf::from("target")
            .join(format!("relative-transaction-test-{}", std::process::id()));
        let tx = Transaction::new(&relative, &[], false).unwrap();
        drop(tx);
        assert!(Transaction::new(Path::new("/"), &[], false).is_err());
        let target = dir.path().join("file");
        fs::write(&target, "user").unwrap();
        assert!(Transaction::new(&target, &[], true).is_err());
        let target = dir.path().join("not-owned");
        fs::create_dir(&target).unwrap();
        fs::write(target.join("manifest.json"), "bad json").unwrap();
        assert!(Transaction::new(&target, &[], true).is_err());
        fs::write(
            target.join("manifest.json"),
            r#"{"producer":"someone-else"}"#,
        )
        .unwrap();
        assert!(Transaction::new(&target, &[], true).is_err());
        assert!(Writer::new(&dir.path().join("missing"), 1, 1).is_err());
        let mut writer = Writer::new(dir.path(), 1, 1).unwrap();
        assert!(writer.append_partition(&target).is_err());
    }
}
