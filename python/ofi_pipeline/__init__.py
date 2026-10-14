"""File-level Python interface to the compiled Rust OFI engine."""

from ._native import version
from .api import (
    InputPaths,
    PartitionReport,
    PipelineConfig,
    RunReport,
    SigningCoverage,
    run_pipeline,
)
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
    "version",
    "PipelineConfig",
    "InputPaths",
    "PartitionReport",
    "RunReport",
    "SigningCoverage",
    "run_pipeline",
    "PipelineError",
    "ConfigurationError",
    "SchemaError",
    "OrderingError",
    "QualityEvidenceError",
    "MissingInputError",
    "MalformedDataError",
    "ArithmeticOverflowError",
    "PipelineIOError",
]
