"""Hand-authored fixtures. This file performs no production computation."""

import csv
import gzip
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

OPEN = 1_340_285_400_000_000_000
LOCAL_OPEN = 34_200_000_000_000


def make_bundle(root: Path, format: str = "parquet") -> Path:
    (root / "data").mkdir(parents=True)
    (root / "reports").mkdir()
    events, quality, trades = [], [], []
    # (ID, seconds, bid size, ask size, accepted, segment, prev, update, ask base)
    history = [
        (0, 1, 100, 120, True, 1, False, True, 1.01),
        (1, 10, 100, 120, True, 1, True, False, 1.01),
        (2, 11, 130, 120, True, 1, True, True, 1.01),
        (3, 11, 130, 100, True, 1, True, True, 1.01),
        (4, 20, 130, 100, True, 1, True, False, 1.01),
        (5, 21, 130, 100, False, 1, False, False, 1.20),
        (6, 31, 130, 100, True, 2, False, True, 1.01),
        (7, 40, 130, 100, True, 2, True, True, 1.02),
        (8, 41, 110, 100, True, 2, True, True, 1.02),
        (9, 60, 110, 100, True, 2, True, False, 1.02),
    ]
    for i, seconds, bs, az, accepted, segment, prev, update, ask in history:
        base = {
            "symbol": "TEST",
            "event_id": i,
            "timestamp": OPEN + seconds * 10**9,
            "time_ns": LOCAL_OPEN + seconds * 10**9,
        }
        quality.append(
            {
                **base,
                "quote_accepted": accepted,
                "reject_reason": "" if accepted else "spread_above_p95",
            }
        )
        if accepted:
            event = {
                **base,
                "date": "2012-06-21",
                "segment_id": segment,
                "prev_state_available": prev,
                "is_quote_update": update,
                "time_seconds_text": f"{34200 + seconds}.000000000",
                "timestamp_subnanosecond_rounded": False,
            }
            size, direction = {4: (7, -1), 9: (3, 1)}.get(i, (1, 1))
            event.update(
                {
                    "event_type": 4 if i in (4, 9) else 1,
                    "event_size": size,
                    "event_price": 1.01 if i in (4, 9) else 1.0,
                    "direction": direction,
                }
            )
            for level in range(1, 6):
                event.update(
                    {
                        f"bid_price_{level}": round(1 - (level - 1) * 0.01, 4),
                        f"ask_price_{level}": round(ask + (level - 1) * 0.01, 4),
                        f"bid_size_{level}": bs if level == 1 else 100 + (10 if i else 0),
                        f"ask_size_{level}": az if level == 1 else 120,
                    }
                )
            events.append(event)
        if i in (4, 5, 9):
            size, direction = {4: (7, -1), 5: (9, 1), 9: (3, 1)}[i]
            trades.append(
                {
                    **base,
                    "date": "2012-06-21",
                    "event_type": 5 if i == 5 else 4,
                    "event_size": size,
                    "event_price": 1.01,
                    "direction": direction,
                    "quote_accepted": accepted,
                    "aggressor_side": -direction,
                    "signed_volume": -direction * size,
                }
            )
    for folder, stem, rows in [
        ("data", "events_clean", events),
        ("data", "trades_clean", trades),
        ("reports", "event_quality", quality),
    ]:
        table = pa.Table.from_pylist(rows)
        table = table.set_column(
            table.schema.get_field_index("timestamp"),
            "timestamp",
            pa.array([r["timestamp"] for r in rows], pa.timestamp("ns", "UTC")),
        )
        pq.write_table(table, root / folder / f"{stem}.parquet", row_group_size=3)
        if format == "csv.gz":
            # Exact integer nanoseconds also remain in time_ns; strings never use float seconds.
            import datetime

            with gzip.open(root / folder / f"{stem}.csv.gz", "wt", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                for row in rows:
                    seconds, ns = divmod(row["timestamp"], 10**9)
                    stamp = datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc)
                    writer.writerow(
                        {**row, "timestamp": stamp.strftime("%Y-%m-%dT%H:%M:%S") + f".{ns:09d}Z"}
                    )
    return root


@pytest.fixture
def bundle(tmp_path):
    return make_bundle(tmp_path / "sample")
