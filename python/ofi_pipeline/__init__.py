"""File-level Python interface to the compiled Rust OFI engine."""

from ._native import version
from .api import PipelineConfig
from .errors import (
    ArithmeticOverflowError,
    ConfigurationError,
    MalformedDataError,
    MissingInputError,
    OrderingError,
    PipelineError,
    PipelineIOError,
    QualityEvidenceError,
    SchemaError,
)

__all__ = [
    "version", "PipelineConfig", "PipelineError", "ConfigurationError", "SchemaError",
    "OrderingError", "QualityEvidenceError", "MissingInputError", "MalformedDataError",
    "ArithmeticOverflowError", "PipelineIOError",
]
