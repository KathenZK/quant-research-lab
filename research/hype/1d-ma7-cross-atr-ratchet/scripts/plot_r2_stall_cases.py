"""Explain three frozen R2 trades; no simulation or historical decision changes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/r2_slowdown_tightening_20260909"
RUN = SOURCE / "runs/s0.05_rev0_accel1_rsi30_original_stall_only_p0/full"
OUTPUT = ROOT / "artifacts/r2_stall_case_review_20260909"
IDS = (1, 4, 9)
DAY = pd.Timedelta(days=1)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_source() -> dict:
    expected = json.loads((SOURCE / "artifact_checksums.json").read_text())
    for name, digest in expected.items():
        assert sha(SOURCE / name) == digest, f"Frozen R2 hash mismatch: {name}"
    return expected


def explanation_log(trade: pd.Series, stops: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Keep source stop fields intact; explanation columns never enter decisions."""
    selected = stops.loc[stops.trade_id == trade.trade_id].copy()
    price_columns = ["timestamp", "open", "high", "low", "close", "ma", "atr", "cross"]
    selected = selected.merge(
        daily[price_columns].rename(columns={"timestamp": "signal_day"}),
        on="signal_day", how="left", validate="many_to_one",
    )
    selected["entry_time"] = trade.entry_time
    selected["exit_time_hour_start"] = trade.exit_time
    selected["exit_interval_end"] = trade.exit_interval_end
    selected["signal_day_was_held"] = (
        (selected.signal_day >= trade.entry_time.floor("D"))
        & (selected.signal_day + DAY <= trade.exit_time)
        & selected.tightening_trigger.ne("entry")
    )
    selected["candidate_after_mult_change"] = (
        selected.ma - trade.side * selected.new_mult * selected.atr
    )
    selected["actual_stop_tightening_in_price"] = (
        trade.side * (selected.new_stop - selected.old_stop)
    )
    eligible = daily.loc[
        (daily.timestamp >= trade.entry_time.floor("D"))
        & (daily.timestamp + DAY <= trade.exit_time)
    ].copy()
    extreme_price, extreme_close = -np.inf, -np.inf
    last_price_day = last_close_day = None
    diagnostics = {}
    for row in eligible.itertuples():
        favorable_price = row.high if trade.side == 1 else -row.low
        favorable_close = trade.side * row.close
        if favorable_price > extreme_price:
            extreme_price, last_price_day = favorable_price, row.timestamp
        if favorable_close > extreme_close:
            extreme_close, last_close_day = favorable_close, row.timestamp
        diagnostics[row.timestamp] = {
            "explain_only_favorable_price_extreme": trade.side * extreme_price,
            "explain_only_favorable_close_extreme": trade.side * extreme_close,
            "explain_only_days_since_price_extreme": (row.timestamp - last_price_day).days,
            "explain_only_days_since_close_extreme": (row.timestamp - last_close_day).days,
        }
    for key in (
        "explain_only_favorable_price_extreme", "explain_only_favorable_close_extreme",
        "explain_only_days_since_price_extreme", "explain_only_days_since_close_extreme",
    ):
        selected[key] = [
            diagnostics.get(row.signal_day, {}).get(key, np.nan) if row.signal_day_was_held else np.nan
            for row in selected.itertuples()
        ]
    assert selected.loc[selected.tightening_trigger.eq("entry"), "signal_day_was_held"].eq(False).all()
    return selected


def dn(value) -> float:
    return mdates.date2num(pd.Timestamp(value).to_pydatetime())


def make_plot(trades: pd.DataFrame, daily: pd.DataFrame, logs: dict[int, pd.DataFrame]) -> None:
    font_path = "/System/Library/Fonts/STHeiti Light.ttc"
    font_manager.fontManager.addfont(font_path)
    font_name = font_manager.FontProperties(fname=font_path).get_name()
    plt.rcParams.update({
        "font.family": font_name, "font.size": 11, "axes.unicode_minus": False,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#a3acb7", "text.color": "#202a35", "axes.labelcolor": "#435261",
    })
    fig, axes = plt.subplots(3, 1, figsize=(16.5, 13.5), facecolor="#f9fafb")
    fig.subplots_adjust(left=.065, right=.977, top=.84, bottom=.085, hspace=.45)
    fig.suptitle("为什么价格已经掉头，止损倍数仍没继续减少？", x=.065, y=.978, ha="left", fontsize=22)
    fig.text(.065, .947, "HYPE 日K · 原入场条件 + 仅停滞时收紧 + 关闭反手 · 原结果逐日日志说明", fontsize=12)
    legend = [
        Line2D([], [], color="#d59a22", lw=2, label="MA7（收盘后才确定）"),
        Line2D([], [], color="#be4551", lw=2, label="实际生效止损（只能收窄）"),
        Line2D([], [], color="#8192a6", lw=1.3, ls=":", label="按当日倍数重算的候选线"),
        Line2D([], [], color="#6b54af", marker="o", markerfacecolor="none", lw=0, markersize=8, label="倍数减少；不保证实际线移动"),
        Line2D([], [], color="#202a35", marker="x", lw=0, markersize=8, label="退出（小时内具体时点未知）"),
    ]
    fig.legend(handles=legend, loc="upper left", bbox_to_anchor=(.058,.93), ncol=3, frameon=False, fontsize=10)
    titles = {
        1: "#1 多单｜0 次减少倍数",
        4: "#4 空单｜减 1 次，但实际止损线没动",
        9: "#9 多单｜1.5 → 1.3 → 1.1",
    }
    subtitles = {
        1: "7/14 后不再创新高；MA − 1.5ATR 仍每天抬升，系统仍判定为“没有停滞”。",
        4: "10/23 收盘时止损停滞，但仓位已浮亏；10/24 收盘小幅盈利才减倍数，候选线仍高于旧止损。",
        9: "两次减少之间，候选止损仍一点点抬升，系统继续跳过减少倍数；它没有按“不创新高天数”触发。",
    }
    for ax, tid in zip(axes, IDS):
        t = trades.loc[trades.trade_id == tid].iloc[0]
        log = logs[tid]
        first = t.entry_time.floor("D") - 2 * DAY
        last = t.exit_time.floor("D") + DAY
        bars = daily.loc[daily.timestamp.between(first, last - DAY)].copy()
        ax.set_facecolor("white")
        ax.set_title(titles[tid], loc="left", fontsize=15, pad=30, fontweight="bold")
        ax.text(0, 1.065, subtitles[tid], transform=ax.transAxes, fontsize=10.5, color="#526170")
        # Exit-day full candle is contextual, never a pre-exit decision input.
        ax.axvspan(dn(t.exit_time.floor("D")), dn(last), facecolor="#e9edf1", alpha=.8)
        for row in bars.itertuples():
            x = dn(row.timestamp) + .5
            color = "#268879" if row.close >= row.open else "#cf6870"
            alpha = .4 if row.timestamp < t.entry_time or row.timestamp >= t.exit_time.floor("D") else .92
            ax.vlines(x, row.low, row.high, color=color, linewidth=1.25, alpha=alpha)
            height = max(abs(row.close-row.open), .045)
            ax.add_patch(Rectangle((x-.27, min(row.open,row.close)), .54, height, facecolor=color, edgecolor=color, alpha=alpha))
        # Feature of calendar day D is placed at D+1, after the close.
        ma_bars = daily.loc[(daily.timestamp >= first-DAY) & (daily.timestamp+DAY <= last)]
        ax.plot([dn(v+DAY) for v in ma_bars.timestamp], ma_bars.ma, color="#d59a22", lw=1.9, zorder=3)
        sx = [dn(v) for v in log.timestamp]
        stop_end = dn(t.exit_time)  # conservative: known active until exit hour begins
        ax.step(sx+[stop_end], log.new_stop.tolist()+[log.new_stop.iloc[-1]], where="post", color="#be4551", lw=2.2, zorder=4)
        ax.plot(sx, log.candidate_after_mult_change, ":", color="#8192a6", lw=1.4, zorder=3)
        entry_x = dn(t.entry_time)
        exit_mid = t.exit_time + (t.exit_interval_end-t.exit_time)/2
        exit_x = dn(exit_mid)
        ax.scatter([entry_x], [t.entry_price], marker="^" if t.side==1 else "v", color="#235c76", s=82, zorder=7)
        ax.scatter([exit_x], [t.exit_price], marker="x", color="#202a35", linewidths=2, s=74, zorder=8)
        ax.annotate(f"入场 {t.entry_price:.2f}", (entry_x, t.entry_price), xytext=(8, 16 if t.side==1 else -28), textcoords="offset points", fontsize=10, color="#235c76")
        ax.annotate(f"退出 {t.exit_price:.2f}", (exit_x,t.exit_price), xytext=(-8, -31 if t.side==1 else 16), textcoords="offset points", ha="right", fontsize=10)
        tightened = log.loc[log.tightened]
        for i, row in enumerate(tightened.itertuples()):
            ax.scatter([dn(row.timestamp)], [row.new_stop], s=135, marker="o", facecolors="none", edgecolors="#6b54af", linewidths=2.2, zorder=9)
            label = f"{row.timestamp:%m/%d} 生效\nm: {row.old_mult:.1f} → {row.new_mult:.1f}"
            if tid == 4:
                label += f"\n止损仍 {row.new_stop:.2f}"
            offset = (-110,34) if tid==4 else ((10,-48) if i==0 else (-68,-48))
            ax.annotate(label, (dn(row.timestamp),row.new_stop), xytext=offset, textcoords="offset points", fontsize=10, color="#6b54af", arrowprops={"arrowstyle":"-", "color":"#6b54af", "lw":.8}, ha="right" if tid==4 else "left")
        # Mark opposite raw MA cross, known at the following boundary, for trade 4.
        if tid == 4:
            for day in [pd.Timestamp("2025-10-20",tz="UTC"), pd.Timestamp("2025-10-23",tz="UTC")]:
                row = bars.loc[bars.timestamp.eq(day)].iloc[0]
                ax.scatter([dn(day+DAY)], [row.close], s=33, marker="D", facecolors="none", edgecolors="#8c6423", zorder=6)
                ax.annotate(f"{day:%m/%d}收盘上穿MA", (dn(day+DAY),row.close), xytext=(0,-24), textcoords="offset points", ha="center", fontsize=9, color="#8c6423")
        ax.set_xlim(dn(first), dn(last))
        lower = min(bars.low.min(), log.new_stop.min(), t.entry_price, t.exit_price)
        upper = max(bars.high.max(), log.new_stop.max(), t.entry_price, t.exit_price)
        spread = upper-lower
        ax.set_ylim(lower-.29*spread, upper+.12*spread)
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.tick_params(axis="both", labelsize=10)
        ax.grid(axis="y", color="#e8edf1", lw=.7)
        ax.set_ylabel("价格（USDT）", fontsize=10)
        ax.text(.99,.965,f"{t.entry_time:%Y-%m-%d} → {t.exit_time:%Y-%m-%d}\n单笔收益 {t.return_on_entry_equity:+.2%}", transform=ax.transAxes, ha="right", va="top", fontsize=10, color="#536170", bbox={"facecolor":"white","alpha":.85,"edgecolor":"none","pad":3})
    fig.text(.065,.038,"全部为 UTC。日K居中显示；MA及止损在收盘后更新，次日生效。灰色退出日的完整K线仅供看走势，退出时并不知道当日最终高低价。",fontsize=10,color="#536170")
    fig.text(.065,.018,"紫圈说明减少 ATR 倍数；红线是否真的推进还受“只能收窄”限制。图中每笔编号沿用原回测；未重新计算交易。",fontsize=10,color="#536170")
    fig.savefig(OUTPUT / "stall-cases.png", dpi=180, facecolor=fig.get_facecolor())
    fig.savefig(OUTPUT / "stall-cases.pdf", facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    expected = verify_source()
    daily = pd.read_csv(SOURCE / "daily_features.csv", parse_dates=["timestamp"])
    trades = pd.read_csv(RUN / "trades.csv", parse_dates=["entry_time", "exit_time", "exit_interval_end"])
    stops = pd.read_csv(RUN / "stops.csv", parse_dates=["timestamp", "signal_day"])
    OUTPUT.mkdir(exist_ok=True)
    logs = {}
    for tid in IDS:
        trade = trades.loc[trades.trade_id.eq(tid)].iloc[0]
        logs[tid] = explanation_log(trade, stops, daily)
        logs[tid].to_csv(OUTPUT / f"trade-{tid}-daily-stop-explanation.csv", index=False)
    pd.concat(logs.values(), ignore_index=True).to_csv(OUTPUT / "daily_decision_log.csv", index=False)
    make_plot(trades, daily, logs)
    verify_source()
    audit = {
        "source_results": str(SOURCE), "source_checksum_manifest_sha256": sha(SOURCE / "artifact_checksums.json"),
        "source_files_verified_before_and_after": len(expected), "simulation_run": False,
        "config": RUN.parent.name, "trade_ids": list(IDS),
        "script_sha256": sha(Path(__file__)),
        "extra_columns": "explain_only columns use completed held daily candles; entry's prior signal day excluded; these columns never entered historical decisions",
        "chart_timing": "UTC; close-derived MA at next daily boundary; actual stop staircase from effective log timestamps; exit marker is interval midpoint, not claimed exact fill time",
        "cases": {str(k): {"stop_log_rows": len(v), "mult_decrements": int(v.tightened.sum()), "first_signal_day_is_held": bool(v.iloc[0].signal_day_was_held)} for k,v in logs.items()},
        "artifacts": {p.name:sha(p) for p in sorted(OUTPUT.iterdir()) if p.is_file() and p.name != "case-chart-audit.json"},
    }
    (OUTPUT / "case-chart-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
