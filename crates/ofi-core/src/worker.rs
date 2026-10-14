//! Bounded independent-partition workers; one queued chunk per worker.
use crate::{
    buckets::{BucketEngine, BucketRow},
    config::Config,
    domain::{Event, Quality, Trade},
    error::{Error, ErrorCode, Result},
    output::Writer,
    pipeline::PartitionReport,
    raw::{RawInput, RawReader, quote_test},
    trades::TradeSequence,
};
use std::{
    path::Path,
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
        mpsc::{SyncSender, sync_channel},
    },
    thread::{self, JoinHandle},
};

pub struct InputRow {
    pub quality: Quality,
    pub event: Option<Event>,
    pub trade: Option<Trade>,
}
#[derive(Default)]
pub struct WorkerStats {
    active: AtomicUsize,
    peak: AtomicUsize,
}
impl WorkerStats {
    pub fn peak(&self) -> usize {
        self.peak.load(Ordering::SeqCst)
    }
}
struct Active(Arc<WorkerStats>);
impl Active {
    fn new(stats: Arc<WorkerStats>) -> Self {
        let active = stats.active.fetch_add(1, Ordering::SeqCst) + 1;
        stats.peak.fetch_max(active, Ordering::SeqCst);
        Self(stats)
    }
}
impl Drop for Active {
    fn drop(&mut self) {
        self.0.active.fetch_sub(1, Ordering::SeqCst);
    }
}

pub struct Worker {
    directory: tempfile::TempDir,
    sender: Option<SyncSender<Vec<InputRow>>>,
    handle: Option<JoinHandle<Result<PartitionReport>>>,
}
impl Worker {
    pub fn spawn(
        symbol: String,
        date: String,
        config: Config,
        raw: Option<RawInput>,
        stage: &Path,
        stats: Arc<WorkerStats>,
    ) -> Result<Self> {
        let directory = tempfile::Builder::new()
            .prefix(".ofi-partition-")
            .tempdir_in(stage)?;
        let path = directory.path().to_owned();
        let (tx, rx) = sync_channel::<Vec<InputRow>>(1);
        let handle = thread::Builder::new()
            .name(format!("ofi-{symbol}-{date}"))
            .spawn(move || {
                let _active = Active::new(stats);
                let mut report = PartitionReport {
                    symbol: symbol.clone(),
                    date: date.clone(),
                    ..PartitionReport::default()
                };
                let mut engine = BucketEngine::new(&symbol, &date, &config)?;
                let mut writer = Writer::new(&path, config.levels, config.chunk_rows)?;
                let mut raw = raw
                    .as_ref()
                    .map(|r| RawReader::open(r, &path))
                    .transpose()?;
                let mut sequence = TradeSequence::default();
                let emit = |row: BucketRow,
                            report: &mut PartitionReport,
                            writer: &mut Writer|
                 -> Result<()> {
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
                };
                for chunk in rx {
                    for input in chunk {
                        let q = &input.quality;
                        let event = input.event.as_ref();
                        let trade = input.trade.as_ref();
                        report.original_rows += 1;
                        report.clean_events += u64::from(q.accepted);
                        report.rejected_events += u64::from(!q.accepted);
                        if !q.accepted {
                            *report
                                .source_rejection_reasons
                                .entry(q.reason.clone())
                                .or_default() += 1;
                        }
                        let raw_row = raw.as_mut().map(|r| r.observe(q)).transpose()?;
                        if let Some(event) = event {
                            if event.execution.as_ref() != trade {
                                return Err(Error::new(
                                    ErrorCode::Quality,
                                    format!(
                                        "accepted execution/trade table disagreement at {:?}",
                                        q.key
                                    ),
                                ));
                            }
                            report.rounded_event_timestamps +=
                                u64::from(event.timestamp_rounded == Some(true));
                            report.missing_precision_flag_rows +=
                                u64::from(event.timestamp_rounded.is_none());
                        }
                        if let Some((row, _)) = &raw_row {
                            report.rounded_raw_timestamps += u64::from(row.rounded);
                        }
                        if let (Some(event), Some((row, _))) = (event, &raw_row) {
                            let book = row.book.as_ref().ok_or_else(|| {
                                Error::new(
                                    ErrorCode::Quality,
                                    "accepted clean book has invalid raw post-state",
                                )
                            })?;
                            if book.0.len() < config.levels
                                || book.0[..config.levels] != event.book.0
                            {
                                return Err(Error::new(
                                    ErrorCode::Quality,
                                    format!("clean/raw post-state mismatch at {:?}", q.key),
                                ));
                            }
                        }
                        let sign = if let Some(t) = trade {
                            let known = sequence.observe(t)?;
                            let sign = if let Some((row, pre)) = &raw_row {
                                quote_test(t, row, pre.as_ref())?
                            } else {
                                Some(known)
                            };
                            report.signing.add(t, sign).map_err(|error| {
                                Error::new(
                                    error.code,
                                    format!(
                                        "{} at {:?}, UTC ns {}",
                                        error.message, q.key, q.timestamp
                                    ),
                                )
                            })?;
                            sign
                        } else {
                            None
                        };
                        engine.observe(q, event, trade.map(|t| (t, sign)), &mut |row| {
                            emit(row, &mut report, &mut writer)
                        })?;
                    }
                }
                engine.finish(&mut |row| emit(row, &mut report, &mut writer))?;
                if let Some(mut raw) = raw {
                    raw.finish()?;
                }
                writer.finish()?;
                Ok(report)
            })?;
        Ok(Self {
            directory,
            sender: Some(tx),
            handle: Some(handle),
        })
    }
    pub fn send(&mut self, rows: Vec<InputRow>) -> Result<()> {
        if self
            .sender
            .as_ref()
            .expect("open worker sender")
            .send(rows)
            .is_err()
        {
            self.close();
            return match self.handle.take().expect("worker handle").join() {
                Ok(Err(error)) => Err(error),
                _ => Err(Error::new(
                    ErrorCode::Io,
                    "partition worker disconnected or panicked",
                )),
            };
        }
        Ok(())
    }
    pub fn close(&mut self) {
        self.sender.take();
    }
    pub fn finish(mut self, output: &mut Writer) -> Result<PartitionReport> {
        self.close();
        let report = self
            .handle
            .take()
            .expect("worker handle")
            .join()
            .map_err(|_| Error::new(ErrorCode::Io, "partition worker panicked"))??;
        output.append_partition(self.directory.path())?;
        Ok(report)
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
        self.close();
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn dependency_panic_is_typed_and_joined() {
        let directory = tempfile::tempdir().unwrap();
        let (tx, rx) = sync_channel(1);
        drop(rx);
        let handle =
            thread::spawn(|| -> Result<PartitionReport> { panic!("simulated dependency panic") });
        let mut worker = Worker {
            directory,
            sender: Some(tx),
            handle: Some(handle),
        };
        assert_eq!(worker.send(vec![]).unwrap_err().code, ErrorCode::Io);
    }
}
