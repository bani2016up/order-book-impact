# Implementation work log

## Baseline replication step 4 — replication notebook and a leverage diagnostic (2026-10-16)

- New `research/notebooks/baseline_replication.ipynb` (48 cells, 26 code; outputs not stored):
  data and how to run, formulas checked against the paper (e_n, OFI, eqs. 1-8c), Tables 2 and 4
  under HC0 / HC3 / wild bootstrap on both datasets, the quadratic-term diagnostics, Table 3 with
  narrow/wide-spread group rows and a Figure-4-style log beta vs log AD prototype, Figures 5-6 on
  BX, a hypothesis table with verdicts computed from the fits, the extension hypothesis for
  Timur (issue #1) and limitations. It calls the `research.baseline` modules; its own logic is
  presentation plus a degenerate-fit flag, window-count tests and verdict rules, which are new and
  untested and say so. Degenerate fits (HC3 undefined or R2 > 0.99) are dropped per model in
  Table 2 and per window in Table 4 (BX: 18 of 1,758 and 48 of 2,519 fits; LOBSTER: none); the
  rule is stated as a judgment call and no window-based verdict differs between raw and cleaned
  fits. Window-count tests compare the share of significant windows with 11% (the simulated
  bootstrap size, a heuristic) with a 5% sensitivity column; fewer than 30 windows is called
  inconclusive (power about 0.42 at 13 windows and 0.65 at 30 for a true 25% share).
- Written by one agent and reviewed by another in three rounds. The review executed every cell
  in plain Python and in an IPython kernel, twice and from two working directories, compared all
  tables with the CLI outputs (agreement within 3e-13), recomputed spot values by hand and checked
  formulas and quoted paper numbers against the paper. Fixed after review: a missing 09:30 slot
  counted as a failure (H5); near-degenerate windows (for example one CSCO window with HC0 z of
  2,889) inflated mean z and F values; "not rejected" was labelled "supported"; the null share
  disagreed with the cited bootstrap size; several sentences overstated what the code showed.
- `fit_models` adds `max_leverage` (largest hat value of the fitted window) to the metrics.
  `LEVERAGE_LIMIT` is kept: in the flagged windows HC3 is finite and conservative (a z near one
  when a single bucket determines a coefficient), while one near-deterministic AMZN window has a
  maximum leverage of only 0.51, so a stricter leverage cut would neither catch it nor be needed
  for the others. The diagnostic lets analyses flag such windows explicitly.
- README: the stale sentence that Table 3 and Figures 5-6 were not implemented now points to
  sections 6-7 and the notebook.
- Checks: `ruff check python research tests benchmarks scripts`, `ruff format --check
  research/notebooks` and `pytest tests/research` (67 tests) passed. The notebook ran end to end in
  about 14 s with no errors, left its inputs unchanged and wrote no files; a rerun after the
  `max_leverage` change gave byte-identical tables and figures.

## Baseline replication step 3 — paper Figures 5 and 6 (2026-10-16)

- New `research/baseline/seasonality.py` and `configs/seasonality.json`. Windows are keyed by
  the exchange-local half-hour slot (America/New_York), because the BX dates span winter and
  summer time and a UTC key would split the open into two slots. Per stock the slot means over
  days are divided by the stock's own mean over all windows; `beta^2 var[OFI]` is built from the
  average patterns of its factors and divided by the `var[dP]` constant, so the two curves of
  Figure 6 share a scale (the paper's footnote 4 builds it the same way). Stocks that cannot be
  normalised or lack slots are listed with the reason in `run.json`.
- Plots use `matplotlib.figure.Figure` directly (no global backend change), the validated
  categorical palette (checked with the dataviz validator; for Figure 6 aqua and yellow are
  below 3:1 on the light surface, so the relief is marker shapes plus the CSV table view),
  2 px lines, a legend and one axis; Figure 6 uses a log axis because one slot is 5x the
  average. A first title claimed the open has the highest impact and lowest depth, which the
  data did not show; titles now only describe what is plotted.
- Tests (`tests/research/test_seasonality.py`, 9): local-time slots across winter and summer
  sessions, window variances, exact normalisation, exclusions with reasons, cross-stock
  statistics, the quoted summary numbers, the plotted data/colours/markers/log axis and the CLI.
- Checks: `ruff check python research tests benchmarks scripts` and `pytest tests/research`
  (66 tests) passed.
- Results (descriptive; `outputs/baseline/seasonality_bx`, `seasonality_bx_narrow`):
  all 8 BX stocks with enough coverage (ADBE and GOOG excluded): beta 1.2x its average at the
  open and 3.4x its 15:30 value, depth 0.94x at the open, var[dP] peak at 11:00, var[OFI] peak at
  15:30 (5x average), correlation of var[dP] with beta^2 var[OFI] across slots 0.65. The four
  narrow-spread stocks (AMD, CSCO, INTC, QCOM): depth 0.69x at the open (paper about 0.5x), beta
  1.33x at the open and 3.4x its closing value (paper about 2x and 5x), var[dP] peak at the open,
  var[OFI] peak at 15:30, correlation 0.90, mean beta^2 var[OFI] / var[dP] 1.29. The wide-spread
  BX stocks do not show the paper's open-to-close pattern clearly, consistent with their weak
  depth law in step 2. 10 dates, 4 to 8 stocks per slot: not a test of the paper's claims.

## Baseline replication step 2 — paper Table 3 and the final dataset (2026-10-16)

- Downloaded the release asset `order_book_final_models.zip` (19,443,935 bytes) and
  `SHA256SUMS-release.txt` from `bani2016up/order-book-impact` release `dataset-2026-10-15` with
  `gh release download` into the ignored `data/`. The archive hash matched the release file and
  all 29 internal checksums in `SHA256SUMS_models.txt` passed. The 791 MB full archive was not
  downloaded. The set is 10 NASDAQ BX stocks, 100 sessions, 111,456 accepted 10-second rows;
  coverage is uneven (7 stocks have 95-123 half-hour windows with at least 20 buckets, ADBE,
  GOOG and QCOM 22-42) and 19,498 rows have unknown trade imbalance.
- New `research/baseline/depth_impact.py` and `configs/depth_impact.json`: Table 3 (paper eqs. 5
  and 6) per stock with Newey-West (Bartlett, automatic bandwidth floor(4 (T/100)^(2/9)))
  standard errors and normal confidence intervals; `beta_i` comes from an OFI-only fit so unknown
  trade signs do not shrink the sample; window depth is the quote-update-weighted mean of the
  buckets' L1 depth. Non-positive betas and skipped windows are counted in `dropped_windows`.
  The squared correlations follow the paper (fitted `c AD^-lambda`, and `1/AD`).
- Tests (`tests/research/test_depth_impact.py`, 16): exact recovery on noise-free power laws,
  recovery and the lambda = 1 test on noisy synthetic laws (lambda 1 and 0.5), no relation
  to depth, dropped and short stocks, the bandwidth rule, config validation and the CLI. A
  first draft asserted a bandwidth exactly on a rounding boundary (T = 273); it was replaced.
- Checks: `ruff check python research tests benchmarks scripts` and `pytest tests/research`
  (57 tests) passed.
- Results (descriptive, in-sample; `outputs/baseline/table3_small`, `table3_bx`):
  small LOBSTER sample (2 stocks, 13 windows each): lambda 0.89 (AAPL, 95% interval 0.62-1.16)
  and 0.98 (MSFT, 0.82-1.14), R2 of eq. (5) 0.52 and 0.86; lambda = 1 is not rejected (paper:
  0.98 on average, R2 74%). Final BX set (881 fitted windows): CSCO, INTC, AMD and QCOM
  (mean spread 2.2-3.1 cents) give lambda 0.87, 0.71, 0.77 and 1.22 with R2 0.58, 0.31, 0.53 and
  0.36; the six stocks with a mean spread of 10 cents or more (MSFT, ADBE, AAPL, NVDA, GOOG,
  AMZN) have R2 of at most 0.09 and lambda mostly near 0 (Spearman of spread against R2 is -0.81,
  n = 10). The paper also reports poor fits for its wide-spread, low-depth stocks. This is a
  10-stock association on one venue (BX), not a tested mechanism.

## Baseline replication step 1C — HC3 and wild bootstrap-t (2026-10-16)

Why: the quadratic-term investigation (five independent analyses under
`outputs/baseline/quadratic_investigation/`, not tracked) found that the paper's HC0 z-test
rejects a true null far too often in our windows (~180 buckets, heavy-tailed OFI·|OFI|).
- New `research/baseline/inference.py`: `wild_bootstrap_p_values` (null imposed per
  coefficient, Rademacher weights, HC3 t, `(1 + extreme) / (1 + B)`), stable per-test seeds
  from a checksum of symbol/date/window/model, and `leverage_values`. HC3 and bootstrap are
  declared undefined (NaN) when an observation has leverage within 1e-8 of one: otherwise the
  HC3 weight divides one rounding error by another and returns a finite but meaningless value
  (a first draft of the test expected NaN and found exactly that).
- `fit_models` adds `hc3_standard_error`, `hc3_z_statistic`, `hc3_p_value` and
  `bootstrap_p_value` to the coefficients; `BaselineConfig` gains `bootstrap_draws` (default 0,
  `configs/baseline.json` uses 999) and `bootstrap_seed`.
- `summarize_terms` and the paper tables take `inference` = `hc0` (default, the paper's test),
  `hc3` or `bootstrap`. The CLI writes `table2/4.csv` (HC0) plus `_hc3` and, if enabled,
  `_bootstrap` variants; `summary_terms.csv` gains an `inference` column; `run.json` lists the
  tests. The numbers in tables 2 and 4 under HC0 are unchanged.
- Checks: `ruff check python research tests benchmarks scripts` passed. `pytest tests/research`
  passed (41 tests). The implementation matches statsmodels HC3 to 1e-15; in 400 simulated
  windows with a true linear model and t(3) regressors the nominal 5% test rejects 34.5%
  (HC0), 10% (HC3) and 11% (bootstrap). `tests/python/test_setup.py` fails in this checkout
  only because the local `.venv` is Python 3.11 and `pyproject.toml` now requires 3.12.
- Real sample (`outputs/baseline/run02`, 104 fits, 0 undefined), share of the 13 windows where
  the quadratic term is significant at 5%, AAPL / MSFT: HC0 92% / 46% (mean z -4.91 / -2.20),
  HC3 46% / 23% (-2.12 / -0.85), bootstrap 46% / 15%. These match the independent
  inference analysis (HC3 6/13 and 3/13). Trade imbalance stays significant next to OFI in
  46% / 31% of windows under HC0 and 38% / 15% under HC3. One day, two stocks, 13 windows
  per symbol; no inference beyond this sample is drawn.

## Final dataset publication — 2026-10-15

- The owner explicitly authorized publication to this repository. Preserve all
  source history and use GitHub Release assets for the real data, keeping large
  archives and generated features out of Git history.
- Added `docs/FINAL_DATASET.md` and a README download section for the ready model
  bundle and complete dataset. Documented the chronological splits, unknown TI,
  sparse five-level coverage, source provenance and current engine requirement.
- Updated the delivered reproduction instructions to use the already integrated
  hidden-side support rather than reapplying the compatibility patch.
- Dataset checks: 7,297,682 clean events, 363,815 executions and 111,456 accepted
  10-second features; 234,000 interval masks and 564 scalar calculations checked.
  Independent reconstruction checked 5,091 sampled states from a complete day.
  Model-loader/gap-safe-lag smoke covered all delivered 10-second rows.
- Both archive packages passed full ZIP CRC and per-member SHA-256 verification
  after the documentation update. Publication changes no numerical data or
  production code; existing compiled-engine acceptance is recorded below.
- Local documentation checks: download paths, split totals, nullable TI counts,
  source/release links, and `git diff --check`. Release assets include external
  archive checksums as well as the internal file checksums.

## Public ITCH hidden-side support plan — 2026-10-15

- Prepare a free multi-session NASDAQ BX dataset outside this source checkout.
- Preserve unknown hidden-execution passive sides as zero rather than inventing
  a sign. Extend input validation only for type-5 zero-side rows; require Quote
  Test for those trades and reject supplied signed-volume evidence.
- Verify the extension with focused Rust/native tests, rebuild the actual PyO3
  engine, and run the self-contained suite before a local explicit-path commit.
- Keep all existing signed LOBSTER semantics and output schemas unchanged.

### Completed evidence

- Allowed zero passive side only for type-5 hidden executions. Unknown-side
  signed-volume evidence and known-direction execution mode fail explicitly.
  Quote Test preserves total volume and existing nullable complete-TI output.
- Native fixture covers accepted and rejected post-quotes, unknown-side hidden
  executions, inside-spread incompleteness, unsafe known-side mode, and supplied
  fabricated sign evidence. Documentation is in `docs/ITCH_INPUT.md`.
- Rebuilt the actual release PyO3 extension with locked dependencies. Focused
  Quote Test integration: 12 passed. Rust core: 34 unit + 6 adapter + 2 pipeline
  tests passed; external-sample Rust test remains explicitly ignored by default.
- Full Python/native/research suite: 130 passed, 4 optional rebuild checks skipped.
  Then explicitly ran original delivered-data acceptance with
  OFI_SAMPLE_DIR and OFI_REBUILD_REFERENCE=1: all five widths passed (5 tests).
  Ruff, strict mypy (7 files), and diff whitespace checks passed.
- On reconstructed BX pilot inputs the reviewed engine computed 23,992 accepted
  10-second intervals for 20 symbol/date sessions. This pilot count is not the
  final dataset size. No source data or generated outputs are committed.
- Local commit only; no push, PR, package upload, or remote modification.


## Merge resolution — uv migration and baseline tables (2026-10-15)

- Resolved the single CHANGELOG conflict by preserving both complete additions:
  local uv/Python 3.12 migration and incoming baseline replication steps 1A/1B.
  Kept the automatically merged README, model/configuration and research tests.
- Combined self-contained Python/native/research/benchmark suite: 128 passed.
  Ruff, strict mypy (seven source files), conflict-marker and diff checks passed.
  Rust algorithms and package interfaces were unchanged by this resolution;
  no new performance or external real-data measurement is claimed. Local merge
  commit only; no push or history rewrite.

## uv and Python 3.12 migration plan — 2026-10-15

- Owner requested uv as the Python package/environment manager and Python >=3.12.
  Preserve production interfaces, Rust algorithms and all existing local commits.
- Add a checked-in universal uv.lock and default Python pin; retain the existing
  optional dependency extras. Build the native extension with maturin through uv,
  in release mode with Cargo.lock enforced, including Rust-source cache keys.
- Migrate source/wheel setup, isolated wheel checks, CI, coverage/benchmark build
  bootstrapping and current documentation. Raise the PyO3 ABI floor consistently.
- Validate source and compiler-free wheel setup, bootstrap failure paths, lock
  consistency, full Rust/Python/real-sample tests, Python 3.13 compatibility,
  lint/types, release wheel and isolated compiled smoke. Create small local
  commits after checks; no push. Historical benchmark evidence stays unchanged;
  packaging/harness identity changes require a fresh performance baseline.

## uv migration — locked native/bootstrap implementation (2026-10-15)

- Raised requires-python and PyO3 ABI to Python 3.12; added .python-version and
  universal uv.lock (37 resolved packages). Existing extras/direct constraints
  remain available; the initial lock selected transitive versions, including
  fonttools 4.67.0 and pluggy 1.7.0 in place of the pre-migration environment.
- uv owns source sync and compiler-free wheel setup. Maturin remains the pinned
  PEP 517 backend with release profile, Cargo --locked and portable-wheel audit
  options. Rust source/manifests are cache keys so native changes rebuild.
- Isolated wheel checks sync locked research dependencies without installing
  the project and install only the provided wheel. Coverage/high-load native
  rebuilds use maturin --uv. High-load snapshots and comparison guards now include
  uv.lock and .python-version; workload/timing/verification logic is unchanged.
- Seven bootstrap tests cover old Python rejection, missing uv/wheel, foreign
  environment isolation, no-Rust wheel setup and lock-failure propagation. Source
  setup, 116 self-contained source/native/research/benchmark tests, 42 Rust tests,
  explicit real ingestion, Rust 1.90 tests (42), fmt, strict Clippy, Ruff and mypy
  passed. After lock-guard additions, 13 focused bootstrap/runner tests passed.
- uv build produced cp312-abi3 with Requires-Python >=3.12 and an optimized release
  build; isolated compiled API/CLI/research/Parquet/error/type-marker smoke passed
  in a fresh uv environment outside checkout. Evidence remains ignored under
  outputs/features/uv-migration-20261015; wheel is in dist/uv-py312.
- Initial probes found macOS uv sandbox system-configuration panic (resolved by
  authorized external execution), unsupported PEP 517 --release (corrected to
  --profile release), and console pytest's missing repository import path
  (documented/CI commands use python -m pytest). No failure was reported as a pass.
- Full Python 3.12/3.13 real acceptance, compiler-free bootstrap, actual benchmark
  build smoke, coverage-manager path and final CI/docs checks follow separately.

## uv migration — CI and Python 3.13 wheel validation (2026-10-15)

- Migrated both CI jobs to setup-uv with pinned uv 0.9.13, locked all-extras sync,
  uv wheel builds and actual wheel installation before compiled tests. The matrix
  now covers Python 3.12/3.13 on Linux/macOS/Windows; PyO3 uses the explicit project
  interpreter. Tests use python -m pytest and --no-sync to preserve the artifact.
- CI YAML parsed successfully and its 3.12/3.13 matrix was checked locally.
  The cp312-abi3 wheel passed all **121 tests on Python 3.13.15 without skips** in a
  fresh uv environment where pip is absent. This includes five real-data widths,
  exact integer/depth/quality reconciliation and accepted row counts
  45966/8985/4390/1382/650; max USD error 2.182785e-13 remains below tolerance.
- Actual wheel bootstrap also passed with cargo/rustc absent from its PATH;
  no project build occurred. Isolated Python 3.12 wheel smoke passed separately.
  Hosted jobs were not triggered or claimed successful. Full Python 3.12 real
  tests and coverage/high-load manager paths are the remaining local checks.

## uv migration — wheel-to-editable benchmark bootstrap (2026-10-15)

- An actual build-enabled smoke in pip-free Python 3.13 exposed a wheel-to-editable
  transition issue: maturin successfully installed the editable .pth, but the
  already running benchmark parent could not import the new package path.
  The failed smoke and its build logs remain retained, not overwritten.
- Refresh installed purelib paths immediately after the untimed build and before
  snapshot/import. This uses the interpreter's installed metadata rather than a
  repository import override; workload, native computation and timers are unchanged.
- Added a regression test that simulates an installer creating an editable .pth
  after interpreter startup and requires the snapshot import to see that module.
  All 14 focused bootstrap/runner tests and Ruff passed. The real retry first
  reinstalled the wheel, verified its native library was in the Python 3.13 venv
  and pip was absent, then completed an offline uv-backed editable rebuild and
  four verified 303-row runs (both signings, two chunk/thread cases). Both the
  lock/pin identities and release-build provenance were recorded.
- Failed/successful smoke roots: benchmarks/results/uv-migration-smoke-20261015
  and uv-migration-smoke-fixed-20261015. This is build/workflow validation, not a
  replacement 1M/10M/20M performance baseline or a speedup claim. No push.

## uv migration — final acceptance and documentation (2026-10-15)

- Final complete suites passed **122 tests on Python 3.12.0 and 122 on Python
  3.13.15, no skips**, including the editable-path regression and all five real
  aggregation widths. Both versions retain exact keys, integer/depth/quality
  values and 45966/8985/4390/1382/650 accepted rows; maximum USD/tick errors remain
  2.182785e-13 / 2.182787e-11 under existing tolerances. Final logs/reconciliation
  identities are recorded in ignored outputs/features/uv-migration-20261015/validation.json.
- One concurrent final 3.13 run had 121 passes and one strict cold cache-gate
  rejection: all input pages were resident in a child after parent preparation.
  Its logs/cache state are retained. The complete serial 3.13 repeat passed all
  122 with unchanged gates; no retry logic, skipped test or relaxed cache claim
  was introduced. Parent preparation does not guarantee later cache residency.
- Final checks: 42 Rust workspace tests, explicit real ingestion (one), Rust
  1.90 workspace (42), formatting, warnings-denied Clippy, Ruff/mypy on both
  Pythons, uv lock --check, dependency integrity for both environments, CI YAML,
  source bootstrap, compiler-free wheel bootstrap, isolated native wheel smoke
  and four-case build-enabled benchmark smoke all passed.
- Actual coverage runner completed with maturin develop --locked --uv. Measured
  Rust core 1830/1849 lines (98.9724%), native binding 42/42 (100%), Python 253/260
  statements and 69/76 branches (95.8333% combined). Its 98 focused Python tests
  passed. Raw instrumented evidence stays in target/coverage-report; historical
  committed coverage reports were not rewritten as current measurements.
- Restored the main environment to an editable optimized release after coverage;
  its native SHA-256 matches the built cp312-abi3 wheel:
  cec453d9ecaf0c5a95871956e83fd714f866ce0920696d627e6a0cbc4e7fcce3.
  Wheel SHA-256: 68e9de1f33dfca079bd54a7baefd77da30e567daf1d79609bab2c068ab2da618.
  Git comparison confirms Rust core, Cargo.lock and production Python API source
  are unchanged from pre-migration 4e2217c. No performance remeasurement claim.
- Updated README, usage/tests/notebook setup and benchmark build instructions.
  Documented --all-extras/--no-sync, dependency updates, Rust rebuild cache keys,
  compiler-free bootstrap and new wheel output folder. Historical handoff and
  warm/cold evidence are marked with current setup links and require a fresh
  performance baseline after packaging/harness identity changes.
- Source/test changes are in 48ccf2c, CI in 19a1eac, benchmark transition fix in
  d988725. This final local documentation commit completes the migration. No
  push, hosted CI trigger, PR, release/package upload, remote change, history
  rewrite or enclosing-repository mutation was performed. Owner reviews/pushes.

## Baseline replication step 1B — window summaries and paper Tables 2 and 4 (2026-10-15)

- New `research/baseline/tables.py`: `summarize_terms`, `summarize_models`, `paper_table2`,
  `paper_table4` and `paper_tables`. Means are over fitted windows; a coefficient is
  significant when its two-sided z-test p-value (HC0) is below 0.05 (strict, undefined
  p-values ignored). Rows are symbols plus a cross-symbol `Average` row. Table F values use
  the classical F. A table is written only if its models exist in the config.
- `research/baseline/run.py` writes `summary_models.csv`, `summary_terms.csv`, `table2.csv`
  and `table4.csv` and records the significance rule in `run.json`. `ofi_quadratic` joins the
  default models and `configs/baseline.json`, so existing default-model tests now expect
  four models and four fitted windows.
- Tests (`tests/research/test_tables.py`): exact boundary/NaN handling of significance;
  column-to-model/term mapping on authored tables with unique values; missing models;
  all-skipped windows; a synthetic replication where trade imbalance is correlated with OFI
  but only OFI moves the price; CLI outputs. A first draft of the synthetic generator added
  one scalar of noise instead of one value per row (R² = 1); inspecting the printed numbers
  exposed it, it was fixed and a guard on R² was added.
- Checks: `python -m pytest -q tests/research` — 28 passed; `ruff check python research tests
  benchmarks scripts` and `ruff format` on the changed files passed. Rust, API and integration
  suites were not rerun (no change there).
- Real sample (`outputs/features/10s`, 4390 rows, 104 fits, no skipped window), preliminary:
  mean in-sample R² of OFI/TI is 0.68/0.40 (paper: 0.65/0.32); with both regressors the
  trade-imbalance mean z falls to 1.08 and is significant in 38% of windows (paper: 1.16, 31%).
  The quadratic term is NOT insignificant here: significant in 92% of AAPL and 46% of MSFT
  windows, negative in every AAPL window, adding 0.12 (AAPL) and 0.02 (MSFT) R² on average
  (paper: 9% of windows, +0.03). One day of two NASDAQ stocks, 13 windows per symbol; the cause
  (e.g. AAPL's wide spread and heavy-tailed OFI) is not investigated and no inference is drawn.

## Baseline replication step 1A — quadratic term and F statistics (2026-10-15)

Plan for step 1 (paper Tables 2 and 4, owner: Fedya): (A) quadratic term and F statistics in
`fit_models`; (B) per-window summaries, paper-layout tables, CLI outputs and documentation.
This entry records subtask A only.

- `research/baseline/run.py`: a model column named `<x>_signed_square` is derived as
  `x * |x|` (the paper's OFI*|OFI| term) when the data lack it; an existing column is never
  replaced and a non-numeric base fails explicitly. The input frame is not mutated.
- Metrics gain `f_statistic` (classical homoskedastic overall F) and `f_statistic_hc0`
  (statsmodels HC0 Wald F). The paper does not state which F it reports, so both are kept.
  A perfect fit yields an infinite classical F; skipped windows keep both columns empty.
- Tests in `tests/research/test_baseline.py` use authored synthetic data with a known
  answer: derived values, recovery of a known curvature coefficient, both F statistics
  against statsmodels, empty values for skipped windows and the perfect-fit case.
- Checks: `python -m pytest -q tests/research` — 20 passed; `ruff check research tests/research`
  and `ruff format --check` on the two changed Python files passed. No Rust, API or real-data
  step was touched, so the broader integration suites were not rerun.

## High-load benchmark — M3 measured baseline and completion

- Executed the complete default suite on the owner's Mac: exact 1M/10M/20M
  original quality rows, four authored symbol/session partitions, five ranks,
  10-second buckets and known-direction signing. Source commit ecdaa97.
  Command: `.venv/bin/python -m benchmarks.high_load --root
  benchmarks/results/high-load/baseline-20261014 --offline`.
- Release build/install preceded generation/timing. The serial suite completed
  24 fresh native-backed children: one warmup plus three measured repetitions
  for each of six size/config cases. All 24 passed conservation/source/schema/
  full-grid/key checks and exact decoded-output equality across repeats/settings.
  Engine/harness source and loaded extension hashes stayed unchanged; both
  source snapshots recorded a clean tracked tree. No concurrent compilation or
  heavy project tests were run during the large measurements.

| Original rows | Threads / chunk | Median seconds (min–max) | Median peak MiB (min–max) |
| ---: | --- | --- | --- |
| 1M | 1 / 4096 | 2.656 (2.617–2.901) | 121.92 (113.64–126.36) |
| 1M | 4 / 65536 | 2.551 (2.538–2.551) | 269.62 (250.09–292.12) |
| 10M | 1 / 4096 | 26.396 (26.260–26.615) | 117.48 (109.09–120.05) |
| 10M | 4 / 65536 | 25.988 (25.626–26.056) | 242.86 (226.06–270.27) |
| 20M | 1 / 4096 | 53.153 (52.907–53.774) | 109.34 (105.53–110.66) |
| 20M | 4 / 65536 | 51.378 (50.766–52.438) | 258.88 (241.28–292.86) |

- Observed throughput: 376k–392k original rows/s. Time scales approximately
  with size in this series; peak RSS does not grow proportionally to total rows.
  Maximum measured peak: 292.86 MiB. This is synthetic warm-cache-leaning evidence,
  not a universal memory bound or real-market performance claim. Both thread
  and chunk settings differ between cases; isolated thread scaling is unmeasured.
- The 20M fixture contains 19,999,804 accepted states, 800,000 executions and
  196 supplied rejected originals. Large data, exact identities, per-run command/
  measurement/verification/RSS JSONL and build/generation logs remain ignored
  under data/high_load/, outputs/features/high-load/ and benchmarks/results/.
- Added docs/high_load/ with an English measured report, reviewed scaling/RSS
  plots and a compact reusable comparison reference. Linked it from README
  and the protocol. Compact-reference verification against full evidence passed
  all six cases at exactly 1x, with identical decoded fingerprints.
- Final focused audit passed: all 24 children/snapshots/counts, stable source/
  binary identity, 20 Markdown local links, SVG parsing, visually reviewed PNG
  plots, Ruff across project Python and staged diff whitespace. The full compiled
  106-test selection passed before the large suite; only evidence/docs changed
  afterward, so it was not rerun. No new coverage percentage is claimed.
- Small fixture Quote Test and many/single-session tooling are implemented and
  tested/documented; large Quote Test/ZIP and alternative-partition measurements
  were not run in this baseline. macOS/Linux RSS support is explicit; Windows
  package support is preserved. Hosted CI checks were configured, not run here.
- Completed benchmark implementation and baseline evidence only. Rust/core/API,
  package dependencies, legacy benchmark workloads and real sample inputs remain
  unchanged. Local milestones: 1d227ce (fixtures), ecdaa97 (runner/protocol);
  this evidence update is committed separately. No optimization agent was started,
  and no push, PR, release upload or deployment was performed.

## High-load benchmark — authorized plan

- Implement benchmark tooling only; keep the Rust engine, public Python API,
  schemas, model layer and existing benchmark workloads unchanged.
- M1: bounded deterministic synthetic Lev-v1 generation with 10M/20M original
  rows, full-session timestamps, five changing levels, trades, quality gaps and
  optional paired raw CSV for Quote Test. Validate small authored fixtures.
- M2: serial fresh-process benchmark suite, release-build/source/binary/input
  provenance, RSS snapshots, repeated-run summaries, decoded-output equivalence
  and conservation checks. Test the orchestration on a small compiled workload.
- M3: execute and retain actual large-workload baseline evidence where practical,
  publish a compact report, document reruns and the later optimization protocol.
  Generated datasets, snapshots and full outputs remain ignored; commits stay local.

### M1 — bounded authored workload

- Added a row-indexed synthetic generator with bounded NumPy/Arrow batches and
  streamed ZSTD Parquet writers. Exact original-row counts are split across
  independent symbol/session partitions and cover a valid configurable session.
- Included all five changing ranks, type-4/type-5 executions, both known signs,
  deliberate supplied-quality gaps, segment/previous-state/L1-update markers and
  optional original paired CSVs. Generation records source hashes, expected
  original/accepted/rejected/trade counts and volume/sign conservation totals.
- Small fixture checks passed: 4 tests, including decoded batch-size invariance,
  timestamps within session, existing-directory protection, invalid parameters,
  and actual compiled Rust calls with both signing modes and gaps. Ruff passed
  for generator/tests. This evidence is synthetic; no large-run result yet.

### M2 — isolated measured runs, snapshots and comparison

- Added a serial suite with fresh native-backed Python children, one warmup and
  three repeats per case by default, release compilation before measurements,
  source/binary/host/input provenance and source/binary stability checks.
- Added self-process RSS snapshots: Linux /proc/self/status and macOS public
  MACH_TASK_BASIC_INFO, read by a small thread while Rust detaches from Python.
  OS high-water RSS, CPU time and page faults are recorded separately. The fixed
  sampling cost is included consistently. No third-party runtime dependency was
  added. Load RSS instrumentation is macOS/Linux; Windows native support stays intact.
- Post-run checks enforce partition/event/trade/sign/volume conservation, full
  grid/key/schema/source identities and canonical decoded feature/quality equality
  across repeats/chunk/thread cases. Baseline comparison rejects mismatched
  protocols, inputs, harness hashes, build provenance and host/runtime.
- Added failure/timeout evidence retention, unique output namespaces, CSV/JSON/MD
  summaries and optional scaling/RSS plots. Documented default and single/many/raw
  scenarios. CI now runs small benchmark-tool checks, never the multi-million suite.
- Focused checks: 10 benchmark tests passed (including both signing modes, empty
  feature output, actual child measurements/reuse/comparison and timeout failure);
  Ruff passed across all Python/research/tests/benchmarks/scripts. A separate release
  build smoke suite of 2,000 original rows completed both cases with verified output;
  plots rendered and were inspected. Small smoke timings are not load evidence.
- Full newly built native/Python/integration/research/real-data/benchmark suite:
  106 passed in 51.37s, no skips. Real-width reference acceptance remains unchanged.
  No production engine, binding, package dependency or public API source changed.
- During development, checks caught empty-Parquet iteration and result namespace
  edge cases, which were fixed. Parent process-list RSS was unavailable in the
  sandbox; self-process sampling replaced it and passed. No external approval is
  needed for the implemented method. Large baseline measurements remain M3.

## Implementation diagrams — detailed views and completion

- Added four detailed editable scenes and SVG previews: the Python/PyO3/Rust
  call sequence, Cargo crates and engine modules, bounded partition workers and
  staged output lifecycle, and the baseline/extension/notebook research layer.
- Completed the ten-view gallery with code anchors and instructions for editing
  scenes and regenerating previews. Linked it from README.md and architecture.md;
  corrected architecture prose to include the existing Python research layer and
  describe staged publication without overstating overwrite atomicity.
- Checked implementation details against the current sources: in-process cdylib,
  owned JSON/envelope/error transport, Python::detach, original-ID quality merge,
  std::thread and sync_channel(1), persistent OFI state across chunks, independent
  trade signing, right-closed buckets and ordered partition Parquet assembly.
- Final focused checks passed: `python docs/diagrams/render.py --check` (10
  scenes/previews), `ruff check docs/diagrams/render.py`, unique scene IDs and
  Excalifont/font-size validation, XML parsing and rsvg-convert rasterization of
  all 10 SVGs, and 116 local Markdown links across the gallery/README/architecture
  document. All ten previews were visually inspected; corrected previews were
  rechecked. Final tracked/staged whitespace checks passed.
- This is documentation-only work: no engine/binding/API/model source, data,
  dependencies, build settings or public interfaces changed. Engine tests and
  benchmarks were not rerun, and no new runtime/real-data/performance result is
  claimed. Scene/preview files contain no dataset rows or compiled binaries.
- The overview milestone is local commit ac15ed8. The detailed milestone is
  committed separately on local main; no push, PR or publication was performed.

## Implementation diagrams — plan and overview milestone

- The owner requested documentation of the actual implementation: architecture,
  data flow, C4, PyO3 communication, Rust crates/modules and ofi-core internals.
- Plan: commit the overview/data-flow/C4 gallery first; then commit the detailed
  bridge/core/research views and documentation navigation. Production interfaces,
  code and repository layout remain unchanged except for docs/diagrams/.
- Added six editable Excalidraw scenes and portable SVG previews: architecture,
  data flow and C4 levels 1–4. Reviewed the current engine at commit 41962ab,
  public Python API, native binding, model entry point and filesystem contracts.
- Added an English gallery with code anchors, C4 scope/notation, element counts
  and edit instructions, plus a standard-library preview renderer/check command.
- Focused evidence: scenes parsed as JSON with unique IDs and Excalifont text;
  SVGs parsed as XML and rasterized with rsvg-convert; all six previews inspected.
  Renderer preview-freshness, Ruff and Markdown local-link checks passed. The
  tracked diff check passed; staging caught a trailing blank line in the new
  gallery, corrected in the follow-up documentation milestone. No runtime code
  changed; engine acceptance was not rerun.
- Next: the four detailed views and README/architecture navigation.

Work on local `main`; do not push. This log replaces `docs/WORK_LOG.md` at the
owner's explicit request. The pre-existing deletions of that file and
`docs/IMPLEMENTATION_TASK.md` are preserved. The implementation specification is
the owner-provided attachment; `docs/DATASET_CONTRACT.md` remains normative.

## Research workspace — shared data helpers

- The owner authorized a same-repository research layer and a team-oriented README.
  Model code is explicitly allowed under `research/`; raw-event computation stays in Rust.
- Added optional research dependencies and the installed `ofi_pipeline.research` module.
  Feature loading validates accepted keys, UTC boundaries, finite numerical features,
  optional requested levels and preserved unknown TI. Lag helpers require all intervening
  intervals to be adjacent within a symbol/session and never mutate the input.
- Updated agent instructions for model locations, ignored result directories and the
  canonical `data/order_book_sample/` location. The separate Russian team-agent handoff
  requested by the owner will be delivered only in chat, not saved in this repository.
- Focused checks passed: `.venv/bin/python -m pytest -q tests/research/test_data.py`
  (10 tests, including compiled Rust output ingestion), Ruff for changed helpers/tests,
  and strict mypy (7 package source files). The sole pandas import annotation documents
  its missing bundled third-party stubs; production API checks remain enabled.
- This adds no change to Rust calculations or the core Python API.
- Intended commit: `feat(research): add validated feature loading and gap-safe lags`.

## Research workspace — runnable models and environment

- Added repository-local baseline, extension and notebook directories, JSON model
  configuration, a starter per-symbol/half-hour OFI/TI/joint OLS comparison with HC0
  covariance, common complete-case samples and explicit skipped-window reasons.
  Model runs record coefficients, metrics, source SHA256, configuration and versions.
- Added `scripts/setup.py` for source/native setup or current compatible wheel
  installation and `scripts/prepare_features.py` for one-time reusable feature output.
- Moved the unchanged ignored sample directory to `data/order_book_sample/`.
  Created new ignored feature/model outputs in the intended structured directories;
  old acceptance/benchmark outputs and historical evidence remain preserved.
- Extended CI/coverage selections for research tests and isolated wheel smoke checks
  for installed feature-loading/lag helpers. Hosted CI remains unrun; no push occurs.
- Passed: actual setup/native release compilation/import; 91 Python/integration/research
  tests; 17 focused research tests after model-metadata changes; Ruff over all Python,
  research, tests, scripts and benchmarks; strict package mypy; diff whitespace checks.
- Actual real-data workflow produced 4390 feature rows from the relocated bundle.
  The default baseline fitted 78 model/window combinations (26 windows x 3 models),
  with zero skipped fits. This is an in-sample starter, not OOS evidence or every
  paper table's full replication.
- Rebuilt the local release wheel and verified it in a fresh environment outside the
  repository: compiled native I/O, Python API/CLI, installed research loader and
  gap-safe lag helper passed. The wheel and all real/generated datasets remain ignored.
- No new full coverage measurement was made; previous engine evidence is historical.
- Intended commit: `feat(research): add reproducible baseline and shared setup`.
- Remaining: commit the team-facing README and current usage/testing navigation.

## Research workspace — team documentation

- Rewrote README as an English team entry point: installation/build, data placement,
  one-time feature computation, installed imports, starter baseline and explicit model,
  configuration, notebook, test and output locations for Fedya and Timur.
- Updated API/testing navigation for the research extra and canonical sample path.
  The README distinguishes historical engine acceptance from the new research layer;
  it does not recycle old coverage percentages as a new measurement.
- The separate Russian instructions requested for coworkers' AI agents are delivered
  only in the chat response. They are not written to a file or committed.
- Checks: reviewed README commands against actual setup, feature generation and model
  execution; reviewed local links; diff whitespace passed. No source behavior changed
  in this documentation step and no push was performed.
- Intended commit: `docs: explain the shared research workflow and model locations`.

## Original implementation checklist

- [x] M0: inspect repository, delivery integrity, physical schemas, preparation code.
- [x] M1: pure Rust workspace, compiled PyO3 extension, typed Python package.
- [x] M2: checked domain types, sessions, decimal time, configuration and ordering.
- [x] M3: streaming Parquet/gzip CSV and original quality alignment.
- [x] M4: gap-aware rank OFI, persistent state and L1 update classification.
- [x] M5: independent executions, known-direction signing and conservation.
- [x] M6: right-closed grids, original boundaries, depth and exclusions.
- [x] M7: atomic output, provenance/QC, typed errors, Python CLI.
- [x] M8: paired raw adapter and pre-execution Quote Test.
- [x] M9: full real sample integrity/parity and independently rebuilt other widths.
- [x] M10: bounded partition concurrency, chunk/thread invariance and benchmarks.
- [x] M11: isolated wheel, coverage, CI, complete English handoff documentation.

Each completed subtask records files/design decisions, exact focused commands,
outcomes/evidence, data status, intended commit message, and remaining work. Final
commit hashes are authoritative in Git history, not self-referential log entries.

## Bootstrap inspection — 2026-10-14

- Verified repository root via `git rev-parse --show-toplevel` and local branch
  `main`. Initial history: `379d32a`, `768cc8c`; branch already one commit ahead
  of `origin/main`. Only pre-existing tracked changes are the two deletions above.
- Read `AGENTS.md`, complete dataset contract and attached implementation task.
  No production code exists initially. Created this log as requested.
- Tool inventory: Homebrew Rust/Cargo 1.98.0; system Python 3.12.0; uv 0.9.13.
  Dependency environments will live in ignored `.venv`; native builds in `target`.
- Owner provided `order_book_sample/`, which contains Parquet, gzip CSV, original
  ZIP archives, quality metadata, hashes and `src/prepare_sample.py`. Read the
  preparation code without executing it. Delivery hash/schema inspection remains
  pending a repository-local inspection environment.
- Confirmed raw decimal rounding is half-up at nanoseconds, quality includes all
  original row IDs/times, reference aggregation uses original boundary states,
  and supplied `is_quote_update` includes the first original observation.
- Design: explicit versioned Lev schema; integer price units of USD/10,000;
  half-unit mids; streaming merge by original ID of events/quality/trades; no
  timestamp join, hidden sorting, or recalibration. Arrow/Parquet owns native I/O.
- Focused checks: `git status --short --branch`, `git log -5 --oneline`,
  `git rev-parse --show-toplevel`, `git remote -v`, file inventory and tool versions
  all passed. A schema inspection attempt failed because the repo-selected
  Python lacked PyArrow; creating a dedicated environment resolves this next.
- Intended commit: `docs: record implementation checklist and repository inventory`.
- Remaining: verify delivery, implement M1–M11, test and measure coverage/performance.

## M0 completion and M1 — native skeleton

- Files: workspace/core/binding Cargo manifests and sources, `Cargo.lock`,
  `pyproject.toml`, `python/ofi_pipeline/{__init__.py,_native.pyi,py.typed}`,
  `tests/integration/test_native.py`, `docs/verified_schema.md`, this log.
- Pinned PyO3 0.27.2 with Python >=3.10 stable ABI; Rust >=1.90. Pure core has
  no Python dependency. A native smoke operation runs with `Python::detach`.
  Maturin mixed layout exposes `ofi_pipeline._native` and retains type markers.
- Native test checks the loaded filename against extension suffixes and invokes
  the actual compiled function. No fallback or subprocess implementation exists.
- Checks passed: `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test --workspace --offline`
  (one core test), `cargo fmt --all -- --check`,
  `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/integration/test_native.py` (one passed),
  `.venv/bin/ruff check python tests/integration/test_native.py`, `.venv/bin/mypy`.
- Delivery inspection: 24/24 SHA256SUMS entries verified from file bytes; physical
  Parquet counts 887,810 events, 68,404 trades, 897,387 original-quality rows,
  4,680 reference quality intervals, 4,390 accepted reference rows. Schema map
  records verified Arrow dtypes and missing fields. Real feature parity is unrun.
- Environment failures resolved: sandbox networking required authorized dependency
  downloads; uv crashed in macOS system configuration, so Python venv/pip was used.
  Disk exhaustion interrupted first build/install; removed only this task's build
  and download caches, disabled dev/test debug symbols and incremental artifacts.
  Free space subsequently increased to ~2.4 GiB. Relative PYO3_PYTHON failed from
  crate build directories; the absolute interpreter path fixed it. Arrow scalar
  inspection uses integer timestamp values (no lossy Python datetime conversion).
- Intended commit: `feat(bindings): bootstrap compiled Rust and Python workspace`.
- Remaining: M2–M11; the extension currently exposes version metadata only.

## M2 — domain, time and configuration

- Added Rust `config`, `domain`, `error`, `time` modules; native owned JSON
  configuration validation; typed frozen Python `PipelineConfig` and eight
  actionable exception categories. Updated manifests/lock, stubs/exports, and
  focused Python tests. No production numerical computation moved to Python.
- Prices use checked USD/10000 integers, preserve half-tick mids and reject
  nonfinite/overprecision values. Time uses UTC int64 ns, New York DST sessions,
  deterministic decimal half-up parsing, and delivered local-ns consistency.
  Ordering permits tied times with distinct IDs and rejects duplicates, decreasing
  time, partition reversal, and missing contiguous original-quality IDs.
- Checks passed: `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test --workspace --offline`
  (8 Rust tests), `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/python/test_config.py tests/integration/test_native.py`
  (30 passed), `.venv/bin/ruff check python tests/python tests/integration`,
  `.venv/bin/mypy`, `cargo clippy --workspace --all-targets --offline -- -D warnings`.
  Final defensive session-width guard: `cargo fmt --all && cargo test -p ofi-core config --offline`
  passed. Direct invalid widths cannot divide by zero or overflow before validation.
- Real sample schemas/hashes are verified; feature parity remains unrun.
- Intended commit: `feat(core): add checked domain and exact session configuration`.
- Remaining: M3–M11; input adapters and feature computation are next.

## M3 — native streaming sample ingestion

- Added `adapter.rs`, Rust adapter fixtures/tests and explicit external-sample
  ingestion test. Pinned Arrow/Parquet 60.0.0, CSV 1.4.0, flate2 1.1.5; committed
  exact transitive resolution in Cargo.lock. Parquet uses bounded record batches
  even for the sample's single large row groups; CSV records stream through gzip.
- Lev-v1 physical names/types are explicit. Invalid UTC units/timezones, local-ns
  disagreement, null required values, missing depth, malformed files, invalid
  books/trades and inconsistent supplied signs fail with typed errors. Preserves
  ties and IDs; quality must cover contiguous original IDs starting at zero.
  Original quality has no date, so derive its New York date from UTC timestamp.
- Focused checks passed: `cargo test -p ofi-core --test adapters --offline` (3),
  `cargo test -p ofi-core --offline` (8 units + 3 adapter tests),
  `cargo clippy -p ofi-core --all-targets --offline -- -D warnings`, `cargo fmt --all`.
  Initial Clippy findings (nested if/unused mut) were fixed before commit.
- Real native ingestion check passed:
  `OFI_SAMPLE_DIR="$PWD/order_book_sample" cargo test -p ofi-core --test sample_ingestion --offline -- --ignored`
  validated every event/trade/original-quality row, ordering and time/price types,
  with 887,810 accepted events, 68,404 trades, 897,387 original rows, 9,577 rejected
  quotes; 17.58 seconds debug/test runtime. This is ingestion, not feature parity.
- Disk now has ~41 GiB free. No dataset files staged, copied or altered.
- Intended commit: `feat(io): stream validated Lev Parquet and gzip CSV inputs`.
- Remaining: merge/alignment must prove accepted/rejected correspondence before
  computing; M4–M11 including real feature parity are pending.

## M4 — gap-aware rank OFI

- Added `ofi.rs` and exported it from the pure core. Computes each requested
  occupied rank independently with checked signed int64 output. Unknown first
  observations and segment resets return `None`, not a zero transition.
- Stateful observation consumes every original quality row, proves event/quality
  ID/time/presence alignment, validates predecessor/segment/L1-change markers,
  and clears the predecessor at every rejected quote. State persists independently
  of input batch boundaries; no transition crosses a rejected gap.
- Focused checks passed: `cargo test -p ofi-core ofi::` (5 tests, including 36
  symmetric/unchanged cases and hand-computed improve/worsen/equal size cases),
  `cargo clippy -p ofi-core --all-targets -- -D warnings`, `cargo fmt --all`.
  Final book validation guard rechecked with `cargo test -p ofi-core ofi:: --offline`.
- The Cargo cache disappeared during disk cleanup; offline resolution failed once.
  Refetched the same pinned versions; no source/lock versions changed.
- Dataset remains available and verified. OFI parity is not yet measured because
  bucket output is still under implementation.
- Intended commit: `feat(core): compute checked rank OFI across original quality rows`.
- Remaining: M5–M11; file-level merge/aggregation/output and Quote Test are pending.

## M5 — independent execution signing

- Added `trades.rs`: known LOBSTER aggressor sign is `-direction`, independent
  of post-execution quote acceptance. Trade sequence rejects duplicate or
  reversed original IDs, while tied times remain valid.
- Checked volume/TI/counts, classified and unclassified volume/counts; unknown
  signs remain explicit. Failed single-trade arithmetic leaves the accumulator
  intact. Separate trades input is the only source of execution volume.
- Checks passed: `cargo fmt --all`, `cargo test -p ofi-core trades:: --offline`
  (2 tests exercising both types/signs, rejected quotes, duplicate prevention,
  conservation and accumulation overflows),
  `cargo clippy -p ofi-core --all-targets --offline -- -D warnings`.
- Actual input integrity and ingestion are verified; TI/output parity is pending.
- Intended commit: `feat(core): sign independent executions and conserve volume`.
- Remaining: M6–M11; Quote Test matching will use the original pre-state adapter.

## M6 — streaming interval aggregation

- Added `buckets.rs`: one live bucket and original-boundary state per active
  symbol/session, checked OFI/depth/counts, all supported right-closed grids,
  UTC interval ends and contemporaneous USD/tick mid changes.
- Emits every grid row to a sink, with explicit reasons and nullable features
  for exclusions. First incomplete buckets, rejected events, missing/invalid
  boundaries and unknown segment transitions are excluded. Newer rejected
  originals invalidate carried boundary states until an accepted original arrives.
- Average depth uses supplied L1-update markers only; no-update valid intervals
  use right-boundary depth. Separate executions contribute even on rejected quotes.
- Checks passed: `cargo fmt --all`, `cargo test -p ofi-core buckets:: --offline`
  (4 tests covering all widths, exact-right boundaries, empty fallback, tied times,
  last grid boundary, L1 weighting, half ticks, rejected carry, missing books,
  independent rejected-quote trades and sink/order errors),
  `cargo clippy -p ofi-core --all-targets --offline -- -D warnings`.
  A test closure borrow error was fixed before checks passed.
- Real feature parity and file-level chunk invariance await the M7 runner/output.
- Intended commit: `feat(core): aggregate original boundaries on right-closed grids`.
- Remaining: M7–M11 including atomic Parquet publication and full integration.

## M7a — file-set core and atomic output

- Added Rust `pipeline.rs`, `output.rs`, core file-set integration tests and
  SHA-256 provenance. Merges quality/events/trades by original IDs, with one-row
  lookahead per stream and one active session engine. Bounded Parquet buffers
  write accepted-only features plus the full quality grid, manifest and QC.
- A new output directory is staged beside its destination and renamed after all
  computation/writes succeed. Overwrite is explicit and limited to owned output
  directories with no other user data. Collision checks resolve symlinks and
  protect inputs. Failed computation leaves existing results intact; if publication
  restoration fails, the old directory is preserved and its location reported.
- Source hashing is one explicit streaming pass, followed by one ordered compute
  pass; no reference feature/mask reads occur. Deterministic manifest provenance
  excludes runtime timing; QC records elapsed time separately. Output signed
  values/counts use int64, unavailable excluded features use Arrow nulls.
- Checks passed: `cargo test -p ofi-core --offline` (19 units + 3 adapter tests;
  external ingestion test explicitly ignored), `cargo test -p ofi-core --test pipeline --offline`
  (2), `cargo clippy --workspace --all-targets --offline -- -D warnings`, `cargo fmt --all`.
  A fixture timestamp literal inferred as i32 was corrected to i64 before commit.
- First real native 10-second run via the in-progress compiled Python API passed:
  `run_pipeline('order_book_sample','outputs/m7-real-10s',PipelineConfig(threads=1,chunk_rows=4096))`.
  Debug runtime 21.205259375 s; AAPL 2,060 accepted/280 rejected; MSFT 2,330/10.
  Compared actual computed output with reference **after** computation: 4,390 keys,
  no missing/extra keys; all 4,680 quality flags match; exact L1–L5 OFI, TI, volume,
  event/L1-update counts; max absolute USD delta error 2.0008994461306884e-13,
  tick delta error 2.000888343900442e-11, depth error 0. This preliminary evidence
  will become a repeatable M9 acceptance report/test.
- Intended commit: `feat(core): publish streamed Parquet features and provenance atomically`.
- Remaining: finish/stage Python API/CLI separately; Quote Test and bounded
  concurrency currently fail/warn explicitly; coverage/packaging/CI pending.

## M7b — typed native API, CLI and compiled fixture integration

- Added native file-set operation with owned inputs/config inside Python::detach;
  Python `InputPaths`, typed `RunReport`/partition/signing metadata, path/environment
  normalization and installed CLI. Updated exports/stubs, packaging entry point,
  README/usage, authored fixture provenance and compiled integration/error tests.
- Rust owns reading, merge, arithmetic and output. Python creates no per-tick
  objects in production. Poison reference files verify no production oracle reads.
  Inputs support strings/pathlib and explicit Parquet or headered gzip CSV files.
- Checks passed: `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/python tests/integration` (43 passed),
  `.venv/bin/ruff check python tests`, `.venv/bin/mypy`,
  `cargo clippy --workspace --all-targets --offline -- -D warnings`,
  `.venv/bin/ofi-pipeline --help` and `python -m ofi_pipeline --help` from a
  temporary cwd in the CLI test. No pure-Python fallback is accepted.
- Fixture comparisons cover chunks 1/2/3/100 versus 65536, tied IDs/time,
  gaps, interval boundaries, all five ranks, exact TI/volume/depth expectations,
  gzip CSV equivalence, empty intervals and failed-run/overwrite/collision behavior.
- Real 10-second evidence recorded in M7a; repeatable reconciliation is next.
- Intended commit: `feat(api): expose compiled file-set pipeline and typed Python CLI`.
- Remaining: M8–M11, including raw Quote Test, actual concurrency, release benchmark,
  full coverage/clean wheel/CI. Rebuilt extension uses current sources.

## M8 — original paired raw Quote Test

- Added `raw.rs`, ZIP 6.0.0 with minimal deflate support, explicit `RawInput`
  sources and sample vendor-archive discovery. Updated Rust pipeline, Python
  input API/exports, usage and compiled raw-pair/ZIP tests.
- Message/book pairing stays by row index. Valid original pre-quotes survive
  post-quote rejection; invalid/missing pre-quotes and inside-spread executions
  remain unknown. Raw/quality IDs/timestamps, accepted post-books and execution
  fields must agree. Same-time events and buffers preserve the preceding quote.
- ZIP payloads spool once to private temporary disk files with constant-size
  copying, then stream CSV pairs; no arbitrary archive pathname is extracted.
  Raw buffers keep one previous book. Spools are removed before publication.
  This extra disk pass/cost is explicit in the manifest and documentation.
- Checks passed: `cargo test -p ofi-core raw:: --offline` (2),
  `cargo clippy --workspace --all-targets --offline -- -D warnings`,
  `.venv/bin/ruff check python tests`, `.venv/bin/mypy`, `cargo fmt --all`,
  `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/integration/test_quote_test.py tests/integration/test_pipeline.py`
  (12 passed; chunks 1/2/3/100, pre/post distinction, hidden unknowns, ZIP discovery,
  missing originals and known-direction regression). Initial fixture lint errors
  were corrected before checks passed.
- Actual sample Quote Test run passed via `run_pipeline` with threads=1,
  chunk_rows=4096: 32.299725625 seconds debug runtime; accepted rows remain
  AAPL 2,060/MSFT 2,330. AAPL classified 1,847,216 / unclassified 1,002,924
  shares (23,665/11,325 executions); MSFT classified 9,887,669 / unclassified
  936,752 shares (29,798/3,616). Total execution volume is conserved, including
  rejected post-quotes. Quote Test TI is separately labeled, not parity TI.
- Intended commit: `feat(core): sign executions against original paired pre-quotes`.
- Remaining: M9 repeatable acceptance and precision provenance, M10 bounded
  concurrency/release measurements, M11 coverage/clean wheels/CI/handoff.

## M9a — exact precision provenance

- Retain delivered rounding flags as `Option<bool>` in the event domain; missing
  flags remain unknown and are counted/warned in QC. Added per-partition delivered
  and raw rounded-timestamp counts. When original decimal text is supplied,
  validate its deterministic rounded ns/flag against delivered values without
  changing the delivered timestamp. Clean CSV with >9 timestamp fractional
  digits is rejected rather than silently truncated by the RFC3339 parser.
- Updated domain/adapter/time/pipeline, typed Python partition metadata and focused
  precision fixture. Half-up carry from 34200.999999999500 -> 34201 seconds is
  verified; a contradictory delivered flag fails as malformed data.
- Checks passed: `cargo test -p ofi-core --offline` (21 unit + 3 adapter + 2
  pipeline tests, external ingestion explicitly ignored), `cargo fmt --all`,
  `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/integration/test_pipeline.py tests/integration/test_quote_test.py`
  (13 passed), `.venv/bin/ruff check python tests`, `.venv/bin/mypy`,
  `cargo clippy --workspace --all-targets --offline -- -D warnings`.
- Real reconciliation suites are running against the verified bundle; no real
  files are committed or modified. New QC distinguishes absent flags from false.
- Intended commit: `fix(io): validate and report delivered timestamp precision evidence`.
- Remaining: M9 acceptance report, M10 concurrency/performance, M11 distribution/coverage.

## M9b — repeatable real-sample acceptance at every width

- Added opt-in `tests/real_sample/test_acceptance.py`, validation-only dependency
  extras, reproducible testing documentation and `docs/reconciliation.json`.
  Integrity fixture checks all delivered hashes, vendor source SHA256/size,
  actual schema/counts/nulls before native acceptance. Missing sample skips
  explicitly; rebuilding reference widths is explicitly opted in.
- Focused check passed:
  `OFI_SAMPLE_DIR="$PWD/order_book_sample" OFI_REBUILD_REFERENCE=1 .venv/bin/python -m pytest -q tests/real_sample --basetemp outputs/m9-acceptance`
  (5 passed in 154.32 seconds). `.venv/bin/ruff check tests/real_sample` passed.
- At 10s: all 4,680 quality decisions, 4,390 accepted keys and 290 rejected
  intervals match; exact integer OFI L1–L5, TI, volume and event/L1-update counts;
  USD max abs error 2.0008994461306884e-13, ticks 2.000888343900442e-11,
  depth 0. Verified all three delivered rounded MSFT event timestamps in QC.
- At 1/5/30/60s: separately rebuilt reference from original archives using the
  fully inspected Lev preparation code as a **test-only oracle**, then compared
  native output and full-width quality. Exact keys/integers/quality all pass;
  float errors within declared tight tolerances. Full counts/error evidence is
  in reconciliation.json. No reference code or Python math enters production.
- Cargo metadata confirms no locked dependency declares an MSRV >1.90; actual
  minimum-toolchain build and platform matrix remain M11 checks.
- Intended commit: `test(sample): reconcile native features against all reference widths`.
- Remaining: M10 bounded concurrency/release measurements; M11 coverage, clean
  wheel installation, CI and final requirement audit. Real-sample acceptance is
  now passed, not pending.

## M10a — bounded independent-partition concurrency

- Added private Rust `worker.rs`, bounded synchronous queues and deterministic
  output assembly. Producer validates/merges inputs in order; each independent
  symbol/session is owned by one persistent worker. At most configured workers
  coexist; at most one chunk queues per worker. Failed workers propagate typed
  errors, close channels and are joined before temporary output is removed.
- Intermediate partition Parquet files are streamed once into final outputs in
  key order and removed before publication. This explicit extra output pass is
  documented in the manifest. No full-day input collectors or parallel chunk
  reinitialization. Uses std threads rather than an additional global Rayon pool.
- Added observed peak worker count to typed/native QC. Added compiled tests for
  two symbols on two dates with threads/chunks (1,1)/(2,2)/(4,3)/(2,100): identical
  decoded features/quality and stable semantic provenance, independent state,
  conserved volumes, configured worker bound and no temporary output leftovers.
- Checks passed: `cargo test -p ofi-core --offline` (21 units + 3 adapter + 2
  pipeline), `cargo clippy --workspace --all-targets --offline -- -D warnings`,
  `cargo fmt --all`, `.venv/bin/ruff check python tests`, `.venv/bin/mypy`,
  `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/integration/test_parallel.py tests/integration/test_pipeline.py tests/integration/test_quote_test.py`
  (14 passed). Current source rebuilt before compiled checks.
- All-width real parity passed before this orchestration change. Release real-data
  determinism/performance and final acceptance will validate the new runner next.
- Intended commit: `perf(core): bound partition workers and assemble deterministic output`.
- Remaining: M10b measured release performance; M11 coverage/distribution/CI/audit.

## M10b — release measurements and real chunk/thread invariance

- Added POSIX benchmark runner, authored 20,000-event/two-symbol generator,
  reproduction README and `docs/performance.json` with hardware, versions,
  formats/compression, cache/timing/RSS scopes and explicit limitations.
- Release build check passed:
  `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --release --offline`
  (53.96 seconds compile; excluded from run metrics). Initial measurements
  overlapped an MSRV compile and were discarded; final fresh-process measurements
  ran after that build ended. OS cache/other host activity remain uncontrolled.
- Commands passed: `benchmarks/run.py` under `.venv/bin/python` with real sample
  and configs threads/chunks 1/4096, 2/65536, 4/1, Quote Test 2/4096, and authored
  fixture 2/4096. Exact decoded `features.parquet` and `bucket_quality.parquet`
  equality across real known-direction runs; Quote Test accepted keys/quality
  match. No synthetic data is labeled real.
- Recorded M2 Pro/10 cores/16 GiB release real known-direction wall times:
  5.3354 s (~168k original events/s; 95.59 MiB peak process RSS), 4.5565 s
  (~197k/s; 155.05 MiB), 48.8275 s (~18k/s; 50.19 MiB) for those configs.
  Real Quote Test: 5.7227 s, 79.27 MiB; synthetic 20k: 0.1131 s, 63.41 MiB.
  Whole-process RSS includes Python/native runtime. Actual peak workers 1/2/2;
  only two real partitions exist, so threads=4 cannot invent more parallel work.
- Minimum-version check also passed:
  `CARGO_TARGET_DIR=target/msrv PYO3_PYTHON="$PWD/.venv/bin/python" /Users/daniilparfenov/.cargo/bin/cargo +1.90.0 test --workspace --locked --offline`
  (21 core units + 3 adapter + 2 pipeline; external ingestion explicitly ignored).
- Intended commit: `perf: record release sample throughput memory and determinism`.
- Remaining: M11 comprehensive coverage, clean wheel smoke, CI, English handoff
  and final requirement audit. Neither implementation nor CI has been pushed.

## M11a — acceptance-audit contract hardening

- Audited the attached requirements against current code. Accepted cleaned
  messages now validate type/size/price/direction and optional raw-price scaling;
  accepted type-4/type-5 executions must match independent trade fields exactly.
  Missing or contradictory executions fail, preventing plausible incomplete TI.
  Updated event domain/adapter/worker and authored fixtures accordingly.
- Full Quote Test TI is now null when any execution is unclassified; explicit
  `classified_trade_imbalance` and `trade_signing_complete` columns retain the
  partial evidence. Typed signing metadata exposes `complete_trade_imbalance`.
  This replaces a plausible zero/partial sum masquerading as full unknown TI.
- Added checked pre-book validation, contextual input/worker errors, and a small
  publication rename seam. Production still calls std::fs::rename; fault tests
  simulate second/third rename failures and verify actual original file contents
  are restored or preserved in a recoverable backup. No blanket coverage exclusion.
- Added focused malformed/empty/truncated evidence, bad units/signs, missing
  schema fields, duplicate headers, outside-session and atomic-publication tests.
- Checks passed: `cargo test -p ofi-core --offline` (21 units + 3 adapter + 2
  pipeline before added publication tests), `cargo test -p ofi-core output:: --offline`
  (2 publication/path tests), `cargo clippy --workspace --all-targets --offline -- -D warnings`,
  `cargo fmt --all`, `.venv/bin/ruff check python tests scripts benchmarks`,
  `.venv/bin/mypy`, `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --offline`,
  `.venv/bin/python -m pytest -q tests/python tests/integration` (62 passed).
- Earlier Python measurement reached 100% production lines/branches (182 lines,
  30 branches); native-binding preliminary measurement covered all 42 authored
  lines. Rust/native profiles will be rebuilt from the frozen final sources and
  inspected for uncovered reachable code; preliminary coverage is not final.
- Intended commit: `fix(core): validate execution evidence and represent unknown TI explicitly`.
- Remaining: full final-source Rust/native/Python coverage, isolated wheel, CI
  docs/handoff, real parity and refreshed performance after this contract change.

## M11b — bounded metadata and final-boundary checks

- Added explicit `max_partitions` (default 1024, range 1..16384) to native/Python
  config and CLI, bounding returned metadata as well as live worker state.
  Lev-v1 quality reasons use a fixed validated vocabulary, so rejection-count
  maps cannot grow once per event. Unknown reasons require an explicit adapter
  change rather than hidden regrouping or recalibration.
- Fixed final bucket flushing near the int64 UTC-nanosecond limit: no unused
  next boundary is computed after session close. Added an extreme-range session
  regression, depth/trade mismatch guards, initial quality-ID validation,
  disappeared-source hashing and contained dependency-panic tests.
- Focused checks passed: `cargo test -p ofi-core --offline` (26 unit, 3 adapter,
  2 pipeline tests; external ingestion explicitly ignored),
  `.venv/bin/python -m pytest -q tests/python/test_config.py tests/integration/test_parallel.py tests/integration/test_pipeline.py`,
  `cargo fmt --all -- --check`, `.venv/bin/mypy`.
  Prior rebuild/check for these changes: maturin develop, Clippy and full
  Python/compiled fixture selection passed (65 tests). An extreme test initially
  chose a local clock beyond representable UTC; corrected its clock before pass.
- Real files remain unchanged and outside Git. Current final-source parity,
  coverage and wheel checks are next; earlier evidence is retained as historical.
- Intended commit: `fix(core): bound report metadata and stop at final session boundary`.
- Remaining: coverage gap audit, clean wheel/CI, refreshed real acceptance and
  performance, English final handoff. External `.gitignore` edit is preserved;
  Cargo.lock remains tracked and committed despite its added ignore rule.

## M11c — final measured coverage and error evidence

- Added `scripts/coverage.py`, `docs/coverage.{md,json}`. Matched Rust 1.90/LLVM
  instrumentation covers test executables plus the real Python-loaded native
  library; source SHA256 is frozen before/after. Raw reports remain in ignored
  target output, with a portable per-module summary committed. No blanket
  production exclusions; inline test bodies are outside the production scope.
- Added overflow tests in core time/raw modules; compiled error tests cover
  corrupt/unpaired original ZIP/CSV evidence, uneven CSV, invalid integer fields,
  missing original quality, and checked partition-volume overflow. Worker volume
  errors now retain original event/symbol/date/UTC ns context.
- Exact check passed: `.venv/bin/python scripts/coverage.py --toolchain 1.90.0`
  (28 Rust unit + 3 adapter + 2 pipeline; 74 Python/compiled integration tests).
  Core: 1756/1764 lines (99.5465%); binding 42/42 (100%); Python 187/187 and
  30/30 branches (100%). Eight missed core counters remain visible: six internal
  invariant guards, OS thread-spawn failure, and final QC-write device failure.
  Their precise limitations are documented, not reported as measured 100%.
- Additional checks passed: `cargo fmt --all -- --check`,
  `PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --workspace --all-targets --locked --offline -- -D warnings`,
  `.venv/bin/ruff check python tests scripts benchmarks`, `.venv/bin/mypy`,
  `git diff --check`.
- Real data remain available and unchanged. Coverage uses authored fixtures;
  final release real-sample acceptance is separate and next.
- Intended commit: `test: measure core native and Python coverage with error evidence`.
- Remaining: rebuild final release/wheel, complete distribution CI docs,
  final all-width parity/performance refresh and English handoff audit.

## M11d — isolated wheel, CI and public contracts

- Added `scripts/wheel_check.py` and `.github/workflows/ci.yml`: isolated wheel
  API/CLI/error/Parquet/type-marker checks plus Linux/macOS/Windows Python
  3.10/3.12 build/import/test matrix and separate Linux instrumented coverage.
  Workflow YAML parses with both expected jobs. Hosted CI is unrun because
  commits remain local; no remote execution or publication was requested.
- Added English architecture and full output schema/interval contract;
  expanded usage/configuration/error/installation docs and reproducible checks.
  Updated verified schema with required execution price, precision-flag behavior
  and link to measured parity. Corrected AGENTS.md's obsolete deleted-document
  references to the owner-authorized attachment/CHANGELOG workflow.
- Final release checks passed:
  `VIRTUAL_ENV="$PWD/.venv" .venv/bin/maturin develop --release --locked --offline`
  (22.30 s compilation), `.venv/bin/maturin build --release --locked --offline --out dist`
  (21.71 s compilation; deployment target causes a separate artifact).
  `.venv/bin/python scripts/wheel_check.py 'dist/*.whl'` passed in a fresh temp
  Python 3.12 environment outside checkout; loaded native belongs to that venv.
  Hand fixture produced OFI [30,0], TI/volume [7,0], depth [125,125], quality
  [false,true,true]; installed CLI and typed missing-input error also passed.
- Wheel contains native shared library, Python API/CLI, _native.pyi and py.typed.
  No Rust compiler is used by the isolated installed-wheel test. Dependency
  download was limited to pinned inspection-only PyArrow in that temp venv.
- Checks passed: `ruby -e 'require "yaml"; p YAML.load_file(".github/workflows/ci.yml").fetch("jobs").keys'`,
  `.venv/bin/ruff check python tests benchmarks scripts`, `git diff --check`.
  Production source SHA256 still matches the committed coverage snapshot.
- Real data are unchanged and available. Final all-width acceptance is running
  against the current release. Removed only the task-generated stray profraw;
  canonical raw coverage evidence remains under ignored target output.
- Intended commit: `build: verify isolated wheels and define platform CI checks`.
- Remaining: final real acceptance, refreshed release metrics, handoff/status audit.

## M11e — final release acceptance and refreshed measurements

- Refreshed `docs/reconciliation.json` and `docs/performance.json` from current
  release output; added portable `docs/acceptance.json` with source SHA256,
  wheel hash and per-layer final checks. Dataset and generated tables remain
  ignored. All 24 delivered hashes and source archive hashes/sizes were checked.
- Exact final full check passed:
  `OFI_SAMPLE_DIR="$PWD/order_book_sample" OFI_REBUILD_REFERENCE=1 .venv/bin/python -m pytest -q tests/python tests/integration tests/real_sample --basetemp outputs/final-acceptance`
  (79 passed in 54.98 s; 74 self-contained and 5 actual real-width tests).
  Integer OFI L1..L5/TI/volume/counts, accepted keys and full quality agree at
  1/5/10/30/60 s. 10 s: 4390 accepted / 4680 total / 290 excluded, AAPL 2060,
  MSFT 2330; 3 delivered rounded MSFT timestamps. Float errors stay below
  declared USD 1e-10, ticks 1e-8, depth 1e-10 tolerances (depth exact).
- Rust final checks passed:
  `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test --workspace --locked --offline`
  (28 unit + 3 adapter + 2 pipeline; default external test explicitly ignored),
  `OFI_SAMPLE_DIR="$PWD/order_book_sample" cargo test -p ofi-core --test sample_ingestion --locked --offline -- --ignored`
  (1 passed in 21.99 s; 887810 events, 68404 trades, 897387 original rows,
  9577 rejected quotes). Rust 1.90/LLVM coverage tests also passed in M11c.
- Final release benchmarks ran sequential fresh processes after compiler/test
  jobs ended. Exact commands/configs/scopes are in `docs/performance.json`:
  real t1/c4096 4.0239 s, 99.27 MiB; t2/c65536 3.9107 s, 323.13 MiB;
  t4/c1 31.2190 s, 54.77 MiB; real Quote Test t2/c4096 4.3259 s, 102 MiB;
  authored 20k t2/c4096 0.1029 s, 62.31 MiB. Hardware M2 Pro/10 cores/16 GiB.
  Whole-process RSS, uncontrolled warm-leaning OS cache, one run per config;
  no general speedup or RSS guarantee. Compile/install excluded.
- PyArrow inspection asserted exact decoded features/full quality and stable
  manifest equality across known-direction chunks/threads. Quote Test quote
  features, accepted keys/quality and total trade volumes/counts are unchanged;
  classified/unclassified conservation is exact. Signing differences remain
  explicit unknown TI, not a parity claim against known direction.
- Intended commit: `test: record final release acceptance and measured determinism`.
- Remaining: English handoff/ordered local history, final repository audit.

## M11f — final English handoff and repository audit

- Added `docs/handoff.md` with API example, full final evidence, coverage limits,
  actual all-width parity, Quote Test conservation, measured release performance,
  operational limitations and ordered authoritative local commits. Updated README
  from bootstrap/pending language to verified completion. Marked M11 complete.
- Documentation points to reproducible commands, portable source/wheel hashes,
  schema/units and per-milestone evidence. Hosted platform CI remains explicitly
  unrun. No research model, GUI/server/database, TAQ claims or trading result
  was added. Optional standalone Rust CLI is omitted; installed Python CLI shares
  the engine. No real data or generated binary/output is committed.
- Final checks: docs/evidence consistency and link review, `git diff --check`,
  production SHA256 verification against measured coverage snapshot,
  `git status --short --branch`, `git ls-files order_book_sample raw data outputs dist`,
  and ordered `git log` audit. Functional/lint/type/coverage/wheel/real acceptance
  results are recorded in M11c–M11e; no production sources changed afterward.
- Repository status: all task changes committed after this entry; only the
  external `.gitignore` edit remains dirty. Cargo.lock is tracked despite its
  new ignore rule. Owner-requested docs deletions remain preserved. No push,
  release/package upload, PR or remote hosted execution occurred.
- Intended commit: `docs: hand off verified Rust pipeline and local acceptance`.
- Remaining required implementation work: none. Known limitations remain honest
  coverage/OS paths, unrun hosted platform matrix, scoped Lev-v1 data and
  documented filesystem/cache/temporary-disk behavior.

## Windows CI — close test-owned Parquet readers before overwrite

- Both supplied Windows/Python 3.10 and 3.12 logs successfully compiled the Rust
  workspace and passed core unit/adapter tests. They failed at the same owned-output
  overwrite in `crates/ofi-core/tests/pipeline.rs` with OS error 5 (access denied).
- The test retained its Parquet reader/file handle across directory replacement
  and backup cleanup. Explicitly drop that reader before overwrite, and scope the
  post-overwrite reader so it is also closed before later directory operations.
- Strengthened the existing cross-platform test: verify the rewritten Parquet is
  readable and both staging and backup directories are removed after success.
  No Windows test was disabled and the Windows CI matrix remains enabled.
- Production Rust, Python API, project structure and output semantics are unchanged;
  this avoids overlapping the separate optimization agent's implementation work.
- Checks passed on macOS: `cargo test -p ofi-core --test pipeline --locked --offline`
  (2 tests); `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test --workspace --locked --offline`
  (33 tests, 1 explicitly ignored external-sample test); `cargo fmt --all -- --check`;
  all-target workspace Clippy with `-D warnings`; diff whitespace review.
- Native Windows execution is unavailable on this host. The owner will push and
  verify both Windows jobs; local checks do not constitute a Windows CI pass.
- Intended local commit: `test: close Parquet readers before Windows overwrite`.
- No push, remote run, release or package publication was performed.

## Rust optimization P0 — baseline and measured plan (2026-10-14)

- Objective: improve execution speed/throughput first and memory second using only Rust implementation changes. Public interfaces, Python/research sources, numerical/quality/signing semantics, output/publication contracts, worker/chunk bounds and project layout are frozen. Work on local main; no push or publication.
- Verified nested repository root and clean working tree at `66e3978`. Read AGENTS.md, README.md, architecture, benchmark README/runner/generator, performance evidence, core/binding code and delivered reference preparation. Existing benchmark options were discovered with `--help`; benchmark workloads/configuration are unchanged.
- Inventory/grouping fixed before optimization: real known-direction family has t1/c4096, t2/c65536, t4/c1; real Quote Test has t2/c4096; authored 20,000-event/two-symbol family has t2/c4096. All cover hash/ingestion, OFI, aggregation, ordered Parquet assembly and publication. Known-direction covers independent execution signing; Quote Test additionally ZIP extraction, raw paired-row alignment, pre-book signing and unknown TI. The real input has rejected gaps/ties and two partitions; the fixture has alternating sizes and one execution per 100 rows. Chunk one stresses batch construction, queues and memory; t1/t2/t4 cover worker bounds; large chunks stress memory.
- Balanced aggregate: geometric mean of normalized case speedups within each family, then geometric mean of the three family means. Every per-case result remains primary; no raw-time averaging. Five serial fresh-process measured runs per case after one unmeasured warm-up per case, rounds in fixed case order. OS cache uncontrolled and warm leaning; no cold-cache measurements. No compilation, installation, fixture generation, profiling or test jobs overlap execution timings; other host activity is uncontrolled.
- Baseline current-source release rebuilt with `VIRTUAL_ENV="$PWD/.venv" PYO3_PYTHON="$PWD/.venv/bin/python" .venv/bin/maturin develop --release --locked --offline` (26.31s excluded). Rust/Cargo 1.98.0, LLVM 22.1.8, Python 3.12.0, macOS 26.5.1 arm64; Mac14,9 Apple M2 Pro, 10 cores (6 performance/4 efficiency), 16 GiB. Cargo.lock and build settings unchanged.
- Commands/evidence in existing ignored paths: `.venv/bin/python benchmarks/results/optimization_measure.py baseline` drives the unchanged `benchmarks/run.py` for every case; `benchmarks/results/optimization/baseline/metadata.json` stores full config definitions, input hashes/sizes, toolchain, commit and loaded-extension SHA256. Raw runs and complete outputs are retained alongside it. Fixture is the existing generator-authored `benchmarks/results/final-authored-fixture` (10,000 rows per symbol), not duplicated real data.
- `.venv/bin/python benchmarks/results/optimization_verify.py baseline` passed: all 30 decoded outputs have exact ordered values, schemas, floating values and nulls, exact manifests, and exact QC after excluding output paths/timing/observed worker peak. Known-direction chunk/thread invariance and Quote Test quote/quality/count/volume equality and classified/unclassified conservation passed.

| Existing case | Median seconds (min–max; MAD) | Median original rows/s | Median peak process MiB (min–max) |
| --- | --- | ---: | --- |
| real-t1-c4096 | 4.003722 (3.963808–4.299242; 0.039914) | 224,138 | 94.78 (89.55–102.58) |
| real-t2-c65536 | 4.259727 (3.950010–4.428237; 0.075049) | 210,668 | 242.22 (199.55–293.53) |
| real-t4-c1 | 33.139421 (32.214164–34.321532; 0.925257) | 27,079 | 51.92 (50.80–54.17) |
| quote-t2-c4096 | 4.358771 (4.347334–4.598869; 0.011438) | 205,881 | 98.25 (88.97–102.12) |
| fixture-t2-c4096 | 0.110453 (0.106891–0.119692; 0.003561) | 181,073 | 63.81 (59.05–67.28) |

- Source identities (SHA256; sizes in bytes):
  - `benchmarks/results/final-authored-fixture/data/events_clean.parquet`: `caf83a1859db44484a9f2e962771a00deed364eed211dfcb348dba32c7038146`, 190682.
  - `benchmarks/results/final-authored-fixture/data/trades_clean.parquet`: `1baa70fed833564919f98e2377e21ef142e80c27e75f4ef67e006de9205dc400`, 5790.
  - `benchmarks/results/final-authored-fixture/reports/event_quality.parquet`: `ac8fef7e0589fb219a23b4fe274335b6e3b416884a6074f00a5d2240d1de626c`, 182070.
  - `data/order_book_sample/data/events_clean.parquet`: `514dd1f6491ec99b2558054ccf0c3fb5add2c6d34e2d8e004b1ad0572a4cb2fa`, 25095171.
  - `data/order_book_sample/data/trades_clean.parquet`: `62db3864391b99accff35bbb734a5091d0df661fea3291f55e2037255cd02f3c`, 1306691.
  - `data/order_book_sample/reports/event_quality.parquet`: `fe0f0806b59f122c22bdcc74df01f4fbb85dc8e8a81a53fde5f1d1f51d230b13`, 8137742.
  - `data/order_book_sample/raw/LOBSTER_SampleFile_AAPL_2012-06-21_5.zip`: `46419dd0d6106be5fcf43600ccd08b2baa5d4cfb76284f1c58773537a3adac50`, 4791006.
  - `data/order_book_sample/raw/LOBSTER_SampleFile_MSFT_2012-06-21_5.zip`: `94e65c07786b8d54712fe9a12aee29d51f418d402e96b6e21b4af1d0bd44131d`, 7515038.
- Profiling: `/usr/bin/sample <own-benchmark-pid> 3 1 -mayDie -file <ignored-profile>` succeeded outside the sandbox for normal (t2/c65536), tiny (t4/c1) and Quote Test (t2/c4096). Sandbox-only attempts could not inspect the processes; they are not claimed as successful profiles. Profiling runs were separate from measured runs.
- Normal profile shows 303 inclusive samples in format_inner, 281 in Row::index and 123 in validate_local_ns plus 68 in date_for_timestamp, across 1473 sampled main-thread stacks. These inclusive counts can overlap and are diagnostic, not additive timing percentages. Tiny profile shows 1503 inclusive read_records samples among 2208 main-thread stacks; Arrow per-batch work dominates. Worker synchronization is present but less prominent. Profiles retained under `benchmarks/results/optimization/profile-*-authorized.txt`.
- Plan: independently test/measure metadata/allocation reductions in ingestion, bounded reuse of parsed calendar metadata with per-row checks preserved, and remaining measured allocation bottlenecks. Keep only supported improvements; investigate regressions. Each retained focused subtask gets Rust tests, rebuilt compiled integration checks, all affected benchmarks, diff review, log evidence and a local commit. Final handoff requires full correctness/research/real-width acceptance, isolated wheel and complete final benchmarks.

## Rust optimization P1 — avoid per-cell metadata allocation

- Hypothesis from baseline sampling: per-event book-column formatting, duplicated Parquet string-column lookup, and allocation of a timestamp type descriptor consume producer CPU. Replaced book-name formatting with fixed names for all five supported ranks, used one name lookup for Parquet text, and matched the timestamp type/timezone without allocating. All schema/type/null/price checks and required/optional fields remain in place; reader batch size, worker queues and output buffers are unchanged. No new dependency/build setting/unsafe code.
- Added a focused Rust adapter regression for every depth 1..5, reversed physical column ordering, chunks 1/2 and nonrepresentable last-rank prices. Existing Parquet null/schema/error and CSV/gzip tests remain unchanged.
- Passed `cargo fmt --all`; `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test -p ofi-core --test adapters --locked --offline` (4 tests); rebuilt release via the P0 maturin command (4.22s excluded); `.venv/bin/python -m pytest -q tests/integration/test_pipeline.py tests/integration/test_parallel.py tests/integration/test_native.py` (26 passed). Inspected the focused diff and ran `git diff --check`.
- Complete five-case, five-run measurements plus one warm-up: `.venv/bin/python benchmarks/results/optimization_measure.py columns`. `.venv/bin/python benchmarks/results/optimization_verify.py columns` passed exact decoded tables/schema/null/float/order/manifest/stable-QC parity for all 30 outputs, source identity equality, chunk/thread invariance and Quote Test conservation. Generated evidence stays ignored.
- Results below use P0 baseline and identical conditions. Real known-direction normal chunks and Quote Test ranges separate clearly from baseline; tiny-chunk improvement is smaller but ranges also separate. Authored fixture shows improvement in the median with overlapping/outlier ranges, so its precise magnitude remains noisy. RSS ranges overlap in all cases; the +4.0% t1 median is inconclusive rather than a memory improvement. Active workers stay 1/2/2/2/2. Retained for consistent execution improvements without expanded memory/worker bounds.

| Case | Median s (min–max; MAD) | Rows/s | Peak MiB (min–max) | Speedup vs baseline / previous |
| --- | --- | ---: | --- | --- |
| real-t1-c4096 | 2.988045 (2.925521–3.010416; 0.012983) | 300,326 | 98.59 (90.47–109.59) | 1.340x / 1.340x |
| real-t2-c65536 | 3.062198 (2.915328–3.128592; 0.066394) | 293,053 | 201.08 (185.31–282.55) | 1.391x / 1.391x |
| real-t4-c1 | 31.194508 (30.919520–31.516923; 0.274988) | 28,767 | 51.19 (49.84–53.91) | 1.062x / 1.062x |
| quote-t2-c4096 | 3.400197 (3.321258–3.455427; 0.047077) | 263,922 | 95.16 (90.25–99.31) | 1.282x / 1.282x |
| fixture-t2-c4096 | 0.090778 (0.086294–0.121728; 0.004485) | 220,317 | 62.44 (61.41–65.14) | 1.217x / 1.217x |
Family speedups: {"real-direction": 1.2557329911622168, "authored": 1.2167305691766097, "real-quote": 1.2819172856587175} balanced: 1.2511726503903464

- Decision: retain. Balanced family-weighted speedup 1.251x; all case median times improved. Next: remove repeated calendar parsing/formatting while retaining per-row validation.

## Rust optimization P2 — reuse bounded calendar metadata

- Hypothesis from P0 profiling: repeated date/clock parsing and formatting wastes producer CPU even though the parsed local midnight repeats across adjacent rows. Added one-entry calendar metadata per TableReader: parsed midnight and formatted quality date. Local New York date is still derived per quality row (no fixed 24-hour DST assumption); every row checks local-day range, checked midnight-plus-nanoseconds arithmetic and exact timestamp agreement. Date changes replace the entry; invalid/overflowing dates preserve existing errors. No event/output result caching, sorting or validation removal. Memory state stays constant per reader, independent of rows/partitions; all batch/queue/worker bounds remain unchanged.
- Added Rust regression coverage for date replacement/return, winter/summer and DST transition dates, repeated dates, invalid dates, nonrepresentable midnight, time range, timestamp mismatch and int64 extrema. Public time functions/signatures and Row enum remain unchanged.
- Passed `cargo fmt --all`; `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test -p ofi-core --locked --offline` (29 units + 4 adapters + 2 pipeline; external ingestion explicitly ignored pending final explicit run); rebuilt release via P0 command (4.87s excluded); `.venv/bin/python -m pytest -q tests/integration/test_pipeline.py tests/integration/test_parallel.py tests/integration/test_native.py tests/integration/test_quote_test.py` (37 passed). Inspected diff and passed `git diff --check`.
- Same complete benchmark protocol: `.venv/bin/python benchmarks/results/optimization_measure.py calendar`; `.venv/bin/python benchmarks/results/optimization_verify.py calendar` passed source identity plus all 30 complete outputs exactly, chunk/thread invariance and Quote Test conservation. `calendar/metadata.json` additionally records Rust source SHA256, lockfile SHA256 and working-tree changes; loaded extension hash is captured. These are final-source suite measurements if no further production edits are retained.
- Comparison below includes baseline and incremental P1 speedups. Normal real-input improvements are clearly beyond noise; incremental tiny-chunk and authored-fixture gains are less certain because ranges overlap. Every final case time range is below its baseline range. All median times improved; no execution regression was observed.
- RSS remains inconclusive: t1 median is +5.6% vs baseline, t2 -4.4%, tiny +0.7%, Quote Test +1.6%, fixture +0.1%; ranges overlap and t2 has a larger maximum. No memory reduction is claimed. Reviewed allocations/state/buffering: two small one-entry metadata values per reader are added; no larger input/output buffer, batch, queue or worker count. Faster producer/consumer scheduling can change occupancy/allocator peaks, which is an inference rather than a demonstrated cause. Prioritize measured execution gains while retaining the existing operational bounds.

| Case | Median s (min–max; MAD) | Rows/s | Peak MiB (min–max) | Speedup vs baseline / previous |
| --- | --- | ---: | --- | --- |
| real-t1-c4096 | 2.487382 (2.413924–2.512182; 0.024800) | 360,776 | 100.11 (94.33–101.06) | 1.610x / 1.201x |
| real-t2-c65536 | 2.422396 (2.371252–2.460587; 0.029998) | 370,454 | 231.53 (198.98–334.84) | 1.758x / 1.264x |
| real-t4-c1 | 30.477616 (30.403882–30.970772; 0.073734) | 29,444 | 52.27 (50.25–55.59) | 1.087x / 1.024x |
| quote-t2-c4096 | 3.162698 (3.118882–3.249435; 0.012279) | 283,741 | 99.83 (91.52–109.59) | 1.378x / 1.075x |
| fixture-t2-c4096 | 0.079602 (0.072534–0.090688; 0.006802) | 251,250 | 63.89 (59.16–66.91) | 1.388x / 1.140x |
Family speedups: {"authored": 1.387565515394952, "real-quote": 1.3781811460777311, "real-direction": 1.4545901845478582} balanced: 1.4063718069161835

- Decision: retain. Baseline-to-final balanced family-weighted speedup 1.406x. Remaining: complete workspace/compiled/research/real-width acceptance, explicit Rust real ingestion, isolated final wheel, final profiling and handoff audit.

## Rust optimization P3 — final acceptance and handoff

- Retained production changes are commits `39388ee` (per-cell metadata allocation) and `7bbe1aa` (bounded parsed local-day metadata); baseline protocol/evidence is `c4c2aba`. The independently authored `c0ce6a6` Rust test portability/log commit arrived during the profiling phase and was preserved. It changed no production implementation, inputs or benchmark workload. No unrelated change was reverted, staged or amended by this optimization task.
- Final-source correctness passed:
  - `cargo fmt --all -- --check`.
  - `PYO3_PYTHON="$PWD/.venv/bin/python" cargo clippy --workspace --all-targets --locked --offline -- -D warnings`.
  - `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test --workspace --locked --offline`: 29 core units, 4 adapter tests and 2 pipeline tests passed. External sample test is ignored by the default suite, then explicitly executed below.
  - `OFI_SAMPLE_DIR="$PWD/data/order_book_sample" cargo test -p ofi-core --test sample_ingestion --locked --offline -- --ignored`: one real-data ingestion test passed (15.01s).
  - `CARGO_TARGET_DIR=target/msrv PYO3_PYTHON="$PWD/.venv/bin/python" /Users/daniilparfenov/.cargo/bin/cargo +1.90.0 test --workspace --locked --offline`: the same 35 self-contained Rust tests passed; opt-in external test is ignored on this toolchain, not claimed as run twice.
  - `OFI_SAMPLE_DIR="$PWD/data/order_book_sample" OFI_REBUILD_REFERENCE=1 .venv/bin/python -m pytest -q tests/python tests/integration tests/research tests/real_sample --basetemp outputs/features/optimization-acceptance`: 96 passed, no skips (55.07s). Actual newly rebuilt native-extension calls, CSV/gzip/Parquet, null/unknown TI, tied timestamps, gaps/sessions/incomplete buckets, chunk/thread invariance, typed errors and publication/overwrite fault protections are covered by these existing tests.
  - `.venv/bin/ruff check python research tests benchmarks scripts`; `.venv/bin/mypy` (7 package source files); `git diff --check`.
- All 24 delivered hashes and raw archive source identities passed real acceptance. Independently rebuilt reference widths 1/5/10/30/60s passed exact accepted keys/quality/integer OFI L1..L5/TI/volume/counts. Accepted counts are 45,966 / 8,985 / 4,390 / 1,382 / 650. Maximum midpoint-change error across widths is 2.183e-13 USD and 2.183e-11 ticks; depth exact, below existing 1e-10 USD / 1e-8 ticks / 1e-10 depth tolerances. Reconciliation reports are retained under ignored `outputs/features/optimization-acceptance`.
- Final wheel: `PYO3_PYTHON="$PWD/.venv/bin/python" .venv/bin/maturin build --release --locked --offline --out dist` passed (39.03s build excluded). `.venv/bin/python scripts/wheel_check.py 'dist/*.whl'` passed outside the checkout in a fresh Python 3.12 venv: local-wheel API/CLI invoke its installed native library, hand-calculated OFI/TI/volume/depth/quality, manifest, missing-input errors, research loader/lag helper and bundled stubs/type markers. No Rust compiler is used by the isolated installation. Log retained in `benchmarks/results/optimization/wheel-check.log`.
- Ignored local wheel SHA256: `d3b6cffa30e2ac1a1ce6bb5529acaf279047cee2003f2805d3d7dfe28d188919`. No wheel/package was published.
- Final benchmark evidence is the complete `calendar` suite, measured after the final production changes, with the same warm-up/five-run serial fresh-process policy as P0. Source, Cargo.lock and measured loaded-extension SHA256 were audited unchanged after full tests and wheel build. No extra favorable runs were substituted; compilation, profiling, fixture creation and correctness checks are outside all measured calls. Exact baseline/final decoded-equivalence evidence is in `baseline/equivalence.json` and `calendar/equivalence.json` (30 complete outputs each); all schema, ordered integers/floats/nulls, full quality, manifests and stable QC match exactly.

Baseline to final (B → F); time variability is median absolute deviation; process RSS variability is observed min–max, not a bound:

| Case | Median seconds B → F (MAD B → F) | Median original krows/s B → F | Median peak MiB B → F (range B → F) | Speedup |
| --- | --- | ---: | --- | ---: |
| real-t1-c4096 | 4.003722 → 2.487382 (0.039914 → 0.024800) | 224.138 → 360.776 | 94.78 → 100.11 (89.55–102.58 → 94.33–101.06) | 1.610x |
| real-t2-c65536 | 4.259727 → 2.422396 (0.075049 → 0.029998) | 210.668 → 370.454 | 242.22 → 231.53 (199.55–293.53 → 198.98–334.84) | 1.758x |
| real-t4-c1 | 33.139421 → 30.477616 (0.925257 → 0.073734) | 27.079 → 29.444 | 51.92 → 52.27 (50.80–54.17 → 50.25–55.59) | 1.087x |
| quote-t2-c4096 | 4.358771 → 3.162698 (0.011438 → 0.012279) | 205.881 → 283.741 | 98.25 → 99.83 (88.97–102.12 → 91.52–109.59) | 1.378x |
| fixture-t2-c4096 | 0.110453 → 0.079602 (0.003561 → 0.006802) | 181.073 → 251.250 | 63.81 → 63.89 (59.05–67.28 → 59.16–66.91) | 1.388x |

- Balanced aggregate: real-direction family 1.455x, real Quote Test 1.378x, authored family 1.388x; equal-family geometric mean **1.406x**. Every case median improved. Final execution ranges separate from baseline; exact magnitude, particularly short fixture runs, remains subject to uncontrolled host/cache variation. No cold-cache or universal speedup claim.
- No execution regressions observed. Memory benefit remains inconclusive: overlapping ranges, t1 median increased 5.6%, and t2 final maximum is 334.84 MiB vs baseline 293.53 MiB despite its lower median. Configured chunk/output buffers, queues and worker limits are unchanged; speed is the first priority. Peak workers remain within limits. These are whole-process fresh-process RSS observations, not guaranteed upper bounds.
- Final profiles: own-process `/usr/bin/sample` captures retained as `profile-final-tiny.txt`, `profile-final-quote.txt` and `profile-final-normal-loop.txt`. The initial final-normal process ended before useful stacks were captured (empty profile); repeated identical public calls in one diagnostic process captured 2199 main-thread samples. No profile elapsed time is benchmark evidence. In that normal diagnostic, book-name format_inner no longer appears; Row::index has 781 inclusive samples, hash_one 519 and read_records 591 (overlapping counts). One-row profile retains 1115 read_records samples and 95 synchronization samples. Remaining bottlenecks are per-batch Arrow materialization at tiny chunks, name hashing/downcasts, allocator/key/book copies and raw CSV/ZIP work in Quote Test. Larger decoder batches could change memory bounds, so no speculative batching rewrite was retained.
- Final audit: only existing Rust adapter/time files and Rust adapter tests changed in this task, plus allowed CHANGELOG updates. Python/research/binding sources, public signatures/config/defaults/supported values, benchmark sources/configurations, dependencies/Cargo.lock/build profiles and project structure are unchanged. OFI/signing/interval/gap/precision/quality/hash/publication contracts are preserved, supported by the checks above. Generated data/results/profiles/binaries stay in existing ignored locations. No new coverage percentage or hosted cross-platform CI result is claimed.
- Final working tree was clean after the implementation commits; this administrative evidence update is committed separately and status rechecked afterward. No push, PR, release/package upload, remote-setting change or deployment was performed. Owner reviews and pushes local commits. Required optimization and validation work is complete; remaining bottlenecks and inconclusive RSS effects are disclosed above.


## Supervised optimization and low-residency benchmark plan — 2026-10-14

- Owner-authorized English, zero-context optimization agents inspect independent bounded subtasks; prioritize execution time, then RSS. Public interfaces, data semantics, fixture bytes and existing benchmark sources remain frozen. Normal comparison guards include ignored Python files recursively beneath benchmarks/results.
- Root schedules all builds, CPU-heavy checks, profiles and measurements serially. Preserve the regular five-case reference and normal plus verified low-residency 1M/10M/20M high-load references, with both original chunk/thread configurations. Cache preparation, builds and correctness verification remain outside timed native calls.
- Instrumentation subtask adds scripts/benchmark_cold.py, focused tests and docs/COLD_INPUT_BENCHMARK.md only; no production or existing benchmark code changes. File-targeted read-only msync invalidation plus independent untouched mincore checks must find zero resident input pages in each fresh child. Physical-device cache remains unverified; timed source hashing can warm inputs before decoding. Failed cache gates cannot claim a completed cold-input measurement.
- Original 1M events-file feasibility probe: ordinary read gives 2070/2070 resident 16KiB pages; targeted synchronous invalidation gives 0/2070 in independent mappings over three cycles. F_NOCACHE reads retain cached pages and are not accepted as eviction evidence.
- Focused checks are required per small local commit; final full acceptance remains root-owned. Preserve evidence under ignored existing results/output locations, retain all repeats and compare exact decoded outputs. No push or history rewrite is authorized. Instrumentation validation and full baseline results are pending at this plan entry.

- Instrumentation checks passed: `.venv/bin/python -m pytest -q tests/benchmarks/test_cold_input.py` (8 passed in 1.59s), `.venv/bin/ruff check scripts/benchmark_cold.py tests/benchmarks/test_cold_input.py`, and `git diff --check`. The native wrapper integration performs two independently prepared fresh children with matching verified decoded outputs, then proves warm input refusal before any output or timed native call. Focused file invalidation checks preserve bytes and modification time over three cycles. Comparison guards reject altered helper/protocol/fixtures/decoded output and unverified release/source/binary/host evidence.
- Inspected the complete helper/test/documentation diff. The root granted the exclusive measurement slot after the regular five-case baseline completed. Freeze the helper at this local instrumentation commit before the full 24-call low-residency baseline; measured outcome will be recorded separately.


## Verified low-residency input baseline completed — 2026-10-14

- Frozen instrumentation commit `a910217`; no production code or existing benchmark source changed. Exclusive serial suite command: `.venv/bin/python -m scripts.benchmark_cold --root benchmarks/results/high-load/cold-input-baseline-20261014 --normal-reference benchmarks/results/high-load/baseline-20261014/summary.json`. Completed 24 calls (six excluded warmups, 18 measured repeats) in 669.3 seconds; full evidence remains ignored. Standard 1M/10M/20M, four partitions, five levels, known direction, 10s buckets, t1-c4096/t4-c65536, 0.5s RSS and exact original fixtures were preserved.
- All 72 child input-file observations and all 72 parent post-preparation observations show zero resident pages. Per-size event/trade/quality pages: 1M 2070/57/1227; 10M 20439/549/12003; 20M 40724/1091/23851. Untouched independent mappings verify targeted invalidation; physical-device cache remains unverified and source hashing can warm inputs during the timed public call.
- Wall medians t1/t4: 1M 2.677294/2.574657s; 10M 26.680096/25.990904s; 20M 52.696098/51.591414s. RSS medians t1/t4: 1M 133.219/234.828 MiB; 10M 113.188/251.594 MiB; 20M 109.797/249.938 MiB. Full ranges/MAD are recorded in docs/COLD_INPUT_BENCHMARK.md and raw evidence. Observed t4 RSS maxima 364.938 MiB at 10M and 336.250 MiB at 20M disclose substantial variability; no memory benefit claim.
- Every run passed unchanged high_load verification and matched normal-reference canonical decoded fingerprints; fixture/source/harness/native/helper hashes remained identical before/after. Independent post-suite audit checked status/counts, every zero-residency observation, identities, six aggregate fingerprints and real cold self-comparison guards. Final full per-row QC/manifest comparison remains supervising-root-owned. Regular five-case baseline completed and was independently verified before this exclusive suite; no concurrent builds/tests/profiles/benchmarks occurred.
- Helper SHA-256 `9bf1590d6c6839eae1248d6a4981d36a7c3de869480a165a74a15db458ae31ee`; native SHA-256 `6cf58dacbb60d5408e0d125321c973aa2cb298fc8b7a9fce7b2a0e52ddb63691`; baseline summary SHA-256 `597a04f7d7c69cf832a6a636a54ea3bd132be30ec964d84ded24b6ea187a8f55`. Future paired cold runs must keep the helper byte-identical. This evidence update is documentation-only; no extra native tests are needed beyond the eight passed focused checks and successful full suite. No push or history rewrite performed.

## Rust optimization P4 — canonical reader indices (2026-10-14, candidate)

- Current-task baseline production is `a662211`; subsequent `a910217` and
  `f9fa511` add the independent cold-input protocol/evidence only. Baselines
  remain retained: regular `optimization/highload-before-20261014`, full warm
  `high-load/baseline-20261014`, and full cold
  `high-load/cold-input-baseline-20261014` under ignored benchmark results.
- First hypothesis: replace per-cell input-name hashing with a private canonical
  39-slot index table resolved once after existing schema/header validation.
  Keep public `Row` variants/`has`, reader methods and all Arrow null/downcast,
  CSV conversion, required/optional schema, ordering and precision checks.
  Physical columns remain arbitrary; unrequested deeper columns stay ignored.
  No decoder batch, queue, worker or configured operational bound increases.
  Typed batch caching and string/book changes are deferred to separate evidence.
- Added authored Rust checks for reversed Parquet columns at all five depths,
  chunks 1/2/4/8 across multiple row groups, ignored deeper wrong-type columns,
  historical cross-kind calls, lazy optional types/null-before-type checks,
  consumed-row error context, earlier segment/trade validation, and optional
  sign validation at open for every input kind with sign short-circuiting.
- Focused checks passed: `cargo fmt --all`; `PYO3_PYTHON="$PWD/.venv/bin/python"
  cargo test -p ofi-core --test adapters --locked --offline` (6 passed);
  `cargo clippy -p ofi-core --all-targets --locked --offline -- -D warnings`;
  `cargo test -p ofi-core --locked --offline` (29 unit + 6 adapter + 2 pipeline
  passed; external sample remains explicitly ignored in this focused command).
  An initial test compile used an unavailable Parquet writer method; corrected
  to the pinned version's `set_max_row_group_row_count` before passing checks.
- Release rebuild passed with explicit `VIRTUAL_ENV="$PWD/.venv"` and
  `PYO3_PYTHON="$PWD/.venv/bin/python"` using
  `.venv/bin/maturin develop --release --locked --offline`.
  `.venv/bin/python -m pytest -q tests/integration/test_pipeline.py --basetemp
  outputs/features/indexed-adapter-checks`: 24 passed in 2.12s through the newly
  rebuilt extension. `git diff --check` passed. Loaded extension SHA-256:
  `6d9ce62675db8d8ebb8c834f563e5943fe31f82f010f7d7a7b7464fd71565ce6`.
- Performance retention is pending serialized regular and preliminary 1M warm/
  cold measurements. No performance claim or production commit yet.
- Serialized regular measurement completed with the unchanged harness via
  `.venv/bin/python /tmp/ofi_regular_stage.py indexed-highload-20261014
  highload-before-20261014`: one warmup + five measured fresh processes per
  case in rounds. All 30 complete outputs match the retained original baseline
  exactly (schemas, ordered values/floats/nulls, full quality, manifest and
  stable QC); current source/native identity guards, chunk/thread invariance
  and Quote Test conservation passed. Current-task baseline comparisons:

| Case | Median seconds before → indexed (MAD before → indexed) | Indexed min–max s | Peak MiB median before → indexed (indexed min–max) | Speedup |
| --- | --- | --- | --- | ---: |
| real-t1-c4096 | 2.377169 → 1.518004 (0.014816 → 0.014327) | 1.452028–1.532331 | 117.11 → 108.88 (104.05–112.23) | 1.566x |
| real-t2-c65536 | 2.327638 → 1.352256 (0.028670 → 0.018413) | 1.333843–1.475855 | 356.75 → 250.86 (238.36–404.38) | 1.721x |
| real-t4-c1 | 29.688308 → 28.917654 (0.264505 → 0.082363) | 28.835291–29.802041 | 57.33 → 49.50 (48.41–50.89) | 1.027x |
| quote-t2-c4096 | 3.056617 → 3.103519 (0.088745 → 0.032509) | 3.042897–3.469477 | 106.06 → 102.33 (98.73–104.69) | 0.985x |
| fixture-t2-c4096 | 0.072252 → 0.058762 (0.000980 → 0.001804) | 0.052883–0.070050 | 63.27 → 65.56 (63.67–67.42) | 1.230x |

- Incremental family-weighted geometric speedup: real-direction 1.404x,
  real Quote Test 0.985x, authored 1.230x; balanced 1.194x. Quote Test's median
  is 1.5% slower with overlapping ranges; all unfavorable results are retained.
- Preliminary 1M-only warm pilot:
  `.venv/bin/python -m benchmarks.high_load --root
  benchmarks/results/high-load/indexed-1m-20261014 --sizes 1000000
  --reuse-fixtures --offline --compare-to /tmp/ofi_warm_baseline_1m.json`.
  Eight calls verified; 3 measured repeats per case. t1/c4096 median 1.702222s
  (1.643256–1.988758; MAD 0.058966), RSS 120.78 MiB (109.14–126.34), 1.560x;
  t4/c65536 1.463256s (1.418391–1.482590; MAD 0.019335), RSS 248.17 MiB
  (234.61–295.97), 1.743x. Equal-case geometric speedup 1.649x.
- Preliminary 1M-only verified low-residency pilot:
  `.venv/bin/python -m scripts.benchmark_cold --root
  benchmarks/results/high-load/indexed-cold-1m-20261014 --normal-reference
  benchmarks/results/high-load/indexed-1m-20261014/summary.json --compare-to
  /tmp/ofi_cold_baseline_1m.json`. All eight parent/child zero-residency gates,
  unchanged helper/input/source/native identities and decoded output checks
  passed. t1/c4096 median 1.537537s (1.531785–1.626211; MAD 0.005752), RSS
  129.44 MiB (117.61–139.02), 1.741x; t4/c65536 1.435804s
  (1.419273–1.462420; MAD 0.016531), RSS 300.11 MiB (238.55–360.09), 1.793x.
  Equal-case geometric speedup 1.767x. The t4 RSS median increased 27.8% versus
  its cold baseline; no general memory reduction is claimed. Operational buffer
  and worker bounds are unchanged. RSS ranges remain broad; allocator/scheduling
  occupancy is a possible explanation, not a proven cause.
- Both /tmp pilot references are explicitly documented selections of the two
  original 1M cases from preserved full baselines, with original verification
  and comparison guards. Pilots do not replace required final 1M/10M/20M suites.
  Machine/cache limitations remain those of the established protocols: normal
  cache uncontrolled/warm leaning; verified pre-call input residency is separate
  from unverified device cache and hashing can warm decoding inside the call.
  Retention decision and commit await supervisor review of all measurements.
- Decision: retain the indexed-only hypothesis for the measured speed-priority
  benefit, preserving the small Quote Test regression and inconclusive RSS evidence.
  Typed batch caching remains unimplemented; the next candidate isolates private
  string/book copy reductions. No implementation commit is pushed.

## Rust optimization P5 — reuse validated key/book storage (2026-10-14, candidate)

- Independent candidate after retained `0516002`: compare borrowed partition
  names/dates before allocating a new partition tuple; reuse OrderGuard and OFI
  original-key String storage only after unchanged checks; private OFI predecessor
  retains only Book rather than an entire Event and embedded execution; explicitly
  reuse predecessor/boundary/left-book Vec storage via field-level `clone_from`.
  Public derives/types/signatures, checked arithmetic and failure sequencing remain
  unchanged. Rejected gaps still clear predecessor/boundary state. No reader/chunk,
  queue, worker, partition or output-buffer bound increases; retained vectors remain
  at requested depth, and a fixed number of key strings retain their maximum seen
  capacities rather than allocating a fresh copy on every row.
- Added three meaningful Rust regressions: changing key lengths across partitions
  and failed order checks preserve owned previous state; caller mutations cannot
  alter retained OFI books; standalone nonzero initial ID and segment-increment
  effects after failed initialization remain historical behavior; emitted bucket
  features and caller books remain independent across repeated boundary reuse.
- Passed `cargo fmt --all -- --check`, `git diff --check`,
  `PYO3_PYTHON="$PWD/.venv/bin/python" cargo test -p ofi-core --locked --offline`
  (32 unit + 6 adapter + 2 pipeline; external sample ignored in this focused run),
  `cargo clippy -p ofi-core --all-targets --locked --offline -- -D warnings`.
  Explicit-venv/PYO3 release rebuild using
  `.venv/bin/maturin develop --release --locked --offline` passed.
  Loaded extension SHA-256:
  `223ff29f11e5d15ef418afaef0052bb52e4332700da5e02431786f7d4fc27222`.
- Performance measurement and retention pending; raw readers remain unchanged.
- Newly compiled `.venv/bin/python -m pytest -q tests/integration/test_pipeline.py
  --basetemp outputs/features/copy-reuse-checks`: 24 passed in 2.03s.
- Serialized regular suite `copy-highload-20261014` via unchanged
  `/tmp/ofi_regular_stage.py` compared incrementally to `indexed-highload-20261014`:
  all 30 outputs exactly matched retained baseline (schemas/order/floats/nulls,
  full quality, manifest and stable QC), with source/native guards and chunk/thread
  invariance/Quote Test conservation passing. One warmup + five measured repeats.

| Case | Indexed → copy median s (copy min–max; MAD) | Indexed → copy peak MiB (copy min–max) | Incremental speedup |
| --- | --- | --- | ---: |
| real-t1-c4096 | 1.518004 → 1.245414 (1.180196–1.349194; 0.020449) | 108.88 → 111.33 (108.81–114.19) | 1.219x |
| real-t2-c65536 | 1.352256 → 1.118947 (1.094927–1.171692; 0.024020) | 250.86 → 265.27 (239.28–340.14) | 1.209x |
| real-t4-c1 | 28.917654 → 29.063102 (28.445883–29.282159; 0.093278) | 49.50 → 51.83 (49.83–52.27) | 0.995x |
| quote-t2-c4096 | 3.103519 → 2.805033 (2.729208–2.808900; 0.002536) | 102.33 → 110.59 (101.67–113.73) | 1.106x |
| fixture-t2-c4096 | 0.058762 → 0.051557 (0.045941–0.087200; 0.005617) | 65.56 → 64.73 (58.73–68.92) | 1.140x |

- Incremental family-weighted geometric speedup 1.127x (real-direction 1.136x,
  Quote Test 1.106x, authored 1.140x); versus current-task baseline 1.345x.
  Tiny chunks are 0.5% slower with overlapping ranges; normal/quote/c1 RSS medians
  rose versus indexed. All cases and adverse observations are retained.
- Preliminary 1M-only warm pilot `copy-1m-20261014`: eight verified calls,
  one warmup + three measured repeats per case; same derived baseline references
  and immutable harness/helper/identity/decoded guards as P4.
  t1/c4096: 1.459269s (1.407163–2.003271;
  MAD 0.052107), RSS 129.94 MiB (129.33–134.94),
  original-baseline speedup 1.820x, RSS ratio 1.0657.
  t4/c65536: 1.130638s (1.126948–1.237980;
  MAD 0.003690), RSS 302.94 MiB (250.30–307.64),
  original-baseline speedup 2.256x, RSS ratio 1.1236.
- Preliminary 1M-only verified low-residency pilot `copy-cold-1m-20261014`: eight verified calls,
  one warmup + three measured repeats per case; same derived baseline references
  and immutable harness/helper/identity/decoded guards as P4.
  t1/c4096: 1.327426s (1.256651–1.364448;
  MAD 0.037022), RSS 128.02 MiB (117.36–134.08),
  original-baseline speedup 2.017x, RSS ratio 0.9609.
  t4/c65536: 1.203487s (1.157903–1.205178;
  MAD 0.001691), RSS 266.84 MiB (243.44–285.91),
  original-baseline speedup 2.139x, RSS ratio 1.1363.
- Warm RSS increased versus indexed pilots (t1 +7.6%, t4 +22.1%); cold RSS
  decreased versus indexed (t1 1.1%, t4 11.1%) but cold t4 remains 13.6% above
  original baseline. No general memory reduction is claimed. Max-seen key String
  capacities are intentionally retained in a fixed number of prior keys; book
  storage remains at requested depth. Cache/machine and pilot limitations of P4
  apply. Full final high-load and acceptance work remain required.
- Decision: retain copy reductions for the independently measured incremental
  speed benefit and exact parity. Raw reader changes are deferred; no push.

## Rust optimization P6 — raw buffers and exhausted-reader lifetime (2026-10-14, candidate)

- Combined I/O candidate after `3810fad`: RawReader reuses its two private CSV
  StringRecords and reserves exactly the already validated 1..5 book depth,
  replacing repeated record allocation and vector growth. Existing public owned
  current/prior-book return values and the preexisting `previous.take()` remain
  unchanged; invalid books still become None. A separate coordinated pipeline
  change explicitly drops exhausted event/trade/quality readers after trailing-row
  and nonempty-current validation, before final chunk handoff/ordered assembly.
  The combined measurements attribute observed changes jointly to raw buffers and
  reader lifetime; neither contribution is claimed isolated.
- Operational decoder batches/chunks/queues/workers/partition/output limits and
  read/validation/error order remain unchanged. Two reusable record capacities
  retain their maximum seen row text, independent of row count; parsed books are
  still owned separately and hold at most five ranks. Raw files/ZIP spool and
  temporary-disk/hash/publication behavior are unchanged.
- Added two raw regressions spanning every depth: valid-invalid-valid books,
  variable field-text widths, independent returned/prior/caller books, alignment
  failure consumes row without publishing post-state, conversion failure consumes
  records without incrementing original ID, and CSV's fixed field-count errors
  preserve previous state. Focused `cargo test -p ofi-core raw::tests --locked
  --offline`: five passed. `cargo test -p ofi-core --locked --offline`: 34 units,
  six adapters and two pipeline tests passed (external sample ignored in this
  focused command). `cargo fmt --all -- --check` and `git diff --check` passed.
- Clippy initially flagged the existing modulo predicate when its local record
  became borrowed; equivalent `is_multiple_of(4)` resolves the warning, with
  final `cargo clippy -p ofi-core --all-targets --locked --offline -- -D warnings`
  and core tests passing. Final explicit-venv/PYO3 release rebuild via
  `.venv/bin/maturin develop --release --locked --offline` passed. Native SHA-256:
  `a4bbe9c69622920b9e6f589ea73ff66f0ac8f497cb5993f54789eeba15507d35`.
- Raw implementation and CHANGELOG belong to the raw subtask; the separately
  authored four-line pipeline reader-drop change is retained pending its own
  commit. Performance and final retention remain pending serial measurements.
- Compiled focused Quote Test/parallel/publication/error integrations:
  `.venv/bin/python -m pytest -q tests/integration/test_quote_test.py
  tests/integration/test_parallel.py tests/integration/test_pipeline.py --basetemp
  outputs/features/io-reuse-checks`: 36 passed in 2.71s through the final rebuilt
  extension, including the coordinated exhausted-reader drops.
- Serialized combined I/O regular suite `io-highload-20261014` via unchanged
  `/tmp/ofi_regular_stage.py` against `copy-highload-20261014`: one warmup + five
  measured repeats per case, all 30 outputs exactly equivalent to retained baseline
  (schemas/order/floats/nulls, full quality, manifest, stable QC). Source/native
  stability, chunk/thread invariance and Quote Test conservation passed.

| Case | Copy → I/O median s (I/O min–max; MAD) | Copy → I/O peak MiB (I/O min–max) | Incremental speedup |
| --- | --- | --- | ---: |
| real-t1-c4096 | 1.245414 → 1.227469 (1.210033–1.353651; 0.017436) | 111.33 → 114.73 (107.36–119.14) | 1.015x |
| real-t2-c65536 | 1.118947 → 1.143882 (1.094324–1.151189; 0.007308) | 265.27 → 245.88 (209.91–406.91) | 0.978x |
| real-t4-c1 | 29.063102 → 28.531394 (28.359381–28.926279; 0.172013) | 51.83 → 51.80 (48.47–53.80) | 1.019x |
| quote-t2-c4096 | 2.805033 → 1.689398 (1.594320–1.884494; 0.053021) | 110.59 → 113.91 (109.88–117.09) | 1.660x |
| fixture-t2-c4096 | 0.051557 → 0.049278 (0.048535–0.052941; 0.000390) | 64.73 → 58.66 (55.91–63.59) | 1.046x |

- Combined incremental family-weighted geometric speedup 1.204x (real-direction
  1.004x, Quote Test 1.660x, authored 1.046x); versus current-task baseline 1.619x.
  Large-chunk real median is 2.2% slower with overlapping ranges. Large RSS maximum
  rose to 406.91 MiB; Quote Test RSS median rose about 3.0%. All observations remain
  retained. Raw buffers and early reader drops were not measured in isolation.
- Preliminary 1M-only combined warm pilot `io-1m-20261014`: eight verified calls,
  one warmup + three measured repeats per case. Unchanged pilot-reference and
  source/native/input/harness/helper/decoded guards passed; every required parent
  and child zero-residency gate passed in the low-residency pilot.
  t1/c4096: 1.473943s (1.377436–1.654505;
  MAD 0.096508), RSS 129.72 MiB (125.33–135.92),
  original-baseline speedup 1.802x, RSS ratio 1.0639.
  t4/c65536: 1.141844s (1.129478–1.203063;
  MAD 0.012367), RSS 292.91 MiB (255.30–358.48),
  original-baseline speedup 2.234x, RSS ratio 1.0863.
- Preliminary 1M-only combined verified low-residency pilot `io-cold-1m-20261014`: eight verified calls,
  one warmup + three measured repeats per case. Unchanged pilot-reference and
  source/native/input/harness/helper/decoded guards passed; every required parent
  and child zero-residency gate passed in the low-residency pilot.
  t1/c4096: 1.309286s (1.278711–1.330652;
  MAD 0.021367), RSS 130.14 MiB (129.58–135.61),
  original-baseline speedup 2.045x, RSS ratio 0.9769.
  t4/c65536: 1.202397s (1.135537–1.209507;
  MAD 0.007110), RSS 258.41 MiB (240.19–320.80),
  original-baseline speedup 2.141x, RSS ratio 1.1004.
- Known-direction 1M warm medians are about 1% slower than copy pilots with
  overlapping ranges; cold t1 improves about 1.4%, cold t4 is approximately flat.
  RSS remains noisy and mixed; no general memory reduction is claimed. These
  known-direction pilots do not exercise raw CSV buffers. Final full-size suites
  and acceptance remain required. P4 cache/device-cache limitations apply.
- Decision: retain the combined I/O hypothesis for the Quote Test speed benefit
  and exact parity. This raw subtask commits only raw.rs and CHANGELOG; the
  separately authored pipeline reader drops remain pending their own commit
  with the same joint measurement attribution. Nothing is pushed.

## Rust optimization P6 — coordinated exhausted-reader release commit (2026-10-14)

- The separate memory investigator authored the four-line pipeline change:
  release event/trade/quality readers after trailing-row and nonempty-current
  validations, before final chunk handoff and ordered partition assembly. Error
  branches, public signatures, configuration, queues, manifest and publication
  remain unchanged. The implementation diff was independently reviewed.
- Supervising-root joint validation with the raw-buffer changes passed: 34 core
  units, six adapters, two pipeline tests and 36 compiled Quote Test/parallel/
  pipeline integrations. All 30 regular outputs and eight calls in each 1M warm
  and verified low-residency pilot passed the unchanged exact parity and stability
  guards recorded above.
- Joint incremental Quote Test speedup was 1.660x; current-task family-weighted
  speedup was 1.619x. Reader release was not measured separately; no isolated
  speed or RSS benefit is claimed. This local commit includes only pipeline.rs
  and this coordinated evidence entry. No push or history rewrite was performed.

## Rust optimization P7 — compact private worker payload (2026-10-14, candidate)

- Replace the private worker row's separate event/trade slots with an inline
  payload: an owned event plus stored execution-agreement flag, or an independent
  eventless trade. The producer compares complete Option<Trade> values only after
  the existing event/trade lookahead advances. Independent table parsing, order
  checks and validation remain intact. Eventless trades, including rejected-quote
  executions, remain owned and reach all existing signing/bucket checks.
- Disagreement still raises the same error at the same worker point after raw
  observation and before event timestamp accounting or clean/raw book checks.
  Downstream borrowing of the event's execution starts after agreement is checked.
  Public domain types/signatures, configuration/defaults, chunk capacities, bounded
  queues/workers, manifest, state/error/publication semantics and benchmark/helper
  sources are unchanged. No lazy chunk reservation is included.
- Actual arm64 inline size, measured by the focused private regression, is 312
  bytes versus the prior 408 bytes: 96 bytes less per reserved row slot (23.53%).
  At capacity 65536 this is 19.5 MiB of slot storage versus 25.5 MiB, excluding
  row-owned strings/books and allocator overhead. This is a layout observation,
  not measured process RSS or execution improvement. Equality and duplicate-trade
  destruction move to the producer, so scheduling/time effects require measurement.
- Added six private regressions: all event/execution/trade Option combinations,
  every equality field, smaller inline layout, eventless rejected type-4/type-5
  signing conservation, unchanged disagreement errors before quality/event defects,
  and raw alignment/parse errors before disagreement while disagreement still
  precedes invalid clean/raw book validation. Authored synthetic rows only.
- `cargo test -p ofi-core worker::tests --locked --offline -- --nocapture`: seven
  passed, including the preexisting dependency panic/join test. Final
  `cargo test -p ofi-core --locked --offline`: 40 units, six adapters and two
  pipeline tests passed; the external-sample test remains explicitly ignored in
  this focused command. Initial Clippy failures were test-only type-complexity and
  err/expect style; a local alias and expect_err resolved them. Final
  `cargo clippy -p ofi-core --all-targets --locked --offline -- -D warnings` passed.
  `rustfmt --edition 2024 --check` on the two owned Rust files and
  `git diff --check` passed.
- Explicit repository-venv VIRTUAL_ENV/PYO3_PYTHON release rebuild via
  `.venv/bin/maturin develop --release --locked --offline` passed. Installed native
  SHA-256: `f054f44ec4b9e7630e970ea42eadb9b6b8bd6a7094406542eeb52c59756334f2`.
  `.venv/bin/python -m pytest -q tests/integration/test_quote_test.py
  tests/integration/test_parallel.py tests/integration/test_pipeline.py --basetemp
  outputs/features/payload-checks`: 36 passed in 2.34s through that extension.
- Root-owned independent review and guarded serial measurements are pending;
  no benchmark, performance-retention decision or implementation commit is claimed.

## Rust optimization P7 — compact payload rejected after measurement (2026-10-14)

- Root and independent review cleared the candidate's validation/error ordering.
  Unchanged regular helper command compared payload-highload-20261014 against
  io-highload-20261014: one warmup plus five measured repeats per case. All 30
  complete outputs passed exact table/schema/order/float/null, full QC/manifest,
  chunk/thread invariance and Quote Test conservation checks. Current-task
  comparisons below use highload-before-20261014, not the helper's older P0 base.

| Regular case | Payload median s (min–max; MAD) | Peak MiB median (min–max) | Incremental / current-task speedup |
| --- | --- | --- | ---: |
| real-t1-c4096 | 1.213284 (1.124710–1.366689; 0.059560) | 103.83 (98.88–110.47) | 1.011692x / 1.959285x |
| real-t2-c65536 | 1.133985 (1.096385–1.299669; 0.037599) | 266.31 (203.91–279.78) | 1.008728x / 2.052619x |
| real-t4-c1 | 30.521220 (29.555661–33.017941; 0.965559) | 51.14 (48.11–52.16) | 0.934805x / 0.972710x |
| quote-t2-c4096 | 1.962442 (1.623797–2.540954; 0.299680) | 103.80 (92.61–108.22) | 0.860865x / 1.557558x |
| fixture-t2-c4096 | 0.046690 (0.044163–0.074979; 0.002527) | 63.56 (56.95–66.08) | 1.055432x / 1.547478x |

- Family-balanced incremental speedup was 0.963494x; current-task balanced
  speedup was 1.560189x versus retained I/O's 1.619x. Every tiny-chunk measured
  result was slower than I/O's 28.359381–28.926279s range. Quote Test's median
  increased about 16.2% from 1.689398s, with broader variability. Unfavorable
  results were preserved rather than dismissed as host noise.
- Unchanged 1M warm and verified low-residency pilots each completed eight
  verified calls. Derived references explicitly select the original baselines'
  two 1M cases with parent SHA provenance. Source/native/helper guards remained
  unchanged, and all 24 parent plus 24 child cold input observations had zero
  resident pages. These pilots do not replace required final full-size suites.

| 1M pilot | Payload median s (min–max; MAD) | Peak MiB median (min–max) | Incremental / current-task speedup |
| --- | --- | --- | ---: |
| warm t1/c4096 | 1.391063 (1.257309–1.480458; 0.089395) | 123.22 (122.92–127.28) | 1.059580x / 1.909510x |
| warm t4/c65536 | 1.111411 (1.108790–1.139261; 0.002621) | 272.97 (225.08–332.03) | 1.027383x / 2.295214x |
| cold t1/c4096 | 1.356273 (1.319605–1.360244; 0.003971) | 132.31 (131.69–139.41) | 0.965356x / 1.974008x |
| cold t4/c65536 | 1.107718 (1.067563–1.109881; 0.002162) | 273.69 (255.89–303.61) | 1.085472x / 2.324288x |

- RSS remained mixed: regular t2/authored medians rose about 8.3%/8.4%; warm
  t1/t4 fell about 5.0%/6.8%; cold t1/t4 rose about 1.7%/5.9% versus I/O.
  The 312-byte candidate layout was confirmed but not retained. No process RSS
  improvement is claimed. Root rejected the candidate under execution-time-first
  priority because the regular regressions outweighed the current evidence.
- Preserved the exact two-Rust-file diff, including private regressions, under
  ignored outputs/features/performance-experiments/compact-payload.patch (13544
  bytes); reverse-apply verification passed before restoring only worker.rs and
  pipeline.rs to verified HEAD 2b53b01, and forward-apply verification passed
  afterward. Full evidence remains under optimization/payload-highload-20261014
  and high-load/payload-1m-20261014 plus payload-cold-1m-20261014 in ignored
  benchmarks/results. No rejected implementation commit was created; no lazy
  reservation, benchmark/helper change, push or history rewrite was performed.
- Restoration checks: explicit repository-venv VIRTUAL_ENV/PYO3_PYTHON release
  rebuild passed; retained native SHA-256 again matches
  `a4bbe9c69622920b9e6f589ea73ff66f0ac8f497cb5993f54789eeba15507d35`.
  `cargo test -p ofi-core --locked --offline`: 34 units, six adapters and two
  pipeline tests passed (external sample explicitly ignored in this focused run).
  Compiled Quote Test/parallel/pipeline command above with --basetemp
  outputs/features/payload-restored-checks: 36 passed in 2.70s. This administrative
  commit includes only CHANGELOG; the retained production source is unchanged.

## Rust optimization P8 — release consumed Arrow batches before replacement (2026-10-14, candidate)

- Minimal lifecycle hypothesis after b8ff8f6: clear the private consumed
  RecordBatch inside the existing exhausted/missing-batch loop before invoking
  the next Parquet decode. Offset resets only after successful replacement,
  exactly as before. Public reader methods return owned rows; private IndexedRow
  references never escape. Parse errors consume the same row and update the same
  counters; decoder failures/EOF and retries invoke the same reader path. All
  null/type/value/order/error checks remain in their existing order. No public
  API, configuration, row/queue/worker bound, Python, helper or harness changes.
- Source inspection of pinned Parquet 60.0.0 establishes that next_inner reads
  records before consuming the new batch. Primitive consume_batch moves decoded
  record data into Arrow buffers; consume_record_data takes its stored values,
  leaving None so the next read lazily allocates a buffer. Holding an exhausted
  batch through that allocation extends the old returned buffers' lifetime.
- For the unchanged high-load c65536 schema, estimated logical decoded payloads
  are about 15.71 MiB/events, 2.57 MiB/quality and 6.20 MiB/full trade batch,
  before capacity rounding, validity, metadata or allocator overhead. The producer
  decodes serially, so the direct overlap change removes one consumed batch at
  a time. Extra input columns/strings and allocator behavior prevent a universal
  RSS bound. This does not attribute the preceding 609.48 MiB warm observation
  to batch overlap and does not claim an RSS or execution improvement.
- Added one authored ownership/error regression at chunk sizes 1/2/3: a null
  rejection reason consumes its source row without advancing ordering state;
  retry across batch rollover preserves row numbering and subsequent contiguous
  order; repeated EOF stays empty; returned quality keys/reasons survive reader
  drop. Existing adapters cover every depth, reordered columns and row groups.
  Initial test compile missed a test-only Arc import; corrected before checks.
- `cargo test -p ofi-core adapter::tests --locked --offline`: one passed.
  `cargo test -p ofi-core --test adapters --locked --offline`: six passed.
  `cargo test -p ofi-core --locked --offline`: 35 units, six adapters and two
  pipeline tests passed; external sample explicitly ignored in this focused run.
  `cargo clippy -p ofi-core --all-targets --locked --offline -- -D warnings`,
  owned-file `rustfmt --edition 2024 --check` and `git diff --check` passed.
- Explicit repository-venv VIRTUAL_ENV/PYO3_PYTHON release rebuild via
  `.venv/bin/maturin develop --release --locked --offline` passed. Native SHA-256:
  `6bbf6b875c1055498fea113d987f881bbc23531ef315fabc18e5147d64290d7c`.
  `.venv/bin/python -m pytest -q tests/integration/test_quote_test.py
  tests/integration/test_parallel.py tests/integration/test_pipeline.py --basetemp
  outputs/features/batch-release-checks`: 36 passed through the rebuilt extension.
- Source/native now ready for root's independent review and guarded measurements;
  no benchmark, retention decision or implementation commit has been performed.

## Rust optimization P8 — early batch release rejected after measurement (2026-10-14)

- Root and independent compatibility review cleared the minimal lifecycle change.
  Frozen regular suite batch-highload-20261014 compared against io-highload-20261014
  through the unchanged helper: one warmup plus five measured calls per case.
  All 30 complete outputs passed exact tables/schema/order/float/null, full QC/
  manifest, chunk/thread invariance and Quote Test conservation. Current-task
  ratios use highload-before-20261014 rather than the helper's older P0 base.

| Regular case | Candidate median s (min–max; MAD) | Peak MiB median (min–max) | Incremental / current-task speedup |
| --- | --- | --- | ---: |
| real-t1-c4096 | 1.152658 (1.132478–1.233397; 0.017468) | 108.33 (105.17–112.17) | 1.064903x / 2.062338x |
| real-t2-c65536 | 1.099141 (1.081517–1.116978; 0.009411) | 256.62 (221.58–375.45) | 1.040705x / 2.117689x |
| real-t4-c1 | 29.261111 (28.795016–29.505021; 0.067922) | 53.75 (51.23–56.25) | 0.975062x / 1.014599x |
| quote-t2-c4096 | 1.630584 (1.533558–1.718185; 0.065774) | 103.56 (99.12–112.94) | 1.036069x / 1.874554x |
| fixture-t2-c4096 | 0.051760 (0.045128–0.053387; 0.001627) | 60.72 (56.98–61.84) | 0.952041x / 1.395886x |

- Regular family-balanced incremental speedup was only 1.004051x; current-task
  speedup was 1.625865x versus retained I/O's 1.619x. Tiny-chunk and authored
  medians regressed. Regular t2/tiny/authored RSS medians rose about 4.4%/3.8%/3.5%.
- Frozen 1M warm batch-1m-20261014 and verified low-residency
  batch-cold-1m-20261014 pilots each completed eight verified calls using the
  same original derived references with parent SHA provenance. Source/native/
  helper guards remained unchanged, and all 24 parent plus 24 child cold input
  observations had zero resident pages. No candidate full-size suite was run.

| 1M pilot | Candidate median s (min–max; MAD) | Peak MiB median (min–max) | Incremental / current-task speedup |
| --- | --- | --- | ---: |
| warm t1/c4096 | 1.460986 (1.320809–1.500898; 0.039912) | 123.20 (111.50–131.89) | 1.008869x / 1.818121x |
| warm t4/c65536 | 1.185183 (1.129985–1.335091; 0.055198) | 284.58 (235.86–359.55) | 0.963433x / 2.152348x |
| cold t1/c4096 | 1.256936 (1.229422–1.272975; 0.016040) | 131.83 (129.41–135.53) | 1.041649x / 2.130016x |
| cold t4/c65536 | 1.279644 (1.271008–1.411310; 0.008636) | 233.84 (216.41–280.45) | 0.939634x / 2.012010x |

- Against recent retained full warm optimized-20261014 1M aggregates, candidate
  speedups were 0.992918x/0.931957x, equal-case geometric 0.961955x; RSS ratios
  were 0.936016/0.929851 with overlapping ranges. Against preceding I/O pilots,
  warm RSS medians fell about 5.0%/2.8%; cold t1 rose 1.3% and cold t4 fell 9.5%.
  Cold t4 time rose about 6.4%, and every candidate repeat was slower than the
  retained I/O pilot's 1.135537–1.209507s range. RSS remained mixed. No explanation
  of the preceding 609.48 MiB peak, isolated allocator cause or process-memory
  improvement is claimed. Root rejected P8 under execution-time-first priority.
- Saved the exact adapter.rs diff plus authored regression under ignored
  outputs/features/performance-experiments/early-batch-release.patch (3882 bytes).
  Reverse-apply check passed before restoring only adapter.rs to verified retained
  HEAD b8ff8f6; forward-apply check passed afterward. All measured evidence remains
  ignored beneath benchmarks/results/optimization/batch-highload-20261014 and
  high-load/batch-1m-20261014 plus batch-cold-1m-20261014. No rejected implementation
  commit, further speculative candidate, reservation/payload change, helper edit,
  push or history rewrite was performed.
- Restoration release rebuild with explicit repository-venv VIRTUAL_ENV and
  PYO3_PYTHON passed; native SHA-256 returned to
  `a4bbe9c69622920b9e6f589ea73ff66f0ac8f497cb5993f54789eeba15507d35`.
  Independent snapshot comparison confirms all 39 source-file hashes and native
  identity match completed full warm optimized-20261014. Restored
  `cargo test -p ofi-core --locked --offline`: 34 units, six adapters and two
  pipeline tests passed (external sample explicitly ignored in this focused run).
  The compiled Quote Test/parallel/pipeline command above with --basetemp
  outputs/features/batch-restored-checks passed 36 tests in 2.44s. This local
  administrative commit includes only CHANGELOG; retained production is unchanged.

## Supervised Rust optimization — final acceptance and report (2026-10-14)

- Retained production is `2b53b01` (canonical column indices, owned key/book reuse,
  raw CSV record reuse, validated-depth reserve, borrowed partition comparison,
  and exhausted-reader release). Public signatures, configuration/defaults,
  schemas/units/nulls/order/errors, Python/PyO3/research layers, operational bounds,
  dependencies, lockfile, build profiles and existing benchmark sources remain
  unchanged. Both rejected candidates were restored and preserved only as ignored
  patches, with evidence in `b8ff8f6` and `8e2b70b`.
- Root supervised zero-context optimization, measurement and independent-review
  agents. Serial exclusive heavy slots prevented task-owned measurements from
  overlapping with builds/tests/profiles or large-data inspection. Host activity
  remains uncontrolled. Independent fresh-context final read-only review of
  `a662211..8e2b70b` found no actionable compatibility issues; review did not claim
  unexecuted tests.
- Final retained regular series: one warmup plus five measured fresh children per
  case, 30 outputs verified. Compare current-task baseline measurements at
  `a662211`, not the older P0 fields embedded in historical summaries. Direction
  family 1.601x, real Quote Test 1.809x, authored family 1.466x; equal-family
  geometric speedup **1.619304397x** (38.2% less time under that weighting).
- Root ran the complete unchanged warm suite, 24 verified calls/18 measured, at
  `benchmarks/results/high-load/optimized-20261014`. Equal-case geometric speedup
  **2.128977695x** versus the preserved full baseline. Warm t4-c65536 medians:
  10M 25.988424s -> 10.995942s (2.363x), 20M 51.378437s -> 22.864259s (2.247x).
- The fresh cold measurement agent ran the complete frozen wrapper with the
  completed warm reference and original cold baseline, 24 verified calls/18
  measured, at `benchmarks/results/high-load/optimized-cold-20261014`. Every one
  of 72 child and 72 parent post-preparation file observations was nonresident;
  all comparison/source/native/helper/input/output guards passed. Equal-case
  geometric speedup **2.179318991x**. Cold t4-c65536 medians: 10M 25.990904s ->
  11.195504s (2.322x), 20M 51.591414s -> 23.822834s (2.166x). Cold summary SHA-256
  `2988d33650ed29e14afccb5aa1660f9538b25a208dc8fe53a791950de39a0bf3`.
- Time-first retention has a material memory tradeoff: all six warm RSS medians
  increased, and five of six cold medians increased. Largest measured warm peak
  292.86 -> 609.48 MiB; cold 364.94 -> 615.14 MiB. Memory reduction was not achieved
  overall. All ranges/outliers are retained; no causal explanation or memory-bound
  guarantee is asserted. Cold means independently verified zero input-page
  residency before worker setup, not physical-device cold cache; timed source
  hashing can warm decoding. t1/t4 change both chunk size and thread cap.
- Final serial acceptance passed: fmt, Clippy with warnings denied, 42 workspace
  Rust tests, one separately enabled real-sample test, the same 42 workspace
  tests on Rust 1.90.0, **114 Python/API/native/research/real/benchmark tests with
  no skips**, Ruff, strict mypy (seven files), diff checks, locked offline release
  wheel, and unchanged isolated wheel smoke outside the checkout. The first
  isolated-wheel attempt failed at sandbox DNS dependency fetch; an authorized
  network retry passed. No helper or dependency policy was weakened.
- Real acceptance verified all 24 delivery hashes/raw ZIP identities and paired
  CSV counts; delivered clean events/trades/quality counts 887810/68404/897387.
  Widths 1/5/10/30/60s produced 45966/8985/4390/1382/650 accepted features; keys,
  integer columns, average depth and quality flags match exactly. Maximum price
  errors 2.182785e-13 USD and 2.182787e-11 ticks are below existing tolerances.
- Root independently audited all **48 full final warm/cold calls, 96 Parquet
  tables**, exact ordered values/dtypes/schema metadata, manifests and stable
  full QC. Only output paths, time and observed peak workers are excluded from
  QC equality. All 39 source hashes and native identity match the retained
  regular/full warm/full cold measurements after acceptance. Native SHA-256
  `a4bbe9c69622920b9e6f589ea73ff66f0ac8f497cb5993f54789eeba15507d35`.
- Added the English `docs/high_load/optimization-20261014.md` report and explicit
  compact `optimization-results-20261014.json` evidence; linked from the main
  README and baseline index. Source/result provenance, all cases/ranges/MAD/RSS,
  rejected candidates, exact commands, checks and limitations are recorded.
  Full measurement logs, RSS traces, final-acceptance/equivalence JSON, generated
  native outputs, static comparison PNG/SVG and rejected patches remain ignored
  under existing result/output directories. Root inspected the exported plot.
- This final evidence commit changes documentation only; measured production,
  installed binary, fixtures and harness stay unchanged. No push, PR, package
  upload, remote change, deployment or history rewrite. Owner reviews/pushes.
- A separate zero-context read-only report audit recomputed all three aggregates,
  checked every table/range/MAD/RSS against artifacts, verified cache observations,
  acceptance counts/log hashes and the 39-source/native closure, and found no
  actionable inaccuracies. Root rechecked reference-summary/helper hashes and
  diff whitespace before the explicit-path documentation commit.
