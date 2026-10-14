"""Create/reuse .venv and install the native pipeline plus the shared research environment."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel", type=Path, help="install a current compatible wheel without Rust"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if sys.version_info < (3, 10):
        parser.error("Python 3.10 or newer is required")
    wheel = args.wheel.expanduser().resolve() if args.wheel else None
    if wheel is not None and not wheel.is_file():
        parser.error(f"wheel not found: {wheel}")
    if wheel is None and (shutil.which("cargo") is None or shutil.which("rustc") is None):
        parser.error("Install Rust >=1.90, or provide --wheel with a compatible current wheel")
    environment = root / ".venv"
    executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executable.is_file():
        venv.create(environment, with_pip=True)
    env = dict(os.environ)
    env["VIRTUAL_ENV"] = str(environment)
    env["PATH"] = str(executable.parent) + os.pathsep + env.get("PATH", "")
    if wheel:
        subprocess.run(
            [str(executable), "-m", "pip", "install", "--force-reinstall", "--no-deps", str(wheel)],
            check=True,
            cwd=root,
            env=env,
        )
        command = [str(executable), "-m", "pip", "install", f"{wheel}[research,dev,test]"]
    else:
        subprocess.run(
            [str(executable), "-m", "pip", "install", "maturin==1.9.6"],
            check=True,
            cwd=root,
            env=env,
        )
        command = [
            str(executable),
            "-m",
            "maturin",
            "develop",
            "--release",
            "--locked",
            "--extras",
            "research,dev,test",
        ]
    subprocess.run(command, check=True, cwd=root, env=env)
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
    print("Activate .venv, then follow the feature and model commands in README.md.")


if __name__ == "__main__":
    main()
