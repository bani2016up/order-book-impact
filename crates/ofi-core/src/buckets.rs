//! One open right-closed bucket per partition; full-grid output streams to a sink.
use crate::{
    config::Config,
    domain::{Book, Event, OrderGuard, Quality, Trade},
    error::{Error, ErrorCode, Result, checked_i64},
    ofi::OfiState,
    time::NS,
    trades::TradeTotals,
};
use serde::Serialize;
use std::collections::BTreeSet;

#[derive(Debug, Clone, Serialize)]
pub struct Features {
    pub mid_price_start: f64,
    pub mid_price_end: f64,
    pub mid_price_change: f64,
    pub mid_price_change_ticks: f64,
    pub avg_depth: f64,
    pub ofi: Vec<i64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct BucketRow {
    pub symbol: String,
    pub date: String,
    pub interval_start: i64,
    pub timestamp: i64,
    pub accepted: bool,
    pub rejection_reasons: String,
    pub event_count: i64,
    pub rejected_events: i64,
    pub quote_update_count: i64,
    pub trades: TradeTotals,
    pub features: Option<Features>,
}

pub struct BucketEngine {
    symbol: String,
    date: String,
    config: Config,
    open: i64,
    close: i64,
    start: i64,
    end: i64,
    width: i64,
    left: Option<Book>,
    boundary: Option<Book>,
    ofi: Vec<i64>,
    depth_sum: i128,
    quote_updates: i64,
    events: i64,
    bad: i64,
    reasons: BTreeSet<&'static str>,
    trades: TradeTotals,
    state: OfiState,
    order: OrderGuard,
}
impl BucketEngine {
    pub fn new(symbol: &str, date: &str, config: &Config) -> Result<Self> {
        config.validate()?;
        let (open, close) = config.session(date)?;
        let width = config.bucket_seconds * NS;
        Ok(Self {
            symbol: symbol.into(),
            date: date.into(),
            config: config.clone(),
            open,
            close,
            start: open,
            end: checked_i64(
                i128::from(open) + i128::from(width),
                "first boundary overflow",
            )?,
            width,
            left: None,
            boundary: None,
            ofi: vec![0; config.levels],
            depth_sum: 0,
            quote_updates: 0,
            events: 0,
            bad: 0,
            reasons: BTreeSet::new(),
            trades: TradeTotals::default(),
            state: OfiState::default(),
            order: OrderGuard::default(),
        })
    }
    pub fn observe(
        &mut self,
        q: &Quality,
        event: Option<&Event>,
        trade: Option<(&Trade, Option<i64>)>,
        sink: &mut impl FnMut(BucketRow) -> Result<()>,
    ) -> Result<()> {
        if q.key.symbol != self.symbol || q.key.date != self.date {
            return Err(Error::new(
                ErrorCode::Order,
                "partition state cannot cross symbols/dates",
            ));
        }
        if q.timestamp < self.open || q.timestamp > self.close {
            return Err(Error::new(
                ErrorCode::Malformed,
                format!("original row outside configured session {:?}", q.key),
            ));
        }
        self.order.observe(&q.key, q.timestamp, true)?;
        while q.timestamp > self.end {
            self.flush(sink)?;
        }
        let transition = self.state.observe(q, event)?;
        self.events = self
            .events
            .checked_add(1)
            .ok_or_else(|| Error::new(ErrorCode::Overflow, "bucket event count overflow"))?;
        if !q.accepted {
            self.bad = self
                .bad
                .checked_add(1)
                .ok_or_else(|| Error::new(ErrorCode::Overflow, "rejected count overflow"))?;
            self.reasons.insert("rejected_event");
        }
        if let Some(event) = event {
            if event.book.0.len() != self.config.levels {
                return Err(Error::new(
                    ErrorCode::Schema,
                    "event depth differs from requested levels",
                ));
            }
            if let Some(ofi) = transition {
                for (sum, value) in self.ofi.iter_mut().zip(ofi) {
                    *sum =
                        checked_i64(i128::from(*sum) + i128::from(value), "bucket OFI overflow")?;
                }
            } else {
                self.reasons.insert("unknown_transition");
            }
            if event.l1_update {
                self.quote_updates = self
                    .quote_updates
                    .checked_add(1)
                    .ok_or_else(|| Error::new(ErrorCode::Overflow, "L1 update count overflow"))?;
                self.depth_sum = self
                    .depth_sum
                    .checked_add(event.book.depth_twice())
                    .ok_or_else(|| Error::new(ErrorCode::Overflow, "depth sum overflow"))?;
            }
            if let Some(boundary) = &mut self.boundary {
                boundary.0.clone_from(&event.book.0);
            } else {
                self.boundary = Some(event.book.clone());
            }
        } else {
            self.boundary = None;
        }
        if let Some((trade, sign)) = trade {
            if trade.key != q.key
                || trade.timestamp != q.timestamp
                || trade.quote_accepted != q.accepted
            {
                return Err(Error::new(
                    ErrorCode::Quality,
                    format!("trade/quality alignment mismatch {:?}", q.key),
                ));
            }
            self.trades.add(trade, sign)?;
        }
        Ok(())
    }
    fn flush(&mut self, sink: &mut impl FnMut(BucketRow) -> Result<()>) -> Result<()> {
        if self.start == self.open {
            self.reasons.insert("first_incomplete_bucket");
        }
        if self.left.is_none() {
            self.reasons.insert("invalid_or_missing_left_boundary");
        }
        if self.boundary.is_none() {
            self.reasons.insert("invalid_or_missing_right_boundary");
        }
        let accepted = self.reasons.is_empty();
        let features = if accepted {
            let left = self.left.as_ref().expect("validated left boundary");
            let right = self.boundary.as_ref().expect("validated right boundary");
            let delta = right.mid_units_twice() - left.mid_units_twice();
            let change = delta as f64 / 20_000.0;
            Some(Features {
                mid_price_start: left.mid_units_twice() as f64 / 20_000.0,
                mid_price_end: right.mid_units_twice() as f64 / 20_000.0,
                mid_price_change: change,
                mid_price_change_ticks: change / self.config.tick_size,
                avg_depth: if self.quote_updates > 0 {
                    self.depth_sum as f64 / (2.0 * self.quote_updates as f64)
                } else {
                    right.depth_twice() as f64 / 2.0
                },
                ofi: self.ofi.clone(),
            })
        } else {
            None
        };
        sink(BucketRow {
            symbol: self.symbol.clone(),
            date: self.date.clone(),
            interval_start: self.start,
            timestamp: self.end,
            accepted,
            rejection_reasons: self.reasons.iter().copied().collect::<Vec<_>>().join("|"),
            event_count: self.events,
            rejected_events: self.bad,
            quote_update_count: self.quote_updates,
            trades: self.trades.clone(),
            features,
        })?;
        match (&mut self.left, &self.boundary) {
            (Some(left), Some(boundary)) => left.0.clone_from(&boundary.0),
            (_, Some(boundary)) => self.left = Some(boundary.clone()),
            (_, None) => self.left = None,
        }
        self.start = self.end;
        if self.start < self.close {
            self.end = checked_i64(
                i128::from(self.end) + i128::from(self.width),
                "bucket boundary overflow",
            )?;
        }
        self.ofi.fill(0);
        self.depth_sum = 0;
        self.quote_updates = 0;
        self.events = 0;
        self.bad = 0;
        self.reasons.clear();
        self.trades = TradeTotals::default();
        Ok(())
    }
    pub fn finish(&mut self, sink: &mut impl FnMut(BucketRow) -> Result<()>) -> Result<()> {
        while self.start < self.close && self.end <= self.close {
            self.flush(sink)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::{Key, Level};
    fn setup(width: i64) -> (Config, i64) {
        let c = Config {
            levels: 1,
            bucket_seconds: width,
            session_close: "09:32:00".into(),
            ..Config::default()
        };
        let open = c.session("2012-06-21").unwrap().0;
        (c, open)
    }
    fn q(id: i64, t: i64, accepted: bool) -> Quality {
        Quality {
            key: Key {
                symbol: "A".into(),
                date: "2012-06-21".into(),
                event_id: id,
            },
            timestamp: t,
            accepted,
            reason: if accepted { "".into() } else { "spread".into() },
        }
    }
    fn e(q: &Quality, size: i64, segment: i64, prev: bool, update: bool) -> Event {
        Event {
            key: q.key.clone(),
            timestamp: q.timestamp,
            book: Book(vec![Level {
                bid: 10000,
                ask: 10100,
                bid_size: size,
                ask_size: 120,
            }]),
            segment,
            prev_available: prev,
            l1_update: update,
            timestamp_rounded: None,
            execution: None,
        }
    }
    #[test]
    fn exact_boundaries_all_widths_and_empty_fallback() {
        for width in [1, 5, 10, 30, 60] {
            let (c, open) = setup(width);
            let mut engine = BucketEngine::new("A", "2012-06-21", &c).unwrap();
            let mut rows = Vec::new();
            let mut sink = |r| {
                rows.push(r);
                Ok(())
            };
            let first = q(0, open + 1, true);
            engine
                .observe(
                    &first,
                    Some(&e(&first, 100, 1, false, true)),
                    None,
                    &mut sink,
                )
                .unwrap();
            let right = q(1, open + width * NS, true);
            engine
                .observe(
                    &right,
                    Some(&e(&right, 130, 1, true, true)),
                    None,
                    &mut sink,
                )
                .unwrap();
            engine.finish(&mut sink).unwrap();
            assert_eq!(rows.len(), 120 / width as usize);
            assert!(!rows[0].accepted);
            assert_eq!(rows[0].event_count, 2);
            assert!(rows[1].accepted);
            assert_eq!(rows[1].event_count, 0);
            let f = rows[1].features.as_ref().unwrap();
            assert_eq!(f.avg_depth, 125.0);
            assert_eq!(f.ofi, vec![0]);
            assert_eq!(rows.last().unwrap().timestamp, open + 120 * NS);
        }
    }
    #[test]
    fn reused_boundary_books_preserve_emitted_features_and_caller_ownership() {
        let (config, open) = setup(10);
        let mut engine = BucketEngine::new("A", "2012-06-21", &config).unwrap();
        let mut rows = Vec::new();
        for (id, seconds, size) in [(0, 1, 100), (1, 11, 130), (2, 21, 160), (3, 31, 190)] {
            let quality = q(id, open + seconds * NS, true);
            let mut event = e(&quality, size, 1, id > 0, true);
            engine
                .observe(&quality, Some(&event), None, &mut |row| {
                    rows.push(row);
                    Ok(())
                })
                .unwrap();
            // Mutating a prior caller book must not change either retained book.
            event.book.0[0].bid_size = 999;
        }
        let first_valid = rows[1].features.as_ref().unwrap();
        assert_eq!(first_valid.avg_depth, 125.0);
        assert_eq!(first_valid.ofi, vec![30]);
        assert_eq!(rows[2].features.as_ref().unwrap().avg_depth, 140.0);
        let retained = first_valid.clone();
        engine
            .finish(&mut |row| {
                rows.push(row);
                Ok(())
            })
            .unwrap();
        assert_eq!(
            rows[1].features.as_ref().unwrap().avg_depth,
            retained.avg_depth
        );
        assert_eq!(rows[1].features.as_ref().unwrap().ofi, retained.ofi);
        assert_eq!(rows[3].features.as_ref().unwrap().avg_depth, 155.0);
    }
    #[test]
    fn l1_update_weighting_half_tick_and_boundary_membership() {
        let (c, open) = setup(10);
        let mut engine = BucketEngine::new("A", "2012-06-21", &c).unwrap();
        let mut rows = Vec::new();
        let mut sink = |r| {
            rows.push(r);
            Ok(())
        };
        for (id, sec, size, update) in [
            (0, 1, 100, true),
            (1, 10, 100, false),
            (2, 11, 130, true),
            (3, 12, 130, false),
            (4, 20, 110, true),
        ] {
            let q = q(id, open + sec * NS, true);
            let mut event = e(&q, size, 1, id > 0, update);
            if id == 4 {
                event.book.0[0].ask = 10200;
            }
            engine.observe(&q, Some(&event), None, &mut sink).unwrap();
        }
        engine.finish(&mut sink).unwrap();
        let f = rows[1].features.as_ref().unwrap();
        assert_eq!(rows[1].event_count, 3);
        assert_eq!(rows[1].quote_update_count, 2);
        assert_eq!(f.avg_depth, 120.0);
        assert_eq!(f.ofi, vec![130]);
        assert_eq!(f.mid_price_change, 0.005);
        assert_eq!(f.mid_price_change_ticks, 0.5);
    }
    #[test]
    fn rejected_more_recent_boundary_is_not_carried_and_trades_survive() {
        let (c, open) = setup(10);
        let mut engine = BucketEngine::new("A", "2012-06-21", &c).unwrap();
        let mut rows = Vec::new();
        let mut sink = |r| {
            rows.push(r);
            Ok(())
        };
        let first = q(0, open + NS, true);
        engine
            .observe(
                &first,
                Some(&e(&first, 100, 1, false, true)),
                None,
                &mut sink,
            )
            .unwrap();
        let bad = q(1, open + 10 * NS, false);
        let trade = Trade {
            key: bad.key.clone(),
            timestamp: bad.timestamp,
            size: 7,
            price: 10100,
            event_type: 5,
            direction: -1,
            quote_accepted: false,
        };
        engine
            .observe(&bad, None, Some((&trade, Some(1))), &mut sink)
            .unwrap();
        let good = q(2, open + 21 * NS, true);
        engine
            .observe(&good, Some(&e(&good, 100, 2, false, true)), None, &mut sink)
            .unwrap();
        engine.finish(&mut sink).unwrap();
        assert_eq!(rows[0].trades.volume, 7);
        assert!(!rows[0].accepted);
        assert!(!rows[1].accepted);
        assert!(!rows[2].accepted);
        assert!(rows[3].accepted);
        assert!(rows[1].rejection_reasons.contains("right_boundary"));
        assert!(rows[1].features.is_none());
    }
    #[test]
    fn missing_state_ties_order_and_failures() {
        let (c, open) = setup(10);
        let mut engine = BucketEngine::new("A", "2012-06-21", &c).unwrap();
        let mut rows = Vec::new();
        let mut sink = |r| {
            rows.push(r);
            Ok(())
        };
        engine.finish(&mut sink).unwrap();
        assert!(rows.iter().all(|r| !r.accepted));
        let mut rows = Vec::new();
        let mut sink = |r| {
            rows.push(r);
            Ok(())
        };
        let mut engine = BucketEngine::new("A", "2012-06-21", &c).unwrap();
        let q0 = q(0, open + NS, true);
        engine
            .observe(&q0, Some(&e(&q0, 100, 1, false, true)), None, &mut sink)
            .unwrap();
        let q1 = q(1, open + NS, true);
        engine
            .observe(&q1, Some(&e(&q1, 130, 1, true, true)), None, &mut sink)
            .unwrap();
        assert!(
            engine
                .observe(
                    &q(2, open, true),
                    Some(&e(&q1, 100, 1, true, true)),
                    None,
                    &mut sink
                )
                .is_err()
        );
        let mut other = q(2, open + NS, true);
        other.key.symbol = "B".into();
        assert!(engine.observe(&other, None, None, &mut sink).is_err());
        assert!(
            engine
                .observe(&q(2, open - 1, false), None, None, &mut sink)
                .is_err()
        );
        let mut engine = BucketEngine::new("A", "2012-06-21", &c).unwrap();
        let mut fail = |_| Err(Error::new(ErrorCode::Io, "sink failed"));
        assert!(engine.finish(&mut fail).is_err());
    }
    #[test]
    fn mismatched_depth_trade_and_extreme_session_close() {
        let (c, open) = setup(10);
        let first = q(0, open + NS, true);
        let mut engine = BucketEngine::new("A", "2012-06-21", &c).unwrap();
        let mut event = e(&first, 100, 1, false, true);
        event.book.0.push(Level {
            bid: 9900,
            ask: 10200,
            bid_size: 100,
            ask_size: 120,
        });
        let mut sink = |_| Ok(());
        assert_eq!(
            engine
                .observe(&first, Some(&event), None, &mut sink)
                .unwrap_err()
                .code,
            ErrorCode::Schema
        );
        let mut engine = BucketEngine::new("A", "2012-06-21", &c).unwrap();
        let trade = Trade {
            key: q(1, open + NS, true).key,
            timestamp: first.timestamp,
            size: 1,
            price: 10000,
            direction: 1,
            event_type: 4,
            quote_accepted: true,
        };
        assert_eq!(
            engine
                .observe(
                    &first,
                    Some(&e(&first, 100, 1, false, true)),
                    Some((&trade, Some(-1))),
                    &mut sink
                )
                .unwrap_err()
                .code,
            ErrorCode::Quality
        );
        let c = Config {
            bucket_seconds: 1,
            session_open: "18:47:15".into(),
            session_close: "18:47:16".into(),
            ..Config::default()
        };
        let mut extreme = BucketEngine::new("A", "2262-04-11", &c).unwrap();
        extreme.finish(&mut sink).unwrap();
    }
}
