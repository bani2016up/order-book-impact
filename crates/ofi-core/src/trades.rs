//! Independent execution signing and checked volume conservation.
use crate::{
    domain::{Key, Trade},
    error::{Error, ErrorCode, Result, checked_i64},
};
use serde::Serialize;

#[derive(Debug, Default, Clone, Serialize)]
pub struct TradeTotals {
    pub volume: i64,
    pub trade_imbalance: i64,
    pub trade_count: i64,
    pub classified_count: i64,
    pub unclassified_count: i64,
    pub classified_volume: i64,
    pub unclassified_volume: i64,
}
impl TradeTotals {
    pub fn add(&mut self, trade: &Trade, sign: Option<i64>) -> Result<()> {
        trade.validate()?;
        if sign.is_some_and(|s| ![-1, 1].contains(&s)) {
            return Err(Error::new(
                ErrorCode::Malformed,
                "trade sign must be -1/+1 or unknown",
            ));
        }
        // Build a complete next state so failed arithmetic leaves the accumulator intact.
        let mut next = self.clone();
        next.volume = checked_i64(
            i128::from(self.volume) + i128::from(trade.size),
            "trade volume overflow",
        )?;
        next.trade_count = self
            .trade_count
            .checked_add(1)
            .ok_or_else(|| Error::new(ErrorCode::Overflow, "trade count overflow"))?;
        if let Some(sign) = sign {
            next.trade_imbalance = checked_i64(
                i128::from(self.trade_imbalance) + i128::from(sign) * i128::from(trade.size),
                "trade imbalance overflow",
            )?;
            next.classified_count = self
                .classified_count
                .checked_add(1)
                .ok_or_else(|| Error::new(ErrorCode::Overflow, "classified count overflow"))?;
            next.classified_volume = checked_i64(
                i128::from(self.classified_volume) + i128::from(trade.size),
                "classified volume overflow",
            )?;
        } else {
            next.unclassified_count = self
                .unclassified_count
                .checked_add(1)
                .ok_or_else(|| Error::new(ErrorCode::Overflow, "unclassified count overflow"))?;
            next.unclassified_volume = checked_i64(
                i128::from(self.unclassified_volume) + i128::from(trade.size),
                "unclassified volume overflow",
            )?;
        }
        *self = next;
        Ok(())
    }
    pub fn merge(&mut self, other: &Self) -> Result<()> {
        macro_rules! add {($($field:ident),+) => {$(self.$field=checked_i64(i128::from(self.$field)+i128::from(other.$field),concat!(stringify!($field)," total overflow"))?;)+};}
        add!(
            volume,
            trade_imbalance,
            trade_count,
            classified_count,
            unclassified_count,
            classified_volume,
            unclassified_volume
        );
        Ok(())
    }
}

/// Separate sequencing prevents any execution being counted twice.
#[derive(Default)]
pub struct TradeSequence {
    last: Option<Key>,
}
impl TradeSequence {
    pub fn observe(&mut self, trade: &Trade) -> Result<i64> {
        trade.validate()?;
        if self.last.as_ref().is_some_and(|k| &trade.key <= k) {
            return Err(Error::new(
                ErrorCode::Order,
                format!("duplicate/unordered execution {:?}", trade.key),
            ));
        }
        self.last = Some(trade.key.clone());
        Ok(-trade.direction)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn t(id: i64, size: i64, direction: i64, event_type: i64) -> Trade {
        Trade {
            key: Key {
                symbol: "A".into(),
                date: "2012-06-21".into(),
                event_id: id,
            },
            timestamp: id,
            size,
            price: 10000,
            direction,
            event_type,
            quote_accepted: false,
        }
    }
    #[test]
    fn both_execution_types_rejected_quotes_and_conservation() {
        let mut totals = TradeTotals::default();
        let mut sequence = TradeSequence::default();
        for trade in [t(0, 30, -1, 4), t(1, 10, 1, 5), t(2, 7, -1, 5)] {
            let sign = sequence.observe(&trade).unwrap();
            totals.add(&trade, Some(sign)).unwrap();
        }
        assert_eq!(totals.volume, 47);
        assert_eq!(totals.trade_imbalance, 27);
        assert_eq!(totals.classified_volume, 47);
        assert_eq!(totals.unclassified_volume, 0);
        assert_eq!(totals.trade_count, 3);
        assert!(totals.trade_imbalance.unsigned_abs() <= totals.volume as u64);
        assert!(sequence.observe(&t(2, 7, -1, 5)).is_err());
        totals.add(&t(3, 11, -1, 5), None).unwrap();
        assert_eq!(totals.unclassified_count, 1);
        assert_eq!(totals.unclassified_volume, 11);
        assert_eq!(totals.volume, 58);
        assert_eq!(
            totals.classified_volume + totals.unclassified_volume,
            totals.volume
        );
        let mut combined = TradeTotals::default();
        combined.merge(&totals).unwrap();
        assert_eq!(combined.volume, 58);
        assert_eq!(combined.trade_count, 4);
        assert!(totals.add(&t(4, 1, 1, 4), Some(0)).is_err());
        assert!(sequence.observe(&t(4, 0, 1, 4)).is_err());
    }
    #[test]
    fn accumulation_overflow_is_checked() {
        let trade = t(0, 1, 1, 4);
        for original in [
            TradeTotals {
                volume: i64::MAX,
                ..TradeTotals::default()
            },
            TradeTotals {
                trade_count: i64::MAX,
                ..TradeTotals::default()
            },
            TradeTotals {
                trade_imbalance: i64::MAX,
                ..TradeTotals::default()
            },
            TradeTotals {
                classified_count: i64::MAX,
                ..TradeTotals::default()
            },
            TradeTotals {
                classified_volume: i64::MAX,
                ..TradeTotals::default()
            },
        ] {
            let mut total = original.clone();
            assert_eq!(
                total.add(&trade, Some(1)).unwrap_err().code,
                ErrorCode::Overflow
            );
            assert_eq!(total.volume, original.volume);
        }
        for original in [
            TradeTotals {
                unclassified_count: i64::MAX,
                ..TradeTotals::default()
            },
            TradeTotals {
                unclassified_volume: i64::MAX,
                ..TradeTotals::default()
            },
        ] {
            let mut total = original;
            assert_eq!(
                total.add(&trade, None).unwrap_err().code,
                ErrorCode::Overflow
            );
        }
        let mut totals = TradeTotals {
            volume: i64::MAX,
            ..TradeTotals::default()
        };
        assert!(
            totals
                .merge(&TradeTotals {
                    volume: 1,
                    ..TradeTotals::default()
                })
                .is_err()
        );
    }
}
