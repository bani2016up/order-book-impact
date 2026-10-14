use ofi_core::{
    config::Config,
    error::{Error, ErrorCode, Result},
};
use pyo3::prelude::*;

#[pyfunction]
fn version(py: Python<'_>) -> String {
    py.detach(|| ofi_core::VERSION.to_owned())
}

fn envelope<T: serde::Serialize>(result: Result<T>) -> String {
    let value = match result {
        Ok(value) => serde_json::json!({"ok": value}),
        Err(error) => serde_json::json!({"error": error}),
    };
    value.to_string()
}

fn parse_config(config_json: &str) -> Result<Config> {
    let config: Config = serde_json::from_str(config_json).map_err(|e| {
        Error::new(
            ErrorCode::Config,
            format!("invalid configuration JSON: {e}"),
        )
    })?;
    config.validate()?;
    Ok(config)
}

#[pyfunction]
fn validate_config(py: Python<'_>, config_json: String) -> String {
    py.detach(move || envelope(parse_config(&config_json)))
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    m.add_function(wrap_pyfunction!(validate_config, m)?)?;
    Ok(())
}
