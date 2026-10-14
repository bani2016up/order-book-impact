import json
from dataclasses import asdict

import pytest

from ofi_pipeline import ConfigurationError, PipelineConfig, _native
from ofi_pipeline.api import _unwrap
from ofi_pipeline.errors import ERROR_TYPES


def test_default_and_serialization():
    config = PipelineConfig()
    assert asdict(config)["session_timezone"] == "America/New_York"
    assert _unwrap(_native.validate_config(json.dumps(asdict(config)))) == asdict(config)
    assert PipelineConfig(levels=1, bucket_seconds=1, trade_signing="quote_test")


@pytest.mark.parametrize(
    "fields",
    [
        {"bucket_seconds": 2},
        {"bucket_seconds": True},
        {"levels": 0},
        {"levels": 1.0},
        {"chunk_rows": 0},
        {"threads": 65},
        {"session_timezone": "UTC"},
        {"session_date": "bad"},
        {"session_open": "16:00:00"},
        {"session_close": "15:59:59"},
        {"adapter_version": "unknown"},
        {"quality_policy": "refilter"},
        {"tick_size": 0},
        {"tick_size": float("nan")},
        {"tick_size": object()},
        {"trade_signing": "lee_ready"},
        {"overwrite": 1},
    ],
)
def test_invalid_configuration(fields):
    with pytest.raises(ConfigurationError):
        PipelineConfig(**fields)


@pytest.mark.parametrize("payload", ["bad", '{"unknown":1}', '{"levels":-1}'])
def test_native_invalid_config(payload):
    with pytest.raises(ConfigurationError):
        _unwrap(_native.validate_config(payload))


@pytest.mark.parametrize("code,exception", ERROR_TYPES.items())
def test_error_mapping(code, exception):
    with pytest.raises(exception, match="symbol A event 1"):
        _unwrap(json.dumps({"error": {"code": code, "message": "symbol A event 1"}}))
