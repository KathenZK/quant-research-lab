"""A fixed synthetic wiring exercise, not a market performance experiment."""
from pathlib import Path
import json

from strategy_lab.research.accounting import LinearAccount
from strategy_lab.research.portfolio import Score, rank_targets, combine_targets, delta_orders


def main():
    root = Path(__file__).resolve().parents[1] / "artifacts/implementation-20260925"
    ts = "2026-09-01T00:00:00Z"
    a = LinearAccount(10000)
    ranking = rank_targets([Score("BTC", 2, ts), Score("ETH", 1, ts)], decision_at=ts, slots=1)
    targets = combine_targets({"trend": ranking, "hedge": {"BTC": -.5, "ETH": .5}}, {"trend": .6, "hedge": .4})
    plan = delta_orders(targets=targets, quantities={}, marks={"BTC": 100, "ETH": 50}, equity=a.equity, fee_rate=.001)
    steps = []
    for i, order in enumerate(plan["execution_sequence"]):
        symbol = order["symbol"]
        # Demonstrate partial fill, restart and completion using actual quantities.
        for part in [1, 2]:
            a.apply({"id": f"entry:{i}:{part}", "kind": "fill", "ts": ts, "symbol": symbol,
                     "quantity": order["quantity"] / 2, "price": {"BTC": 100, "ETH": 50}[symbol],
                     "fee_rate": .001, "marks": {"BTC": 100, "ETH": 50}})
            a = LinearAccount.restore(a.snapshot())
            steps.append(a.state())
    later = "2026-09-02T00:00:00Z"
    for s, rate in [("BTC", .001), ("ETH", -.002)]:
        a.apply({"id": "funding:" + s, "kind": "funding", "ts": later, "symbol": s,
                 "rate": rate, "settlement_type": "regular", "marks": {"BTC": 110, "ETH": 45}})
    close = delta_orders(targets={}, quantities={s: p["quantity"] for s, p in a.positions.items()},
                         marks={"BTC": 110, "ETH": 45}, equity=a.equity, fee_rate=.001)
    for order in close["execution_sequence"]:
        s = order["symbol"]
        a.apply({"id": "exit:" + s, "kind": "fill", "ts": later, "symbol": s,
                 "quantity": order["quantity"], "price": {"BTC": 110, "ETH": 45}[s], "fee_rate": .001,
                 "marks": {"BTC": 110, "ETH": 45}})
    assert not a.positions
    result = {"status": "SYNTHETIC_ACCOUNT_WIRING_PASS", "market_data_used": False,
              "alpha_evidence": False, "synthetic_prices_not_actual_BTC_ETH_quotes": True,
              "initial_cash": 10000, "net_targets": targets, "entry_plan": plan,
              "partial_fill_states": steps, "final_account": a.state(), "snapshot": a.snapshot()}
    with (root / "synthetic-joint-account.json").open("x") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({"status": result["status"], "targets": targets, "final_account": a.state()}, indent=2))


if __name__ == "__main__":
    main()
