# Binance-15M-Asset-Specific-Six-Strategy-Selector Core Ledger

## Family Identity

- Full family name：`Binance-15M-Asset-Specific-Six-Strategy-Selector`
- Short id：`BIN-15M-AS6S`
- Market：Binance USD-M Futures perpetual
- Symbols：`BTCUSDT / ETHUSDT / SOLUSDT / BNBUSDT / TRXUSDT / HYPEUSDT`
- Timeframe：资产专属 `15m / 1h` 混合信号；高周期状态只使用闭合 K
- Mechanism：每币独立发现机制，再做六币全局单仓仲裁；比较不抢占与强信号抢占。
- Collision warning：不是 `BIN-1H-AR-MAE` 或 `BIN-1H-ML6AS` 的版本，不改变三条 HYPE 参考家族身份。

## Current State

- Status：`archived`。2026-08-05 按用户决定停止本家族后续研究，仅保留
  V1/V5/V6 的叙事记录、规格与历史脚本。
- Evidence health：本地行情、funding、冻结 JSON、交易清单与规范 parity
  产物已删除，不再重建；历史指标只能用于复盘，不能作为新的复现、登记或
  promotion 证据。
- Final OOS：原定 `[2026-07-14, 2026-10-14)` 一次性未来 OOS 已放弃，
  不再揭示或裁决。
- Runner boundary：2026-09-03 用户决定停止 V6 两条 dry-run 实例，runner 提交 `a5a3b2a`，服务器 `2026-09-03T06:47:02Z` 生效。实际授权、模式与运行状态只以 quant-runner 为准。

## Version Rules

- `V1` 固定九条资产专属腿、账户缩放 `0.75`、nonpreemptive 单仓仲裁、成本、执行和冻结时点。
- `V6` 固定 15 条资产专属腿、真实 15m mark 保护语义、账户缩放 `0.75` 与两套
  路由；任何腿、参数、scale、路由或成交语义变化都必须新版本，且在最终 OOS
  揭示前禁止修改。
- 单币机制试验与 reused-holdout 淘汰均为 observation；V6 的
  strong-breakout-preemptive 是同一注册版本内的冻结对照路线，不单独获得版本号。
- 成分机制或全局账户状态机变化都需要新 observation；已登记后发生交易路径变化则需要新版本。

## Version Table

| Version | Status | Role / Core Idea | Key Frozen Metrics | Evidence | Decision / Live Readiness |
| --- | --- | --- | --- | --- | --- |
| `BIN-15M-AS6S-V1` | `archived` | 九条资产专属 `15m/1h` 腿，全局单仓，持仓期间绝不抢占，账户缩放 `0.75` | full：`3.611x annual / +1012.61% / -12.37% DD / 90.55% / 307`；reused 3m：`+42.32% / -6.25% DD / 92.50% / 40` | [冻结规格](specs/binance-as6s-future-oos-freeze-2026-07-14.md)；[近期切片](diagnostics/binance-as6s-v1-recent-slices-2026-07-14.md) | 仅保留历史指标；最终 OOS 放弃，不再复现或 promotion |
| `BIN-15M-AS6S-V6-NP` / `BIN-15M-AS6S-V6-SBP` | `archived` | 15 条资产专属腿、真实 15m mark 保护退出、全局单仓双路线，scale `0.75` | NP full：`31.078x annual / -17.99% DD / 85.65% / 634`；SBP full：`30.817x / -17.04% DD / 85.21% / 568` | [冻结规格](specs/binance-as6s-v6-mark-joint-future-oos-freeze-2026-07-15.md)；[账户审计](diagnostics/binance-as6s-v6-mark-clean-rsi-joint-candidate-audit-2026-07-15.md)；[Runner 对拍](runner-tracking/binance-as6s-v6-mark-joint-runner-2026-07-15.md) | 仅保留历史 dry-run 叙事；产物删除，最终 OOS 放弃 |
| `BIN-15M-AS6S-V5-JOINT-NP`（V5 joint-state observation） | `archived` | 15 条资产专属腿、真实成交驱动 cooldown、nonpreemptive 联合单仓，账户缩放 `0.40` | full：`5.8156x annual / +3280.13% / -12.86% DD / 85.17% / 553` | [Runner 对拍](runner-tracking/binance-as6s-v5-joint-runner-2026-07-15.md)；[退役记录](runner-tracking/binance-as6s-v5-retire-engine-inhouse-2026-08-04.md) | Runner 侧 V5 已整体退役；未登记 observation 仅保留历史实现与对拍叙事 |
| `portfolio-first-v2-observation` | `archived` | 单腿不限胜率、账户胜率硬门槛；六腿、账户缩放 `0.50`；nonpreemptive 主候选与强突破抢占对照 | nonpreemptive full：`6.525x annual / +4154.96% / -8.93% DD / 89.07% / 247`；当前 3m：`+28.46% / -7.49% DD / 81.08% / 37` | [组合优先诊断](diagnostics/binance-as6s-portfolio-first-v2-observation-2026-07-14.md) | 未登记 observation，仅保留历史记录 |

## Shared Assumptions

- BTC/ETH/SOL/BNB/TRX 单币研究尽量使用最近两年；HYPE 使用 Binance 上市以来全部历史。
- V1 选择只使用 `<2026-04-14` 数据；`[2026-04-14, 2026-07-14)` 对 V1 是 reused holdout，只能淘汰。组合优先 observation 按用户新口径把截至 `2026-07-14` 的数据用于研究选择，并把 `[2026-07-14, 2026-10-14)` 保留为自己的未来最终 OOS。
- Binance 成本：手续费 `0.001/fill`、基础滑点 `4 bps/fill`、真实历史 funding；另做 `8 bps/fill` 压力。
- 多空双向，允许空仓，账户最大暴露 `3x`。
- V1 账户缩放 `0.75`，冻结腿的最大有效暴露 `1.875x`；同一时刻最多一笔持仓。
- V6 两条路线账户缩放均为 `0.75`，最大有效暴露 `2.25x`；同一时刻最多一笔持仓。
- 最终组合硬门槛：full 和未来 OOS 胜率均 `>=80%`，full trades `>=200`，未来 OOS trades `>=30`，full 和未来 OOS 最大回撤均严格 `<20%`，收益均为正。

## Evidence Map

- 产物删除与归档边界：[artifacts/README.md](artifacts/README.md)
- 数据质量审计：[diagnostics/binance-six-asset-15m-data-quality-2026-07-14.md](diagnostics/binance-six-asset-15m-data-quality-2026-07-14.md)
- V1 冻结规格与近期切片：[specs/binance-as6s-future-oos-freeze-2026-07-14.md](specs/binance-as6s-future-oos-freeze-2026-07-14.md)、[diagnostics/binance-as6s-v1-recent-slices-2026-07-14.md](diagnostics/binance-as6s-v1-recent-slices-2026-07-14.md)
- V5 观察、历史 Runner 对拍与退役记录：[diagnostics/binance-as6s-v5-joint-state-observation-2026-07-14.md](diagnostics/binance-as6s-v5-joint-state-observation-2026-07-14.md)、[runner-tracking/binance-as6s-v5-joint-runner-2026-07-15.md](runner-tracking/binance-as6s-v5-joint-runner-2026-07-15.md)、[runner-tracking/binance-as6s-v5-retire-engine-inhouse-2026-08-04.md](runner-tracking/binance-as6s-v5-retire-engine-inhouse-2026-08-04.md)
- V6 冻结规格、账户审计与历史 Runner 对拍：[specs/binance-as6s-v6-mark-joint-future-oos-freeze-2026-07-15.md](specs/binance-as6s-v6-mark-joint-future-oos-freeze-2026-07-15.md)、[diagnostics/binance-as6s-v6-mark-clean-rsi-joint-candidate-audit-2026-07-15.md](diagnostics/binance-as6s-v6-mark-clean-rsi-joint-candidate-audit-2026-07-15.md)、[runner-tracking/binance-as6s-v6-mark-joint-runner-2026-07-15.md](runner-tracking/binance-as6s-v6-mark-joint-runner-2026-07-15.md)、[V6 dry-run 停止](runner-tracking/binance-as6s-v6-dry-run-stop-2026-09-03.md)
- 历史脚本入口：[scripts/](scripts/README.md)
