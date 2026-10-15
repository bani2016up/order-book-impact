"""Sync the locked uv environment, building Rust or installing a compatible wheel."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel", type=Path, help="install a current compatible wheel without Rust"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required")
    uv = shutil.which("uv")
    if uv is None:
        parser.error("Install uv >=0.9.13: https://docs.astral.sh/uv/getting-started/installation/")
    wheel = args.wheel.expanduser().resolve() if args.wheel else None
    if wheel is not None and not wheel.is_file():
        parser.error(f"wheel not found: {wheel}")
    if wheel is None and (shutil.which("cargo") is None or shutil.which("rustc") is None):
        parser.error("Install Rust >=1.90, or provide --wheel with a compatible current wheel")
    environment = root / ".venv"
    executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = dict(os.environ)
    env["UV_PROJECT_ENVIRONMENT"] = str(environment)
    command = [uv, "sync", "--locked", "--all-extras", "--python", sys.executable]
    if wheel:
        command.append("--no-install-project")
    subprocess.run(command, check=True, cwd=root, env=env)
    env["VIRTUAL_ENV"] = str(environment)
    env["PATH"] = str(executable.parent) + os.pathsep + env.get("PATH", "")
    if wheel:
        subprocess.run(
            [uv, "pip", "install", "--python", str(executable), "--reinstall", "--no-deps", str(wheel)],
            check=True,
            cwd=root,
            env=env,
        )
    subprocess.run(
        [
            str(executable),
            "-c",
            "from ofi_pipeline import version; from ofi_pipeline.research import load_features; "
            "import statsmodels, sklearn; print('Native pipeline and research environment ready:', version())",
        ],
        check=True,
        cwd=root,
        env=env,
    )
    print("Use uv run --no-sync, or activate .venv and follow README.md.")


if __name__ == "__main__":
    main()
