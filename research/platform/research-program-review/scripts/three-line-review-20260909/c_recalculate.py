#!/usr/bin/env python3
"""Offline independent checks for C0/C0-E1; never import the research engine.

Reads frozen local inputs only. Writes this audit's JSON to --output, never to
the source family. This is accounting verification, not executable-net-return
or long-term-strategy certification.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text())


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def num(row: dict[str, str], key: str) -> float:
    return float(row.get(key) or 0)


def depth_price(levels: list, quantity: float, inverse: bool = False) -> float:
    remaining = quantity
    cost = 0.0
    for row in levels:
        price, size = map(float, row[:2])
        fill = min(remaining, size)
        cost += fill / price if inverse else fill * price
        remaining -= fill
        if remaining <= 1e-10:
            return quantity / cost if inverse else cost / quantity
    raise ValueError(f"Insufficient captured depth: {remaining} unfilled")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path,
        default=Path("/Users/ZK/.codex/worktrees/5f41/quant-strategy-lab"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("/tmp/three-line-c-review-20260909/review_results.json"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if output.is_relative_to(root):
        raise ValueError("Refusing output inside the source worktree")
    family = root / "research/asset-portfolios/8h-btceth-small-account-carry"
    raw = family / "artifacts/raw/capture_curl_20260908"
    results = family / "artifacts/results"
    summary = read_json(results / "summary.json")
    orders = csv_rows(results / "orders.csv")
    quotes = csv_rows(results / "quotes_and_economics.csv")
    instruments = {
        row["instId"]: row
        for row in read_json(family / "artifacts/raw/spot_instruments.json")["data"]
    }

    manifest = read_json(family / "artifacts/input_manifest.json")
    mismatches = [
        row["path"] for row in manifest["files"]
        if hashlib.sha256((family / row["path"]).read_bytes()).hexdigest()
        != row["sha256"]
    ]
    assert not mismatches, mismatches
    audit = {
        "audit_date": "2026-09-09",
        "source_worktree": str(root),
        "family": str(family.relative_to(root)),
        "method": "Independent standard-library joins and arithmetic; no engine import or network",
        "input_hash_check": {"files_checked": len(manifest["files"]), "mismatches": mismatches},
        "assets": {},
        "qualification": {
            "conditional_accounting_reproduced": True,
            "executable_net_return_certified": False,
            "long_term_strategy_certified": False,
            "note": "OHLC execution and funding mark proxies, historical calendar/access/fee/margin evidence remain limited",
        },
    }

    for asset in ("BTC", "ETH"):
        rates = {
            int(row["fundingTime"]): float(row["realizedRate"])
            for path in raw.glob(f"funding_{asset}_[0-9][0-9].json")
            for row in read_json(path)["data"]
        }
        marks = {
            int(row[0]): tuple(map(float, row[1:5]))
            for path in raw.glob(f"mark_{asset}_[0-9][0-9].json")
            for row in read_json(path)["data"] if row[-1] == "1"
        }
        funding_rows = csv_rows(results / f"{asset.lower()}_funding_events.csv")
        q = float(funding_rows[0]["quantity"])
        funding = sum(q * rates[int(row["ts"])] * marks[int(row["ts"])][0] for row in funding_rows)
        linear = [row for row in orders if row["asset"] == asset and row.get("structure") != "inverse_expiry"]
        pnl = sum(
            num(row, "quote_cash_delta") + num(row, "quote_pnl")
            - (num(row, "quote_fee") if row["leg"] == "linear_perpetual" else 0)
            for row in linear
        ) + funding
        metric = summary["assets"][asset]["perpetual_history_base"]
        error = pnl - metric["net_pnl_usd_proxy"]
        assert abs(error) < 1e-8, (asset, error)
        sell_spot = next(row for row in linear if row["leg"] == "spot" and row["side"] == "sell")
        short = next(row for row in linear if row["leg"] == "linear_perpetual" and row["side"] == "sell")
        exit_q = num(sell_spot, "base_qty")
        lot = float(instruments[asset + "-USDT"]["lotSz"])
        dust = exit_q - math.floor((exit_q + 1e-13) / lot) * lot
        minimum_headroom = math.inf
        breaches = 0
        checked_hours = 0
        for row in csv_rows(results / f"{asset.lower()}_account_hourly.csv"):
            if row.get("event") == "closed_both_legs":
                continue
            ts = int(row["ts"])
            high = marks[ts][1]
            wallet = float(row["isolated_wallet_usdt"])
            headroom = wallet + q * (num(short, "price") - high) - q * high * 0.01
            minimum_headroom = min(minimum_headroom, headroom)
            breaches += headroom <= 0
            checked_hours += 1

        quote_checks = []
        for multiplier in (1, 2):
            quote = next(
                row for row in quotes
                if row["asset"] == asset and row["structure"] == "inverse_expiry"
                and row["round"] == "0" and int(row["cost_multiplier"]) == multiplier
            )
            spot = read_json(raw / f"book_r0_{asset}-USDT.json")["data"][0]
            future = read_json(raw / f"book_r0_{quote['instrument']}.json")["data"][0]
            contracts = float(quote["contracts"])
            notional = float(quote["face_notional_usd"])
            gross = float(quote["spot_gross_qty"])
            spot_fee = 0.001 * multiplier
            future_fee = 0.0005 * multiplier
            slip = 0.0002 * multiplier
            s = depth_price(spot["asks"], gross) * (1 + slip)
            f = depth_price(future["bids"], contracts, inverse=True) * (1 - slip)
            terminal = (float(spot["asks"][0][0]) + float(spot["bids"][0][0])) / 2
            coins = gross * (1 - spot_fee) - notional / f * future_fee
            coins += notional * (1 / terminal - 1 / f) - notional / terminal * 0.0001 * multiplier
            ending = 10000 - gross * s + coins * terminal * (1 - spot_fee) * (1 - slip)
            quote_error = ending - 10000 - float(quote["conditional_flat_terminal_net_usd"])
            assert abs(quote_error) < 1e-8, (asset, multiplier, quote_error)
            quote_checks.append({
                "cost_multiplier": multiplier,
                "contracts": contracts,
                "usd_face_notional": notional,
                "spot_entry_depth_vwap": s,
                "inverse_entry_harmonic_vwap": f,
                "conditional_terminal_net_usd": ending - 10000,
                "difference_from_report_usd": quote_error,
            })

        audit["assets"][asset] = {
            "funding_events": len(funding_rows),
            "negative_funding_events": sum(rates[int(row["ts"])] < 0 for row in funding_rows),
            "funding_rebuilt_usdt_proxy": funding,
            "perpetual_net_rebuilt_usd_proxy": pnl,
            "difference_from_report_usd": error,
            "final_equity_rebuilt_usd_proxy": 10000 + pnl,
            "simple_annualized_total_capital_pct_reported": metric["simple_annualized_return_pct"],
            "net_using_reported_funding_low": metric["net_pnl_usd_proxy"] - funding + metric["funding_lower_bound_usdt"],
            "net_using_reported_funding_high": metric["net_pnl_usd_proxy"] - funding + metric["funding_upper_bound_usdt"],
            "exit_spot_dust_check": {
                "lot": lot,
                "unrounded_dust_quantity": dust,
                "dust_value_usd_proxy": dust * num(sell_spot, "price"),
                "note": "Reported all-coin disposal is not exact executable lot rounding; immaterial to this economic conclusion",
            },
            "mark_high_margin_proxy": {
                "hours_checked": checked_hours,
                "maintenance_rate": 0.01,
                "minimum_headroom_usdt": minimum_headroom,
                "breaches": breaches,
                "note": "Existing hourly mark highs; not actual liquidation timing, fee, or historical tier certification",
            },
            "inverse_round_zero_quotes": quote_checks,
        }

    timing = []
    for directory in ("capture_20260908", "capture_curl_20260908"):
        capture = family / "artifacts/raw" / directory
        for round_number in range(3):
            clock_path = capture / f"book_r{round_number}_clock.json"
            if not clock_path.exists():
                continue
            clock = int(read_json(clock_path)["data"][0]["ts"])
            pairs = []
            for asset in ("BTC", "ETH"):
                spot_ts = int(read_json(capture / f"book_r{round_number}_{asset}-USDT.json")["data"][0]["ts"])
                for instrument in (asset + "-USDT-SWAP", asset + "-USD-261030"):
                    future_ts = int(read_json(capture / f"book_r{round_number}_{instrument}.json")["data"][0]["ts"])
                    skew = abs(spot_ts - future_ts)
                    age = max(abs(clock - spot_ts), abs(clock - future_ts))
                    pairs.append({
                        "asset": asset, "instrument": instrument,
                        "skew_ms": skew, "age_vs_capture_clock_ms": age,
                        "passes_relative_timing_only": skew <= 2000 and age <= 10000,
                    })
            timing.append({
                "capture": directory,
                "round": round_number,
                "passes_relative_timing_only": sum(pair["passes_relative_timing_only"] for pair in pairs),
                "pairs": pairs,
            })
    audit["capture_relative_timing_checks"] = timing
    audit["capture_timing_scope"] = "Relative timestamps only here; this does not rerun absolute local/server clock acceptance"
    audit["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({
        "status": "PASS_CONDITIONAL_ACCOUNTING_WITH_DOCUMENTED_LIMITS",
        "input_files_checked": len(manifest["files"]),
        "assets": {asset: data["perpetual_net_rebuilt_usd_proxy"] for asset, data in audit["assets"].items()},
        "output": str(output),
    }, indent=2))


if __name__ == "__main__":
    main()
