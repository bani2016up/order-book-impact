//! Stable error categories crossing the native boundary.
use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorCode {
    Config,
    Schema,
    Order,
    Quality,
    MissingFile,
    Malformed,
    Overflow,
    Io,
}

#[derive(Debug, thiserror::Error, Serialize)]
#[error("{code:?}: {message}")]
pub struct Error {
    pub code: ErrorCode,
    pub message: String,
}

impl Error {
    pub fn new(code: ErrorCode, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}

impl From<std::io::Error> for Error {
    fn from(error: std::io::Error) -> Self {
        let code = if error.kind() == std::io::ErrorKind::NotFound {
            ErrorCode::MissingFile
        } else {
            ErrorCode::Io
        };
        Self::new(code, error.to_string())
    }
}

pub type Result<T> = std::result::Result<T, Error>;

pub fn checked_i64(value: i128, context: &str) -> Result<i64> {
    i64::try_from(value).map_err(|_| Error::new(ErrorCode::Overflow, context))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn codes_and_checked_arithmetic() {
        assert_eq!(checked_i64(42, "test").unwrap(), 42);
        assert_eq!(
            checked_i64(i128::MAX, "test").unwrap_err().code,
            ErrorCode::Overflow
        );
        for (kind, code) in [
            (std::io::ErrorKind::NotFound, ErrorCode::MissingFile),
            (std::io::ErrorKind::PermissionDenied, ErrorCode::Io),
        ] {
            let error = Error::from(std::io::Error::from(kind));
            assert_eq!(error.code, code);
            assert!(!error.to_string().is_empty());
        }
    }
}
