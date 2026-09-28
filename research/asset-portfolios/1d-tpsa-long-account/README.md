# Binance-1D-TPSA-Long-Account

- Alias：`BIN-1D-TPSA-LA`；独立家族，Binance USDT-M 历史多头事件、完整 UTC 日K。
- 版本：`R0`；主状态：`registered / not promoted / not live-ready`。
- 研究结论：本轮账户候选 **NO-GO**；结果标签 `HARD-GATE-FAILED / diagnostic-only`，净收益输入与实际执行另有具体阻塞。这不是 runner 的 NO-GO 主状态，也不否定旧 TPSA 的条件排序命题。
- 10,000美元主条件账户2025-01-01至2026-07-01降至2,108.53美元，价格与手续费口径收益-78.91%、最大回撤79.45%；真实funding未知、日open为理想代理，不能当正式净绩效。

入口：[主账](binance-1d-tpsa-la-core-ledger.md) · [报告](diagnostics/r0-results-2026-09-08.md) · [研究契约](specs/r0-contract.md) · [机器摘要](artifacts/summary.json) · [决策日志](decision-log.md) · [逐笔交互路径](artifacts/trade_paths.html) · [权益与回撤](artifacts/equity_drawdown.png)。

复现使用 [一键入口](scripts/run_all.py)，须给新的空输出目录，绝不改写原仓库或冻结产物：

```bash
/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python /Users/ZK/.codex/worktrees/5f41/quant-strategy-lab/research/asset-portfolios/1d-tpsa-long-account/scripts/run_all.py --output-dir /tmp/tpsa-la-r0-replay-new
```

依赖原仓库只读共享湖、原冻结事件/cache及已固定SHA源码；查 [源清单](artifacts/source_manifest.json)、[环境](artifacts/model_audit.json)、[完整清单](artifacts/artifact_manifest.json)。运行重验当前所pin的不可变bundle并消费返回帧，约数分钟。SVG绘图用已提供bundled ReportLab运行时；可选 [PNG绘图器](scripts/plot_png.py) 只读CSV，需matplotlib，不参与训练。

[原假设家族](../1d-trend-prebreakout-state-atlas/README.md) · [资产索引](../README.md) · [总研究索引](../../README.md)。无 runner 交接、实例或下单。
