"""有界、只读核查官方终止公告和公开价格接口，不计算策略净值或修改数据湖。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/baseline-verification-20260908/terminal-evidence"
PROJECTION = FAMILY / "artifacts/lifecycle-inputs-20260908/daily-returned-frames.parquet"
PROJECTION_SHA = "3565255edeafcdc5dd3083191b820d2302f993e4ac89679bd812e43601e7049a"
EVENTS = [
    {"symbol": "BNXUSDT", "terminal_utc": "2025-03-17T09:00:00Z", "published_utc": "2025-02-26", "url": "https://www.binance.com/en/support/announcement/detail/2f963977c7274e0583f16f2e26987b61", "new_orders_stop_utc": "2025-03-17T08:30:00Z", "role": "held_terminal_March_2025_and_ineligible_entry_April"},
    {"symbol": "VIDTUSDT", "terminal_utc": "2025-04-14T09:00:00Z", "published_utc": "2025-04-08T06:00:00Z", "url": "https://www.binance.com/en/support/announcement/detail/fac9c3e401da4cc8b604566fd261d70c", "new_orders_stop_utc": "2025-04-14T08:30:00Z", "role": "held_terminal_April_2025"},
    {"symbol": "ALPACAUSDT", "terminal_utc": "2025-04-30T09:00:00Z", "published_utc": "2025-04-24T04:00:00Z", "url": "https://www.binance.com/en/support/announcement/detail/0274f9d47da1437990bc13eb17b0ec99", "new_orders_stop_utc": "2025-04-30T08:30:00Z", "role": "ineligible_entry_May_2025_not_a_June_exit"},
    {"symbol": "FRONTUSDT", "terminal_utc": "2024-08-23T09:00:00Z", "published_utc": "2024-08-19", "url": "https://www.binance.com/en/support/announcement/detail/3ab5488a00e04d4fb338c77ea28326a8", "new_orders_stop_utc": "2024-08-23T08:30:00Z", "role": "ineligible_entry_September_2024"},
    {"symbol": "LOKAUSDT", "terminal_utc": "2025-07-21T09:00:00Z", "published_utc": "2025-07-10T09:00:00Z", "url": "https://www.binance.com/en/support/announcement/detail/551eeaf9861c47b8ad3482f45abf3f38", "new_orders_stop_utc": "2025-07-21T08:30:00Z", "role": "ineligible_entry_August_2025"},
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_json(path: Path, data: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, default=str)
        handle.write("\n")


def text_nodes(node: object) -> str:
    if isinstance(node, dict):
        if node.get("node") == "text":
            return str(node.get("text", ""))
        return "".join(text_nodes(child) for child in node.get("child", [])) + ("\n" if node.get("tag") in {"p", "h2", "h3", "li"} else "")
    if isinstance(node, list):
        return "".join(text_nodes(child) for child in node)
    return ""


def fetch(item: tuple[str, str]) -> dict:
    name, url = item
    dest = OUT / name
    if dest.exists():
        return json.loads((OUT / (name + ".meta.json")).read_text())
    started = datetime.now(timezone.utc).isoformat()
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"})
        try:
            response = urlopen(request, timeout=25)
        except HTTPError as exc:
            response = exc
        body = response.read()
        meta = {"requested_url": url, "final_url": response.geturl(),
                "fetched_at_utc": started, "http_status": response.status,
                "content_type": response.headers.get("content-type"),
                "bytes": len(body), "sha256": sha(body), "path": str(dest.relative_to(FAMILY))}
        with dest.open("xb") as handle:
            handle.write(body)
    except Exception as exc:
        meta = {"requested_url": url, "fetched_at_utc": started, "error": repr(exc)}
    save_json(OUT / (name + ".meta.json"), meta)
    return meta


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(e["symbol"] + "-announcement.html", e["url"]) for e in EVENTS]
    jobs.extend([
        ("settlement-rule-change-20241104.html", "https://www.binance.com/en-AE/support/announcement/detail/4bcabddf0e81423ebca242e185bf157d"),
        ("settlement-faq.html", "https://www.binance.com/en/support/faq/detail/dd60dfbf654d4055aa6b217ea6d5ddba"),
        ("market-data-api-doc.html", "https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data"),
    ])
    for e in EVENTS:
        if "/detail/" in e["url"]:
            jobs.append((e["symbol"] + "-announcement-cms.json", "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode=" + e["url"].split("/")[-1]))
    jobs.append(("settlement-rule-change-cms.json", "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode=4bcabddf0e81423ebca242e185bf157d"))
    for e in EVENTS:
        symbol = e["symbol"]
        terminal = pd.Timestamp(e["terminal_utc"])
        start = terminal - pd.Timedelta(minutes=60 if terminal.year == 2024 else 30)
        jobs.append((symbol + "-delivery-price.json", "https://fapi.binance.com/futures/data/delivery-price?" + urlencode({"pair": symbol})))
        jobs.append((symbol + "-index-1m.json", "https://fapi.binance.com/fapi/v1/indexPriceKlines?" + urlencode({"pair": symbol, "interval": "1m", "startTime": int(start.timestamp()*1000), "endTime": int(terminal.timestamp()*1000)-1, "limit": 100})))
    with ThreadPoolExecutor(max_workers=4) as pool:
        fetched = list(pool.map(fetch, jobs))
    for row in fetched:
        print(json.dumps(row, ensure_ascii=False), flush=True)
    # Inspect only the explicitly frozen family projection, not a fresh data-lake query.
    assert sha(PROJECTION.read_bytes()) == PROJECTION_SHA
    d = pd.read_parquet(PROJECTION)
    slices = []
    reviewed = []
    for e in EVENTS:
        symbol = e["symbol"][:-4] + "/USDT:USDT"
        terminal = pd.Timestamp(e["terminal_utc"])
        end = (terminal + pd.offsets.MonthBegin(1)).normalize() + pd.Timedelta(days=3)
        part = d[d.symbol.eq(symbol) & d.ts.ge(terminal.normalize()-pd.Timedelta(days=1)) & d.ts.lt(end)]
        slices.append(part)
        after = part[part.ts.gt(terminal)]
        record = dict(e, settlement_price_verified=False, exact_settlement_price=None,
                      projection_after_terminal_days=int(len(after)),
                      projection_positive_volume_days_after_terminal=int(after.volume.gt(0).sum()),
                      projection_positive_tradecount_days_after_terminal=int(after.trade_count.gt(0).sum()))
        cms_path = OUT / (e["symbol"] + "-announcement-cms.json")
        cms = json.loads(cms_path.read_bytes())
        if cms.get("code") != "000000" or not cms.get("data"):
            raise ValueError(f"Official CMS response not accepted: {e['symbol']}")
        body = cms["data"]["body"]
        try:
            tree = json.loads(body)
        except json.JSONDecodeError:
            tree = json.loads(body.replace('\\"', '"'))
        body_text = text_nodes(tree)
        terminal_label = terminal.strftime("%Y-%m-%d %H:%M")
        restriction_label = pd.Timestamp(e["new_orders_stop_utc"]).strftime("%Y-%m-%d %H:%M")
        record.update({"official_cms_title": cms["data"]["title"],
                       "official_cms_publish_date": cms["data"].get("publishDate"),
                       "official_cms_path": str(cms_path.relative_to(FAMILY)),
                       "official_cms_sha256": sha(cms_path.read_bytes()),
                       "official_cms_contains_terminal_timestamp": terminal_label in body_text,
                       "official_cms_contains_restriction_timestamp": restriction_label in body_text,
                       "official_cms_contains_automatic_settlement": "automatic settlement" in body_text.lower(),
                       "official_cms_body_text_chars": len(body_text)})
        if not record["official_cms_contains_terminal_timestamp"]:
            raise ValueError(f"Expected terminal timestamp not in official CMS: {e['symbol']}")
        price_path = OUT / (e["symbol"] + "-delivery-price.json")
        index_path = OUT / (e["symbol"] + "-index-1m.json")
        for source, path in [("delivery", price_path), ("index_1m", index_path)]:
            try:
                payload = json.loads(path.read_bytes())
                record[source + "_response_type"] = type(payload).__name__
                record[source + "_response_rows"] = len(payload) if isinstance(payload, list) else None
                if isinstance(payload, dict):
                    record[source + "_error"] = payload
                if source == "delivery" and isinstance(payload, list):
                    record["delivery_records_at_exact_terminal"] = [r for r in payload if r.get("deliveryTime") == int(terminal.timestamp()*1000)]
                if source == "index_1m" and isinstance(payload, list) and payload:
                    times = [r[0] for r in payload]
                    needed = 60 if terminal.year == 2024 else 30
                    record["index_1m_complete_window"] = times == list(range(int((terminal-pd.Timedelta(minutes=needed)).timestamp()*1000), int(terminal.timestamp()*1000), 60_000))
                    if record["index_1m_complete_window"]:
                        record["index_1m_envelope_mean_low"] = sum(float(r[3]) for r in payload)/len(payload)
                        record["index_1m_envelope_mean_high"] = sum(float(r[2]) for r in payload)/len(payload)
                        record["index_1m_envelope_caveat"] = "Not exact settlement: valid only if archived 1m index OHLC covers every index sample used by the official settlement rule. No final settlement receipt."
            except (ValueError, OSError) as exc:
                record[source + "_parse_error"] = str(exc)
        reviewed.append(record)
    output = OUT / "projection-terminal-days.csv"
    if not output.exists():
        pd.concat(slices).to_csv(output, index=False)
    summary = {"status": "TERMINAL_EVENTS_REVIEWED_NOT_SETTLEMENT_VALUES_VERIFIED", "events": reviewed,
               "sources": fetched, "projection": {"path": str(PROJECTION.relative_to(FAMILY)), "sha256": PROJECTION_SHA},
               "projection_extract_sha256": sha(output.read_bytes()),
               "source_script_sha256": sha(Path(__file__).read_bytes()),
               "not_permitted": ["last_trade_as_settlement", "zero_volume_placeholder_as_execution", "successor_symbol_splice", "missing_settlement_fill_zero"],
               "historical_identity_scope": "Five named termination events only; not full PIT identity coverage or proof of other symbol tradability."}
    if not (OUT / "summary-with-cms.json").exists():
        save_json(OUT / "summary-with-cms.json", summary)
    if not (OUT / "final-review.json").exists():
        save_json(OUT / "final-review.json", summary)
    print(json.dumps(reviewed, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
