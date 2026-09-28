# SOL Research Index

本目录存放 Solana 单资产策略家族。任何版本号都必须和市场、周期、机制一起引用；状态词定义见 [strategy-status-glossary.md](../../docs/research-governance/strategy-status-glossary.md)。


## 状态

本目录家族状态列写 `见顶层`，以 [research/README.md](../README.md) 为准。

| Directory | 状态 |
| --- | --- |
| [1h-adaptive-regime/](1h-adaptive-regime/README.md) | 见顶层 |
| [1h-volatility-compression-breakout/](1h-volatility-compression-breakout/README.md) | 见顶层 |
| [4h-rs4-regime-switch/](4h-rs4-regime-switch/README.md) | 见顶层 |
| [1h-pullback-bracket/](1h-pullback-bracket/README.md) | 见顶层 |

## 当前研究线

- `SOL-1H-Adaptive-Regime`（`SOL-1H-AR`）：[1h-adaptive-regime/](1h-adaptive-regime/README.md)。Binance USD-M Futures `SOLUSDT` perpetual `1h` 多指标自适应 regime 研究；V1、V2、V3 已登记。V3 为 `Donchian core + VWAP arm-confirm-expire satellite`，full annual `2.10x`、DD `-19.05%`、win `79.17%`；reused holdout `+2.61%` 但只有 `3` 笔。当前 `registered / not promoted / not live-ready`。主账：[sol-1h-ar-core-ledger.md](1h-adaptive-regime/sol-1h-ar-core-ledger.md)。
- `SOL-1H-Volatility-Compression-Breakout`（`SOL-1H-VCB`）：[1h-volatility-compression-breakout/](1h-volatility-compression-breakout/README.md)。多 K 波动压缩 arm + 冻结区间突破 + ATR 正偏退出；2026-07-13 扩展搜索 `14848` 候选、hard pass `0`，最好观察 reused holdout 为负且 K+2 DD 失败；当前 `explore / not promoted / not live-ready`。主账：[sol-1h-vcb-core-ledger.md](1h-volatility-compression-breakout/sol-1h-vcb-core-ledger.md)。
- `SOL-4H-RS4-Regime-Switch`（`SOL-4H-RS4`）：[4h-rs4-regime-switch/](4h-rs4-regime-switch/README.md)。压缩 MACD v10 + 扩张 Donchian melt 显式 router；首轮 `401` 规格 base-gate `0`，最好失败观察 full DD `-47.97%`，且无 intrabar protection stop；当前 `explore / not promoted / not live-ready`。主账：[sol-4h-rs4-core-ledger.md](4h-rs4-regime-switch/sol-4h-rs4-core-ledger.md)。
- `SOL-1H-Pullback-Bracket`（`SOL-1H-PB`）：[1h-pullback-bracket/](1h-pullback-bracket/README.md)。趋势持续 → 回踩 arm → 恢复确认 → 即时 ATR bracket；首轮 `1500` 候选 hard pass `0`，最好观察 full annual `1.14x`、fresh forward `-2.01%`；当前 `explore / not promoted / not live-ready`。主账：[sol-1h-pb-core-ledger.md](1h-pullback-bracket/sol-1h-pb-core-ledger.md)。
- `SOL-4H-RS4-Regime-Switch`（`SOL-4H-RS4`）：[4h-rs4-regime-switch/](4h-rs4-regime-switch/README.md)。压缩 MACD v10 + 扩张 Donchian melt 显式 router；首轮 `401` 规格 base-gate `0`，最好失败观察 full DD `-47.97%`，且无 intrabar protection stop；当前 `explore / not promoted / not live-ready`。主账：[sol-4h-rs4-core-ledger.md](4h-rs4-regime-switch/sol-4h-rs4-core-ledger.md)。
