"""Actionable error categories shared with the native core."""


class PipelineError(Exception):
    """Base class for all expected pipeline failures."""


class ConfigurationError(PipelineError, ValueError):
    """Invalid configuration or session."""


class SchemaError(PipelineError, ValueError):
    """Physical schema or units disagree with the adapter."""


class OrderingError(PipelineError, ValueError):
    """Duplicate IDs, decreasing time or missing original rows."""


class QualityEvidenceError(PipelineError, ValueError):
    """Insufficient or inconsistent original quality evidence."""


class MissingInputError(PipelineError, FileNotFoundError):
    """A required file is missing."""


class MalformedDataError(PipelineError, ValueError):
    """An input value violates the data contract."""


class ArithmeticOverflowError(PipelineError, OverflowError):
    """A checked operation or exact conversion exceeded its range."""


class PipelineIOError(PipelineError, OSError):
    """Input/output or atomic publication failed."""


ERROR_TYPES: dict[str, type[PipelineError]] = {
    "config": ConfigurationError,
    "schema": SchemaError,
    "order": OrderingError,
    "quality": QualityEvidenceError,
    "missing_file": MissingInputError,
    "malformed": MalformedDataError,
    "overflow": ArithmeticOverflowError,
    "io": PipelineIOError,
}
