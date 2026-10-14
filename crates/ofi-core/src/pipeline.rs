//! Coarse file-set operation: streaming ID merge, compute, provenance, publish.
use crate::{
    VERSION,
    adapter::{Kind, TableReader},
    config::{Config, TradeSigning},
    error::{Error, ErrorCode, Result},
    output::{Transaction, Writer, write_json},
    raw::RawInput,
    trades::TradeTotals,
    worker::{InputRow, Worker, WorkerStats},
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, VecDeque},
    fs::File,
    io::Read,
    path::PathBuf,
    sync::Arc,
    time::Instant,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Inputs {
    pub events: PathBuf,
    pub trades: PathBuf,
    pub quality: PathBuf,
    #[serde(default)]
    pub raw: Vec<RawInput>,
}
#[derive(Debug, Default, Serialize)]
pub struct PartitionReport {
    pub symbol: String,
    pub date: String,
    pub original_rows: u64,
    pub clean_events: u64,
    pub rejected_events: u64,
    pub feature_rows: u64,
    pub total_buckets: u64,
    pub rejected_buckets: u64,
    pub rejection_reasons: BTreeMap<String, u64>,
    pub source_rejection_reasons: BTreeMap<String, u64>,
    pub signing: TradeTotals,
    pub rounded_event_timestamps: u64,
    pub missing_precision_flag_rows: u64,
    pub rounded_raw_timestamps: u64,
}
#[derive(Debug, Serialize)]
pub struct RunReport {
    pub output_dir: PathBuf,
    pub features_path: PathBuf,
    pub bucket_quality_path: PathBuf,
    pub manifest_path: PathBuf,
    pub quality_report_path: PathBuf,
    pub partitions: Vec<PartitionReport>,
    pub config: Config,
    pub algorithm_version: String,
    pub schema_version: String,
    pub elapsed_seconds: f64,
    pub peak_partition_workers: usize,
    pub warnings: Vec<String>,
}
fn hash(path: &std::path::Path) -> Result<serde_json::Value> {
    let mut source = File::open(path).map_err(|error| {
        let error = Error::from(error);
        Error::new(error.code, format!("{}: {}", path.display(), error.message))
    })?;
    let mut hash = Sha256::new();
    let mut bytes = 0_u64;
    let mut buffer = [0_u8; 65536];
    loop {
        let n = source.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hash.update(&buffer[..n]);
        bytes += n as u64;
    }
    Ok(serde_json::json!({"sha256":format!("{:x}",hash.finalize()),"size_bytes":bytes}))
}

pub fn run(inputs: Inputs, output: PathBuf, config: Config) -> Result<RunReport> {
    config.validate()?;
    let started = Instant::now();
    let mut input_paths = vec![
        inputs.events.as_path(),
        inputs.trades.as_path(),
        inputs.quality.as_path(),
    ];
    for source in &inputs.raw {
        input_paths.extend(source.paths()?);
    }
    let transaction = Transaction::new(&output, &input_paths, config.overwrite)?;
    let sources = serde_json::json!({"events":hash(&inputs.events)?,"trades":hash(&inputs.trades)?,"quality":hash(&inputs.quality)?});
    let mut events = TableReader::open(
        &inputs.events,
        Kind::Events,
        config.levels,
        config.chunk_rows,
    )?;
    let mut trades = TableReader::open(
        &inputs.trades,
        Kind::Trades,
        config.levels,
        config.chunk_rows,
    )?;
    let mut quality = TableReader::open(
        &inputs.quality,
        Kind::Quality,
        config.levels,
        config.chunk_rows,
    )?;
    let mut next_event = events.next_event()?;
    let mut next_trade = trades.next_trade()?;
    let mut writer = Writer::new(transaction.stage.path(), config.levels, config.chunk_rows)?;
    let stats = Arc::new(WorkerStats::default());
    let mut partitions = Vec::new();
    let mut waiting = VecDeque::<Worker>::new();
    let mut current: Option<Worker> = None;
    let mut partition: Option<(String, String)> = None;
    let mut partition_count = 0;
    let mut chunk = Vec::with_capacity(config.chunk_rows);
    while let Some(q) = quality.next_quality()? {
        if partition
            .as_ref()
            .is_none_or(|(symbol, date)| symbol != &q.key.symbol || date != &q.key.date)
        {
            let key = (q.key.symbol.clone(), q.key.date.clone());
            partition_count += 1;
            if partition_count > config.max_partitions {
                return Err(Error::new(
                    ErrorCode::Config,
                    "file set exceeds configured max_partitions; split file sets or explicitly increase the metadata bound",
                ));
            }
            if let Some(mut worker) = current.take() {
                if !chunk.is_empty() {
                    worker.send(std::mem::take(&mut chunk))?;
                }
                worker.close();
                waiting.push_back(worker);
            }
            if waiting.len() >= config.threads {
                partitions.push(
                    waiting
                        .pop_front()
                        .expect("bounded pending workers")
                        .finish(&mut writer)?,
                );
            }
            let raw = if config.trade_signing == TradeSigning::QuoteTest {
                let candidates: Vec<_> = inputs
                    .raw
                    .iter()
                    .filter(|r| r.symbol == q.key.symbol && r.date == q.key.date)
                    .collect();
                if candidates.len() != 1 {
                    return Err(Error::new(
                        ErrorCode::Quality,
                        format!(
                            "Quote Test requires exactly one original raw pair/archive for {} {}",
                            q.key.symbol, q.key.date
                        ),
                    ));
                }
                Some(candidates[0].clone())
            } else {
                None
            };
            current = Some(Worker::spawn(
                key.0.clone(),
                key.1.clone(),
                config.clone(),
                raw,
                transaction.stage.path(),
                stats.clone(),
            )?);
            partition = Some(key);
        }
        if next_event.as_ref().is_some_and(|e| e.key < q.key)
            || next_trade.as_ref().is_some_and(|t| t.key < q.key)
        {
            return Err(Error::new(
                ErrorCode::Quality,
                format!(
                    "input row lacks original quality evidence before {:?}",
                    q.key
                ),
            ));
        }
        let event = if next_event.as_ref().is_some_and(|e| e.key == q.key) {
            let event = next_event.take();
            next_event = events.next_event()?;
            event
        } else {
            None
        };
        let trade = if next_trade.as_ref().is_some_and(|t| t.key == q.key) {
            let trade = next_trade.take();
            next_trade = trades.next_trade()?;
            trade
        } else {
            None
        };
        chunk.push(InputRow {
            quality: q,
            event,
            trade,
        });
        if chunk.len() >= config.chunk_rows {
            current
                .as_mut()
                .expect("partition initialized")
                .send(std::mem::take(&mut chunk))?;
        }
    }
    if next_event.is_some() || next_trade.is_some() {
        return Err(Error::new(
            ErrorCode::Quality,
            "event/trade rows remain after original quality evidence ended",
        ));
    }
    let mut current = current
        .ok_or_else(|| Error::new(ErrorCode::Quality, "original quality evidence is empty"))?;
    // Release exhausted input buffers before final chunk handoff and partition assembly.
    drop(events);
    drop(trades);
    drop(quality);
    if !chunk.is_empty() {
        current.send(chunk)?;
    }
    current.close();
    waiting.push_back(current);
    while let Some(worker) = waiting.pop_front() {
        partitions.push(worker.finish(&mut writer)?);
    }
    writer.finish()?;
    let mut warnings = Vec::new();
    if partitions.iter().any(|p| p.missing_precision_flag_rows > 0) {
        warnings.push("Some clean events lack delivered timestamp rounding flags; integer UTC nanoseconds remain validated.".into());
    }
    let mut raw_hashes = Vec::new();
    for input in &inputs.raw {
        for path in input.paths()? {
            raw_hashes.push(hash(path)?);
        }
    }
    let manifest = serde_json::json!({"producer":"ofi-pipeline","algorithm_version":VERSION,"schema_version":"ofi-v1","adapter_version":config.adapter_version,"dataset_identity":sources,"raw_sources":raw_hashes,"config":config,"units":{"prices":"USD","price_changes":"USD and ticks","volume_depth_ofi_ti":"shares","timestamp":"UTC nanoseconds"},"semantics":{"buckets":"(start, end], anchored at New York session open; first incomplete excluded","boundary":"last original row at/before boundary, including rejected rows and tied event order","ofi":"rank-based L1..L5 extension; unknown initialization excluded","depth":"mean over L1 updates; right-boundary fallback","trade_signing":config.trade_signing,"lags":"sparse accepted intervals require actual temporal-adjacency checks"},"concurrency":"ordered producer; at most configured independent session workers; one queued chunk per worker; partition outputs merged in key order", "input_passes":"temporary partition Parquet output is read once for ordered final assembly; clean inputs: one streaming SHA-256 pass plus one ordered computation pass; Quote Test ZIPs: bounded-memory extraction to temporary disk then one paired-row pass, plus source hashing; no reference-feature reads"});
    write_json(&transaction.stage.path().join("manifest.json"), &manifest)?;
    let output_dir = transaction.destination.clone();
    let report = RunReport {
        features_path: output_dir.join("features.parquet"),
        bucket_quality_path: output_dir.join("bucket_quality.parquet"),
        manifest_path: output_dir.join("manifest.json"),
        quality_report_path: output_dir.join("quality_report.json"),
        output_dir,
        partitions,
        config,
        algorithm_version: VERSION.into(),
        schema_version: "ofi-v1".into(),
        elapsed_seconds: started.elapsed().as_secs_f64(),
        peak_partition_workers: stats.peak(),
        warnings,
    };
    write_json(
        &transaction.stage.path().join("quality_report.json"),
        &report,
    )?;
    transaction.publish()?;
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn disappeared_source_hash_is_actionable() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("missing.csv");
        let error = hash(&path).unwrap_err();
        assert_eq!(error.code, ErrorCode::MissingFile);
        assert!(error.message.contains("missing.csv"));
    }
}
