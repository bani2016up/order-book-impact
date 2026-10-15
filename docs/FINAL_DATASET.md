# Final NASDAQ BX dataset — 2026-10-15

The [dataset release](https://github.com/bani2016up/order-book-impact/releases/tag/dataset-2026-10-15)
contains real public NASDAQ BX ITCH 5.0 data for AAPL, ADBE, AMD, AMZN, CSCO,
GOOG, INTC, MSFT, NVDA and QCOM. It covers 100 stock/date sessions across ten
nonconsecutive dates. It is a separate venue/sample from the original small
dataset and from the paper's consolidated NBBO sample.

## Download

| Release asset | Contents | Approximate size |
| --- | --- | --- |
| [order_book_final_models.zip](https://github.com/bani2016up/order-book-impact/releases/download/dataset-2026-10-15/order_book_final_models.zip) | Ready 10-second features, chronological model splits, reports, figures and documentation | 19 MB |
| [order_book_final_full.zip](https://github.com/bani2016up/order-book-impact/releases/download/dataset-2026-10-15/order_book_final_full.zip) | Everything above plus cleaned events/trades, reconstructed paired raw files, quality/provenance rows, preparation scripts and 1/5/10/30/60-second features | 791 MB |
| [SHA256SUMS-release.txt](https://github.com/bani2016up/order-book-impact/releases/download/dataset-2026-10-15/SHA256SUMS-release.txt) | SHA-256 of both archives | <1 KB |

Both ZIPs unpack into `order_book_final/`. Choose one archive; the full archive
already includes the model files. Original complete-day gzip feeds (8.3 GB)
are not bundled. Their exact URLs, sizes and hashes are in `reports/sources.json`.

For example, from the repository root with GitHub CLI installed:

```sh
gh release download dataset-2026-10-15 --repo bani2016up/order-book-impact \
  --pattern order_book_final_models.zip --pattern SHA256SUMS-release.txt --dir data
cd data
shasum -a 256 order_book_final_models.zip
# Compare with the corresponding line in SHA256SUMS-release.txt.
unzip -n order_book_final_models.zip
cd ..
```

Alternatively, use the download links above and unpack into `data/` manually.
Generated data remains ignored by Git. Within the extracted directory, verify
all model files with `shasum -a 256 -c SHA256SUMS_models.txt`; use `SHA256SUMS.txt`
for the full archive.

## Use the ready features

Reading Parquet directly needs pandas and pyarrow. Recomputing Rust features
is unnecessary for model development.

```python
import pandas as pd

features = pd.read_parquet("data/order_book_final/data/features_10s.parquet")
train = features.loc[features["split"] == "train"].copy()
validation = features.loc[features["split"] == "validation"].copy()
test = features.loc[features["split"] == "test"].copy()
predictors = ["ofi_l1", "ofi_l2", "ofi_l3", "ofi_l4", "ofi_l5"]
target = "mid_price_change_ticks"
```

The target is the price change in the **same interval** as OFI: a contemporary
impact regression, not a future-price forecast. Fit scaling, PCA, regularization
and other learned transformations on train only. Use validation for selection
and test for final evaluation.

| Split | Trading dates | Accepted 10-second rows |
| --- | --- | ---: |
| Train | 2018-12-28, 2019-01-30, 2019-03-27, 2019-05-30, 2019-07-30, 2019-08-30, 2019-10-30 | 82,964 |
| Validation | 2019-12-30 | 11,425 |
| Test | 2020-01-30, 2020-03-02 | 17,067 |
| Total | 10 separate dates | 111,456 |

These splits also exist as individual Parquet files in `model_data/`.
The repository's shared loader accepts the annotated file or the native
`features/10s/` output. Use its gap-safe lag helper instead of shifting across
missing intervals or trading days:

```python
from ofi_pipeline.research import lag_feature, load_features

features = load_features("data/order_book_final/data/features_10s.parquet")
features = lag_feature(features, "ofi_l1", bucket_seconds=10, periods=1)
```

Fedya's existing baseline entry point can consume the saved features:

```sh
uv run --no-sync python -m research.baseline.run \
  --features data/order_book_final/features/10s \
  --config configs/baseline.json --output-dir outputs/baseline/bx-final
```

That entry point runs the configured descriptive baseline. For held-out model
evaluation, explicitly use the supplied train/validation/test splits.

## Preparation and limits

- 8,368,923 source events for the selected stocks became 7,297,682 cleaned
  events and 363,815 valid executions. Full day streams were replayed from
  premarket to reconstruct orders, then restricted to 09:30–16:00 New York time.
- Quotes require five real occupied levels, positive values, ordered levels and
  best bid below best ask. Missing depth is never fabricated. Per-stock spread
  thresholds are the 95th percentiles calibrated on the seven training dates
  only and held fixed for validation/test.
- Rust computes all five feature widths. The 10-second grid has 234,000 rows
  before quality rejection; 111,456 are accepted and 101,354 of those have events.
  Do not fill rejected intervals with zero. Inspect `bucket_quality.parquet`
  and `reports/bucket_coverage.csv` for missing intervals.
- NASDAQ BX hidden execution messages do not reveal their passive side. Their
  input direction remains unknown (`0`); all execution signs use the immediate
  pre-event Quote Test. Total `trade_imbalance` is nullable when any execution
  sign is unknown: 91,958 accepted 10-second rows have complete TI, and 19,498
  do not. Volume still includes all valid executions. For OFI/TI comparisons,
  use the same rows selected by `trade_signing_complete` for all compared models.
- ADBE, GOOG and QCOM have sparse five-level BX coverage; some GOOG/QCOM test
  sessions have no accepted rows. Begin with AAPL, AMD or INTC if needed, and
  report observation counts per stock/session. Prices are historical and
  unadjusted for later splits. This single-venue dataset is not NBBO.

The full bundle includes Russian `README.md`, `DATA_DICTIONARY.md` and
`REPRODUCE.md`, source scripts, licenses, exact physical schemas and provenance
reports. Recompute using engine commit
`88cf38454d71d657d101b89920557a1cb5d0be23` or a descendant. Its hidden-side
support is already included; do not apply the archived compatibility patch
again on current `main`.

## Verification

Archive packaging checks every member's SHA-256 and ZIP CRC. Dataset validation
checks all 234,000 10-second acceptance masks and 564 scalar feature/volume/sign
calculations. A separate full-day ITCH replay checked 5,091 sampled five-level
states across ten stocks without invoking the primary decoder. Details are in
`reports/verification.json`, `reports/independent_reconstruction.json` and
`reports/model_loader_smoke.json`. The shared research loader and gap-safe lags
were exercised on all 111,456 delivered feature rows.

Sources: [official NASDAQ BX archive](https://emi.nasdaq.com/ITCH/Nasdaq%20BX%20ITCH/),
[ITCH 5.0 specification](https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/NQTVITCHspecification.pdf),
and the MIT-licensed [itch-book decoder](https://github.com/groovg/itch-book)
version 0.2.1. Source limitations and the difference from the paper's TAQ/NBBO
protocol remain explicit in the delivered documentation.
