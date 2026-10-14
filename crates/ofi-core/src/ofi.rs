//! Rank-based OFI; unknown segment initialization is distinct from zero.
use crate::{
    domain::{Book, Event, Key, Quality},
    error::{Error, ErrorCode, Result, checked_i64},
};

pub fn contribution(previous: &Book, current: &Book) -> Result<Vec<i64>> {
    previous.validate()?;
    current.validate()?;
    if previous.0.len() != current.0.len() {
        return Err(Error::new(ErrorCode::Schema, "book depths disagree"));
    }
    previous
        .0
        .iter()
        .zip(&current.0)
        .map(|(p, c)| {
            let mut value = 0_i128;
            if c.bid >= p.bid {
                value += i128::from(c.bid_size);
            }
            if c.bid <= p.bid {
                value -= i128::from(p.bid_size);
            }
            if c.ask <= p.ask {
                value -= i128::from(c.ask_size);
            }
            if c.ask >= p.ask {
                value += i128::from(p.ask_size);
            }
            checked_i64(value, "OFI transition exceeds signed int64")
        })
        .collect()
}

#[derive(Default)]
pub struct OfiState {
    previous: Option<Book>,
    last_original: Option<Key>,
    segment: i64,
}

impl OfiState {
    /// Call once for every original quality row, in order, across batch boundaries.
    pub fn observe(
        &mut self,
        quality: &Quality,
        event: Option<&Event>,
    ) -> Result<Option<Vec<i64>>> {
        if self.last_original.as_ref().is_some_and(|k| {
            k.symbol != quality.key.symbol
                || k.date != quality.key.date
                || i128::from(k.event_id) + 1 != i128::from(quality.key.event_id)
        }) {
            return Err(Error::new(
                ErrorCode::Order,
                format!(
                    "OFI requires contiguous original order at {:?}",
                    quality.key
                ),
            ));
        }
        if quality.accepted != event.is_some() {
            return Err(Error::new(
                ErrorCode::Quality,
                format!(
                    "accepted-book/quality presence disagree at {:?}",
                    quality.key
                ),
            ));
        }
        let transition = if let Some(event) = event {
            event.book.validate()?;
            if event.key != quality.key || event.timestamp != quality.timestamp {
                return Err(Error::new(
                    ErrorCode::Quality,
                    format!("event/quality ID or time mismatch at {:?}", quality.key),
                ));
            }
            if event.prev_available != self.previous.is_some() {
                return Err(Error::new(
                    ErrorCode::Quality,
                    format!(
                        "prev_state_available contradicts original quality at {:?}",
                        quality.key
                    ),
                ));
            }
            let result = if let Some(previous) = &self.previous {
                if event.segment != self.segment {
                    return Err(Error::new(
                        ErrorCode::Quality,
                        format!("unexpected segment change at {:?}", quality.key),
                    ));
                }
                if (event.book.0[0] != previous.0[0]) != event.l1_update {
                    return Err(Error::new(
                        ErrorCode::Quality,
                        format!("is_quote_update contradicts L1 change at {:?}", quality.key),
                    ));
                }
                Some(contribution(previous, &event.book)?)
            } else {
                self.segment = self
                    .segment
                    .checked_add(1)
                    .ok_or_else(|| Error::new(ErrorCode::Overflow, "segment count overflow"))?;
                if event.segment != self.segment {
                    return Err(Error::new(
                        ErrorCode::Quality,
                        format!("segment initialization mismatch at {:?}", quality.key),
                    ));
                }
                None
            };
            if let Some(previous) = &mut self.previous {
                previous.0.clone_from(&event.book.0);
            } else {
                self.previous = Some(event.book.clone());
            }
            result
        } else {
            self.previous = None;
            None
        };
        if let Some(last) = &mut self.last_original {
            last.reuse_from(&quality.key);
        } else {
            self.last_original = Some(quality.key.clone());
        }
        Ok(transition)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::Level;
    fn level() -> Level {
        Level {
            bid: 10000,
            ask: 10200,
            bid_size: 100,
            ask_size: 120,
        }
    }
    #[test]
    fn hand_calculated_bid_ask_cases() {
        let p = level();
        let prev = Book(vec![p]);
        for (c, expected) in [
            (Level { bid_size: 130, ..p }, 30),
            (Level { bid_size: 70, ..p }, -30),
            (p, 0),
            (Level { ask_size: 100, ..p }, 20),
            (Level { ask_size: 140, ..p }, -20),
            (
                Level {
                    bid: 10100,
                    bid_size: 37,
                    ..p
                },
                37,
            ),
            (Level { bid: 9900, ..p }, -100),
            (
                Level {
                    ask: 10100,
                    ask_size: 43,
                    ..p
                },
                -43,
            ),
            (Level { ask: 10300, ..p }, 120),
            (
                Level {
                    bid_size: 130,
                    ask_size: 100,
                    ..p
                },
                50,
            ),
            (
                Level {
                    bid: 10100,
                    ask: 10300,
                    bid_size: 37,
                    ..p
                },
                157,
            ),
        ] {
            assert_eq!(contribution(&prev, &Book(vec![c])).unwrap(), vec![expected]);
        }
    }
    #[test]
    fn symmetric_and_unchanged_invariants() {
        let p = level();
        let mirror = |l: Level| Level {
            bid: 30000 - l.ask,
            ask: 30000 - l.bid,
            bid_size: l.ask_size,
            ask_size: l.bid_size,
        };
        for bid in [9900, 10000, 10100] {
            for ask in [10200, 10300, 10400] {
                for size in [1, 30, 100, 1000] {
                    let c = Level {
                        bid,
                        ask,
                        bid_size: size,
                        ask_size: 120 + size,
                    };
                    assert_eq!(
                        contribution(&Book(vec![c]), &Book(vec![c])).unwrap(),
                        vec![0]
                    );
                    assert_eq!(
                        contribution(&Book(vec![p]), &Book(vec![c])).unwrap()[0],
                        -contribution(&Book(vec![mirror(p)]), &Book(vec![mirror(c)])).unwrap()[0]
                    );
                }
            }
        }
    }
    #[test]
    fn deep_rank_change_and_checked_overflow() {
        let p = level();
        let deep = Level {
            bid: 9900,
            ask: 10300,
            ..p
        };
        let prev = Book(vec![p, deep]);
        let cur = Book(vec![
            p,
            Level {
                bid: 9950,
                bid_size: 25,
                ..deep
            },
        ]);
        assert_eq!(contribution(&prev, &cur).unwrap(), vec![0, 25]);
        assert!(contribution(&prev, &Book(vec![p])).is_err());
        let previous = Book(vec![Level {
            ask_size: i64::MAX,
            ..p
        }]);
        let current = Book(vec![Level {
            bid: 10100,
            ask: 10300,
            bid_size: i64::MAX,
            ..p
        }]);
        assert_eq!(
            contribution(&previous, &current).unwrap_err().code,
            ErrorCode::Overflow
        );
    }
    fn q(id: i64, accepted: bool) -> Quality {
        Quality {
            key: Key {
                symbol: "A".into(),
                date: "2012-06-21".into(),
                event_id: id,
            },
            timestamp: id,
            accepted,
            reason: if accepted { "".into() } else { "gap".into() },
        }
    }
    fn event(id: i64, segment: i64, prev: bool) -> Event {
        Event {
            key: q(id, true).key,
            timestamp: id,
            book: Book(vec![level()]),
            segment,
            prev_available: prev,
            l1_update: false,
            timestamp_rounded: None,
            execution: None,
        }
    }
    #[test]
    fn first_segment_gap_and_persistent_state() {
        let mut s = OfiState::default();
        let first = event(0, 1, false);
        assert_eq!(s.observe(&q(0, true), Some(&first)).unwrap(), None);
        assert_eq!(
            s.observe(&q(1, true), Some(&event(1, 1, true))).unwrap(),
            Some(vec![0])
        );
        assert_eq!(s.observe(&q(2, false), None).unwrap(), None);
        assert_eq!(
            s.observe(&q(3, true), Some(&event(3, 2, false))).unwrap(),
            None
        );
        assert_eq!(
            s.observe(&q(4, true), Some(&event(4, 2, true))).unwrap(),
            Some(vec![0])
        );
    }
    #[test]
    fn retained_books_are_owned_and_failed_calls_keep_historical_state_effects() {
        let mut state = OfiState::default();
        // Standalone OFI state historically permits a nonzero first original ID.
        let mut first = event(7, 1, false);
        state.observe(&q(7, true), Some(&first)).unwrap();
        first.book.0[0].bid_size = 999;
        let mut second = event(8, 1, true);
        second.book.0[0].bid_size = 130;
        second.l1_update = true;
        assert_eq!(
            state.observe(&q(8, true), Some(&second)).unwrap(),
            Some(vec![30])
        );
        let mut third = event(9, 2, true);
        third.book.0[0].bid_size = 150;
        third.l1_update = true;
        assert!(state.observe(&q(9, true), Some(&third)).is_err());
        third.segment = 1;
        assert_eq!(
            state.observe(&q(9, true), Some(&third)).unwrap(),
            Some(vec![20])
        );
        // Neither caller-owned input is overwritten by retained buffer reuse.
        assert_eq!(second.book.0[0].bid_size, 130);
        assert_eq!(first.book.0[0].bid_size, 999);
        state.observe(&q(10, false), None).unwrap();
        assert!(
            state
                .observe(&q(11, true), Some(&event(11, 5, false)))
                .is_err()
        );
        // Initialization increments the segment before reporting its mismatch.
        assert_eq!(
            state
                .observe(&q(11, true), Some(&event(11, 3, false)))
                .unwrap(),
            None
        );
        assert_eq!(
            state
                .observe(&q(12, true), Some(&event(12, 3, true)))
                .unwrap(),
            Some(vec![0])
        );
    }
    #[test]
    fn inconsistent_alignment_markers_and_segments_fail() {
        let mut s = OfiState::default();
        assert!(s.observe(&q(0, true), None).is_err());
        assert!(s.observe(&q(0, false), Some(&event(0, 1, false))).is_err());
        assert!(s.observe(&q(0, true), Some(&event(1, 1, false))).is_err());
        assert!(
            s.observe(
                &q(0, true),
                Some(&Event {
                    timestamp: 9,
                    ..event(0, 1, false)
                })
            )
            .is_err()
        );
        assert!(s.observe(&q(0, true), Some(&event(0, 1, true))).is_err());
        let mut s = OfiState::default();
        assert!(s.observe(&q(0, true), Some(&event(0, 2, false))).is_err());
        let mut s = OfiState::default();
        s.observe(&q(0, true), Some(&event(0, 1, false))).unwrap();
        assert!(s.observe(&q(2, true), Some(&event(2, 1, true))).is_err());
        assert!(s.observe(&q(1, true), Some(&event(1, 2, true))).is_err());
        assert!(
            s.observe(
                &q(1, true),
                Some(&Event {
                    l1_update: true,
                    ..event(1, 1, true)
                })
            )
            .is_err()
        );
    }
}
