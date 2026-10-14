"""Generate an explicitly authored two-symbol performance fixture, never market data."""

import argparse
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
parser.add_argument("--rows-per-symbol", type=int, default=10000)
args = parser.parse_args()
root = args.directory
(root / "data").mkdir(parents=True)
(root / "reports").mkdir()
all_events, all_trades, all_quality = [], [], []
for symbol in ["FIXTURE_A", "FIXTURE_B"]:
    for i in range(args.rows_per_symbol):
        offset = 1 + i * 100_000_000
        base = {
            "symbol": symbol,
            "event_id": i,
            "timestamp": 1_340_285_400_000_000_000 + offset,
            "time_ns": 34_200_000_000_000 + offset,
        }
        execution = i % 100 == 99
        event = {
            **base,
            "date": "2012-06-21",
            "segment_id": 1,
            "prev_state_available": i > 0,
            "is_quote_update": True,
            "timestamp_subnanosecond_rounded": False,
            "event_type": 4 if execution else 1,
            "event_size": 7 if execution else 1,
            "direction": -1 if execution else 1,
            "event_price": 1.01 if execution else 1.0,
        }
        for level in range(1, 6):
            event.update(
                {
                    f"bid_price_{level}": round(1 - (level - 1) * 0.01, 4),
                    f"ask_price_{level}": round(1.01 + (level - 1) * 0.01, 4),
                    f"bid_size_{level}": 100 + i % 2 if level == 1 else 100,
                    f"ask_size_{level}": 120,
                }
            )
        all_events.append(event)
        all_quality.append({**base, "quote_accepted": True, "reject_reason": ""})
        if execution:
            all_trades.append(
                {
                    **base,
                    "date": "2012-06-21",
                    "event_type": 4,
                    "event_size": 7,
                    "event_price": 1.01,
                    "direction": -1,
                    "quote_accepted": True,
                    "aggressor_side": 1,
                    "signed_volume": 7,
                }
            )
for directory, name, rows in [
    ("data", "events_clean", all_events),
    ("data", "trades_clean", all_trades),
    ("reports", "event_quality", all_quality),
]:
    table = pa.Table.from_pylist(rows)
    table = table.set_column(
        table.schema.get_field_index("timestamp"),
        "timestamp",
        pa.array([r["timestamp"] for r in rows], pa.timestamp("ns", "UTC")),
    )
    pq.write_table(table, root / directory / f"{name}.parquet", compression="zstd")
print(f"Authored synthetic fixture: {len(all_events)} events; {len(all_trades)} executions")
