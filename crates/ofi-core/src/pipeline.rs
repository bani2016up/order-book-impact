//! Coarse file-set operation: streaming ID merge, compute, provenance, publish.
use crate::{
    VERSION,
    adapter::{Kind, TableReader},
    buckets::{BucketEngine, BucketRow},
    config::{Config, TradeSigning},
    error::{Error, ErrorCode, Result},
    output::{Transaction, Writer, write_json},
    raw::{RawInput, RawReader, quote_test},
    trades::{TradeSequence, TradeTotals},
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs::File, io::Read, path::PathBuf, time::Instant};

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
    pub warnings: Vec<String>,
}
fn hash(path: &std::path::Path) -> Result<serde_json::Value> {
    let mut source = File::open(path)?;
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
    let mut sequence = TradeSequence::default();
    let mut writer = Writer::new(transaction.stage.path(), config.levels, config.chunk_rows)?;
    let mut raw: Option<RawReader> = None;
    let mut partitions = Vec::<PartitionReport>::new();
    let mut engine: Option<BucketEngine> = None;
    let mut report = PartitionReport::default();
    fn emit(row: BucketRow, report: &mut PartitionReport, writer: &mut Writer) -> Result<()> {
        report.total_buckets += 1;
        if row.accepted {
            report.feature_rows += 1;
        } else {
            report.rejected_buckets += 1;
            for reason in row.rejection_reasons.split('|') {
                *report.rejection_reasons.entry(reason.into()).or_default() += 1;
            }
        }
        writer.write(row)
    }
    while let Some(q) = quality.next_quality()? {
        if report.symbol != q.key.symbol || report.date != q.key.date {
            if let Some(mut r) = raw.take() {
                r.finish()?;
            }
            if config.trade_signing == TradeSigning::QuoteTest {
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
                raw = Some(RawReader::open(candidates[0], transaction.stage.path())?);
            }
            if let Some(mut old) = engine.take() {
                old.finish(&mut |row| emit(row, &mut report, &mut writer))?;
                partitions.push(report);
            }
            report = PartitionReport {
                symbol: q.key.symbol.clone(),
                date: q.key.date.clone(),
                ..PartitionReport::default()
            };
            engine = Some(BucketEngine::new(&q.key.symbol, &q.key.date, &config)?);
        }
        report.original_rows += 1;
        report.clean_events += u64::from(q.accepted);
        report.rejected_events += u64::from(!q.accepted);
        if !q.accepted {
            *report
                .source_rejection_reasons
                .entry(q.reason.clone())
                .or_default() += 1;
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
        let matched_event = next_event.as_ref().filter(|e| e.key == q.key);
        let matched_trade = next_trade.as_ref().filter(|t| t.key == q.key);
        let raw_row = if let Some(raw) = raw.as_mut() {
            Some(raw.observe(&q)?)
        } else {
            None
        };
        if let Some(event) = matched_event {
            report.rounded_event_timestamps += u64::from(event.timestamp_rounded == Some(true));
            report.missing_precision_flag_rows += u64::from(event.timestamp_rounded.is_none());
        }
        if let Some((row, _)) = &raw_row {
            report.rounded_raw_timestamps += u64::from(row.rounded);
        }
        if let (Some(event), Some((row, _))) = (matched_event, &raw_row) {
            let book = row.book.as_ref().ok_or_else(|| {
                Error::new(
                    ErrorCode::Quality,
                    "accepted clean book has invalid raw post-state",
                )
            })?;
            if book.0.len() < config.levels || book.0[..config.levels] != event.book.0 {
                return Err(Error::new(
                    ErrorCode::Quality,
                    format!("clean/raw post-state mismatch at {:?}", q.key),
                ));
            }
        }
        let sign = if let Some(t) = matched_trade {
            let known = sequence.observe(t)?;
            let sign = if let Some((row, pre)) = &raw_row {
                quote_test(t, row, pre.as_ref())?
            } else {
                Some(known)
            };
            report.signing.add(t, sign)?;
            sign
        } else {
            None
        };
        engine.as_mut().expect("partition initialized").observe(
            &q,
            matched_event,
            matched_trade.map(|t| (t, sign)),
            &mut |row| emit(row, &mut report, &mut writer),
        )?;
        if matched_event.is_some() {
            next_event = events.next_event()?;
        }
        if matched_trade.is_some() {
            next_trade = trades.next_trade()?;
        }
    }
    if next_event.is_some() || next_trade.is_some() {
        return Err(Error::new(
            ErrorCode::Quality,
            "event/trade rows remain after original quality evidence ended",
        ));
    }
    if let Some(mut engine) = engine {
        engine.finish(&mut |row| emit(row, &mut report, &mut writer))?;
        partitions.push(report);
    } else {
        return Err(Error::new(
            ErrorCode::Quality,
            "original quality evidence is empty",
        ));
    }
    if let Some(mut raw) = raw {
        raw.finish()?;
    }
    writer.finish()?;
    let mut warnings = if config.threads > 1 {
        vec!["This initial runner is sequential; bounded independent-partition concurrency is pending.".into()]
    } else {
        vec![]
    };
    if partitions.iter().any(|p| p.missing_precision_flag_rows > 0) {
        warnings.push("Some clean events lack delivered timestamp rounding flags; integer UTC nanoseconds remain validated.".into());
    }
    let mut raw_hashes = Vec::new();
    for input in &inputs.raw {
        for path in input.paths()? {
            raw_hashes.push(hash(path)?);
        }
    }
    let manifest = serde_json::json!({"producer":"ofi-pipeline","algorithm_version":VERSION,"schema_version":"ofi-v1","adapter_version":config.adapter_version,"dataset_identity":sources,"raw_sources":raw_hashes,"config":config,"units":{"prices":"USD","price_changes":"USD and ticks","volume_depth_ofi_ti":"shares","timestamp":"UTC nanoseconds"},"semantics":{"buckets":"(start, end], anchored at New York session open; first incomplete excluded","boundary":"last original row at/before boundary, including rejected rows and tied event order","ofi":"rank-based L1..L5 extension; unknown initialization excluded","depth":"mean over L1 updates; right-boundary fallback","trade_signing":config.trade_signing,"lags":"sparse accepted intervals require actual temporal-adjacency checks"},"input_passes":"clean inputs: one streaming SHA-256 pass plus one ordered computation pass; Quote Test ZIPs: bounded-memory extraction to temporary disk then one paired-row pass, plus source hashing; no reference-feature reads"});
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
        warnings,
    };
    write_json(
        &transaction.stage.path().join("quality_report.json"),
        &report,
    )?;
    transaction.publish()?;
    Ok(report)
}
