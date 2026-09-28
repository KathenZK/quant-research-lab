# Decision Log

## 2026-09-10 — 按用户新要求回放登记之后历史

用户本轮要求检查早期策略落档后能否继续盈利，授权本次独立诊断恢复原移植程序中的V6参数并查看2026-07-16至2026-09-05 15:00 UTC。NP和SBP两模式均已实际回放，分别约-8.09%和-12.97%；原手续费/滑点，资金费为现存事件估计。原Lab冻结JSON仍缺失，本次不声称重新验证其哈希或完整历史parity。

原10月完整OOS在8月已放弃；本次查看区间属于已揭示历史，今后不得再称未知样本。家族封存状态和生产实例不变。完整配置恢复、官方mark输入、逐笔和结果见[落档后回放报告](../multi-legacy-post-registration-audit/diagnostics/report-20260910.md)及[本次AS6S产物](../multi-legacy-post-registration-audit/artifacts/other_assets/AS6S_V6/results.json)。

## 2026-09-03 — 用户停止 V6 两条 dry-run 实例

决定：用户已在 quant-runner 提交 `a5a3b2a` 将 `bin-15m-as6s-v6-mark-np-dry-run` 与 `bin-15m-as6s-v6-mark-preemptive-dry-run` 设为 `enabled=false`，lock `enabled_allowed=false` / `approval_level=none`；服务器 `quant-runner-dryrun` 于 `2026-09-03T06:47:02Z` 重启后两实例停止，停止前 `position_open=0`。家族主状态保持 `archived`。Lab 不推断启停，本条只记录已执行事实。

证据：[停止记录](runner-tracking/binance-as6s-v6-dry-run-stop-2026-09-03.md)

## 2026-08-05 — 封存家族并放弃最终 OOS

用户决定本家族只保留研究复盘记录，不再重建已删除的行情、funding、冻结与 parity 产物；全家族进入 `archived`，原定最终 OOS 不再揭示。研究封存不修改 quant-runner，实际实例状态仍只以其配置与运行账本为准，删除边界见 [artifacts/README.md](artifacts/README.md)。

## 2026-08-04 — V5/V6 parity 证据健康度降级

V5 JOINT NP 与 V6 NP/SBP 的规范 parity JSON 已不在干净 checkout 中，证据健康度记为 `MISSING_EVIDENCE`；缺失证据阻止新 promotion，不能自动决定 runner 启停。V5/V6 的实际启用与模式只以 quant-runner 为准，既有叙事报告见 [`binance-as6s-v6-mark-joint-runner-2026-07-15.md`](runner-tracking/binance-as6s-v6-mark-joint-runner-2026-07-15.md)。

## 2026-07-14 — 建立资产特异六币策略组合家族

决定保留旧六币组合的全局单仓与仲裁思想，但不再强制六币使用同一套机制。三条 HYPE 历史策略只作为趋势状态机、突破延续和短周期反转的机制先验；每个币必须独立完成参数缩放、walk-forward 与成本后诊断。

## 2026-07-14 — 当前三个月降级为 reused holdout

`[2026-04-14, 2026-07-14)` 已被多个相关家族揭示，只用于淘汰和风险诊断，不作为最终首次 OOS。家族冻结后以 `[2026-07-14, 2026-10-14)` 的未来新增三个月作为最终 OOS。

## 2026-07-14 — 数据门禁通过并启动预拟合搜索

六币 15m K 线与 funding 已补至 `2026-07-14`，连续性、重复、空值和 funding 间隔审计的 blocker 均为 0。预拟合搜索只读取 `<2026-04-14T09:00:00Z`，按币分别搜索趋势状态、突破延续和短周期反转三类机制；每个机制先冻结预拟合第一名，再揭示 reused holdout，禁止用当前三个月在同一机制内挑第二名替换失败者。

## 2026-07-14 — 首轮 15m 结果因 MAE 回撤遗漏作废并重跑

首轮组合脚本只在平仓权益点计算 drawdown，遗漏持仓内 MAE，导致账户回撤偏乐观。该首轮预拟合、reused reveal 和账户比较 artifact 不作为有效结论。引擎补入逐笔 `mae_return_1x`，单腿与账户指标均在每笔交易结束前先检查 MAE trough；随后按原随机种子和原搜索空间完整重跑。旧 1h 机制迁移使用原引擎的 `equity_mae`，不受此缺陷影响。

## 2026-07-14 — 旧 1h 腿改为逐信号联合状态机

旧 `BIN-1H-AR-MAE` 先在每个 sleeve 内跑完持仓和 cooldown，再删除被账户阻塞的交易，会产生反事实偏差。本家族迁移时改为逐信号无状态机会；只有账户真实执行某一 1h 腿后，才从真实退出时点写入该腿 cooldown。账户层严格要求下一笔 `entry_ts > previous exit_ts`，持仓期间信号不排队。

## 2026-07-14 — 冻结九腿和双路线等待未来 OOS

冻结九条资产专属腿。nonpreemptive 路线账户缩放 `0.75`；strong-breakout-preemptive 路线缩放 `0.50`，抢占阈值 `0.70`、margin `0.05`、最短持仓 `8h`。两条路线均通过当前 reused diagnostic 和 8bps/K+2 压力，但不登记版本、不 promotion；`[2026-07-14T09:00Z, 2026-10-14T09:00Z)` 期间禁止改参，等待一次性最终 OOS。

## 2026-07-14 — 登记 BIN-15M-AS6S-V1

按用户要求把九腿 nonpreemptive 路线登记为 `BIN-15M-AS6S-V1`；strong-breakout-preemptive 保留为对照 observation。V1 维持 `registered / not promoted / not live-ready`，未来最终 OOS 与冻结禁改边界不变；证据见[冻结规格](specs/binance-as6s-future-oos-freeze-2026-07-14.md)与[近期切片审计](diagnostics/binance-as6s-v1-recent-slices-2026-07-14.md)。

## 2026-07-14 — 单腿取消 80% 胜率门槛，改为组合优先搜索

按用户新口径，单腿只要求成本后正期望与风险可控，`80%` 胜率只在最终账户层执行。组合优先搜索得到六腿候选，包含两条全窗胜率低于 `80%` 的正期望腿；当前账户诊断通过且全窗风险收益优于 V1，但最近一个月为负、未来 OOS 未发生，因此只记录为未登记的 V2 candidate observation，证据见[组合优先诊断](diagnostics/binance-as6s-portfolio-first-v2-observation-2026-07-14.md)。

## 2026-07-14 — V2 停止推进，改为单币前沿优先的 V3 observation

用户指出组合优先流程仍未真正完成“先为每个币找高收益、高胜率、低回撤机制，再组合”的目标。本轮停止推进 V2，重新审计全部预拟合前沿，并按各币 ATR 分布搜索高频补充腿。结果找回被旧账户裁剪遗漏的 SOL 强突破腿；Clean-RSI 只有 HYPE 在实际 funding、8 bps 与 K+2 后保留正期望，其余币不强制套用。账户最终保留 15 条资产专属腿，nonpreemptive 与 strong-breakout-preemptive 均通过当前账户层诊断，但未来最终 OOS 未发生，因此只记录为未登记 V3 candidate observation；证据见[单币优先 V3 诊断](diagnostics/binance-as6s-asset-first-v3-diagnostic-2026-07-14.md)。

## 2026-07-14 — 冻结 V3 observation 等待一次性未来 OOS

V3 进一步通过合成执行语义审计与 funding 结算边界压力。全六币可交易区间两条路线频率分别为 `0.954` 和 `0.966` 笔/日，接近目标 `1` 笔/日；全区间较低频率主要来自 HYPE 上市前的不可交易时期。冻结 15 条腿、两套账户缩放和抢占参数，锁定 122 个依赖文件（含未来一次性揭示程序）与六币历史数据逻辑哈希；在 `2026-10-14T09:00Z` 前禁止调参或查看部分未来窗口。冻结不构成版本登记，状态保持 `not registered / not promoted / not live-ready`；证据见[V3 未来 OOS 冻结规格](specs/binance-as6s-v3-future-oos-freeze-2026-07-14.md)。

## 2026-07-15 — V4 否决并建立 V5 joint-state observation

V3 的 `exit_ts` 候选 tie-break 虽未在历史样本触发，但代码路径不可实盘，故 V4 删除所有入场期未来字段。继续翻译 runner 状态机时发现 V4 仍沿用了 `frontier15m / cleanrsi15m` 的单腿虚拟占仓候选流：即使某个信号被全局账户挡住，假想交易仍会压制同腿后续信号。联合状态审计确认历史逐笔账发生变化，因此 V4 live-executable gate 改判为 `FAIL`。

V5 不重新选腿或调参，只取消未成交候选的虚拟状态；只有账户真实接受的交易才能创建持仓和退出后 cooldown。修正后 nonpreemptive 全区间 `553` 笔、胜率 `85.17%`、年化权益倍数 `5.82x`、最大回撤 `-12.86%`；最近三个月 `81` 笔、胜率 `83.95%`、收益 `+69.19%`、回撤 `-7.89%`。两条路线的 8 bps 与 K+2 账户硬门槛仍通过。V5 继续沿用原未来 OOS 时间边界，状态为未登记 observation，证据见[V5 联合状态观察](diagnostics/binance-as6s-v5-joint-state-observation-2026-07-14.md)。

## 2026-07-15 — V5 Runner 离线对拍通过并接入禁用配置

Runner 已完成 45 个冻结候选、15 条腿完整退出和 553 笔 nonpreemptive 账户路由
对拍，并补齐多币种 mark 保护与重启恢复定向测试。为使统一 CLI 能重复验证，
新增 `bin-15m-as6s-v5-joint-np-dry-run` manifest/TOML 实例及 fixture 驱动 strict
replay，但实例固定 `enabled=false / approval_level=none`。本决定不授权持续
dry-run、live 或查看锁定未来 OOS；批准上限继续为 `disabled`。

## 2026-07-15 — V6 双路线 Runner 严格对拍通过但保持禁用

冻结 V6 的两条路线已完成 Runner 翻译：不抢占 `634/634`、强突破抢占
`568/568` 全账户路径一致，mark 保护、缺失数据 fail-closed、抢占重启恢复和
执行故障注入通过；证据见 [Runner 对拍](runner-tracking/binance-as6s-v6-mark-joint-runner-2026-07-15.md)。
两个实例继续固定 `enabled=false`；本决定不授权持续 dry-run、testnet、live，
也不解除未来 OOS 禁改禁看边界。

## 2026-07-15 — 补齐 V6 标准近期切片但不据此改参

V6 的 1d/7d/1m/3m/6m/1y base-cost 切片已补齐；两条路线最近 7d 均为负，
nonpreemptive 最近 1m 胜率为 `78.57%`，因此不能把长期高胜率解释为每周稳定
盈利。该结果只作冻结时点诊断，不改变双路线、参数或未来 OOS 门禁；证据见
[标准近期切片](diagnostics/binance-as6s-v6-recent-slices-2026-07-15.md)。

## 2026-07-15 — 授权 V6 双路线持续 dry-run

用户明确授权同时启用 V6 不抢占与强突破抢占两个持续 `dry-run` 实例。两条路线
各自使用独立 state directory 和虚拟执行账户，公共平台账本按实例名与策略 ID
分账，不互相净额；基础名义金额均为 `10 USDT`，最大 allocation `2.25`。
本授权只用于 forward 观测，不构成 testnet、live 或 promotion 批准，也不改变
`[2026-07-14T09:00:00Z, 2026-10-14T09:00:00Z)` 未来 OOS 禁改禁看边界。

## 2026-08-04 — V5 退役，引擎代码内聚进 V6 模块

用户决定 AS6S 家族只保留 V6 双路线，V5 整体退役：

- runner manifest 移除 `bin-15m-as6s-v5-joint-np-dry-run` 条目，`dryrun.toml`
  同步移除该 disabled 实例，lock 重新生成。
- runner 删除 `strategies/asset_specific_six_selector_v5_joint_state/` 目录；
  V6 原先依赖的 V5 引擎代码（config/signals/router/mod 四文件）原样迁入
  `strategies/asset_specific_six_selector_v6_mark_joint_state/`，作为
  `engine_*.rs` 内部模块，行为逐位不变（diff 审计 + 全量测试通过）。
- V5 专属 strict replay、parity fixture 环境变量与测试一并移除；V6 双路线
  parity 审计维持不变（fixture 仍需 Lab 侧重新落盘后执行，见跟踪文档）。
- V5 历史对拍证据保留在本家族 ledger 与
  [V5 Runner 对拍](runner-tracking/binance-as6s-v5-joint-runner-2026-07-15.md)，
  不构成注册或 promotion。

执行细节见 [V5 退役记录](runner-tracking/binance-as6s-v5-retire-engine-inhouse-2026-08-04.md)。
