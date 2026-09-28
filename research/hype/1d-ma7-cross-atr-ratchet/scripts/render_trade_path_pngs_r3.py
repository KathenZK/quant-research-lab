"""Four full-history R3 path figures from the verified saved chart payload."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, fontManager
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "artifacts/r3_trade_paths_20260909"
ARMS = ("P2_extreme", "P2_ma", "P2_extreme_cross_cap10", "P4_ma")
FONT = Path("/System/Library/Fonts/STHeiti Light.ttc")
GREEN, RED, BLUE, STOP, PURPLE = "#167566", "#c34e59", "#347eb1", "#a17124", "#8560ac"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def date_num(value):
    return value / 86_400_000


def render(data, name):
    fontManager.addfont(str(FONT))
    plt.rcParams.update({"font.family": FontProperties(fname=str(FONT)).get_name(),
                         "axes.unicode_minus": False, "axes.edgecolor": "#d9dfdb",
                         "axes.labelcolor": "#35423e", "xtick.color": "#64726e",
                         "ytick.color": "#64726e", "font.size": 10})
    arm, candles = data["arms"][name], data["candles"]
    fig, axes = plt.subplots(4, 1, figsize=(19.8, 13.2), sharex=True,
                             gridspec_kw={"height_ratios": [5.8, 1.15, 1.1, 1.55], "hspace": .13})
    fig.patch.set_facecolor("#f5f5f0")
    price, mult, rsi, equity = axes
    for axis in axes:
        axis.set_facecolor("white")
        axis.grid(axis="y", color="#e5eae5", linewidth=.7)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
    for bar in candles:
        x = date_num(bar[0]) + .5
        color = GREEN if bar[4] >= bar[1] else RED
        price.vlines(x, bar[3], bar[2], color=color, linewidth=.6, zorder=2)
        price.add_patch(Rectangle((x-.3, min(bar[1], bar[4])), .6,
                                  max(.035, abs(bar[4]-bar[1])), facecolor=color,
                                  edgecolor=color, linewidth=.5, zorder=2))
    dates = [date_num(b[0]) + 1 for b in candles]
    price.plot(dates, [b[5] for b in candles], color=BLUE, linewidth=1.1, zorder=3)
    for trade in arm["trades"]:
        x0, x1 = date_num(trade["entry"]), date_num(trade["exitPlot"])
        price.axvspan(x0, x1, color=GREEN if trade["side"] == 1 else RED, alpha=.055, zorder=1)
        tx = [date_num(p[0]) for p in trade["stops"]] + [x1]
        ty = [p[1] for p in trade["stops"]] + [trade["stops"][-1][1]]
        price.step(tx, ty, where="post", color=STOP, linewidth=1, linestyle=(0, (4, 2)), zorder=3)
        price.plot([x0, x1], [trade["entryPrice"], trade["exitPrice"]],
                   color=GREEN if trade["pnl"] >= 0 else RED, linewidth=.9,
                   linestyle=(0, (2, 3)), zorder=3)
        price.scatter([x0], [trade["entryPrice"]], marker="^" if trade["side"] == 1 else "v",
                      s=43, color=GREEN if trade["side"] == 1 else RED,
                      edgecolor="white", linewidth=.5, zorder=5)
        reason = trade["exitReason"]
        marker, color = (("D", STOP) if reason.startswith("stop") else
                         ("s", "#64726e") if reason == "sample_end" else
                         ("x", BLUE) if reason == "opposite_cross" else ("o", PURPLE))
        price.scatter([x1], [trade["exitPrice"]], marker=marker, s=35, color=color,
                      linewidth=1.5 if marker == "x" else .5, zorder=5)
        price.annotate(str(trade["id"]), (x0, trade["entryPrice"]),
                       xytext=(0, 11 if trade["side"] == -1 else -15),
                       textcoords="offset points", color=GREEN if trade["side"] == 1 else RED,
                       ha="center", fontsize=8,
                       bbox={"facecolor": "white", "edgecolor": "none", "alpha": .86, "pad": .6}, zorder=6)
        steps = trade["progress"]
        mult.step([date_num(p["ts"]) for p in steps] + [x1],
                  [p["mult"] for p in steps] + [trade["finalMult"]], where="post",
                  color=STOP, linewidth=1)
        for p in steps:
            if p["tightened"]:
                price.scatter([date_num(p["ts"])], [p["stop"]], s=13,
                              edgecolor=STOP, facecolor="white", linewidth=.8, zorder=4)
                mult.scatter([date_num(p["ts"])], [p["mult"]], s=10, color=STOP, zorder=4)
        if trade["tpSignal"] is not None:
            rsi.scatter([date_num(trade["tpSignal"]) + 1], [trade["tpRsi"]],
                        s=20, color=PURPLE, zorder=4)
    legend = [Line2D([], [], color=BLUE, label="MA7"),
              Line2D([], [], color=STOP, linestyle="--", label="实际止损"),
              Line2D([], [], color=STOP, marker="o", markerfacecolor="white", linestyle="", label="减ATR倍数"),
              Line2D([], [], color=GREEN, marker="^", linestyle="", label="开多"),
              Line2D([], [], color=RED, marker="v", linestyle="", label="开空"),
              Line2D([], [], color=STOP, marker="D", linestyle="", label="止损"),
              Line2D([], [], color=PURPLE, marker="o", linestyle="", label="RSI止盈"),
              Line2D([], [], color=BLUE, marker="x", linestyle="", label="反穿退出"),
              Line2D([], [], color="#64726e", marker="s", linestyle="", label="样本结束结算")]
    price.legend(handles=legend, loc="upper left", ncol=9, frameon=False, fontsize=9)
    price.set_ylabel("价格 / USDT")
    mult.set_ylim(.35, 1.65)
    mult.set_yticks([.5, 1, 1.5])
    mult.axhline(.5, color="#9ca69e", linewidth=.7, linestyle="--")
    mult.set_ylabel("ATR倍数")
    rsi.plot(dates, [b[7] for b in candles], color=PURPLE, linewidth=.9)
    rsi.axhspan(0, 30, color="#f5efea")
    rsi.axhline(30, color=STOP, linewidth=.8, linestyle="--")
    rsi.set_ylim(0, 100)
    rsi.set_yticks([0, 30, 70, 100])
    rsi.set_ylabel("RSI6")
    equity.plot([date_num(p[0]) for p in arm["equity"]], [p[1] for p in arm["equity"]],
                 color=GREEN, linewidth=1)
    equity.set_ylabel("净值 / USDT")
    equity.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    equity.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    equity.set_xlabel("UTC 日期 · 编号对应当前方案全部交易；与旧B0的匹配号见交互图")
    equity.set_xlim(date_num(candles[0][0])-2, date_num(data["end"])+3)
    summary = arm["summary"]
    fig.suptitle(f"HYPE 日K全部交易 ｜ {name} · {arm['label']}", x=.07, y=.978,
                 ha="left", fontsize=20, fontweight="bold")
    fig.text(.07, .948,
             f"累计收益 {summary['return_pct']:+.2f}%  ·  最大回撤 {abs(summary['max_drawdown_pct']):.2f}%  ·  全部{summary['trades']}笔（多{summary['long_trades']} / 空{summary['short_trades']}）  ·  2025-06-29—2026-09-04",
             fontsize=12, color="#35423e")
    anchor = "MA止损＋持仓日K极值保护" if summary["stop_anchor"] == "extreme" else "仍使用MA止损"
    extras = ("；反向穿越退出" if summary["exit_opposite_cross"] else "") + ("；初始距离上限10%" if summary["initial_stop_cap_pct"] else "")
    fig.text(.07, .922,
             f"完整持仓日K的最高/最低连续{summary['progress_days']}日未刷新后启动，每天减0.2至0.5，不要求浮盈、启动不撤销；{anchor}{extras}。",
             fontsize=10, color="#64726e")
    fig.text(.07, .024,
             "单边手续费0.05%＋滑点0.03%，未计完整资金费率。实际止损只收窄、次日生效；盘中止损仅定位到小时。倍数下限并非现价与止损距离下限。",
             fontsize=9, color="#64726e")
    fig.subplots_adjust(top=.89, bottom=.075, left=.07, right=.98)
    path = OUT / f"{name}-trade-paths.png"
    fig.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def main():
    audit_path, payload_path = OUT / "chart_audit.json", OUT / "payload.json"
    audit = json.loads(audit_path.read_text())
    assert sha(payload_path) == audit["payload_sha256"]
    assert sha(OUT / "hype-ma7-r3-trade-paths.html") == audit["html_sha256"]
    data = json.loads(payload_path.read_text())
    images = {arm: render(data, arm) for arm in ARMS}
    receipt = {"chart_audit_sha256": sha(audit_path), "payload_sha256": sha(payload_path),
               "renderer_sha256": sha(Path(__file__)), "matplotlib_version": matplotlib.__version__,
               "no_backtest_rerun": True, "all_trades_shown_for_each_arm": True,
               "outputs": {p.name: sha(p) for p in images.values()}}
    (OUT / "static_chart_audit.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: str(v) for k, v in images.items()}, indent=2))


if __name__ == "__main__":
    main()
