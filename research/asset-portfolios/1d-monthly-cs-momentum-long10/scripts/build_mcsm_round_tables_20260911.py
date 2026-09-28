"""Normalize audited research outputs for the user workbook; no market-data reads."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

FAMILY = Path(__file__).resolve().parents[1]
ROUND = FAMILY / "artifacts/drawdown-frequency-round-20260911"
OLD = FAMILY / "artifacts/mechanism-round-20260910/single-exit"
OUT = ROUND / "delivery/workbook-data.json"
NAMES = {"baseline": "B0 原月度", "single_exit": "S1 逐币退出", "x5": "X5 首次卖弱五币",
         "x10": "X10 首次全退出", "B0": "B0 同期原月度", "M28": "M28 月换28日榜",
         "W28": "W28 周换28日榜", "W7": "W7 周换7日榜"}
PRICE = "不计资金费的价格对照"
FUNDED = "观察资金费估算，非精确净收益"
WEEKLY = "未计资金费，完整净收益不可用"


def read_json(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    if value is None or pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def short_names(values):
    if isinstance(values, str):
        values = values.split(", ")
    return ", ".join(str(x).split("/")[0] for x in values)


def main():
    if OUT.exists():
        raise FileExistsError(OUT)
    d, b, w = ROUND / "drawdown", ROUND / "broader-exit", ROUND / "weekly"
    for folder, mapping in ((d, "files_sha256"), (b, "source_sha256")):
        for relative, expected in read_json(folder / "summary.json")[mapping].items():
            if sha(folder / relative) != expected:
                raise ValueError(f"changed audited input: {folder / relative}")
    for name in ("drawdown-summary.json", "breadth-summary.json"):
        if not read_json(ROUND / "independent-audit" / name)["status"].startswith("PASS"):
            raise ValueError("independent audit not complete")
    independent_weekly = read_json(ROUND / "independent-audit/weekly-summary.json")
    if len(independent_weekly["results"]) != 8 or any(r["status"] not in {
        "INDEPENDENT_PRICE_ACCOUNT_ALL_NAV_TRADES_MONTHS_YEARS_PASS",
        "CONFIRMED_FIRST_MISSING_INPUT_NO_FULL_RETURN"} for r in independent_weekly["results"]):
        raise ValueError("weekly independent adjudication incomplete")
    for relative, expected in read_json(ROUND / "independent-audit/weekly-started.json")["input_sha256"].items():
        if sha(FAMILY.parents[2] / relative) != expected:
            raise ValueError(f"weekly audit source changed: {relative}")
    summary, years, months, legs, periods, sources = [], [], [], [], [], []
    old_metrics = {f"{m['scenario']}-{m['strategy']}-4bp": m for m in read_json(OLD / "summary.json")["results"]
                   if m["slippage_rate"] == .0004}
    dm = pd.read_parquet(d / "monthly-details.parquet")
    dy = pd.read_parquet(d / "yearly-details.parquet")
    dl = pd.read_parquet(d / "holding-legs.parquet")
    bm = read_json(b / "summary.json")["results"]
    for account, metric in old_metrics.items():
        scenario, strategy, slip = metric["scenario"], metric["strategy"], metric["slippage_rate"]
        fund_label = PRICE if scenario == "price_only" else FUNDED
        shared = {"group": "76个月退出比较", "strategy": NAMES[strategy], "funding": fund_label, "slippage": slip}
        summary.append({**shared, "start": "2020-03-01T00:15Z", "end": "2026-07-01T00:15Z",
                        "initial": 100000., "final": metric["final_equity"], "total_return": metric["total_return"],
                        "cagr": metric["cagr_365_25"], "mdd": metric["max_drawdown_daily_and_rebalance"],
                        "price_pnl": metric["price_pnl_usdt"], "funding_pnl": metric["funding_pnl_usdt"] if scenario != "price_only" else None,
                        "fees": metric["fees_usdt"], "slip_cost": metric["slippage_usdt"], "status": "历史回放完成；不实盘"})
        for r in dm.loc[dm.account.eq(account)].to_dict("records"):
            months.append({**shared, "month": r["month"], "start_equity": r["start_equity"], "end_equity": r["end_equity"],
                           "pnl": r["pnl"], "return": r["return"], "price_pnl": r["price_pnl"],
                           "funding_pnl": r["funding_pnl"] if scenario != "price_only" else None,
                           "fees": r["fees"], "slip_cost": r["slippage"], "held": r["holdings_text"],
                           "initial_names": r["holdings_text"], "exits": r["early_exits"],
                           "start": r["month"] + pd.Timedelta(minutes=15),
                           "end": r["month"] + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15),
                           "time_rule": "换仓后至下月换仓后；含下一边界费用"})
        for r in dy.loc[dy.account.eq(account)].to_dict("records"):
            years.append({**shared, **{k: r[k] for k in ("year", "months", "start_equity", "end_equity", "pnl", "return", "price_pnl", "fees")},
                          "funding_pnl": r["funding_pnl"] if scenario != "price_only" else None, "slip_cost": r["slippage"]})
        for r in dl.loc[dl.account.eq(account)].to_dict("records"):
            legs.append({**shared, "month": r["month"], "symbol": r["symbol"].split("/")[0],
                         "entry": r["entry_ts"], "exit": r["actual_exit_ts"], "quantity": r["initial_quantity"],
                         "entry_price": r["entry_price"], "exit_price": r["exit_price"], "price_pnl": r["price_pnl"],
                         "funding_pnl": r["funding_pnl"] if scenario != "price_only" else None,
                         "exit_kind": r["exit_reason"], "exit_fee": r["direct_exit_fees"], "exit_slip": r["direct_exit_slippage"]})
    for metric in bm:
        scenario, strategy, slip = metric["scenario"], metric["strategy"], metric["slippage_rate"]
        folder = b / f"{scenario}-{strategy}-{round(slip * 10000)}bp"
        shared = {"group": "76个月退出比较", "strategy": NAMES[strategy], "funding": PRICE if scenario == "price_only" else FUNDED, "slippage": slip}
        summary.append({**shared, "start": "2020-03-01T00:15Z", "end": "2026-07-01T00:15Z", "initial": 100000.,
                        "final": metric["final_equity"], "total_return": metric["total_return"], "cagr": metric["cagr_365_25"],
                        "mdd": metric["max_drawdown_daily_and_rebalance"], "price_pnl": metric["price_pnl_usdt"],
                        "funding_pnl": metric["funding_pnl_usdt"] if scenario != "price_only" else None,
                        "fees": metric["fees_usdt"], "slip_cost": metric["slippage_usdt"], "status": "历史回放完成；不实盘"})
        for r in pd.read_parquet(folder / "monthly.parquet").to_dict("records"):
            months.append({**shared, "month": r["month"], "start_equity": r["account_start_equity"], "end_equity": r["account_end_equity"],
                           "pnl": r["pnl_usdt"], "return": r["account_return"], "price_pnl": r["price_pnl_usdt"],
                           "funding_pnl": r["funding_pnl_usdt"] if scenario != "price_only" else None,
                           "fees": r["fee_usdt"], "slip_cost": r["slippage_usdt"], "held": r["holdings"],
                           "initial_names": r["holdings"], "exits": r["early_exit_count"],
                           "start": r["month"] + pd.Timedelta(minutes=15),
                           "end": r["month"] + pd.offsets.MonthBegin(1) + pd.Timedelta(minutes=15),
                           "time_rule": "换仓后至下月换仓后；含下一边界费用"})
        for r in pd.read_parquet(folder / "yearly.parquet").to_dict("records"):
            years.append({**shared, "year": r["year"], "months": r["months"], "start_equity": r["start_equity_usdt"], "end_equity": r["end_equity_usdt"],
                          "pnl": r["pnl_usdt"], "return": r["account_return"], "price_pnl": r["price_pnl_usdt"],
                          "funding_pnl": r["funding_pnl_usdt"] if scenario != "price_only" else None, "fees": r["fee_usdt"], "slip_cost": r["slippage_usdt"]})
        for r in pd.read_parquet(folder / "holding-legs.parquet").to_dict("records"):
            legs.append({**shared, "month": r["month"], "symbol": r["symbol"].split("/")[0], "entry": r["entry_ts"],
                         "exit": r["actual_exit_ts"], "quantity": r["quantity"], "entry_price": r["entry_price"], "exit_price": r["exit_price"],
                         "price_pnl": r["price_pnl_usdt"], "funding_pnl": r["funding_pnl_usdt"] if scenario != "price_only" else None,
                         "exit_kind": r["exit_kind"], "exit_fee": r["early_or_terminal_fee"], "exit_slip": r["early_or_terminal_slippage"]})
    wh = pd.read_parquet(w / "holding-windows.parquet")
    plan = read_json(w / "execution-plan.json")
    if sha(w / "holding-windows.parquet") != plan["holding_windows_sha256"]:
        raise ValueError("weekly selection plans changed")
    failed_plans_added = set()
    weekly_results = read_json(w / "summary.json")["accounts"]
    for metric in weekly_results:
        strategy, slip = metric["strategy"], metric["slippage_rate"]
        folder = w / f"{strategy}-{round(slip * 10000)}bp"
        shared = {"group": "75个月频率比较", "strategy": NAMES[strategy], "funding": WEEKLY, "slippage": slip}
        summary.append({**shared, "start": "2020-04-01T00:15Z", "end": "2026-07-01T00:15Z", "initial": 100000.,
                        "final": metric.get("final_equity"), "total_return": metric.get("total_return"), "cagr": metric.get("cagr_365_25"),
                        "mdd": metric.get("max_drawdown_common_grid"), "price_pnl": metric.get("price_pnl_usdt"), "funding_pnl": None,
                        "fees": metric.get("fees_usdt"), "slip_cost": metric.get("slippage_usdt"),
                        "status": ("价格回放完成；未计资金费，不能实盘" if metric.get("total_return") is not None
                                   else "持仓估值/结算输入缺失，全期收益不可用：" + metric.get("reason", metric["status"]))})
        if metric.get("total_return") is None:
            if strategy not in failed_plans_added:
                for entry, group in wh.loc[wh.strategy.eq(strategy)].groupby("entry_ts", sort=True):
                    if group.scheduled_exit_ts.nunique() != 1 or len(group) != 10:
                        raise ValueError("failed-account selection plan not a ten-name period")
                    periods.append({**shared, "slippage": None, "entry": entry,
                                    "exit": group.scheduled_exit_ts.iloc[0], "start_equity": None,
                                    "end_equity": None, "pnl": None, "return": None,
                                    "holdings": short_names(group.sort_values("rank").symbol),
                                    "status": "仅事前选币计划；回放未完成，不能当实际交易/收益"})
                failed_plans_added.add(strategy)
            continue
        nav = pd.read_parquet(folder / "nav.parquet")
        previous = {"price_pnl": 0., "fees": 0., "slippage": 0.}
        for r in pd.read_parquet(folder / "monthly.parquet").to_dict("records"):
            endrow = nav.loc[nav.ts.eq(r["period_end"])].iloc[-1]
            parts = {field: float(endrow[field] - previous[field]) for field in ("price_pnl", "fees", "slippage")}
            previous = endrow
            months.append({**shared, "month": r["month"], "start_equity": r["start_equity"], "end_equity": r["end_equity"],
                           "pnl": r["pnl_usdt"], "return": r["return"], "price_pnl": parts["price_pnl"], "funding_pnl": None,
                           "fees": parts["fees"], "slip_cost": parts["slippage"], "held": short_names(r["held_symbols_during_month"]),
                           "initial_names": short_names(r["month_start_symbols"]), "exits": None,
                           "start": r["period_start"], "end": r["period_end"], "time_rule": "自然月00:00估值；首尾00:15"})
        mtable = pd.DataFrame([r for r in months if all(r[k] == shared[k] for k in shared)])
        for r in metric["yearly"]:
            yrows = mtable.loc[pd.to_datetime(mtable.month, utc=True).dt.year.eq(r["year"])]
            years.append({**shared, "year": r["year"], "months": r["months"], "start_equity": r["start_equity"], "end_equity": r["end_equity"],
                          "pnl": r["pnl_usdt"], "return": r["return"], "price_pnl": yrows.price_pnl.sum(), "funding_pnl": None,
                          "fees": yrows.fees.sum(), "slip_cost": yrows.slip_cost.sum()})
        for r in pd.read_parquet(folder / "periods.parquet").to_dict("records"):
            names = wh.loc[wh.strategy.eq(strategy) & wh.entry_ts.eq(r["entry_ts"])].sort_values("rank").symbol
            periods.append({**shared, "entry": r["entry_ts"], "exit": r["exit_ts"], "start_equity": r["start_equity"],
                            "end_equity": r["end_equity"], "pnl": r["end_equity"] - r["start_equity"],
                            "return": r["return"], "holdings": short_names(names),
                            "status": "已完成价格回放；未计资金费"})
        terminal_frame = pd.read_parquet(folder / "terminals.parquet")
        terminal_fees = terminal_frame.set_index(["ts", "symbol"]).fee.to_dict() if len(terminal_frame) else {}
        price_legs = pd.read_parquet(folder / "leg-price-pnl.parquet")
        if not np.isclose(price_legs.period_price_pnl_usdt.sum(), metric["price_pnl_usdt"], atol=1e-4, rtol=0):
            raise ValueError("weekly whole-leg price cash does not reproduce the account")
        for r in price_legs.to_dict("records"):
            legs.append({**shared, "month": r["entry_ts"].replace(day=1, hour=0, minute=0, second=0),
                         "symbol": r["symbol"].split("/")[0], "entry": r["entry_ts"], "exit": r["exit_ts"],
                         "quantity": r["account_entry_quantity"], "entry_price": r["entry_reference_price"],
                         "exit_price": r["exit_reference_price"], "price_pnl": r["period_price_pnl_usdt"], "funding_pnl": None,
                         "exit_kind": "条件终止估价" if r["terminal"] else "计划换仓；整段持仓损益",
                         "exit_fee": terminal_fees.get((r["exit_ts"], r["symbol"]), 0.), "exit_slip": 0.})
    for folder in (d, b, w, ROUND / "independent-audit"):
        for p in sorted(folder.glob("*summary.json")):
            sources.append({"file": str(p.relative_to(FAMILY)), "sha256": sha(p)})
    # Reconcile imported snapshots before authoring a workbook.
    mtable = pd.DataFrame(months)
    for row in summary:
        if row["final"] is None:
            continue
        selected = mtable
        for key in ("group", "strategy", "funding", "slippage"):
            selected = selected.loc[selected[key].eq(row[key])]
        if not np.isclose(selected.pnl.sum(), row["final"] - 100000., atol=1e-4, rtol=0):
            raise ValueError("workbook monthly cash cannot reproduce final account")
        if not np.isclose(np.prod(1 + selected["return"]) - 1, row["total_return"], atol=1e-9, rtol=0):
            raise ValueError("workbook monthly compounding mismatch")
    payload = {"summary": summary, "yearly": years, "monthly": months, "legs": legs, "periods": periods,
               "drawdown": read_json(d / "window-summary.json"), "sources": sources,
               "counts": {"accounts": len(summary), "complete_accounts": sum(r["final"] is not None for r in summary),
                          "blocked_accounts": sum(r["final"] is None for r in summary),
                          "yearly": len(years), "monthly": len(months), "legs": len(legs), "periods": len(periods),
                          "completed_periods": sum(r["pnl"] is not None for r in periods),
                          "planned_only_periods": sum(r["pnl"] is None for r in periods)},
               "contract_sha256": "aa38d87cf3cb374d4f587faf3660586950986bfa2a25813e851d65c28862d2d4"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("x") as stream:
        json.dump(clean(payload), stream, ensure_ascii=False, allow_nan=False)
    print(json.dumps(payload["counts"]))


if __name__ == "__main__":
    main()
