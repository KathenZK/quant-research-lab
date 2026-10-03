#!/usr/bin/env python3
"""Read-only independent raw-to-canonical verification; no builder imports."""
import argparse
import csv
import hashlib
import io
import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("snapshot")
    p.add_argument("receipt")
    a = p.parse_args()
    root, out = Path(a.snapshot), Path(a.receipt)
    assert not out.exists()
    manifest_bytes = (root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    assert manifest["timeframe"] == "4h"
    assert not manifest["trusted"]
    native = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trade_count", "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"]
    added = ["ts", "exchange", "market_type", "timeframe", "symbol", "native_symbol", "source", "bar_close_ts", "source_archive"]
    all_native = []
    for entry in manifest["archives"]:
        zbytes = (root / entry["zip"]["path"]).read_bytes()
        cbytes = (root / entry["checksum"]["path"]).read_bytes()
        rbytes = (root / entry["csv"]["path"]).read_bytes()
        for data, kind in ((zbytes, "zip"), (cbytes, "checksum"), (rbytes, "csv")):
            assert sha(data) == entry[kind]["sha256"]
            assert len(data) == entry[kind]["bytes"]
        checksum, filename = cbytes.decode().strip().split()
        assert checksum == sha(zbytes)
        assert filename == Path(entry["zip"]["path"]).name
        with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
            assert z.testzip() is None
            assert z.namelist() == [filename[:-4] + ".csv"]
            assert z.read(z.namelist()[0]) == rbytes
        all_native.extend((row, filename) for row in csv.reader(io.StringIO(rbytes.decode())))
    body = (root / manifest["canonical_csv"]["path"]).read_bytes()
    assert sha(body) == manifest["canonical_csv"]["sha256"]
    assert len(body) == manifest["canonical_csv"]["bytes"]
    canonical = list(csv.reader(io.StringIO(body.decode())))
    assert canonical[0] == native + added
    assert len(canonical) - 1 == len(all_native) == 4572
    start = int(datetime(2022, 12, 1, tzinfo=timezone.utc).timestamp()) * 1000
    def iso(t):
        return datetime.fromtimestamp(t / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    for i, ((row, filename), canon) in enumerate(zip(all_native, canonical[1:])):
        assert len(row) == 12 and canon[:12] == row
        opened, closed, trades = int(row[0]), int(row[6]), int(row[8])
        assert opened == start + i * 14400000 and closed == opened + 14400000 - 1
        op, hi, lo, cl, volume = map(float, row[1:6])
        quote, tb, tq = float(row[7]), float(row[9]), float(row[10])
        assert all(math.isfinite(x) for x in (op, hi, lo, cl, volume, quote, tb, tq))
        assert 0 < lo <= op <= hi and lo <= cl <= hi
        assert volume > 0 and trades > 0 and quote >= 0 and 0 <= tb <= volume and 0 <= tq <= quote
        assert canon[12:] == [iso(opened), "binance", "spot", "4h", "BTC/USDT", "BTCUSDT", "binance_vision", iso(closed), filename]
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(canonical)
    assert buffer.getvalue().encode() == body
    result = {"status": "PASS_RAW_TO_CANONICAL_INDEPENDENT_AUDIT", "snapshot": str(root), "checked_rows": 4572,
              "checked_archive_triplets": len(manifest["archives"]), "native_fields_lossless": True,
              "builder_module_imported": False, "canonical_csv_sha256": sha(body), "manifest_sha256": sha(manifest_bytes),
              "auditor_sha256": sha(Path(__file__).read_bytes()), "at_utc": datetime.now(timezone.utc).isoformat(),
              "trusted": False, "finality_or_tradability_approval": False}
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
