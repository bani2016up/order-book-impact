"""Typed configuration and file-level calls; numerical work belongs to Rust."""
from dataclasses import asdict, dataclass
import json
from typing import Any, Literal

from . import _native
from .errors import ConfigurationError, ERROR_TYPES


def _unwrap(payload: str) -> Any:
    response = json.loads(payload)
    if "error" in response:
        error = response["error"]
        raise ERROR_TYPES[error["code"]](error["message"])
    return response["ok"]


@dataclass(frozen=True)
class PipelineConfig:
    """Lev-v1 session, bounded processing and supplied-quality configuration."""

    bucket_seconds: int = 10
    levels: int = 5
    trade_signing: Literal["lobster_direction", "quote_test"] = "lobster_direction"
    chunk_rows: int = 65536
    threads: int = 2
    session_timezone: str = "America/New_York"
    session_date: str | None = None
    session_open: str = "09:30:00"
    session_close: str = "16:00:00"
    tick_size: float = 0.01
    adapter_version: str = "lev-v1"
    quality_policy: str = "supplied-clean"
    overwrite: bool = False

    def __post_init__(self) -> None:
        for field in ("bucket_seconds", "levels", "chunk_rows", "threads"):
            if type(getattr(self, field)) is not int:
                raise ConfigurationError(f"{field} must be an integer")
        if type(self.overwrite) is not bool:
            raise ConfigurationError("overwrite must be a boolean")
        try:
            encoded = json.dumps(asdict(self), allow_nan=False)
        except (ValueError, TypeError) as error:
            raise ConfigurationError(str(error)) from error
        _unwrap(_native.validate_config(encoded))
