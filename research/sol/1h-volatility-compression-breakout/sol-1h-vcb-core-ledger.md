# SOL-1H-Volatility-Compression-Breakout Core Ledger

## Family Identity

- Full family name：`SOL-1H-Volatility-Compression-Breakout`
- Alias：`SOL-1H-VCB`
- Market / exchange / symbol / timeframe：Binance USD-M Futures / `SOLUSDT` perpetual / `1h`
- Mechanism summary：多 K 波动压缩区间状态机 + 有限窗口突破确认 + ATR 正偏退出。
- Boundary：独立于 `SOL-1H-Adaptive-Regime`，不继承其版本号。

## Current State

- Current version(s)：无登记版本。
- Current status：`explore`
- Runner / dry-run / live status：无 runner；未进入 dry-run/live。
- Live-readiness blockers：硬门槛 `0` 命中；最好观察 reused holdout 为负；fresh forward 仅约 10 天且 `0` 笔；K+2 full DD 超过 `20%`。
- Next decision gate：若继续该 family，必须提出非参数扩搜的机制变化，并重新冻结 prefit-only 选择；不得依据 reused holdout 倒选。

## Version Rules

- `V1`：只有在 prefit/validation、reused-holdout 审计、fresh-forward 和执行压力均形成足够证据后，由用户明确登记。
- `Vx.y`：只用于已登记主版本的受控增强。
- Observation / diagnostic rows：搜索最佳值默认只作为 observation，不自动分配版本号。
- New version trigger：用户明确登记，且主账能记录指标、证据和 live-readiness 结论。

## Version Table

当前无登记版本。

## Shared Assumptions

- Data：最近两年闭合 Binance `SOLUSDT` perpetual `1h` K；2026-07-13 刷新。
- Cost：fee `0.001`/fill；slippage `4 bps`/fill。
- Execution timing：闭合 K 信号，下一根 open 成交；stop-first；gap-open。
- Position sizing：fixed 或基于 ATR stop distance 的 risk sizing，最大杠杆不超过 `3x`。
- Funding / carry：逐笔计入真实 Binance funding。

## Evidence Map

- 2026-09-03 README 压缩：完整原文见 [decision-log.md](decision-log.md) 当日条目。
- 压缩前 README 同时记录两套不得丢弃的搜索计数：正文首轮 `entry configs 800 / generated 2940 / eligible 341 / prefit hard pass 0`（最佳观察 prefit annual `1.3048x`、DD `-18.77%`、win `25.23%`、trades `107`）；后续扩搜口径以决策记录为准。
- 数据窗口：UTC `2024-07-13T07:00:00Z`–`2026-07-13T06:00:00Z`，`17520` 根闭合 `1h`；missing/duplicate/critical null/OHLCV/raw-normalized 均为 `0`。
- Diagnostics：[sol-1h-vcb-search-2026-07-13.md](diagnostics/sol-1h-vcb-search-2026-07-13.md)
- Scripts / artifacts：[fetch_sol_1h_vcb_data.py](scripts/fetch_sol_1h_vcb_data.py)、[research_sol_1h_vcb_search.py](scripts/research_sol_1h_vcb_search.py)、[artifacts/](artifacts/)

