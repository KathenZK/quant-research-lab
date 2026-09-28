# Artifacts

本目录保留 `HYPE-1D-MA7-Asymmetric-Body-Trend` 各登记版本、观察分支、原始趋势状态机与意图优化研究的持久化机器证据。

## 原始 MA7 趋势状态机（2026-08-09）

- [机器摘要](hype_1d_ma7_original_trend_2026-08-09_summary.json)、[A–D 指标](hype_1d_ma7_original_trend_2026-08-09_metrics.csv)、[执行压力](hype_1d_ma7_original_trend_2026-08-09_stress.csv)与[E 保护](hype_1d_ma7_original_trend_2026-08-09_protection.csv)。
- [90 日 rolling](hype_1d_ma7_original_trend_2026-08-09_rolling_90d.csv)、[CPCV](hype_1d_ma7_original_trend_2026-08-09_cpcv.csv)、[MC3](hype_1d_ma7_original_trend_2026-08-09_mc3.csv)、[核心 OAT](hype_1d_ma7_original_trend_2026-08-09_core_sensitivity.csv)、[RSI 邻域](hype_1d_ma7_original_trend_2026-08-09_rsi_sensitivity.csv)与[24 相位](hype_1d_ma7_original_trend_2026-08-09_phase24.csv)。
- [近期切片](hype_1d_ma7_original_trend_2026-08-09_recent.csv)、[逐笔交易](hype_1d_ma7_original_trend_2026-08-09_trades.csv)、[完整路径](hype_1d_ma7_original_trend_2026-08-09_path.csv)与[动作账本](hype_1d_ma7_original_trend_2026-08-09_actions.csv)。
- [自包含交互式 HTML](hype_1d_ma7_original_trend_trade_path_2026-08-09.html)：四臂切换、432 根日 K、MA7/`±0.75ATR7`、RSI6、权益、212 笔逐笔入出场连线和交易表。

## 原始意图优化 Development（2026-08-09）

- [冻结 manifest](hype_1d_ma7_intent_optimization_2026-08-09_manifest.json)及其[SHA256](hype_1d_ma7_intent_optimization_2026-08-09_manifest.sha256)：数据质量、D/V/H 边界、83 项自检和 10 个实现 pin。
- [174-row Development trials](hype_1d_ma7_intent_optimization_2026-08-09_development_trials.json)及其[SHA256](hype_1d_ma7_intent_optimization_2026-08-09_development_trials.sha256)：A=108、B=30、C=27、D=9，全部 `OK`，无数值错误或跳过。
- [Development 机器裁决](hype_1d_ma7_intent_optimization_2026-08-09_development.json)及其[SHA256](hype_1d_ma7_intent_optimization_2026-08-09_development.sha256)：第一名 `C001` 未通过双重支配与压力门，无 fallback champion，V/H 未揭示，未创建 validation、holdout 或 final 产物。
- [D-only 失败首位交互式 HTML](hype_1d_ma7_intent_optimization_2026-08-09_failed_first_c001_development_trade_path.html)及其[SHA256](hype_1d_ma7_intent_optimization_2026-08-09_failed_first_c001_development_trade_path.sha256)：C001/V4 切换、MA7/ATR/RSI/state/equity、20/10 笔逐笔连线；仅为 `development_failed_first_only` 诊断，不是 champion 或 OOS 报告。

## 多空分离搜索

- [机器摘要](hype_1d_ma7_separated_summary_2026-08-04.json)：搜索合同、候选、基准、压力、切片、相位、邻域、消融与 bootstrap。
- [完整交易路径交互图](hype_1d_ma7_separated_trade_path_2026-08-04.html)：日 K、MA7、逐笔入场/出场连线、权益曲线与交易表。
- [单边候选前沿](hype_1d_ma7_separated_frontier_2026-08-04.csv)与[组合候选前沿](hype_1d_ma7_separated_pairs_2026-08-04.csv)。
- [主候选交易](hype_1d_ma7_separated_primary_trades_2026-08-04.csv)与[完整权益路径](hype_1d_ma7_separated_primary_path_2026-08-04.csv)。
- [近期切片](hype_1d_ma7_separated_primary_recent_2026-08-04.csv)与[90 日滚动窗口](hype_1d_ma7_separated_primary_rolling_90d_2026-08-04.csv)。
- [多空消融](hype_1d_ma7_separated_primary_components_2026-08-04.csv)。
- [参数邻域](hype_1d_ma7_separated_primary_neighborhood_2026-08-04.csv)。
- [日界相位](hype_1d_ma7_separated_primary_phase_2026-08-04.csv)。

## V1 EMA7 替换

- [机器摘要](hype_1d_v1_ema7_substitution_summary_2026-08-05.json)与[指标表](hype_1d_v1_ema7_substitution_metrics_2026-08-05.csv)。
- [近期切片](hype_1d_v1_ema7_substitution_recent_2026-08-05.csv)、[日界相位](hype_1d_v1_ema7_substitution_phase_2026-08-05.csv)与[90 日滚动窗口](hype_1d_v1_ema7_substitution_rolling_90d_2026-08-05.csv)。
- [EMA7 交易](hype_1d_v1_ema7_substitution_trades_2026-08-05.csv)与[EMA7 组合路径](hype_1d_v1_ema7_substitution_path_2026-08-05.csv)。

## V1 3x 杠杆

- [机器摘要](hype_1d_v1_3x_leverage_summary_2026-08-05.json)与[指标表](hype_1d_v1_3x_leverage_metrics_2026-08-05.csv)。
- [近期切片](hype_1d_v1_3x_leverage_recent_2026-08-05.csv)、[日界相位](hype_1d_v1_3x_leverage_phase_2026-08-05.csv)与[90 日滚动窗口](hype_1d_v1_3x_leverage_rolling_90d_2026-08-05.csv)。
- [3x 交易](hype_1d_v1_3x_leverage_trades_2026-08-05.csv)与[3x 组合路径](hype_1d_v1_3x_leverage_path_2026-08-05.csv)。

## V1 前瞻观察与审计（2026-08-06 起）

- [数据同步证据](hype_1h_prospective_sync_2026-08-06.json)：fapi 补充 `1h` K 线与 funding 的零 blocker 审计。
- [观察 #1 机器摘要](hype_1d_v1_prospective_obs_2026-08-06_summary.json)、[窗内路径](hype_1d_v1_prospective_obs_2026-08-06_path.csv)与[窗内成交](hype_1d_v1_prospective_obs_2026-08-06_trades.csv)。
- [首日/相位/起跑点审计摘要](hype_1d_v1_protection_phase_audit_2026-08-06_summary.json)、[首日明细](hype_1d_v1_protection_phase_audit_2026-08-06_first_day.csv)、[相位网格](hype_1d_v1_protection_phase_audit_2026-08-06_phases.csv)与[起跑点网格](hype_1d_v1_protection_phase_audit_2026-08-06_starts.csv)。

## V1 trailing stop 后反手空诊断

- [机器摘要](hype_1d_v1_trailing_stop_short_reversal_2026-08-06_summary.json)与[指标/压力表](hype_1d_v1_trailing_stop_short_reversal_2026-08-06_metrics.csv)。
- [逐笔交易](hype_1d_v1_trailing_stop_short_reversal_2026-08-06_trades.csv)、[近期切片](hype_1d_v1_trailing_stop_short_reversal_2026-08-06_recent.csv)与[相位检查](hype_1d_v1_trailing_stop_short_reversal_2026-08-06_phase.csv)。
- [V2 1x 完整交易路径 HTML](hype_1d_ma7_abt_v2_trade_path_2026-08-06.html)：425 根日 K、MA7、权益曲线与 19 笔逐笔入场—出场连线；`R-S` 标记 7 笔 trailing-stop 反手空。

## V2 3x 杠杆观察

- [机器摘要](hype_1d_v2_3x_leverage_2026-08-06_summary.json)与[指标/压力表](hype_1d_v2_3x_leverage_2026-08-06_metrics.csv)。
- [近期切片](hype_1d_v2_3x_leverage_2026-08-06_recent.csv)、[日界相位](hype_1d_v2_3x_leverage_2026-08-06_phase.csv)与[90 日滚动窗口](hype_1d_v2_3x_leverage_2026-08-06_rolling_90d.csv)。
- [3x 交易](hype_1d_v2_3x_leverage_2026-08-06_trades.csv)与[3x 路径](hype_1d_v2_3x_leverage_2026-08-06_path.csv)。

## V2 全参数与斜率专项消融

- [机器摘要](hype_1d_v2_full_parameter_ablation_2026-08-06_summary.json)、[27 组 OAT](hype_1d_v2_full_parameter_ablation_2026-08-06_oat.csv)与[32 组斜率网格](hype_1d_v2_full_parameter_ablation_2026-08-06_slope_grid.csv)。
- [24 相位](hype_1d_v2_full_parameter_ablation_2026-08-06_phase24.csv)、[近期切片](hype_1d_v2_full_parameter_ablation_2026-08-06_recent.csv)、[90 日滚动](hype_1d_v2_full_parameter_ablation_2026-08-06_rolling_90d.csv)与[最新延伸](hype_1d_v2_full_parameter_ablation_2026-08-06_latest.csv)。

## 二元/三状态 MA7 迟滞诊断

- [机器摘要](hype_1d_ma7_three_state_hysteresis_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_ma7_three_state_hysteresis_2026-08-07_metrics.csv)、[近期切片](hype_1d_ma7_three_state_hysteresis_2026-08-07_recent.csv)、[90 日滚动](hype_1d_ma7_three_state_hysteresis_2026-08-07_rolling_90d.csv)、[24 相位](hype_1d_ma7_three_state_hysteresis_2026-08-07_phase24.csv)与[最新延伸](hype_1d_ma7_three_state_hysteresis_2026-08-07_latest.csv)。
- [二元交易](hype_1d_ma7_three_state_hysteresis_2026-08-07_binary_d075_trades.csv)、[三状态交易](hype_1d_ma7_three_state_hysteresis_2026-08-07_tri_d075_n025_k3_trades.csv)、[三状态路径](hype_1d_ma7_three_state_hysteresis_2026-08-07_tri_d075_n025_k3_path.csv)与[交互式 HTML](hype_1d_ma7_three_state_hysteresis_trade_path_2026-08-07.html)。

## 状态边界 × V2斜率混合诊断

- [机器摘要](hype_1d_ma7_state_slope_hybrid_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_ma7_state_slope_hybrid_2026-08-07_metrics.csv)、[近期切片](hype_1d_ma7_state_slope_hybrid_2026-08-07_recent.csv)、[90日滚动](hype_1d_ma7_state_slope_hybrid_2026-08-07_rolling_90d.csv)、[24相位](hype_1d_ma7_state_slope_hybrid_2026-08-07_phase24.csv)、[最新延伸](hype_1d_ma7_state_slope_hybrid_2026-08-07_latest.csv)与[入场质量](hype_1d_ma7_state_slope_hybrid_2026-08-07_entry_quality.csv)。
- [CORE交易](hype_1d_ma7_state_slope_hybrid_2026-08-07_hybrid_core_trades.csv)与[路径](hype_1d_ma7_state_slope_hybrid_2026-08-07_hybrid_core_path.csv)；[风险层交易](hype_1d_ma7_state_slope_hybrid_2026-08-07_hybrid_v2_risk_trades.csv)与[路径](hype_1d_ma7_state_slope_hybrid_2026-08-07_hybrid_v2_risk_path.csv)；[CORE交互式HTML](hype_1d_ma7_state_slope_hybrid_core_trade_path_2026-08-07.html)。

## V2空头迟滞0.75诊断

- [机器摘要](hype_1d_v2_short_hysteresis_075_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_v2_short_hysteresis_075_2026-08-07_metrics.csv)、[近期切片](hype_1d_v2_short_hysteresis_075_2026-08-07_recent.csv)、[90日滚动](hype_1d_v2_short_hysteresis_075_2026-08-07_rolling_90d.csv)、[24相位](hype_1d_v2_short_hysteresis_075_2026-08-07_phase24.csv)与[最新延伸](hype_1d_v2_short_hysteresis_075_2026-08-07_latest.csv)。
- [V2交易](hype_1d_v2_short_hysteresis_075_2026-08-07_v2_control_trades.csv)、[`0.75`交易](hype_1d_v2_short_hysteresis_075_2026-08-07_short_exit_075_trades.csv)、[关闭hard stop归因交易](hype_1d_v2_short_hysteresis_075_2026-08-07_short_exit_075_no_hard_trades.csv)与[关闭trailing归因交易](hype_1d_v2_short_hysteresis_075_2026-08-07_short_exit_075_no_trail_trades.csv)。

## V3全参数消融

- [机器摘要](hype_1d_v3_full_parameter_ablation_2026-08-07_summary.json)、[28组OAT](hype_1d_v3_full_parameter_ablation_2026-08-07_oat.csv)与[32组斜率网格](hype_1d_v3_full_parameter_ablation_2026-08-07_slope_grid.csv)。
- [24相位](hype_1d_v3_full_parameter_ablation_2026-08-07_phase24.csv)、[近期切片](hype_1d_v3_full_parameter_ablation_2026-08-07_recent.csv)、[90日滚动](hype_1d_v3_full_parameter_ablation_2026-08-07_rolling_90d.csv)与[最新延伸](hype_1d_v3_full_parameter_ablation_2026-08-07_latest.csv)。
- [V3 1x完整交易路径HTML](hype_1d_ma7_abt_v3_trade_path_2026-08-07.html)：425根UTC日K、MA7、权益曲线与19笔入场—出场连线，其中7笔标记为trailing-stop强制反手空；金色★`L15`标出long slope从`0.02`提高至`0.04`时会过滤的亏损交易。

## V3 3x杠杆观察

- [机器摘要](hype_1d_v3_3x_leverage_2026-08-07_summary.json)与[指标/压力表](hype_1d_v3_3x_leverage_2026-08-07_metrics.csv)。
- [近期切片](hype_1d_v3_3x_leverage_2026-08-07_recent.csv)、[日界相位](hype_1d_v3_3x_leverage_2026-08-07_phase.csv)与[90日滚动窗口](hype_1d_v3_3x_leverage_2026-08-07_rolling_90d.csv)。
- [3x交易](hype_1d_v3_3x_leverage_2026-08-07_trades.csv)与[3x路径](hype_1d_v3_3x_leverage_2026-08-07_path.csv)。

## V3日线跌破MA7次日反手诊断

- [机器摘要](hype_1d_v3_daily_ma7_cross_reversal_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_v3_daily_ma7_cross_reversal_2026-08-07_metrics.csv)、[近期切片](hype_1d_v3_daily_ma7_cross_reversal_2026-08-07_recent.csv)、[90日滚动](hype_1d_v3_daily_ma7_cross_reversal_2026-08-07_rolling_90d.csv)、[24相位](hype_1d_v3_daily_ma7_cross_reversal_2026-08-07_phase24.csv)与[最新延伸](hype_1d_v3_daily_ma7_cross_reversal_2026-08-07_latest.csv)。
- [V3控制交易](hype_1d_v3_daily_ma7_cross_reversal_2026-08-07_v3_control_trades.csv)、[trailing只平仓交易](hype_1d_v3_daily_ma7_cross_reversal_2026-08-07_trail_flat_control_trades.csv)、[日线cross反手交易](hype_1d_v3_daily_ma7_cross_reversal_2026-08-07_daily_cross_reversal_trades.csv)与[完整交易路径HTML](hype_1d_ma7_abt_v3_daily_ma7_cross_reversal_trade_path_2026-08-07.html)：425根UTC日K、MA7、权益曲线和22笔入场—出场连线，`R-S`标记6笔日线cross反手。

## V3强制反手入场审计

- [逐笔审计](hype_1d_v3_forced_reversal_entry_audit_2026-08-07.csv)与[机器摘要](hype_1d_v3_forced_reversal_entry_audit_2026-08-07_summary.json)：复核登记V3的7笔trailing反手，确认R-S02与R-S12在当时可知MA7上方开空，且5笔只持有1日。

## V3强制反手确认修正

- [机器摘要](hype_1d_v3_reversal_confirmation_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_v3_reversal_confirmation_2026-08-07_metrics.csv)、[近期切片](hype_1d_v3_reversal_confirmation_2026-08-07_recent.csv)、[90日滚动](hype_1d_v3_reversal_confirmation_2026-08-07_rolling_90d.csv)、[24相位](hype_1d_v3_reversal_confirmation_2026-08-07_phase24.csv)与[最新延伸](hype_1d_v3_reversal_confirmation_2026-08-07_latest.csv)。
- [`MA_ONLY`交易](hype_1d_v3_reversal_confirmation_2026-08-07_ma_only_trades.csv)、[路径](hype_1d_v3_reversal_confirmation_2026-08-07_ma_only_path.csv)与[完整交易路径HTML](hype_1d_ma7_abt_v3_ma_only_reversal_trade_path_2026-08-07.html)：只在拟反手`1h` open低于上一完整日MA7时开空，共17笔交易、5笔反手、2次拒绝。
- [登记V4完整交易路径HTML](hype_1d_ma7_abt_v4_trade_path_2026-08-07.html)：与`MA_ONLY`逐笔等价，标题与身份更新为V4；425根UTC日K、MA7、权益曲线和17笔交易均有入场—出场连线。

## V4自然short入场时序

- [机器摘要](hype_1d_v4_short_entry_timing_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_v4_short_entry_timing_2026-08-07_metrics.csv)、[近期切片](hype_1d_v4_short_entry_timing_2026-08-07_recent.csv)、[90日滚动](hype_1d_v4_short_entry_timing_2026-08-07_rolling_90d.csv)、[24相位](hype_1d_v4_short_entry_timing_2026-08-07_phase24.csv)与[最新延伸](hype_1d_v4_short_entry_timing_2026-08-07_latest.csv)。
- [`V4_CONTROL`交易](hype_1d_v4_short_entry_timing_2026-08-07_v4_control_trades.csv) · [`1d`入场slope交易](hype_1d_v4_short_entry_timing_2026-08-07_short_entry_slope_1d_trades.csv) · [持续穿越交易](hype_1d_v4_short_entry_timing_2026-08-07_persistent_cross_2d_trades.csv)；对应逐日path使用同名前缀的`_path.csv`。

## V4多空持续regime入场

- [机器摘要](hype_1d_v4_flat_regime_entry_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_v4_flat_regime_entry_2026-08-07_metrics.csv)、[近期切片](hype_1d_v4_flat_regime_entry_2026-08-07_recent.csv)、[90日滚动](hype_1d_v4_flat_regime_entry_2026-08-07_rolling_90d.csv)、[24相位](hype_1d_v4_flat_regime_entry_2026-08-07_phase24.csv)与[最新延伸](hype_1d_v4_flat_regime_entry_2026-08-07_latest.csv)。
- [`V4_CONTROL`交易](hype_1d_v4_flat_regime_entry_2026-08-07_v4_control_trades.csv) · [flat regime交易](hype_1d_v4_flat_regime_entry_2026-08-07_flat_regime_entry_trades.csv)；对应逐日path使用同名前缀的`_path.csv`。

## V4目标侧regime直接反手

- [机器摘要](hype_1d_v4_target_side_regime_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_v4_target_side_regime_2026-08-07_metrics.csv)、[近期切片](hype_1d_v4_target_side_regime_2026-08-07_recent.csv)、[90日滚动](hype_1d_v4_target_side_regime_2026-08-07_rolling_90d.csv)、[24相位](hype_1d_v4_target_side_regime_2026-08-07_phase24.csv)与[最新延伸](hype_1d_v4_target_side_regime_2026-08-07_latest.csv)。
- [`V4_CONTROL`交易](hype_1d_v4_target_side_regime_2026-08-07_v4_control_trades.csv) · [target-side交易](hype_1d_v4_target_side_regime_2026-08-07_target_side_regime_trades.csv)；后者含17次下一日open直接反手，对应逐日path使用同名前缀的`_path.csv`。

## V4 cooldown消融

- [机器摘要](hype_1d_v4_cooldown_ablation_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_v4_cooldown_ablation_2026-08-07_metrics.csv)、[近期切片](hype_1d_v4_cooldown_ablation_2026-08-07_recent.csv)、[90日滚动](hype_1d_v4_cooldown_ablation_2026-08-07_rolling_90d.csv)、[24相位](hype_1d_v4_cooldown_ablation_2026-08-07_phase24.csv)与[最新延伸](hype_1d_v4_cooldown_ablation_2026-08-07_latest.csv)。
- [`V4_CONTROL`交易](hype_1d_v4_cooldown_ablation_2026-08-07_v4_control_trades.csv) · [去long cooldown交易](hype_1d_v4_cooldown_ablation_2026-08-07_no_long_cooldown_trades.csv) · [去short cooldown交易](hype_1d_v4_cooldown_ablation_2026-08-07_no_short_cooldown_trades.csv) · [两侧都去交易](hype_1d_v4_cooldown_ablation_2026-08-07_no_both_cooldown_trades.csv)；对应逐日path使用同名前缀的`_path.csv`。

## V4 ATR容错趋势状态机

- [机器摘要](hype_1d_v4_band_state_machine_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_v4_band_state_machine_2026-08-07_metrics.csv)、[近期切片](hype_1d_v4_band_state_machine_2026-08-07_recent.csv)、[90日滚动](hype_1d_v4_band_state_machine_2026-08-07_rolling_90d.csv)、[24相位](hype_1d_v4_band_state_machine_2026-08-07_phase24.csv)与[最新延伸](hype_1d_v4_band_state_machine_2026-08-07_latest.csv)。
- [`V4_CONTROL`交易](hype_1d_v4_band_state_machine_2026-08-07_v4_control_trades.csv)与[路径](hype_1d_v4_band_state_machine_2026-08-07_v4_control_path.csv)；[ATR-band交易](hype_1d_v4_band_state_machine_2026-08-07_band_state_machine_trades.csv)与[路径](hype_1d_v4_band_state_machine_2026-08-07_band_state_machine_path.csv)。
- [完整交易路径HTML](hype_1d_ma7_abt_v4_band_state_machine_trade_path_2026-08-07.html)：425根UTC日K、MA7、上下`0.75×ATR7`边界、持仓/cooldown状态、权益曲线及28笔入场—出场连线。

## V4有限reclaim pending第一轮

- [机器摘要](hype_1d_v4_finite_reclaim_pending_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_v4_finite_reclaim_pending_2026-08-07_metrics.csv)、[近期切片](hype_1d_v4_finite_reclaim_pending_2026-08-07_recent.csv)、[90日滚动](hype_1d_v4_finite_reclaim_pending_2026-08-07_rolling_90d.csv)、[24相位](hype_1d_v4_finite_reclaim_pending_2026-08-07_phase24.csv)与[最新延伸](hype_1d_v4_finite_reclaim_pending_2026-08-07_latest.csv)。
- [`V4_CONTROL`交易](hype_1d_v4_finite_reclaim_pending_2026-08-07_v4_control_trades.csv)、[short等待1日](hype_1d_v4_finite_reclaim_pending_2026-08-07_short_pending_1d_trades.csv)、[short等待2日](hype_1d_v4_finite_reclaim_pending_2026-08-07_short_pending_2d_trades.csv)、[long等待1日](hype_1d_v4_finite_reclaim_pending_2026-08-07_long_pending_1d_trades.csv)、[long等待2日](hype_1d_v4_finite_reclaim_pending_2026-08-07_long_pending_2d_trades.csv)与四组多空组合；对应逐日path使用同名前缀的`_path.csv`。

## V4 pending质量与handoff第二轮

- [机器摘要](hype_1d_v4_pending_quality_handoff_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_v4_pending_quality_handoff_2026-08-07_metrics.csv)、[近期切片](hype_1d_v4_pending_quality_handoff_2026-08-07_recent.csv)、[90日滚动](hype_1d_v4_pending_quality_handoff_2026-08-07_rolling_90d.csv)、[24相位](hype_1d_v4_pending_quality_handoff_2026-08-07_phase24.csv)与[最新延伸](hype_1d_v4_pending_quality_handoff_2026-08-07_latest.csv)。
- [`V4_CONTROL`交易](hype_1d_v4_pending_quality_handoff_2026-08-07_v4_control_trades.csv)、[short等待1日控制](hype_1d_v4_pending_quality_handoff_2026-08-07_sp1_control_trades.csv)、[anti-chase](hype_1d_v4_pending_quality_handoff_2026-08-07_sp1_cap_075_trades.csv)、[handoff](hype_1d_v4_pending_quality_handoff_2026-08-07_sp1_handoff_trades.csv)与[组合候选](hype_1d_v4_pending_quality_handoff_2026-08-07_sp1_cap_075_handoff_trades.csv)；对应逐日path使用同名前缀的`_path.csv`。
- [最佳局部候选完整交易路径HTML](hype_1d_ma7_abt_v4_pending_quality_handoff_trade_path_2026-08-07.html)：425根UTC日K、MA7、short pending `0.25–0.75×ATR7`区、pending接受/拒绝/handoff事件、权益曲线与20笔入场—出场连线。

## V4对称MA7 cross × 持仓迟滞

- [机器摘要](hype_1d_v4_symmetric_cross_hysteresis_2026-08-07_summary.json)、[分期/压力/延迟](hype_1d_v4_symmetric_cross_hysteresis_2026-08-07_metrics.csv)、[近期切片](hype_1d_v4_symmetric_cross_hysteresis_2026-08-07_recent.csv)、[90日滚动](hype_1d_v4_symmetric_cross_hysteresis_2026-08-07_rolling_90d.csv)、[24相位](hype_1d_v4_symmetric_cross_hysteresis_2026-08-07_phase24.csv)与[最新延伸](hype_1d_v4_symmetric_cross_hysteresis_2026-08-07_latest.csv)。
- [`V4_CONTROL`交易](hype_1d_v4_symmetric_cross_hysteresis_2026-08-07_v4_control_trades.csv)、[对称候选交易](hype_1d_v4_symmetric_cross_hysteresis_2026-08-07_symmetric_cross_d075_trades.csv)、[逐笔差异](hype_1d_v4_symmetric_cross_hysteresis_2026-08-07_trade_deltas.csv)与两侧逐日path。
- [完整交易路径HTML](hype_1d_ma7_abt_v4_symmetric_cross_d075_trade_path_2026-08-07.html)：425根UTC日K、MA7、持仓`±0.75×ATR7`边界、持仓/cooldown状态、权益曲线及29笔入场—出场连线。

## 初始规则

- [机器摘要](hype_1d_ma7_abt_summary_2026-08-04.json)：合同、数据质量、基准、全期指标与交易 bootstrap。
- [全期指标](hype_1d_ma7_abt_metrics_2026-08-04.csv)：三种空头退出解释及 long-only / short-only 消融。
- [近期切片](hype_1d_ma7_abt_recent_slices_2026-08-04.csv)：沿完整权益路径、锚定数据终点的 `1d/7d/1m/3m/6m/1y`，不重置仓位。
- [时间切分](hype_1d_ma7_abt_chronological_2026-08-04.csv)：flat-start prefit、researcher-exposed 最后 90 日与全期。
- [90 日滚动窗口](hype_1d_ma7_abt_rolling_90d_2026-08-04.csv)。
- [MA 邻域](hype_1d_ma7_abt_ma_neighborhood_2026-08-04.csv)：`SMA5–SMA10` 稳健性诊断。
- [执行压力](hype_1d_ma7_abt_execution_stress_2026-08-04.csv)：`8 bps`、额外延迟与零 funding 控制。
- [日界相位](hype_1d_ma7_abt_phase_audit_2026-08-04.csv)：UTC 与 `12:00 UTC` 日界。
- [字面版交易](hype_1d_ma7_abt_literal_trades_2026-08-04.csv)与[字面版权益路径](hype_1d_ma7_abt_literal_path_2026-08-04.csv)。

这些文件是已揭示历史上的 diagnostic evidence，不是 prospective OOS 或 promotion 许可。

## V4-PFT修复 Development

- [冻结manifest](hype_1d_ma7_v4_pft_repair_2026-08-09_manifest.json)：38项前置测试、432日数据审计、exact V4全窗锚点、8臂配置与实现pin。
- [8臂完整trials](hype_1d_ma7_v4_pft_repair_2026-08-09_development_trials.json)与[Development机器裁决](hype_1d_ma7_v4_pft_repair_2026-08-09_development.json)：8/8完成、0个passer、无champion，V/H未揭示。
- [A001_T D-only完整交易路径](hype_1d_ma7_v4_pft_repair_2026-08-09_development_failed_A001_T_trade_path.html)：259根UTC日K、MA7、权益曲线和12笔入场—出场连线；明确标记hard-gate FAIL与V/H未揭示。
- 每个JSON/HTML均带同basename `.sha256` sidecar；这是researcher-exposed Development diagnostic evidence，不是prospective/OOS或promotion许可。

## TPR趋势阶段与风险效率（Development PASS / Validation FAIL）

- [冻结manifest](hype_1d_ma7_trend_phase_risk_2026-08-09_manifest.json)：56项前置测试、432日/10,390小时/2,597 funding零blocker审计、13臂信号网格、9臂条件杠杆网格与实现pin。
- [13臂Development trials与事件研究](hype_1d_ma7_trend_phase_risk_2026-08-09_development_trials.json)、[Development机器裁决](hype_1d_ma7_trend_phase_risk_2026-08-09_development.json)及[D champion冻结](hype_1d_ma7_trend_phase_risk_2026-08-09_champion.json)：`QOFF_EOFF_T25X2`是唯一通过者，D/WFO同时提高收益、降低真实`1h`顺序MDD。
- [一次性Validation](hype_1d_ma7_trend_phase_risk_2026-08-09_validation.json)：T在V中0次触发，候选与exact V4逐笔相同，均为`+12.21%/-18.82%`、3笔，hard-gate FAIL。
- [D champion完整逐笔HTML](hype_1d_ma7_trend_phase_risk_2026-08-09_development_QOFF_EOFF_T25X2_trade_path.html)：259根UTC日K、MA7、候选/V4切换、12/10笔完整入场—出场连线与权益路径。
- 每个JSON/HTML均带同basename `.sha256` sidecar且已复核；因V失败，不存在leverage、holdout或final artifact，H保持未揭示。

## WTL广域趋势生命周期（Development FAIL）

- [冻结manifest](hype_1d_ma7_wide_trend_lifecycle_2026-08-10_manifest.json)：57项前置测试、432日/10,390小时/2,597 funding零blocker审计、D/V/H边界、exact V4锚点和实现pin。
- [Stage A](hype_1d_ma7_wide_trend_lifecycle_2026-08-10_stage_a.json)：entry、long/short MFE与short RSI共`555/555`个单模块trial，0 error。
- [Stage B](hype_1d_ma7_wide_trend_lifecycle_2026-08-10_stage_b.json)：32个候选的六折flat-start rolling筛选，每族保留4个。
- [Stage C](hype_1d_ma7_wide_trend_lifecycle_2026-08-10_stage_c.json)：`624/624`个低复杂度组合；440个组合只差冻结的V候选3笔门，0个prepass passer，因此无deep、champion、leverage、holdout或final artifact。
- [失败后多轮消融](hype_1d_ma7_wide_trend_lifecycle_2026-08-10_post_fail_ablation.json)：162条独立D+V经济路径、四模块全上下文leave-one-out、代表候选keep-one/leave-one与rolling归因；角色严格为`DIAGNOSTIC_ONLY`。
- 全部JSON都有同basename `.sha256` sidecar并已复核；H=`[356,432)`从未运行WTL候选。

## OAPP机会感知利润保护（Development PASS / H FAIL）

- [冻结manifest](hype_1d_ma7_opportunity_aware_profit_protection_2026-08-10_manifest.json)：68项测试、957单模块、64组合上限、9杠杆臂、数据/实现pin和H未访问声明。
- [Stage A](hype_1d_ma7_opportunity_aware_profit_protection_2026-08-10_stage_a.json)：912个long MFE +45个RSI，957/957、0 error；经济路径去重。
- [Stage B](hype_1d_ma7_opportunity_aware_profit_protection_2026-08-10_stage_b.json)与[Stage C](hype_1d_ma7_opportunity_aware_profit_protection_2026-08-10_stage_c.json)：32条rolling/8bps路径、64组合、32 prepass、11 deep及11组完整OAT。
- [唯一champion](hype_1d_ma7_opportunity_aware_profit_protection_2026-08-10_champion.json)与[H前杠杆冻结](hype_1d_ma7_opportunity_aware_profit_protection_2026-08-10_leverage_freeze.json)：`0.5ATR/10%/2d + RSI20×2`及9个<=3x target臂。
- [H访问锁](hype_1d_ma7_opportunity_aware_profit_protection_2026-08-10_holdout_access_lock.json)与[一次性H裁决](hype_1d_ma7_opportunity_aware_profit_protection_2026-08-10_holdout.json)：OAPP 1x `+16.70%/-17.94%` vs V4 `+22.43%/-17.94%`，hard-gate FAIL。
- [最终机器报告](hype_1d_ma7_opportunity_aware_profit_protection_2026-08-10_final.json)、[原锁定HTML](hype_1d_ma7_opportunity_aware_profit_protection_2026-08-10_full_trade_path.html)与[可缩放逐笔HTML V2](hype_1d_ma7_opportunity_aware_profit_protection_2026-08-10_full_trade_path_zoomable_v2.html)：全窗17/17笔连线；V2增加滚轮/按钮缩放、拖拽平移、双区间滑块、逐笔聚焦、策略切换和完整参数表，不覆盖原证据。
- 全部JSON/HTML都有同basename `.sha256` sidecar；H已耗尽，不存在替补或重跑许可。

## PEHC利润退出后handoff（Exposed shadow freeze / prospective insufficient）

- [冻结manifest](hype_1d_ma7_profit_exit_handoff_continuity_2026-08-10_manifest.json)：87项测试、432日/10,390小时/2,597 funding零blocker、490臂与19个实现pin。
- [Stage A](hype_1d_ma7_profit_exit_handoff_continuity_2026-08-10_stage_a.json)：490/490、0 error、8个54日flat-start block，去重为13条经济路径。
- [Stage B](hype_1d_ma7_profit_exit_handoff_continuity_2026-08-10_stage_b.json)与[Stage C](hype_1d_ma7_profit_exit_handoff_continuity_2026-08-10_stage_c.json)：13条8bps/funding-off/12h深审，3条通过shadow门，冻结`PEHC_294`。
- [Shadow candidate](hype_1d_ma7_profit_exit_handoff_continuity_2026-08-10_shadow_candidate.json)、[post-freeze逐事件消融](hype_1d_ma7_profit_exit_handoff_continuity_2026-08-10_post_freeze_ablation.json)与[prospective协议](hype_1d_ma7_profit_exit_handoff_continuity_2026-08-10_prospective_protocol.json)：角色严格为`shadow-only`，前瞻状态`INSUFFICIENT_FUTURE_DATA`，杠杆锁定。
- [前瞻observer manifest](hype_1d_ma7_profit_exit_handoff_continuity_prospective_observer_v1_2026-08-10_manifest.json)：97项联合测试、冻结候选/V4逐字节anchor、observer与上游artifact SHA链、cold-flat和最早样本合格terminal口径。
- [初始前瞻观察](hype_1d_ma7_profit_exit_handoff_continuity_prospective_observer_v1_2026-08-10_observation_through_2026-08-05.json)：前瞻起点前`0`个新增完整UTC日，`performance_disclosed=false`，没有读取或持久化候选/对照绩效。
- [原锁定HTML](hype_1d_ma7_profit_exit_handoff_continuity_2026-08-10_full_trade_path.html)与[可缩放逐笔HTML V2](hype_1d_ma7_profit_exit_handoff_continuity_2026-08-10_full_trade_path_zoomable_v2.html)：候选/V4切换、19/17笔连线、60个shadow/handoff事件、1根明确标记的display-only terminal candle；V2增加滚轮/按钮缩放、拖拽平移、双区间滑块、逐笔聚焦和完整继承参数表，无外部依赖。
- [Zoomable V2 manifest](hype_1d_ma7_oapp_pehc_zoomable_trade_paths_v2_2026-08-10_manifest.json)：固定OAPP与`PEHC_294`身份、源artifact SHA、生成器/测试SHA、交互能力与逐笔连线审计。
- 所有JSON/HTML均带同basename `.sha256` sidecar且已复核；全部历史绩效是researcher-exposed诊断，不是OOS、登记或promotion许可。

## CTLS持续趋势生命周期（R1–R6 HARD-GATE-FAILED）

- [R1修复后manifest](hype_1d_ma7_ctls_2026-08-10_manifest_v2.json)与[R1 Stage A](hype_1d_ma7_ctls_2026-08-10_stage_a_v2.json)：324项规则十状态搜索，0项通过；原始manifest保留为pre-performance修复审计证据。
- [R2连续强度](hype_1d_ma7_ctls_r2_2026-08-10_direction_a1.json)：1,944项，0项通过；方向与flat recall互斥。
- [R3 walk-forward可辨识性](hype_1d_ma7_ctls_r3_2026-08-10_direction.json)：372项，0项通过；高准确率路径flip过高。
- [R4稳定趋势段](hype_1d_ma7_ctls_r4_2026-08-10_direction.json)：1,488项，0项通过；改变评估真值后仍存在准确率/flip冲突。
- [R5持续期解码](hype_1d_ma7_ctls_r5_2026-08-10_direction.json)：4,464项，0项通过；低flip与跨折稳定互斥。
- [R6日内上下文](hype_1d_ma7_ctls_r6_2026-08-10_direction.json)：62项因果特征、4,464项、3,941条独立路径，0项通过；这是本轮最终机器裁决。
- 六轮合计`13,056`个配置；状态识别未过门，所以没有PnL、LES、杠杆、champion、final或交易路径HTML artifact。

## V6-DTEC延迟趋势episode（Development HARD-GATE-FAILED）

- [冻结manifest](hype_1d_ma7_v6_delayed_episode_2026-08-10_manifest.json)：41项前置测试、exact V6身份/关闭等价、`576+576+16`搜索空间、D/六折/评估边界与实现pin。
- [Stage A](hype_1d_ma7_v6_delayed_episode_2026-08-10_stage_a.json)：1,152个long-only/short-only配置。long最优`+339.54%/-17.77%`但MDD不变且只有1个确认样本；short最优标签`7/9`命中但绩效降至`+130.10%/-26.40%`。
- [Stage B](hype_1d_ma7_v6_delayed_episode_2026-08-10_stage_b.json)：16个多空组合全部同一经济路径，`+177.57%/-26.40%`，0项通过。
- [Evaluation](hype_1d_ma7_v6_delayed_episode_2026-08-10_evaluation.json)明确`evaluation_accessed=false`；[最终裁决](hype_1d_ma7_v6_delayed_episode_2026-08-10_final.json)为`HARD-GATE-FAILED`。
- 全部JSON带同basename `.sha256` sidecar；无champion、无杠杆、无V7、无交易路径HTML。
- [全432日同窗post-reveal诊断](hype_1d_ma7_v6_dtec_l189_full_history_post_reveal_2026-08-10.json)：用户授权后比较exact V6 `+617.11%/-18.39%`与`DTEC_L189` `+623.48%/-20.97%`，并保留后108日cold-flat双劣证据；角色仅为diagnostic，不改变原hard-gate失败。

## V6七项转换链修复（全历史post-reveal HARD-GATE-FAILED）

- [锁定机器证据v2](hype_1d_ma7_v6_transition_repair_ablation_2026-08-10_v2.json)：exact V6关闭等价、14个逐项arm、108个组合、8bps、8×54日cold-flat、近期切片、完整事件与逐笔经济路径；收益更高/MDD更小/双改善均为`0/108`，无champion。
- v2及其`.sha256`为最终引用；无后缀v1仅有合同市场名元数据误写，绩效、事件和交易内容与v2逐项相同，保留但已被v2取代。
- 本分支没有V7、杠杆或交易路径HTML；所有结果均为researcher-exposed diagnostic evidence。

## V6连续趋势Overlay（全历史post-reveal HARD-GATE-FAILED）

- [机器证据](hype_1d_ma7_v6_continuous_trend_overlay_2026-08-10.json)：exact V6与`CTO_L189`、`CTO_S005`、`CTO_L189_S005`、`CTO_C001`四个冻结overlay候选的全窗、8bps、funding-off、额外一日lag、8×54日cold-flat、近期切片和机会成本审计；0个候选通过。
- 方向命中率不是成功门：`CTO_L189`为`+623.48%/-20.97%`但只有1个确认且MDD恶化；short类候选破坏V6 long/OAPP/PEHC链条。本分支不登记V7、不运行杠杆、不生成交易路径HTML。
- [严格三门放行器机器证据](hype_1d_ma7_v6_strict_continuation_overlay_2026-08-10.json)：只运行一套固定非ML规则（3日同侧、`2d`斜率、MA7距离、ER5、MAE预算与机会成本门）；结果为`+255.26%/-32.65%`，相对V6收益少`361.85pp`且MDD多`14.26pp`，继续`HARD-GATE-FAILED`。

## V6 RSI6记忆cross（全历史post-reveal FAIL）

- [最终机器证据v2](hype_1d_ma7_v6_rsi6_memory_cross_2026-08-10_v2.json)：exact V6关闭等价、主规则与4个消融/敏感性arm、8bps、8×54日cold-flat、近期切片、完整逐笔差异及实现pin；主规则增收但扩大MDD。
- 无后缀v1只因零容差把路径相同的浮点尾差误称为MDD改善；v2以`1e-10`容差更正比较标签，成交和指标数值不变，后续只引用v2。
- [主规则可缩放完整路径](hype_1d_ma7_v6_rsi6_memory_cross_2026-08-10_primary_trade_path.html)与[审计manifest](hype_1d_ma7_v6_rsi6_memory_cross_2026-08-10_trade_path_manifest.json)：433根展示K线（含1根terminal display-only）、A1/V6切换、21/19笔全部连线、3个记忆cross事件、无外部依赖。
- 本分支不登记V7、不运行杠杆、不改变V6；所有绩效均为researcher-exposed diagnostic evidence。

## V6 short cooldown 5d → 2d（单变量FAIL）

- [机器证据](hype_1d_ma7_v6_short_cooldown_2d_2026-08-10.json)：逐字段唯一变量审计、exact V6与RSI6记忆cross双重对照、8bps、8×54日cold-flat、近期切片和完整逐笔差异；两组均FAIL。
- [可缩放完整路径](hype_1d_ma7_v6_short_cooldown_2d_2026-08-10_trade_path.html)与[审计manifest](hype_1d_ma7_v6_short_cooldown_2d_2026-08-10_trade_path_manifest.json)：2d/5d切换、19/19笔全部连线、2个新增亏损short事件、无外部依赖。
- 本分支不修改V6、不登记V7、不继续搜索cooldown天数；所有绩效均为researcher-exposed diagnostic evidence。

## V6固定3x杠杆（已暴露历史HIGH_TAIL_RISK）

- [机器证据](hype_1d_ma7_abt_v6_3x_leverage_2026-08-10.json)：exact V6 `1x/3x`逐笔等价、真实`1h`风险回放、8bps、funding-off、额外一日延迟、近期切片、8×54日cold-flat、13个90日滚动窗、24相位及简化maintenance筛查。
- [可缩放完整路径](hype_1d_ma7_abt_v6_3x_leverage_trade_path_2026-08-10.html)与[审计manifest](hype_1d_ma7_abt_v6_3x_leverage_trade_path_2026-08-10_manifest.json)：固定3x/exact V6 1x切换、19/19笔全部连线、完整shadow/handoff事件、无外部依赖。
- 3x主相位为`+14,164.73%/-45.35%`，但24相位最差`-59.97%/-94.19%`、最大marked leverage `7.65x`；只作用户明确授权的diagnostic，不解锁或修改V6杠杆。

## V6固定2x杠杆（已暴露历史HISTORICAL_SCREEN_ONLY）

- [机器证据](hype_1d_ma7_abt_v6_2x_leverage_2026-08-10.json)：exact V6 `1x/2x`逐笔等价、真实`1h`风险回放、8bps、funding-off、额外一日延迟、近期切片、8×54日cold-flat、13个90日滚动窗、24相位及简化maintenance筛查。
- 2x主相位为`+3,532.97%/-31.51%`，简化maintenance未触发，但24相位最差MDD为`-81.31%`；只作用户明确授权的diagnostic，不解锁或修改V6杠杆。

## V6 EMA7 替换（已暴露历史FAIL）

- [机器证据](hype_1d_ma7_abt_v6_ema7_substitution_2026-08-10.json)：只将 V6 的 `features.ma7` 替换为 `EMA(span=7, adjust=False, min_periods=7)`，其余 V6/OAPP/PEHC/成本/执行顺序不变；全窗`-24.54%/-62.30%` vs V6 `+617.11%/-18.39%`，8bps、funding-off、lag、分块、滚动和24相位均失败。

## V6执行层优化（已暴露历史FAIL）

- [机器证据](hype_1d_ma7_abt_v6_execution_improvement_2026-08-10.json)：exact V6 `1x` 上测试18个“限价改善 + 超时市价兜底”候选。最佳 `X_K10_T24` 为`+641.76%/-17.77%`，主窗双优但 lag、cold-flat block 与核心链条门失败；entry-only和entry+exit均双劣。本分支不改V6、不登记V7、不生成HTML。
- [盘中ATR阈值入场机器证据](hype_1d_ma7_v6_intraday_threshold_entry_2026-08-11.json)及其[SHA256](hype_1d_ma7_v6_intraday_threshold_entry_2026-08-11.json.sha256)：使用上一完整日 `SMA7/ATR7` 测试 `0.25/0.50/0.65/0.80/1.00 ATR` fresh intraday threshold entry；最佳 `1.00 ATR` 仅`+60.08%/-41.80%`，5项全部FAIL，不改V6、不登记V7、不生成HTML。
- [全参数消融机器证据](hype_1d_ma7_abt_v6_full_parameter_ablation_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v6_full_parameter_ablation_2026-08-11.json.sha256)：224个V4/V5/V6 active-parameter OAT与单参数邻域候选；`short_cooldown_days_3`最佳为`+711.04%/-18.40%`，已按用户请求登记为V7；`8/10d`与`short_rsi_threshold_25`仍只作post-reveal前瞻线索。
- [V7冻结机器证据](hype_1d_ma7_abt_v7_short_cooldown3_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v7_short_cooldown3_2026-08-11.json.sha256)：完整参数、20笔交易、逐日路径、handoff事件、实现SHA与HTML审计；状态为`registered / not promoted / not live-ready`。
- [V7交互式交易路径HTML](hype_1d_ma7_abt_v7_trade_path_2026-08-11.html)及其[SHA256](hype_1d_ma7_abt_v7_trade_path_2026-08-11.html.sha256)：432根UTC日K、MA7、RSI6与`30/70`参考线、权益、V7/Exact V6切换、20/19笔逐笔入出场连线和完整冻结参数表；无外部依赖。
- [V7固定2x机器证据](hype_1d_ma7_abt_v7_2x_leverage_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v7_2x_leverage_2026-08-11.json.sha256)：exact V7 `1x/2x`逐笔等价、真实`1h`风险回放、8bps、funding-off、额外一日延迟、近期切片、8×54日cold-flat、13个90日滚动窗、24相位及简化maintenance筛查；主相位`+4,550.71%/-31.51%`，24相位最差MDD`-87.02%`，仅作`HISTORICAL_SCREEN_ONLY`诊断。
- [V7四机制逐项消融机器证据](hype_1d_ma7_abt_v7_four_mechanism_ablation_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v7_four_mechanism_ablation_2026-08-11.json.sha256)：pending reclaim、short RSI放宽、overbought exhaustion short、post-exit cooldown override四个固定机制逐项ablation；全部FAIL，M1交易数34/MDD`-52.30%`，组合臂44笔/MDD`-45.33%`，不修改V7。
- [V7四机制组合搜索机器证据](hype_1d_ma7_abt_v7_four_mechanism_combo_search_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v7_four_mechanism_combo_search_2026-08-11.json.sha256)：240个post-reveal组合候选；唯一全窗双优类为`P0__R25x2__CG__O0`，即只把short RSI止盈从`20×2`放宽到`25×2`，`+715.71%/-18.40%`、20笔、8个block全正，裁决`POST_REVEAL_CANDIDATE_ONLY`，不改V7。
- [V7 stale reclaim probe机器证据](hype_1d_ma7_abt_v7_stale_reclaim_probe_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v7_stale_reclaim_probe_2026-08-11.json.sha256)：144个过期reclaim补票/轻仓probe候选；无全窗双优，最佳`S_long_only_MIN2_MAX3_D1p25_L0p25`为`+572.40%/-20.90%`、26笔、stale confirm 5次，裁决`FAIL / noise-releasing`。
- [V7反向K+RSI极值reclaim机器证据](hype_1d_ma7_abt_v7_reverse_rsi_reclaim_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v7_reverse_rsi_reclaim_2026-08-11.json.sha256)：54个raw cross当天反向K/RSI极值放行候选；无全窗双优，最佳`RK_short_only_R0p50_D1p00_L1p00`为`+351.06%/-23.72%`、23笔、触发11次，both版本能命中目标三段但收益/MDD恶化，裁决`FAIL`。
- [V7反向K+RSI后续确认机器证据](hype_1d_ma7_abt_v7_reverse_rsi_followthrough_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v7_reverse_rsi_followthrough_2026-08-11.json.sha256)：324个reverse-rsi tag + follow-through候选；`FT_long_only_R0p50_A2_P0p25_D1p25_L0p50` 为 `+728.96%/-17.87%`、23笔、tag/confirm `10/2`，压力包通过，裁决`POST_REVEAL_CANDIDATE_ONLY`，不改V7。
- [V7空头MA7斜率退出变体机器证据](hype_1d_ma7_abt_v7_short_slope_exit_variants_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v7_short_slope_exit_variants_2026-08-11.json.sha256)：测试`lookback=2/3`、`MA7上拐+close>MA7`及ATR buffer三类空头退出；所有变体收益低于V7，最佳收益`+574.59%/-18.40%`，裁决`FAIL / path-disruption`。
- [V7 delayed impulse机器证据](hype_1d_ma7_abt_v7_delayed_impulse_confirmation_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v7_delayed_impulse_confirmation_2026-08-11.json.sha256)：144个实体impulse补票候选；最佳`+718.20%/-20.98%`、22笔、tag/confirm `14/1`，裁决`FAIL / higher-return-higher-risk`。
- [V7 state-control机器证据](hype_1d_ma7_abt_v7_state_control_variants_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v7_state_control_variants_2026-08-11.json.sha256)：空头max_hold延长与PEHC禁用诊断；max_hold延长降至`+697.06%/-18.40%`，禁用PEHC降至`+512.12%/-21.57%`，均FAIL。
- [V7全参数清理消融机器证据](hype_1d_ma7_abt_v7_full_parameter_cleanup_ablation_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v7_full_parameter_cleanup_ablation_2026-08-11.json.sha256)：224个V7全参数/OAT候选；`short_rsi_threshold_25`为post-reveal小候选`+715.71%/-18.40%`，V7.1只登记功能等价参数面清理。
- [V7.1 Binance U本位Top15迁移机器证据](hype_1d_ma7_abt_v7_1_top15_binance_perp_transfer_2026-08-11.json)及其[SHA256](hype_1d_ma7_abt_v7_1_top15_binance_perp_transfer_2026-08-11.json.sha256)：按最近30个已闭合UTC日K `quote_volume` 在 Binance U本位 futures 全部合约中选Top15，包含`PERPETUAL`、`TRADIFI_PERPETUAL`、`USDT`和`USDC`；最终15个标的仅2个正收益，中位收益`-27.49%`，裁决`TRANSFER_FAIL`。
- [V7.1 Binance USDT本位Top30迁移机器证据](hype_1d_ma7_abt_v7_1_top30_binance_usdt_u_margin_transfer_2026-08-12.json)及其[SHA256](hype_1d_ma7_abt_v7_1_top30_binance_usdt_u_margin_transfer_2026-08-12.json.sha256)：过滤`USDC`、保留`USDT`普通永续与`TRADIFI_PERPETUAL`，按最近30个已闭合UTC日K `quote_volume` 取Top30；正收益`9/30`、有交易`29/30`、中位收益`-20.81%`，裁决`TRANSFER_FAIL`。
- [V7.1 MA20替换USDT本位Top20机器证据](hype_1d_ma7_abt_v7_1_ma20_top20_binance_usdt_u_margin_transfer_2026-08-12.json)及其[SHA256](hype_1d_ma7_abt_v7_1_ma20_top20_binance_usdt_u_margin_transfer_2026-08-12.json.sha256)：同USDT-only口径取Top20，仅将`SMA7`替换为`SMA20`；正收益`11/20`、中位收益`+1.25%`，但`HYPEUSDT`降至`-2.65%`，裁决`TRANSFER_MIXED_POSITIVE / diagnostic-only`。
- [V7.1 OAPP反弹重置机器证据](hype_1d_ma7_abt_v7_1_oapp_rebound_reset_2026-08-20.json)及其[SHA256](hype_1d_ma7_abt_v7_1_oapp_rebound_reset_2026-08-20.json.sha256)：扩展数据精确复现`08-09 55.113`开多、`08-16 56.894` OAPP平仓；RR、AF05、MAG05均阻止该次退出，但canonical全路径全部低于V7.1，裁决生产`KEEP V7.1`、研究`SHADOW RR`，不改runner。
- [2026-08-20前瞻数据同步审计](hype_1h_prospective_sync_2026-08-20.json)：1h K线与funding补齐至`2026-08-20 04:00 UTC`，连续性与重复时间戳审计零阻断。
- [2026-09-04前瞻数据同步审计](hype_1h_prospective_sync_2026-09-04.json)：1h K线与funding补齐至`2026-09-04 11:00 UTC`，连续性与重复时间戳审计零阻断。
- [2026-09-04 dry-run 开仓快照](hype_1d_ma7_abt_v7_1_dry_run_open_trade_2026-09-04.json)：第一笔 `ma7_reclaim_long` 仍持有，对照研究回放。
- [2026-09-07前瞻数据同步审计](hype_1h_prospective_sync_2026-09-07.json)：1h K线与funding补齐至`2026-09-07 07:00 UTC`，连续性与重复时间戳审计零阻断。
- [2026-09-07 dry-run 首笔闭合快照](hype_1d_ma7_abt_v7_1_dry_run_closed_trade_2026-09-07.json)：OAPP 平仓，对照研究下一开盘。
- [V7.1 OAPP零利润回吐机器证据](hype_1d_ma7_abt_v7_1_oapp_zero_profit_floor_2026-08-20.json)及其[SHA256](hype_1d_ma7_abt_v7_1_oapp_zero_profit_floor_2026-08-20.json.sha256)：ZPF只在收盘回到entry或以下时退出；canonical为`+469.37%/-25.07%`，弱于V7.1及OAPP off，PEHC handoff归零，裁决`NO-GO ZPF / KEEP V7.1`。
- [V7.1 OAPP七日振幅半距市价机器证据](hype_1d_ma7_abt_v7_1_oapp_range7_half_trail_2026-08-20.json)及其[SHA256](hype_1d_ma7_abt_v7_1_oapp_range7_half_trail_2026-08-20.json.sha256)：关闭 long OAPP 后，持仓最高价回吐过去7日高低差一半即1h市价平；canonical为`+185.20%/-33.04%/23笔`，弱于V7.1与OAPP off，08-09多头在`08-11 16:00`亏损离场，裁决`NO-GO R7H / KEEP V7.1`。
- [V7.1 持仓ER7机器证据](hype_1d_ma7_abt_v7_1_er_hold_overlay_2026-08-20.json)及其[SHA256](hype_1d_ma7_abt_v7_1_er_hold_overlay_2026-08-20.json.sha256)：`08-15 ER7=0.239`低于8个canonical OAPP锁中位`0.312`，第0层分不开，第1层未跑，裁决`LAYER0_NOT_SEPARABLE / KEEP V7.1`。
- [SNC02趋势健康出场机器证据](hype_1d_ma7_snc02_trend_health_exit_2026-08-20.json)及其[SHA256](hype_1d_ma7_snc02_trend_health_exit_2026-08-20.json.sha256)：exact SNC02入场加冻结健康出场；canonical`+62.86%/-28.91%/37笔`优于裸核但未过MDD20，08-09多头在`08-12`因ER非正亏损离场，裁决`NO-GO THX / KEEP V7.1`。
- [对称裸MA7 Cross + Slope机器证据](hype_1d_ma7_symmetric_naked_cross_slope_2026-08-20.json)及其[SHA256](hype_1d_ma7_symmetric_naked_cross_slope_2026-08-20.json.sha256)：`SNC02`多空镜像fresh cross + `0.02ATR7` slope、只按反向合格信号翻仓；扩展`+32.56%/-50.79%`，能抓住08-09 long但lag/MDD失败，只作独立signal-core control。
- [对称裸MA7 Cross + Slope交互交易路径](hype_1d_ma7_symmetric_naked_cross_slope_trade_path_2026-08-20.html)、[SHA256](hype_1d_ma7_symmetric_naked_cross_slope_trade_path_2026-08-20.html.sha256)与[审计manifest](hype_1d_ma7_symmetric_naked_cross_slope_trade_path_2026-08-20_manifest.json)：446根完整UTC日K、SMA7、归一化1日斜率、真实1h权益、25笔入出场连线、合格信号及terminal-censored标识，无外部依赖。
- [SNC02风险覆盖OAT机器证据](hype_1d_ma7_snc02_risk_overlay_oat_2026-08-20.json)及其[SHA256](hype_1d_ma7_snc02_risk_overlay_oat_2026-08-20.json.sha256)：首次运行前冻结FF3、MA05、HS25、BE20、PT25_A3五个单变量臂；MA05为`+148.79%/-33.61%`且保留08-09 long，但0/5通过MDD20/RISK_OVERLAY门，Stage A不组合、不登记版本。

- [SNC02 MA05试仓与确认扩仓Stage B机器证据](hype_1d_ma7_snc02_ma05_probe_sizing_stage_b_2026-08-20.json)及其[SHA256](hype_1d_ma7_snc02_ma05_probe_sizing_stage_b_2026-08-20.json.sha256)：固定0.5x为`+64.69%/-19.50%`但未过收益/最新趋势保留门；三种确认扩仓MDD为`-33.17%~-45.99%`且lag全负，`CONTINUATION_CANDIDATE=0/5`。

- [SNC02 MA05固定ATR灾难止损Stage C机器证据](hype_1d_ma7_snc02_ma05_hard_stop_stage_c_2026-08-20.json)及其[SHA256](hype_1d_ma7_snc02_ma05_hard_stop_stage_c_2026-08-20.json.sha256)：`1.0/1.5/2.0ATR7`三档均未过MDD20；HS10最好为`+114.32%/-32.39%`，HS15双劣，HS20主路径0触发同control，固定ATR路线关闭。

- [SNC02 MA05权益回撤节流Stage D机器证据](hype_1d_ma7_snc02_ma05_equity_drawdown_governor_stage_d_2026-08-20.json)及其[SHA256](hype_1d_ma7_snc02_ma05_equity_drawdown_governor_stage_d_2026-08-20.json.sha256)：0.25x两臂把MDD压至`-18.61%/-18.93%`，但低风险状态超过92%、收益仅`+10.48%/+11.38%`且最新趋势只保留约四分之一；0.5x两臂仍未过MDD20，0/4候选。

- [SNC02趋势优先全量审计机器证据](hype_1d_ma7_snc02_trend_first_discovery_audit_2026-08-20.json)及其[SHA256](hype_1d_ma7_snc02_trend_first_discovery_audit_2026-08-20.json.sha256)：审计103个raw fresh cross和全部campaign；control major加权capture为`47.19%`、最新long为`83.53%`，CSM02虽补到13个事后major cross却为`-66.03%/-81.68%`并打断最新趋势，裁决`TREND_FIRST_GATE_FAILED`。

- [SNC02 EMA50分层发现机器证据](hype_1d_ma7_snc02_ema50_hierarchical_discovery_2026-08-20.json)及其[SHA256](hype_1d_ma7_snc02_ema50_hierarchical_discovery_2026-08-20.json.sha256)：HCSM50将delayed trade降至16笔，但仍在08-12误翻空，major加权capture仅`36.01%`，扩展窗`-10.93%/-57.50%`；不搜索EMA span。

## V6结构性入场与仓位管理（全历史post-reveal FAIL）

- [锁定机器证据v2](hype_1d_ma7_v6_structural_sizing_2026-08-10_v2.json)：exact V6关闭等价、9个预注册候选、逐笔probe/确认加仓/方向冷却/ATR目标事件、8bps、8×54日cold-flat、近期切片及因果episode差异；无后缀v1只因把复利基数变化误计为独立episode而被v2取代，绩效数值不变。
- [最佳诊断臂可缩放完整路径v2](hype_1d_ma7_v6_structural_sizing_2026-08-10_v2_best_trade_path.html)与[审计manifest v2](hype_1d_ma7_v6_structural_sizing_2026-08-10_v2_trade_path_manifest.json)：`A_LONG_P05_C2`/exact V6切换、19/19笔全部连线，仅画memory pass与promotion两条语义事件线，无外部依赖。
- long probe仅1个独立episode且MDD不变；方向冷却、short probe、ATR cap及组合均未同时提高收益并降低回撤。不登记V7、不修改V6。

## V6漏趋势逐段归因与隔离Probe（全历史post-reveal FAIL）

- [锁定机器证据](hype_1d_ma7_v6_missed_trend_attribution_2026-08-10.json)及其[SHA256](hype_1d_ma7_v6_missed_trend_attribution_2026-08-10.sha256)：29个CTLS-R4事后稳定趋势段、99个因果raw-cross root、逐段capture/freshness/cooldown/仓位归因、固定5日经济标签、34笔隔离`0.25x` probe、8bps、funding-off、额外1日lag、leave-one-out、近期切片与9项零失败invariant。
- V6只在15/29段有同向暴露，时长加权覆盖`39.51%`；但probe把`+617.11%/-18.39%`降至`+496.39%/-21.72%`，裁决`NON_ECONOMIC_MISSES / diagnostic-only`。不登记V7、不修改V6，普通诊断不生成HTML。
