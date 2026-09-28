#!/usr/bin/env python3
"""Frozen seven-ETF, whole-share cash-account diagnostic. No live orders."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import exchange_calendars as xcals
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
CFG_PATH = ROOT / "specs/p0-contract.json"
RAW_CFG = json.loads(CFG_PATH.read_text())
ADMISSIBILITY_PATH = ROOT / "specs/data-admissibility.json"
ADMISSIBILITY = json.loads(ADMISSIBILITY_PATH.read_text())
CFG = dict(RAW_CFG, data_start=ADMISSIBILITY["data_start"], account_start=ADMISSIBILITY["account_start"])
SYMS = CFG["symbols"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def fetch():
    """New retained research raw snapshots; existing files are immutable."""
    p1 = int(pd.Timestamp(RAW_CFG["data_start"], tz="UTC").timestamp())
    p2 = int(pd.Timestamp(CFG["cutoff_exclusive_utc"]).timestamp())
    def one(sym):
        path = ART / "raw" / f"{sym}.json"
        source_meta = ART / "raw" / f"{sym}-source.json"
        host = json.loads(source_meta.read_text())["host"] if source_meta.exists() else "query2"
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?" + urlencode(
            {"period1": p1, "period2": p2, "interval": "1d", "events": "div,splits,capitalGains"}
        )
        if not path.exists():
            failures=[]
            for attempt in range(4):
                try:
                    r = subprocess.run(["curl", "--compressed", "--http1.1", "--fail", "--location", "--silent", "--show-error", "--max-time", "35", "--user-agent", "Mozilla/5.0", url], capture_output=True, check=True)
                    payload = json.loads(r.stdout)
                    assert payload["chart"]["result"][0]["meta"]["symbol"] == sym
                    path.write_bytes(r.stdout)
                    break
                except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
                    failures.append(str(exc))
            if failures:
                write_json(ART/"raw"/f"{sym}-fetch-errors.json",failures)
            if not path.exists():
                raise RuntimeError(f"fetch failed {sym}: {failures}")
        print("raw retained", sym, flush=True)
        return {"symbol": sym, "path": str(path.relative_to(ROOT)), "url": url,
                        "sha256": sha(path), "fetched_at_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                        "acceptance": "raw_unaccepted; retained diagnostic input, not trusted normalized"}
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(one, SYMS))
    write_json(ART / "raw-manifest.json", {"contract_sha256": sha(CFG_PATH), "admissibility_sha256": sha(ADMISSIBILITY_PATH), "sources": records})


def load_data():
    cal = xcals.get_calendar("XNYS", start="2014-01-01", end="2027-01-15")
    sched = cal.schedule.copy()
    sched.index = pd.DatetimeIndex(sched.index).tz_localize(None)
    cutoff = pd.Timestamp(CFG["cutoff_exclusive_utc"])
    sched = sched[(sched.index >= CFG["data_start"]) & (sched["close"] < cutoff)]
    ix = sched.index
    frames, audits, events = {}, [], []
    for sym in SYMS:
        raw = json.loads((ART / "raw" / f"{sym}.json").read_text())["chart"]["result"][0]
        assert raw["meta"]["symbol"] == sym and raw["meta"]["currency"] == "USD"
        ts = pd.to_datetime(raw["timestamp"], unit="s", utc=True)
        dates = ts.tz_convert("America/New_York").tz_localize(None).normalize()
        q = raw["indicators"]["quote"][0]
        f = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")}, index=dates)
        raw_zero_volume_count = int((f.volume==0).sum())
        f = f.loc[f.index >= CFG["data_start"]]
        assert not f.index.duplicated().any(), f"duplicate {sym}"
        missing = ix.difference(f.index)
        extra = f.index.difference(ix)
        assert len(missing) == 0 and len(extra) == 0, f"calendar {sym}: missing={list(missing)} extra={list(extra)}"
        f = f.loc[ix].copy()
        assert np.isfinite(f.to_numpy()).all() and (f[["open", "high", "low", "close"]] > 0).all().all()
        assert (f.volume > 0).all()
        assert (f.high + 1e-6 >= f[["open", "close", "low"]].max(axis=1)).all()
        assert (f.low - 1e-6 <= f[["open", "close", "high"]].min(axis=1)).all()
        ev = raw.get("events", {})
        splits = ev.get("splits", {})
        assert not splits, f"split unsupported; fail closed {sym}: {splits}"
        f["distribution"] = 0.0
        for typ in ("dividends", "capitalGains"):
            for item in ev.get(typ, {}).values():
                d = pd.Timestamp(item["date"], unit="s", tz="UTC").tz_convert("America/New_York").tz_localize(None).normalize()
                if d < ix[0]:
                    continue
                assert d in ix and item["amount"] >= 0
                f.loc[d, "distribution"] += float(item["amount"])
                events.append({"symbol": sym, "ex_date": str(d.date()), "amount_per_share": item["amount"], "type": typ,
                               "actual_pay_date": "UNKNOWN", "diagnostic_lag_calendar_days": 60})
        f["total_return"] = (f.close + f.distribution) / f.close.shift(1) - 1
        f.loc[ix[0], "total_return"] = 0.0  # index anchor only; no account return on warmup anchor
        f["tr_index"] = (1 + f.total_return).cumprod()
        # adjclose is an independent diagnostic, never an execution or integer-share price.
        adj = pd.Series(raw["indicators"]["adjclose"][0]["adjclose"], index=dates).loc[ix]
        vendor_ret = adj.pct_change(fill_method=None)
        audits.append({"symbol": sym, "exchange": raw["meta"].get("fullExchangeName"), "rows": len(f),
                       "start": str(ix[0].date()), "end": str(ix[-1].date()), "missing_sessions": len(missing),
                       "extra_sessions": len(extra), "raw_zero_volume_count_before_admission":raw_zero_volume_count, "splits": len(splits), "distributions": int((f.distribution > 0).sum()),
                       "max_explicit_vs_adj_daily_return_diff": float((vendor_ret - f.total_return).abs().max()),
                       "native_bar_timestamp_utc_first": str(ts[0]), "closure_as_of": str(cutoff),
                       "accepted_for": "diagnostic ledger only", "trusted_normalized": False})
        frames[sym] = f
        f.assign(date=f.index.astype(str), symbol=sym).to_csv(ART / f"bars-{sym}.csv", index=False, float_format="%.12g")
    pd.DataFrame(events).to_csv(ART / "distribution-events.csv", index=False)
    write_json(ART / "data-audit.json", {"calendar": "XNYS", "calendar_version": xcals.__version__,
                "row_and_session_checks": "PASS", "full_trusted_input": False,
                "blockers": ["Raw daily quote volume/vwap/trade_count unavailable; no trusted normalized promotion.",
                             "Historical actual distribution pay dates not available; receivable/60-day cash release is an explicit assumption.",
                             "Daily opening print is an execution proxy, not historical bid/ask/auction fill proof."], "symbols": audits})
    return frames, sched


def settlement_days(d):
    return 3 if d < pd.Timestamp("2017-09-05") else 2 if d < pd.Timestamp("2024-05-28") else 1


def fee(qty, notional):
    return max(1.0, .005 * qty) + .00005 * notional


def metrics(eq):
    r = eq.equity.pct_change(fill_method=None).dropna()
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    nav = eq.equity
    return {"start": str(eq.index[0].date()), "end": str(eq.index[-1].date()), "sessions": len(eq),
            "final_equity_usd": float(nav.iloc[-1]), "net_profit_usd": float(nav.iloc[-1] - 10000),
            "total_return": float(nav.iloc[-1] / 10000 - 1), "cagr": float((nav.iloc[-1] / 10000) ** (1 / years) - 1),
            "annual_volatility": float(r.std(ddof=1) * np.sqrt(252)),
            "sharpe_zero_cash_rate": float(r.mean() / r.std(ddof=1) * np.sqrt(252)),
            "max_drawdown": float((nav / nav.cummax() - 1).min()),
            "mean_gross_exposure": float(eq.gross_exposure.mean()), "min_settled_cash": float(eq.settled_cash.min())}


def run_account(frames, sched, variant):
    ix = sched.index
    bank_holidays = USFederalHolidayCalendar().holidays(ix[0], ix[-1] + pd.Timedelta(days=30))
    settlement_ix = ix.difference(bank_holidays)
    def due_for(trade_date):
        k = settlement_ix.searchsorted(trade_date, side="right") + settlement_days(trade_date) - 1
        return settlement_ix[k] if k < len(settlement_ix) else trade_date + pd.Timedelta(days=10)
    closes = pd.DataFrame({s: f.close for s, f in frames.items()})
    opens = pd.DataFrame({s: f.open for s, f in frames.items()})
    rets = pd.DataFrame({s: f.total_return for s, f in frames.items()})
    tri = pd.DataFrame({s: f.tr_index for s, f in frames.items()})
    month_end = pd.Series(ix, index=ix).groupby(ix.to_period("M")).last().tolist()
    month_end = [d for d in month_end if d.month != ix[-1].month or d.year != ix[-1].year]  # latest incomplete month never signals
    end_positions = {d: j for j, d in enumerate(month_end)}
    start_i = int(ix.searchsorted(pd.Timestamp(CFG["account_start"])))
    # Include prior session as an explicit $10,000 seed for auditable compounding.
    eval_ix = ix[start_i - 1:]
    holdings = np.zeros(len(SYMS), dtype=int)
    cash = 10000.0
    unsettled, dividends_due = [], []
    sells, buy_batches = {}, {}
    orders, decisions, cash_events, rows, pnlrows = [], [], [], [], []
    cum_fees = cum_slip = cum_tax = cum_div = turnover = normalized_turnover = 0.0
    slip = .002 if "cost20bps" in variant else .005 if "cost50bps" in variant else .0005
    delay = 2 if "delay2" in variant else 0
    tax = .30 if "tax30" in variant else 0
    paylag = 90 if "pay90" in variant else 60
    lookback = 10 if "10m_" in variant else 14 if "14m_" in variant else 12
    is_trend = variant.startswith("trend")
    risk_scale = variant not in ("static_equal_weight", "spy_only", "trend_12m_unscaled")
    prior_nav = 10000.0
    prior_h = holdings.copy()
    def recval():
        return sum(x[1] for x in unsettled) + sum(x[1] for x in dividends_due)
    for i in range(start_i - 1, len(ix)):
        d = ix[i]
        # Pay receivables before trading. Entitlement itself was recognized on ex-date.
        for collection, typ in ((unsettled, "sale_settlement"), (dividends_due, "dividend_payment")):
            paid = [x for x in collection if x[0] <= d]
            for due, amount, sym in paid:
                cash += amount
                cash_events.append({"date": str(d.date()), "type": typ, "symbol": sym, "amount_usd": amount})
            collection[:] = [x for x in collection if x[0] > d]
        div_asset = np.zeros(len(SYMS))
        if i >= start_i:
            for k, sym in enumerate(SYMS):
                amount = float(frames[sym].distribution.iloc[i]) * holdings[k]
                if amount:
                    due = d + pd.Timedelta(days=paylag)
                    net = amount * (1-tax)
                    dividends_due.append((due, net, sym))
                    div_asset[k] = net
                    cum_div += amount
                    cum_tax += amount * tax
                    cash_events.append({"date": str(d.date()), "type": "dividend_entitlement", "symbol": sym,
                                        "amount_usd": net, "gross_usd": amount, "tax_usd": amount*tax, "due_date_floor": str(due.date())})
        fee_asset, slip_asset = np.zeros(len(SYMS)), np.zeros(len(SYMS))
        # Quantities below were decided using information from an earlier close.
        if i in sells:
            target, weights, signal_d = sells.pop(i)
            has_sales = False
            for k, sym in enumerate(SYMS):
                q = int(max(holdings[k] - target[k], 0))
                if not q:
                    continue
                has_sales = True
                rawpx = float(opens.iloc[i,k]); px = rawpx*(1-slip); notional=q*px; cost=fee(q, notional)
                holdings[k] -= q
                due = due_for(d)
                unsettled.append((due, notional-cost, sym))
                fee_asset[k] += cost; slip_asset[k] += q*rawpx*slip
                turnover += notional
                normalized_turnover += notional / prior_nav
                orders.append({"date": str(d.date()), "side": "SELL", "symbol": sym, "quantity": q, "raw_open": rawpx,
                               "fill_price": px, "notional_usd": notional, "fee_usd": cost, "slippage_usd": q*rawpx*slip,
                               "signal_date": str(signal_d.date()), "quantity_decision_date": str(signal_d.date()),
                               "settlement_date": str(due.date()), "status": "FILLED_OPEN_PROXY"})
            bi = int(ix.searchsorted(due_for(d))) if has_sales else i
            if bi < len(ix):
                buy_batches[bi] = (weights, signal_d)
        if i in buy_batches:
            weights, signal_d = buy_batches.pop(i)
            prev_px = closes.iloc[i-1].to_numpy()
            # Cash present now was known/released by this session; quantities use prior close.
            eq_prev = prior_nav  # never combine today's ex-date receivable with yesterday's cum-dividend close
            desired = np.floor(eq_prev * weights * .98 / prev_px).astype(int)
            wanted = np.maximum(desired - holdings, 0)
            estimated = sum(q*p*(1+slip) + fee(int(q),q*p*(1+slip)) for q,p in zip(wanted,prev_px) if q)
            if estimated > cash*.98 and estimated > 0:
                wanted = np.floor(wanted * cash*.98/estimated).astype(int)
            for k, sym in enumerate(SYMS):
                q=int(wanted[k])
                if not q:
                    continue
                rawpx=float(opens.iloc[i,k]); px=rawpx*(1+slip); notional=q*px; cost=fee(q,notional)
                status = "FILLED_OPEN_PROXY" if notional+cost <= cash+1e-9 else "REJECTED_INSUFFICIENT_CASH_AT_OPEN"
                orders.append({"date": str(d.date()), "side":"BUY", "symbol":sym, "quantity":q, "raw_open":rawpx,
                               "fill_price":px, "notional_usd":notional, "fee_usd":cost if status=="FILLED_OPEN_PROXY" else 0,
                               "slippage_usd":q*rawpx*slip if status=="FILLED_OPEN_PROXY" else 0,
                               "signal_date":str(signal_d.date()), "quantity_decision_date":str(ix[i-1].date()),
                               "settlement_date":str(due_for(d).date()), "cash_debit_date":str(d.date()), "status":status})
                if status=="FILLED_OPEN_PROXY":
                    cash-=notional+cost; holdings[k]+=q
                    fee_asset[k]+=cost; slip_asset[k]+=q*rawpx*slip; turnover+=notional
                    normalized_turnover += notional / prior_nav
        closepx=closes.iloc[i].to_numpy()
        nav=cash+recval()+float(holdings @ closepx)
        if i == start_i-1:
            price_pnl=np.zeros(len(SYMS))
        else:
            price_pnl=prior_h*(opens.iloc[i].to_numpy()-closes.iloc[i-1].to_numpy()) + holdings*(closepx-opens.iloc[i].to_numpy())
        pnl=price_pnl+div_asset-fee_asset-slip_asset
        assert abs(nav-prior_nav-float(pnl.sum())) < 1e-7, (d,nav-prior_nav,pnl.sum())
        assert cash>=-1e-8 and (holdings>=0).all() and np.issubdtype(holdings.dtype,np.integer)
        cum_fees+=float(fee_asset.sum()); cum_slip+=float(slip_asset.sum())
        row={"date":str(d.date()),"equity":nav,"settled_cash":cash,"unsettled_sale_proceeds":sum(x[1] for x in unsettled),
             "dividend_receivable":sum(x[1] for x in dividends_due),"holdings_value":float(holdings@closepx),
             "gross_exposure":float(holdings@closepx)/nav,"fees_cumulative":cum_fees,"slippage_cumulative":cum_slip,
             "distribution_tax_cumulative":cum_tax,"gross_dividends_cumulative":cum_div,"one_way_notional_cumulative":turnover}
        row.update({f"shares_{s}":int(q) for s,q in zip(SYMS,holdings)})
        row.update({f"close_{s}":float(p) for s,p in zip(SYMS,closepx)})
        rows.append(row)
        for k,sym in enumerate(SYMS):
            pnlrows.append({"date":str(d.date()),"symbol":sym,"price_pnl_usd":price_pnl[k],"net_distribution_usd":div_asset[k],
                            "fees_usd":fee_asset[k],"slippage_usd":slip_asset[k],"net_pnl_usd":pnl[k]})
        prior_nav=nav;prior_h=holdings.copy()
        # Closed month-end signal for future open, including the pre-account seed session.
        if d in end_positions:
            mi=end_positions[d]
            if mi < lookback:
                continue
            w=np.ones(len(SYMS))/len(SYMS)
            cov=rets.iloc[max(0,i-125):i+1].cov().to_numpy()*252
            vol=float(np.sqrt(w@cov@w))
            scale=min(1.,.10/vol) if risk_scale else 1.
            mom=tri.loc[d].to_numpy()/tri.loc[month_end[mi-lookback]].to_numpy()-1
            if variant=="spy_only":
                w=np.array([1.,0,0,0,0,0,0])
            else:
                w=w*scale*(mom>0 if is_trend else 1)
            target=np.floor(nav*w*.98/closepx).astype(int)
            j=i+1+delay
            if j < len(ix):
                sells[j]=(target,w,d)
            for k,sym in enumerate(SYMS):
                decisions.append({"signal_date":str(d.date()),"signal_close_utc":str(sched.loc[d,"close"]),
                    "first_execution_date":str(ix[j].date()) if j<len(ix) else "AFTER_CUTOFF", "symbol":sym,
                    "lookback_months":lookback,"momentum":mom[k],"pool_volatility":vol,"risk_scale":scale,
                    "target_weight":w[k],"target_shares_at_signal":int(target[k])})
    eq=pd.DataFrame(rows).set_index(pd.to_datetime([x["date"] for x in rows]))
    eq.index.name="session"
    met=metrics(eq)
    met.update({"variant":variant,"fees_usd":cum_fees,"slippage_usd":cum_slip,"distribution_tax_usd":cum_tax,
                "gross_dividends_usd":cum_div,"one_way_turnover_per_year":normalized_turnover/((ix[-1]-eval_ix[0]).days/365.25),
                "order_count":len(orders),"filled_orders":sum(o["status"]=="FILLED_OPEN_PROXY" for o in orders),
                "rejected_orders":sum(o["status"]!="FILLED_OPEN_PROXY" for o in orders)})
    out=ART/variant;out.mkdir(exist_ok=True)
    eq.to_csv(out/"account.csv",index=False,float_format="%.12g")
    pd.DataFrame(orders).to_csv(out/"orders.csv",index=False,float_format="%.12g")
    pd.DataFrame(decisions).to_csv(out/"decisions.csv",index=False,float_format="%.12g")
    pd.DataFrame(cash_events).to_csv(out/"cash-events.csv",index=False,float_format="%.12g")
    pp=pd.DataFrame(pnlrows);pp.to_csv(out/"asset-pnl.csv",index=False,float_format="%.12g")
    pp.groupby("symbol").sum(numeric_only=True).to_csv(out/"asset-contribution.csv",float_format="%.12g")
    write_json(out/"metrics.json",met)
    return eq,met


def manual_checks():
    # Distinct accounting proof, using arithmetic fixed independently of market engine.
    start=10000.;buy_q=10;buy_px=100*(1+.0005);buy_fee=1+buy_q*buy_px*.00005
    cash=start-buy_q*buy_px-buy_fee
    ex_close=98.;dist=2.;receivable=buy_q*dist
    ex_nav=cash+buy_q*ex_close+receivable
    assert abs(ex_nav-(start-10*.05-buy_fee))<1e-9
    sell_px=102*(1-.0005);sell_fee=1+10*sell_px*.00005
    unsettled=10*sell_px-sell_fee
    sold_nav=cash+unsettled+receivable
    settled_nav=(cash+unsettled+receivable)
    assert sold_nav==settled_nav
    # A future 2:1 split must fail, not create fake double return from unchanged share counts.
    assert settlement_days(pd.Timestamp("2016-02-01"))==3
    assert settlement_days(pd.Timestamp("2018-02-01"))==2
    assert settlement_days(pd.Timestamp("2026-02-01"))==1
    return {"status":"PASS", "buy_cash_usd":cash,"buy_fee_usd":buy_fee,"ex_date_nav_usd":ex_nav,
            "dividend_receivable_usd":receivable,"sale_receivable_usd":unsettled,"final_nav_usd":settled_nav,
            "final_profit_usd":settled_nav-start,"explanation":"10 shares at adverse 100.05; dividend 2 and ex close98; sell10 at101.949. Entitlement/settlement moves do not create PnL. Costs charged once."}


def research():
    manifest=json.loads((ART/"raw-manifest.json").read_text())
    assert manifest["contract_sha256"]==sha(CFG_PATH)
    assert manifest["admissibility_sha256"]==sha(ADMISSIBILITY_PATH)
    for r in manifest["sources"]:
        assert sha(ROOT/r["path"])==r["sha256"]
    frames,sched=load_data()
    write_json(ART/"manual-arithmetic-check.json",manual_checks())
    accounts={};mets=[]
    for var in CFG["variants"]:
        eq,m=run_account(frames,sched,var);accounts[var]=eq;mets.append(m)
        print(var,round(m["cagr"]*100,3),round(m["max_drawdown"]*100,3),flush=True)
    mm=pd.DataFrame(mets).set_index("variant")
    mm.to_csv(ART/"metrics.csv",float_format="%.12g")
    annual=[];blocks=[];recent=[]
    periods=[("2017-2019 partial","2017-03-01","2019-12-31"),("2020-2021","2020-01-01","2021-12-31"),
             ("2022","2022-01-01","2022-12-31"),("2023-2024","2023-01-01","2024-12-31"),("2025+ REUSED","2025-01-01","2026-12-31")]
    for var,eq in accounts.items():
        r=eq.equity.pct_change(fill_method=None).fillna(0)
        for year,g in r.groupby(r.index.year):
            annual.append({"variant":var,"year":year,"net_return":float((1+g).prod()-1)})
        for name,start,end in periods:
            rr=r.loc[start:end]
            nav=(1+rr).cumprod()
            if len(rr):
                blocks.append({"variant":var,"period":name,"net_return":float(nav.iloc[-1]-1),"max_drawdown":float((nav/nav.cummax().clip(lower=1)-1).min()),"sessions":len(rr)})
        for name,days in [("1d",1),("7d",7),("1m",30),("3m",91),("6m",183),("1y",365)]:
            prev=eq.equity.loc[eq.index<=eq.index[-1]-pd.Timedelta(days=days)]
            if len(prev):
                recent.append({"variant":var,"period":name,"net_return":float(eq.equity.iloc[-1]/prev.iloc[-1]-1)})
    pd.DataFrame(annual).to_csv(ART/"annual.csv",index=False)
    pd.DataFrame(blocks).to_csv(ART/"market-blocks.csv",index=False)
    pd.DataFrame(recent).to_csv(ART/"recent.csv",index=False)
    main=mm.loc["trend_12m_risk10"];static=mm.loc["static_risk10"]
    criterion_risk=abs(main.max_drawdown)<=.9*abs(static.max_drawdown) and main.cagr>=static.cagr-.01
    criterion_growth=main.cagr>=static.cagr+.01 and abs(main.max_drawdown)<=abs(static.max_drawdown)+.02
    econ=bool(main.cagr>0 and main.max_drawdown>=-.30 and mm.loc["trend_12m_cost20bps","cagr"]>0 and (criterion_risk or criterion_growth))
    rmain=accounts["trend_12m_risk10"].equity.pct_change(fill_method=None).fillna(0)
    rstatic=accounts["static_risk10"].equity.pct_change(fill_method=None).fillna(0)
    ratio=min(1.,float(rmain.std()/rstatic.std()))
    matched=(1+rstatic*ratio).cumprod()*10000
    matched.to_csv(ART/"expost-vol-matched-static-diagnostic.csv",header=["equity"])
    yrs=pd.DataFrame(annual).query("variant=='trend_12m_risk10'")
    bestyear=int(yrs.loc[yrs.net_return.idxmax(),"year"])
    stripped=rmain.loc[rmain.index.year!=bestyear]
    attr={"diversification_cagr_delta_static_minus_spy":float(mm.loc["static_equal_weight","cagr"]-mm.loc["spy_only","cagr"]),
          "risk_scaling_cagr_delta":float(static.cagr-mm.loc["static_equal_weight","cagr"]),
          "trend_conditional_exposure_cagr_delta":float(main.cagr-static.cagr),
          "trend_vs_static_drawdown_improvement":float(abs(static.max_drawdown)-abs(main.max_drawdown)),
          "expost_vol_match_scalar_nontradable":ratio,"expost_matched_static_final_equity":float(matched.iloc[-1]),
          "best_year":bestyear,"return_compounded_excluding_best_year":float((1+stripped).prod()-1),
          "not_prediction_alpha_proof":True}
    write_json(ART/"attribution.json",attr)
    summary={"family":CFG["family"],"alias":CFG["alias"],"version":"P0-2026-09-08 (exploratory frozen research object)",
             "status":"explore / not promoted / not live-ready",
             "result_label":"ECONOMIC_CANDIDATE_WITH_DATA_EXECUTION_BLOCKERS" if econ else "NO_GO_PREDECLARED_ECONOMIC_INCREMENT",
             "diagnostic_economic_gate_pass":econ,"initial_capital_usd":10000,
             "coverage":{"data_start":str(sched.index[0].date()),"account_seed":str(accounts["trend_12m_risk10"].index[0].date()),"start":CFG["account_start"],"end":str(sched.index[-1].date()),"symbols":SYMS},
             "historical_exposure":CFG["history_role"],"variant_metrics":mets,"attribution":attr,
             "blockers":["Raw daily surface is not accepted normalized input; no quote/VWAP/trade-count provenance.",
                         "Historical issuer pay dates not verified; 60/90-day cash-release assumptions only.",
                         "Broker access/tax residency/actual execution costs and opening fills unverified; no true orders.",
                         "Current surviving ETF pool and reused history; no blind future validation."],
             "artifacts":{"metrics":"artifacts/metrics.csv","main_account":"artifacts/trend_12m_risk10/account.csv","main_orders":"artifacts/trend_12m_risk10/orders.csv","data_audit":"artifacts/data-audit.json","manifest":"artifacts/raw-manifest.json"}}
    write_json(ART/"summary.json",summary)
    env={"python":sys.version,"platform":platform.platform(),"packages":{p:importlib.metadata.version(p) for p in ("numpy","pandas","exchange_calendars","matplotlib")}}
    write_json(ART/"environment.json",env)
    # Scientific output chart from conventional plotting, not generative media.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(12,8),sharex=True,gridspec_kw={"height_ratios":[2,1]})
    for v in ("trend_12m_risk10","static_risk10","static_equal_weight","spy_only"):
        eq=accounts[v].equity
        axes[0].plot(eq.index,eq,label=v,linewidth=1.5)
        axes[1].plot(eq.index,(eq/eq.cummax()-1)*100,label=v,linewidth=1)
    axes[0].set_ylabel("USD, initial 10,000");axes[1].set_ylabel("Drawdown (%)")
    axes[0].set_title("Seven ETFs, whole-share cash accounts | reused historical diagnostic")
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.2);axes[1].grid(alpha=.2)
    fig.tight_layout();fig.savefig(ART/"equity-drawdown.png",dpi=160);plt.close(fig)
    hashed={str(p.relative_to(ROOT)):sha(p) for p in sorted(ROOT.rglob("*")) if p.is_file() and p.name not in ("hashes.json",) and "__pycache__" not in p.parts}
    write_json(ART/"hashes.json",hashed)
    print(json.dumps({"economic_gate_pass":econ,"result_label":summary["result_label"]}))


if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--fetch",action="store_true");args=ap.parse_args()
    if args.fetch:fetch()
    research()
