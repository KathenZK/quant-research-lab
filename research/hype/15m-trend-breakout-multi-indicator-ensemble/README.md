# HYPE-15M-Trend-Breakout-Multi-Indicator-Ensemble

- Full family name：`HYPE-15M-Trend-Breakout-Multi-Indicator-Ensemble`（别名 `HYPE-15M-TB-MII-ENS`）
- 市场/周期：Binance `HYPEUSDT` perpetual `15m`
- 机制：`HYPE-EMA-TB-V39` + `HYPE-15M-MII-V1.4` 单账户 `single_v39_priority_k1`（V39 优先，V1.4 强平让位）。
- 当前状态：`V2 dry-run / PASS / not live-ready`

## 边界

本目录不修改两个母家族的版本定义。母账：[hype-ema-tb-core-ledger.md](../15m-ema-trend-breakout/hype-ema-tb-core-ledger.md)、[hype-15m-mii-core-ledger.md](../15m-multi-indicator-intraday/hype-15m-mii-core-ledger.md)。

## 入口

- 主账：[hype-15m-tb-mii-ens-core-ledger.md](hype-15m-tb-mii-ens-core-ledger.md)
- 决策记录：[decision-log.md](decision-log.md)
- V2 live validation spec：[hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md](live-specs/hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md)
- V2 live-executable 审计：[hype-15m-tb-mii-ens-v2-live-executable-audit-2026-07-09.md](diagnostics/hype-15m-tb-mii-ens-v2-live-executable-audit-2026-07-09.md)
- V2 组合回测：[hype-15m-tb-mii-ensemble-v39-v14-combination-backtest-2026-07-09.md](notes/hype-15m-tb-mii-ensemble-v39-v14-combination-backtest-2026-07-09.md)

压缩前 README 全文与阅读顺序见 [decision-log.md](decision-log.md) 2026-09-03 条目。
