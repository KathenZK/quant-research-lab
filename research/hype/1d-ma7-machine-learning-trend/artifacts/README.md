# Artifacts

本目录保留 `HYPE-1D-MA7-Machine-Learning-Trend` 的机器可审计结果、逐折指标、验证交易和完整交易路径 HTML。

- `hype_1d_ma7_mlt_p0_365d_train_validation_2026-08-27_summary.json`：P0 总摘要与 `ML_NO_EDGE` 裁决。
- `*_ml_candidates.csv` / `*_rule_candidates.csv`：冻结的 72 个 ML 与 4,320 个规则候选训练内逐折指标。
- `*_validation_predictions.csv` / `*_validation_trades.csv` / `*_validation_path.csv`：一次性验证预测、逐笔与净值路径。
- `*_trade_paths.html`：完整验证 K 线、ML/规则净值与每笔 entry-exit 连线，支持拖动和缩放。
- `*_v7_1_descriptive_reference.json`：exact V7.1 同起止时间的已揭示历史参考，不是 clean OOS。
- `hype_1d_ma7_mlt_p1_cross_event_dynamic_exit_2026-08-27_summary.json`：P1 事件定义、模型 OOF、四条验证策略、V7.1 描述性参考与裁决。
- `*_events.csv`：全部严格穿越事件、趋势标签、固定周期收益与验证入场概率。
- `*_exit_training_rows.csv`：按完整 event 分组的持仓日状态与继续持有标签。
- `*_validation_trades.csv` / `*_validation_path.csv` / `*_validation_decisions.csv`：P1 四策略逐笔、净值路径和逐次概率决策。
- `*_model_manifest.json`：固定特征、逻辑回归系数及 expanding/group OOF 指标。
- `*_trade_paths.html`：P1 自包含交互式验证路径；含 K 线、金黄色 SMA7、斜率、四策略权益、6 个穿越事件和四策略共 18 笔 entry-exit 连线，支持策略开关、拖动、缩放、悬停和逐笔聚焦。
- `*_trade_paths_manifest.json`：HTML 源文件哈希、81 根 K 线/81 个 MA7 点、信号、权益与逐策略交易计数校验。
- `hype_1d_ma7_mlt_p2_episode_policy_2026-08-27_summary.json`：P2 episode、两个模型 group OOF、三策略教学回放、P1/V7.1 参考与裁决。
- `*_episode_candidates.csv`：raw-cross episode 的逐日候选、标签、特征和后段概率。
- `*_survival_training_rows.csv`：按 episode 分组的趋势存活训练状态。
- `*_validation_trades.csv` / `*_validation_path.csv` / `*_validation_decisions.csv`：P2 full/no-reversal/raw-H7 的逐笔、每日权益和完整动作概率。
- `*_model_manifest.json`：P2 entry/survival 固定特征、系数与 expanding group OOF。

## P3 Purged Cross Survival

- `hype_1d_ma7_mlt_p3_purged_cross_survival_2026-08-27_development_manifest.json`：验证前冻结的365日边界、特征块 OOF、selected blocks、内部确认与合同哈希。
- `*_development_entry_blocks.csv` / `*_development_survival_blocks.csv`：train-only 特征块消融。
- `*_internal_confirmation_*.csv`：未参与特征选择的开发期内部确认交易、权益和动作。
- `*_summary.json` / `*_model_manifest.json`：P3 最终训练、一次性81日验证、模型系数与裁决。
- `*_validation_candidates.csv` / `*_validation_trades.csv` / `*_validation_path.csv` / `*_validation_decisions.csv`：精确穿越概率、逐笔、权益与每日 survival 动作。
- `*_post_validation_model_audit.json`：冻结概率对标签完整验证事件的 entry/survival AUC 后审计，不参与选择。
- 每个产物均有 `.sha256` sidecar。

## P4 V7.1 Behavior Clone + Residual

- `hype_1d_ma7_mlt_p4_v7_1_behavior_clone_residual_2026-08-27_development_manifest.json`：验证前冻结的 exact V7.1 source/config hashes、模型、特征、阈值、训练门禁与 selected residual arm。
- `*_teacher_daily_states.csv` / `*_clone_predictions.csv` / `*_clone_oof_predictions.csv`：365日教师状态、完整训练拟合和 expanding OOF 行为克隆证据。
- `*_residual_training_rows.csv` / `*_internal_confirmation.csv` / `*_training_residual_decisions.csv`：train-only trade-filter/exit-extension 标签、最后四笔内部确认与全训练决策。
- `*_development_summary.json`：V7.1 训练期基准、clone fit/OOF、残差内部确认与完整训练回放。
- `*_validation_clone_predictions.csv` / `*_validation_residual_decisions.csv`：冻结模型在81日 reused holdout 的动作预测与残差决策。
- `*_validation_teacher_trades.csv` / `*_validation_overlay_trades.csv` / `*_validation_summary.json`：V7.1 与 P4 的逐笔公平对决及 `V7_1_NOT_BEATEN` 裁决。
- `*_recent_slices.json`：从冻结验证逐笔交易重建的最近 `1d/7d/1m/3m/6m/1y` 收益与 MDD；只补报表，不重训或改动作。
- `*_v7_1_comparison_trade_paths.html`：完整446日（训练365日 + 验证81日）的 HYPE K线、SMA7、exact V7.1 与 P4 两套各20笔交易连线；训练/验证边界清楚分隔，黄色区间突出训练6笔与验证1笔延长退出，支持分段查看、循环聚焦差异、拖动、缩放和悬停。连续权益线只作“训练终值 × 验证相对权益”的视觉拼接，验证账户实际独立从1开始。
- `*_v7_1_comparison_trade_paths_manifest.json`：446根K线、440个有效SMA7点（前6日为7日均线预热）、两套各447个拼接权益点、各20笔交易、7笔变化和 source hashes 校验。
- 每个 P4 产物均有 `.sha256` sidecar。

## P5 Opportunity Repair + Lifecycle

- `hype_1d_ma7_mlt_p5_opportunity_repair_lifecycle_2026-08-28_development_manifest.json`：365日物理截断、标签成熟 purge、三组累加特征块、固定模型/阈值、开发门禁和 source hashes。
- `*_training_feature_labels.csv` / `*_development_oof_predictions.csv`：仅训练期可见的因果特征、hindsight 监督标签和四折扩展窗 OOF 概率。
- `*_internal_confirmation_predictions.csv` / `*_internal_confirmation_decisions.csv` / `*_internal_confirmation_trades.csv`：前285日拟合、最后80日不重训的开发期内部确认。
- `*_training_predictions.csv` / `*_training_decisions.csv` / `*_training_trades.csv` / `*_training_v7_1_trades.csv`：完整365日重拟合概率、状态机动作和 P5/V7.1 公平回放逐笔。
- `*_training_episode_capture.csv` / `*_validation_episode_capture.csv`：P5 与 V7.1 对 hindsight stable-trend episodes 的逐段同向覆盖，只用于归因。
- `*_feature_importance.csv`：冻结 B1 ExtraTrees 因子重要度。
- `*_development_summary.json` / `*_validation_summary.json`：样本内、OOF、内部确认和 reused-holdout 对决；最终裁决 `V7_1_NOT_BEATEN`。
- `*_validation_predictions.csv` / `*_validation_decisions.csv` / `*_validation_trades.csv` / `*_validation_v7_1_trades.csv`：冻结模型在81日的概率、动作和逐笔。
- `*_v7_1_comparison_trade_paths.html`：完整446日（训练365日 + 验证81日）P5/V7.1 对照；含446根K线、MA7、30段 hindsight stable-trend 区间、P5 raw/smoothed 概率、两套连续视觉权益、P5 39笔和V7.1 20笔 entry-exit 连线。可切换策略/MA7/趋势区间，拖动、缩放、悬停，并循环聚焦“P5新识别趋势”和“下一笔P5亏损”。
- `*_v7_1_comparison_trade_paths_manifest.json`：图表源文件哈希、446根K线、440个MA7点、446个概率点、两套各447个权益点、30段趋势、59条交易连线和8段 P5 新识别趋势校验。
- 每个 P5 产物均有 `.sha256` sidecar。

## P6 V7.1 Anchor + Three-Head Lifecycle

- `hype_1d_ma7_mlt_p6_v7_anchor_three_head_lifecycle_2026-08-28_development_manifest.json`：365日物理截断、三头特征/标签/模型/阈值、source hashes、六项开发门禁和 `holdout_permitted=false`。
- `*_entry_rows.csv` / `*_survival_rows.csv` / `*_reversal_rows.csv`：ENTRY_VALUE、SURVIVAL_3D、REVERSAL_VALUE 三个训练表；未来路径只在标签列。
- `*_oof_predictions.csv`：四折 expanding OOF 的逐头概率、标签和 fold；AUC 分别为 `0.581/0.530/0.514`。
- `*_internal_confirmation_scores.csv` / `*_internal_confirmation_decisions.csv` / `*_internal_confirmation_trades.csv`：前285日拟合、最后80日不重训的开发内部确认。
- `*_training_scores.csv` / `*_training_decisions.csv` / `*_training_trades.csv` / `*_training_v7_1_trades.csv`：完整365日重拟合、三笔 core 动态延长、八笔 supplemental entry 与 exact V7.1 公平回放；逐笔 `net_return` 已按同一回放器回填。
- `*_training_episode_capture.csv`：完整训练和内部确认的 P6/V7.1 hindsight stable-trend 逐段覆盖，只用于归因。
- `*_development_summary.json`：样本内、OOF、最后80日内部确认、最近分片与门禁裁决；状态为 `DEVELOPMENT_FAILED_HOLDOUT_LOCKED`。
- `*_v7_1_training_trade_paths.html`：只画前365日。含365根K线、MA7、23段 hindsight stable-trend 区间、三头概率、完整拟合与最后80日内部确认两套权益，以及 P6完整25笔 / V7.1 17笔 / P6内部确认5笔 / V7.1内部确认2笔共49条 entry-exit 连线。竖虚线分隔前285日开发与最后80日内部确认；可切换策略/MA7/趋势区间，拖动、缩放、悬停，并循环聚焦“P6补单”和“内部确认亏损”。后81日未读取，也不在图中。
- `*_v7_1_training_trade_paths_manifest.json`：图表源文件哈希、365根K线、359个MA7点、三头概率点数、四套权益点、23段趋势、5段 P6 新识别趋势和49条交易连线校验；`holdout_read=false`。
- P6 没有任何 `*_validation_*` 文件；开发门禁失败后不得读取后81日。
- 每个 P6 开发产物均有 `.sha256` sidecar。

## P7 Cross-Asset Survival-Only Overlay

- `hype_1d_ma7_mlt_p7_cross_asset_survival_overlay_2026-08-28_development_manifest.json`：供体资产、36 个冻结 survival 特征、日历 OOF、五项开发门禁和 `holdout_permitted=false`。
- `*_donor_survival_rows.csv` / `*_donor_oof_predictions.csv`：BTC/ETH/BNB/SOL 的 `SURVIVAL_3D` 训练表与四折日历 OOF；不含 HYPE。路径 HTML 不画这四个币；供体学到了什么见诊断里「供体到底学到了什么」。
- `*_hype_training_feature_frame.csv` / `*_hype_training_survival_rows.csv`：仅用于 HYPE 覆盖打分，不进入训练集。
- `*_internal_confirmation_scores.csv` / `*_internal_confirmation_decisions.csv` / `*_internal_confirmation_trades.csv`：前285日供体拟合、HYPE 最后80日不重训的内部确认；本轮延长 0 笔，与 V7.1 逐笔重合。
- `*_training_scores.csv` / `*_training_decisions.csv` / `*_training_trades.csv` / `*_training_v7_1_trades.csv`：完整供体拟合后的 HYPE 365 日迁移覆盖；两笔 short RSI 止盈被延长，收益低于 V7.1。只作归因，不是门禁。
- `*_training_episode_capture.csv`：完整训练迁移和内部确认的 P7/V7.1 hindsight stable-trend 逐段覆盖。
- `*_development_summary.json`：供体 OOF、HYPE 内部确认、365 日迁移与门禁裁决；状态为 `DEVELOPMENT_FAILED_HOLDOUT_LOCKED`。
- `*_v7_1_training_trade_paths.html`：训练365日 + 数据湖验证期。默认打开验证窗（2026-05-31→2026-08-27）。连续回放 P7/V7.1 各21笔，官方空仓重开验证窗各3笔，共48条连线。金虚线标出湖内最后一根闭合日K（2026-08-27）。这是可视化，不是 P7 合同 validate。
- `*_v7_1_training_trade_paths_manifest.json`：454根K线、89日验证、连续入场4笔 / 空仓重开3笔、3笔延长、48条连线；`holdout_read=true` 且 `visualization_only=true`。
- `*_lake_validation_summary.json` / `*_lake_continuous_trades.csv` / `*_lake_validation_trades.csv`：湖内验证窗回放证据。P7 合同 `holdout_permitted` 仍为 false。
- P7 没有合同 `--stage validate` 产物；门禁状态仍是 `DEVELOPMENT_FAILED_HOLDOUT_LOCKED`。
- `hype_1d_ma7_mlt_p7_btc_survival_overlay_scout_2026-08-31_summary.json` 与 `*_p7_btc_*_trades.csv`：冻结 P7 覆盖打到 `BTCUSDT` exact V7.1 的 SCOUT 回放，不是新版本。结论见 [BTC SCOUT 诊断](../diagnostics/hype-1d-ma7-mlt-p7-btc-survival-overlay-scout-2026-08-31.md)。
- 每个 P7 开发产物均有 `.sha256` sidecar。

## P8 MA7 Cross First-Hit Event Atlas

- `hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31_development_manifest.json`：P8 冻结合同、脚本、source loader 与 artifacts 哈希；`holdout_read=false`，HYPE 只读前365日。
- `*_events.csv`：五资产每次 raw `SMA7` cross 的因果状态、primary first-hit、MFE/MAE、净收益、14 日去重标记和 episode cluster。
- `*_first_hit_matrix.csv`：每个 raw cross 的 `4×4×4=64` 组 first-hit 结果；primary 为 `+2 ATR before -1 ATR within 14d`，同小时冲突按不利先触发。
- `*_feature_bin_stats.csv` / `*_two_way_state_matrix.csv`：预注册单变量分箱与十个二维矩阵，`n<30` 标记 `INSUFFICIENT_SAMPLE`。
- `*_matched_controls.csv` / `*_cluster_bootstrap.csv`：非穿越同侧、7日动量和随机匹配 controls，以及 asset × episode cluster bootstrap。
- `*_asset_direction_summary.csv` / `*_summary.json`：分资产、分方向、去重敏感性、controls uplift 和最终裁决 `INSUFFICIENT_SAMPLE`。
- `hype_1d_ma7_mlt_p8_ma7_cross_first_hit_event_atlas_2026-08-31.html`：自包含交互式事件图谱，含 MA7、事件标记、每笔 entry 到 first-hit/观察终点连线、拖动、缩放、复位、事件聚焦和筛选；明确标记后81日未读取。
- `*_html_manifest.json`：HTML 哈希、蜡烛/事件/路径连线数量、交互功能和 `holdout_read=false` 校验。
- 每个 P8 artifact 均有 `.sha256` sidecar；P8 没有任何 validation artifact。
