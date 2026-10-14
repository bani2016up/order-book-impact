"""Render recorded high-load scaling and RSS snapshots after measurements finish."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def render(root):
    summary = json.loads((root / "summary.json").read_text())
    if summary["status"] != "complete":
        raise ValueError("Only a complete, verified suite can be plotted")
    groups = {}
    for row in summary["aggregates"]:
        label = f"{row['signing']} · t{row['threads']} · c{row['chunk_rows']}"
        groups.setdefault(label, []).append(row)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    for label, rows in groups.items():
        rows.sort(key=lambda row: row["original_rows"])
        x = [row["original_rows"] / 10**6 for row in rows]
        for axis, prefix, ylabel in zip(
            axes, ("wall_seconds", "peak_rss_mib"), ("Public-call time (s)", "OS peak RSS (MiB)")
        ):
            median = [row[prefix + "_median"] for row in rows]
            lower = [m - row[prefix + "_min"] for m, row in zip(median, rows)]
            upper = [row[prefix + "_max"] - m for m, row in zip(median, rows)]
            axis.errorbar(x, median, yerr=[lower, upper], marker="o", capsize=3, label=label)
            axis.set(xlabel="Original events (millions)", ylabel=ylabel)
            axis.grid(alpha=0.2)
    ticks = sorted({row["original_rows"] / 10**6 for row in summary["aggregates"]})
    for axis in axes:
        axis.set_xticks(ticks)
        axis.set_xlim(0, max(ticks) * 1.1)
        axis.set_ylim(bottom=0)
    axes[0].legend(fontsize=8)
    fig.suptitle("Authored synthetic workload · medians and observed min–max\n"
                 "Fresh processes; uncontrolled OS cache; no cold-cache claim", fontsize=11)
    fig.savefig(root / "scaling.png", dpi=180)
    fig.savefig(root / "scaling.svg")
    plt.close(fig)
    selected = []
    for aggregate in summary["aggregates"]:
        selected.append(next(row for row in summary["runs"]
                             if not row["warmup"] and row["case_id"] == aggregate["case_id"]))
    fig, axes = plt.subplots(len(selected), 1, figsize=(11, max(4, 2.4 * len(selected))),
                             squeeze=False, constrained_layout=True)
    for axis, row in zip(axes[:, 0], selected):
        path = Path(row["artifact_dir"]) / "rss.jsonl"
        points = [json.loads(line) for line in path.read_text().splitlines()]
        points = [point for point in points if point["rss_bytes"] is not None]
        axis.plot([p["since_sampler_start_seconds"] for p in points],
                  [p["rss_bytes"] / 1024**2 for p in points], linewidth=1.5)
        axis.axhline(row["peak_process_rss_bytes"] / 1024**2, linestyle="--",
                     color="#b45309", linewidth=1, label="OS high-water RSS")
        axis.set(title=row["case_id"] + " · first measured repeat",
                 xlabel="Seconds since sampling began (just before native call)",
                 ylabel="RSS (MiB)")
        axis.grid(alpha=0.2)
        axis.set_ylim(bottom=0)
        axis.legend(fontsize=8)
    fig.suptitle("Recorded process RSS snapshots · sampling can miss short peaks", fontsize=12)
    fig.savefig(root / "rss-traces.png", dpi=150)
    plt.close(fig)
    print(root / "scaling.png")
    print(root / "rss-traces.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    render(parser.parse_args().root)


if __name__ == "__main__":
    main()
