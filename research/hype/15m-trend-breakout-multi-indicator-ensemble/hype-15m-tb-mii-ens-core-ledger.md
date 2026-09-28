# HYPE-15M-TB-MII-ENS Core Ledger

Family：`HYPE-15M-Trend-Breakout-Multi-Indicator-Ensemble`

Alias：`HYPE-15M-TB-MII-ENS`

Created：2026-07-07

## 边界

本台账覆盖 `HYPE-EMA-Trend-Breakout` 趋势腿（V35 或 V39）与 `HYPE-15M-Multi-Indicator-Intraday` 反转腿（V1.3 或 V1.4）的组合研究。裸版本号不具有策略身份；母版本定义以各自家族主账为准。

## 当前状态

- 当前状态：`HYPE-15M-TB-MII-ENS-V2 dry-run / not live-ready`；叙事 replay parity 曾通过但规范 JSON 已缺失，2026-08-04 起证据健康度为 `MISSING_EVIDENCE`，既有 dry-run 用户授权保留，live 仍未授权。共享 15m 行情组曾于 2026-07-21→07-30 [group halt](../15m-ema-crossover/runner-tracking/hype-ema-x-runner-2026-07-30-group-halt.md)，`d514e65` 部署后已恢复；停摆区间观察作废。
- 当前登记版本：`V2 = HYPE-EMA-TB-V39 + HYPE-15M-MII-V1.4`，单账户 `single_v39_priority_k1` 主口径（V39 优先 + V1.4 强平让位）。
- `V2` 是用户于 2026-07-09 指定登记的组合版本号；此前 V35+V1.3 与 V39+V1.3 仍为 diagnostic evidence，不反推登记为 V1。
- 2026-07-09 已导出 V2 validation spec，并完成 live-executable 审计；早间失败结论保留为 historical pre-dry-run finding。同日 `quant-runner` 已新增 `hype_tb_mii_ensemble` replay validation kind、全样本 replay parity、continuous dry-run runtime，以及 disabled live pilot 执行链。
- 2026-07-09 晚间完成全样本 replay 对拍：runner replay 与研究引擎 `single_v39_priority_k1` 逐笔路径完全一致（`291` 笔 / V39 `107` + V1.4 `184` / preempt `3` / 出场原因、价格、allocation 全一致），权益差异完全由 runner smoke 未计 V39 funding 解释（`+69593%` vs `+68193%`，回撤 `-27.85%` vs `-28.01%`）；6m/3m 近期窗口指标同样一致。见 [replay parity 报告](runner-tracking/hype-15m-tb-mii-ens-v2-runner-replay-parity-2026-07-09.md)。
- 2026-07-09 本轮完成 runtime/live pilot 代码路径并部署线上 dry-run：`hype-tb-mii-ens-dry-run` 已随 `quant-runner-dryrun` 在 `47.80.57.36` 运行，首次健康检查 `ok`、`position_open=0`、无 warning/error；`hype-tb-mii-ens-live` live config 仍 disabled。实现 V39 K+2、MII K+1、preempt close-confirm-open、保护单、重启状态、交易所核对和 fail-closed 门禁。见 [runtime/live-pilot tracking](runner-tracking/hype-15m-tb-mii-ens-v2-runtime-live-pilot-2026-07-09.md)。尚未完成/未批准：真实 live 启用、subaccount env/余额确认、持续 dry-run 运行窗口、V39 funding 统一记账、实盘 fill 对拍。
- 2026-07-14 首笔 V39 趋势腿 dry-run 持仓完成 entry/MFE 对齐：signal/entry timestamp 与研究回放一致，entry price 仅差约 `0.47 bps`；该空单最高 `4.8387ATR` 后未触发 `5ATR` TP，截至快照仍 open。V35/V39 保护线复测否决固定 `4.75ATR` TP、全局 `4.75 -> 4.25` / `4.90 -> 4.40` floor 和固定 16 根冷却；V2 保持当前规则，close reconciliation 待实际平仓。见 [near-TP runtime 对齐](runner-tracking/hype-15m-tb-mii-ens-v2-near-tp-runtime-reconciliation-2026-07-14.md)。
- 母版本状态：`HYPE-EMA-TB-V39` 为观察候选（未跨所迁移、未 walk-forward、未 live-executable 审计）；`HYPE-15M-MII-V1.4` 为 registered / not live-ready（未 runner dry-run）。组合继承全部 blocker（趋势腿：盘口级 stop 证据、闪崩尾部风险；V1.4：资金费、重启恢复、kill switch、同样本选参风险），并新增单账户杠杆叠加与 preempt 换仓时序风险。

## 数据与成本口径

- Exchange：Binance；Market：USD-M perpetual；Symbol：`HYPE/USDT:USDT`；Timeframe：`15m`。
- 数据：标准 raw/normalized 数据湖；首轮至 `2026-06-26T04:00:00Z`，第二轮至 `2026-07-08T05:30:00Z`；质量 gate 全通过。
- 趋势腿成本：`0.00085`/fill（家族 canonical 覆盖），计入 Binance funding。
- MII 腿成本：fee `0.001`/fill + slippage `4 bps`/fill（round-trip `0.28%`），funding 未计。
- 组合评估窗口从趋势腿 warmup（1600 根 15m）后开始：`2025-06-16T02:30:00Z` 起。

## 版本规则

- 本家族版本号只登记组合层定义，不改写任一母家族版本。
- 可登记版本必须写明：趋势腿版本、MII 腿版本、账户结构、冲突仲裁、入场延迟口径、成本口径、门禁结果、证据链接与 live-readiness 结论。
- `registered` 只代表研究主账留名；V2 既有 dry-run 授权不因 parity JSON 缺失自动改变，但新 promotion 前须补 Git-tracked 规范证据。若申请 live，必须完成 walk-forward、资金费统一、重启/kill-switch 与 online open/close reconciliation。
- `V2` 的主口径固定为 `single_v39_priority_k1`；双子账户 50/50 与 no-preempt 只作为对照，不属于 V2 实盘/单账户定义。

## 版本表

| Version | 组合定义 | 主口径指标 | 周度审计 | 状态 | 证据 |
| --- | --- | --- | --- | --- | --- |
| `HYPE-15M-TB-MII-ENS-V2` | `HYPE-EMA-TB-V39` + `HYPE-15M-MII-V1.4`；单账户 `single_v39_priority_k1`；V39 优先，V1.4 持仓遇 V39 信号强平让位；MII K+1 open | `+68192.54%` 总收益 / `-28.01%` 最大回撤 / Sharpe `5.79` / `291` 笔 / 胜率 `82.82%`；让位 `3` 次 | 过去一年 `274` 笔，`228` 胜 / `46` 负，胜率 `83.21%`；V39 `104` 笔，V1.4 `170` 笔；零交易周 `5` | `dry-run / not live-ready` | [组合回测报告](notes/hype-15m-tb-mii-ensemble-v39-v14-combination-backtest-2026-07-09.md)、[runner smoke](runner-tracking/hype-15m-tb-mii-ens-v2-runner-implementation-smoke-2026-07-09.md)、[runner parity](runner-tracking/hype-15m-tb-mii-ens-v2-runner-replay-parity-2026-07-09.md)、[runtime tracking](runner-tracking/hype-15m-tb-mii-ens-v2-runtime-live-pilot-2026-07-09.md)、[周度审计](notes/hype-15m-tb-mii-ens-v2-weekly-trade-audit-2026-07-09.md)、[validation spec](live-specs/hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md)、[live-executable 审计](diagnostics/hype-15m-tb-mii-ens-v2-live-executable-audit-2026-07-09.md) |

## 组合结构台账

### 2026-07-07 首轮：V35 + V1.3（数据湖至 `2026-06-26`）

| 结构 | 说明 | K+1 全样本 | 最大回撤 | Sharpe | 结论 |
| --- | --- | ---: | ---: | ---: | --- |
| `leg_v35_only` | V35 单独（对照） | `+7604.96%` | `-23.46%` | `4.78` | 收益主力腿 |
| `leg_mii_v13_k1` | V1.3 单独（对照，组合窗口） | `+496.37%` | `-21.54%` | `3.07` | 频率补充腿 |
| `portfolio_5050_rebal` | 双子账户 50/50 逐 K 再平衡 | `+2498.88%` | `-13.96%` | `5.99` | 回撤/Sharpe 最优，收益让渡大 |
| `portfolio_3070_rebal` | 30% V35 / 70% V1.3 | `+1410.68%` | `-11.85%` | `5.50` | 全表最浅回撤 |
| `single_v35_priority` | 单账户，V35 优先 + preempt | `+34987.81%` | `-28.01%` | `5.59` | 收益最高；回撤叠加、K+2 压力 `-33.59%` |
| `single_no_preempt` | 单账户，V1.3 持仓时放弃 V35 | `+23691.23%` | `-30.30%` | `5.23` | 劣于 preempt，不建议 |

两腿日收益相关系数 `-0.087`（组合窗口，K+1）。

### 2026-07-08 第二轮：V39 + V1.3（数据湖至 `2026-07-08`，含门禁校验）

门禁：数据质量 gate 全 `0`；V39 腿与 canonical 引擎逐 K 权益零差；V39 canonical 与主账登记值（`+9969.45% / -23.46% / 107 笔 / 79.44%`）逐项一致；V1.3 腿单仓链与 MII 引擎 K+1 `176` 笔、K+2 `181` 笔逐笔一致，终值零差。

| 结构 | 说明 | K+1 全样本 | 最大回撤 | Sharpe | 结论 |
| --- | --- | ---: | ---: | ---: | --- |
| `leg_v39_only` | V39 单独（对照） | `+9969.45%` | `-23.46%` | `4.81` | 收益主力腿，替代 V35 后腿内改进 |
| `leg_mii_v13_k1` | V1.3 单独（对照，组合窗口） | `+435.69%` | `-21.54%` | `2.85` | 最近 1 月 `-11.02%`，低波动期有负收益段 |
| `portfolio_5050_rebal` | 双子账户 50/50 逐 K 再平衡 | `+2748.51%` | `-13.96%` | `5.87` | 回撤/Sharpe 形状最好 |
| `portfolio_3070_rebal` | 30% V39 / 70% V1.3 | `+1433.32%` | `-11.85%` | `5.35` | 全表最浅回撤 |
| `single_v39_priority` | 单账户，V39 优先 + preempt（让位 `2` 次） | `+39829.29%` | `-28.01%` | `5.47` | 收益最高（`248` 笔 = V39 `107` + V1.3 `141`）；K+2 压力 `-33.82%` |
| `single_no_preempt` | 单账户，V1.3 持仓时放弃 V39 | `+27682.78%` | `-30.28%` | `5.15` | 劣于 preempt，不建议 |

两腿日收益相关系数 `-0.084`（组合窗口，K+1）。结构性结论与首轮一致；新增发现：最近 1 月 V1.3 腿把 `single_v39_priority` 拖到 `+5.89%`（V39 单独 `+23.40%`），组合在低波动期不只是退化为纯趋势腿，还可能被 V1.3 的负收益段拖累。

### 2026-07-09 第三轮：V39 + V1.4（数据湖至 `2026-07-08`，含门禁校验）

反转腿升级为 `HYPE-15M-MII-V1.4`（`V1.3 + min_rvol96 1.0 -> 0.85`，MII 主账进取观察版本）。门禁：数据质量 gate 全 `0`；V39 腿与 canonical 引擎逐 K 零差且与主账登记值一致；V1.4 engine 全样本与 MII 主账登记值一致（K+1 `+978.36% / -24.70% / 232 笔 / 84.91%`；K+2 `+535.54% / -38.30%`）；V1.4 腿单仓链与 MII 引擎 K+1 `221` 笔、K+2 `228` 笔逐笔一致，终值零差。

| 结构 | 说明 | K+1 全样本 | 最大回撤 | Sharpe | 结论 |
| --- | --- | ---: | ---: | ---: | --- |
| `leg_v39_only` | V39 单独（对照） | `+9969.45%` | `-23.46%` | `4.81` | 收益主力腿 |
| `leg_mii_v14_k1` | V1.4 单独（对照，组合窗口） | `+844.18%` | `-22.03%` | `3.42` | 比 V1.3 腿收益近翻倍，回撤持平；最近 1 月 `-3.50%` |
| `portfolio_5050_rebal` | 双子账户 50/50 逐 K 再平衡 | `+3733.19%` | `-13.96%` | `6.23` | 回撤/Sharpe 形状最好 |
| `portfolio_3070_rebal` | 30% V39 / 70% V1.4 | `+2206.12%` | `-13.60%` | `5.75` | 低回撤方向 |
| `single_v39_priority` | 单账户，V39 优先 + preempt（让位 `3` 次） | `+68192.54%` | `-28.01%` | `5.79` | 收益最高（`291` 笔 = V39 `107` + V1.4 `184`）；K+2 压力 `-30.98%` |
| `single_no_preempt` | 单账户，V1.4 持仓时放弃 V39 | `+51471.60%` | `-28.75%` | `5.54` | 劣于 preempt，不建议 |

两腿日收益相关系数 `-0.074`（组合窗口，K+1）。与 V1.3 轮（同窗口）相比：`single_v39_priority_k1` 从 `+39829%` 提升到 `+68193%` 而全样本回撤不变（回撤主导段来自 V39 腿）；K+2 延迟压力回撤从 `-33.82%` 收敛到 `-30.98%`；最近 1 月 MII 腿负收益从 `-11.02%` 缓和到 `-3.50%` 但仍拖累组合。注意 V1.4 的 `min_rvol96=0.85` 本身是同一数据湖上网格选出的进取观察点，组合改善继承该同样本选参风险。

2026-07-09 后续登记：该轮单账户 `single_v39_priority_k1` 被用户指定记录为 `V2`。登记不改变 live-readiness 结论；同日 live-executable 审计结论为 `FAILED / NO-GO`。近一年周度开单审计见 [hype-15m-tb-mii-ens-v2-weekly-trade-audit-2026-07-09.md](notes/hype-15m-tb-mii-ens-v2-weekly-trade-audit-2026-07-09.md)，live-executable 审计见 [hype-15m-tb-mii-ens-v2-live-executable-audit-2026-07-09.md](diagnostics/hype-15m-tb-mii-ens-v2-live-executable-audit-2026-07-09.md)。

## 证据

- 2026-09-03 README 压缩：完整原文与阅读顺序见 [decision-log.md](decision-log.md) 当日条目。
- 母版本参数细节以母家族主账为准：[hype-ema-tb-core-ledger.md](../15m-ema-trend-breakout/hype-ema-tb-core-ledger.md)、[hype-15m-mii-core-ledger.md](../15m-multi-indicator-intraday/hype-15m-mii-core-ledger.md)。

入口

- 首次组合回测（V35 + V1.3）：[hype-15m-tb-mii-ensemble-first-combination-backtest-2026-07-07.md](notes/hype-15m-tb-mii-ensemble-first-combination-backtest-2026-07-07.md)
- V39 + V1.3 组合回测含门禁：[hype-15m-tb-mii-ensemble-v39-combination-backtest-2026-07-08.md](notes/hype-15m-tb-mii-ensemble-v39-combination-backtest-2026-07-08.md)
- V39 + V1.4 组合回测含门禁：[hype-15m-tb-mii-ensemble-v39-v14-combination-backtest-2026-07-09.md](notes/hype-15m-tb-mii-ensemble-v39-v14-combination-backtest-2026-07-09.md)
- V2 近一年周度开单审计：[hype-15m-tb-mii-ens-v2-weekly-trade-audit-2026-07-09.md](notes/hype-15m-tb-mii-ens-v2-weekly-trade-audit-2026-07-09.md)
- V2 live validation spec（非实盘批准）：[hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md](live-specs/hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md)
- V2 live-executable 审计（失败）：[hype-15m-tb-mii-ens-v2-live-executable-audit-2026-07-09.md](diagnostics/hype-15m-tb-mii-ens-v2-live-executable-audit-2026-07-09.md)
- V2 runner implementation smoke：[hype-15m-tb-mii-ens-v2-runner-implementation-smoke-2026-07-09.md](runner-tracking/hype-15m-tb-mii-ens-v2-runner-implementation-smoke-2026-07-09.md)
- V2 首笔 V39 腿 near-TP runtime 对齐：[hype-15m-tb-mii-ens-v2-near-tp-runtime-reconciliation-2026-07-14.md](runner-tracking/hype-15m-tb-mii-ens-v2-near-tp-runtime-reconciliation-2026-07-14.md)
- 复现脚本：[research_hype_15m_tb_mii_ensemble_backtest.py](scripts/research_hype_15m_tb_mii_ensemble_backtest.py)（`--trend v35|v39 --mii v13|v14`）
- 保留产物：[hype_15m_tb_mii_ensemble_backtest_2026-07-07.json](artifacts/hype_15m_tb_mii_ensemble_backtest_2026-07-07.json)、[hype_15m_tb_mii_ensemble_backtest_v39_2026-07-08.json](artifacts/hype_15m_tb_mii_ensemble_backtest_v39_2026-07-08.json)、[hype_15m_tb_mii_ensemble_backtest_v39_v14_2026-07-09.json](artifacts/hype_15m_tb_mii_ensemble_backtest_v39_v14_2026-07-09.json)、[V2 合并周度 CSV](artifacts/hype_15m_tb_mii_ens_v2_single_v39_priority_k1_weekly_trades_1y_2026-07-09.csv)、[V2 分腿周度 CSV](artifacts/hype_15m_tb_mii_ens_v2_single_v39_priority_k1_weekly_trades_by_leg_1y_2026-07-09.csv) 及配套 equity/trades CSV。
- Decision log：[decision-log.md](decision-log.md)

## 已知风险

- 同样本组合，无 untouched OOS；权重与仲裁规则未做稳健性搜索。
- 单账户组合的超额收益来自资金利用率（趋势腿空档被 MII 腿复利），不是新 alpha；回撤同样叠加。
- 成本口径两腿不统一；MII 腿 funding 未计。
- 单账户全时段带 `2.5x-3x` 暴露，Binance 闪崩插针尾部风险大于趋势腿单独。
- MII 近期信号枯竭时组合退化为纯趋势腿；且 2026-06 段显示低波动期 MII 还可能贡献负收益（V1.4 最近 1 月 `-3.50%`）。

## 下一步（若继续）

- 统一成本口径并给 MII 腿补 funding 回放。
- 对仲裁规则做邻域测试（如 MII 持仓中允许趋势腿只在反向信号时 preempt）。
- 滚动窗口与随机切片复核组合回撤叠加的频率。
- 若要任何 promotion 讨论，先完成两个母家族各自的 live-executable 审计。
