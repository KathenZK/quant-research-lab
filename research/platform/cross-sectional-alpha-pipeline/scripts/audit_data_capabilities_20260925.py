"""Predeclared coverage probe. No alpha fitting, return ranking or universe search."""
from pathlib import Path
import json

import duckdb
import pandas as pd

from strategy_lab.data.research_bundle import read_bundle_contract, require_research_startup
from strategy_lab.data.funding_v2 import load_funding_v2
from strategy_lab.research.evidence import sha256

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "research/platform/cross-sectional-alpha-pipeline/artifacts/implementation-20260925/data-capabilities"


def main():
    bundle, pin = read_bundle_contract(ROOT)
    request = {"schema_version": 1, **pin, "mode": "price_diagnostic", "timeframe": "1d",
               "symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT", "HYPE/USDT:USDT"],
               "start": "2025-07-01T00:00:00Z", "end": "2026-09-05T00:00:00Z",
               "gap_policy": "reject", "asset_policy": "crypto_only", "backward_bars": 30, "forward_bars": 3}
    OUT.mkdir(exist_ok=False)
    (OUT / "request.json").write_text(json.dumps(request, indent=2) + "\n")
    accepted = require_research_startup(request, project_root=ROOT)
    (OUT / "price-startup-receipt.json").write_text(json.dumps(accepted.report, indent=2) + "\n")
    fc = bundle["components"]["funding"]
    funding = load_funding_v2(ROOT / "data" / fc["root"], expected_manifest_sha256=fc["manifest_sha256"])
    funding.segments.to_csv(OUT / "proven-funding-segments.csv", index=False)
    price_root = ROOT / "data" / bundle["components"]["1d"]["root"]
    paths = [str(p) for p in sorted(price_root.rglob("*.parquet"))]
    # Entire physical inventory was content-verified by the startup above. This
    # read only measures observed coverage; it is not a new trading universe.
    con = duckdb.connect()
    try:
        relation = con.read_parquet(paths, hive_partitioning=False)
        columns = relation.columns
        daily = relation.aggregate("symbol, count(*) as observed_daily_rows, min(ts) as first_open, max(ts) as last_open", "symbol").df()
    finally:
        con.close()
    segments = funding.segments
    coverage = segments.groupby("symbol").agg(funding_segments=("segment_id", "size"),
                                                proven_funding_first=("start", "min"), proven_funding_last=("end", "max"))
    events = funding.events.groupby("symbol").agg(observed_funding_events=("event_id", "size"),
                                                   ambiguous_events=("event_unambiguous", lambda x: int((~x).sum())))
    matrix = pd.DataFrame([{"symbol": s, "observed_asset_class": cls} for s, cls in bundle["observed_asset_classes"].items()])
    matrix = matrix.merge(daily, on="symbol", how="left").merge(coverage, on="symbol", how="left").merge(events, on="symbol", how="left")
    matrix["funding_segments"] = matrix.funding_segments.fillna(0).astype(int)
    matrix["pit_universe_proven"] = False
    matrix["identity_for_requested_account"] = "NOT_REVIEWED_BY_THIS_AUDIT"
    matrix["mark_price_in_bundle"] = False
    matrix["available_at_received_at_in_price_schema"] = "available_at" in columns and "received_at" in columns
    matrix["taker_buy_volume_in_price_schema"] = "taker_buy_volume" in columns
    matrix["funding_note"] = "first/last span is not continuous full-window proof"
    matrix.to_csv(OUT / "observed-code-capabilities.csv", index=False)
    probes = []
    a, b = pd.Timestamp(request["start"]), pd.Timestamp(request["end"])
    for symbol, price in accepted.prices.items():
        price.to_parquet(OUT / (symbol.split("/")[0] + "-returned-price.parquet"), index=False)
        full = segments[segments.symbol.eq(symbol) & segments.start.le(a) & segments.end.ge(b)]
        observed = funding.events[funding.events.symbol.eq(symbol) & funding.events.ts.gt(a) & funding.events.ts.le(b)]
        calendar_pass = False
        if len(full) == 1:
            expected = funding.expected[funding.expected.segment_id.eq(full.segment_id.iloc[0]) & funding.expected.ts.gt(a) & funding.expected.ts.le(b)]
            calendar_pass = bool(observed.event_unambiguous.all() and set(observed.event_id) == set(expected.event_id))
        probes.append({"symbol": symbol, **accepted.report["symbols"][symbol],
                       "observed_funding_events_in_window": len(observed),
                       "full_window_funding_segments": len(full), "funding_calendar_proven": calendar_pass,
                       "identity_reviewed": False, "mark_price_verified": False,
                       "net_research_ready": False, "exclusion_reason": "full-window funding proof absent; identity and mark-price evidence not certified" if not calendar_pass else "identity and mark-price evidence not certified"})
    result = {"status": "PRICE_PROBE_PASS_NET_EXPERIMENT_NOT_STARTED", "request": request,
              "observed_codes": len(matrix), "observed_daily_rows": int(matrix.observed_daily_rows.sum()),
              "funding_events": len(funding.events), "funding_proven_symbols": int((matrix.funding_segments > 0).sum()),
              "funding_proven_segments": len(segments), "price_columns": columns, "probe": probes,
              "price_diagnostic_only": True, "alpha_metrics_computed": False,
              "pit_universe_proven": False, "received_at_available_at_reconstructed": False,
              "oi_basis_orderbook_mark_in_bundle": False,
              "scope_note": "capability of current frozen input bundle, not a claim that no other local/provider data exists"}
    (OUT / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    files = {str(p.relative_to(OUT)): sha256(p) for p in OUT.iterdir() if p.is_file()}
    (OUT / "checksums.json").write_text(json.dumps(files, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
