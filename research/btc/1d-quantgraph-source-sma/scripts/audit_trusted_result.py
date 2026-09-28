"""Independent SMA signal/ledger arithmetic check; no strategy selection."""

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from strategy_lab.knowledge.market_dataset import read_market_dataset
from strategy_lab.knowledge.market_contract import sha


def audit(contract_path, manifest_path, result_dir):
    bars, contract, _, _, _ = read_market_dataset(contract_path, manifest_path)
    if contract["rule_ast"]["signal"] != "PRICE_SMA":
        raise ValueError("This independent audit covers the frozen SMA family only")
    cfg = contract["engine_config"]
    root = Path(result_dir)
    results = []
    for trial, parameters in enumerate(contract["parameter_grid"]):
        account = pd.read_csv(root / f"account-{trial}.csv")
        fills = pd.read_csv(root / f"fills-{trial}.csv")
        trades = pd.read_csv(root / f"trades-{trial}.csv")
        account.ts = pd.to_datetime(account.ts, utc=True)
        fills.ts = pd.to_datetime(fills.ts, utc=True)
        bar_index = {t: i for i, t in enumerate(bars.ts)}
        cash, qty, previous = cfg["initial_cash"], 0.0, cfg["initial_cash"]
        total_fee, total_slip, max_error = 0.0, 0.0, 0.0
        n = int(parameters[0])
        for row in account.itertuples(index=False):
            i = bar_index[row.ts]
            # Slice stops before the execution bar: independently check timing.
            desired = i >= n and bars.close.iloc[i - 1] > np.mean(
                bars.close.iloc[i - n : i]
            )
            was_long = qty > 1e-12
            todays = fills[fills.ts == row.ts]
            signal_fills = todays[todays.reason == "prior_closed_signal"]
            expected = [] if desired == was_long else ["buy" if desired else "sell"]
            if signal_fills.side.tolist() != expected:
                raise ValueError("Prior closed SMA / next-open fills disagree")
            fee_sum = slip_sum = 0.0
            for fill in todays.itertuples(index=False):
                if fill.reason not in {"prior_closed_signal", "end_of_study"}:
                    raise ValueError("Unexpected execution reason")
                terminal = fill.reason == "end_of_study"
                if terminal and (i != len(bars) - 1 or fill.side != "sell"):
                    raise ValueError("Terminal liquidation outside study boundary")
                raw = bars.close.iloc[i] if terminal else bars.open.iloc[i]
                expected_price = raw * (
                    1 + (1 if fill.side == "buy" else -1) * cfg["slippage_bps"] / 10000
                )
                expected_fee = fill.qty * fill.price * cfg["fee_bps"] / 10000
                if not np.isclose(
                    fill.price, expected_price, rtol=1e-12
                ) or not np.isclose(fill.fee, expected_fee, rtol=1e-12):
                    raise ValueError("Fill price/fee differs from frozen nonzero cost")
                if fill.side == "buy":
                    cash -= fill.qty * fill.price + fill.fee
                    qty += fill.qty
                else:
                    cash += fill.qty * fill.price - fill.fee
                    qty -= fill.qty
                fee_sum += fill.fee
                slip_sum += fill.qty * abs(fill.price - raw)
            equity = cash + qty * bars.close.iloc[i]
            max_error = max(max_error, abs(equity - row.equity))
            if not np.allclose(
                [equity, equity / previous - 1, fee_sum, slip_sum],
                [row.equity, row.return_net, row.fee, row.slippage_cost],
                rtol=1e-10,
                atol=1e-8,
            ):
                raise ValueError("Account ledger does not reconcile")
            previous = equity
            total_fee += fee_sum
            total_slip += slip_sum
        if abs(qty) > 1e-10 or not np.isclose(
            cash - cfg["initial_cash"], trades.pnl.sum(), rtol=1e-10, atol=1e-8
        ):
            raise ValueError("Terminal cash / whole-trade PnL mismatch")
        results.append(
            dict(
                parameters=parameters,
                status="PASS",
                fills=len(fills),
                closed_trades=len(trades),
                max_equity_error=max_error,
                fees=total_fee,
                slippage=total_slip,
            )
        )
    report = dict(
        status="PASS",
        method="Independent prior-close SMA slices and cash/quantity ledger reconstruction",
        code_sha256=sha(__file__),
        contract_sha256=sha(contract_path),
        manifest_sha256=sha(manifest_path),
        trials=results,
    )
    (root / "ledger-reconciliation.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for arg in ("contract", "manifest", "result-dir"):
        p.add_argument("--" + arg, required=True, type=Path)
    a = p.parse_args()
    print(json.dumps(audit(a.contract, a.manifest, a.result_dir)))
