//! Checked prices, books and original event order.
use crate::error::{Error, ErrorCode, Result};

pub const PRICE_SCALE: f64 = 10_000.0;

pub fn price_units(usd: f64) -> Result<i64> {
    let scaled = usd * PRICE_SCALE;
    if !scaled.is_finite() || scaled <= 0.0 || scaled > 9_007_199_254_740_991.0 {
        return Err(Error::new(
            ErrorCode::Overflow,
            format!("price {usd} is nonpositive, nonfinite or exceeds exact integer precision"),
        ));
    }
    if (scaled - scaled.round()).abs() > 0.000001 {
        return Err(Error::new(
            ErrorCode::Malformed,
            format!("USD price {usd} is not representable in USD/10000 units"),
        ));
    }
    Ok(scaled.round() as i64)
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct Key {
    pub symbol: String,
    pub date: String,
    pub event_id: i64,
}

impl Key {
    pub(crate) fn reuse_from(&mut self, key: &Self) {
        self.symbol.clone_from(&key.symbol);
        self.date.clone_from(&key.date);
        self.event_id = key.event_id;
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct Level {
    pub bid: i64,
    pub ask: i64,
    pub bid_size: i64,
    pub ask_size: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Book(pub Vec<Level>);

impl Book {
    pub fn validate(&self) -> Result<()> {
        if self.0.is_empty() || self.0.len() > 5 {
            return Err(Error::new(
                ErrorCode::Schema,
                "book must contain 1..5 levels",
            ));
        }
        for (i, l) in self.0.iter().enumerate() {
            if l.bid <= 0
                || l.ask <= l.bid
                || l.bid_size <= 0
                || l.ask_size <= 0
                || (i > 0 && (l.bid >= self.0[i - 1].bid || l.ask <= self.0[i - 1].ask))
            {
                return Err(Error::new(
                    ErrorCode::Malformed,
                    format!("invalid book at rank {}", i + 1),
                ));
            }
        }
        Ok(())
    }
    pub fn mid_units_twice(&self) -> i128 {
        i128::from(self.0[0].bid) + i128::from(self.0[0].ask)
    }
    pub fn depth_twice(&self) -> i128 {
        i128::from(self.0[0].bid_size) + i128::from(self.0[0].ask_size)
    }
}

#[derive(Debug, Clone)]
pub struct Event {
    pub key: Key,
    pub timestamp: i64,
    pub book: Book,
    pub segment: i64,
    pub prev_available: bool,
    pub l1_update: bool,
    pub timestamp_rounded: Option<bool>,
    pub execution: Option<Trade>,
}
#[derive(Debug, Clone)]
pub struct Quality {
    pub key: Key,
    pub timestamp: i64,
    pub accepted: bool,
    pub reason: String,
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Trade {
    pub key: Key,
    pub timestamp: i64,
    pub size: i64,
    pub price: i64,
    pub direction: i64,
    pub event_type: i64,
    pub quote_accepted: bool,
}

impl Trade {
    pub fn validate(&self) -> Result<()> {
        if ![4, 5].contains(&self.event_type)
            || (![-1, 1].contains(&self.direction)
                && !(self.event_type == 5 && self.direction == 0))
            || self.size <= 0
            || self.price <= 0
        {
            return Err(Error::new(
                ErrorCode::Malformed,
                format!("invalid execution {:?}", self.key),
            ));
        }
        Ok(())
    }
}

#[derive(Default)]
pub struct OrderGuard {
    last: Option<(Key, i64)>,
}
impl OrderGuard {
    pub fn observe(&mut self, key: &Key, timestamp: i64, contiguous: bool) -> Result<()> {
        if key.symbol.is_empty() || key.event_id < 0 {
            return Err(Error::new(ErrorCode::Order, format!("invalid key {key:?}")));
        }
        let new_partition = self
            .last
            .as_ref()
            .is_none_or(|(prior, _)| prior.symbol != key.symbol || prior.date != key.date);
        if contiguous && new_partition && key.event_id != 0 {
            return Err(Error::new(
                ErrorCode::Quality,
                format!("original quality evidence must start at event_id 0 for {key:?}"),
            ));
        }
        if let Some((prior, time)) = &self.last {
            let same = prior.symbol == key.symbol && prior.date == key.date;
            if key <= prior
                || (same
                    && (timestamp < *time
                        || (contiguous
                            && i128::from(key.event_id) != i128::from(prior.event_id) + 1)))
            {
                return Err(Error::new(
                    ErrorCode::Order,
                    format!("unordered/duplicate/missing original row {key:?} after {prior:?}"),
                ));
            }
        }
        if let Some((prior, time)) = &mut self.last {
            prior.reuse_from(key);
            *time = timestamp;
        } else {
            self.last = Some((key.clone(), timestamp));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn prices_books_and_half_ticks() {
        assert_eq!(price_units(585.93).unwrap(), 5_859_300);
        for p in [0.0, -1.0, f64::NAN, f64::INFINITY, 1e20, 0.00001] {
            assert!(price_units(p).is_err());
        }
        let l = Level {
            bid: 10000,
            ask: 10100,
            bid_size: 100,
            ask_size: 121,
        };
        let book = Book(vec![l]);
        book.validate().unwrap();
        assert_eq!(book.mid_units_twice(), 20100);
        assert_eq!(book.depth_twice(), 221);
        assert!(Book(vec![]).validate().is_err());
        assert!(Book(vec![l; 6]).validate().is_err());
        for bad in [
            Level { bid: 0, ..l },
            Level { ask: 10000, ..l },
            Level { bid_size: 0, ..l },
            Level { ask_size: 0, ..l },
        ] {
            assert!(Book(vec![bad]).validate().is_err());
        }
        assert!(Book(vec![l, l]).validate().is_err());
        assert!(
            Book(vec![
                l,
                Level {
                    bid: 9900,
                    ask: 10100,
                    ..l
                }
            ])
            .validate()
            .is_err()
        );
        Book(vec![
            l,
            Level {
                bid: 9900,
                ask: 10200,
                ..l
            },
        ])
        .validate()
        .unwrap();
    }
    #[test]
    fn order_ties_duplicates_gaps_and_partitions() {
        let key = |s: &str, id| Key {
            symbol: s.into(),
            date: "2012-06-21".into(),
            event_id: id,
        };
        assert!(
            OrderGuard::default()
                .observe(&key("A", 1), 1, true)
                .is_err()
        );
        let mut g = OrderGuard::default();
        g.observe(&key("A", 0), 1, true).unwrap();
        g.observe(&key("A", 1), 1, true).unwrap();
        assert!(g.observe(&key("A", 1), 1, true).is_err());
        assert!(g.observe(&key("A", 2), 0, true).is_err());
        assert!(g.observe(&key("A", 3), 2, true).is_err());
        g.observe(&key("A", 3), 2, false).unwrap();
        g.observe(&key("B", 0), 0, true).unwrap();
        assert!(g.observe(&key("A", 4), 3, false).is_err());
        assert!(g.observe(&key("", 0), 1, false).is_err());
        assert!(g.observe(&key("B", -1), 1, false).is_err());
    }
    #[test]
    fn reused_order_keys_remain_owned_and_failures_preserve_previous_state() {
        let mut guard = OrderGuard::default();
        let mut source = Key {
            symbol: "A_long_symbol".into(),
            date: "2012-06-21".into(),
            event_id: 0,
        };
        guard.observe(&source, 10, true).unwrap();
        let original = source.clone();
        source.symbol = "Z".into();
        source.date = "later".into();
        assert_eq!(guard.last.as_ref().unwrap().0, original);
        for (symbol, date) in [
            ("B", "2012-06-21"),
            ("C_much_longer_symbol", "2012-06-21"),
            ("D", "short"),
        ] {
            let mut key = Key {
                symbol: symbol.into(),
                date: date.into(),
                event_id: 0,
            };
            guard.observe(&key, 10, true).unwrap();
            key.event_id = 1;
            guard.observe(&key, 10, true).unwrap();
            let saved = guard.last.clone();
            assert!(guard.observe(&key, 10, true).is_err());
            key.event_id = 2;
            assert!(guard.observe(&key, 9, true).is_err());
            key.event_id = 3;
            assert!(guard.observe(&key, 11, true).is_err());
            assert_eq!(guard.last, saved);
            key.event_id = 2;
            guard.observe(&key, 11, true).unwrap();
            assert_eq!(guard.last.as_ref().unwrap(), &(key, 11));
        }
    }
    #[test]
    fn execution_validation() {
        let t = Trade {
            key: Key {
                symbol: "A".into(),
                date: "2012-06-21".into(),
                event_id: 1,
            },
            timestamp: 0,
            size: 1,
            price: 1,
            direction: 1,
            event_type: 4,
            quote_accepted: false,
        };
        t.validate().unwrap();
        Trade {
            event_type: 5,
            direction: 0,
            ..t.clone()
        }
        .validate()
        .unwrap();
        for bad in [
            Trade {
                size: 0,
                ..t.clone()
            },
            Trade {
                price: 0,
                ..t.clone()
            },
            Trade {
                direction: 0,
                ..t.clone()
            },
            Trade {
                event_type: 1,
                ..t.clone()
            },
        ] {
            assert!(bad.validate().is_err());
        }
    }
}
