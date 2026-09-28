# Binance-1D-MA7-CTP Core Ledger

## Family Identity

- Full family name：`Binance-1D-MA7-Cross-Trend-Probability`
- Alias：`BIN-1D-MA7-CTP`
- 市场/周期：Binance USD-M USDT 永续，完整 UTC 日 K。
- 机制：只在严格 SMA7 方向穿越事件上，判断下一 UTC open 起 20 日是否先到顺向 `+2 ATR` 而非逆向 `-1 ATR`。
- 碰撞警告：不是 `BIN-1D-CATL` 一般 asset-day 模型，不是 `BIN-1D-TPSA` / `BIN-1D-MA7-RC`，不修改 HYPE P0-P8/V7.1；`HYPER/USDT:USDT` 必须保留。

## Current State

- 当前实验：`P7 Temporal Drift, Score Monotonicity and Calibration Decomposition`。
- 主状态：`explore / diagnostic-only / not promoted / not live-ready`
- P0 SCOUT：裸穿越后约 30% 走出趋势段，斜率/放量/30 日路径几乎不抬升。
- P1 裁决：`UNSTABLE_MA7_EVENT_SIGNAL`。开发期有弱排序，但全面过拟合；2025+ AUC 0.5202，95% CI 穿过 0.50，合并系统 2026 年 AUC 0.4753 并触发年度方向翻转门。
- P2 裁决：`SIGNAL_EXPLAINED_BY_MA7_CORE`。只用 2025 年前 MA7 穿越，单一 pooled 极简模型在 D1-D3 稳定门过线，但 F1 相对 F0 paired AUC 差 95% CI 下界为 -0.0050，不能证明穿越前路径提供独立增量。2026-09-01 已修复 Platt 方法名覆盖与同样本校准评价问题；D2-D3 前向 Brier 由 0.2200 改善到 0.2183，原始排序指标不变。
- P3 裁决：`DATA_BLOCK_NOT_READY`。合同锁定后、训练前严格样本为 52,563 行、338 资产，但 `feature_known_at < entry_ts` 为 0 行且全部等于 `entry_ts`，未满足 P3 明确时点门禁，因此停止训练，不生成 OOF 或增量裁决。
- P3R 裁决：`SUGGESTIVE_CONTEXT_INCREMENT_ONLY`。只修复 P3 时间边界为 `feature_known_at == entry_ts == ts+1d` 后完成训练；B1 流动性与 B3 市场/BTC 环境点估计为正但 CI 穿 0 且 BH q=0.5924，B2 MA30 与 B4 funding 为 `NO_INCREMENT_BEYOND_P2`，无上下文块统计确认。
- P4 裁决：`FULL_B0_REMAINS_REFERENCE`。在 52,563 条严格样本上把 P2 B0 的 69 特征固定分成六组；B0 D1-D3 macro AUC `0.5799`、fold-relative Top10 成功率 `41.62%`，`M_EVENT_25` 与 `M_EVENT_VOL_36` 均未通过非劣门槛；仅 G4 成交活跃度达到 `REQUIRED_DEVELOPMENT_EVIDENCE`。
- P5 裁决：`NO_NEW_INCREMENT_B0_REMAINS_REFERENCE`。严格 pre-2025 样本复现 P4 的 52,563 行；2025+ 主加密验证 46,892 行，B0 year-relative AUC/Top10 为 `0.5589/35.11%`，删除 G3、RSI6、完整周线与组合候选的 2025+ paired AUC/Top10 CI 均未满足确认增量或尾部专家门槛；HYPE 原始分区未读、事件/预测/指标 0 行。
- P6 裁决：`MARKET_OR_SIDE_VALUE_ONLY`。市场状态按 P0R 方向化字段还原为原始 `BULL/MIXED/BEAR` 六格；2025+ 同日同方向 Top5 主检验中，B0 相对同日随机基准成功率差 `-0.15pp`，M1 差 `-1.36pp`、事件标签净收益差 `-0.37pp`，M1 相对 B0 成功率差 `-1.21pp`，未达到 +5pp 研究投入门槛；无合格未揭示新 OOS，记录 `PENDING_FRESH_OOS` 但不建议继续扩特征。
- P7 裁决：`DATA_OR_REPRODUCTION_FAILURE`。P7 复现 2025+ 主加密 `46,892`、2025 `32,111`、2026 `14,781`、HYPE `0`、HYPER 保留、TradFi `100` 排除和 raw 阈值 `0.510070`，但当前 P5 脚本重建 `R_B0_69` 与 P5/P6 冻结 raw score 最大误差 `0.009287`，超过 `1e-8`，按合同停止分数漂移、校准和结构归因解释。
- 运行/交接：无 runner、无 dry-run、无 live spec、无 handoff。
- 隔离：P1-P5 输入、事件、OOF、模型卡/报告中 `HYPE/USDT:USDT` 均为 0 行；P5 从 P0R donor allowlist 排除 HYPE 后按资产分区读取 P0 日线，保留 `HYPER/USDT:USDT`；P5 记录 2025+ 为 `ITERATIVE_REUSED_VALIDATION_2025_PLUS`，known TradFi 仅作 unsupported diagnostic。
- 下一决策门：停止基于同一已看历史继续调参；若要恢复 P7 问题，先恢复可逐行复现的 P5/P6 冻结模型参数或环境，再在读新标签前完成 canonical 数据迁移对账和前瞻 OOS 协议，不默认 promotion。

## Version Rules

- `P0/P1/...` 是研究实验，不是可交易策略版本。
- 只有用户明确要求“登记/冻结 Vx”时才创建 registered strategy version。
- 改标签、屏障、ATR、事件定义或把非穿越日纳入训练，必须新开实验，不得覆盖 P1 裁决。

## Version Table

| 版本/观察 | 状态 | 角色/核心内容 | 关键冻结指标 | 证据 | 决策与 live-readiness |
| --- | --- | --- | --- | --- | --- |
| `P0 MA7 Cross Trend Probability SCOUT` | `explore / diagnostic-only / not promoted / not live-ready` | 四币与全市场裸穿越条件概率 | 全市场 111,918 可标签穿越，合计 30.4% | [合同](specs/binance-1d-ma7-cross-trend-probability-contract-2026-08-31.md)、[全市场](diagnostics/binance-1d-ma7-cross-trend-probability-all-market-2026-08-31.md) | 过滤器几乎不抬升；不是策略 |
| `P1 Cross-Conditioned Entry-Value Modeling` | `explore / diagnostic-only / not promoted / not live-ready` | 只训练 101,187 条合格 MA7 穿越；LONG/SHORT 双头 walk-forward | 2025+ 系统 AUC 0.5202，CI [0.4400, 0.6012]；LONG 0.5232 / SHORT 0.5314；系统 2026 AUC 0.4753；全部主折 `SEVERE_OVERFIT_WARNING` | [合同](specs/binance-1d-ma7-ctp-p1-cross-conditioned-entry-model-contract-2026-09-01.md)、[报告](diagnostics/binance-1d-ma7-ctp-p1-cross-conditioned-entry-model-2026-09-01.md)、[审计](diagnostics/binance-1d-ma7-ctp-p1-modeling-audit-2026-09-01.md) | `UNSTABLE_MA7_EVENT_SIGNAL`；not live-ready |
| `P2 Pooled-Minimal MA7 Cross Stability Audit` | `explore / diagnostic-only / not promoted / not live-ready` | 只用 F0/F1、单一 pooled 方向对齐模型，禁止 2025+ 预测 | 2022/2023/2024 验证 AUC 0.5945/0.5598/0.5715；OOF AUC 0.5673，CI [0.5394, 0.5936]；F1-F0 paired diff CI [-0.0050, 0.0453]；前向校准 Brier 0.2200→0.2183 | [合同](specs/binance-1d-ma7-ctp-p2-pooled-minimal-stability-contract-2026-09-01.md)、[报告](diagnostics/binance-1d-ma7-ctp-p2-pooled-minimal-stability-2026-09-01.md)、[审计](diagnostics/binance-1d-ma7-ctp-p2-modeling-audit-2026-09-01.md) | `SIGNAL_EXPLAINED_BY_MA7_CORE`；校准修复后排序不变；无新 OOS，not live-ready |
| `P3 Independent Context Feature Block Audit` | `explore / diagnostic-only / not promoted / not live-ready` | 计划在 P2 F1 基准上逐块检验流动性、MA30、市场环境与 funding 增量 | 合同锁后严格样本 52,563 行；`feature_known_at < entry_ts` 0 行、`== entry_ts` 52,563 行 | [合同](specs/binance-1d-ma7-ctp-p3-context-feature-block-audit-contract-2026-09-01.md)、[报告](diagnostics/binance-1d-ma7-ctp-p3-context-feature-block-audit-2026-09-01.md)、[审计](diagnostics/binance-1d-ma7-ctp-p3-modeling-audit-2026-09-01.md) | `DATA_BLOCK_NOT_READY`；训练前停止，无 OOF/模型卡，not live-ready |
| `P3R Time-Boundary Repair + Independent Context Feature Block Audit` | `explore / diagnostic-only / not promoted / not live-ready` | P3 审计修复；只把时点门禁改为 `feature_known_at == entry_ts == ts+1d`，其余样本/标签/候选不变 | 严格样本 52,563 行；B3 AUC diff +0.0030，CI [-0.0261, 0.0337]，q=0.5924；B1 +0.0006，q=0.5924；无 confirmed block | [合同](specs/binance-1d-ma7-ctp-p3r-time-boundary-repair-context-feature-block-audit-contract-2026-09-02.md)、[报告](diagnostics/binance-1d-ma7-ctp-p3r-context-feature-block-audit-2026-09-02.md)、[审计](diagnostics/binance-1d-ma7-ctp-p3r-modeling-audit-2026-09-02.md) | `SUGGESTIVE_CONTEXT_INCREMENT_ONLY`；不是策略、无 2025+ 预测、not live-ready |
| `P4 Core Factor Ablation + Compressed Tail-Ranking Audit` | `explore / diagnostic-only / not promoted / not live-ready` | 对 P2 B0 69 特征做六组删除消融、单组诊断、25/36 特征预注册压缩和 15 单元资产 holdout | B0 macro AUC `0.5799`、fold-relative Top10 `41.62%`；`M_EVENT_25` AUC diff `-0.0345`、Top10 diff `+0.49pp`；`M_EVENT_VOL_36` AUC diff `-0.0208`、Top10 diff `-1.76pp`；G4 删除 Top10 diff `-1.38pp`，q=0.009 | [合同](specs/binance-1d-ma7-ctp-p4-core-factor-ablation-compression-contract-2026-09-02.md)、[报告](diagnostics/binance-1d-ma7-ctp-p4-core-factor-ablation-compression-2026-09-02.md)、[审计](diagnostics/binance-1d-ma7-ctp-p4-modeling-audit-2026-09-02.md) | `FULL_B0_REMAINS_REFERENCE`；压缩候选仅供未来新 OOS 观察，未登记策略版本，not live-ready |
| `P5 Oscillator + Completed-Weekly-Regime Increment and 2025+ Validation Audit` | `explore / diagnostic-only / not promoted / not live-ready` | 固定六候选检验删除 G3、Wilder RSI6 与已闭合 UTC 周线增量；2025+ 明确定义为复用验证集 | pre-2025 52,563 行；2025+ 主加密 46,892 行；B0 2025+ AUC/Top10 `0.5589/35.11%`；修复后 `C_NO_G3_58` AUC diff CI `[-0.0099, 0.0162]`、Top10 diff CI `[-0.83pp, 4.66pp]`；周线 lookahead 0 | [合同](specs/binance-1d-ma7-ctp-p5-oscillator-weekly-validation-contract-2026-09-02.md)、[报告](diagnostics/binance-1d-ma7-ctp-p5-oscillator-weekly-validation-2026-09-02.md)、[建模审计](diagnostics/binance-1d-ma7-ctp-p5-modeling-audit-2026-09-02.md)、[周线审计](diagnostics/binance-1d-ma7-ctp-p5-weekly-causality-audit-2026-09-02.md)、[独立验收](diagnostics/binance-1d-ma7-ctp-p5-independent-acceptance-audit-2026-09-02.md) | `NO_NEW_INCREMENT_B0_REMAINS_REFERENCE`；原始 CI/校准/阈值缺陷已最小修复并重跑，弱排序器诊断，不登记策略版本，not live-ready |
| `P6 Market-Regime x Side Conditional Ranking Value Audit` | `explore / diagnostic-only / not promoted / not live-ready` | 只比较 `R_B0_69`、`M0_MARKET_ONLY`、`M1_B0_X_SIDE_X_REGIME`，拆分市场/方向解释与同日同方向选币能力 | 2025+ B0/M0/M1 AUC `0.5589/0.5175/0.5410`；同日同方向 Top5：B0 `-0.15pp`、M1 `-1.36pp` vs 同日随机基准；M1 vs B0 `-1.21pp`，CI `[-2.25pp,-0.26pp]`，BH q `0.084`；M1 净收益差 `-0.37pp` | [合同](specs/binance-1d-ma7-ctp-p6-market-regime-side-conditional-ranking-contract-2026-09-03.md)、[报告](diagnostics/binance-1d-ma7-ctp-p6-market-regime-side-conditional-ranking-2026-09-03.md)、[前瞻协议](specs/binance-1d-ma7-ctp-p6-prospective-oos-confirmation-protocol-2026-09-03.md)、[汇总 JSON](artifacts/binance_1d_ma7_ctp_p6_summary.json) | `MARKET_OR_SIDE_VALUE_ONLY`；2025+ 为复用验证，`PENDING_FRESH_OOS`，不是 V6、不改 runner、not live-ready |
| `P7 Temporal Drift, Score Monotonicity and Calibration Decomposition` | `explore / diagnostic-only / not promoted / not live-ready` | 计划解释 `R_B0_69` 在 2025/2026 的时间漂移、分数单调性和校准差异；合同要求先重建 B0 到 `1e-8` | 样本锚点通过：2025+ `46,892`、2025 `32,111`、2026 `14,781`、阈值以上 `839/511`；B0 重建最大误差 `0.009287`，未过 `1e-8` | [合同](specs/binance-1d-ma7-ctp-p7-temporal-drift-calibration-decomposition-contract-2026-09-04.md)、[报告](diagnostics/binance-1d-ma7-ctp-p7-temporal-drift-calibration-decomposition-2026-09-04.md)、[建模审计](diagnostics/binance-1d-ma7-ctp-p7-modeling-audit-2026-09-04.md)、[汇总 JSON](artifacts/binance_1d_ma7_ctp_p7_summary.json) | `DATA_OR_REPRODUCTION_FAILURE`；停止解释性归因，P8 仅建议 E 冻结观察，not live-ready |

## Shared Assumptions

- 物理输入只允许 CATL P0R donor panel 与其 feature/manifest；ATR 锚点、20 日 `+2/-1` first-hit 与成本模型继承 P0/P0R。
- 信号在完整 UTC 日收盘后形成，从下一 UTC open 起算；同小时双触不利优先。
- `label_entry_net_return` 只作分层诊断，不进 X，不年化、不合成账户权益。
- 2025+ 是 `model-unseen / hypothesis-revealed historical test`，不是严格盲测。
- P2 不读取 2025+ 建模行，不生成 2025+ 预测；P2 仅冻结等待新 OOS 的诊断证据。
- P4 明确标注 `2022-2024 IS REUSED DEVELOPMENT HISTORY, NOT NEW BLIND OOS`；不生成策略仓位、权益曲线、Sharpe、live spec 或交易路径 HTML。
- P5 明确标注 2025+ 为 `ITERATIVE_REUSED_VALIDATION_2025_PLUS`；只可作本轮预注册候选比较，不能参与训练、校准、阈值或新候选生成。
- P6 明确标注受已观察 2025+ 启发；只做事件评分归因，不生成策略仓位、账户权益、Sharpe、live spec 或 runner 改动。
- P7 明确标注 2025+ 为 `ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS`；B0 不能精确重建时必须 fail closed，不得继续讲机制故事。

## Evidence Map

- [家族 README](README.md)
- [决策记录](decision-log.md)
- [P1 脚本](scripts/run_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py)
- [P2 脚本](scripts/run_binance_1d_ma7_ctp_p2_pooled_minimal_stability.py)
- [P3 脚本](scripts/run_binance_1d_ma7_ctp_p3_context_feature_block_audit.py)
- [P3R 脚本](scripts/run_binance_1d_ma7_ctp_p3r_time_boundary_repair_context_feature_block_audit.py)
- [P4 脚本](scripts/run_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py)
- [P5 脚本](scripts/run_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py)
- [P6 脚本](scripts/run_binance_1d_ma7_ctp_p6_market_regime_side_conditional_ranking.py)
- [P7 脚本](scripts/run_binance_1d_ma7_ctp_p7_temporal_drift_calibration_decomposition.py)
- [产物索引](artifacts/README.md)
- [针对性测试](../../../tests/test_binance_1d_ma7_ctp_p1_cross_conditioned_entry_model.py)
- [P2 针对性测试](../../../tests/test_binance_1d_ma7_ctp_p2_pooled_minimal_stability.py)
- [P3 针对性测试](../../../tests/test_binance_1d_ma7_ctp_p3_context_feature_block_audit.py)
- [P3R 针对性测试](../../../tests/test_binance_1d_ma7_ctp_p3r_time_boundary_repair.py)
- [P4 针对性测试](../../../tests/test_binance_1d_ma7_ctp_p4_core_factor_ablation_compression.py)
- [P5 针对性测试](../../../tests/test_binance_1d_ma7_ctp_p5_oscillator_weekly_validation.py)
- [P6 针对性测试](../../../tests/test_binance_1d_ma7_ctp_p6_market_regime_side_conditional_ranking.py)
- [P7 针对性测试](../../../tests/test_binance_1d_ma7_ctp_p7_temporal_drift_calibration_decomposition.py)

## What Not To Put Here

- 不粘贴完整参数表、十分位全表或 SHAP 清单；放到 specs / diagnostics / artifacts。
- 不把每次运行追加成新章节。
