# Verified Lev adapter map

Inspected 2026-10-14 at the owner-provided `order_book_sample/` path with
PyArrow 18.1.0. All 24 entries of `SHA256SUMS.txt` matched SHA-256 computed
from actual files. Each delivered Parquet has one row group; batches must still
be bounded independently of row-group size.

| Input | Verified rows | Required physical columns / types |
| --- | ---: | --- |
| `data/events_clean.parquet` | 887,810 | `symbol`, `date`: string; `event_id`, `time_ns`, `event_type`, `event_size`, `direction`, `segment_id`: int64; `timestamp`: timestamp[ns, UTC]; `bid_price_N`, `ask_price_N`: float64 USD; sizes: int64 shares; `prev_state_available`, `is_quote_update`, `timestamp_subnanosecond_rounded`: bool |
| `data/trades_clean.parquet` | 68,404 | symbol/date strings; event_id/time_ns/type/size/direction/aggressor_side/signed_volume int64; timestamp[ns, UTC]; event_price float64 USD; quote_accepted bool |
| `reports/event_quality.parquet` | 897,387 | symbol string; event_id/time_ns int64; timestamp[ns, UTC]; quote_accepted bool; reject_reason string; **no date, book, or L1-update marker** |
| `reports/bucket_quality_10s.parquet` | 4,680 | symbol/date; timestamp and bucket_start [ns, UTC]; valid_for_regression bool; rejected_events/event_count int64; reference features |
| `data/features_10s.parquet` | 4,390 | identical columns to reference quality table, accepted rows only |

Quality dates must be derived from UTC timestamp in America/New_York. Validate
`time_ns` against local midnight plus delivered integer nanoseconds; do not parse
CSV timestamps as floating seconds. Explicit alias mappings will be part of a
versioned adapter, not inferred from values.

Read `src/prepare_sample.py` completely. Raw archive message/orderbook rows are
paired by index. Nanoseconds are decimal half-up (the tenth digit >= 5 increments
the first nine). First raw row is marked as an L1 update; retain delivered markers
for sample parity, while treating segment starts as unknown OFI transitions.
`aggregate_reference` works on original rows, including rejected quotes, with
right-closed integer arithmetic and last-original-state boundaries. Reference
OFI values inside excluded buckets are not meaningful accepted features.

The full quality table supplies timing/completeness for every original event.
Accepted books alone suffice for accepted-bucket boundary/OFI/depth computation
when merged with that table. Quote Test needs original pre-execution quotes,
including rejected states, and therefore the paired raw archive adapter.

No production reader may read the reference features table or the reference
10-second quality mask. Other widths must derive their own decisions.

Observed sample: AAPL's first accepted event ID is 14, after rejected original
rows. The quality table starts at ID 0. This proves why accepted-only shifting
or boundary searches would be unsafe. These observations verify schemas and
integrity; they do not yet prove independently computed feature parity.
