use crate::{
    domain::price_units,
    error::{Error, ErrorCode, Result},
    time::{NS, local_timestamp},
};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TradeSigning {
    #[default]
    LobsterDirection,
    QuoteTest,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    pub bucket_seconds: i64,
    pub levels: usize,
    pub trade_signing: TradeSigning,
    pub chunk_rows: usize,
    pub threads: usize,
    pub session_timezone: String,
    pub session_date: Option<String>,
    pub session_open: String,
    pub session_close: String,
    pub tick_size: f64,
    pub adapter_version: String,
    pub quality_policy: String,
    pub overwrite: bool,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            bucket_seconds: 10,
            levels: 5,
            trade_signing: TradeSigning::default(),
            chunk_rows: 65536,
            threads: 2,
            session_timezone: "America/New_York".into(),
            session_date: None,
            session_open: "09:30:00".into(),
            session_close: "16:00:00".into(),
            tick_size: 0.01,
            adapter_version: "lev-v1".into(),
            quality_policy: "supplied-clean".into(),
            overwrite: false,
        }
    }
}

impl Config {
    pub fn validate(&self) -> Result<()> {
        if ![1, 5, 10, 30, 60].contains(&self.bucket_seconds)
            || !(1..=5).contains(&self.levels)
            || !(1..=1_048_576).contains(&self.chunk_rows)
            || !(1..=64).contains(&self.threads)
        {
            return Err(Error::new(
                ErrorCode::Config,
                "width must be 1/5/10/30/60, levels 1..5, chunk_rows 1..1048576, threads 1..64",
            ));
        }
        if self.session_timezone != "America/New_York"
            || self.adapter_version != "lev-v1"
            || self.quality_policy != "supplied-clean"
        {
            return Err(Error::new(
                ErrorCode::Config,
                "lev-v1 requires America/New_York and supplied-clean quality policy",
            ));
        }
        price_units(self.tick_size)
            .map_err(|e| Error::new(ErrorCode::Config, format!("tick_size: {e}")))?;
        self.session(self.session_date.as_deref().unwrap_or("2012-06-21"))?;
        Ok(())
    }
    pub fn session(&self, date: &str) -> Result<(i64, i64)> {
        if ![1, 5, 10, 30, 60].contains(&self.bucket_seconds) {
            return Err(Error::new(ErrorCode::Config, "unsupported bucket width"));
        }
        if self.session_date.as_deref().is_some_and(|d| d != date) {
            return Err(Error::new(
                ErrorCode::Config,
                format!("input date {date} disagrees with session_date"),
            ));
        }
        let open = local_timestamp(date, &self.session_open)?;
        let close = local_timestamp(date, &self.session_close)?;
        if close <= open
            || (i128::from(close) - i128::from(open)) % i128::from(self.bucket_seconds * NS) != 0
        {
            return Err(Error::new(
                ErrorCode::Config,
                "session must be increasing and exactly divisible by bucket width",
            ));
        }
        Ok((open, close))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn config_validation() {
        for bucket_seconds in [1, 5, 10, 30, 60] {
            Config {
                bucket_seconds,
                ..Config::default()
            }
            .validate()
            .unwrap();
        }
        assert!(
            Config {
                bucket_seconds: i64::MAX,
                ..Config::default()
            }
            .session("2012-06-21")
            .is_err()
        );
        for change in [
            r#"{"bucket_seconds":0}"#,
            r#"{"levels":6}"#,
            r#"{"chunk_rows":0}"#,
            r#"{"threads":65}"#,
            r#"{"session_timezone":"UTC"}"#,
            r#"{"adapter_version":"guess"}"#,
            r#"{"quality_policy":"p95"}"#,
            r#"{"tick_size":0.00001}"#,
            r#"{"session_open":"16:00:00"}"#,
            r#"{"session_close":"15:59:59"}"#,
            r#"{"session_date":"bad"}"#,
        ] {
            let config: Config = serde_json::from_str(change).unwrap();
            assert!(config.validate().is_err(), "{change}");
        }
        let c = Config {
            session_date: Some("2012-06-21".into()),
            ..Config::default()
        };
        assert!(c.session("2012-06-22").is_err());
        assert!(serde_json::from_str::<Config>(r#"{"unknown":1}"#).is_err());
        assert!(serde_json::from_str::<Config>(r#"{"trade_signing":"lee_ready"}"#).is_err());
    }
}
