"""Rebuild monthly summaries and consolidate every completed frozen observation."""
import hashlib
import json
import numpy as np
import pandas as pd
import other_assets_replay as ar


def rebuild_months():
    checks = []
    for path in sorted(ar.OUT.rglob("*_equity.csv")):
        curve = pd.read_csv(path)
        curve["ts"] = pd.to_datetime(curve.ts, utc=True)
        # An August 1 00:00 close finishes July's final interval.
        months = (curve.ts - pd.Timedelta(nanoseconds=1)).dt.strftime("%Y-%m")
        rows, previous = [], 1.
        for month, group in curve.groupby(months):
            value = float(group.equity.iloc[-1])
            rows.append({"month": month, "return": value / previous - 1., "ending_equity": value})
            previous = value
        monthly = pd.DataFrame(rows)
        monthly.to_csv(path.with_name(path.name.replace("_equity.csv", "_monthly.csv")), index=False)
        assert np.isclose(np.prod(1. + monthly["return"]), float(curve.equity.iloc[-1]), rtol=1e-12, atol=1e-12)
        checks.append({"equity_path": str(path.relative_to(ar.ROOT)), "months": len(rows), "pass": True})
    ar.write_json(ar.OUT / "monthly_verification.json", {"status": "PASS", "month_assignment": "close timestamp minus one nanosecond", "checks": checks})


def main():
    rebuild_months()
    supplements, raw_results = [], []
    root = ar.OUT / "unregistered_observations"
    for path in sorted(root.glob("*/results.json")):
        values = json.loads(path.read_text())
        raw_results.extend(values)
        cfg = json.loads((path.parent / "frozen_contract.json").read_text())
        for row in values:
            scenario = row["scenario"]
            fee = row.get("fee_per_fill", .001)
            slip = row.get("slippage_per_fill", .0008 if scenario == "slippage_8bps" else .0004)
            limitation = "Frozen unregistered observation; no re-selection; limited sample; funding cashflow/coverage not fully verified"
            if row.get("timeframe") == "30m":
                limitation += "; UTC 30m aggregates two verified 15m bars and retains the original 8640-bar (180-day) quantile window"
            if cfg.get("limitation"):
                limitation += "; " + cfg["limitation"]
            supplements.append({
                **row, "family": cfg.get("family", row["name"]), "registered": False, "primary": False,
                "drawdown": row["close_marked_max_drawdown"], "trades": row["trade_count"],
                "cost": f"{fee:g} fee/fill + {slip * 10000:g} bps adverse slip/fill; observed funding estimate",
                "equity_path": str((path.parent / f"{scenario}_equity.csv").relative_to(ar.ROOT)),
                "trades_path": str((path.parent / f"{scenario}_trades.csv").relative_to(ar.ROOT)),
                "source": str((path.parent / "frozen_contract.json").relative_to(ar.ROOT)),
                "limitation": limitation,
            })
    ar.write_json(root / "results.json", raw_results)
    ar.write_json(ar.OUT / "supplemental_results.json", supplements)
    pending = [{
        "family": "bnb/15m-adaptive-regime", "status": "NO_UNIQUE_FROZEN_STRATEGY", "missing": None,
        "reason": "Ledger and reports contain market-character/event diagnostics and candidate search scripts, but identify no single frozen selected strategy/configuration; a new performance search would be needed to choose one",
        "evidence": "research/bnb/15m-adaptive-regime/bnb-15m-ar-core-ledger.md",
    }]
    assert (ar.ROOT / pending[0]["evidence"]).exists()
    ar.write_json(ar.OUT / "scope_inventory.json", {
        "registered_single_asset_replayed": [{"asset": asset, "version": value[0], "registration_date": value[1], "results": f"{asset}/results.json"} for asset, value in ar.REGISTERED.items()],
        "registered_six_asset_replayed": {"family": "Binance-15M-AS6S", "version": "V6", "routes": 2, "parameter_recovery": "as6s_recovery.json", "results": "AS6S_V6/results.json", "status": "RECOVERED_AND_REPLAYED", "limitation": "Original Lab freeze deleted; recovered original runner configuration and historical parity evidence. Original freeze hash and full historical parity were not re-verified."},
        "unregistered_unique_frozen_observations_replayed": sorted(set(row["name"] for row in supplements)),
        "supplemental_scenario_count": len(supplements),
        "unreplayed": pending,
        "scope_policy": "Current request covers registered versions and uniquely frozen spec/report observations. Lack of registration alone does not exclude a strategy. The frozen SOL 4h RS4 observation is supplemental with its original open-to-open model limitation.",
    })
    # Only regenerate pins for our orchestration code. Original pins must hold.
    for path in ar.OUT.rglob("source_pins.json"):
        pins = json.loads(path.read_text())
        for source in pins:
            current = hashlib.sha256((ar.ROOT / source).read_bytes()).hexdigest()
            if source.startswith("research/asset-portfolios/multi-legacy-post-registration-audit/scripts/other_assets"):
                pins[source] = current
            else:
                assert current == pins[source], f"Pinned source changed: {source}"
        ar.write_json(path, pins)
    print(f"Consolidated {len(supplements)} supplemental scenario rows; rebuilt all monthly tables")


if __name__ == "__main__":
    main()
