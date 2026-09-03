# HYPE-5M-PBTR 决策日志

家族 id：`HYPE-5M-PBTR`

这是 Binance HYPE `5m` 回踩恢复入场与 ATR trailing-stop 研究的家族级阅读路径。

## 2026-09-03 — tiny_live_pilot 续期至 2026-12-24

决定：用户已在 quant-runner 提交 `a5a3b2a` 将 `hype-pullback-live` 的 `approval_expires_at` 由 `2026-09-24` 续期至 `2026-12-24T00:00:00Z`。资金边界与策略参数不变。Lab 只记录该已执行授权窗口，不扩大 sizing。

## 2026-09-03 — live 实例 halted 待用户决定

决定：只读观察到 `hype-pullback-live` 的 `strategy_health.status=halted`，自 `2026-08-19T21:31Z` 无新事件；live 服务仍 `active`、`NRestarts=0`。用户尚未决定如何处理。结论仅列出待选项，Lab 不推断启停。

证据：[halted incident](runner-tracking/hype-5m-pbtr-live-halted-incident-2026-09-03.md)

## 当前边界

- 这是一个独立的 HYPE 策略家族。
- 不要把新的 `HYPE-5M-PBTR` 研究存放到 `15m-ema-trend-breakout/`。
- 不要从裸版本号 `V1`、`V2`、`V35` 或其他版本号推断策略身份。
- 后续新建文件若包含带小数点的版本号，必须用连字符保留层级，例如 `HYPE-5M-PBTR-V3.2` 写作 `v3-2`，不要写成 `v32`，避免和未来 `V32` 混淆。
- 活跃 package 代码仍只承载数据与研究基础设施；策略事实以本 Markdown 家族树和一次性研究脚本为准。

## 研究批次记录

- `2026-08-04`：规范 parity JSON 已不在干净 checkout 中，将 `HYPE-5M-PBTR-V6.2.1` 的证据健康度标为 `MISSING_EVIDENCE`；是否停止或调整实例必须由用户另行决定，实际授权与运行配置只以 quant-runner 为准。既有叙事证据见 [`hype-5m-pbtr-runner-2026-07-09.md`](runner-tracking/hype-5m-pbtr-runner-2026-07-09.md)。
- `2026-07-20`：按用户决定，将 `HYPE-5M-PBTR-V6.2.1` 的 `tiny-live-pilot` 到期时间延至 `2026-09-24T00:00:00Z`；资金边界与策略参数不变，dry-run 并行保留，真实成交生命周期未完成前不得扩大资金。当前 runner 证据见 [`hype-5m-pbtr-runner-2026-07-11.md`](runner-tracking/hype-5m-pbtr-runner-2026-07-11.md)，实际授权以 quant-runner 为准。
- `notes/hype-5m-indicator-ensemble-search.md`：在 `2025-06-01` 到 `2026-06-01` 的 Binance HYPE 永续 `5m` 数据上进行指标组合搜索。单条原始或精炼策略均未达到 `20x 年化 / >=80% 胜率 / >-20% 回撤`；一个由高胜率 EMA/Bollinger 回归腿组成的单仓 ensemble 达到全样本目标。该批次只作为研究前身，存在明显过拟合风险，不是已提升的 live 版本。
- `live-specs/ensemble-specs/README.md`：记录最初 `7` 个 `target_pass=True` 的 HYPE Binance `5m` 单仓 ensemble 组合作为 live-code 交接规格。它们共享相同精炼腿，只是腿数和杠杆不同；当前仅保留为历史支撑材料，不是现行提升路线。
- `notes/hype-5m-ensemble-forward-oos-2026-06-23.md`：加入 `2026-06-01` 到 `2026-06-23 04:00 UTC` 的 Binance HYPE `5m` 数据后，早期 7 个 ensemble 配置无法保持 `>=80%` 胜率和 `<20%` 回撤。这否定了高胜率小利润路径作为 live-ready 方向。
- `notes/hype-5m-positive-payoff-search-2026-06-23.md`：要求 `payoff_ratio > 1`、每个切片胜率 `>=60%`、每个切片年化 `>=20x` 后，基础搜索没有命中。定向 refinement 虽产生数学命中，但回撤不可接受；结论是在讨论收益前必须加入生存约束。
- `notes/hype-5m-survival-frontier-2026-06-23.md`：生存前沿要求每个切片 `payoff_ratio > 1`、交易数、胜率底线 `55%/58%/60%`，以及回撤底线 `-20%/-25%/-30%`。最有用的中间候选是 `HYPE_PP_R05732__dir_htf_ge_0.688442`，全样本年化 `29.07x`，最差切片年化 `9.75x`，最差切片胜率 `58.29%`，payoff `2.19`。
- `ablations/hype-5m-r05732-strategy-ablation-2026-06-23.md`：将 R05732 提升为 `HYPE-5M-PBTR-V1` 候选。消融显示 `trail_atr=0.75` 和 `min_hold_bars=6` 是核心；删除最终 `dir_htf` 会显著提高频率和收益，但降低最差切片胜率；`pullback_buffer=0.01` 以及删除/提高固定止盈是最佳后续方向。
- `diagnostics/hype-5m-pbtr-v1-strict-live-audit-2026-06-27.md`：按严格可实盘订单时序重测 `HYPE-5M-PBTR-V1`，确认旧口径确实赚钱但不可交接实盘。更新数据到 `2026-06-26 04:15 UTC` 后，legacy stop-price fill 为 `1358` 笔、总收益 `+1713.55%`、PF `2.806`、最大回撤 `-7.77%`；但 live-realistic 口径变为 `1357` 笔、总收益 `-87.29%`、PF `0.637`、最大回撤 `-88.27%`。解锁时 stop 可正常挂上的比例仅 `31.47%`，`68.53%` 需要解锁市价平仓；开仓即挂 `0.75 ATR` 初始保护止损的反事实口径 PF 也只有 `0.510`。结论：V1 不是被后续版本“改坏”后才失效，V1 本身已经依赖 crossed/stale stop 或 target 的不可实盘成交假设，不能作为回退上线版本。
- `hype-5m-pullback-trail-core-ledger.md`：`HYPE-5M-PBTR-V1/V2` 主账。
- `notes/hype-5m-pullback-trail-v2-combo-test-2026-06-23.md`：围绕 V1 消融发现测试 `10240` 个同步组合，`1568` 个通过 V2 门槛。提升 `HYPE-5M-PBTR-V2`，参数为 `pullback_buffer=0.01`、`tp_atr=99`、`stop_atr=0.5`、`roc_window=96`、`min_efficiency=0`、`dir_htf>=0.5`。
- `live-specs/hype-5m-pullback-trail-v2-live-spec.md`：`HYPE-5M-PBTR-V2` 的详细复现规格，供实现 AI 使用，包含指标公式、信号构造、单仓执行、ATR trailing-stop 管理、重启恢复和验收指标。
- `ablations/hype-5m-pullback-trail-v2-ablation-slices-2026-06-23.md`：V2 全参数消融，包含 `56` 个周切片、滚动 1w/1m/3m/6m/full 统计，以及 V1/V2 横向对比。
- `ablations/hype-5m-pullback-trail-v2-live-cost-ablation-slices-2026-06-23.md`：用观测到的实盘执行成本重跑 V2 全参数消融和时间切片，成本为手续费 `4.1466 bps/turnover`、开仓滑点 `+10.73 bps`、平仓滑点 `-2.64 bps`、净滑点 `+4.0449 bps/total turnover`。
- `ablations/hype-5m-pullback-trail-v21-live-cost-variants-2026-06-23.md`：通过固定/删除 V2 中不活跃参数，提升简化表达 `HYPE-5M-PBTR-V2.1-clean`，随后在同一实盘成本模型下测试 V2.1A 收益分支、V2.1B clean-plus 分支和 V2.1C 稳定分支。
- `diagnostics/hype-5m-pbtr-v21a-live-realistic-audit-2026-06-24.md`：按严格实盘订单时序重测已进入实盘/实盘 dry-run 的 `HYPE-5M-PBTR-V2.1A`。原始实盘成本回测 PF `2.79`，但若开仓即挂 `0.5 ATR` 初始保护止损，PF 降至 `0.46`；若锁仓期不挂策略止损、解锁时穿越 stop 则市价退出，PF 降至 `0.54`。结论是 V2.1A 也存在 `min_hold_bars + trailing` 出口不可执行假设问题。
- `diagnostics/hype-5m-pbtr-v21a-unlock-exit-audit-2026-06-24.md`：专门复核 V2.1A dry-run 中“持有 6 根、第 7 根 trailing 触发退出”的现象。原始回测中第 7 根 stop 子集 `2746` 笔、PF `1.98`，说明现象成立；但第 7 根开盘直接平仓、解锁 trailing 市价平仓、收盘 trailing 平仓三种可执行口径 PF 均约 `0.54`，因此 14 笔 dry-run 盈利必须逐笔对账，不能证明旧状态机可放大。
- `diagnostics/hype-5m-pbtr-v21a-fixed-hold-exit-2026-06-24.md`：作为 unlock-exit 审计补充，测试纯固定持有 `1-24` 根 K。固定持有 6 根、第 7 根开盘平仓 PF `0.54`、平均每笔 `-0.20%`；第 7 根原始 stop 中约 `79.10%` 在开盘时已经穿越 stop，说明问题不是 ATR 是否用当前 K，而是旧 stop 价大多已不可成交。
- `diagnostics/hype-5m-pbtr-v21a-dryrun-ledger-audit-2026-06-24.md`：复核 `/Users/ZK/OpenCode/hype-pullback` paper-live dry-run SQLite。SQLite 只有 `13` 笔已关闭交易，全部 short，账面 stop 价成交净赚 `+0.3672 USDT`；但 `11/13` 笔在 runner 设置 stop 的那根闭合 K 收盘时已经越过 stop，若按下一根开盘价退出则总计 `-0.0851 USDT`，按下一根收盘价退出则 `-0.1614 USDT`。结论是 dry-run 盈利来自 stop 已不可按旧价成交时仍按 `current_stop` 入账，不能作为可实盘证据。
- `diagnostics/hype-5m-pbtr-v21a-immediate-tp-audit-2026-06-25.md`：测试开仓后立即挂 `1 * ATR14` 固定止盈、不挂初始止损，前 `6` 根只允许止盈，第 `6` 根后再启用 trailing stop。即时止盈使约 `42.85%` 的交易在前 6 根止盈；旧 stop 价成交口径仍有 PF `1.86`，但 live-realistic 口径 PF 只有 `0.53`，总收益约 `-99.89%`。结论是即时 1ATR 止盈不能修复 V2.1A 的可执行性问题。
- `diagnostics/hype-5m-pbtr-v21a-remove-final-htf-live-cost-2026-06-24.md`：接受 `remove_final_filter_dir_htf` 作为来自 V2.1A 的独立高频候选，并使用观测实盘成本复核。
- `diagnostics/hype-5m-pbtr-v3-ablation-audit-2026-06-24.md`：正式将该高频候选记录为 `HYPE-5M-PBTR-V3`，包含全参数消融、周/月/滚动时间切片，以及对不真实年化的资深量化审计。V3 不是 V2.1A 的替代版本，需要小资金 dry-run 和执行压力测试。
- `diagnostics/hype-5m-pbtr-v31-min-hold-9-2026-06-24.md`：将 V3 消融中表现最强的 `min_hold_bars=9` 固化为 `HYPE-5M-PBTR-V3.1` 研究候选，并生成 HTML 交易路径图。V3.1 样本内显著提高胜率/PF，但最大回撤扩大，不能直接替代 V3。
- `diagnostics/hype-5m-pbtr-v32-clean-entry-filters-2026-06-24.md`：根据外部审计意见删除 V3.1 中剩余无贡献/负贡献入场过滤器，形成 `HYPE-5M-PBTR-V3.2`。V3.2 仅保留方向、pullback/resume、`min_hold_bars=9` 和 ATR trailing exit，样本内收益和回撤均优于 V3.1，是当前更简洁的 paper/dry-run 首选表达。
- `ablations/hype-5m-pbtr-v32-full-parameter-ablation-2026-06-24.md`：对 V3.2 重做全参数消融。结论是旧入场过滤器不应加回，核心入场仍是 `pullback_resume`，核心退出仍是 `min_hold + ATR trailing`；`trail_atr=0.5`、`min_hold_bars=12`、`stop_atr=0.25` 只作为下一轮 V3.3 研究方向。
- `live-specs/hype-5m-pbtr-v3-2-live-spec.md`：面向同事实盘/paper 复现的 V3.2 完整参数与执行规格，包含入场、持仓、平仓、成本、状态恢复和 dry-run 验收线。
- `diagnostics/hype-5m-pbtr-v3-3-minimal-2026-06-24.md`：将 V3.2 中所有兼容保留、关闭、有限值保护和基本不触发参数彻底移除，形成 `HYPE-5M-PBTR-V3.3` 最小复现表达。回测与 V3.2 几乎一致，仅多出 `2` 笔交易，说明 V3.2 大参数表可以从交接规格中删除。
- `live-specs/hype-5m-pbtr-v3-3-live-spec.md`：面向同事实盘/paper 复现的 V3.3 最小规格，只保留 `EMA21/EMA96`、`pullback_buffer=0.01`、`stop_atr=0.5`、`trail_atr=0.75` 和 `min_hold_bars=9`。
- `ablations/hype-5m-pbtr-v3-3-full-parameter-ablation-2026-06-24.md`：对 V3.3 的 6 个有效参数做单因子全参数消融。结论是 6 个参数都是真正生效参数，不能继续删除；`trail_atr=0.5`、`min_hold_bars=12/18`、`stop_atr=0.25` 是样本内增强候选，但 `trail_atr=0` 是不可实盘复现的退化边界，必须剔除。
- `diagnostics/hype-5m-pbtr-v33-reinit-trailing-2026-06-24.md`：测试 V3.3 方案 2：锁仓期只观察，不把锁仓期峰谷带入 trailing，第 10 根 K 重新初始化 stop。该机制能消除解锁即 stop 已穿越的不可挂单问题，但在 V3.3 原参数下仍失败，最佳 PF 仅约 `0.61`，说明必须在可执行状态机上重新搜索更宽 trailing/更短锁仓/应急止损参数。
- `diagnostics/hype-5m-pbtr-v33-immediate-tp-audit-2026-06-25.md`：把 V2.1A 的即时 `1 * ATR14` 止盈补救迁移到 V3.3。即时止盈使约 `50.19%` 的交易在 `min_hold_bars=9` 锁仓期内先止盈；旧 stop 价成交口径 PF `2.38`，但 live-realistic 口径 PF 仅 `0.55`，总收益约 `-100%`。结论是 V3.3 也不能靠入场即挂 1ATR 止盈修复。
- `diagnostics/hype-5m-pbtr-v33-immediate-tp2-audit-2026-06-25.md`：测试 V3.3 开仓即时 `2 * ATR14` 止盈。锁仓期止盈率降至 `25.76%`，旧 stop 价成交口径 PF `3.40`，但 live-realistic 口径 PF 只有 `0.60`，总收益仍约 `-100%`。结论是扩大即时止盈到 2ATR 也不能修复 V3.3。
- `diagnostics/hype-5m-pbtr-v33-immediate-tp-grid-2026-06-25.md`：完整搜索 V3.3 即时止盈 ATR 倍数，`tp_atr=0.25..8.00` 步长 `0.25`，并附加 `10/12`。live-realistic PF 最佳为 `2.5ATR`，PF `0.615`，总收益和最大回撤仍约 `-100%`。结论是问题不是 TP 倍数没调准，而是未止盈交易解锁后的退出状态机本身负期望。
- `diagnostics/hype-5m-pbtr-v3-4-combo-candidates-2026-06-24.md`：对 V3.3 单因子有效增强项做组合测试，最强实用候选为 `EMA9/96 + pullback_buffer=0.01 + stop_atr=0.25 + trail_atr=0.5 + min_hold_bars=18`，样本内胜率 `72.95%`、PF `19.92`、最大回撤 `-11.27%`。该组合提升记录为 `HYPE-5M-PBTR-V4`，但仍需实盘可行性审计。
- `diagnostics/hype-5m-pbtr-v4-live-viability-audit-2026-06-24.md`：对 `HYPE-5M-PBTR-V4` 做实盘可行性审计。结论是 V4 不是不可计算策略，成本压力下仍有较强缓冲；但若从开仓即挂 `0.25 ATR` 保护止损，反事实回测会变成 PF `0.17`、最大回撤约 `-100%`。V4 只能进入 paper-live / 极小资金审计，不能直接生产。
- `diagnostics/hype-5m-pbtr-live-realistic-trailing-2026-06-24.md`：按严格实盘订单时序重测 `HYPE-5M-PBTR-V3.3` 与 `HYPE-5M-PBTR-V4`：锁仓期不挂策略止损，解锁时若 `active_stop` 已被穿越则市价平仓，否则挂 reduce-only stop-market 并继续 trailing。结果 V3.3 live-realistic PF `0.58`、V4 live-realistic PF `0.67`，两者均坍缩为亏损结构，说明当前 `min_hold_bars + trailing` 退出路径不能直接交接实盘。
- `diagnostics/hype-5m-pbtr-fixed-bracket-search-2026-06-24.md`：对 V3.3/V4 信号测试入场即挂固定 ATR bracket order，不使用 `min_hold_bars` 或 trailing。V3.3 原始信号 `21289` 个，V4 原始信号 `22774` 个；`TP=5ATR/SL=3ATR` 分别 PF `0.79`/`0.76`，最佳组合也只有 PF `1.05`/`1.06` 且总收益为负、回撤深，说明固定止盈止损不能救活这两个信号。
- `diagnostics/hype-5m-pbtr-reset-bracket-search-2026-06-24.md`：对 V3.3/V4 信号测试每根 5m K 收盘后围绕最新 close/ATR 重设 TP/SL。该状态机可实盘执行，但 V3.3 最佳 PF `2.22` 只来自 `24` 笔超长持仓，中位持仓约 `2984` 根 5m K，最大回撤 `-69.21%`，最近 1 个月无交易；V4 最佳组合全样本仍亏损。结论是动态 bracket 也不能直接救活 V3.3/V4。
- `diagnostics/hype-5m-pbtr-reset-bracket-maxhold48-2026-06-24.md`：在动态 bracket 上加入 `max_hold_bars=48`，即最多持仓约 4 小时。V3.3 原最佳 `TP=6/SL=10` PF 从 `2.22` 降至 `0.79`，最大回撤 `-98.90%`；全网格最佳也只有 V3.3 PF `0.81`、V4 PF `0.83`。这确认此前改善主要来自十天级超长持仓，不是 5m 信号本身。
- `diagnostics/hype-5m-pbtr-live-repair-plan-2026-06-24.md`：根据 V2.1A/V3.3/V4 的 live-realistic 失败和一次小型 reinit 参数探测，提出下一轮 `HYPE-5M-PBTR-V5` 应从可执行状态机重新开始：开仓即保护止损，或先观察后入场；不再接受 crossed stop 按旧 stop 价成交的回测口径。
- `diagnostics/hype-5m-pbtr-v5-executable-search-2026-06-24.md`：执行 first-pass `HYPE-5M-PBTR-V5` 搜索，测试 `1980` 个可实盘状态机组合，包括开仓即保护止损与观察后入场。无候选通过 gate，且无 watchlist；最佳 PF 约 `0.69`。附加单特征事件质量探测也没有找到 PF `>1` 的子集，说明当前 pullback-trailing 直接规则不应继续交接实盘。
- `diagnostics/hype-5m-pbtr-v5-1-event-quality-2026-06-24.md`：把原始 pullback 触发器降级为高频事件源，新增 observation-confirmed 事件质量筛选层，并在筛选后重新做 exact executable replay。找到一个很窄的候选：`opp_wick_atr <= 0` 且 `abs_ema_spread_bps <= 92.9084`，全样本 `180` 笔、PF `1.25`、验证 PF `1.29`、forward PF `1.06`、最大回撤 `-10.37%`。
- `diagnostics/hype-5m-pbtr-v5-1-candidate-ablation-2026-06-24.md`：对 V5.1 候选做删除过滤器和邻域参数消融，测试 `9736` 行。真正通过 candidate gate 的只有同一规则的重复入口；一旦放宽 `opp_wick_atr`，交易频率上升但 PF 快速跌破 `1`。月度稳定性不足，`2026-04` PF 仅 `0.10`，所以 V5.1 不能进入真实资金执行，只能作为 paper/audit 候选。
- `diagnostics/hype-5m-pbtr-v5-2-walk-forward-ranking-2026-06-24.md`：接受“不要写真钱 live spec，先做 walk-forward event ranking 和 audit runner”的方向后，将 V5.1 固定筛选层改为 live-feasible 月度 walk-forward 排名器。测试 `96` 个配置，全部低于 PF `1`，最高 walk-forward PF `0.93`，平均每笔仍为负；生成 `artifacts/hype_5m_pbtr_v52_paper_audit_events.csv` 记录所有 observation-confirmed 事件的接受/拒绝、阈值、分数和 paper 订单状态。结论：当前评分器无法在线学到 V5.1 的事后阈值条件，不应 paper 部署。
- `diagnostics/hype-5m-pbtr-v6-live-executable-search-2026-06-25.md`：按用户要求重新参考 V3.3 的信号触发方式探索可实盘盈利组合，并将 Binance HYPE `5m` 数据湖补到 `2026-06-25 05:50 UTC` 最后一根已闭合 K。搜索 `216` 个信号形态与 `78` 个退出形态，prescreen 只按 `2025-05-30 -> 2026-03-01` 样本内排序，随后对 top `80` 组合做 exact executable replay。原始搜索产生 `2120` 行精筛候选和 `179` 个宽松 gate 通过项；默认 full-PF top 不是最终选择，必须结合后续稳健性复核阅读。
- `diagnostics/hype-5m-pbtr-v6-candidate-robustness-2026-06-25.md`：围绕 V6 最强可执行基座做邻域复核，测试 `2464` 行 exact replay，`112` 行通过严格 robust pass。当前最值得 paper 的候选是 `EMA21/EMA55` 多头回踩恢复、`pullback_buffer=0.01`、无 candle 方向过滤、`dir_htf >= 0.5`、`dir_ret192_bps >= 788.123`，入场后立即挂 `TP=3ATR14 / SL=7ATR14`，无 trailing，`36` 根 K 超时 open 平仓。全样本 `147` 笔、总收益 `+76.43%`、年化倍数 `1.70x`、PF `1.72`、胜率 `59.86%`、payoff `1.15`、最大回撤 `-11.28%`；`2026-06-01 -> 2026-06-25 05:55 UTC` OOS `10` 笔、`+2.07%`、PF `1.45`。这是 paper/live-dry-run 候选，不是生产 sizing 版本。
- `ablations/hype-5m-pbtr-v6-full-parameter-ablation-2026-06-25.md`：正式将上一轮 paper 候选记录为 `HYPE-5M-PBTR-V6`，并对 `51` 个单因子变体做全参数消融，`13` 个变体通过 V6 robust gate。核心结论：删除质量过滤后 PF 降至 `0.806`、最大回撤 `-66.09%`；`side_mode=short/both` 失败；`quality_window=192` 是唯一通过的动量窗口；`EMA21/55` 是当前最稳趋势定义；`SL=6/7/8/10ATR` 与 `TP=2.5/3ATR` 有邻域稳定性；加回 trailing 或将 timeout 缩到 `12` 根 K 会显著削弱。V6 定义保持 `TP=3ATR/SL=7ATR/timeout=36`，暂不因单因子小增益升级。
- `diagnostics/hype-5m-pbtr-v33-retry-arm-2026-06-26.md`：复核 V3.3 线上 stop-arm overlay 的近似回测。第 `7` 根 5m K 开始尝试挂 reduce-only stop-market，穿越时按 5 秒 retry 近似，第 `10` 根处理周期市价兜底；同时跑 `5m_conservative`、`5m_optimistic`、`1m_conservative`、`1m_optimistic` 四个口径。结果四者 PF 分别约 `0.583`、`0.566`、`0.574`、`0.580`，最大回撤均约 `-100%`。1m 数据能稍微改善 arm 诊断，但不能恢复旧 stop-fill baseline 的正 EV；该 overlay 只能作为实盘风控/审计机制，不应提升为 paper/live 候选。
- `diagnostics/hype-5m-pbtr-v3-3-1-prev-exit-filter-2026-06-27.md`：将当前 V3.3 retry-arm overlay 在主账记录为 `HYPE-5M-PBTR-V3.3.1`，并测试“上一单平仓价顺势过滤”：第一笔允许入场；之后多头要求新开仓价高于上一笔平仓价，空头要求新开仓价低于上一笔平仓价。过滤拒绝约 `39%-40%` 候选，交易数降至约 `6.6k-6.8k`，但 5m 悲观/乐观 PF 仅 `0.581`/`0.560`，1m 悲观/乐观 PF 仅 `0.568`/`0.571`，最大回撤仍约 `-100%`。结论是该过滤不能修复 V3.3.1 的 retry-arm 负期望。
- `diagnostics/hype-5m-pbtr-v3-3-1-no-initial-stop-buffer-grid-2026-06-27.md`：在 V3.3.1 retry-arm overlay 上去掉初始止损价 floor，并扫描 `pullback_buffer=0.0100` 到 `-0.0200`。正向和轻微负向 buffer 大多仍为亏损结构；`pullback_buffer=-0.0100` 在四个口径都为正收益且 PF `>1`，5m 乐观 `37` 笔、收益 `+9.27%`、PF `1.477`、最大回撤 `-10.30%`，但样本极少。更负的 `-0.0125` 转亏，`-0.0150` 虽 PF 高但只有 `7` 笔，`-0.0200` 只有 `1` 笔。结论是“深回踩事件质量”值得记录为低样本线索，但不能提升为 V3.3.1 候选。
- `diagnostics/hype-5m-pbtr-v3-3-1-rescue-search-2026-06-27.md` 与 `diagnostics/hype-5m-pbtr-v3-3-1-rescue-neighborhood-2026-06-27.md`：围绕 no-initial-stop、负 `pullback_buffer`、long-only、`ret192_bps` 动量、EMA spread、close position 和 adverse wick 做两阶段 rescue search。原始高频双向 V3.3.1 仍不可救；但低频 long-only 深回踩子集出现四口径一致正收益：`pb=-0.0075/ret192>=250/spread<=225` 最少 `35` 笔、最差 PF `2.207`、最差收益 `+16.93%`、回撤 `-4.58%`；`pb=-0.0060/ret192>=250/spread<=150/close_pos>=0.55` 最少 `53` 笔、最差 PF `1.602`、最差收益 `+14.44%`、回撤 `-8.77%`；`pb=-0.0060/ret192>=200/spread<=125` 最少 `61` 笔、最差 PF `1.318`、最差收益 `+9.66%`、回撤 `-9.14%`。这些是 rescue 线索，需要 walk-forward/月度切片复核，不能直接提升为 paper/live。
- `diagnostics/hype-5m-pbtr-v3-3-1-range10-take-profit-2026-06-27.md`：测试 V3.3.1 开仓后 5 秒轮询早停止盈 overlay，若浮盈达到信号 K 最近 10 根 5m K 的平均振幅就 reduce-only 市价平仓，不再进入 stop-arm/trailing。为公平比较，裁剪到 5m/1m 重叠样本。结果约 `49%-51%` 交易提前止盈，胜率提升到约 `51%-53%`，但 payoff 只有约 `0.50-0.54`，四口径 PF 仅约 `0.55-0.56`，累计收益约 `-97%`。结论是该早停止盈改善胜率观感但破坏盈亏比，不能救回原始 V3.3.1。
- `diagnostics/hype-5m-pbtr-v3-3-1-combo-overlay-2026-06-27.md`：把组合式风控 overlay 加到全量 V3.3.1：入场即 emergency stop，浮盈后推保本，更高浮盈后 range10 trailing，早期无推进则 time exit。5m/1m 重叠样本中，四口径最优配置仍只有 min PF `0.285`、min total `-99.92%`、worst drawdown `-99.92%`。结论是全量原始信号质量太低，单靠退出 overlay 会变成大量小亏/止损，不能把噪声信号变成正期望。
- `diagnostics/hype-5m-pbtr-v3-3-1-filter-directions-2026-06-27.md`：把昨晚 V3.3.1 实盘复盘提出的五类过滤方向放回 V3.3.1 retry-arm overlay：反抽实体强度、EMA21 斜率同向、回踩深度上限、ATR 稳定、1h EMA 大周期确认，并加入少量组合过滤。回测使用本地 1m/5m 重叠区间 `2026-03-25 00:00 UTC` 到 `2026-06-26 04:15 UTC`，四口径复核。全部过滤 min PF 均低于 `1`；最强 `combo_ret_spread` 最少 `690` 笔、min total `-66.01%`、min PF `0.634`，相比 base 的 min PF `0.565` 有降噪但仍稳定亏损。结论是这些过滤不能救回全量 V3.3.1，只能把“强趋势 + EMA spread”保留为低频 rescue 子集特征。
- `diagnostics/hype-5m-pbtr-ml-event-quality-2026-06-27.md`：按“机器学习是否能提高 trailing/armed 概率并救活 V3.3.1”的问题，构建 V3.3.1 事件级 strict retry-arm 标签，共 `21451` 个事件，其中 walk-forward 可打分 `19737` 个；用 `numpy` logistic/ridge 分别预测 `positive_net`、`bad_unlock`、`trailing_positive` 和 clipped `net_ret_1x`，每月只用历史训练，选择 top `5%/10%/20%/30%` 事件再做 exact replay。结果最强 robust 行为为 `ml_top_20pct`，四口径 min PF `0.585`、min total `-98.35%`、最少 `549` 笔；单口径最高 PF 也只有 `0.659`。ML 将 trailing-positive rate 从 baseline 的 `27.35%` 小幅提高到最高 `29.61%`，但 bad unlock/deadline 仍约 `60%-62%`，不能救回全量 V3.3.1。结论是“提高 trailing/armed 概率”不是充分目标；后续若继续 ML，只能转向低频 deep pullback long-only + 强动量/spread 的事件质量路线。
- `diagnostics/hype-5m-pbtr-v3-3-1-armed-pyramiding-2026-06-27.md`：测试“stop-arm / trailing 成功后给盈利订单加杠杆”的 armed-after pyramiding overlay。网格覆盖 `add_mult=0.25/0.5/1.0`、stop cushion `0.1/0.3/0.5/0.8 ATR`、最大追价 `0.5/1.0/1.5 ATR`，并区分 `lock`（stop 已锁住原仓扣费利润）与 `nolock`（仅 armed 后浮盈）两类。四口径 robust 最强配置等同不加仓 baseline：min PF `0.565`、min total `-96.92%`、worst DD `-96.99%`，`lock` 条件下多数无可加仓机会；`nolock` 虽能把加仓率提高到个位数或十几百分点，但加仓腿平均收益仍为负，典型约 `-0.14%` 到 `-0.19%`。结论是加仓只会放大 V3.3.1 原始负期望，不能作为 rescue 或扩仓方向。
- `diagnostics/hype-5m-pbtr-v3-3-1-pb005-arm4-2026-06-27.md`：测试 `pullback_buffer=0.005` 且 stop-arm 从第 `7` 根提前到第 `4` 根，deadline 仍为第 `9` 根。在 1m/5m 重叠样本中，原始信号数从 baseline 的 `5098` 降到 `4667`（`-8.45%`），但因为更早 armed、平均持仓缩短，单仓实际交易数反而上升 `+7.81%` 到 `+16.93%`。armed 率提高约 `18.68%-20.49%`，deadline 率同步下降，但 PF 全面变差：5m conservative `0.606 -> 0.552`，5m optimistic `0.591 -> 0.507`，1m conservative `0.565 -> 0.476`，1m optimistic `0.591 -> 0.507`。结论是提前 trailing 改善执行形态但更早暴露噪声止损，不能救回 V3.3.1。

## 当前决策

- `HYPE-5M-PBTR-V1`：历史旧口径胜率体验基线；strict live audit 显示 live-realistic PF 仅 `0.637`、总收益 `-87.29%`，不能作为回退上线或 dry-run 候选。
- `HYPE-5M-PBTR-V2`：当前主要收益 dry-run 候选，频率和 payoff 更高，但胜率略低。
- `HYPE-5M-PBTR-V2.1-clean`：在观测实盘成本分析下，作为 V2 的首选简化表达；表现与 V2 基本一致，同时移除了不活跃解释参数。
- `HYPE-5M-PBTR-V2.1A`：已经进入实盘/实盘 dry-run 的收益候选；严格 live-realistic 口径下 PF 降至 `0.54`。unlock-exit、fixed-hold、本地 dry-run ledger 与 immediate-TP 审计确认第 7 根附近 stop 子集赚钱依赖旧 stop 价成交；即时 1ATR 止盈也不能修复。不应扩大仓位，只能作为极小资金监控样本，并先修正 runner 记账/退出口径。
- `HYPE-5M-PBTR-V3`：来自 V2.1A、关闭 final HTF 的独立高频研究候选；与 `V3-lite = V2.1A + dir_htf >= 0` 并行测试，不作为生产直接替代版本。
- `HYPE-5M-PBTR-V3.1`：来自 V3，将 `min_hold_bars` 提高到 `9`；作为高收益研究候选单独 dry-run，重点观察真实回撤是否显著扩张。
- `HYPE-5M-PBTR-V3.2`：来自 V3.1，删除剩余入场过滤器；保留为 clean 高频表达历史记录。
- `HYPE-5M-PBTR-V3.3`：来自 V3.2，删除所有兼容/关闭/保护/基本不触发参数；已不再作为当前同事实盘复现首选，因为严格 live-realistic trailing 口径下 PF 降至 `0.58`，即时 TP 网格最佳 `2.5ATR` 也只有 PF `0.615`，新增 retry-arm overlay 的 5m/1m 保守与乐观口径也全部低于 PF `1`。
- `HYPE-5M-PBTR-V3.3.1`：V3.3 的实盘 stop-arm retry overlay 记录版；修复 `-2021` 崩溃、短间隔 retry 和第 10 根市价兜底审计问题，但原始 5m/1m 悲观与乐观回测均低于 PF `1`。上一单平仓价顺势过滤、range10 早停止盈、全量组合式保本/trailing/早退 overlay、昨晚实盘复盘提出的五类入场过滤方向、以及轻量 ML 事件质量选择器都无效；去掉初始止损 floor 后，深回踩 long-only + 动量/spread 过滤出现 `35-61` 笔的四口径正收益 rescue 线索。当前状态从“完全 no-go”调整为“原始 V3.3.1 no-go，但低频事件质量子集可继续 walk-forward 复核”，仍不作为 paper/live 候选。
- `HYPE-5M-PBTR-V3.3-reinit-trailing`：方案 2 的机制修复记录；可执行性改善，但原参数 PF 仍约 `0.61`，不是可交接版本。
- `HYPE-5M-PBTR-V4`：来自 V3.3 有效单因子组合测试；样本内显著强于 V3.3，但严格 live-realistic trailing 口径下 PF 降至 `0.67`，不应进入直接 paper-live 交接。
- `HYPE-5M-PBTR-fixed-bracket`：固定 ATR 止盈止损修复尝试；退出完全可执行，但 V3.3/V4 信号没有恢复稳健正期望，记录为 no-go。
- `HYPE-5M-PBTR-reset-bracket`：每 5m 重设 TP/SL 修复尝试；V3.3 表面 PF 改善依赖极少数超长持仓和深回撤，V4 仍亏损，记录为 no-go。
- `HYPE-5M-PBTR-reset-bracket-maxhold48`：对 reset bracket 加 48 根 K 最长持仓后，V3.3/V4 均失效，确认超长持仓假改善不可用。
- `HYPE-5M-PBTR-live-repair-plan`：当前建议；冻结 V3.3/V4 实盘交接，下一轮按 executable-first V5 重做，不再围绕旧锁仓回测继续调参。
- `HYPE-5M-PBTR-V5-executable-search`：已完成首轮，结论为 no-go；直接规则和简单事件过滤都没有实盘正期望，下一步若继续应改为 leakage-safe 事件质量建模，或者放弃这条 5m pullback-trailing 线。
- `HYPE-5M-PBTR-V5.1-event-quality`：已完成首轮事件质量筛选和候选消融；发现了可执行、正期望但边际很薄的 observation-confirmed 候选。当前结论是“有研究价值，但不是实盘版本”；必须继续做 walk-forward/ranking 化、audit，并在线记录所有 rejected trigger。
- `HYPE-5M-PBTR-V5.2-walk-forward-ranking`：已完成首轮；ranking 方法没有复现 V5.1 固定阈值的正期望，记录为 no-go for paper deployment。V5.1 固定阈值只能当作可疑研究线索，不能当作 live 规则。
- `HYPE-5M-PBTR-V6-live-executable-search`：已完成泄漏控制搜索。原始搜索用于发现候选，不直接作为 live spec；后续必须优先阅读 V6 candidate robustness 和 V6 full-parameter ablation。
- `HYPE-5M-PBTR-V6`：当前最可执行的新候选，已正式进入主账。它放弃旧 `min_hold_bars + trailing`，改成闭合 K 信号、下一根 open 入场、入场即固定 TP/SL、36 根 K 时间退出。允许进入 audit / 极小资金 dry-run 设计，但生产 sizing 前必须先验证真实盘口滑点、reduce-only bracket 维护、重启恢复、以及至少连续 `30-50` 笔 paper 订单的 live/outcome 偏差。
- `diagnostics/hype-5m-pbtr-v6-tp25-sizing-2026-06-27.md` 与 `diagnostics/hype-5m-pbtr-v6-1-trade-paths-2026-06-27.md`：将 `TP=2.5ATR + fixed 3x` 记录为 `HYPE-5M-PBTR-V6.1` sizing/exit 变体，并生成每笔交易的局部 5m K 线 HTML 路径图。V6.1 全样本 `157` 笔，fixed `3x` 总收益 `+408.95%`、PF `1.773`、胜率 `63.69%`、最大回撤 `-25.63%`、单笔最差 `-14.81%`；退出分布为 target `87`、time_open `68`、stop_market `2`。结论：V6.1 回测收益漂亮，但 sizing 风险显著高于 V6，只能作为 audit sizing variant，不能直接生产。
- `diagnostics/hype-5m-pbtr-v6-1-tp-trigger-trailing-2026-06-27.md`：测试 V6.1 “触发 `2.5ATR` 止盈后不平仓，改为 trailing stop 让利润奔跑”。扫描 `lock_atr=0/1/1.5/2/2.5`、`trail_atr=1/1.5/2/2.5/3/4`、`max_hold=36/72/144` 后，所有 trailing overlay 都低于 fixed TP 基线。最强 `trigger2.5_lock2.5_trail2.5_max36` 为总收益 `+364.32%`、最大回撤 `-27.70%`，不如 fixed `TP=2.5ATR` 的 `+408.95%`、`-25.63%`。结论：V6.1 暂不加 trailing；它的 edge 是吃固定目标，不是右尾趋势跟随。
- `diagnostics/hype-5m-pbtr-v6-1-short-combo-search-2026-06-27.md`：按用户要求搜索 short-only executable bracket 策略，并与 `HYPE-5M-PBTR-V6.1` long-only 做严格单仓组合回放。宽网格共保留 `255596` 条 short 候选结果；top short 基本收敛为 `dir_ret48_bps>=400` 的快速下跌动量过滤。收益最高组合 `combo_short_rank1` 为 `212` 笔、总收益 `+973.56%`、PF `1.776`、最大回撤 `-28.69%`；更均衡的 `combo_short_rank2` 为 `210` 笔、总收益 `+833.71%`、PF `1.771`、最大回撤 `-22.38%`，优于 V6.1 long-only 的 `+408.95%` / `-25.63%`。但 top short 的 VAL/OOS 样本只有个位数；要求 `VAL>=5/OOS>=10` 后只剩 `2` 个候选，组合回撤分别约 `-50.20%` 和 `-33.82%`。原始搜索时先列观察线索；后续 `combo_short_rank2` 已经由 V6.2 全参数消融固化为 paper/live-dry-run 候选。
- `ablations/hype-5m-pbtr-v6-2-full-parameter-ablation-2026-06-28.md`：按用户要求将 `combo_short_rank2` 正式记录为 `HYPE-5M-PBTR-V6.2`，并做全参数消融和小额实盘可行性复核。V6.2 基线为 `210` 笔、fixed `3x` 总收益 `+833.71%`、PF `1.771`、胜率 `64.76%`、最大回撤 `-22.38%`、最差单笔 `-14.81%`；分边为 long `157` 笔、`+408.95%`、PF `1.773`，short `53` 笔、`+83.46%`、PF `1.764`。测试 `75` 个变体，`40` 个通过 robust gate；long leg 有可用邻域，但所有 short entry/filter 变体均未通过，说明 short leg 不能随意放宽。V6.2 无旧 delayed trailing stop 穿越问题，但仍有 bracket 订单维护、取消一致性、滑点/跳空和 short 样本偏少风险。结论：V6.2 可进入 paper / 极小资金 live-dry-run 候选；若真钱观察，应从 `1x` 或极小 notional 开始，不按 `3x` 生产。
- `HYPE-5M-PBTR-V6.2.1`：接受 V6.2 消融中的 `long_htf_threshold_0p0` 作为 V6.2.1 live runner 默认表达。它只把 long leg 从 V6.2 的 `htf_spread >= 0.5` 放宽为 `htf_spread >= 0`，short rank2 不变；fixed `3x` ablation 为 `219` 笔、总收益 `+1022.25%`、PF `1.804`、胜率 `64.38%`、最大回撤 `-22.35%`，OOS PF `1.439`。该结果允许进入 `hype-pullback-enhance` dry-run / 极小 notional live audit，但不是生产 sizing；默认配置应先 `dry_run`、`1x`、小 notional，并重点验证 bracket 订单、撤单一致性、timeout、市价滑点、重启恢复和 SQLite 复盘字段。
- `ablations/hype-5m-pbtr-v6-2-1-full-parameter-ablation-2026-06-29.md`：按用户要求对 `HYPE-5M-PBTR-V6.2.1` 做专项全参数消融。沿用 V6.2 的数据、成本、单仓回放和 robust gate，共测试 `75` 个单因子/组合/sizing 变体，除 baseline 外 `37/74` 个通过 gate。结论：`htf_spread>=0` 仍是默认表达；收紧回 `0.5` 降到 `+833.71%` / PF `1.771`，完全删除 HTF 过滤降到 `+895.91%` / PF `1.745` 且回撤扩大到 `-24.10%`。`long_tp_atr=4.0` 与更高收益的 `short_htf_threshold_0p5` 都不替换 baseline，前者弱于 V6.2.1，后者 short OOS 只有 `3` 笔、未过 gate。
- `diagnostics/hype-5m-pbtr-v6-2-1-live-feasibility-audit-2026-06-30.md`：按用户要求深查 V6.2.1 是否存在未来函数、价格穿越或不可实盘问题。结论：未发现明确未来函数、同 K TP/SL 乐观顺序或旧 V3/V4 delayed trailing crossed stale stop 旧价成交；截断重算 `91` 个 feature-point 失败 `0` 个，baseline 没有 stop/target open-gap 退出，也没有同根 TP/SL 同触发。当前数据湖到 `2026-06-30T06:15Z` 后 fixed `3x` 为 `220` 笔、`+1054.07%`、PF `1.813`、最大回撤 `-22.35%`；bracket 延迟一根 5m K 的保守口径仍为 `+1030.87%`、PF `1.803`、最大回撤 `-23.73%`。状态不升级：仍只允许 dry-run / 极小 notional live audit，必须用真实订单日志验证 bracket 成对维护、单边成交撤单、timeout 市价平仓、重启恢复和滑点。
- `live-specs/hype-5m-pbtr-v6-2-1-live-spec.md`：按用户要求为同事实盘观察导出完整复现规格。该 spec 单文件列出 V6.2.1 的 long/short leg 参数、特征公式、相邻信号抑制、组合单仓、入场即 reduce-only TP/SL bracket、timeout open、状态持久化、重启恢复、回归验收数值和 `30-50` 笔 live audit gate。用途是让同事的 AI 不读研究脚本也能复现策略；状态仍是 dry-run / tiny-notional audit，不是生产批准。
- `diagnostics/hype-5m-pbtr-v6-2-1-dynamic-atr-bracket-2026-06-30.md`：按用户询问测试“固定 TP/SL 改动态 ATR TP/SL”。确认 V6.2.1 当前默认是 fixed entry-ATR bracket：TP/SL 用信号 K `ATR14` 一次性算出，持仓中不再随 ATR 变化。本轮测试 `4` 类 live-executable 动态 ATR bracket、共 `48` 个变体；最高收益 `entry_anchor_dynamic_atr__tp1p5__sl1p0` 为 `190` 笔、`+1124.81%`、PF `1.870`，但 DD 扩到 `-29.89%` 且 `186` 笔发生实际止损放宽；低回撤代表 `close_reset_dynamic_atr__tp0p75__sl1p25` 为 `+882.65%`、PF `1.838`、DD `-20.25%`，收益低于 fixed baseline。结论：没有动态版本在收益、PF、回撤三者上同时稳健优于 fixed baseline，默认不替换。
- `ablations/hype-5m-pbtr-v6-2-tp4-htf0-combo-probe-2026-06-28.md`：测试两个正向单因子是否能叠加：`long_tp_atr=4.0` + `long_htf_threshold=0.0`。组合 fixed `3x` 为 `191` 笔、总收益 `+876.75%`、PF `1.781`、胜率 `58.64%`、最大回撤 `-24.43%`、OOS `14` 笔 / PF `1.683`，通过 robust gate；但它低于单独 `long_htf_threshold=0.0` 的 `+1022.25%` / PF `1.804`，且回撤高于 V6.2.1。结论：`TP4+HTF0` 可作为观察变体，但不替换 `hype-pullback-enhance` 默认 V6.2.1（`TP=2.5ATR + htf_spread>=0`）。
- `HYPE-5M-executable-broad-search-2026-06-25`：按用户提出的 `>=20x` 年化、`>=50%` 胜率、最大回撤优于 `-20%`、可实盘四项硬条件，对旧 indicator entry styles 做 `13134` 个入场即 bracket 的严格可执行搜索。无命中；即使不设最低交易数，最高年化也只有约 `1.18x`，`>=100` 笔交易时最高年化约 `1.05x`。V6 paper candidate 是目前最接近“可实盘 + 胜率/回撤达标”的候选，但年化远低于 `20x`，不能包装成满足本次目标的策略。
- 下一轮 `HYPE-5M-PBTR` 研究优先级：第一是让 `hype-pullback-enhance` 先跑 V6.2.1 dry-run / run-once，记录接受信号、虚拟或真实 bracket TP/SL/timeout、撤单一致性和真实盘口偏差；第二是继续对 `dir_ret192_bps` 与 long HTF 阈值做 walk-forward 固化，确认 `788.123 bps` 与 `htf_spread >= 0` 不是事后阈值；第三才是考虑极小资金 live。不要再把旧 `min_hold_bars + trailing` 回测当作实盘依据。
- V1/V2/V2.1/V3/V3.1/V3.2/V3.3/V3.3.1/V4/V5.1/V5.2/V6/V6.1/V6.2/V6.2.1 候选在生产 sizing 前都必须先有 live dry-run 或 audit 证据；其中 V3.3.1 当前已是 no-go research，只能保留其线上风控/审计启发。
- `2026-07-08`：状态口径对齐。`HYPE-5M-PBTR-V6.2.1` 已在 quant-runner 以 `hype_pullback` dry-run 配置运行（`configs/dryrun.toml`），状态确认为 `dry-run / forward-test required`，并补建 `runner-tracking/` 目录（此前缺失，违反 dry-run 准入条件）。首份 runner 观察报告缺失前不得升级 `live`，也不得据此给出 `NO-GO`。
- `2026-07-09`：对 2026-06 已知信号窗口做 runtime/research 对拍。Research 源为 feasibility audit `baseline_stop_first` 的 16 笔 June 成交；runtime 用 `quant-runner replay-dry-run --name hype-pullback-dry-run --limit 15000 --start-ts 2026-06-01T00:00:00Z --end-ts 2026-06-30T06:15:00Z`。结果 `16/16 MATCH`（`signal_ts/side/entry_ts/exit_ts/reason/entry_price/net_ret_1x`）。报告：[`runner-tracking/hype-5m-pbtr-runner-2026-07-09.md`](runner-tracking/hype-5m-pbtr-runner-2026-07-09.md)。同日确认线上 7/1-7/9 无信号是市场空窗，不是实现漏信号。状态仍为 `dry-run / forward-test required`；真实 fill 生命周期尚未验收。

## 2026-07-10 既有 tiny-notional live 追认

- 本条是对已经存在的 `hype-pullback-live enabled=true` 运行事实的追认，
  不是事前生产批准，也不把 V6.2.1 提升为 production sizing。
- 允许级别固定为 `tiny_live_pilot`，复核截止
  `2026-07-24T00:00:00Z`；到期前必须重新确认，否则后续部署/重启门禁应拒绝。
- 资金边界是专用 `hype-pullback-live` 子账户当时的全部余额；禁止未写
  decision log 的追加资金。
- 当前仍缺真实 fill 生命周期、部分成交、本地 OCO、重启恢复和平台安全闸
  的线上验收。Runner 新 execution v2 在完成离线故障注入和 flat 窗口切换前
  默认关闭。

## 2026-07-11 execution v2 source gate complete

- `live_execution_sim.rs` 已覆盖超时已成交、partial fill、保护/紧急平仓失败、
  entry-arm kill、孤儿单撤销和 user-stream 断线。
- source config 已切换为 `execution.enabled=true` /
  `user_stream_enabled=true`，但尚未部署，现网服务不因此改变。
- entry-arm kill 的恢复策略固定为自动撤未成交 entry，或 reduce-only 平掉
  孤儿仓位，然后继续 fail-closed 等待人工复核。
- 下一步只能在 live flat、无挂单且 artifact/unit 原子安装 preflight 通过后
  部署；部署后必须回写首次 user stream/reconcile 和真实 fill 证据。

## 2026-07-11 execution v2 live-only cutover

- preflight 再次确认 live flat、无挂单、无 open live trade，远端 main 干净。
- Runner `712b3e9` 的 GitHub Actions artifact 经 ELF x86-64 与 SHA-256
  校验后安装；只替换/restart live，dry-run 进程和 unit 未改动。
- live 已运行 `Type=notify + WatchdogSec=120`，私有 user stream 已连接，
  首周期 health `ok`，跨完整 watchdog 周期 PID 不变、重启数为 0、journal
  无 warning/error。
- 状态保持 `live / tiny-live-pilot / forward-test required`，不扩大资金；
  第一笔真实 fill 仍必须逐单回写并在 2026-07-24 前复核。

## 2026-07-13 统一 execution 引擎代码门禁（未部署）

- Runner 已删除 `platform.execution.enabled` 和 live V1 fallback；dry-run/live
  共用唯一订单生命周期，只在 venue 层分别使用持久化 simulated venue 与
  Binance REST + User Data Stream。上文“默认关闭/切换为 true”是当时的历史
  记录，不再代表下一版配置能力。
- 本次配置 schema 与旧二进制不兼容，禁止 binary-only rollback。发布必须在
  live flat、无挂单、无 open trade 时先停止 service，再同步 `origin/main`
  配置并安装匹配 Actions artifact；失败后保持 service 停止，只允许 forward fix
  或 `origin/main` revert commit + 对应 artifact。
- `risk-resume` 改为拿 `runner.lock` 后执行 pending、venue/local position 和保护单
  reconcile；只有 clean 才清除 execution/strategy pause 与 `MANUAL_HALT`，禁止
  手工编辑 `engine_state.json` 恢复。
- 存量 dry-run 持仓迁移、迁移中断恢复、EMA-X 仅 stop、six-asset 显式 symbol、
  mismatch 拒绝 resume 和 candle-count memo/ledger 滑点一致性均增加回归覆盖。
- 当前仍是代码变更，未部署、未重启，也没有新的真实 fill 证据；PBTR 状态保持
  `live / tiny-live-pilot / forward-test required`，不得扩大资金。

## 2026-07-13 统一 execution 引擎已部署

- 用户明确批准在 candle-count 与 six-asset 两笔 dry-run open trade 存续时执行
  双服务切换；live 自身在发布前后均为 local/exchange/ledger flat 且无挂单。
- Runner `cd00ef24c8f2c33d17bee19c51d017e264c76356` 的 Actions artifact
  `0ce2b5513716cd84cf825abf19db4c65d6509b6386721c438bbc06fc022735a5`
  已按 stopped-service 原子流程安装；配置先由新 binary `validate-config`，
  安装失败不会 binary-only rollback。
- 两笔 dry-run 状态均完成 `simulated_venue_migrated`：candle-count 恢复 entry +
  reduce-only TP/SL，six-asset 恢复 symbol-explicit HYPE entry。跨 watchdog 周期
  PID 稳定、重启数为 0、无 warning/error、全部 health=`ok`。
- PBTR 没有新交易证据，live 仍为 tiny pilot；本次只完成执行引擎切换，不改变
  promotion、资金边界或 2026-07-24 复核期限。

## 2026-07-13 graceful shutdown 通知去重决定

- 双服务切换产生 7 条策略级 shutdown outbox；因 live/dry-run watchdog 对共享
  SQLite pending rows 非原子读取，其中 6 条被发送两次，用户实际收到约 13-14 条。
- 决定删除逐策略 critical shutdown，改为每个 systemd service 一条汇总；共享
  outbox 消费改为 SQLite 原子 claim + lease owner fencing；dispatcher 在退出前
  按 dedupe key 立即投递，避免两个进程重复投递或依赖已退出 watchdog。
- 该修复只影响运维通知，不影响策略、订单、持仓、PnL 或 live-readiness。
- 已按标准 artifact 流程部署到 `bd3f33d`
  （Actions run `29231086156`，SHA-256
  `1af8a2df3591bfb4dd28991302ad03d215ae8491d2202c59612d68ef8d703f48`）。
  新二进制验证重启时 outbox 仅 2 条汇总 `service_graceful_shutdown`，
  各 `attempts=1`，确认去重生效。

## 2026-07-13 runtime 稳定性故障域调整决定

- live `positionRisk` 和 dry-run SOL OHLCV 各发生一次 transient timeout，旧运行
  模型均把单次依赖失败扩大为 service `exit 1`；另确认旧 watchdog 会因
  `already_processed` 缺少 success timestamp 形成 false-stale 重启。
- 决定把安全边界改为“未知状态禁止增加风险，但持续风险管理”：transient
  reconcile 关闭 entry gate 并原地重试；已有仓位、user stream、撤单、保护和平仓
  不得停止。只有成功 snapshot 确认的 mismatch 才进入持久 fail-closed。
- market-data/self-managed/live group 改为独立 supervisor；单组错误不再终止兄弟
  group。systemd watchdog 只证明 control plane 可调度，策略 freshness 独立告警。
- Runner `e69589f` 已于 `2026-07-13 21:02-21:03 CST` 按 dry-run → live
  两阶段部署，Actions run `29251245126` 与 artifact SHA-256
  `e6b4420df1e9e9cc7eea4d011e21c3cb3619c441131ec33c881b3c9e8f123b30`
  已校验。继续保持 tiny-live-pilot，不增资，不改变 promotion、parity 或
  2026-07-24 复核门禁。

## 2026-07-15 tiny-live 平台硬风控决定

- live 平台数值闸改为主动阻断新增风险：单策略北京时间自然日已实现净亏损达到
  `5 USDT`、请求开仓名义超过 `50 USDT`，或连续 cycle error 达到 `3` 次时禁止
  新开仓；撤单、保护恢复和平仓不受影响。
- 该配置用于约束既有 dedicated subaccount tiny-live-pilot，防止未记录增资后
  风险随余额自动扩大；不改变“禁止未记录追加资金”、promotion、parity 或
  2026-07-24 复核期限。
- freshness 隔离改为单 market-data group / Driver bundle 的本地故障域，兄弟
  策略和 systemd control-plane watchdog 不再被单策略 stale 连带重启。
- 当前仅完成本地配置/代码变更，尚未部署；线上事实仍以 2026-07-13 artifact 为准。

## 2026-08-03 runner 执行安全加固（未部署）

- 全仓库风险审计（2026-08-02）的 P1 执行安全项全部修复并本地验证：
  CLI live 授权强制、protection deadline 先平仓再暂停、REST 对账识别保护单
  部分成交（幂等）、入场等待终态成交、marginType 严格校验与回读确认、
  `engine_state.json` fsync 耐久性与 schema version、密钥隔离（dry-run 不再
  加载 live.env、密钥 0600、disabled 实例不读凭据进内存）。同步落地低风险
  P2 运维硬化：validate-config 完整校验、disabled 实例 ledger 写回
  enabled=0、release workflow 限 main、Actions 固定 SHA、cargo audit 门禁。
- 两个架构性 P2（V6/V5 Driver 耦合、多市场统一限流）按稳定性优先原则继续
  冻结，后续单独立项。
- 全部为平台执行语义加固，策略信号/出场/参数口径不变，V6.2.1 live spec 无需
  修订；不改变 promotion、parity、资金边界或 2026-09-24 授权复核门禁。
- 部署前置：`.secrets/dryrun.env` 由部署脚本从 live.env 自动派生（仅通知
  变量），服务器只维护 live.env；live 首次以新二进制启动时保证金模式校验
  属预期 fail-fast。
- 详细改动与测试证据见
  [`hype-5m-pbtr-runner-2026-08-03.md`](runner-tracking/hype-5m-pbtr-runner-2026-08-03.md)；
  当前仅完成本地变更（234 测试全绿），尚未提交与部署。
