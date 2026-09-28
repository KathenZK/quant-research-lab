"""Static overview from the already verified chart payload; no backtest or lake reads."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, fontManager
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "artifacts/trade_paths_20260909"
FONT = Path("/System/Library/Fonts/STHeiti Light.ttc")
GREEN, RED, BLUE, STOP, PURPLE = "#167566", "#c34e59", "#347eb1", "#a17124", "#8560ac"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def date_num(ms):
    return mdates.date2num(datetime.fromtimestamp(ms / 1000, timezone.utc))


def render(data, name):
    fontManager.addfont(str(FONT))
    plt.rcParams.update(
        {
            "font.family": FontProperties(fname=str(FONT)).get_name(),
            "axes.unicode_minus": False,
            "axes.edgecolor": "#d9dfdb",
            "axes.labelcolor": "#35423e",
            "xtick.color": "#64726e",
            "ytick.color": "#64726e",
            "font.size": 10,
        }
    )
    a, candles = data["arms"][name], data["candles"]
    fig, axes = plt.subplots(
        3,
        1,
        figsize=(18, 11),
        sharex=True,
        gridspec_kw={"height_ratios": [5.5, 1.2, 1.7], "hspace": 0.13},
    )
    fig.patch.set_facecolor("#f5f5f0")
    price, rsi, eq = axes
    for axis in axes:
        axis.set_facecolor("white")
        axis.grid(axis="y", color="#e5eae5", linewidth=0.7)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
    for b in candles:
        x = date_num(b[0]) + 0.5
        up = b[4] >= b[1]
        color = GREEN if up else RED
        price.vlines(x, b[3], b[2], color=color, linewidth=0.6, zorder=2)
        price.add_patch(
            Rectangle(
                (x - 0.30, min(b[1], b[4])),
                0.60,
                max(0.06, abs(b[4] - b[1])),
                facecolor=color,
                edgecolor=color,
                linewidth=0.5,
                zorder=2,
            )
        )
    price.plot(
        [date_num(b[0]) + 1 for b in candles],
        [b[5] for b in candles],
        color=BLUE,
        linewidth=1.05,
        zorder=3,
    )
    for t in a["trades"]:
        x0, x1 = date_num(t["entry"]), date_num(t["exitPlot"])
        price.axvspan(
            x0, x1, color=GREEN if t["side"] == 1 else RED, alpha=0.055, zorder=1
        )
        tx = [date_num(p[0]) for p in t["stops"]] + [x1]
        ty = [p[1] for p in t["stops"]] + [t["stops"][-1][1]]
        price.step(
            tx,
            ty,
            where="post",
            color=STOP,
            linewidth=0.95,
            linestyle=(0, (4, 2)),
            zorder=3,
        )
        price.plot(
            [x0, x1],
            [t["entryPrice"], t["exitPrice"]],
            color=GREEN if t["pnl"] >= 0 else RED,
            linewidth=0.85,
            linestyle=(0, (2, 3)),
            zorder=3,
        )
        price.scatter(
            [x0],
            [t["entryPrice"]],
            marker="^" if t["side"] == 1 else "v",
            s=40,
            color=GREEN if t["side"] == 1 else RED,
            edgecolor="white",
            linewidth=0.5,
            zorder=5,
        )
        exit_marker = (
            "D"
            if t["exitReason"].startswith("stop")
            else "s"
            if t["exitReason"] == "sample_end"
            else "o"
        )
        exit_color = (
            STOP if exit_marker == "D" else "#64726e" if exit_marker == "s" else PURPLE
        )
        price.scatter(
            [x1],
            [t["exitPrice"]],
            marker=exit_marker,
            s=32,
            color=exit_color,
            edgecolor="white",
            linewidth=0.5,
            zorder=5,
        )
        price.annotate(
            str(t["id"]),
            (x0, t["entryPrice"]),
            xytext=(0, 10 if t["side"] == -1 else -14),
            textcoords="offset points",
            color=GREEN if t["side"] == 1 else RED,
            ha="center",
            fontsize=8,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 0.5},
            zorder=6,
        )
        if t["tpSignal"] is not None:
            rsi.scatter(
                [date_num(t["tpSignal"]) + 1],
                [t["tpRsi"]],
                s=22,
                color=PURPLE,
                zorder=4,
            )
    legend = [
        Line2D([], [], color=BLUE, label="MA7（收盘后）"),
        Line2D([], [], color=STOP, linestyle="--", label="实际移动止损"),
        Line2D([], [], color=GREEN, marker="^", linestyle="", label="开多"),
        Line2D([], [], color=RED, marker="v", linestyle="", label="开空"),
        Line2D([], [], color=STOP, marker="D", linestyle="", label="止损"),
        Line2D([], [], color=PURPLE, marker="o", linestyle="", label="RSI止盈"),
        Line2D([], [], color="#64726e", marker="s", linestyle="", label="样本结束结算"),
    ]
    price.legend(handles=legend, loc="upper left", ncol=7, frameon=False, fontsize=9)
    price.set_ylabel("价格 / USDT")
    rsi.plot(
        [date_num(b[0]) + 1 for b in candles],
        [b[7] for b in candles],
        color=PURPLE,
        linewidth=0.9,
    )
    rsi.axhspan(0, 30, color="#f5efea")
    rsi.axhline(30, color=STOP, linewidth=0.8, linestyle="--")
    rsi.set_ylim(0, 100)
    rsi.set_yticks([0, 30, 70, 100])
    rsi.set_ylabel("RSI6")
    eq.plot(
        [date_num(p[0]) for p in a["equity"]],
        [p[1] for p in a["equity"]],
        color=GREEN,
        linewidth=1,
    )
    eq.set_ylabel("净值 / USDT")
    eq.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    eq.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    eq.set_xlabel("UTC 日期")
    axes[-1].set_xlim(date_num(data["candles"][0][0]) - 2, date_num(data["end"]) + 3)
    s = a["summary"]
    fig.suptitle(
        f"HYPE 日K交易路径 ｜ {a['label']}",
        x=0.07,
        y=0.975,
        ha="left",
        fontsize=20,
        fontweight="bold",
    )
    fig.text(
        0.07,
        0.94,
        f"累计收益 +{s['return_pct']:.2f}%   ·   最大回撤 {abs(s['max_drawdown_pct']):.2f}%   ·   {s['trades']}笔   ·   交易编号与交互图逐笔表一致",
        fontsize=12,
        color="#35423e",
    )
    fig.text(
        0.07,
        0.027,
        "单边手续费0.05%＋滑点0.03%，未计资金费率。多单背景浅绿、空单浅红；连线绿色为本笔盈利，红色为亏损。盘中止损标记只代表所在小时，精确区间见交互图。",
        fontsize=9,
        color="#64726e",
    )
    fig.subplots_adjust(top=0.9, bottom=0.08, left=0.07, right=0.975)
    path = OUT / f"{name}-trade-paths.png"
    fig.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def main():
    html = OUT / "hype-ma7-trade-paths.html"
    audit = json.loads((OUT / "chart_audit.json").read_text())
    assert sha(html) == audit["html_sha256"]
    payload = re.search(
        r'<script type="application/json" id="frozen-data">(.*?)</script>',
        html.read_text(),
        re.S,
    )
    data = json.loads(payload.group(1))
    images = {name: render(data, name) for name in data["arms"]}
    receipt = {
        "chart_html_sha256": sha(html),
        "renderer_sha256": sha(Path(__file__)),
        "matplotlib_version": matplotlib.__version__,
        "outputs": {p.name: sha(p) for p in images.values()},
    }
    (OUT / "static_chart_audit.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: str(v) for k, v in images.items()}, indent=2))


if __name__ == "__main__":
    main()
