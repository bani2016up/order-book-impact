"""Bootstrap boundaries: locked sync, compiler-free wheels and fail-fast errors."""

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture
def setup(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts" / "setup.py"
    spec = importlib.util.spec_from_file_location("project_setup", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", [str(path)])
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/tools/{name}")
    return module


def capture_runs(monkeypatch, setup):
    calls = []

    def run(command, **kwargs):
        calls.append((command, {**kwargs, "env": kwargs["env"].copy()}))

    monkeypatch.setattr(setup.subprocess, "run", run)
    return calls


def test_source_sync_targets_repository_even_with_foreign_environment(setup, monkeypatch):
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "/foreign/environment")
    calls = capture_runs(monkeypatch, setup)
    setup.main()
    command, options = calls[0]
    assert command[1:5] == ["sync", "--locked", "--all-extras", "--python"]
    assert command[5] == sys.executable
    assert options["env"]["UV_PROJECT_ENVIRONMENT"] == str(options["cwd"] / ".venv")
    assert len(calls) == 2  # Dependency/build failure cannot be hidden by an extra installer.


def test_wheel_bootstrap_does_not_require_or_build_rust(setup, monkeypatch, tmp_path):
    wheel = tmp_path / "current.whl"
    wheel.touch()
    monkeypatch.setattr(sys, "argv", ["setup.py", "--wheel", str(wheel)])
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/tools/uv" if name == "uv" else None)
    calls = capture_runs(monkeypatch, setup)
    setup.main()
    assert "--no-install-project" in calls[0][0]
    command = calls[1][0]
    assert command[1:3] == ["pip", "install"]
    assert command[-3:] == ["--reinstall", "--no-deps", str(wheel)]
    assert "--python" in command
    assert len(calls) == 3


def test_failed_locked_sync_stops_before_install_or_import(setup, monkeypatch):
    calls = []

    def fail(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(setup.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        setup.main()
    assert len(calls) == 1


@pytest.mark.parametrize("version", [(3, 10), (3, 11)])
def test_unsupported_python_is_rejected_before_environment_changes(setup, monkeypatch, capsys, version):
    calls = capture_runs(monkeypatch, setup)
    monkeypatch.setattr(sys, "version_info", version)
    with pytest.raises(SystemExit, match="2"):
        setup.main()
    assert "Python 3.12 or newer is required" in capsys.readouterr().err
    assert not calls


def test_missing_uv_has_no_pip_fallback(setup, monkeypatch, capsys):
    calls = capture_runs(monkeypatch, setup)
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="2"):
        setup.main()
    assert "Install uv" in capsys.readouterr().err
    assert not calls


def test_missing_wheel_leaves_environment_untouched(setup, monkeypatch, tmp_path, capsys):
    calls = capture_runs(monkeypatch, setup)
    monkeypatch.setattr(sys, "argv", ["setup.py", "--wheel", str(tmp_path / "missing.whl")])
    with pytest.raises(SystemExit, match="2"):
        setup.main()
    assert "wheel not found" in capsys.readouterr().err
    assert not calls
