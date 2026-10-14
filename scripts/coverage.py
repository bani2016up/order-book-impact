"""Measure native/core and Python coverage from one immutable source snapshot.

Requires rustup, the selected toolchain's llvm-tools-preview, maturin and pytest-cov.
The aggregate counts authored production lines before inline cfg(test) modules;
raw LLVM reports remain available without production exclusions.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--toolchain", default="1.90.0")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
os.chdir(root)
output = root / "target" / "coverage-report"
output.mkdir(parents=True, exist_ok=True)
profiles = output / "profiles"
profiles.mkdir(exist_ok=True)
for path in profiles.glob("*.profraw"):
    path.unlink()
source_files = sorted([*root.glob("crates/*/src/*.rs"), *root.glob("python/ofi_pipeline/*.py")])


def snapshot():
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files
    }


before = snapshot()
rustup = Path.home() / ".cargo" / "bin" / ("rustup.exe" if os.name == "nt" else "rustup")
rustc = Path(
    subprocess.check_output(
        [str(rustup), "which", "rustc", "--toolchain", args.toolchain], text=True
    ).strip()
)
cargo = Path(
    subprocess.check_output(
        [str(rustup), "which", "cargo", "--toolchain", args.toolchain], text=True
    ).strip()
)
sysroot = Path(subprocess.check_output([str(rustc), "--print", "sysroot"], text=True).strip())
host = next(
    s.split(": ", 1)[1]
    for s in subprocess.check_output([str(rustc), "-vV"], text=True).splitlines()
    if s.startswith("host: ")
)
llvm = sysroot / "lib" / "rustlib" / host / "bin"
suffix = ".exe" if os.name == "nt" else ""
env = dict(os.environ)
env.update(
    {
        "RUSTC": str(rustc),
        "CARGO": str(cargo),
        "RUSTUP_TOOLCHAIN": args.toolchain,
        "RUSTFLAGS": "-C instrument-coverage -C debuginfo=1",
        "CARGO_TARGET_DIR": str(root / "target" / "coverage-final"),
        "PYO3_PYTHON": sys.executable,
        "VIRTUAL_ENV": sys.prefix,
        "LLVM_PROFILE_FILE": str(profiles / "%m-%p.profraw"),
    }
)
env["PATH"] = str(cargo.parent) + os.pathsep + env["PATH"]
commands = []


def run(command, **kwargs):
    commands.append([str(c) for c in command])
    return subprocess.run(command, check=True, env=env, **kwargs)


# JSON artifacts identify exact current test executables, never stale glob matches.
result = run(
    [str(cargo), "test", "--workspace", "--locked", "--message-format=json"],
    capture_output=True,
    text=True,
)
print(result.stderr)
print("Rust suites completed; artifact log saved")
(output / "cargo-artifacts.txt").write_text(result.stdout)
objects = []
for line in result.stdout.splitlines():
    if not line.startswith("{"):
        continue
    item = json.loads(line)
    if item.get("reason") == "compiler-artifact" and item.get("executable"):
        objects.append(item["executable"])
run([sys.executable, "-m", "maturin", "develop", "--locked"])
# Native shared-library counters require instrumented build AND Python runtime profiles.
native = subprocess.check_output(
    [sys.executable, "-c", "from ofi_pipeline import _native; print(_native.__file__)"],
    text=True,
    env=env,
).strip()
objects.append(native)
run(
    [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/python",
        "tests/integration",
        "tests/research",
        "--cov=ofi_pipeline",
        "--cov-branch",
        "--cov-report=term-missing",
        f"--cov-report=json:{output / 'python.json'}",
    ]
)
if before != snapshot():
    raise RuntimeError("source changed during coverage; rebuild and remeasure")
profile = output / "rust.profdata"
run(
    [
        str(llvm / f"llvm-profdata{suffix}"),
        "merge",
        "-sparse",
        *(str(p) for p in profiles.glob("*.profraw")),
        "-o",
        str(profile),
    ]
)
base = [str(llvm / f"llvm-cov{suffix}"), "export", objects[0], f"-instr-profile={profile}"]
for obj in objects[1:]:
    base += ["-object", obj]
with (output / "rust.json").open("w") as f:
    run(base, stdout=f)
show = base.copy()
show[1] = "show"
show += ["-format=text", "-show-instantiations=false"]
# Show only authored files; raw export above keeps complete unfiltered mappings.
show += [str(p) for p in source_files if p.suffix == ".rs"]
with (output / "rust.txt").open("w") as f:
    run(show, stdout=f)
files = {}
current = None
for line in (output / "rust.txt").read_text().splitlines():
    if line.startswith(str(root)) and line.endswith(".rs:"):
        current = Path(line[:-1])
        files.setdefault(current, {})
    elif current:
        match = re.match(r"\s*(\d+)\|\s*(\d+(?:\.\d+)?[kMGTPE]?)\|", line)
        if match:
            files[current][int(match[1])] = 0 if float(match[2].rstrip("kMGTPE")) == 0 else 1
if not any("ofi-core" in str(p) for p in files) or not any("ofi-python" in str(p) for p in files):
    raise RuntimeError("coverage missing core or native source mappings")
summary = {
    "toolchain": args.toolchain,
    "instrumentation": "Rust LLVM instrumentation in unit executables and real shared library, runtime profiles merged",
    "production_scope": "authored source lines with LLVM counters before inline cfg(test); no blanket production exclusions",
    "source_sha256": before,
    "commands": commands,
    "files": {},
}
for path, lines in files.items():
    source = path.read_text().splitlines()
    cutoff = next(
        (i + 1 for i, s in enumerate(source) if s.strip() == "#[cfg(test)]"), len(source) + 1
    )
    measured = {n: c for n, c in lines.items() if n < cutoff}
    missed = [n for n, c in measured.items() if c == 0]
    summary["files"][str(path.relative_to(root))] = {
        "measured_lines": len(measured),
        "covered_lines": len(measured) - len(missed),
        "missed_lines": missed,
    }
for label, prefix in [("rust_core", "crates/ofi-core/"), ("native_binding", "crates/ofi-python/")]:
    group = [v for k, v in summary["files"].items() if k.startswith(prefix)]
    count = sum(v["measured_lines"] for v in group)
    covered = sum(v["covered_lines"] for v in group)
    summary[label] = {
        "lines": count,
        "covered": covered,
        "percent": 100 * covered / count if count else None,
    }
summary["python"] = json.loads((output / "python.json").read_text())["totals"]
(output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({k: summary[k] for k in ["rust_core", "native_binding", "python"]}, indent=2))
