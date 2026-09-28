"""Fixed weekly Top10 continuation; official terminal-index conditional estimates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from audit_mcsm_weekly_account_20260911 import load_saved_endpoints
from research_mcsm_single_asset_exit_20260910 import load_frozen_inputs
from research_mcsm_weekly_20260911 import (
    DAY, END, FAMILY, MIN15, ROOT, apply_known_terminals, baseline_adapter_recheck,
    feature_table, nominate, pin, priced_windows, qualify_ranked, replay_price, save, sha,
)

START = pd.Timestamp("2020-06-01T00:15Z")
OLD = FAMILY / "artifacts/drawdown-frequency-round-20260911/weekly"
OUT = FAMILY / "artifacts/weekly-top10-20260924"
SPEC = FAMILY / "specs/binance-1d-mcsm-weekly-top10-20260924.md"
SCRIPT_PINS = {
    "research_mcsm_weekly_20260911.py": "69d710405a2d14a22fc6061c3a1c4e4e54824142d7e5ff4169e6757c971acb31",
    "audit_mcsm_weekly_account_20260911.py": "be3d0f4e24c5206cb1c5fc4a9cdc8dffbc5b175d47b61caee07882a8413446e7",
    "mcsm_baseline_accounting_20260908.py": "0445d4e7afa76576558dfd122983dab2c12e523718383f01d45bfc0e2779972c",
}


def load_inputs():
    for name, digest in SCRIPT_PINS.items():
        pin(Path(__file__).with_name(name), digest)
    pin(OLD / "postrun-integrity.json", "7c1b3cc76843e9f542cedc6883ee1c22acb2709d09ead67de556fc85ceeb452b")
    integrity = json.loads((OLD / "postrun-integrity.json").read_text())
    pin(OLD / "summary.json", integrity["summary_sha256"])
    pin(OLD / "execution-plan.json", "b8fac320f7e8faabce9a78f1e3d818e685215fbf9ce7d2f4a3275ab9f76fc289")
    pin(OLD / "qualified-nomination-freeze.json", "bf10ef25d99953f0f25c0eacbfa89ea43bf7b749f37b386bba07b5d4c8574e0a")
    chosen = json.loads((OLD / "qualified-nomination-freeze.json").read_text())
    pin(OLD / "qualification-plan.json", chosen["qualification_plan_sha256"])
    pin(OLD / "nominations.parquet", chosen["nominations_sha256"])
    for item in integrity["new_receipt_hashes"]:
        pin(OLD / item["path"], item["sha256"])
    plan = json.loads((OLD / "execution-plan.json").read_text())
    pin(OLD / "holding-windows.parquet", plan["holding_windows_sha256"])
    endpoints, hashes = load_saved_endpoints(plan)
    h, _, daily, _, terminals, _ = load_frozen_inputs()
    return h, daily, endpoints, terminals, pd.read_parquet(OLD / "nominations.parquet"), hashes


def prepare_holdings(base, daily, endpoints, old_nom):
    feat = feature_table(daily)
    ranked, counts = nominate(feat, "W7", start=pd.Timestamp("2020-04-01T00:15Z"), end=END, all_candidates=True)
    if not counts.status.eq("TEN_AVAILABLE").all():
        raise ValueError("missing weekly eligible decision")
    rebuilt, _ = qualify_ranked(ranked, endpoints)
    old = old_nom.loc[old_nom.strategy.eq("W7")]
    columns = ["entry_ts", "symbol", "rank", "formation_return", "adv30", "scheduled_exit_ts"]
    a = rebuilt[columns].sort_values(["entry_ts", "symbol"]).reset_index(drop=True)
    b = old[columns].sort_values(["entry_ts", "symbol"]).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False, rtol=1e-12, atol=1e-12)
    weekly = rebuilt.loc[rebuilt.entry_ts.ge(START)].copy()
    monthly = base.loc[base.entry_ts.ge(START)].copy()
    monthly["strategy"] = "B0"
    monthly["decision_ts"] = monthly.month
    monthly["scheduled_exit_ts"] = monthly.month + pd.offsets.MonthBegin(1) + MIN15
    cols = ["strategy", "decision_ts", "entry_ts", "scheduled_exit_ts", "symbol", "weight"]
    h = pd.concat([monthly[cols], weekly[cols]], ignore_index=True)
    validate_schedule(h)
    return h, {"all_original_w7_nominations_rebuilt": len(rebuilt), "exact_saved_nomination_parity": True,
               "no_ma120_filter": True, "counts": h.groupby("strategy").size().to_dict()}


def validate_schedule(h):
    if set(h.strategy) != {"B0", "W7"}:
        raise ValueError("wrong strategy set")
    for strategy, g in h.groupby("strategy"):
        expected = pd.date_range(START.floor("D"), END.floor("D") - DAY,
                                 freq="MS" if strategy == "B0" else "W-MON") + MIN15
        counts = g.groupby("entry_ts").size()
        if list(counts.index) != list(expected) or not counts.eq(10).all():
            raise ValueError("incomplete Top10 schedule")
        if g.duplicated(["entry_ts", "symbol"]).any() or not np.allclose(g.weight, .1):
            raise ValueError("non-fixed 10 percent slots")
        if not g.scheduled_exit_ts.gt(g.entry_ts).all() or g.scheduled_exit_ts.max() != END:
            raise ValueError("incorrect holding period")


def load_new_terminals():
    path = OUT / "terminal-evidence/summary.json"
    evidence = json.loads(path.read_text())
    assert evidence["status"] == "TWO_OFFICIAL_INDEX_WINDOWS_AVAILABLE_NOT_EXACT_SETTLEMENT"
    for name, digest in evidence["files_sha256"].items():
        pin(path.parent / name, digest)
    terms = []
    for row in evidence["events"]:
        for kind in ["source", "announcement", "window"]:
            pin(FAMILY / row[f"{kind}_path"], row[f"{kind}_sha256"])
        terms.append({**row, "ts": pd.Timestamp(row["ts"])})
    return terms


def choose_terminals(terms, scenario):
    if scenario not in {"center", "low", "high"}:
        raise ValueError("unprescribed terminal scenario")
    return [{**t, "center": t[scenario]} for t in terms]


def leg_cash(h, result, endpoints, terminals):
    legs = priced_windows(h, endpoints, terminals)
    if not legs.endpoint_status.eq("BOTH_REFERENCE_PRICES_AVAILABLE").all():
        raise ValueError("unpriced held leg")
    q = result["trades"].set_index(["ts", "symbol"]).new_quantity.to_dict()
    legs["account_entry_quantity"] = [q[(t, s)] for t, s in zip(legs.entry_ts, legs.symbol)]
    legs["period_price_pnl_usdt"] = legs.account_entry_quantity * (legs.exit_reference_price - legs.entry_reference_price)
    # Equal-entry capital comparison keeps compounding and account size separate.
    legs["standalone_net_price_return"] = legs.gross_price_return - (.001 + result["metrics"]["slippage_rate"])
    legs["standalone_net_price_return"] -= (legs.exit_reference_price / legs.entry_reference_price
        * (.001 + np.where(legs.terminal, 0., result["metrics"]["slippage_rate"])))
    if not np.isclose(legs.period_price_pnl_usdt.sum(), result["metrics"]["price_pnl_usdt"], atol=1e-6, rtol=1e-11):
        raise ValueError("leg cash does not reconcile")
    return legs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "execute"])
    args = parser.parse_args()
    base, daily, endpoints, original_terms, old_nom, hashes = load_inputs()
    if args.phase == "prepare":
        h, parity = prepare_holdings(base, daily, endpoints, old_nom)
        terms = original_terms + load_new_terminals()
        h = apply_known_terminals(h, terms)
        h.to_parquet(OUT / "holding-windows.parquet", index=False)
        grid = sorted(set(h.entry_ts) | {END})
        save(OUT / "plan.json", {"contract_sha256": sha(SPEC), "script_sha256": sha(Path(__file__)),
                                 "source_script_pins": SCRIPT_PINS, "start": START, "end": END,
                                 "holdings_sha256": sha(OUT / "holding-windows.parquet"), "parity": parity,
                                 "terminal_evidence_sha256": sha(OUT / "terminal-evidence/summary.json"),
                                 "common_grid": grid, "retained_endpoint_hashes": hashes,
                                 "no_new_strategy_returns_computed": True,
                                 "scenarios": [{"terminal": t, "slip": s} for t in ["center", "low", "high"]
                                               for s in ([.0004, .0008] if t == "center" else [.0004])]})
        print(json.dumps(parity), flush=True)
        return
    plan = json.loads((OUT / "plan.json").read_text())
    pin(SPEC, plan["contract_sha256"])
    pin(Path(__file__), plan["script_sha256"])
    pin(OUT / "holding-windows.parquet", plan["holdings_sha256"])
    pin(OUT / "terminal-evidence/summary.json", plan["terminal_evidence_sha256"])
    for name, digest in plan["retained_endpoint_hashes"].items():
        pin(ROOT / name, digest)
    h = pd.read_parquet(OUT / "holding-windows.parquet")
    validate_schedule(h)
    terms = original_terms + load_new_terminals()
    grid = [pd.Timestamp(t) for t in plan["common_grid"]]
    # Full original 76-month comparator remains exactly reproducible.
    parity76 = baseline_adapter_recheck(endpoints, daily, original_terms, OUT)
    old_b0 = pd.read_parquet(OLD / "holding-windows.parquet")
    old_b0 = old_b0.loc[old_b0.strategy.eq("B0")]
    old_grid = [pd.Timestamp(t) for t in json.loads((OLD / "execution-plan.json").read_text())["common_grid"]]
    check75 = replay_price(old_b0, endpoints, daily, original_terms, old_grid, .0004)
    expected75 = next(r for r in json.loads((OLD / "summary.json").read_text())["accounts"]
                      if r["strategy"] == "B0" and r["slippage_rate"] == .0004)
    for key in ["total_return", "final_equity", "max_drawdown_common_grid", "fees_usdt", "slippage_usdt"]:
        assert np.isclose(check75["metrics"][key], expected75[key], rtol=1e-11, atol=1e-6), key
    save(OUT / "baseline-reproductions.json", {"original76": parity76, "old75": {"matches": True,
                                               "final_equity": check75["metrics"]["final_equity"]}})
    results = []
    for sc in plan["scenarios"]:
        selected_terms = choose_terminals(terms, sc["terminal"])
        for strategy, held in h.groupby("strategy", sort=True):
            label = f"{strategy}-{sc['terminal']}-{round(sc['slip'] * 10000)}bp"
            print(f"REPLAY {label}", flush=True)
            directory = OUT / label
            directory.mkdir()
            try:
                result = replay_price(held, endpoints, daily, selected_terms, grid, sc["slip"], start=START, end=END)
                result["leg-price-pnl"] = leg_cash(held, result, endpoints, selected_terms)
            except (ValueError, KeyError) as exc:
                failed = {"strategy": strategy, "terminal_scenario": sc["terminal"], "slippage_rate": sc["slip"],
                          "status": "BLOCKED_NO_SKIPPING_OR_RETURN_PUBLISHED", "reason": str(exc), "total_return": None}
                save(directory / "summary.json", failed)
                results.append(failed)
                continue
            metrics = result.pop("metrics")
            nav = result["nav"].set_index("ts")
            turnovers = []
            for ts, trades in result["trades"].groupby("ts"):
                equity = float(nav.loc[ts].equity)
                turnovers.append(float(trades.traded_notional.sum()) / equity)
            metrics.update(strategy=strategy, terminal_scenario=sc["terminal"],
                           status="CONDITIONAL_TERMINAL_ESTIMATE_PRICE_ONLY_NOT_VERIFIED_NET",
                           traded_notional_usdt=float(result["trades"].traded_notional.sum()),
                           turnover_sum_equity_units=float(sum(turnovers)),
                           mean_rebalance_turnover_equity=float(np.mean(turnovers)),
                           weekly_or_monthly_win_rate=float(result["periods"]["return"].gt(0).mean()))
            for name, frame in result.items():
                frame.to_parquet(directory / f"{name}.parquet", index=False)
            save(directory / "summary.json", metrics)
            results.append(metrics)
            print(json.dumps({k: metrics[k] for k in ["strategy", "terminal_scenario", "slippage_rate", "total_return",
                                                    "cagr_365_25", "max_drawdown_common_grid", "terminal_closes"]}), flush=True)
    save(OUT / "summary.json", {"status": "COMPUTED_PENDING_INDEPENDENT_AUDIT", "accounts": results,
                                "funding_included": False, "exact_terminal_settlement_verified": False,
                                "files_sha256": {str(p.relative_to(OUT)): sha(p) for p in sorted(OUT.rglob("*")) if p.is_file()}})


if __name__ == "__main__":
    main()
