import json
import os
import subprocess
import sys

import pytest

from ofi_pipeline import ConfigurationError, PipelineConfig, run_pipeline, _native
from ofi_pipeline.api import _path, _unwrap
from ofi_pipeline.cli import main


@pytest.mark.parametrize("path", ["", "bad\0path", b"bytes", 123])
def test_path_failures(path):
    with pytest.raises(ConfigurationError):
        _path(path)


def test_missing_and_ambiguous_configuration(bundle, tmp_path, monkeypatch):
    monkeypatch.delenv("OFI_SAMPLE_DIR", raising=False)
    for kwargs in [
        {},
        {"output_dir": tmp_path / "no-input"},
        {"sample_dir": bundle, "output_dir": tmp_path / "x", "config": {}},
        {"sample_dir": bundle, "output_dir": tmp_path / "y", "inputs": {}},
    ]:
        with pytest.raises(ConfigurationError):
            run_pipeline(**kwargs)
    monkeypatch.setenv("OFI_SAMPLE_DIR", str(bundle))
    report = run_pipeline(
        output_dir=tmp_path / "env", config=PipelineConfig(session_close="09:31:00")
    )
    assert report.feature_rows == 3
    for inputs in ["not-json", '{"events":"x"}']:
        with pytest.raises(ConfigurationError):
            _unwrap(_native.run_pipeline(inputs, str(tmp_path / "bad"), "{}"))


def test_cli_success_and_failures(bundle, tmp_path, capsys):
    assert (
        main(
            [
                "--sample-dir",
                str(bundle),
                "--output-dir",
                str(tmp_path / "cli"),
                "--session-close",
                "09:31:00",
                "--chunk-rows",
                "1",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["schema_version"] == "ofi-v1"
    for args in [
        ["--output-dir", str(tmp_path / "bad"), "--events", "missing"],
        [
            "--sample-dir",
            str(bundle),
            "--output-dir",
            str(tmp_path / "bad"),
            "--bucket-seconds",
            "2",
        ],
        ["--unknown"],
    ]:
        with pytest.raises(SystemExit) as error:
            main(args)
        assert error.value.code == 2
    result = subprocess.run(
        [sys.executable, "-m", "ofi_pipeline", "--help"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=os.environ,
    )
    assert result.returncode == 0 and "LOBSTER" in result.stdout
