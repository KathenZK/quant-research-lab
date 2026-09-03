# HYPE-EMA-Trend-Breakout

- Full family name：`HYPE-EMA-Trend-Breakout`（历史别名：`HYPE-EMA-TB`）
- 市场/周期：HYPE `15m`
- 机制：EMA96/EMA384 趋势突破 / 追多追空，带 ADX、成交量、1h 确认、live-realistic 执行检查与跨所执行变体。
- 当前状态：`HYPE-EMA-TB-V35` 为 grandfathered `live / external-observation`；`V35.1` 为 `dry-run / not live-ready`；V35.2-V35.3、V36-V41 为 `registered / not promoted / not live-ready`。

## 边界

- 不是更早的 `HYPE-EMA-Crossover`（`HYPE-EMA-X`）金叉/死叉家族。
- 这里的 `V35` 不是 `HYPE-CC-V35` 或 `HYPE-EMA-X-V14`；历史报告文件名（`hype_v30_*`、`hype_v35_*` 等）跨家族撞名，必须回链接文档确认身份。
- Binance HYPE `5m` 回踩研究已拆分到独立家族 `../5m-pullback-trail/`；本地 `HYPE-5M-PBTR-V1/V2` 与本家族版本无关。
- 引用用完整名：`HYPE-EMA-TB-V30`、`HYPE-EMA-TB-V35`、`HYPE-EMA-TB-V36`。

## 入口

- 主账：[hype-ema-tb-core-ledger.md](hype-ema-tb-core-ledger.md)
- 决策记录：[decision-log.md](decision-log.md)
- V35.1 规格与 dry-run handoff：[hype-trend-strategy-v35-1-spec.md](specs/hype-trend-strategy-v35-1-spec.md) · [hype-ema-tb-v35-1-runner-draft.md](live-specs/hype-ema-tb-v35-1-runner-draft.md)
- V35.2 空头分批观察版：[hype-trend-strategy-v35-2-spec.md](specs/hype-trend-strategy-v35-2-spec.md)
- V35.3 非对称止损观察版：[hype-trend-strategy-v35-3-spec.md](specs/hype-trend-strategy-v35-3-spec.md)
- 最新编号研究规格：[hype-trend-strategy-v41-spec.md](specs/hype-trend-strategy-v41-spec.md)
- Runner handoff / live spec：[live-specs/](live-specs/)

脚本在 [scripts/](scripts/)，被报告引用的产物在 [artifacts/](artifacts/)，[legacy-canvas/](legacy-canvas/) 为冻结迁移历史；旧实验结论已归入主账、diagnostics、notes 与 artifacts，不再保留不存在的 `experiments/` 路由。
