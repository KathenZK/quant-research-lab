# Artifacts

本目录保留 `BIN-1D-MA7-CTP` 的机器可审计事件表与条件概率格子。

- [binance_1d_ma7_ctp_events_2026-08-31.csv](binance_1d_ma7_ctp_events_2026-08-31.csv)：逐笔穿越事件、斜率、放量、7/30/60/90 日路径和前瞻标签。
- [binance_1d_ma7_ctp_rates_2026-08-31.csv](binance_1d_ma7_ctp_rates_2026-08-31.csv)：分样本、分币、分方向、分过滤器的发生率与 Wilson 区间。
- [binance_1d_ma7_ctp_path_rates_2026-08-31.csv](binance_1d_ma7_ctp_path_rates_2026-08-31.csv)：上涨/回撤比、最大回撤、最大上涨和价格位置分桶。
- [binance_1d_ma7_ctp_summary_2026-08-31.json](binance_1d_ma7_ctp_summary_2026-08-31.json)：数据质量、事件计数和裁决摘要。
- [binance_1d_ma7_ctp_all_market_events_2026-08-31.parquet](binance_1d_ma7_ctp_all_market_events_2026-08-31.parquet)：全市场逐笔穿越事件。
- [binance_1d_ma7_ctp_all_market_rates_2026-08-31.csv](binance_1d_ma7_ctp_all_market_rates_2026-08-31.csv)：全市场过滤发生率。
- [binance_1d_ma7_ctp_all_market_path_rates_2026-08-31.csv](binance_1d_ma7_ctp_all_market_path_rates_2026-08-31.csv)：全市场路径分桶。
- [binance_1d_ma7_ctp_all_market_symbol_rates_2026-08-31.csv](binance_1d_ma7_ctp_all_market_symbol_rates_2026-08-31.csv)：分币裸穿越发生率。
- [binance_1d_ma7_ctp_all_market_quality_2026-08-31.json](binance_1d_ma7_ctp_all_market_quality_2026-08-31.json)：入选/剔除与完整日质量。
- [binance_1d_ma7_ctp_all_market_summary_2026-08-31.json](binance_1d_ma7_ctp_all_market_summary_2026-08-31.json)：全市场宇宙与裁决摘要。
- [binance_1d_ma7_ctp_hype_vs_universe_2026-08-31.json](binance_1d_ma7_ctp_hype_vs_universe_2026-08-31.json)：HYPE 相对全市场、同窗口和上市队列的对照摘要。P1 未读取该文件。

## P1 Cross-Conditioned Entry-Value Modeling

- [binance_1d_ma7_ctp_p1_feature_spec.json](binance_1d_ma7_ctp_p1_feature_spec.json)：读标签前冻结的 T1/T0 特征块与 F0–F3 方案。
- [binance_1d_ma7_ctp_p1_contract_lock.json](binance_1d_ma7_ctp_p1_contract_lock.json)：合同与 feature spec SHA256。
- [binance_1d_ma7_ctp_p1_event_panel_summary.json](binance_1d_ma7_ctp_p1_event_panel_summary.json)：101,187 条 MA7 事件审计。
- [binance_1d_ma7_ctp_p1_oof_predictions.parquet](binance_1d_ma7_ctp_p1_oof_predictions.parquet)：D1-D3 OOF；HYPE 0 行。
- [binance_1d_ma7_ctp_p1_historical_test_predictions.parquet](binance_1d_ma7_ctp_p1_historical_test_predictions.parquet)：2025+ 一次性历史测试预测。
- [binance_1d_ma7_ctp_p1_fold_metrics.parquet](binance_1d_ma7_ctp_p1_fold_metrics.parquet)：训练/验证并列指标。
- [binance_1d_ma7_ctp_p1_decile_metrics.parquet](binance_1d_ma7_ctp_p1_decile_metrics.parquet)：概率十分位与成本后净收益。
- [binance_1d_ma7_ctp_p1_feature_importance.parquet](binance_1d_ma7_ctp_p1_feature_importance.parquet)：gain / SHAP / permutation。
- [binance_1d_ma7_ctp_p1_prehistorical_lock.json](binance_1d_ma7_ctp_p1_prehistorical_lock.json)：读取 2025+ 前锁定的模型身份。
- [binance_1d_ma7_ctp_p1_model_card.json](binance_1d_ma7_ctp_p1_model_card.json)：模型卡；not live-ready。
- [binance_1d_ma7_ctp_p1_summary.json](binance_1d_ma7_ctp_p1_summary.json)：裁决与隔离汇总。
- [binance_1d_ma7_ctp_p1_manifest.json](binance_1d_ma7_ctp_p1_manifest.json)：产物 SHA256。

## P2 Pooled-Minimal MA7 Cross Stability Audit

- [binance_1d_ma7_ctp_p2_feature_spec.json](binance_1d_ma7_ctp_p2_feature_spec.json)：读标签前冻结的 F0/F1 极简特征合同。
- [binance_1d_ma7_ctp_p2_contract_lock.json](binance_1d_ma7_ctp_p2_contract_lock.json)：P2 合同、feature spec 与 P1 feature spec SHA256。
- [binance_1d_ma7_ctp_p2_oof_predictions.parquet](binance_1d_ma7_ctp_p2_oof_predictions.parquet)：D1-D3 OOF；只含 `<2025-01-01`，HYPE 0 行。
- [binance_1d_ma7_ctp_p2_fold_metrics.parquet](binance_1d_ma7_ctp_p2_fold_metrics.parquet)：全部候选的训练/验证并列指标及分层诊断。
- [binance_1d_ma7_ctp_p2_decile_metrics.parquet](binance_1d_ma7_ctp_p2_decile_metrics.parquet)：锁定 pooled 模型概率十分位与成本后事件收益。
- [binance_1d_ma7_ctp_p2_model_card.json](binance_1d_ma7_ctp_p2_model_card.json)：单一 pooled 模型卡；无 2025+ 预测，not live-ready。
- [binance_1d_ma7_ctp_p2_summary.json](binance_1d_ma7_ctp_p2_summary.json)：裁决、隔离、稳定性和重训冻结摘要。
- [binance_1d_ma7_ctp_p2_manifest.json](binance_1d_ma7_ctp_p2_manifest.json)：P2 产物 SHA256。

## P3 Independent Context Feature Block Audit

- [binance_1d_ma7_ctp_p3_feature_spec.json](binance_1d_ma7_ctp_p3_feature_spec.json)：读标签前冻结的 B0 与 B1-B4 单块增量特征合同。
- [binance_1d_ma7_ctp_p3_contract_lock.json](binance_1d_ma7_ctp_p3_contract_lock.json)：P3 合同、feature spec 与未读标签事件审计 SHA256。
- [binance_1d_ma7_ctp_p3_summary.json](binance_1d_ma7_ctp_p3_summary.json)：训练前 `DATA_BLOCK_NOT_READY` 裁决与严格样本时点门禁失败摘要。
- [binance_1d_ma7_ctp_p3_manifest.json](binance_1d_ma7_ctp_p3_manifest.json)：P3 失败审计产物 SHA256；因训练前停止，不包含 OOF 或增量比较 parquet。

## P3R Time-Boundary Repair + Independent Context Feature Block Audit

- [binance_1d_ma7_ctp_p3r_feature_spec.json](binance_1d_ma7_ctp_p3r_feature_spec.json)：P3R 冻结特征合同；B0-B4 feature arrays 与原 P3 逐字段一致，仅补时点修复元数据。
- [binance_1d_ma7_ctp_p3r_contract_lock.json](binance_1d_ma7_ctp_p3r_contract_lock.json)：P3R 合同、feature spec、P0R/P2/P3 SHA 与未读标签事件审计。
- [binance_1d_ma7_ctp_p3r_fold_metrics.parquet](binance_1d_ma7_ctp_p3r_fold_metrics.parquet)：B0-B4 D1-D3 训练/验证并列指标及分层指标。
- [binance_1d_ma7_ctp_p3r_oof_predictions.parquet](binance_1d_ma7_ctp_p3r_oof_predictions.parquet)：D1-D3 OOF raw 与前向校准概率；只含 `<2025-01-01` 且 HYPE 0 行。
- [binance_1d_ma7_ctp_p3r_incremental_comparisons.parquet](binance_1d_ma7_ctp_p3r_incremental_comparisons.parquet)：B1-B4 相对 B0 的 paired 增量、CI、p/q 值与裁决。
- [binance_1d_ma7_ctp_p3r_decile_metrics.parquet](binance_1d_ma7_ctp_p3r_decile_metrics.parquet)：B0-B4 概率十分位与成本后事件收益。
- [binance_1d_ma7_ctp_p3r_model_card.json](binance_1d_ma7_ctp_p3r_model_card.json)：P3R pooled Logistic 模型卡；无 2025+ 预测，not live-ready。
- [binance_1d_ma7_ctp_p3r_summary.json](binance_1d_ma7_ctp_p3r_summary.json)：P3R 裁决、样本审计、隔离、校准、增量与重训摘要。
- [binance_1d_ma7_ctp_p3r_manifest.json](binance_1d_ma7_ctp_p3r_manifest.json)：P3R 产物 SHA256 manifest。

## P4 Core Factor Ablation + Compressed Tail-Ranking Audit

- [binance_1d_ma7_ctp_p4_factor_group_spec.json](binance_1d_ma7_ctp_p4_factor_group_spec.json)：读标签前冻结的六组因子划分，69 个 P2 B0 字段完整且不重复。
- [binance_1d_ma7_ctp_p4_contract_lock.json](binance_1d_ma7_ctp_p4_contract_lock.json)：P4 合同、factor spec、P2/P3R feature spec 与脚本 SHA256，状态为 `FROZEN_BEFORE_P4_LABEL_READ`。
- [binance_1d_ma7_ctp_p4_fold_metrics.parquet](binance_1d_ma7_ctp_p4_fold_metrics.parquet)：15 个候选模型的 D1-D3 训练/验证指标、分层指标和 overfit 检查。
- [binance_1d_ma7_ctp_p4_oof_predictions.parquet](binance_1d_ma7_ctp_p4_oof_predictions.parquet)：D1-D3 OOF raw probability、fold-relative percentile/decile 与前向校准概率；只含 `<2025-01-01`，HYPE 0 行。
- [binance_1d_ma7_ctp_p4_ablation_comparisons.parquet](binance_1d_ma7_ctp_p4_ablation_comparisons.parquet)：六个删除式消融和两个压缩模型相对 B0 的 paired bootstrap 差值、CI、p/q 值与裁决。
- [binance_1d_ma7_ctp_p4_only_group_metrics.parquet](binance_1d_ma7_ctp_p4_only_group_metrics.parquet)：六个单组模型的独立预测能力诊断。
- [binance_1d_ma7_ctp_p4_asset_holdout_metrics.parquet](binance_1d_ma7_ctp_p4_asset_holdout_metrics.parquet)：`time walk-forward × leave-asset-group-out` 的 15 单元资产泛化审计。
- [binance_1d_ma7_ctp_p4_decile_metrics.parquet](binance_1d_ma7_ctp_p4_decile_metrics.parquet)：fold-relative 与 legacy pooled-raw 十分位指标。
- [binance_1d_ma7_ctp_p4_coefficient_stability.parquet](binance_1d_ma7_ctp_p4_coefficient_stability.parquet)：标准化 Logistic 系数稳定性与组内相关摘要。
- [binance_1d_ma7_ctp_p4_model_card.json](binance_1d_ma7_ctp_p4_model_card.json)：P4 诊断模型卡；无策略、无 2025+ 预测、not live-ready。
- [binance_1d_ma7_ctp_p4_summary.json](binance_1d_ma7_ctp_p4_summary.json)：P4 数据审计、候选表现、消融、压缩、holdout、隔离和全局裁决摘要。
- [binance_1d_ma7_ctp_p4_manifest.json](binance_1d_ma7_ctp_p4_manifest.json)：P4 输入与输出产物 SHA256 manifest。

## P5 Oscillator + Completed-Weekly-Regime Increment and 2025+ Validation Audit

- [binance_1d_ma7_ctp_p5_feature_spec.json](binance_1d_ma7_ctp_p5_feature_spec.json)：读标签和 2025+ 验证前冻结的六候选字段顺序、RSI6 与完整周线特征块。
- [binance_1d_ma7_ctp_p5_contract_lock.json](binance_1d_ma7_ctp_p5_contract_lock.json)：P5 合同、feature spec、脚本与 P4/P0R 输入 SHA256，状态为 `FROZEN_BEFORE_P5_LABEL_AND_2025_VALIDATION_READ`。
- [binance_1d_ma7_ctp_p5_data_audit.json](binance_1d_ma7_ctp_p5_data_audit.json)：P4 严格样本复现、HYPE/HYPER、TradFi 排除、RSI/周线缺失和周线 causality 审计。
- [binance_1d_ma7_ctp_p5_fold_metrics.parquet](binance_1d_ma7_ctp_p5_fold_metrics.parquet)：六个预注册候选的 D1-D3 训练/验证与前向校准指标。
- [binance_1d_ma7_ctp_p5_pre2025_oof_predictions.parquet](binance_1d_ma7_ctp_p5_pre2025_oof_predictions.parquet)：pre-2025 D1-D3 OOF raw/calibrated predictions；HYPE 0 行。
- [binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet](binance_1d_ma7_ctp_p5_validation_2025_plus_predictions.parquet)：`ITERATIVE_REUSED_VALIDATION_2025_PLUS` 一次性预测、frozen-threshold selection、seen/new 与 TradFi 标记；HYPE 0 行。
- [binance_1d_ma7_ctp_p5_paired_comparisons.parquet](binance_1d_ma7_ctp_p5_paired_comparisons.parquet)：挑战者相对 `R_B0_69` 的 2,000 次共享 28 日块整集重采样 diff、CI、p/q 值；每次重新计算非线性指标。
- [binance_1d_ma7_ctp_p5_strata.parquet](binance_1d_ma7_ctp_p5_strata.parquet)：开发期、2025+、分年、方向、seen/new、non-overlap、月度与 28 日块分层指标。
- [binance_1d_ma7_ctp_p5_calibration.json](binance_1d_ma7_ctp_p5_calibration.json)：仅由折起点前已完成标签的 pre-2025 OOF 拟合的 Platt 校准、参数和同概率空间 frozen threshold。
- [binance_1d_ma7_ctp_p5_model_card.json](binance_1d_ma7_ctp_p5_model_card.json)：P5 诊断模型卡；无策略、无权益、无 live/handoff。
- [binance_1d_ma7_ctp_p5_summary.json](binance_1d_ma7_ctp_p5_summary.json)：P5 样本、候选、2025+ 复用验证、HYPE 隔离与全局裁决摘要。
- [binance_1d_ma7_ctp_p5_manifest.json](binance_1d_ma7_ctp_p5_manifest.json)：P5 输入与输出产物 SHA256 manifest。
- [P5 独立验收与修复审计](../diagnostics/binance-1d-ma7-ctp-p5-independent-acceptance-audit-2026-09-02.md)：区分 Cursor 原始输出与修复后有效输出，记录独立复算、缺陷、修复和最终裁决。

## P6 Market-Regime x Side Conditional Ranking Value Audit

- [binance_1d_ma7_ctp_p6_config.json](binance_1d_ma7_ctp_p6_config.json)：P6 机器可读合同、六格市场状态、候选模型、四类选择口径和 bootstrap 参数。
- [binance_1d_ma7_ctp_p6_contract_lock.json](binance_1d_ma7_ctp_p6_contract_lock.json)：P6 合同、配置、脚本和 P5 manifest 的锁定 SHA256。
- [binance_1d_ma7_ctp_p6_exposure_ledger.json](binance_1d_ma7_ctp_p6_exposure_ledger.json)：2025+ 复用验证、新 OOS 缺口和 future OOS 前置条件记录。
- [binance_1d_ma7_ctp_p6_data_audit.json](binance_1d_ma7_ctp_p6_data_audit.json)：P0R/P5 输入、HYPE 隔离、市场状态还原和 P5 关键科学产物 hash 审计。
- [binance_1d_ma7_ctp_p6_b0_reproduction_audit.json](binance_1d_ma7_ctp_p6_b0_reproduction_audit.json)：`R_B0_69` 字段数、P5 OOF/validation prediction SHA256 与复用边界。
- [binance_1d_ma7_ctp_p6_fold_stage_metrics.parquet](binance_1d_ma7_ctp_p6_fold_stage_metrics.parquet)：外层 D1-D3、内层 B0 OOF 和 M1 warm-up/训练样本表。
- [binance_1d_ma7_ctp_p6_predictions.parquet](binance_1d_ma7_ctp_p6_predictions.parquet)：逐事件 B0、M0、M1 raw score、六格、market state 与数据角色。
- [binance_1d_ma7_ctp_p6_market_state_metrics.parquet](binance_1d_ma7_ctp_p6_market_state_metrics.parquet)：训练、OOF、2025、2026、方向、六格和 selection 分层指标。
- [binance_1d_ma7_ctp_p6_selection_metrics.parquet](binance_1d_ma7_ctp_p6_selection_metrics.parquet)：年度全局、格内排序、同日同方向 Top5 与 frozen threshold 口径。
- [binance_1d_ma7_ctp_p6_paired_bootstrap_stats.parquet](binance_1d_ma7_ctp_p6_paired_bootstrap_stats.parquet)：2,000 次共享 28 日块 paired bootstrap 主检验。
- [binance_1d_ma7_ctp_p6_concentration_diagnostics.json](binance_1d_ma7_ctp_p6_concentration_diagnostics.json)：同日 Top5 的资产、月份、BTC/ETH 剔除和最大贡献剔除诊断。
- [binance_1d_ma7_ctp_p6_summary.json](binance_1d_ma7_ctp_p6_summary.json)：P6 裁决、核心数字、HYPE 隔离、non-overlap 和 P5 manifest drift 摘要。
- [binance_1d_ma7_ctp_p6_manifest.json](binance_1d_ma7_ctp_p6_manifest.json)：P6 输入与输出 SHA256 manifest，排除 manifest 自身。

## P7 Temporal Drift, Score Monotonicity and Calibration Decomposition

- [binance_1d_ma7_ctp_p7_config.json](binance_1d_ma7_ctp_p7_config.json)：P7 机器可读合同、样本角色、固定 raw 阈值、固定分箱、统计族、bootstrap 和 verdict 候选。
- [binance_1d_ma7_ctp_p7_contract_lock.json](binance_1d_ma7_ctp_p7_contract_lock.json)：状态 `FROZEN_BEFORE_P7_DECOMPOSITION_OUTPUT_READ` 的合同、config 和 input inventory 锁。
- [binance_1d_ma7_ctp_p7_input_inventory.json](binance_1d_ma7_ctp_p7_input_inventory.json)：P7 读取的 P4/P5/P6/P0R 输入文件、哈希和 P6 modeling audit 缺口记录。
- [binance_1d_ma7_ctp_p7_data_audit.json](binance_1d_ma7_ctp_p7_data_audit.json)：样本角色、HYPE/HYPER、TradFi 排除、pre-2025 年龄/流动性边界和 fail-closed 原因。
- [binance_1d_ma7_ctp_p7_anchor_parity.json](binance_1d_ma7_ctp_p7_anchor_parity.json)：2025+、2025、2026、阈值、HYPE/HYPER、TradFi 与 B0 重建锚点。
- [binance_1d_ma7_ctp_p7_model_reconstruction.json](binance_1d_ma7_ctp_p7_model_reconstruction.json)：`R_B0_69` 确定性重建审计；最大 raw probability 误差 `0.009287`，未过 `1e-8`。
- [binance_1d_ma7_ctp_p7_frozen_coefficients.json](binance_1d_ma7_ctp_p7_frozen_coefficients.json)：按当前 P5 脚本重建出的系数、预处理参数与失败误差；不作为可解释 B0 机制证据。
- [binance_1d_ma7_ctp_p7_score_distribution_drift.parquet](binance_1d_ma7_ctp_p7_score_distribution_drift.parquet) / [csv](binance_1d_ma7_ctp_p7_score_distribution_drift.csv)：因 B0 重建失败，仅保存 fail-closed 审计占位，不含漂移结论。
- [binance_1d_ma7_ctp_p7_feature_drift.parquet](binance_1d_ma7_ctp_p7_feature_drift.parquet) / [binance_1d_ma7_ctp_p7_feature_group_drift.csv](binance_1d_ma7_ctp_p7_feature_group_drift.csv)：因 B0 重建失败，仅保存 fail-closed 审计占位。
- [binance_1d_ma7_ctp_p7_fixed_score_bin_outcomes.parquet](binance_1d_ma7_ctp_p7_fixed_score_bin_outcomes.parquet)、[binance_1d_ma7_ctp_p7_score_monotonicity.json](binance_1d_ma7_ctp_p7_score_monotonicity.json)、[binance_1d_ma7_ctp_p7_calibration_metrics.json](binance_1d_ma7_ctp_p7_calibration_metrics.json)、[binance_1d_ma7_ctp_p7_calibration_bins.parquet](binance_1d_ma7_ctp_p7_calibration_bins.parquet)、[binance_1d_ma7_ctp_p7_year_interactions.json](binance_1d_ma7_ctp_p7_year_interactions.json)：排序/校准分析因重建门禁失败停止，保留失败审计占位。
- [binance_1d_ma7_ctp_p7_composition_decomposition.json](binance_1d_ma7_ctp_p7_composition_decomposition.json)、[binance_1d_ma7_ctp_p7_composition_cells.parquet](binance_1d_ma7_ctp_p7_composition_cells.parquet)、[binance_1d_ma7_ctp_p7_feature_contribution_drift.parquet](binance_1d_ma7_ctp_p7_feature_contribution_drift.parquet)、[binance_1d_ma7_ctp_p7_feature_group_contribution.csv](binance_1d_ma7_ctp_p7_feature_group_contribution.csv)、[binance_1d_ma7_ctp_p7_label_economic_decomposition.json](binance_1d_ma7_ctp_p7_label_economic_decomposition.json)：结构、贡献和经济分解因重建门禁失败停止，保留失败审计占位。
- [binance_1d_ma7_ctp_p7_concentration_metrics.json](binance_1d_ma7_ctp_p7_concentration_metrics.json)、[binance_1d_ma7_ctp_p7_leave_one_out.parquet](binance_1d_ma7_ctp_p7_leave_one_out.parquet)、[binance_1d_ma7_ctp_p7_nonoverlap_episode_checks.json](binance_1d_ma7_ctp_p7_nonoverlap_episode_checks.json)、[binance_1d_ma7_ctp_p7_bootstrap_results.parquet](binance_1d_ma7_ctp_p7_bootstrap_results.parquet)：集中度、稳健性和 bootstrap 因重建门禁失败停止，保留失败审计占位。
- [binance_1d_ma7_ctp_p7_summary.json](binance_1d_ma7_ctp_p7_summary.json)：P7 全局裁决 `DATA_OR_REPRODUCTION_FAILURE`、核心锚点和 P8 E 路由。
- [binance_1d_ma7_ctp_p7_manifest.json](binance_1d_ma7_ctp_p7_manifest.json)：P7 正式产物 SHA256 manifest，排除 manifest 自身。
- [binance_1d_ma7_ctp_p7_chart_01_raw_score_distribution.svg](binance_1d_ma7_ctp_p7_chart_01_raw_score_distribution.svg) 至 [binance_1d_ma7_ctp_p7_chart_10_concentration_summary.svg](binance_1d_ma7_ctp_p7_chart_10_concentration_summary.svg)：失败审计静态 SVG，占位说明门禁失败，不呈现漂移结论。
