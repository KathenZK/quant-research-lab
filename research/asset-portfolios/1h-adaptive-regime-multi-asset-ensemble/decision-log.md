## 2026-09-03 — 家族 README 压缩为路由页

- 决定：按家族 README ≤30 行路由页合同压缩 `README.md`（压缩前 42 行）。下列原文从 README 下沉到本决策记录，信息不删除、研究结论不变。

<details>
<summary>压缩前 README 全文</summary>

````markdown
# Binance-1H-Adaptive-Regime-Multi-Asset-Ensemble

- Full family name：`Binance-1H-Adaptive-Regime-Multi-Asset-Ensemble`
- Short id：`BIN-1H-AR-MAE`
- Market：Binance USD-M Futures perpetual，六个 symbol：`TRXUSDT`、`SOLUSDT`、`HYPEUSDT`、`ETHUSDT`、`BTCUSDT`、`BNBUSDT`
- Timeframe：`1h`

## 家族定义

本家族研究把六个单资产 `1h` adaptive-regime 家族的最新登记版本组合成跨资产组合：

- `TRX-1H-Adaptive-Regime-V3`
- `SOL-1H-Adaptive-Regime-V2`
- `HYPE-1H-Adaptive-Regime-V4`
- `ETH-1H-Adaptive-Regime-V3`
- `BTC-1H-Adaptive-Regime-V4`
- `BNB-1H-Adaptive-Regime-V3`

每个 sleeve 保持其家族冻结交易路径（信号、执行契约、成本、funding 全部不变）；组合层只做账户级持仓/资金规则，不做信号融合。这是跨资产组合研究线，隶属 `research/asset-portfolios/`，不改变任何成分家族的版本身份。

## 当前状态

- 当前版本：`BIN-1H-AR-MAE-V1`。
- 当前状态：`dry-run / not live-ready`；manifest 中 `six-asset-ensemble-dry-run` 已启用，live disabled。
- Runner：strict replay `371/371` parity PASS；持续 dry-run 与 strict replay 的 mark-price、cooldown 和 timeout 语义差异已登记，不能混作同一口径。
- 历史 pre-dry-run 研究发现：原始 V1 full DD `-21.43%` 穿破 `<20%` 门槛，账户 overlay 在成本压力下仍失败。这些是风险证据，不是当前 `NO-GO` 或禁止 dry-run 声明。
- 下一决策门：持续积累 runner-tracking 证据并完成 online open/close reconciliation；当前不得启用 live。

## 入口

- 主账：[binance-1h-ar-mae-core-ledger.md](binance-1h-ar-mae-core-ledger.md)
- 决策记录：[decision-log.md](decision-log.md)
- V1 完整复现规格（给同事/AI）：[binance-1h-ar-mae-v1-full-reproduction-spec-2026-07-07.md](specs/binance-1h-ar-mae-v1-full-reproduction-spec-2026-07-07.md)
- V1 简版规格：[binance-1h-ar-mae-v1-single-position-spec-2026-07-07.md](specs/binance-1h-ar-mae-v1-single-position-spec-2026-07-07.md)
- 首次组合回测（等权 `1/6`）：[binance-1h-ar-mae-first-combination-backtest-2026-07-07.md](notes/binance-1h-ar-mae-first-combination-backtest-2026-07-07.md)
- V1 单仓先到先得回测：[binance-1h-ar-mae-single-position-backtest-2026-07-07.md](notes/binance-1h-ar-mae-single-position-backtest-2026-07-07.md)
- V1 风险覆盖层诊断：[binance-1h-ar-mae-v1-risk-overlay-diagnostics-2026-07-09.md](notes/binance-1h-ar-mae-v1-risk-overlay-diagnostics-2026-07-09.md)
- TRX MACD 尾部风险根因与全局 overlay：[binance-1h-ar-mae-v1-trx-tail-risk-optimization-2026-07-10.md](notes/binance-1h-ar-mae-v1-trx-tail-risk-optimization-2026-07-10.md)
- TRX MACD 定向尾部覆盖层：[binance-1h-ar-mae-v1-trx-targeted-tail-overlay-2026-07-10.md](notes/binance-1h-ar-mae-v1-trx-targeted-tail-overlay-2026-07-10.md)
- V1 每周交易统计：[binance-1h-ar-mae-v1-weekly-stats-2026-07-09.md](notes/binance-1h-ar-mae-v1-weekly-stats-2026-07-09.md)
- 复现脚本：`scripts/research_binance_1h_ar_multi_asset_ensemble_backtest.py`、`scripts/research_binance_1h_ar_mae_single_position_backtest.py`
- 产物：`artifacts/`
````

</details>

# Binance-1H-Adaptive-Regime-Multi-Asset-Ensemble 决策记录

## 2026-07-20 状态口径同步

- 决策：基于当时 runner 运行事实，将 `BIN-1H-AR-MAE-V1` 研究状态统一为 `dry-run / not live-ready`；早期 `NO-GO / not promoted` 文字仅作为 historical pre-dry-run finding。当前实例授权与模式只以 quant-runner 为准。
- 证据：[主账](binance-1h-ar-mae-core-ledger.md)、[handoff](live-specs/binance-1h-ar-mae-v1-handoff-not-live-ready.md)、[runner tracking](runner-tracking/binance-1h-ar-mae-v1-runner-status.md)。

## 2026-07-07 创建家族并完成首次组合回测

- 背景：用户要求把 TRX/SOL/HYPE/ETH/BTC/BNB 六个 `1h` adaptive-regime 家族的最新登记版本组合成一个新策略并回测。
- 成分冻结：`TRX-1H-Adaptive-Regime-V3`、`SOL-1H-Adaptive-Regime-V2`、`HYPE-1H-Adaptive-Regime-V4`、`ETH-1H-Adaptive-Regime-V3`、`BTC-1H-Adaptive-Regime-V4`、`BNB-1H-Adaptive-Regime-V3`；每 sleeve 复用家族冻结交易路径，运行前与各家族主账 current full 指标硬校验一致（annual/DD/win/trades 零漂移）。
- 组合结构：六个子账户 sleeve 等权 `1/6`；主口径小时再平衡，对照口径不再平衡；权益曲线小时级构建，持仓中按 bar close mark-to-market，出场按冻结 `equity_ret` 对齐。
- 结果：全期（2024-08-17 至 2026-07-02 UTC）再平衡年化 `4.069x`、收益 `+1284.22%`、最大回撤 `-4.43%`、胜率 `89.66%`（`522` 笔、PF `6.627`）；六 sleeve 齐备段（2025-07-14 起）`3.821x / -4.43%`；reused holdout（2026-04-03 起）`1.625x / 75.38% win`；`last_7d` 为 `-1.71%`。六 sleeve 日收益相关性最大 `0.185`，平均毛暴露 `0.247x`。
- 决策：登记为 first combination diagnostic observation（未编号，不登记 Vx），状态 `NO-GO / not promoted / not live-ready`。理由：成分全部是 diagnostic NO-GO 版本；最近三个月是已揭盲 reused holdout 且组合明显走弱；组合层未做 K+2/滑点/成本压力与再平衡摩擦审计；六资产生产状态机、对账、缺 K fail-closed、kill switch 全部缺失。
- 证据：`notes/binance-1h-ar-mae-first-combination-backtest-2026-07-07.md`、`artifacts/binance_1h_ar_mae_first_backtest_2026-07-07.json`、`artifacts/binance_1h_ar_mae_equity_2026-07-07.csv`、`artifacts/binance_1h_ar_mae_trades_2026-07-07.csv`。

## 2026-07-07 单仓先到先得结构回测

- 背景：用户要求测试另一种组合结构——六个策略同时跑，但全账户同一时间只允许一笔持仓，谁先来信号就开谁的仓。
- 规则：单仓槽位先到先得；持仓期间忽略所有其他信号（不抢仓、不提前平仓）；新入场必须严格晚于上一笔出场 K；同小时平手按家族冻结 current-full 年化降序裁决（出现 `22` 次）；中选交易占用全额权益并按 sleeve 冻结杠杆执行（最高 `5x`）。
- 结果：候选 `522` 笔、中选 `371` 笔、阻塞跳过 `151` 笔；全期年化 `287.01x`、最大回撤 `-21.43%`、胜率 `90.30%`、PF `6.862`；reused holdout `7.67x / +65.31% / -19.79% DD / 78.57% win`；`last_7d` 仅 `+0.46%` 且期间回撤 `-15.92%`。
- 决策：登记为 `BIN-1H-AR-MAE-SINGLE-POS-2026-07-07` combination diagnostic observation，`NO-GO / not promoted / not live-ready`。理由：full 与 `last_6m/1y` 回撤 `-21.43%` 穿破 `<20%` 硬门槛；全期收益是样本内强势成分在全额高杠杆下的复利放大，无实盘意义；阻塞后未做逐 K 联合状态机重演（sleeve 内 cooldown 反事实是近似）；成分全部 NO-GO；组合层压力与生产执行审计缺失。
- 证据：`notes/binance-1h-ar-mae-single-position-backtest-2026-07-07.md`、`artifacts/binance_1h_ar_mae_single_position_2026-07-07.json`、`artifacts/binance_1h_ar_mae_single_position_equity_2026-07-07.csv`、`artifacts/binance_1h_ar_mae_single_position_trades_2026-07-07.csv`。

## 2026-07-07 登记为 V1

- 背景：用户明确要求“把这个组合策略记为 V1”。这里的“这个组合策略”按上下文指 2026-07-07 刚完成的全账户单仓、先到先得结构，而不是此前等权 `1/6` observation。
- 登记版本：`Binance-1H-Adaptive-Regime-Multi-Asset-Ensemble-V1`（短 id：`BIN-1H-AR-MAE-V1`）。
- 冻结身份：成分固定为 TRX V3、SOL V2、HYPE V4、ETH V3、BTC V4、BNB V3；全账户单仓槽位；先到先得；持仓期间忽略其他全部信号；同小时平手按家族 current-full 年化降序；中选交易占用全额权益并按 sleeve 冻结杠杆执行。
- 指标：full `287.01x / -21.43% DD / 90.30% win / 371 trades / PF 6.862`；reused holdout `7.67x / +65.31% / -19.79% DD / 78.57% win / 42 trades`；`last_7d +0.46% / -15.92% DD`；`last_1m +58.18% / -15.92% DD`；`last_3m +66.01% / -19.79% DD`；`last_6m +1089.35% / -21.43% DD`；`last_1y +13315.39% / -21.43% DD`。
- 决策：登记为 `V1` 但状态保持 `NO-GO / not promoted / not live-ready`。理由：full 与 `last_6m/1y` 回撤 `-21.43%` 穿破 `<20%` 硬门槛；阻塞后未做逐 K 联合状态机重演；成分全部是 diagnostic NO-GO；组合层压力与生产执行审计缺失。
- 证据：`specs/binance-1h-ar-mae-v1-full-reproduction-spec-2026-07-07.md`、`specs/binance-1h-ar-mae-v1-single-position-spec-2026-07-07.md`、`binance-1h-ar-mae-core-ledger.md`、`notes/binance-1h-ar-mae-single-position-backtest-2026-07-07.md`。

## 2026-07-09 quant-runner dry-run 接入

- 背景：用户要求在 `quant-runner` 实现 `BIN-1H-AR-MAE-V1`，达到可跑 dry-run。
- 实现：`kind = six_asset_ensemble`；六资产联合状态机 dry-run（非 lab 冻结交易路径后筛选的 diagnostic 近似）；live 禁止；`configs/dryrun.toml` 增加 `six-asset-ensemble-dry-run`。
- 验证：本地 `smoke-test` 通过；本地 `run-once` 返回 `flat_no_signal`（当前小时无 due 候选）。
- 决策：dry-run 可观察，但状态仍为 `NO-GO / not promoted / not live-ready`。未改变 promotion 结论；`replay-dry-run` 与研究路径对拍未完成。
- 证据：`runner-tracking/binance-1h-ar-mae-v1-runner-status.md`。

## 2026-07-09 runner replay 对拍零误差 + spec 修正 + runner 指标 bug 修复

- 背景：用户要求审核 `quant-runner` 中 `six_asset_ensemble` 实现与 spec 的对齐情况，并回放对拍 lab 回测。
- 参数审核：runner 冻结 leg 参数与六个家族冻结引擎配置逐字段一致（含 V1 基线继承的隐含字段与冻结 sleeve priorities）；spec 文档发现三处与冻结路径不符（ETH BB `side_mode`/`max_atr_bps`、ETH RSI `max_atr_bps`/`require_body_dir`/`max_aligned_funding_bps`、TRX Stoch 漏记 `max_dist_ema_bps`/`max_aligned_funding_bps`），已同步修正 lab 与 runner 两份 spec；代码与冻结路径本来正确。
- runner bug：审核发现 `indicators::rolling_mean` 被前导 NaN 永久污染，导致 `stoch_d` 全 NaN、TRX/HYPE Stoch 腿在 runtime/replay 中永不出信号；已修复为 pandas `rolling(min_periods=window)` 语义。
- replay 对拍：runner 新增 `replay-dry-run` 严格回放（Binance 公共 klines+funding，数据边界锁定 lab parquet 快照），复现 candidates `522` / selected `371` / skipped `151` / ties `22`，逐笔 `371/371` 与冻结 trades CSV 全字段一致（equity_ret 误差 <1e-9），full/reused_holdout/last_* 窗口指标与 V1 spec 期望一致。
- dry-run：本地 `smoke-test`、`run-once`（`flat_no_signal`）、重复周期幂等（`already_processed`）通过。
- 决策：runner 引擎实现确认与 V1 冻结路径一致；V1 状态不变，仍为 `registered diagnostic / NO-GO / not promoted / not live-ready`。
- 证据：`runner-tracking/binance-1h-ar-mae-v1-runner-status.md`、`artifacts/binance_1h_ar_mae_v1_runner_replay_parity_2026-07-09.json`、`specs/binance-1h-ar-mae-v1-full-reproduction-spec-2026-07-07.md`（修正）。

## 2026-07-09 V1 风险覆盖层与 TRX MACD 消融诊断

- 背景：用户要求按优化建议做一轮 V1 风险约束、TRX MACD 消融与成本压力诊断。
- 方法：保持 V1 六个冻结 sleeve 交易路径与全账户单仓先到先得选择规则；只在账户层叠加风险覆盖层，包括全局 `3x`/`2.5x` cap、TRX `macd_flip` cap 或剔除、`>3x` 候选过滤，以及 cap 后的额外 `4 bps/fill` 滑点和 double fee+slippage 压力。成本压力为交易后账户层近似，不是逐 K 成交重演。
- 结果：V1 baseline 复现为 full `287.01x / -21.43% DD`；全局 `3x` cap 为 `192.49x / -19.99% DD`，但加 `4 bps/fill` 额外滑点后失败为 `134.46x / -20.18% DD`；全局 `2.5x` cap 为 `122.81x / -18.68% DD`，加 `4 bps/fill` 后仍为 `88.47x / -19.19% DD`；double fee+slippage 下 `3x` 与 `2.5x` 都失败，最差回撤约 `-25.5%`。
- 决策：登记为未编号 diagnostic observation `BIN-1H-AR-MAE-V1-RISK-OVERLAY-2026-07-09`，不登记 `V1.1/V1.2`，状态 `NO-GO / not promoted / not live-ready`。若后续要冻结新版本，优先研究 `V1 + 全账户单笔暴露 cap 2.5x`，并先完成逐 K 联合状态机重演与真实 K+2/成本压力。
- 证据：`notes/binance-1h-ar-mae-v1-risk-overlay-diagnostics-2026-07-09.md`、`artifacts/binance_1h_ar_mae_v1_risk_overlay_diagnostics_2026-07-09.json`、`artifacts/binance_1h_ar_mae_v1_risk_overlay_matrix_2026-07-09.csv`、`scripts/research_binance_1h_ar_mae_v1_risk_overlay_diagnostics.py`。

## 2026-07-10 TRX MACD 尾部根因与全局风险预算诊断

- 背景：TRX V3 clean tune 已处于局部最优；组合层的重点改为处理 `TRX macd_flip 5x` 高暴露尾部，而不是继续追单资产收益。
- 根因：V1 中选 TRX MACD `37` 笔仅 `2` 笔最终亏损，但最差单笔账户 MAE `-17.17%`、最大计划初始止损风险 `24.72%`。组合最深 close-marked DD 由 BNB 连续亏损先造成账户下沉，再由一笔 TRX MACD 盈利交易到达 TP 前的浮亏加深。
- 全局方案：prefit-only 选中 `1.0% signal-ATR budget + 8%/12% account-DD cap 2x/1x`，将 full DD 压到 `-14.93%`、TRX 最差 MAE 压到 `-7.09%`，但 full 年化只剩 `7.88x`，reused holdout 只剩 `+1.70%`；对所有 sleeve 过度降杠杆。
- 决策：不采用全局 `1% ATR` 作为下一版；继续研究只作用于 TRX MACD 的定向覆盖层。
- 证据：`notes/binance-1h-ar-mae-v1-trx-tail-risk-optimization-2026-07-10.md`、`artifacts/binance_1h_ar_mae_v1_trx_tail_risk_2026-07-10.json`、`scripts/research_binance_1h_ar_mae_v1_trx_tail_risk_optimization.py`。

## 2026-07-10 TRX MACD 定向尾部覆盖层

- 方法：保持 V1 六 sleeve、单仓先到先得选择、entry/exit、费用、滑点和 funding 全部冻结；只有中选 TRX MACD 暴露可变。sizing 只使用 signal ATR 与入场前账户 close-marked DD。
- prefit-only 选择：计划初始止损账户风险 `<=10%`；入场前账户 DD 达 `2%` 时 TRX MACD cap `3x`，达 `6%` 时 cap `2x`。门槛为 prefit close DD `<20%`、TRX 最差 MAE `<10%`、账户状态叠加 MAE `<20%`，且 prefit annual 至少保留 V1 的 `50%`；排序优先保留收益。
- 冻结后结果：full `231.59x / -19.99% DD / 90.30% win / 371 trades`，相对 V1 `287.01x / -21.43%`；reused holdout `6.31x / +57.37% / -17.38% DD`。TRX MACD `34/37` 笔降暴露，平均 `5.00x -> 3.03x`，最大计划止损风险 `24.72% -> 10.00%`，最差 MAE `-17.17% -> -9.71%`，账户状态叠加 MAE `-23.10% -> -18.80%`。
- 压力：额外 `4 bps/fill` full `160.18x / -20.18% DD`；double-cost `62.93x / -27.53% DD`。TRX-only 网格无法突破 `-20.18%` 的额外滑点 DD 下限，因为 TRX 风险压下后 close-DD 主因转为 BNB 连续亏损；保守 account-tail 主因转为 HYPE DI 与 SOL Donchian。
- 决策：TRX 定向规则是目前更有效的风险—收益折中，但仍为未编号 diagnostic observation，不登记 `V2`；下一步应测试轻量跨 sleeve account-tail guard 或 BNB loss-cluster 专项，而不是继续压 TRX。
- 证据：`notes/binance-1h-ar-mae-v1-trx-targeted-tail-overlay-2026-07-10.md`、`artifacts/binance_1h_ar_mae_v1_trx_targeted_tail_2026-07-10.json`、`artifacts/binance_1h_ar_mae_v1_trx_targeted_tail_matrix_2026-07-10.csv`、`scripts/research_binance_1h_ar_mae_v1_trx_targeted_tail_overlay.py`。

## 2026-07-11 dry-run platform `trades` 漏记修复

- 背景：线上 `six-asset-ensemble-dry-run` 已持有 BNB，但 platform ledger `trades` 无记录；`events`/`strategy_health` 正常。
- 根因：runtime 未接 `emit_ledger_trade_open`。
- 处理：quant-runner 补齐 open/holding/close 的 `trades` 写入，增加 closed trade 不得被重复 open 重开的终态保护；并对当前 open 持仓做 DB 回填。状态仍 `NO-GO / not promoted / not live-ready`。
- SPEC 复核：strict replay 的 371/371 逐笔 parity 仍有效；持续 dry-run runtime 是近似联合状态机。已修复 funding 获取失败静默按零、runtime ledger PnL 未计 funding及 Runner SPEC dry-run 身份冲突；跨 symbol 最新 K 不一致时可能混用执行小时的风险仍待处理。任何 promotion 讨论前仍必须统一既有 runtime 差异或建立正式新规格。
- 证据：`runner-tracking/binance-1h-ar-mae-v1-runner-status.md`。

## 2026-07-12 ledger / funding 修复部署

- Runner `main@282bf9c` 已通过 GitHub Actions governance、quality、Linux release
  build，并部署到 `quant-runner-dryrun.service`。
- 重启后服务 active、journal 无 warning/error、全部 strategy health 为 `ok`；
  six-asset 当前 flat。已有 candle-count dry-run short 从本地状态正常恢复。
- live 进程未重启；本次部署不改变 `NO-GO / not promoted / not live-ready`。
- 证据：`runner-tracking/binance-1h-ar-mae-v1-runner-status.md`。
