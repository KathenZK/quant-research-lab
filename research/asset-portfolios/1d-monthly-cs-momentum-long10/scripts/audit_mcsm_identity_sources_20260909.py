"""Four-source identity appendix; no selection changes or counterfactual backtest."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
ROOT = FAMILY / "artifacts/baseline-estimate-20260909"
INPUTS = ROOT / "inputs"
OUT = INPUTS / "selection-appendix/identity-sources"
SOURCES = [
    {"name": "litentry-terminal", "code": "2a9feaa556f74dcdaa2192366f0e247c", "locale": "en",
     "checks": ["Litentry", "Heima", "2025-01-31 09:00", "automatic settlement"]},
    {"name": "lighter-launch", "code": "6a33be00231c4539b3a4a625538e4d1e", "locale": "en-AU",
     "checks": ["Lighter", "2025-12-23", "17:30"]},
    {"name": "aergo-terminal", "code": "db7ad1c7aa6248cda735102cdcdc4b8d", "locale": "en",
     "checks": ["Aergo", "2025-03-27 09:00", "automatic settlement"]},
    {"name": "aergo-relaunch", "code": "82f730b7ef444a38b323ab7a2e56b757", "locale": "en",
     "checks": ["Aergo", "2025-04-16 11:00", "0x91af0fbb28aba7e31403cb457106ce79397fd4e6"]},
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, obj: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(obj, handle, indent=2, ensure_ascii=False, default=str)
        handle.write("\n")


def text_nodes(node: object) -> str:
    if isinstance(node, dict):
        if node.get("node") == "text":
            return str(node.get("text", ""))
        return "".join(text_nodes(child) for child in node.get("child", [])) + (
            "\n" if node.get("tag") in {"p", "h2", "h3", "li", "tr"} else "")
    if isinstance(node, list):
        return "".join(text_nodes(child) for child in node)
    return ""


def fetch(item: dict) -> dict:
    url = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode=" + item["code"]
    path = OUT / (item["name"] + "-cms.json")
    meta_path = OUT / (item["name"] + "-cms.meta.json")
    if path.exists():
        meta = json.loads(meta_path.read_text())
        assert sha(path) == meta["sha256"], "Existing source hash changed"
    else:
        fetched = datetime.now(timezone.utc).isoformat()
        req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"})
        with urlopen(req, timeout=25) as response:
            raw = response.read()
            meta = {"requested_url": url, "final_url": response.geturl(),
                    "fetched_at_utc": fetched, "http_status": response.status,
                    "content_type": response.headers.get("Content-Type"), "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest()}
        with path.open("xb") as handle:
            handle.write(raw)
        save_json(meta_path, meta)
    cms = json.loads(path.read_bytes())
    assert cms.get("code") == "000000" and cms.get("data"), item["name"]
    data = cms["data"]
    body = data["body"]
    try:
        tree = json.loads(body)
    except json.JSONDecodeError:
        tree = json.loads(body.replace('\\"', '"'))
    body_text = text_nodes(tree)
    checks = {token: token.lower() in body_text.lower() for token in item["checks"]}
    assert all(checks.values()), {"source": item["name"], "checks": checks}
    pub = data.get("publishDate")
    result = {"name": item["name"], "title": data["title"], "article_code": item["code"],
              "article_url": f"https://www.binance.com/{item['locale']}/support/announcement/detail/{item['code']}",
              "published_at_utc": pd.Timestamp(pub, unit="ms", tz="UTC").isoformat(),
              "cms_path": str(path.relative_to(FAMILY)), "cms_sha256": sha(path),
              "capture": meta, "fact_token_checks": checks}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        sources = list(pool.map(fetch, SOURCES))
    source_summary = json.loads((INPUTS / "summary.json").read_text())
    for name in ("holdings.parquet", "daily-original-buckets.parquet"):
        assert sha(INPUTS / name) == source_summary["files"][name]
    holdings = pd.read_parquet(INPUTS / "holdings.parquet")
    daily = pd.read_parquet(INPUTS / "daily-original-buckets.parquet")
    price_dir = ROOT / "price-only-first-run/price_only"
    price_summary = json.loads((price_dir / "summary.json").read_text())
    trades_path = price_dir / "trades.parquet"
    trades_sha = sha(trades_path)
    trades = pd.read_parquet(trades_path)
    evidence = []
    executed = []
    for symbol, month in [("AERGO/USDT:USDT", "2025-05-01"), ("LIT/USDT:USDT", "2026-01-01")]:
        row = holdings.loc[holdings.symbol.eq(symbol) & holdings.month.eq(pd.Timestamp(month, tz="UTC"))].iloc[0]
        selected = row.to_dict()
        ends = daily.loc[daily.symbol.eq(symbol) & daily.ts.isin([row.formation_start_day, row.formation_end_day])]
        assert len(ends) == 2
        legs = trades.loc[trades.symbol.eq(symbol) & trades.ts.ge(row.entry_ts) & trades.ts.le(row.exit_ts)].copy()
        assert len(legs) == 2 and legs.iloc[0].old_quantity == 0 and legs.iloc[-1].new_quantity == 0
        cost = float(legs.fee.sum() + legs.slippage.sum())
        pnl = float(legs.realized_price_pnl.sum())
        evidence.append({"holding": selected, "formation_endpoint_rows": ends.to_dict("records"),
                         "realized_price_pnl_usdt": pnl, "actual_trading_costs_usdt": cost,
                         "price_only_net_contribution_usdt": pnl-cost,
                         "signed_share_of_full_price_only_net_profit": (pnl-cost)/price_summary["net_profit_model_usdt"]})
        executed.extend(legs.to_dict("records"))
    total_price = sum(r["realized_price_pnl_usdt"] for r in evidence)
    total_costs = sum(r["actual_trading_costs_usdt"] for r in evidence)
    result = {
        "status": "LIT_CROSS_ASSET_TICKER_REUSE_CONFIRMED_AERGO_TERMINATED_AND_RELAUNCHED_CONTRACT",
        "scope": "Two preidentified long boundaries only; historical official articles captured as of this run; not whole-market PIT governance.",
        "sources": sources,
        "identity_findings": {
            "LIT": {"old_underlying": "Litentry", "old_successor": "Heima (HEI)",
                    "old_futures_termination_utc": "2025-01-31T09:00:00Z",
                    "new_underlying": "Lighter Protocol", "new_futures_launch_utc": "2025-12-23T17:30:00Z",
                    "formation_crosses_different_assets": True, "momentum_signal_identity_valid": False},
            "AERGO": {"old_and_new_underlying_names": "Aergo (AERGO)",
                      "old_futures_termination_utc": "2025-03-27T09:00:00Z",
                      "new_futures_launch_utc": "2025-04-16T11:00:00Z",
                      "new_announcement_underlying_contract_address": "0x91af0fbb28aba7e31403cb457106ce79397fd4e6",
                      "different_token_identity_proven": False, "continuous_same_futures_contract": False,
                      "formation_crosses_terminated_and_relaunched_contracts": True,
                      "scope_note": "Official articles name the same Aergo underlying; full token lineage is not audited. This was automatic settlement and a subsequent launch, not uninterrupted trading."}},
        "two_legs": evidence, "executed_trades": executed,
        "posthoc_attribution": {
            "realized_price_pnl_usdt": total_price, "trading_costs_usdt": total_costs,
            "price_only_net_contribution_usdt": total_price-total_costs,
            "full_price_only_net_profit_usdt": price_summary["net_profit_model_usdt"],
            "signed_share_of_full_price_only_net_profit": (total_price-total_costs)/price_summary["net_profit_model_usdt"],
            "not_counterfactual": True, "funding_included": False,
            "interpretation": "Sums realized PnL and actual fees/slippage on existing account quantities. No rerun, no filtering, and no assertion that removing the legs yields the difference."},
        "input_pins": {"holdings_sha256": sha(INPUTS / "holdings.parquet"),
                       "daily_buckets_sha256": sha(INPUTS / "daily-original-buckets.parquet"),
                       "price_only_trades_path": str(trades_path.relative_to(FAMILY)),
                       "price_only_trades_sha256": trades_sha,
                       "price_only_summary_sha256": sha(price_dir / "summary.json")},
        "frozen_760_holdings_changed": False, "new_backtest_computed": False,
        "strict_baseline_valid": False, "source_script_sha256": sha(Path(__file__))}
    assert sha(trades_path) == trades_sha
    assert sha(INPUTS / "holdings.parquet") == source_summary["files"]["holdings.parquet"]
    save_json(OUT / "summary.json", result)
    print(json.dumps(result["posthoc_attribution"], indent=2), flush=True)


if __name__ == "__main__":
    main()
