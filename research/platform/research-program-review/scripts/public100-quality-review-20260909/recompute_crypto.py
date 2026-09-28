#!/usr/bin/env python3
"""Read-only PUBLIC100 D7-D10 independent execution-ledger audit.

Run with the already-installed Freqtrade Python (pandas for Feather only):
  /tmp/public100-freqtrade-env/bin/python /tmp/public100-quality-crypto-20260909/recompute_crypto.py

No downloads, strategy execution, backtest, optimization, or repository writes.
All results are diagnostic account arithmetic, not a formal strategy acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import zipfile

import pandas as pd


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def group_summary(trades, key):
    groups = defaultdict(list)
    for trade in trades:
        groups[key(trade)].append(trade)
    return {
        k: {"trades": len(v), "pnl": math.fsum(t["net"] for t in v),
            "gross": math.fsum(t["gross"] for t in v),
            "fees": math.fsum(t["fees"] for t in v),
            "wins": sum(t["net"] > 0 for t in v)}
        for k, v in sorted(groups.items())
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("/Users/ZK/OpenCode/quant-strategy-lab"))
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    repo = args.repo.resolve()
    family = repo / "research/asset-portfolios/multi-public-strategies-100"
    out = args.out.resolve()
    if out == repo or repo in out.parents:
        raise ValueError("Audit output must be outside the repository")
    out.mkdir(parents=True, exist_ok=True)
    inputs = {}

    def read(path, snapshot=False):
        path = path.resolve()
        data = path.read_bytes()
        label = str(path.relative_to(repo)) if repo in path.parents else str(path)
        entry = {"path": label, "absolute_path": str(path), "sha256": sha(data), "bytes": len(data)}
        if snapshot:
            dest = out / "snapshots" / (label if not label.startswith("/") else "runtime/" + path.name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            entry["snapshot"] = str(dest.relative_to(out))
        inputs[str(path)] = entry
        return data

    for name in ["specs/run-contract-v1.json", "specs/freqtrade-backtest-config.json",
                 "specs/data-and-execution-boundaries.md", "scripts/run_freqtrade.py",
                 "scripts/prepare_freqtrade.py", "scripts/summarize_native.py",
                 "artifacts/freqtrade-adapter-manifest.json",
                 "diagnostics/crypto-failure-attribution-20260909.md",
                 "diagnostics/public100-progress-ranking-20260909.md"]:
        read(family / name, snapshot=True)
    source_root = family / "artifacts/sources"
    for dirname, pattern in [
        ("surendrad24__ZwaAP-FreqTrade-Strategies", "*.py"),
        ("vishnugovind10__institutional-crypto-funding-analyzer", "*.py"),
        ("Adeline117__Strategy-project", "*.py"),
        ("briplot__systematic-crypto-strategy", "notebook-code.txt"),
        ("0xSmartCrypto__meridian", "*.ts"),
    ]:
        for path in sorted((source_root / dirname).rglob(pattern)):
            read(path, snapshot=True)
        read(source_root / dirname / "README.md", snapshot=True)
    for name in ["optimize/backtesting.py", "wallets.py", "strategy/interface.py", "config_schema/config_schema.py"]:
        path = Path("/tmp/public100-freqtrade-env/lib/python3.12/site-packages/freqtrade") / name
        if path.exists():
            read(path, snapshot=True)

    manifest = json.loads(read(family / "artifacts/freqtrade/run-manifest.json", snapshot=True))
    results = []
    all_trades = []
    for run in manifest["runs"]:
        assert run["returncode"] == 0, run
        zip_path = family / run["files"][0]
        zdata = read(zip_path)
        with zipfile.ZipFile(io.BytesIO(zdata)) as zipped:
            names = zipped.namelist()
            main_name = next(n for n in names if n.endswith(".json") and not n.endswith("_config.json"))
            strat = json.loads(zipped.read(main_name))["strategy"][run["strategy"]]
            zipped_config = zipped.read(next(n for n in names if n.endswith("_config.json")))
            config = json.loads(zipped_config)
            code = zipped.read(next(n for n in names if n.endswith("_" + run["strategy"] + ".py")))
            local_code = read(source_root / "surendrad24__ZwaAP-FreqTrade-Strategies/strategies" / (run["strategy"] + ".py"), snapshot=True)
            assert code == local_code, (run["id"], "source mismatch")
            assert config["stake_amount"] == 12 and config["dry_run_wallet"] == 25
            assert config["max_open_trades"] == 1 and config["trading_mode"] == "spot"
            assert config["tradable_balance_ratio"] == .99
            assert strat["starting_balance"] == 25 and strat["max_open_trades"] == 1
            trades = []
            for index, original in enumerate(strat["trades"]):
                assert not original["is_short"] and not original["is_open"]
                assert original["funding_fees"] == 0  # Spot; funding is inapplicable.
                buys = []; sells = []; fees = []; orders = []
                for order in original["orders"]:
                    side = order["ft_order_side"]
                    assert side in {"buy", "sell"}
                    notional = order["safe_price"] * order["amount"]
                    fee = original["fee_open"] if side == "buy" else original["fee_close"]
                    assert fee == run["fee"]
                    (buys if side == "buy" else sells).append(notional)
                    fees.append(notional * fee)
                    orders.append({"side": side, "price": order["safe_price"], "amount": order["amount"],
                                   "timestamp": order["order_filled_timestamp"], "notional": notional,
                                   "fee_rate": fee, "fee": notional * fee})
                gross = math.fsum(sells) - math.fsum(buys)
                total_fee = math.fsum(fees)
                net = gross - total_fee
                error = abs(net - original["profit_abs"])
                assert error < 1e-8, (run["id"], index, error)
                trades.append({"index": index, "pair": original["pair"], "open": original["open_date"],
                               "close": original["close_date"], "close_year": original["close_date"][:4],
                               "entries": len(buys), "exit_reason": original["exit_reason"],
                               "buy_notional": math.fsum(buys), "sell_notional": math.fsum(sells),
                               "turnover": math.fsum(buys + sells), "gross": gross, "fees": total_fee,
                               "net": net, "reported_net": original["profit_abs"], "error": error,
                               "reported_profit_ratio": original["profit_ratio"], "orders": orders})
            total = math.fsum(t["net"] for t in trades)
            gross = math.fsum(t["gross"] for t in trades)
            fees = math.fsum(t["fees"] for t in trades)
            turnover = math.fsum(t["turnover"] for t in trades)
            wins = [t for t in trades if t["net"] > 0]
            losses = [t for t in trades if t["net"] < 0]
            mean_win = math.fsum(t["net"] for t in wins) / len(wins)
            mean_loss = math.fsum(t["net"] for t in losses) / len(losses)
            capital_error = abs(strat["final_balance"] - (25 + total))
            assert capital_error < 1e-6
            wallet_name = next(n for n in names if n.endswith("_wallet.feather"))
            wallet = pd.read_feather(io.BytesIO(zipped.read(wallet_name)))
            equity = wallet.groupby("date", sort=True)["total_quote"].sum()
            mdd = float((1 - equity / equity.cummax()).max())
            assert abs(mdd - strat["wallet_stats"]["max_drawdown_account"]) < 1e-10
            result = {
                "id": run["id"], "strategy": run["strategy"], "fee_one_way": run["fee"],
                "zip_path": run["files"][0], "zip_sha256": sha(zdata),
                "source_identical_to_native_zip": True, "source_sha256": sha(code),
                "native_config_sha256": sha(zipped_config),
                "trades": len(trades), "wins": len(wins), "losses": len(losses),
                "win_rate": len(wins) / len(trades), "mean_win_usdt": mean_win,
                "mean_loss_usdt": mean_loss, "win_loss_payoff_ratio": mean_win / abs(mean_loss),
                "sample_breakeven_win_rate": abs(mean_loss) / (mean_win + abs(mean_loss)),
                "mean_trade_usdt": total / len(trades),
                "mean_win_profit_ratio": math.fsum(t["reported_profit_ratio"] for t in wins) / len(wins),
                "mean_loss_profit_ratio": math.fsum(t["reported_profit_ratio"] for t in losses) / len(losses),
                "profit_factor": math.fsum(t["net"] for t in wins) / abs(math.fsum(t["net"] for t in losses)),
                "gross_same_fills_usdt": gross, "fees_usdt": fees, "net_usdt": total,
                "turnover_usdt": turnover, "total_return": total / 25,
                "final_balance": strat["final_balance"], "wallet_mdd_recomputed": mdd,
                "realized_mdd_reported": strat["max_drawdown_account"],
                "wallet_peak_recomputed": float(equity.max()), "wallet_peak_time": str(equity.idxmax()),
                "last_trade": max(t["close"] for t in trades),
                "end_available_99pct": strat["final_balance"] * .99,
                "end_available_below_fixed_stake": strat["final_balance"] * .99 < 12,
                "fees_fraction_of_positive_gross": fees / gross if gross > 0 else None,
                "same_fill_breakeven_total_one_way_bps": gross / turnover * 10000,
                "same_fill_remaining_one_way_bps": total / turnover * 10000,
                "max_trade_reconciliation_error": max(t["error"] for t in trades),
                "capital_reconciliation_error": capital_error,
                "exit_attribution": group_summary(trades, lambda t: t["exit_reason"]),
                "entry_count_attribution": group_summary(trades, lambda t: str(t["entries"])),
                "pair_attribution": group_summary(trades, lambda t: t["pair"]),
                "year_attribution_by_close": group_summary(trades, lambda t: t["close_year"]),
                "top_5_wins_net": math.fsum(sorted((t["net"] for t in wins), reverse=True)[:5]),
                "rejected_signals": strat["rejected_signals"],
                "native_timeframe": strat["timeframe"], "native_detail_timeframe": strat["timeframe_detail"],
                "native_cagr_reported": strat["cagr"],
            }
            results.append(result)
            all_trades.append({"id": run["id"], "fee": run["fee"], "trades": trades})

    # The continuation directory can be active. Record a point-in-time inventory,
    # not an endorsement or a publication status inferred from partial results.
    continuation_inventory = []
    continuation = family / "artifacts/continuation-r2"
    for path in sorted(continuation.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            continuation_inventory.append({"path": str(path.relative_to(family)), "sha256": sha(data),
                                           "bytes": len(data), "mtime_ns": path.stat().st_mtime_ns})
    # Existing frozen inputs should not change while they are being audited.
    for path, meta in inputs.items():
        assert sha(Path(path).read_bytes()) == meta["sha256"], (path, "INPUT_CHANGED_DURING_AUDIT")

    output = {
        "audit_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "EXPLORE_UNTRUSTED_INDEPENDENT_LEDGER_RECOMPUTATION",
        "repo": str(repo), "script_sha256": sha(Path(__file__).read_bytes()),
        "no_downloads_no_backtest_no_optimization": True,
        "runs": results,
        "checks": {"run_count": len(results), "trade_count_across_fee_paths": sum(r["trades"] for r in results),
                   "source_identity_passes": sum(r["source_identical_to_native_zip"] for r in results),
                   "wallet_mdd_reconciliation_passes": len(results),
                   "max_trade_error": max(r["max_trade_reconciliation_error"] for r in results),
                   "max_capital_error": max(r["capital_reconciliation_error"] for r in results),
                   "inputs_unchanged_during_audit": True},
        "limits": ["Same-fill gross attribution is not a zero-fee rerun.",
                   "Fee sensitivity paths differ; fees are not a realistic limit-fill or slippage model.",
                   "Wallet MDD sampled on the native strategy timeframe is not continuous intrabar account risk.",
                   "This does not independently revalidate all source market-data rows or historical venue filters.",
                   "Continuation inventory is a timestamped observation, not publication acceptance."],
        "inputs": sorted(inputs.values(), key=lambda x: x["path"]),
        "continuation_inventory_not_accepted_results": continuation_inventory,
    }
    (out / "recomputed.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    (out / "trade_attribution.json").write_text(json.dumps(all_trades, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(output["checks"], indent=2))
    for row in results:
        print(f"{row['id']} fee={row['fee_one_way']:.4f}: trades={row['trades']}, "
              f"gross={row['gross_same_fills_usdt']:.9f}, fees={row['fees_usdt']:.9f}, "
              f"net={row['net_usdt']:.9f}, return={row['total_return']:.6%}, "
              f"wallet_mdd={row['wallet_mdd_recomputed']:.6%}")


if __name__ == "__main__":
    main()
