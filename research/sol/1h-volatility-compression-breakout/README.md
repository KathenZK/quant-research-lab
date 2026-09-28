# SOL-1H-Volatility-Compression-Breakout

- Full family name：`SOL-1H-Volatility-Compression-Breakout`（别名 `SOL-1H-VCB`）
- 市场/周期：Binance USD-M Futures `SOLUSDT` perpetual `1h`
- 机制：多 K 波动压缩 arm、冻结箱体、有限窗口突破确认、下一根 open 入场、ATR fixed/trailing exit。
- 当前状态：`explore / HARD-GATE-FAILED / not promoted / not live-ready`（无登记版本）

## 边界

独立于 `SOL-1H-Adaptive-Regime`，不继承其 V1/V2。本家族身份是显式多 K 压缩区间状态机与正偏趋势收益结构，不是单 K squeeze / Donchian / VWAP 回穿。

## 入口

- 主账：[sol-1h-vcb-core-ledger.md](sol-1h-vcb-core-ledger.md)
- 决策记录：[decision-log.md](decision-log.md)
- 首轮搜索：[sol-1h-vcb-search-2026-07-13.md](diagnostics/sol-1h-vcb-search-2026-07-13.md)
- 数据抓取：[fetch_sol_1h_vcb_data.py](scripts/fetch_sol_1h_vcb_data.py)
- 搜索脚本：[research_sol_1h_vcb_search.py](scripts/research_sol_1h_vcb_search.py)
- 产物：[artifacts/README.md](artifacts/README.md)

压缩前 README 全文、两套搜索计数与数据窗口见 [decision-log.md](decision-log.md) 2026-09-03 条目与主账 Evidence Map。
