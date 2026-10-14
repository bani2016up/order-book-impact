# Output intervals, columns and units

Algorithm `0.1.0`, adapter `lev-v1`, output schema `ofi-v1`. Both Parquet files
use the same schema and ZSTD compression. Rows sort by symbol, New York session
date and UTC interval end. `features.parquet` contains accepted rows only;
`bucket_quality.parquet` contains the complete session grid, including exclusions.

| Columns | Physical type | Meaning |
| --- | --- | --- |
| `symbol`, `date` | UTF-8 | Symbol and local session date `YYYY-MM-DD`. |
| `interval_start`, `timestamp` | timestamp[ns, UTC] | Actual left and right boundaries; timestamp is the interval end. |
| `accepted` | bool | Quote/boundary completeness for the interval. All feature rows are true. |
| `rejection_reasons` | UTF-8 | Empty if accepted; sorted pipe-separated reason codes otherwise. |
| `event_count`, `rejected_events` | int64 | Original in-session events and rejected quote events. |
| `quote_update_count` | int64 | Accepted L1-update markers; the supplied marker is validated against original ordering/segment state. |
| `volume`, `classified_volume`, `unclassified_volume` | int64 | Total execution shares and classification split. |
| `trade_count`, `classified_count`, `unclassified_count` | int64 | Independent type-4/type-5 execution counts and classification split. |
| `trade_imbalance` | nullable int64 | Full signed execution shares; null if any trade is unclassified. |
| `classified_trade_imbalance` | int64 | Signed shares from classified trades only. |
| `trade_signing_complete` | bool | True when every interval execution has a sign, including empty trade intervals. |
| `mid_price_start`, `mid_price_end` | nullable float64 | Valid boundary midpoint in USD. Half ticks are preserved internally. |
| `mid_price_change` | nullable float64 | End minus start midpoint, USD. |
| `mid_price_change_ticks` | nullable float64 | USD change divided by configured tick size. |
| `avg_depth` | nullable float64 | Mean `(bid_size_1 + ask_size_1) / 2` in shares over L1 updates. |
| `ofi_l1` through requested `ofi_lN` | nullable int64 | Checked signed rank-based OFI shares, one column per requested level. |

All arithmetic accumulators use checked integer operations. Counts/sizes use
int64 storage with nonnegative validation, never truncated integer casts.
Excluded buckets have null midpoint/depth/OFI features; independent trade totals
remain observable even when quote quality failed. Quote acceptance and trade
classification are separate decisions: a valid Quote Test feature row may have
unknown full TI.

The grid is anchored at local session open and uses `(start, end]`: at the sample
open 13:30:00 UTC, a 13:30:10 event belongs to the interval ending 13:30:10,
whereas 13:30:10.000000001 belongs to the next interval. The first interval is
always excluded. Both boundary books must be the newest original state at or
before their boundary, preserving row/event order at ties. A newer rejected state
invalidates that boundary; an older accepted book cannot conceal it. A rejected
gap clears the OFI predecessor; initialization is unavailable rather than zero.

Rejection codes are `first_incomplete_bucket`, `rejected_event`,
`unknown_transition`, `invalid_or_missing_left_boundary` and
`invalid_or_missing_right_boundary`. These computed interval codes are distinct
from source-event quality reasons in the QC report. Multiple reasons may apply.

With no L1 updates in a valid interval, average depth falls back to the right
boundary depth. L2-L5-only changes contribute rank OFI without additional L1-depth
weight. Valid empty intervals can carry zero OFI/TI/volume and boundary-derived
depth; exclusions cannot be converted into these plausible zero observations.

For example, two accepted 10-second rows ending 13:30:20 and 13:30:40 are separated
by an excluded interval. A row shift is not a 10-second lag. Join on symbol/date
and check actual timestamp difference before deriving temporal lags. OFI and
price change refer to the same interval, with no forecasting interpretation.

`manifest.json` retains deterministic source paths/hashes, config, schema/units,
algorithm version and semantics. `Cargo.lock` pins dependency versions. `quality_report.json` adds per-session
input/output/rejection counts, signing coverage, precision evidence, peak workers,
warnings and elapsed time. Runtime timings are variable; decoded values and stable
semantic metadata, rather than compressed Parquet bytes, define reproducibility.
