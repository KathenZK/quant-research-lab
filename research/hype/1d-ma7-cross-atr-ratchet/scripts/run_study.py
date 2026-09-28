"""Run the finite preregistered study against pinned startup-returned artifacts."""
from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd

from engine import Config, features, simulate

BASE = Path(__file__).resolve().parents[1]
INPUT = BASE / "artifacts/inputs_20260909"
OUT = BASE / "artifacts/results_20260909"
INPUT_CHECKSUM_SHA256 = "a402fabb987f1f1836c56913cbc4a8d8e0d5a781d4bf50be851891864091c9d5"
INPUT_REQUIRED_FILES = frozenset({
    "hourly.parquet", "daily.parquet", "funding_observed_unverified.parquet",
    "price_request_1h.json", "price_request_1d.json", "startup_1h.json", "startup_1d.json",
    "startup_net_rejected.json", "data_audit.json", "funding_audit.json",
    "funding_coverage_segments.parquet", "funding_coverage_expected_events.parquet",
})
INPUT_SYMBOL = "HYPE/USDT:USDT"
INPUT_START = "2025-05-31T00:00:00Z"
INPUT_END = "2026-09-05T00:00:00Z"
INPUT_BUNDLE_PIN = {
    "bundle_id": "binance.v3.research_inputs.v2",
    "bundle_path": "research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json",
    "bundle_sha256": "d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs():
    if digest(INPUT / "checksums.json") != INPUT_CHECKSUM_SHA256:
        raise ValueError("Pinned input checksum manifest changed")
    expected = json.loads((INPUT / "checksums.json").read_text())
    if set(expected) != INPUT_REQUIRED_FILES:
        raise ValueError("Pinned input checksum manifest has missing or unexpected files")
    for name, checksum in expected.items():
        if digest(INPUT / name) != checksum:
            raise ValueError(f"Pinned input changed: {name}")
    for timeframe, backward, rows in [("1h", 1, 11088), ("1d", 29, 462)]:
        receipt = json.loads((INPUT / f"startup_{timeframe}.json").read_text())
        request = {
            "schema_version": 1, **INPUT_BUNDLE_PIN, "mode": "price_diagnostic",
            "timeframe": timeframe, "symbols": [INPUT_SYMBOL],
            "start": INPUT_START, "end": INPUT_END, "gap_policy": "reject",
            "asset_policy": "crypto_only", "backward_bars": backward, "forward_bars": 0,
        }
        if (receipt.get("status") != "PRICE_DIAGNOSTIC_INPUTS_VERIFIED"
                or receipt.get("price_inputs_verified") is not True
                or receipt.get("funding_window_verified") is not False
                or any(receipt.get(key) != value for key, value in INPUT_BUNDLE_PIN.items())
                or receipt.get("request") != request
                or json.loads((INPUT / f"price_request_{timeframe}.json").read_text()) != request):
            raise ValueError(f"Invalid startup status or pinned request identity: {timeframe}")
        symbols = receipt.get("symbols", {})
        stats = symbols.get(INPUT_SYMBOL, {})
        if (set(symbols) != {INPUT_SYMBOL} or stats.get("rows") != rows
                or stats.get("expected_grid_rows") != rows
                or stats.get("missing_grid_rows") != 0 or stats.get("ineligible_rows") != 0
                or stats.get("eligible_segments") != 1
                or stats.get("complete_windows") != rows - backward + 1):
            raise ValueError(f"Invalid startup window statistics: {timeframe}")
    h = pd.read_parquet(INPUT / "hourly.parquet").rename(columns={"ts": "timestamp"})
    d = pd.read_parquet(INPUT / "daily.parquet").rename(columns={"ts": "timestamp"})
    f = pd.read_parquet(INPUT / "funding_observed_unverified.parquet").rename(columns={"ts": "timestamp"})
    for frame, timeframe, backward in [(h, "1h", 1), (d, "1d", 29)]:
        expected_grid = pd.date_range(INPUT_START, INPUT_END, freq=timeframe, inclusive="left")
        mask = pd.Series(frame.index >= backward - 1, index=frame.index)
        if (not pd.DatetimeIndex(frame.timestamp).equals(expected_grid)
                or not frame.symbol.eq(INPUT_SYMBOL).all()
                or not frame.timeframe.eq(timeframe).all()
                or not frame.exchange.eq("binance").all() or not frame.market_type.eq("perp").all()
                or frame.eligible.dtype != bool or not frame.eligible.all()
                or frame.is_closed.dtype != bool or not frame.is_closed.all()
                or frame.research_segment_id.nunique() != 1
                or frame.research_window_valid.dtype != bool
                or not frame.research_window_valid.equals(mask)):
            raise ValueError(f"Invalid pinned price frame or feature mask: {timeframe}")
    if (len(f) != 2771 or not f.symbol.eq(INPUT_SYMBOL).all()
            or not f.timestamp.gt(pd.Timestamp(INPUT_START)).all()
            or not f.timestamp.le(pd.Timestamp(INPUT_END)).all()
            or f.event_id.duplicated().any()):
        raise ValueError("Invalid pinned observed funding frame")
    return h, features(d), f


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str, allow_nan=False) + "\n")


def save_run(label, result):
    summary, trades, curve, stops, funds = result
    write_json(OUT / f"{label}_summary.json", summary)
    trades.to_csv(OUT / f"{label}_trades.csv", index=False)
    curve.to_parquet(OUT / f"{label}_equity.parquet", index=False)
    stops.to_csv(OUT / f"{label}_stops.csv", index=False)
    if len(funds):
        funds.to_csv(OUT / f"{label}_funding.csv", index=False)


def period_returns(curve):
    day = curve[curve.kind == "hour_close"].set_index("timestamp").equity.copy()
    # End-of-hour timestamps at midnight close the preceding UTC day.
    day.index = day.index - pd.Timedelta(microseconds=1)
    previous = 10000.0
    rows = []
    for period, block in day.groupby(day.index.tz_localize(None).to_period("Q")):
        last = float(block.iloc[-1])
        if period == day.index.tz_localize(None).to_period("Q")[-1]:
            last = float(curve.equity.iloc[-1])
        rows.append({"quarter": str(period), "return_pct": (last / previous - 1) * 100, "end_equity": last})
        previous = last
    return rows


def render_charts(d, runs):
    colors = ["#12675b", "#c98032", "#8456af", "#506987"]
    shown = [("主方案：单日加速+RSI", runs["primary"]),
             ("同条件：只用移动止损", runs["reverse_only"]),
             ("单日加速+RSI，关闭反手", runs["no_reverse_accel1"]),
             ("买入持有", runs["buy_hold"])]
    allcurves = []
    for _, r in shown:
        c = r[2].groupby("timestamp").equity.last().resample("1D").last().dropna()
        allcurves.append(c)
    start = min(c.index[0].value for c in allcurves)
    end = max(c.index[-1].value for c in allcurves)
    low = min(float(c.min()) for c in allcurves) * .95
    high = max(float(c.max()) for c in allcurves) * 1.05
    width, height = 1120, 400
    def x(t):
        return 75 + (t.value - start) / (end - start) * 1000
    def y(v):
        return 350 - (v - low) / (high - low) * 300
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="各方案账户净值曲线">']
    for i in range(6):
        value = low + (high - low) * i / 5
        yy = y(value)
        parts.append(f'<line x1="75" x2="1075" y1="{yy}" y2="{yy}" stroke="#ddd"/><text x="8" y="{yy+4}" font-size="13">{value:,.0f}</text>')
    for i, ((label, _), curve) in enumerate(zip(shown, allcurves)):
        points = " ".join(f"{x(t):.2f},{y(v):.2f}" for t, v in curve.items())
        parts.append(f'<polyline fill="none" stroke="{colors[i]}" stroke-width="2" points="{points}"/><text x="{80+i*265}" y="22" fill="{colors[i]}" font-size="14">{label}</text>')
    for ts in pd.date_range(pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC"), freq="2MS"):
        parts.append(f'<text x="{x(ts):.1f}" y="380" text-anchor="middle" font-size="13">{ts:%Y-%m}</text>')
    parts.append('</svg>')
    svg = "".join(parts)
    (OUT / "equity.svg").write_text(svg)
    trade_html = runs["primary"][1][["trade_id", "side", "entry_time", "entry_price", "exit_time", "exit_price", "exit_reason", "net_pnl"]].round(3).to_html(index=False)
    html = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>HYPE 日线 MA7 策略回测</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1180px;margin:40px auto;padding:0 24px;color:#24312e;background:#fafaf7}}h1{{font-size:29px}}p{{line-height:1.7}}svg{{width:100%;background:white}}table{{border-collapse:collapse;font-size:13px;width:100%}}td,th{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}.scroll{{overflow:auto}}</style>
<h1>HYPE 日线 MA7 穿越与移动止损</h1><p>2025-06-29 至 2026-09-04 · 每笔约1倍本金 · 单边手续费0.05% + 滑点0.03% · 未计资金费率。历史数据已重复使用，此图只展示本次历史回测。</p>
{svg}<p>主方案：MA7斜率大于0.05 ATR；1.5 ATR止损只收窄；止损前5天有效反向穿越可反手；盈利空单满足 RSI6≤30 和单日加速后，次日开盘退出。</p>
<h2>主方案全部交易</h2><p>side：1为多单，-1为空单。盘中止损时间表示触发所在小时的起点，精确区间见CSV。</p><div class="scroll">{trade_html}</div></html>'''
    (OUT / "charts.html").write_text(html)


def buy_hold(h, start, end, config):
    sample = h[(h.timestamp >= start) & (h.timestamp < end)]
    fill = float(sample.iloc[0].open) * (1 + config.slip)
    qty = 10000 / (fill * (1 + config.fee))
    cash = 10000 - qty * fill * config.fee
    curve = pd.DataFrame({"timestamp": sample.timestamp + pd.Timedelta(hours=1), "equity": cash + qty * (sample.close - fill)})
    last = float(sample.iloc[-1].close)
    final = cash + qty * (last * (1 - config.slip) - fill) - qty * last * (1 - config.slip) * config.fee
    curve = pd.concat([pd.DataFrame({"timestamp": [start], "equity": [10000.0]}), curve, pd.DataFrame({"timestamp": [end], "equity": [final]})], ignore_index=True)
    vals = curve.equity
    summary = {"name": "buy_hold", "return_pct": (final / 10000 - 1) * 100, "ending_equity": final, "max_drawdown_pct": float((vals / vals.cummax() - 1).min()) * 100,
               "start": str(start), "end_exclusive": str(end), "trades": 1, "funding_window_verified": False}
    return summary, pd.DataFrame(), curve, pd.DataFrame(), pd.DataFrame()


def main():
    OUT.mkdir(exist_ok=True)
    h, d, f = load_inputs()
    d.to_csv(OUT / "daily_features.csv", index=False)
    start = d.loc[d.ready, "timestamp"].iloc[0] + pd.Timedelta(days=1)
    end = h.timestamp.iloc[-1] + pd.Timedelta(hours=1)
    split = start + pd.Timedelta(days=int((end - start).days * .6))
    configs = [Config(slope, reverse, mode) for slope, reverse, mode in itertools.product([0.0, .02, .05, .10], [False, True], ["none", "rsi30", "accel1_rsi30", "accel2_rsi30"])]
    write_json(OUT / "run_manifest.json", {"input_checksums_file_sha256": digest(INPUT / "checksums.json"),
               "contract_sha256": digest(BASE / "specs/contract-20260909.md"), "engine_sha256": digest(BASE / "scripts/engine.py"),
               "run_script_sha256": digest(Path(__file__)), "start": start, "end": end, "split": split,
               "computation_started_at_utc": str(pd.Timestamp.now(tz="UTC")), "configs": [c.__dict__ for c in configs],
               "primary": Config().__dict__, "classification": "ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS"})
    rows, all_full = [], {}
    for c in configs:
        for window, lo, hi in [("full", start, end), ("early60", start, split), ("late40", split, end)]:
            result = simulate(h, d, c, lo, hi)
            rows.append({"window": window, **result[0]})
            if window == "full":
                all_full[c.name] = result
                result[1].to_csv(OUT / f"grid_{c.name}_trades.csv", index=False)
        print(f"completed {c.name}", flush=True)
    grid = pd.DataFrame(rows)
    grid.to_csv(OUT / "all_results.csv", index=False)
    chosen = {"primary": Config(), "basic": Config(reverse=False, short_exit="none"),
              "no_reverse_accel1": Config(reverse=False),
              "reverse_only": Config(short_exit="none"), "rsi_only": Config(short_exit="rsi30"),
              "accel2": Config(short_exit="accel2_rsi30")}
    runs = {key: all_full[value.name] for key, value in chosen.items()}
    for key, value in runs.items():
        save_run(key, value)
    checks = []
    for key, c, funding, carry in [("observed_funding_estimate", Config(), f, 0),
                                   ("slippage_stress", replace(Config(), slip=.001), None, 0),
                                   ("daily_signal_delay_1h", replace(Config(), delay_hours=1), None, 0),
                                   ("adverse_carry_5bp_day", Config(), None, .0005)]:
        result = simulate(h, d, c, start, end, funding, carry)
        save_run(key, result)
        checks.append({"scenario": key, **result[0]})
    pd.DataFrame(checks).to_csv(OUT / "sensitivity.csv", index=False)
    runs["buy_hold"] = buy_hold(h, start, end, Config())
    write_json(OUT / "buy_hold_summary.json", runs["buy_hold"][0])
    runs["buy_hold"][2].to_parquet(OUT / "buy_hold_equity.parquet", index=False)
    pd.DataFrame(period_returns(runs["primary"][2])).to_csv(OUT / "primary_quarters.csv", index=False)
    render_charts(d, runs)
    write_json(OUT / "key_results.json", {key: value[0] for key, value in runs.items()})
    # Input and account checks execute on every run, including sensitivity runs.
    write_json(OUT / "artifact_checksums.json", {p.name: digest(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "artifact_checksums.json"})
    print(json.dumps({k: v[0] for k, v in runs.items()}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
