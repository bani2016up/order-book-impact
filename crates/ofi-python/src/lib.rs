use pyo3::prelude::*;

#[pyfunction]
fn version(py: Python<'_>) -> String {
    py.detach(|| ofi_core::VERSION.to_owned())
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    Ok(())
}
