"""Bounded official terminal-index evidence, never a synthetic confirmed settlement."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

import numpy as np
import pandas as pd

from audit_baseline_terminals_20260908 import text_nodes

FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/weekly-top10-20260924/terminal-evidence"
SPEC = FAMILY / "specs/binance-1d-mcsm-weekly-top10-20260924.md"
EVENTS = [
    {"symbol": "BZRXUSDT", "terminal": "2021-12-19T02:00Z", "article": "dff27dc6bcbb432c902bcbea5e24ddfa"},
    {"symbol": "KEEPUSDT", "terminal": "2022-02-15T02:00Z", "article": "96698a6a80f64cb1ae27f813032bfaa9"},
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        f.write("\n")


def fetch(name, url):
    path = OUT / name
    meta_path = path.with_name(path.name + ".meta.json")
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if sha(path) != meta["sha256"] or meta["url"] != url:
            raise ValueError("changed retained response")
    else:
        try:
            response = urlopen(Request(url, headers={"User-Agent": "QuantResearch/1.0"}), timeout=25)
        except HTTPError as exc:
            response = exc
        body = response.read()
        meta = {"url": url, "final_url": response.geturl(), "status": response.status,
                "fetched_utc": datetime.now(timezone.utc).isoformat(), "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest()}
        with path.open("xb") as f:
            f.write(body)
        save(meta_path, meta)
    if meta["status"] in (403, 451):
        raise PermissionError(f"access refused; no alternate route: {url}")
    return path, meta


def validate_minutes(rows, terminal):
    begin = terminal - pd.Timedelta(hours=1)
    start_ms, end_ms = int(begin.timestamp() * 1000), int(terminal.timestamp() * 1000)
    selected = [r for r in rows if str(r[0]).isdigit() and start_ms <= int(r[0]) < end_ms]
    if [int(r[0]) for r in selected] != list(range(start_ms, end_ms, 60000)):
        raise ValueError("terminal hour does not have exactly 60 ordered minute bars")
    values = np.asarray([[float(x) for x in r[1:5]] for r in selected])
    if (not np.isfinite(values).all() or not (values > 0).all()
            or not (values[:, 2] <= values.min(axis=1)).all()
            or not (values[:, 1] >= values.max(axis=1)).all()):
        raise ValueError("bad index OHLC")
    if not all(int(r[6]) == int(r[0]) + 59999 for r in selected):
        raise ValueError("unclosed or incorrect minute interval")
    return selected, {"center": float(values.mean()), "low": float(values[:, 2].mean()), "high": float(values[:, 1].mean())}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plan_path = OUT / "request-plan.json"
    if not plan_path.exists():
        save(plan_path, {"contract_sha256": sha(SPEC), "script_sha256": sha(Path(__file__)), "events": EVENTS,
                         "window_minutes": 60, "archive_404_fallback": "single public indexPriceKlines call",
                         "not_actual_settlement_receipts": True})
    plan = json.loads(plan_path.read_text())
    if sha(SPEC) != plan["contract_sha256"] or sha(Path(__file__)) != plan["script_sha256"]:
        raise ValueError("collection plan changed")
    results = []
    for event in EVENTS:
        symbol, terminal = event["symbol"], pd.Timestamp(event["terminal"])
        cms_url = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode=" + event["article"]
        cms_path, meta = fetch(symbol + "-announcement.json", cms_url)
        if meta["status"] != 200:
            raise ValueError("official announcement not available")
        payload = json.loads(cms_path.read_text())
        assert payload["code"] == "000000"
        body = payload["data"]["body"]
        try:
            tree = json.loads(body)
        except json.JSONDecodeError:
            tree = json.loads(body.replace('\\"', '"'))
        text = text_nodes(tree)
        assert terminal.strftime("%Y-%m-%d %H:%M") in text
        assert "automatic settlement" in text.lower()
        assert pd.Timestamp(payload["data"]["publishDate"], unit="ms", tz="UTC") < terminal
        day = terminal.strftime("%Y-%m-%d")
        filename = f"{symbol}-1m-{day}.zip"
        url = f"https://data.binance.vision/data/futures/um/daily/indexPriceKlines/{symbol}/1m/{filename}"
        archive, meta = fetch(filename, url)
        if meta["status"] == 200:
            checksum, check_meta = fetch(filename + ".CHECKSUM", url + ".CHECKSUM")
            assert check_meta["status"] == 200 and checksum.read_text().split()[0] == sha(archive)
            with zipfile.ZipFile(archive) as z:
                assert len(z.namelist()) == 1
                rows = list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
            source = archive
        elif meta["status"] == 404:
            url = "https://fapi.binance.com/fapi/v1/indexPriceKlines?" + urlencode({
                "pair": symbol, "interval": "1m", "startTime": int((terminal - pd.Timedelta(hours=1)).timestamp() * 1000),
                "endTime": int(terminal.timestamp() * 1000) - 1, "limit": 100})
            source, api_meta = fetch(symbol + "-index-1m.json", url)
            assert api_meta["status"] == 200
            rows = json.loads(source.read_text())
            assert isinstance(rows, list)
        else:
            raise ValueError(f"unexpected official archive response {meta['status']}")
        selected, prices = validate_minutes(rows, terminal)
        target = OUT / (symbol + "-terminal-minute-window.json")
        save(target, selected)
        result = {"symbol": symbol[:-4] + "/USDT:USDT", "ts": terminal, **prices,
                  "source_path": str(source.relative_to(FAMILY)), "source_sha256": sha(source),
                  "announcement_path": str(cms_path.relative_to(FAMILY)), "announcement_sha256": sha(cms_path),
                  "window_path": str(target.relative_to(FAMILY)), "window_sha256": sha(target),
                  "minute_count": len(selected), "source_quality": "CONDITIONAL_INDEX_MINUTE_PROXY_NOT_EXACT_SETTLEMENT"}
        results.append(result)
        print(json.dumps(result, default=str), flush=True)
    save(OUT / "summary.json", {"status": "TWO_OFFICIAL_INDEX_WINDOWS_AVAILABLE_NOT_EXACT_SETTLEMENT",
                               "events": results, "request_plan_sha256": sha(plan_path),
                               "files_sha256": {str(p.relative_to(OUT)): sha(p) for p in OUT.iterdir() if p.is_file()}})


if __name__ == "__main__":
    main()
