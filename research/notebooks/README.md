# Exploratory notebooks

- `baseline_replication.ipynb`: the paper's Tables 2-4 on the small LOBSTER sample and the
  final BX dataset and Figures 5-6 on BX only, with formulas, HC0/HC3/bootstrap tests and
  computed hypothesis verdicts (needs both datasets; writes no files).

Store English-named notebooks here. Install the research environment first;
Jupyter itself is optional (`uv add --optional research jupyterlab`, then
`uv sync --locked --all-extras` and `uv run --no-sync jupyter lab`). Commit the
reviewed pyproject.toml and uv.lock change when sharing that dependency.

In a notebook, shared helpers are imported from the installed package rather
than from a repository-relative import hack:

```python
from pathlib import Path
from ofi_pipeline.research import load_features

repo = Path("/absolute/path/to/order-book-impact-pipeline")
features = load_features(repo / "outputs/features/10s")
```

Move reusable model code into `research/baseline/` or `research/extensions/` and
provide a module entry point runnable from the repository root. Keep cell
outputs and generated figures small; save large artifacts under `outputs/`.
Notebooks must not duplicate the Rust event engine or hide target/split/units.
