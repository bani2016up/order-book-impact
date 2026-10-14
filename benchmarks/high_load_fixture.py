"""Bounded deterministic synthetic Lev-v1 load fixtures, never market data."""

import argparse
from contextlib import ExitStack
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import tempfile
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

VERSION = 1
OPEN_NS = 1_340_285_400_000_000_000
LOCAL_OPEN_NS = 34_200_000_000_000
NS = 1_000_000_000
DATE = "2012-06-21"


@dataclass(frozen=True)
class FixtureSpec:
    total_rows: int
    partitions: int = 4
    batch_rows: int = 65536
    seed: int = 20261014
    trade_every: int = 25
    reject_every: int = 100003
    session_seconds: int = 23400
    with_raw: bool = False

    def validate(self):
        for name in ("total_rows", "partitions", "batch_rows", "seed", "trade_every",
                     "reject_every", "session_seconds"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")
        if not 1 <= self.partitions <= 1024 or not 2 * self.partitions <= self.total_rows <= 10**9:
            raise ValueError("Need 1..1024 partitions and 2*partitions..1B original rows")
        if not 1 <= self.batch_rows <= 1048576 or not 0 <= self.seed < 2**32:
            raise ValueError("Invalid generation batch size or seed")
        if self.trade_every < 2 or self.reject_every not in (0,) and self.reject_every < 2:
            raise ValueError("trade_every must be >=2; reject_every must be 0 or >=2")
        if not 60 <= self.session_seconds <= 23400 or self.session_seconds % 60:
            raise ValueError("Session seconds must be a multiple of 60 within 60..23400")
        if type(self.with_raw) is not bool:
            raise ValueError("with_raw must be boolean")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def noise(ids, seed, salt):
    """Stateless row-indexed values: decoded data does not depend on batch size."""
    with np.errstate(over="ignore"):
        value = ids.astype(np.uint64) + np.uint64(seed) + np.uint64(salt * 1000003)
        value = (value ^ (value >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        value = (value ^ (value >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return value ^ (value >> np.uint64(31))


def book(ids, partition, seed):
    bid = 1_000_000 + partition * 10000 + ((ids // 32) % 101 - 50) * 100
    ask = bid + (1 + (ids // 7) % 4) * 100
    levels = []
    for level in range(5):
        bs = (noise(ids, seed, 2 * level + 1) % 901).astype(np.int64) + 100
        az = (noise(ids, seed, 2 * level + 2) % 901).astype(np.int64) + 100
        levels.append((bid - level * 100, ask + level * 100, bs, az))
    return levels


def table(columns, mask=None):
    result = {}
    for name, values in columns.items():
        if mask is not None:
            values = values[mask]
        if name == "timestamp":
            dtype = pa.timestamp("ns", tz="UTC")
        elif values.dtype.kind in "iu":
            dtype = pa.int64()
        elif values.dtype.kind == "b":
            dtype = pa.bool_()
        elif values.dtype.kind == "f":
            dtype = pa.float64()
        else:
            dtype = pa.string()
        result[name] = pa.array(values, type=dtype)
    return pa.table(result)


def batch(spec, partition, count, first, stop):
    ids = np.arange(first, stop, dtype=np.int64)
    seed = spec.seed + partition * 10003
    current = book(ids, partition, seed)
    prior = book(np.maximum(ids - 1, 0), partition, seed)
    stride, remainder = divmod(spec.session_seconds * NS - 2, count - 1)
    offset = 1 + ids * stride + (ids * remainder) // (count - 1)
    accepted = np.ones(len(ids), dtype=bool)
    previous = ids > 0
    segment = np.ones(len(ids), dtype=np.int64)
    if spec.reject_every:
        accepted &= (ids == 0) | (ids % spec.reject_every != 0)
        previous &= (ids <= 1) | ((ids - 1) % spec.reject_every != 0)
        segment += ids // spec.reject_every
    l1_update = ~previous
    for now, before in zip(current[0], prior[0]):
        l1_update |= now != before
    execution = ids % spec.trade_every == spec.trade_every - 1
    ordinal = ids // spec.trade_every
    hidden = execution & (ordinal % 4 == 3)
    direction = np.where(ordinal % 2 == 0, -1, 1).astype(np.int64)
    size = np.where(execution, 7 + noise(ids, seed, 20) % 50, 1).astype(np.int64)
    kind = np.where(hidden, 5, np.where(execution, 4, 1)).astype(np.int64)
    price = np.where(
        execution,
        np.where(hidden, (prior[0][0] + prior[0][1]) // 2,
                 np.where(direction == -1, prior[0][1], prior[0][0])),
        current[0][0],
    )
    symbol = f"LOAD_{partition:04d}"
    base = {
        "symbol": np.full(len(ids), symbol),
        "event_id": ids,
        "timestamp": OPEN_NS + offset,
        "time_ns": LOCAL_OPEN_NS + offset,
    }
    events = {
        **base, "date": np.full(len(ids), DATE),
        "segment_id": segment, "prev_state_available": previous,
        "is_quote_update": l1_update,
        "timestamp_subnanosecond_rounded": np.zeros(len(ids), dtype=bool),
        "event_type": kind, "event_size": size,
        "event_price": price.astype(np.float64) / 10000, "direction": direction,
    }
    for rank, (bid, ask, bs, az) in enumerate(current, 1):
        events.update({f"bid_price_{rank}": bid.astype(np.float64) / 10000,
                       f"ask_price_{rank}": ask.astype(np.float64) / 10000,
                       f"bid_size_{rank}": bs, f"ask_size_{rank}": az})
    quality = {**base, "quote_accepted": accepted,
               "reject_reason": np.where(accepted, "", "spread_above_p95")}
    trades = {
        **base, "date": np.full(len(ids), DATE), "event_type": kind,
        "event_size": size, "event_price": events["event_price"], "direction": direction,
        "quote_accepted": accepted, "aggressor_side": -direction,
        "signed_volume": -direction * size,
    }
    classified = execution & ~hidden
    expected = {
        "original_rows": len(ids), "clean_events": int(accepted.sum()),
        "rejected_events": int((~accepted).sum()), "trade_count": int(execution.sum()),
        "volume": int(size[execution].sum()),
        "known_trade_imbalance": int((-direction[execution] * size[execution]).sum()),
        "quote_classified_count": int(classified.sum()),
        "quote_classified_volume": int(size[classified].sum()),
        "quote_classified_imbalance": int((-direction[classified] * size[classified]).sum()),
    }
    return (table(events, accepted), table(trades, execution), table(quality),
            (base["time_ns"], kind, size, price, direction, current), expected)


def write_raw(messages, books, raw):
    times, kinds, sizes, prices, directions, levels = raw
    messages.writelines(
        f"{int(t)//NS}.{int(t)%NS:09d},{int(k)},0,{int(s)},{int(p)},{int(d)}\n"
        for t, k, s, p, d in zip(times, kinds, sizes, prices, directions)
    )
    values = np.column_stack([value for bid, ask, bs, az in levels
                              for value in (ask, az, bid, bs)])
    np.savetxt(books, values, fmt="%d", delimiter=",")


def generate(directory, spec):
    spec.validate()
    directory = Path(directory).absolute()
    if directory.exists():
        raise FileExistsError(f"Refusing to replace an existing fixture: {directory}")
    directory.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=".high-load-fixture-", dir=directory.parent) as temporary:
        stage = Path(temporary)
        (stage / "data").mkdir()
        (stage / "reports").mkdir()
        paths = {"events": "data/events_clean.parquet", "trades": "data/trades_clean.parquet",
                 "quality": "reports/event_quality.parquet"}
        reports, raw_inputs = [], []
        with ExitStack() as stack:
            writers = {}
            for partition in range(spec.partitions):
                count = spec.total_rows // spec.partitions + int(
                    partition < spec.total_rows % spec.partitions
                )
                counters = {}
                if spec.with_raw:
                    (stage / "raw").mkdir(exist_ok=True)
                    message = f"raw/LOAD_{partition:04d}_message.csv"
                    orderbook = f"raw/LOAD_{partition:04d}_orderbook.csv"
                    # Each pair closes at its partition boundary, not only at suite completion.
                    raw_inputs.append({"symbol": f"LOAD_{partition:04d}", "date": DATE,
                                       "message": message, "orderbook": orderbook})
                with ExitStack() as pair:
                    if spec.with_raw:
                        m = pair.enter_context((stage / message).open("w", newline=""))
                        b = pair.enter_context((stage / orderbook).open("w", newline=""))
                    for first in range(0, count, spec.batch_rows):
                        events, trades, quality, raw, expected = batch(
                            spec, partition, count, first, min(first + spec.batch_rows, count)
                        )
                        for kind, rows in zip(paths, (events, trades, quality)):
                            if kind not in writers:
                                writers[kind] = stack.enter_context(pq.ParquetWriter(
                                    stage / paths[kind], rows.schema, compression="zstd"
                                ))
                            if rows.num_rows:
                                writers[kind].write_table(rows, row_group_size=spec.batch_rows)
                        if spec.with_raw:
                            write_raw(m, b, raw)
                        for name, value in expected.items():
                            counters[name] = counters.get(name, 0) + value
                reports.append({"symbol": f"LOAD_{partition:04d}", "date": DATE, **counters})
        identities = {}
        for kind, relative in paths.items():
            path = stage / relative
            identities[kind] = {"path": relative, "size_bytes": path.stat().st_size,
                                "sha256": sha256(path),
                                "rows": pq.ParquetFile(path).metadata.num_rows}
        raw_sources = []
        for item in raw_inputs:
            for kind in ("message", "orderbook"):
                path = stage / item[kind]
                raw_sources.append({"path": item[kind], "size_bytes": path.stat().st_size,
                                    "sha256": sha256(path)})
        document = {
            "kind": "authored-synthetic-high-load-fixture", "generator_version": VERSION,
            "spec": asdict(spec), "inputs": identities, "raw_inputs": raw_inputs,
            "raw_sources": raw_sources, "expected_partitions": reports,
            "session_close": f"{(34200+spec.session_seconds)//3600:02d}:"
                             f"{((34200+spec.session_seconds)//60)%60:02d}:00",
            "generation_seconds": time.perf_counter() - started,
            "provenance": "Stateless authored book states, not real/repeated market data. "
                          "Quality rejections are deliberately supplied gaps, not an estimated p95.",
        }
        (stage / "fixture.json").write_text(json.dumps(document, indent=2) + "\n")
        if directory.exists():
            raise FileExistsError(directory)
        stage.rename(directory)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--total-rows", type=int, required=True)
    parser.add_argument("--partitions", type=int, default=4)
    parser.add_argument("--batch-rows", type=int, default=65536)
    parser.add_argument("--seed", type=int, default=20261014)
    parser.add_argument("--trade-every", type=int, default=25)
    parser.add_argument("--reject-every", type=int, default=100003)
    parser.add_argument("--session-seconds", type=int, default=23400)
    parser.add_argument("--with-raw", action="store_true")
    args = parser.parse_args()
    spec = FixtureSpec(**{k: v for k, v in vars(args).items() if k != "directory"})
    print(json.dumps(generate(args.directory, spec), indent=2))


if __name__ == "__main__":
    main()
