"""Typed configuration and file-level calls; numerical work belongs to Rust."""

from dataclasses import asdict, dataclass
from os import PathLike as OSPathLike, environ, fspath
from pathlib import Path
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


@dataclass(frozen=True)
class RawInput:
    """Original row-paired CSVs or one vendor ZIP for a symbol/session."""

    symbol: str
    date: str
    archive: "PathLike | None" = None
    message: "PathLike | None" = None
    orderbook: "PathLike | None" = None


@dataclass(frozen=True)
class InputPaths:
    """Explicit Lev-v1 inputs, each a Parquet or headered CSV/gzip CSV file."""

    events: "PathLike"
    trades: "PathLike"
    quality: "PathLike"
    raw: tuple[RawInput, ...] = ()


@dataclass(frozen=True)
class SigningCoverage:
    volume: int
    trade_imbalance: int
    trade_count: int
    classified_count: int
    unclassified_count: int
    classified_volume: int
    unclassified_volume: int


@dataclass(frozen=True)
class PartitionReport:
    symbol: str
    date: str
    original_rows: int
    clean_events: int
    rejected_events: int
    feature_rows: int
    total_buckets: int
    rejected_buckets: int
    rejection_reasons: dict[str, int]
    source_rejection_reasons: dict[str, int]
    signing: SigningCoverage
    rounded_event_timestamps: int
    missing_precision_flag_rows: int
    rounded_raw_timestamps: int


@dataclass(frozen=True)
class RunReport:
    output_dir: "Path"
    features_path: "Path"
    bucket_quality_path: "Path"
    manifest_path: "Path"
    quality_report_path: "Path"
    partitions: tuple[PartitionReport, ...]
    config: PipelineConfig
    algorithm_version: str
    schema_version: str
    elapsed_seconds: float
    warnings: tuple[str, ...]

    @property
    def feature_rows(self) -> int:
        return sum(p.feature_rows for p in self.partitions)


# Path normalization lives in Python; all file parsing/computation lives in Rust.

PathLike = str | OSPathLike[str]


def _path(value: PathLike) -> str:
    try:
        normalized = fspath(value)
    except TypeError as error:
        raise ConfigurationError("paths must be strings or pathlib/os.PathLike objects") from error
    if not isinstance(normalized, str) or not normalized or "\0" in normalized:
        raise ConfigurationError("paths must be nonempty strings without NUL bytes")
    return str(Path(normalized).expanduser().absolute())


def run_pipeline(
    sample_dir: PathLike | None = None,
    output_dir: PathLike | None = None,
    config: PipelineConfig | None = None,
    *,
    inputs: InputPaths | None = None,
) -> RunReport:
    """Compute one ordered file set in Rust and atomically publish a result directory.

    Either pass a sample directory (or set OFI_SAMPLE_DIR) or explicit InputPaths.
    The output directory must be new unless overwrite is explicitly enabled.
    """
    if output_dir is None:
        raise ConfigurationError("output_dir is required")
    if config is None:
        config = PipelineConfig()
    if not isinstance(config, PipelineConfig):
        raise ConfigurationError("config must be a PipelineConfig")
    if inputs is not None:
        if sample_dir is not None or not isinstance(inputs, InputPaths):
            raise ConfigurationError("use either sample_dir or an InputPaths object")
    else:
        sample_dir = sample_dir if sample_dir is not None else environ.get("OFI_SAMPLE_DIR")
        if sample_dir is None:
            raise ConfigurationError("provide sample_dir, InputPaths, or OFI_SAMPLE_DIR")
        root = Path(_path(sample_dir))

        def table(stem: str) -> Path:
            parquet = root / "data" / f"{stem}.parquet"
            return parquet if parquet.exists() else root / "data" / f"{stem}.csv.gz"

        raw_inputs = []
        if config.trade_signing == "quote_test":
            import re

            for archive in sorted((root / "raw").glob("LOBSTER_SampleFile_*_5.zip")):
                match = re.fullmatch(r"LOBSTER_SampleFile_(.+)_(\d{4}-\d{2}-\d{2})_5", archive.stem)
                if match:
                    raw_inputs.append(RawInput(match[1], match[2], archive=archive))
        inputs = InputPaths(
            table("events_clean"),
            table("trades_clean"),
            root / "reports" / "event_quality.parquet",
            tuple(raw_inputs),
        )
    paths: dict[str, Any] = {
        name: _path(getattr(inputs, name)) for name in ("events", "trades", "quality")
    }
    paths["raw"] = [
        {
            "symbol": source.symbol,
            "date": source.date,
            **{
                field: _path(getattr(source, field)) if getattr(source, field) is not None else None
                for field in ("archive", "message", "orderbook")
            },
        }
        for source in inputs.raw
    ]
    payload = _unwrap(
        _native.run_pipeline(
            json.dumps(paths), _path(output_dir), json.dumps(asdict(config), allow_nan=False)
        )
    )
    partitions = tuple(
        PartitionReport(**{**p, "signing": SigningCoverage(**p["signing"])})
        for p in payload["partitions"]
    )
    return RunReport(
        **{
            name: Path(payload[name])
            for name in (
                "output_dir",
                "features_path",
                "bucket_quality_path",
                "manifest_path",
                "quality_report_path",
            )
        },
        partitions=partitions,
        config=config,
        algorithm_version=payload["algorithm_version"],
        schema_version=payload["schema_version"],
        elapsed_seconds=payload["elapsed_seconds"],
        warnings=tuple(payload["warnings"]),
    )
