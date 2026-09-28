# HYPE-1D-MA7-Machine-Learning-Trend Core Ledger

## Family Identity

- Full family name：`HYPE-1D-MA7-Machine-Learning-Trend`
- Alias：`HYPE-1D-MA7-MLT`
- Market：Binance USD-M `HYPEUSDT` perpetual
- Timeframe：UTC `1d`；来源为可信 `1h` 闭合 K 聚合
- Mechanism：P0 学习全体日频状态；P1 限定 strict cross；P2 扩展 raw-cross episode；P3 用精确 raw-cross、purged OOF 特征块和 canonical survival 学习入场与趋势死亡；P4 直接学习 exact V7.1 的教师动作并尝试 residual 退出；P5 以稳定趋势生命周期监督 raw-cross root；P6 以 exact V7.1 为 core，分别学习 entry value、survival 和 reversal value；P7 用 BTC/ETH/BNB/SOL 训练 survival-only，再覆盖 HYPE 的 V7.1 非保护性日线退出；P8 回到 raw MA7 cross 本身，做跨资产 first-hit 事件图谱，不训练 ML。
- Collision warning：本家族不是 `HYPE-1D-MA7-ABT-V7.2`，不继承或改写 V7.1。

## Current State

- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 当前版本：无 registered version
- 当前实验：P8 已完成 raw `SMA7` cross first-hit 事件图谱。五资产完整 primary 事件 `624`，成功率 `32.9%`，相对非穿越同侧 Baseline B uplift `+3.3pp` 但 cluster bootstrap `[-2.2pp, +6.1pp]` 跨不过 0；14 日同资产同方向去重后成功率降至 `29.6%` 且净期望转负。HYPE 前365日只读 `2025-05-31`→`2026-05-30`，后81日未读取。裁决 `INSUFFICIENT_SAMPLE`，见 [P8 结果](diagnostics/hype-1d-ma7-mlt-p8-ma7-cross-first-hit-event-atlas-2026-08-31.md)。
- 下一门禁：P7 合同 `holdout_permitted=false` 不变，不得把本次读取当成晋升证据。后续新合同的供体训练可以使用币安全部可用 K，不必截到 HYPE 训练终点；不得降阈值、不得把 HYPE 放入训练集。P0–P7 均不授权 runner。

## Version Rules

- 特征、标签、模型候选、训练/验证切分、执行或选择规则任一实质变化，均须新合同；不得在已揭示验证集上静默重选。
- 自 P3 起，`2026-05-31` 至 `2026-08-19` 的 81 日窗口永久只允许由冻结后的评估器读取；特征构造、标签设计、模型/阈值选择、消融和停止判断必须只使用前 365 日及其内部时间顺序 OOF。因该窗口已在 P0–P2 中揭示，它只能标记为 reused holdout，不能恢复为 clean OOS。
- P0 是 diagnostic experiment，不自动登记版本。

## Version Table

| 版本/实验 | 状态 | 角色 | 证据 | 决策 |
| --- | --- | --- | --- | --- |
| P0 365d train / locked validation | `ML_NO_EDGE / diagnostic-only / not promoted / not live-ready` | ML 与 train-only MA 参数搜索的公平后段比较 | [冻结合同](specs/hype-1d-ma7-mlt-p0-365d-train-validation-contract-2026-08-27.md) · [结果](diagnostics/hype-1d-ma7-mlt-p0-365d-train-validation-2026-08-27.md) · [机器摘要](artifacts/hype_1d_ma7_mlt_p0_365d_train_validation_2026-08-27_summary.json) | ML validation `-38.64%/-52.87%`，弱于规则 `-2.64%/-30.80%` 与买持 `+0.62%`；不登记版本 |
| P1 strict cross / dynamic exit | `MECHANICAL_HOLDOUT_PASS_BUT_UNPROVEN_LOW_SAMPLE / diagnostic-only / not promoted / not live-ready` | 事件级趋势成功分类 + 持仓日动态退出 | [冻结合同](specs/hype-1d-ma7-mlt-p1-cross-event-dynamic-exit-contract-2026-08-27.md) · [结果](diagnostics/hype-1d-ma7-mlt-p1-cross-event-dynamic-exit-2026-08-27.md) · [机器摘要](artifacts/hype_1d_ma7_mlt_p1_cross_event_dynamic_exit_2026-08-27_summary.json) | 验证 `+6.82%/-1.44%/3 trades` 机械胜过简单 cross，但 entry OOF AUC `0.444`、样本极少且复用已揭示窗口；未胜 V7.1，不登记版本 |
| P2 episode policy learning | `BEHAVIOR_IMPROVED_BUT_MODEL_GENERALIZATION_FAILED / diagnostic-only / not promoted / not live-ready` | raw-cross 7日episode + entry/survival + `LONG/FLAT/SHORT` | [教学合同](specs/hype-1d-ma7-mlt-p2-episode-policy-learning-contract-2026-08-27.md) · [结果](diagnostics/hype-1d-ma7-mlt-p2-episode-policy-learning-2026-08-27.md) · [机器摘要](artifacts/hype_1d_ma7_mlt_p2_episode_policy_2026-08-27_summary.json) | 教学回放 `+9.41%/-24.09%/7 trades/1 reversal`，但 OOF AUC `0.403/0.467` 且 raw-cross H7 `+34.57%`；不登记版本 |
| P3 purged cross survival | `VALIDATION_FAILED / diagnostic-only / not promoted / not live-ready` | 精确 raw-cross + train-only 特征块 + canonical survival | [冻结合同](specs/hype-1d-ma7-mlt-p3-purged-cross-survival-contract-2026-08-27.md) · [结果](diagnostics/hype-1d-ma7-mlt-p3-purged-cross-survival-2026-08-27.md) · [机器摘要](artifacts/hype_1d_ma7_mlt_p3_purged_cross_survival_2026-08-27_summary.json) | 内部确认 `+7.47%`，但81日验证 `-8.96%/-26.10%/7 trades`、entry AUC `0.500`；不登记版本 |
| P4 V7.1 behavior clone + residual | `V7_1_NOT_BEATEN / diagnostic-only / not promoted / not live-ready` | exact V7.1 日线行为克隆 + train-only filter/exit-extension | [冻结合同](specs/hype-1d-ma7-mlt-p4-v7-1-behavior-clone-residual-contract-2026-08-27.md) · [结果](diagnostics/hype-1d-ma7-mlt-p4-v7-1-behavior-clone-residual-2026-08-27.md) · [开发摘要](artifacts/hype_1d_ma7_mlt_p4_v7_1_behavior_clone_residual_2026-08-27_development_summary.json) · [验证摘要](artifacts/hype_1d_ma7_mlt_p4_v7_1_behavior_clone_residual_2026-08-27_validation_summary.json) | 训练 fit 100%，OOF transition recall `72.73%`，训练 residual 胜教师；81日 residual `+25.06%` 弱于教师 `+28.19%`，不登记版本 |
| P5 opportunity repair + lifecycle | `V7_1_NOT_BEATEN / diagnostic-only / reused-holdout / not promoted / not live-ready` | raw-cross root + stable-trend lifecycle 二分类 + 补入/持有/退出/反手 | [冻结合同](specs/hype-1d-ma7-mlt-p5-opportunity-repair-lifecycle-contract-2026-08-28.md) · [结果](diagnostics/hype-1d-ma7-mlt-p5-opportunity-repair-lifecycle-2026-08-28.md) · [开发摘要](artifacts/hype_1d_ma7_mlt_p5_opportunity_repair_lifecycle_2026-08-28_development_summary.json) · [验证摘要](artifacts/hype_1d_ma7_mlt_p5_opportunity_repair_lifecycle_2026-08-28_validation_summary.json) | OOF/验证 AUC `0.699/0.708`，训练覆盖段数 `19/23` 高于 V7.1 `14/23`；但训练收益更低，81日 `-8.99%` 对 V7.1 `+28.19%`，不登记版本 |
| P6 V7.1 anchor + three-head lifecycle | `DEVELOPMENT_FAILED_HOLDOUT_LOCKED / diagnostic-only / not promoted / not live-ready` | V7.1 core + entry/survival/reversal 三头残差策略 | [冻结合同](specs/hype-1d-ma7-mlt-p6-v7-anchor-three-head-lifecycle-contract-2026-08-28.md) · [结果](diagnostics/hype-1d-ma7-mlt-p6-v7-anchor-three-head-lifecycle-2026-08-28.md) · [开发摘要](artifacts/hype_1d_ma7_mlt_p6_v7_anchor_three_head_lifecycle_2026-08-28_development_summary.json) · [冻结清单](artifacts/hype_1d_ma7_mlt_p6_v7_anchor_three_head_lifecycle_2026-08-28_development_manifest.json) | 完整训练 `+729.80%` 看似胜出，但三头 OOF 约等于随机，内部确认新增3笔全亏；门禁失败，81日未读取，不登记版本 |
| P7 cross-asset survival-only overlay | `DEVELOPMENT_FAILED_HOLDOUT_LOCKED / diagnostic-only / not promoted / not live-ready` | BTC/ETH/BNB/SOL 训练 `SURVIVAL_3D`，覆盖 exact V7.1 非保护性日线退出 | [冻结合同](specs/hype-1d-ma7-mlt-p7-cross-asset-survival-overlay-contract-2026-08-28.md) · [结果](diagnostics/hype-1d-ma7-mlt-p7-cross-asset-survival-overlay-2026-08-28.md) · [开发摘要](artifacts/hype_1d_ma7_mlt_p7_cross_asset_survival_overlay_2026-08-28_development_summary.json) · [冻结清单](artifacts/hype_1d_ma7_mlt_p7_cross_asset_survival_overlay_2026-08-28_development_manifest.json) | 供体 OOF AUC `0.617` 过线，但 HYPE 内部确认与 V7.1 重合、365日迁移更差；门禁失败，81日未读取，不登记版本 |
| P8 MA7 cross first-hit event atlas | `INSUFFICIENT_SAMPLE / diagnostic-only / not promoted / not live-ready` | raw MA7 cross 之后的 1h first-hit 事件图谱，不训练 ML | [冻结合同](specs/hype-1d-ma7-mlt-p8-ma7-cross-first-hit-event-atlas-contract-2026-08-31.md) · [结果](diagnostics/hype-1d-ma7-mlt-p8-ma7-cross-first-hit-event-atlas-2026-08-31.md) · [摘要](artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31_summary.json) · [冻结清单](artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31_development_manifest.json) | 五资产 primary 成功率 `32.9%`；相对 Baseline B uplift 的 bootstrap 下界小于 0，供体只有 2/4 正向，HYPE episode cluster 仅 2；不支持进入 ML 训练 |

## Shared Assumptions

- 数据：标准数据湖 Binance HYPEUSDT perpetual `1h`，只保留显式闭合且完整的 24 根小时 K 后聚合 UTC 日 K。
- 成本：单边手续费 `0.001` + 不利滑点 `4 bps`；另计实际 funding。
- 时序：日收盘只读取当前及历史；最早下一 UTC open 成交；固定 `1x`、单仓、不加仓。
- P0 的固定持有期与 P1 的日收盘动态退出均没有盘中止损，只是方向/机会识别诊断，因此始终 `not live-ready`。

## Evidence Map

- [P0 合同](specs/hype-1d-ma7-mlt-p0-365d-train-validation-contract-2026-08-27.md)
- [P0 结果](diagnostics/hype-1d-ma7-mlt-p0-365d-train-validation-2026-08-27.md)
- [研究脚本](scripts/run_hype_1d_ma7_mlt_p0.py)
- [P1 合同](specs/hype-1d-ma7-mlt-p1-cross-event-dynamic-exit-contract-2026-08-27.md)
- [P1 结果](diagnostics/hype-1d-ma7-mlt-p1-cross-event-dynamic-exit-2026-08-27.md)
- [P1 研究脚本](scripts/run_hype_1d_ma7_mlt_p1_cross_event.py)
- [P1 可拖动交易路径（含 SMA7）](artifacts/hype_1d_ma7_mlt_p1_cross_event_dynamic_exit_2026-08-27_trade_paths.html) · [渲染器](scripts/render_hype_1d_ma7_mlt_p1_trade_path.py) · [清单](artifacts/hype_1d_ma7_mlt_p1_cross_event_dynamic_exit_2026-08-27_trade_paths_manifest.json)
- [P2 教学合同](specs/hype-1d-ma7-mlt-p2-episode-policy-learning-contract-2026-08-27.md) · [P2 结果](diagnostics/hype-1d-ma7-mlt-p2-episode-policy-learning-2026-08-27.md) · [P2 脚本](scripts/run_hype_1d_ma7_mlt_p2_episode_policy.py)
- [P3 冻结合同](specs/hype-1d-ma7-mlt-p3-purged-cross-survival-contract-2026-08-27.md) · [P3 结果](diagnostics/hype-1d-ma7-mlt-p3-purged-cross-survival-2026-08-27.md) · [P3 脚本](scripts/run_hype_1d_ma7_mlt_p3_purged_cross_survival.py)
- [P4 冻结合同](specs/hype-1d-ma7-mlt-p4-v7-1-behavior-clone-residual-contract-2026-08-27.md) · [P4 结果](diagnostics/hype-1d-ma7-mlt-p4-v7-1-behavior-clone-residual-2026-08-27.md) · [P4 脚本](scripts/run_hype_1d_ma7_mlt_p4_v7_1_behavior_clone_residual.py) · [开发冻结清单](artifacts/hype_1d_ma7_mlt_p4_v7_1_behavior_clone_residual_2026-08-27_development_manifest.json)
- [P5 冻结合同](specs/hype-1d-ma7-mlt-p5-opportunity-repair-lifecycle-contract-2026-08-28.md) · [P5 结果](diagnostics/hype-1d-ma7-mlt-p5-opportunity-repair-lifecycle-2026-08-28.md) · [P5 脚本](scripts/run_hype_1d_ma7_mlt_p5_opportunity_repair_lifecycle.py) · [P5 开发冻结清单](artifacts/hype_1d_ma7_mlt_p5_opportunity_repair_lifecycle_2026-08-28_development_manifest.json) · [完整446日对照图](artifacts/hype_1d_ma7_mlt_p5_opportunity_repair_lifecycle_2026-08-28_v7_1_comparison_trade_paths.html)
- [P6 冻结合同](specs/hype-1d-ma7-mlt-p6-v7-anchor-three-head-lifecycle-contract-2026-08-28.md) · [P6 结果](diagnostics/hype-1d-ma7-mlt-p6-v7-anchor-three-head-lifecycle-2026-08-28.md) · [P6 脚本](scripts/run_hype_1d_ma7_mlt_p6_v7_anchor_three_head_lifecycle.py) · [P6 开发冻结清单](artifacts/hype_1d_ma7_mlt_p6_v7_anchor_three_head_lifecycle_2026-08-28_development_manifest.json) · [训练期交易路径](artifacts/hype_1d_ma7_mlt_p6_v7_anchor_three_head_lifecycle_2026-08-28_v7_1_training_trade_paths.html)
- [P7 冻结合同](specs/hype-1d-ma7-mlt-p7-cross-asset-survival-overlay-contract-2026-08-28.md) · [P7 结果](diagnostics/hype-1d-ma7-mlt-p7-cross-asset-survival-overlay-2026-08-28.md) · [P7 脚本](scripts/run_hype_1d_ma7_mlt_p7_cross_asset_survival_overlay.py) · [P7 开发冻结清单](artifacts/hype_1d_ma7_mlt_p7_cross_asset_survival_overlay_2026-08-28_development_manifest.json) · [训练+验证交易路径](artifacts/hype_1d_ma7_mlt_p7_cross_asset_survival_overlay_2026-08-28_v7_1_training_trade_paths.html) · [P7 打到 BTC 的 SCOUT](diagnostics/hype-1d-ma7-mlt-p7-btc-survival-overlay-scout-2026-08-31.md)
- [P8 冻结合同](specs/hype-1d-ma7-mlt-p8-ma7-cross-first-hit-event-atlas-contract-2026-08-31.md) · [P8 结果](diagnostics/hype-1d-ma7-mlt-p8-ma7-cross-first-hit-event-atlas-2026-08-31.md) · [P8 脚本](scripts/run_hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas.py) · [P8 事件表](artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31_events.csv) · [P8 first-hit 矩阵](artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31_first_hit_matrix.csv) · [P8 交互式事件图谱](artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31.html) · [P8 开发冻结清单](artifacts/hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31_development_manifest.json)
- [Artifacts 索引](artifacts/README.md)
