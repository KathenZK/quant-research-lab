"""Download a fixed small spot window through Binance's documented public archive."""

import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

import pandas as pd
from strategy_lab.data.quality import audit_ohlcv_frame

ROOT = Path(__file__).resolve().parents[4]
RAW = (
    ROOT
    / "data/raw/ohlcv/exchange=binance/market_type=spot/timeframe=1d/source=vision/date=2026-10-03/M0216"
)
OUT = Path(__file__).resolve().parents[1] / "artifacts/20261003-first-replay"
COLS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_base",
    "taker_quote",
    "ignore",
]


def fetch():
    RAW.mkdir(parents=True, exist_ok=False)
    OUT.mkdir(parents=True, exist_ok=False)
    records, sources = [], []
    months = ["2022-12"] + [f"{y}-{m:02d}" for y in [2023, 2024] for m in range(1, 13)]
    for month in months:
        name = f"BTCUSDT-1d-{month}.zip"
        url = f"https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/{name}"
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = response.read()
        with urllib.request.urlopen(url + ".CHECKSUM", timeout=30) as response:
            checksum = response.read()
        digest = hashlib.sha256(payload).hexdigest()
        assert checksum.decode().split()[0] == digest, "provider checksum mismatch"
        (RAW / name).write_bytes(payload)
        (RAW / (name + ".CHECKSUM")).write_bytes(checksum)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            assert archive.namelist() == [name[:-4] + ".csv"]
            rows = list(
                csv.reader(io.TextIOWrapper(archive.open(archive.namelist()[0])))
            )
        assert all(len(row) == 12 for row in rows)
        records.extend(rows)
        sources.append(
            dict(
                url=url,
                sha256=digest,
                rows=len(rows),
                bytes=len(payload),
                retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            )
        )
    with (OUT / "input.csv").open("x", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLS)
        writer.writerows(records)
    frame = pd.DataFrame(records, columns=COLS).apply(pd.to_numeric)
    expected = pd.date_range("2022-12-01", "2024-12-31", freq="D", tz="UTC")
    frame["ts"] = pd.to_datetime(frame.open_time, unit="ms", utc=True)
    assert list(frame.ts) == list(expected), (
        "missing, duplicate, unordered, or unexpected dates"
    )
    assert ((frame.close_time - frame.open_time) == 86_399_999).all()
    assert (frame.volume > 0).all() and (frame.quote_volume > 0).all()
    for key, value in dict(
        exchange="binance",
        symbol="BTC/USDT",
        market_type="spot",
        timeframe="1d",
        source="binance_vision_monthly",
    ).items():
        frame[key] = value
    # Official historical monthly archives contain completed bars; additionally
    # verify native close_time duration and the explicit closed cutoff above.
    frame["is_closed"] = True
    frame["vwap"] = frame.quote_volume / frame.volume
    qa = audit_ohlcv_frame(
        frame, expected_timeframe="1d", closure_as_of="2025-01-01T00:00:00Z"
    )
    assert qa.trusted, qa
    manifest = dict(
        dataset_id="binance.spot.BTCUSDT.1d.M0216.20261003",
        sources=sources,
        input_sha256=hashlib.sha256((OUT / "input.csv").read_bytes()).hexdigest(),
        qa=qa.to_dict(),
        rows=len(frame),
        warmup_rows=31,
        evaluation_rows=731,
        cutoff_exclusive="2025-01-01T00:00:00Z",
        license="CC BY-NC-SA 4.0",
        attribution="Binance Vision",
        pit_proven=False,
        tradability_proven=False,
    )
    (OUT / "input-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: manifest[k]
                for k in [
                    "dataset_id",
                    "rows",
                    "warmup_rows",
                    "evaluation_rows",
                    "input_sha256",
                    "qa",
                ]
            }
        )
    )


if __name__ == "__main__":
    fetch()
