# Dataset contract: Lev's five-level sample

## Evidence and authority

This document translates the dataset description supplied by the owner into an English implementation contract. The attachment was titled "Small dataset for the Price Impact of Order Book Events project" and was prepared on 2026-10-14. The actual sample bundle has not been inspected in this checkout. Therefore physical column names, Arrow dtypes, file hashes, and the counts below are expected inputs to verify, not observations already verified by this project.

On receipt, inspect Parquet schemas, `reports/sources.json`, `SHA256SUMS.txt`, quality reports, and `src/prepare_sample.py`. Record schema mappings and discrepancies. Never guess physical column names or modify calculations merely to force a count match.

## Sample scope

- Symbols: AAPL and MSFT.
- Trading date: 2012-06-21.
- Session: 09:30-16:00 America/New_York; this date uses daylight saving time.
- UTC session: 13:30-20:00 UTC.
- Depth: five occupied bid and ask price levels.
- Reported cleaned events: 887,810.
- Reported visible and hidden execution messages: 68,404.
- Reported valid 10-second feature rows across both symbols: 4,390.
- Full regular-session 10-second grid: 2,340 intervals per symbol, 4,680 total.
- Reported excluded intervals: 290 total, including each symbol's first interval.
- All observations in the real sample are reported to be real. Do not fabricate replacements.

This is NASDAQ single-venue LOBSTER data, not the paper's consolidated NBBO data for 50 stocks in April 2010. No NBBO reconstruction belongs in the sample adapter. TAQ quote modes, correction indicators, and condition flags are absent and must not be invented. Volume describes execution messages present in the NASDAQ sample, not market-wide volume. Prices are historical and are not adjusted for subsequent splits.

## Bundle layout

| Relative path | Role |
| --- | --- |
| `data/events_clean.parquet` | Cleaned messages with five-level post-event order-book states; primary input to the Rust engine. |
| `data/trades_clean.parquet` | Independently cleaned type-4/type-5 executions, aggressor side, and signed volume. |
| `data/features_10s.parquet` | Lev's reference feature table. Test oracle only; never a production input that replaces computation. |
| `data/*.csv.gz` | Equivalent tables with headers; Parquet is preferred for timestamp fidelity. |
| `reports/table1.csv`, `reports/table1.md` | Descriptive statistics, following the structure of the paper's Table 1. |
| `reports/quality_report.json` | Counts, spread thresholds, rejection reasons, and timestamp precision information. |
| `reports/event_quality.parquet` | Quality mask for every original row, keyed by `(symbol, event_id)`. |
| `reports/bucket_quality_10s.parquet` | All 4,680 intervals, including rejected ones, with quality status. |
| `reports/sources.json` | Original source URLs, sizes, and SHA-256 values. |
| `raw/*.zip` | Unchanged LOBSTER archives: paired message/orderbook files and vendor description. |
| `src/prepare_sample.py` | Reference cleaning, descriptive statistics, plots, and aggregation. Read and compare; do not invoke it as the production Rust engine. |
| `src/quickstart.py`, `src/verify_sample.py` | Dataset-provided examples and delivery checks. |
| `SHA256SUMS.txt` | Delivery integrity manifest. |

Real files stay outside Git. Resolve the bundle from an explicit path or `OFI_SAMPLE_DIR`. No automatic download or hidden network dependency is allowed in the production pipeline or default tests.

## Logical event fields

Map actual physical columns to these concepts, preserving additional provenance when useful:

- Symbol, trading date/session identifier, `event_id`, event type, event size, event price, and passive-side direction.
- UTC nanosecond timestamp and `time_ns`, an integer count of nanoseconds since **local** midnight.
- For each level 1 through 5: bid price/size and ask price/size.
- `segment_id` and `prev_state_available`.
- Where supplied: `time_seconds_text` and `timestamp_subnanosecond_rounded`.

`event_id` is the original row number/order key, not the exchange order ID. Message and orderbook files are paired by row number. Row n's book state is the state **after** event n. Do not join the paired raw files on timestamps.

Preserve order `(symbol, session, event_id)`. Multiple events can have identical timestamps and distinct event IDs. Do not deduplicate them. Timestamps must be nondecreasing within a symbol/session. A sort by timestamp alone is insufficient; never create a Cartesian join on tied timestamps.

## Numerical and time representation

Cleaned prices are USD; cleaned sizes are shares. Raw LOBSTER prices are integer USD times 10,000. Do not apply raw-price scaling a second time to cleaned USD values.

Use integer nanosecond time arithmetic, with explicit America/New_York conversion for sessions. Do not use Moscow session hours or the execution host's timezone. `time_ns` is not a Unix timestamp.

Three MSFT source timestamps reportedly contain twelve fractional decimal places. Lev rounded them to the nearest nanosecond, preserving original text and a flag; the stated absolute rounding error is below 0.5 ns. Do not reparse them through binary floating-point seconds or apply a second rounding step. For raw ingestion, use deterministic decimal-to-nanosecond conversion, document the rounding/tie rule, and compare it with the reference preparation code.

Prefer checked integer prices/volumes internally. Preserve half-tick mid-prices rather than truncating `(bid + ask) / 2`. All price conversions, signed accumulations, and interval arithmetic must detect overflow or invalid precision.

## Quote filtering and segments

Lev reports the following preprocessing:

1. Regular-session timestamps in `[09:30, 16:00]`.
2. Positive quote prices and sizes; strict `bid < ask`; valid five-level states; asks increasing and bids decreasing by rank.
3. Service events 6 and 7 are excluded; the delivered sample reportedly contains none.
4. An L1 update changes at least one of best bid price/size or best ask price/size. The first observation initializes the book. Events changing only deeper levels are retained but are not additional L1 updates for descriptive statistics or average L1 depth.
5. Spread p95 is calculated per symbol on base-valid L1 updates. Reject `spread > p95`; retain equality. Reported thresholds: AAPL USD 0.30, MSFT USD 0.02.
6. Reported rejected event rows: AAPL 9,250, MSFT 327. Reported rejected fractions of L1 updates: 4.259% and 0.0527%, respectively. Discrete spreads make these fractions different from exactly 5%.
7. `segment_id` and `prev_state_available` identify discontinuities after filtering. Never compute OFI with a naive shift across a rejected section. The first observation of a segment initializes state; a transition without a valid predecessor is unknown, not an observed zero imbalance.

The primary clean-input mode honors these precomputed decisions and does not silently refilter or recompute p95. Validate and record them. Correct classification for all bucket widths requires original quality timing and boundary-state information; inspect whether the quality masks contain it, otherwise read the paired raw files. If inputs cannot prove completeness, fail with an actionable error rather than claiming a valid bucket.

## Trades and signs

- Valid trades are type-4 visible and type-5 hidden executions with positive price/size, regular-session time, and direction in `{-1, +1}`.
- These trades are cleaned separately from quotes. A valid trade survives even if its corresponding post-execution quote is rejected by the spread filter.
- LOBSTER `direction` describes the passive limit order: +1 means a bid/buy limit order, -1 means an ask/sell limit order.
- Therefore `aggressor_side = -direction` and `signed_volume = aggressor_side * event_size`.
- `quote_accepted` means the post-execution state passed quote-quality checks. It is **not** a Quote Test match or trade sign.
- An execution message is not necessarily one entire market order. Do not interpret counts as counts of originating market orders.

The default signing mode is known LOBSTER direction. Validate supplied aggressor/sign columns against the formula when both are available. Prevent duplicated trades when events and the separate trades table overlap.

An explicitly separate Quote Test mode uses the state **before** each execution, reconstructed from original row order. It must retain sequencing at tied timestamps. Hidden executions may be inside the spread and remain unclassified. Record classified/unclassified counts and volume; do not turn unclassified trades into sells or claim they have a known Quote Test sign. The reference TI uses known direction, so Quote Test output is not expected to equal it.

## OFI definition

For each rank j, using current post-event state n and the valid preceding state:

```text
e_n(j) = I[bid_price_n(j) >= bid_price_prev(j)] * bid_size_n(j)
       - I[bid_price_n(j) <= bid_price_prev(j)] * bid_size_prev(j)
       - I[ask_price_n(j) <= ask_price_prev(j)] * ask_size_n(j)
       + I[ask_price_n(j) >= ask_price_prev(j)] * ask_size_prev(j)

OFI_k(j) = sum of valid e_n(j) within interval k
```

Equality activates both appropriate terms, producing the size difference. Keep all events for deep-level OFI, including repeated L1 states; these contribute zero to L1 when the L1 state is unchanged.

L2-L5 use **rank-based** application of this formula. A rank can refer to a different price after the book moves. This is an explicitly labeled research extension, not OFI at a fixed price and not a claim that the original paper evaluated these five levels.

## Buckets, boundaries, and features

- Supported widths: 1, 5, 10, 30, and 60 seconds; default 10.
- Grid origin: the local regular-session open, converted to UTC.
- Membership: **(start, end]**; an event exactly on a right boundary belongs to that interval, not the next one.
- Output `timestamp` is the right boundary in UTC nanoseconds.
- Boundary states are the last **original** book states with time <= boundary; at tied times take the last event in original order. Looking up only accepted rows can silently select an older state and is not sufficient when quality information says a newer original state was rejected.
- The first bucket is excluded because the archive lacks the opening predecessor state required at the left boundary.
- Exclude a bucket containing a filtered/invalid event or an invalid/missing state at either boundary. Treat segment initialization and unknown transitions consistently with the reference masks and preparation code.
- Do not fill excluded buckets with zero OFI. Emit their quality record separately.
- Sparse accepted rows are not necessarily adjacent intervals. Lag construction must compare the actual interval grid and session, not shift the accepted table blindly.

Features:

| Field | Definition |
| --- | --- |
| `mid_price_change` | Right-boundary mid minus left-boundary mid, in USD. |
| `mid_price_change_ticks` | The same change divided by USD 0.01 for this sample. |
| `ofi_l1` through `ofi_l5` | Sum of rank-specific event contributions in the interval. |
| `avg_depth` | Mean `(bid_size_1 + ask_size_1) / 2` over L1 updates inside the interval; if none occur and boundaries are valid, use the right-boundary depth. No time weighting. |
| `volume` | Sum of valid type-4/type-5 execution sizes, independently of quote acceptance. |
| `trade_imbalance` | Sum of `aggressor_side * event_size` in known-direction mode. |

Use original L1-update markers if provided. Otherwise reproduce their definition from the full original order and inspect the reference code; do not count a segment-start state as a genuine size/price change across a missing predecessor merely because it is the first accepted row.

## Reference reconciliation

Join computed and reference features on `(symbol, session, timestamp)`, inspecting the reference's date/session representation. Require identical accepted key sets and quality classifications at 10 seconds. Compare OFI, signed volume, volume, counts, signs, and IDs exactly. Compare USD/tick changes and depth with declared tight absolute/relative tolerances that accommodate equivalent floating-point conversion without hiding semantic differences.

Expected counts apply only to the exact delivered bundle and matching configuration. Produce a reconciliation report with per-column max error, missing/extra keys, per-symbol counts, and the first mismatching keys. Never consume `features_10s.parquet` to create production outputs; it is an independent validation input only.

## Research interpretation

OFI and price change belong to the same interval. This is contemporaneous price-impact explanation, not next-interval prediction. The p95 thresholds in the descriptive sample use the whole day; they are not train-only calibrated preprocessing. For a future forecasting/OOS workflow, fit thresholds on training data and apply them unchanged to test data.

Two stocks over one day support debugging and preliminary regressions, not month-scale robustness, reliable seasonality, confirmation of lambda near one, or proven OOS improvement from L2-L5. Do not duplicate the day to create an artificial larger research sample.

## Sources

- User-supplied dataset description, prepared by Lev on 2026-10-14.
- [LOBSTER data structure](https://php.lobsterdata.com/info/DataStructure.php): row correspondence, raw scaling, event types, and passive-side direction.
- [LOBSTER sample files](https://php.lobsterdata.com/info/DataSamples.php).
- [Paper, March 2011 version](https://arxiv.org/pdf/1011.6402v3).
