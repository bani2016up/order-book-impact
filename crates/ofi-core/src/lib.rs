//! Pure Rust processing engine. No Python objects or callbacks belong here.

/// Library/algorithm version shared with the native Python module.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

#[cfg(test)]
mod tests {
    #[test]
    fn version_is_semantic() {
        assert_eq!(super::VERSION, "0.1.0");
    }
}

pub mod config;
pub mod domain;
pub mod error;
pub mod time;
