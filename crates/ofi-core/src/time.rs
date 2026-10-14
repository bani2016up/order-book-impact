//! Integer nanoseconds and explicit local-session conversion.
use crate::error::{Error, ErrorCode, Result, checked_i64};
use chrono::{DateTime, NaiveDate, NaiveTime, TimeZone};
use chrono_tz::America::New_York;

pub const NS: i64 = 1_000_000_000;

pub fn local_timestamp(date: &str, clock: &str) -> Result<i64> {
    let date = NaiveDate::parse_from_str(date, "%Y-%m-%d")
        .map_err(|e| Error::new(ErrorCode::Config, format!("invalid session date: {e}")))?;
    let time = NaiveTime::parse_from_str(clock, "%H:%M:%S")
        .map_err(|e| Error::new(ErrorCode::Config, format!("invalid session clock: {e}")))?;
    New_York
        .from_local_datetime(&date.and_time(time))
        .single()
        .ok_or_else(|| {
            Error::new(
                ErrorCode::Config,
                "ambiguous or nonexistent New York session time",
            )
        })?
        .timestamp_nanos_opt()
        .ok_or_else(|| {
            Error::new(
                ErrorCode::Overflow,
                "session timestamp exceeds UTC nanoseconds",
            )
        })
}

pub fn date_for_timestamp(timestamp: i64) -> String {
    DateTime::from_timestamp_nanos(timestamp)
        .with_timezone(&New_York)
        .format("%Y-%m-%d")
        .to_string()
}

pub fn timestamp_from_text(text: &str) -> Result<i64> {
    if text
        .split_once('.')
        .is_some_and(|(_, fraction)| fraction.bytes().take_while(u8::is_ascii_digit).count() > 9)
    {
        return Err(Error::new(
            ErrorCode::Schema,
            "clean CSV timestamp has subnanosecond precision; use delivered rounded UTC nanoseconds",
        ));
    }
    let stamp = DateTime::parse_from_rfc3339(text).map_err(|e| {
        Error::new(
            ErrorCode::Malformed,
            format!("invalid RFC3339 timestamp {text}: {e}"),
        )
    })?;
    if stamp.offset().local_minus_utc() != 0 {
        return Err(Error::new(
            ErrorCode::Schema,
            "CSV timestamp must have UTC offset",
        ));
    }
    stamp
        .timestamp_nanos_opt()
        .ok_or_else(|| Error::new(ErrorCode::Overflow, "CSV timestamp overflow"))
}

/// Raw LOBSTER seconds: decimal half-up at the tenth digit, matching Lev.
pub fn decimal_seconds_ns(text: &str) -> Result<(i64, bool)> {
    let (whole, fraction) = text.split_once('.').unwrap_or((text, ""));
    if whole.is_empty()
        || !whole
            .bytes()
            .chain(fraction.bytes())
            .all(|b| b.is_ascii_digit())
    {
        return Err(Error::new(
            ErrorCode::Malformed,
            format!("invalid raw decimal time: {text}"),
        ));
    }
    let whole: i128 = whole
        .parse()
        .map_err(|_| Error::new(ErrorCode::Overflow, "raw time integer overflow"))?;
    let mut nanos = 0_i128;
    for i in 0..9 {
        nanos = nanos * 10 + i128::from(fraction.as_bytes().get(i).map_or(0, |b| b - b'0'));
    }
    if fraction.as_bytes().get(9).is_some_and(|b| *b >= b'5') {
        nanos += 1;
    }
    let value = whole
        .checked_mul(i128::from(NS))
        .and_then(|w| w.checked_add(nanos))
        .ok_or_else(|| Error::new(ErrorCode::Overflow, "raw decimal time overflow"))?;
    Ok((
        checked_i64(value, "raw decimal time overflow")?,
        fraction.len() > 9,
    ))
}

pub fn validate_local_ns(date: &str, timestamp: i64, time_ns: i64) -> Result<()> {
    if !(0..86_400 * NS).contains(&time_ns) {
        return Err(Error::new(
            ErrorCode::Malformed,
            "time_ns is outside local day",
        ));
    }
    let expected = checked_i64(
        i128::from(local_timestamp(date, "00:00:00")?) + i128::from(time_ns),
        "local timestamp overflow",
    )?;
    if expected != timestamp {
        return Err(Error::new(
            ErrorCode::Schema,
            format!("timestamp/time_ns disagree on {date}: {timestamp} vs {expected}"),
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sessions_and_dst() {
        assert_eq!(
            local_timestamp("2012-06-21", "09:30:00").unwrap(),
            1_340_285_400_000_000_000
        );
        assert_eq!(
            local_timestamp("2012-01-03", "09:30:00").unwrap(),
            timestamp_from_text("2012-01-03T14:30:00Z").unwrap()
        );
        assert_eq!(date_for_timestamp(1_340_285_400_000_000_000), "2012-06-21");
        for (date, clock) in [
            ("bad", "09:30:00"),
            ("2012-06-21", "25:00:00"),
            ("2012-03-11", "02:30:00"),
            ("2012-11-04", "01:30:00"),
            ("2500-01-01", "09:30:00"),
        ] {
            assert!(local_timestamp(date, clock).is_err());
        }
    }
    #[test]
    fn exact_decimal_and_overflows() {
        for (text, ns, rounded) in [
            ("34200.271739507", 34_200_271_739_507, false),
            ("1", NS, false),
            ("1.000000000499", NS, true),
            ("1.000000000500", NS + 1, true),
            ("1.999999999999", 2 * NS, true),
            ("0.1", 100_000_000, false),
        ] {
            assert_eq!(decimal_seconds_ns(text).unwrap(), (ns, rounded));
        }
        for text in [
            "-1",
            ".5",
            "1.a",
            "1.2.3",
            "",
            "9223372037",
            "99999999999999999999999999999999999999999999999",
            "170141183460469231731687303715884105727",
        ] {
            assert!(decimal_seconds_ns(text).is_err(), "{text}");
        }
        assert!(timestamp_from_text("bad").is_err());
        assert!(timestamp_from_text("2012-06-21T13:30:00.000000000001Z").is_err());
        assert!(timestamp_from_text("2012-06-21T09:30:00-04:00").is_err());
        assert!(timestamp_from_text("2500-01-01T00:00:00Z").is_err());
        let stamp = local_timestamp("2012-06-21", "09:30:00").unwrap();
        validate_local_ns("2012-06-21", stamp, 34_200 * NS).unwrap();
        assert!(validate_local_ns("2012-06-21", stamp, 0).is_err());
        assert!(validate_local_ns("2012-06-21", stamp, -1).is_err());
    }
}
