## 2026-09-03 — 家族 README 压缩为路由页

- 决定：按家族 README ≤30 行路由页合同压缩 `README.md`（压缩前 39 行）。下列原文从 README 下沉到本决策记录，信息不删除、研究结论不变。

<details>
<summary>压缩前 README 全文</summary>

````markdown
# HYPE-15M-Trend-Breakout-Multi-Indicator-Ensemble

Alias：`HYPE-15M-TB-MII-ENS`

Created：2026-07-07

## 边界

本目录研究 Binance HYPEUSDT 永续 `15m` 上把两个既有家族版本组合成一个新策略：

- 趋势腿：`HYPE-EMA-Trend-Breakout` 的 V35 或 V39（EMA96/384 趋势突破 + ADX/成交量/1h 确认，K+2 open 入场，5ATR 止盈 / 7ATR 硬止损 / ADX22 delayed3 / 384 根 timeout，ATR 动态仓位上限 3x；V39 = V35 + `long_vol_min 0.35` + `short_target_atr_pct 0.022` - 空头 1h EMA 确认）。
- 反转腿：`HYPE-15M-Multi-Indicator-Intraday` 的 V1.3 或 V1.4（RSI(7) 40/60 反转 + MACD 方向 + ATR96 0.75%-2.80%，K+1 open 入场，ATR96 bracket TP=1.25x / SL=5.0x / hold=24，固定 2.5x 暴露；V1.3 `RVOL96>=1.0`，V1.4 `RVOL96>=0.85`）。

本目录不修改两个母家族的版本定义；母版本口径以各自主账为准：

- [hype-ema-tb-core-ledger.md](../15m-ema-trend-breakout/hype-ema-tb-core-ledger.md)
- [hype-15m-mii-core-ledger.md](../15m-multi-indicator-intraday/hype-15m-mii-core-ledger.md)

## 当前状态

- 当前状态：`V2 dry-run active / replay parity PASS / live disabled / not live-ready`。
- 当前登记版本：`V2 = HYPE-EMA-TB-V39 + HYPE-15M-MII-V1.4`，单账户 `single_v39_priority_k1`（V39 优先 + V1.4 强平让位）。
- 首次组合回测（V35 + V1.3）见 [hype-15m-tb-mii-ensemble-first-combination-backtest-2026-07-07.md](notes/hype-15m-tb-mii-ensemble-first-combination-backtest-2026-07-07.md)。
- V39 + V1.3 组合回测（含门禁校验）见 [hype-15m-tb-mii-ensemble-v39-combination-backtest-2026-07-08.md](notes/hype-15m-tb-mii-ensemble-v39-combination-backtest-2026-07-08.md)。
- V39 + V1.4 组合回测（含门禁校验）见 [hype-15m-tb-mii-ensemble-v39-v14-combination-backtest-2026-07-09.md](notes/hype-15m-tb-mii-ensemble-v39-v14-combination-backtest-2026-07-09.md)。
- V2 近一年周度开单审计见 [hype-15m-tb-mii-ens-v2-weekly-trade-audit-2026-07-09.md](notes/hype-15m-tb-mii-ens-v2-weekly-trade-audit-2026-07-09.md)。
- V2 live validation spec（非实盘批准）见 [hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md](live-specs/hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md)。
- V2 live-executable 审计（失败）见 [hype-15m-tb-mii-ens-v2-live-executable-audit-2026-07-09.md](diagnostics/hype-15m-tb-mii-ens-v2-live-executable-audit-2026-07-09.md)。
- 家族主账：[hype-15m-tb-mii-ens-core-ledger.md](hype-15m-tb-mii-ens-core-ledger.md)。

## 阅读顺序

1. `../../README.md`
2. `../README.md`
3. 本文件
4. [hype-15m-tb-mii-ens-core-ledger.md](hype-15m-tb-mii-ens-core-ledger.md)
5. [decision-log.md](decision-log.md)
6. [notes/](notes/) 内具体报告
7. [live-specs/](live-specs/) 内 runner / dry-run / live validation 规格
````

</details>

# Decision Log

## 2026-08-18 — 同组 halt，观察窗口再断

- `hype-tb-mii-ens-dry-run` 在 `2026-08-17 19:00Z` / `19:15Z` 两次 `missing Binance kline`（NextOpen 取价），随后被共享 15m 组 halt。模拟多仓已在 `19:16Z` 重启 cycle 按 `indicator_exit` 平掉。自 `19:19Z` 起观察窗口断裂；研究身份不变。证据：[hype-15m-group-halt-2026-08-17.md](../15m-ema-trend-breakout/runner-tracking/hype-15m-group-halt-2026-08-17.md)。

## 2026-08-04 — 缺失 parity 证据但保留用户授权

- 决定：规范 parity JSON 已不在干净 checkout 中，`HYPE-15M-TB-MII-ENS-V2` 证据健康度标记为 `MISSING_EVIDENCE`。文件缺失阻止新 promotion，不能自动决定实例启停；实际授权与模式只以 quant-runner 为准，历史叙事报告见 [`hype-15m-tb-mii-ens-v2-runner-replay-parity-2026-07-09.md`](runner-tracking/hype-15m-tb-mii-ens-v2-runner-replay-parity-2026-07-09.md)。

## 2026-07-15 V39 腿慢启动主动退出复测

- 问题：用户提出对当前参与 V2 production dry-run 的 V39 趋势腿测试“持仓 6–8h 且历史 MFE<1.5ATR 后 next-open 主动退出”。
- 结果：V39 单腿 base 为 `+8789.36% / -23.46% / Sharpe4.62`；6h 规则仅 `+5324.46% / -23.46% / 4.24`、资金保留 `61.02%`，8h 规则 `+6574.67% / -23.88% / 4.38`、保留 `75.09%`，分别误杀 5/2 笔最终 TP5；同向 episode reset 也未挽救。
- 决定：不修改 `HYPE-15M-TB-MII-ENS-V2` dry-run 配置，不改变已通过 parity 的 V39 腿状态机，不启用 live。独立母版本 V39 仍是 registered；实际 dry-run 身份为包含 V39 趋势腿的组合 V2。
- 证据：[V39 慢启动主动退出报告](../15m-ema-trend-breakout/diagnostics/hype-ema-tb-v39-slow-start-active-exit-2026-07-15.md)。

## 2026-07-14 V39 腿临近 TP 回吐与保护线复测

- 运行证据：`hype-tb-mii-ens-dry-run` 的 `ema_tb_v39` 空单于 `2026-07-13T14:45Z` 以 `64.156` 入场，最大 MFE `4.8387ATR`，截至 `2026-07-14T07:45Z` 仍 open；runner signal/entry timestamp 与研究回放一致，entry price 仅差约 `0.47 bps`，close 对齐待实际平仓后补充。
- 决定：保持 V2 当前 `5ATR TP / 7ATR SL` 和 runner 配置不变。`4.75 -> lock 4.25` 虽能在本次锁定约 `+6.62%`，但 V39 full 从 `+9969.45%` 降到 `+7417.48%` 且会立即同向重入；固定 16 根冷却、`4.90 -> 4.40` 和固定 `4.75ATR TP` 也均不成立。不修改 dry-run，不启用 live。
- 证据：[runtime 对齐报告](runner-tracking/hype-15m-tb-mii-ens-v2-near-tp-runtime-reconciliation-2026-07-14.md)、[V35/V39 floor 复测](../15m-ema-trend-breakout/notes/hype-ema-tb-v35-v39-near-tp-floor-diagnostic-2026-07-14.md)。

## 2026-07-09 V2 production dry-run deployed

- 问题：用户要求把 V2 “发到线上去”，本次范围确认为只部署/重启 `dryrun` 服务，不开启 live。
- 做法：将 `quant-runner` 当前分支快进合入 `main` 并推送到 `origin/main`；服务器 `47.80.57.36:/home/admin/quant-runner` 从 `origin/main` fast-forward 到 `0391054 Restore TB-MII ensemble V2 spec.`，远端执行 `cargo fmt --check`、`cargo test -p quant-runner`、`cargo build --release` 后只重启 `quant-runner-dryrun.service`。
- 验证：本地与远端测试均通过（`61` library tests + `2` integration tests）；`quant-runner-dryrun.service` 重启后 active/running，`MainPID=740299`；10 分钟 warning/error journal 检查无记录；`strategy_health` 显示 `hype-tb-mii-ens-dry-run` 为 `ok`、`position_open=0`、`last_bar_ts=2026-07-09T12:00:00+00:00`、`updated_at=2026-07-09T12:23:38.905367617+00:00`。首个运行周期输出 `event=holding`、`active_leg=none`、`position_open=false`、pending signal 均为 `null`。
- 决定：状态更新为 `production dry-run deployed and healthy / disabled live pilot code path implemented / live not enabled / not promoted`。本次未重启 live 服务，也未将 `hype-tb-mii-ens-live` 设为 enabled。下一步是累计 dry-run 运行窗口并抽取 open/close/fill 生命周期数据做回测/运行对齐。
- 证据：[runtime/live-pilot tracking](runner-tracking/hype-15m-tb-mii-ens-v2-runtime-live-pilot-2026-07-09.md)、[V2 主账](hype-15m-tb-mii-ens-core-ledger.md)。

## 2026-07-09 V2 continuous runtime 与 disabled live pilot 代码路径实现

- 问题：用户要求完成 `V2 小额实盘执行链计划`，达到可小额 live pilot 的代码条件，但默认不直接开启 live。
- 做法：在 `quant-runner` 抽出 V2 纯决策 helper，扩展 `TbMiiEnsembleState`，新增 `trading/runner/tb_mii_ensemble.rs` continuous runtime；实现 V39 K+2、MII K+1、MII open 型出场先于 V39、V39 优先 preempt、live 市价入场与 reduce-only TP/SL、preempt close-confirm-open、交易所 position/open-orders 核对、保护单一次恢复、fail-closed 门禁；新增 enabled dry-run 配置 `hype-tb-mii-ens-dry-run` 和 disabled live 配置 `hype-tb-mii-ens-live`。
- 验证：`cargo fmt --check`、`cargo clippy --all-targets`、`cargo test` 全通过；`smoke-test --name hype-tb-mii-ens-dry-run` 返回 `ok=true`；full replay 命令 `replay-dry-run --limit 38900 --end-ts 2026-07-08T05:30:00Z` 仍为 `291` 笔 / V39 `107` / V1.4 `184` / preempt `3`，窗口 `2025-06-16T02:30:00Z` 至 `2026-07-08T05:30:00Z`。
- 决定：状态更新为 `continuous dry-run runtime implemented / disabled live pilot code path implemented / live not enabled / not promoted`。这满足代码侧 live pilot 前置条件，但不等于实盘批准；下一步需要用户提供独立 subaccount env、确认小余额规模，并显式批准把 live pilot `enabled = true`。先跑 dry-run 观察并回写线上生命周期数据。
- 证据：[runtime/live-pilot tracking](runner-tracking/hype-15m-tb-mii-ens-v2-runtime-live-pilot-2026-07-09.md)、[V2 主账](hype-15m-tb-mii-ens-core-ledger.md)、[runner-side spec](file:///Users/ZK/OpenCode/quant-runner/crates/quant-runner/src/runner/strategies/hype_tb_mii_ensemble/HYPE-15M-TB-MII-ENS-V2-SPEC.md)。

## 2026-07-09 V2 runner replay 全样本对拍通过（交易路径）

- 问题：用户希望尽快小资金实盘，要求先确认 runner 实现与 spec 的对齐情况、replay 是否与研究引擎一致。
- 做法：runner commit `53e4b6d`（含第二轮对齐修复：MII open 型出场先于 V39 入场、逐 K mark-to-market、公共指标复用、warmup 2500）。用 `replay-dry-run --limit 38900 --end-ts 2026-07-08T05:30:00Z` 拉取 Binance 公共 kline `37,165` 根闭合 15m K，覆盖组合评估起点 `2025-06-16T02:30:00Z` 至数据湖末尾，对拍研究脚本 `single_v39_priority_k1` 的 291 笔逐笔路径。
- 结果：逐笔路径零不一致——`291` 笔、V39 `107` + V1.4 `184`、preempt `3`、出场原因逐类计数一致（词表映射 1:1）、entry/exit 价格最大相对差 `4.33e-16`、allocation 精确一致。MII 腿逐笔收益 engine-exact（最大差 `6.7e-16`）；V39 腿逐笔收益最大差 `0.48%`，全部来自 runner smoke 不计 funding。整体：`+69593%` vs 研究含 funding `+68193%`，回撤 `-27.85%` vs `-28.01%`，胜率同为 `82.82%`；6m/3m 近期窗口（137 笔 / 72 笔、腿分布、preempt）全部一致。
- 决定：验证门禁第 3 条（组合 replay gate）交易路径部分判定 PASS，状态更新为 `runner replay parity PASS (trade path) / live-executable FAILED / NO-GO / not promoted / not dry-run handoff / not live-ready`。**不构成 live 批准**：连续 dry-run runtime、live preempt 原子流程、保护单、重启恢复、kill switch、V39 funding 记账仍未实现。若用户坚持小资金 pilot，顺序为：实现连续 runtime -> shadow/dry-run 差异报告 -> live-executable 审计 -> 用户显式批准。
- 证据：[replay parity 报告](runner-tracking/hype-15m-tb-mii-ens-v2-runner-replay-parity-2026-07-09.md)、[runner 逐笔 CSV](artifacts/hype_15m_tb_mii_ens_v2_runner_replay_parity_trades_2026-07-09.csv)、[对拍摘要 JSON](artifacts/hype_15m_tb_mii_ens_v2_runner_replay_parity_summary_2026-07-09.json)。

## 2026-07-09 V2 runner replay validation kind implemented

- 问题：用户要求按 `live-specs/hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md` 在 `quant-runner` 实现 V2 策略。
- 做法：在 `quant-runner` 新增 `hype_tb_mii_ensemble` strategy kind、runner-side SPEC、固定代码默认参数、V39 + MII V1.4 组合 replay 状态机、`replay-dry-run` CLI 分支和 disabled validation TOML 实例。普通连续 dry-run/live runtime 显式 blocked，避免未审计 preempt 下单路径误运行。
- 验证：`cargo fmt`、`cargo clippy --all-targets --all-features`、`cargo test` 均通过；`cargo run -- smoke-test --config configs/dryrun.toml --name hype-tb-mii-ens-v2-validation` 返回 `ok=true`；`cargo run -- replay-dry-run --config configs/dryrun.toml --name hype-tb-mii-ens-v2-validation --limit 1000` 跑通，窗口 `2026-06-28T21:45:00Z` 至 `2026-07-09T07:30:00Z`，`1000` 根 K，输出 `2` 笔（V39 `1`、MII `1`、preempt `0`）。
- 决定：移除“runner kind 不存在”这一 replay validation blocker；状态更新为 `runner replay validation implemented / live-executable FAILED / NO-GO / not promoted / not dry-run handoff / not live-ready`。这不构成 dry-run handoff 或 live approval；下一步必须做标准数据湖 parity，对拍 `291` 笔、V39 `107`、MII V1.4 `184`、preempt `3` 和权益曲线。
- 证据：[runner implementation smoke](runner-tracking/hype-15m-tb-mii-ens-v2-runner-implementation-smoke-2026-07-09.md)、[V2 live validation spec](live-specs/hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md)、[V2 主账](hype-15m-tb-mii-ens-core-ledger.md)。

## 2026-07-09 V2 live-executable 审计失败

- 问题：用户要求对 `HYPE-15M-TB-MII-ENS-V2` 做 live-executable 验证，确认是否可以进入 dry-run/live。
- 做法：核对 V2 live validation spec、组合回测报告、Python 组合状态机、本地 [`quant-runner`](file:///Users/ZK/OpenCode/quant-runner) 与 [`hype-trend`](file:///Users/ZK/OpenCode/hype-trend) 静态实现。生成静态检查 JSON，并撰写 diagnostics 报告。
- 结果：研究侧数据质量与 Python replay 门禁保持通过；执行侧审计失败。主要 blocker：`quant-runner` 没有 `hype_tb_mii_ensemble` / V2 strategy kind，没有 `HYPE-EMA-TB-V39` trend-breakout kind；现有 `hype_mii` 默认仍是 `HYPE-15M-MII-V1.3 / min_rvol96=1.0`，不是 V1.4；`hype-trend` 是 V35 单腿 runner；组合全局单仓、V39 优先、V1.4 preempt 原子强平、V2 state/restart、funding 统一、kill switch 和 notional cap 均无实现证据。
- 决定：状态更新为 `live validation spec draft / live-executable FAILED / NO-GO / not promoted / not dry-run / not live-ready`。不得直接 live、不得直接替换 V35 live、不得与 V35 live 同账户同 symbol 并行真单。下一步只能先做 V2 runner 实现与标准数据湖 replay 对拍。
- 证据：[V2 live-executable 审计](diagnostics/hype-15m-tb-mii-ens-v2-live-executable-audit-2026-07-09.md)、[静态检查摘要](artifacts/hype_15m_tb_mii_ens_v2_live_executable_static_audit_2026-07-09.md)、[V2 live validation spec](live-specs/hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md)。

## 2026-07-09 V2 live validation spec 导出（非实盘批准）

- 问题：用户说明此前 `HYPE-EMA-Trend-Breakout-V35` 在实盘运行过，现在希望把 `HYPE-15M-TB-MII-ENS-V2` “实盘看看”，要求先出一份 live spec 文档。
- 做法：导出 V2 live validation spec，明确 V2 不是 V35 runner 配置改参即可运行，而是需要新增组合状态机、`HYPE-15M-MII-V1.4` 腿、全局单仓仲裁、`preempted_by_v39` 强平让位流程、保护单、重启恢复、交易所对账和 kill switch。
- 关键边界：V2 live 前不得与现有 V35 live service 在同一 Binance 账户 / `HYPEUSDT` 上同时真单运行；若只做 shadow/dry-run，可以并行但不得提交真实订单或撤改 V35 订单。preempt 必须先取消 V1.4 保护单、只减仓平 V1.4、确认 flat，再开 V39。
- 决定：当时状态更新为 `live validation spec draft / NO-GO / not promoted / not live-ready`，不构成 dry-run 或 live 批准。后续同日 live-executable 审计结论为 `FAILED / NO-GO`，当前状态以主账为准：`live validation spec draft / live-executable FAILED / NO-GO / not promoted / not dry-run / not live-ready`；下一步应先实现 runner replay，对拍标准数据湖 `291` 笔、V39 `107` 笔、V1.4 `184` 笔、preempt `3` 次，再做 shadow/dry-run。
- 证据：[V2 live validation spec](live-specs/hype-15m-tb-mii-ens-v2-live-validation-spec-not-live-ready-2026-07-09.md)、[V2 主账](hype-15m-tb-mii-ens-core-ledger.md)。

## 2026-07-09 V2 登记与近一年周度开单审计

- 问题：用户要求把 `HYPE-EMA-TB-V39 + HYPE-15M-MII-V1.4` 组合记录为 `V2`，并查看过去一年每周开单数与周胜率。
- 登记：`V2` 固定为单账户主口径 `single_v39_priority_k1`，即 V39 优先、V1.4 只在 V39 空档开仓，若 V39 入场信号出现则强平 V1.4 让位；MII 腿使用 K+1 open。
- 周度审计：窗口锚定数据末尾 `2026-07-08T05:30:00Z` 向前一年；按 `entry_ts` 归入 UTC ISO 周。过去一年共 `274` 笔，`228` 胜 / `46` 负，整体胜率 `83.21%`；V39 `104` 笔，V1.4 `170` 笔；有交易周 `48` 个，零交易周 `5` 个；最高开单周为 `2026-W05`，`20` 笔，胜率 `90.00%`。
- 决定：当时主账登记为 `V2 registered diagnostic / NO-GO / not promoted / not live-ready`。登记只表示组合版本留名，不构成 promotion；后续同日 live-executable 审计结论为 `FAILED / NO-GO`，当前状态以主账为准：`live validation spec draft / live-executable FAILED / NO-GO / not promoted / not dry-run / not live-ready`。V2 仍继承 V39 未跨所/未 walk-forward/未 live-executable 审计、V1.4 未 runner dry-run 与同样本选参风险，以及组合特有 preempt 换仓时序风险。
- 证据：[组合回测报告](notes/hype-15m-tb-mii-ensemble-v39-v14-combination-backtest-2026-07-09.md)、[V2 周度审计](notes/hype-15m-tb-mii-ens-v2-weekly-trade-audit-2026-07-09.md)、[V2 周度 CSV](artifacts/hype_15m_tb_mii_ens_v2_single_v39_priority_k1_weekly_trades_1y_2026-07-09.csv)。

## 2026-07-09 V39 + V1.4 组合复测（含门禁校验）

- 问题：反转腿从 `HYPE-15M-MII-V1.3` 升级为 `HYPE-15M-MII-V1.4`（`min_rvol96 1.0 -> 0.85`）后，与 `HYPE-EMA-TB-V39` 的组合结果如何；全链路门禁校验。
- 门禁：数据质量 gate 全 `0`（同 2026-07-08 窗口）；V39 腿与 canonical 引擎逐 K 零差且与主账登记值一致；V1.4 engine 全样本与 MII 主账登记值逐项一致（K+1 `+978.36% / -24.70% / 232 笔`；K+2 `+535.54% / -38.30%`）；V1.4 腿单仓链逐笔一致（K+1 `221` 笔、K+2 `228` 笔），终值零差。全部通过。
- 结果：`single_v39_priority_k1` 全样本 `+68192.54% / -28.01% / Sharpe 5.79 / 291 笔`（V39 `107` + V1.4 `184`，让位 `3` 次），比 V1.3 轮收益 +71% 而全样本回撤不变；K+2 压力回撤从 `-33.82%` 收敛到 `-30.98%`；`portfolio_5050_rebal_k1` `+3733.19% / -13.96% / 6.23`；两腿日收益相关 `-0.074`。最近 1 月 MII 腿 `-3.50%`（V1.3 轮 `-11.02%`），仍拖累组合（`+14.85%` vs V39 单独 `+23.40%`）。
- 决定：当时维持 `combination diagnostic / NO-GO / not live-ready`，暂不登记版本；后续同日按用户要求登记为 `V2`，见上方记录。V1.4 的 `min_rvol96=0.85` 是同一数据湖上选出的进取观察点，组合层改善继承同样本选参风险；组合继承 V39（未跨所/未 walk-forward/未 live-executable 审计）与 V1.4（registered、未 runner dry-run）的全部 blocker。
- 证据：[hype-15m-tb-mii-ensemble-v39-v14-combination-backtest-2026-07-09.md](notes/hype-15m-tb-mii-ensemble-v39-v14-combination-backtest-2026-07-09.md)。

## 2026-07-08 V39 + V1.3 组合复测（含门禁校验）

- 问题：趋势腿从 `HYPE-EMA-TB-V35` 升级为 `HYPE-EMA-TB-V39` 后，与 `HYPE-15M-MII-V1.3` 的组合结果如何；同时对全链路做门禁校验。
- 门禁：数据质量 gate（`38765` 根，缺口/重复/无效 OHLC/空值/raw-normalized mismatch 全 `0`）；V39 腿与 canonical 引擎逐 K 权益零差；V39 canonical 与主账登记值逐项一致（`+9969.45% / -23.46% / 107 笔 / 79.44%`）；V1.3 腿单仓选择链与 MII 引擎逐笔一致（K+1 `176` 笔、K+2 `181` 笔），终值零差。全部通过。
- 结果：结构性结论与 V35 版一致。`single_v39_priority_k1` 全样本 `+39829.29% / -28.01% / Sharpe 5.47 / 248 笔`（V39 `107` + V1.3 `141`，让位 `2` 次）；`portfolio_5050_rebal_k1` `+2748.51% / -13.96% / 5.87`；两腿日收益相关 `-0.084`。新增发现：最近 1 月 V1.3 腿 `-11.02%` 把单账户组合拖到 `+5.89%`（V39 单独 `+23.40%`），低波动期 V1.3 不只是不开单，还可能贡献负收益段。
- 决定：维持 `combination diagnostic / NO-GO / not live-ready`，不登记版本；组合继承 V39（未跨所/未 walk-forward/未 live-executable 审计）与 V1.3（dry-run 观察中）的全部 blocker。
- 证据：[hype-15m-tb-mii-ensemble-v39-combination-backtest-2026-07-08.md](notes/hype-15m-tb-mii-ensemble-v39-combination-backtest-2026-07-08.md)。

## 2026-07-07 首次组合回测（V35 + V1.3）

- 问题：把 `HYPE-EMA-Trend-Breakout-V35` 与 `HYPE-15M-MII-V1.3` 结合为一个新策略会怎样。
- 做法：在标准数据湖共同窗口上测试双子账户组合（50/50、70/30、30/70 逐 K 再平衡、50/50 固定拆分）与单账户冲突仲裁（V35 优先 preempt / no-preempt），V1.3 腿含 K+2 延迟压力。
- 校验：组合循环中的 V35 腿与 canonical 引擎逐 K 权益曲线零差；V1.3 腿 engine-exact 复核与主账一致（K+1 `549.30% / -22.01% / 84.78% / 184` 笔）。
- 结果：两腿日收益相关 `-0.087`。50/50 子账户回撤最浅方向（`-13.96%`，Sharpe `5.99`）但收益让渡大；单账户 V35 优先收益最高（K+1 `+34987.81%`）但回撤叠加到 `-28.01%`（K+2 压力 `-33.59%`）。preempt 显著优于 no-preempt；preempt 实际仅触发 2 次。
- 决定：记录为 first combination diagnostic，不登记版本、不 promotion；两个母版本均为 NO-GO，组合继承全部 blocker。后续若推进，先统一成本口径、补 V1.3 腿 funding、做仲裁规则邻域与滚动切片复核。
- 证据：[hype-15m-tb-mii-ensemble-first-combination-backtest-2026-07-07.md](notes/hype-15m-tb-mii-ensemble-first-combination-backtest-2026-07-07.md)。
