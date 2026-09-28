# BIN-1D-MA7-CTP P4：MA7核心因子消融、模型压缩与高分穿越稳定性审计

> 2026-09-02 08:56:43.654558+00:00。状态：`explore / diagnostic-only / not promoted / not live-ready`。
> `2022-2024 IS REUSED DEVELOPMENT HISTORY, NOT NEW BLIND OOS`。
> P4 不是策略版本，不生成仓位、权益曲线、live spec、runner handoff 或 live-ready 产物。

## 1. 全局裁决

**FULL_B0_REMAINS_REFERENCE** / `explore / diagnostic-only / not promoted / not live-ready`；未来新 OOS 候选：`R_FULL_B0_69`。
- B0 fold-relative Top10 成功率 `41.62%`，uplift `0.0935`，净收益均值/中位数 `0.0146` / `-0.0445`。
- B0 Macro AUC `0.5799`，OOF raw AUC `0.5716`，20 日 non-overlap AUC `0.5671`。
- HYPE/2025+/TradFi 隔离：`0/0/0`。

## 2. 数据与隔离审计

| Item | Value |
| --- | ---: |
| 原始 pre-2025 MA7 事件 | 54137 |
| 严格样本 | 52563 |
| 资产 | 338 |
| long / short | 26237 / 26326 |
| 正例率 | 32.53% |
| 最早 / 最晚事件 | 2019-11-27 00:00:00+00:00 / 2024-12-10 00:00:00+00:00 |
| 最大 label_end_ts_20d | 2024-12-31 00:00:00+00:00 |
| 非穿越 / 重复 asset+ts / 空标签 / 不完整20日路径 | 0 / 0 / 0 / 0 |
| feature_known_at < / == / > entry_ts | 0 / 52563 / 0 |
| HYPE / 已知 TradFi 严格事件 | 0 / 0 |

## 3. 69个特征到六组的映射

| Group | Count | Fields |
| --- | ---: | --- |
| `G1_T1_MA7_STATE` | 12 | `t1_dir_close_ma7_dist_atr`, `t1_dir_ma7_slope_1d_atr`, `t1_dir_ma7_slope_3d_atr`, `t1_dir_ma7_slope_5d_atr`, `t1_dir_ma7_slope_change_3d`, `t1_dir_ma7_slope_accel_5d`, `t1_days_since_ma7_cross`, `t1_ma7_cross_count_7d`, `t1_ma7_cross_count_14d`, `t1_dir_price_side_ma7`, `t1_dir_favorable_run_days`, `t1_dir_opposite_run_days` |
| `G2_EVENT_GEOMETRY` | 13 | `dir_close_ma7_dist_atr`, `dir_ma7_slope_1d_atr`, `dir_ma7_slope_3d_atr`, `dir_ma7_slope_5d_atr`, `dir_ma7_slope_change_3d`, `dir_ma7_slope_accel_5d`, `large_cross_degree_atr`, `dir_ret_1d`, `daily_range_atr`, `body_atr`, `dir_close_location`, `dir_favorable_wick_atr`, `dir_adverse_wick_atr` |
| `G3_VOLATILITY_STATE` | 11 | `atr7_pct`, `atr14_pct`, `atr30_pct`, `atr14_to_atr30`, `atr7_to_atr30`, `t1_atr7_pct`, `t1_atr14_pct`, `t1_atr30_pct`, `t1_atr14_to_atr30`, `t1_atr7_to_atr30`, `t1_volatility_state_p0r` |
| `G4_VOLUME_ACTIVITY` | 5 | `volume_to_7d`, `quote_volume_to_7d`, `volume_to_30d`, `quote_volume_to_30d`, `volume_change_1d` |
| `G5_T1_MOMENTUM_LOCATION` | 21 | `t1_dir_ret_1d`, `t1_dir_ret_3d`, `t1_dir_ret_7d`, `t1_dir_ret_14d`, `t1_dir_ret_30d`, `t1_dir_ret_60d`, `t1_dir_range_pos_3d`, `t1_dir_range_pos_7d`, `t1_dir_range_pos_14d`, `t1_dir_range_pos_30d`, `t1_dir_range_pos_60d`, `t1_dir_distance_to_favorable_extreme_3d_atr`, `t1_dir_distance_to_favorable_extreme_7d_atr`, `t1_dir_distance_to_favorable_extreme_14d_atr`, `t1_dir_distance_to_favorable_extreme_30d_atr`, `t1_dir_distance_to_favorable_extreme_60d_atr`, `t1_dir_distance_from_adverse_extreme_3d_atr`, `t1_dir_distance_from_adverse_extreme_7d_atr`, `t1_dir_distance_from_adverse_extreme_14d_atr`, `t1_dir_distance_from_adverse_extreme_30d_atr`, `t1_dir_distance_from_adverse_extreme_60d_atr` |
| `G6_T1_PATH_REGIME` | 7 | `t1_path_efficiency_7d`, `t1_path_efficiency_14d`, `t1_path_efficiency_30d`, `t1_path_efficiency_60d`, `t1_shock_day`, `t1_sideways_state`, `t1_reexpansion_state` |

## 4. 候选模型及特征数量

| Candidate | Role | Feature count |
| --- | --- | ---: |
| `R_FULL_B0_69` | reference | 69 |
| `D_NO_G1_T1_MA7` | deletion_ablation | 57 |
| `D_NO_G2_EVENT_GEOMETRY` | deletion_ablation | 56 |
| `D_NO_G3_VOLATILITY` | deletion_ablation | 58 |
| `D_NO_G4_VOLUME` | deletion_ablation | 64 |
| `D_NO_G5_T1_MOMENTUM_LOCATION` | deletion_ablation | 48 |
| `D_NO_G6_T1_PATH_REGIME` | deletion_ablation | 62 |
| `O_G1_T1_MA7_ONLY` | only_group_diagnostic | 12 |
| `O_G2_EVENT_GEOMETRY_ONLY` | only_group_diagnostic | 13 |
| `O_G3_VOLATILITY_ONLY` | only_group_diagnostic | 11 |
| `O_G4_VOLUME_ONLY` | only_group_diagnostic | 5 |
| `O_G5_T1_MOMENTUM_LOCATION_ONLY` | only_group_diagnostic | 21 |
| `O_G6_T1_PATH_REGIME_ONLY` | only_group_diagnostic | 7 |
| `M_EVENT_25` | compressed_preregistered | 25 |
| `M_EVENT_VOL_36` | compressed_preregistered | 36 |

## 5. 每个模型D1/D2/D3训练期和验证期指标

| Candidate | Fold | Train n | Train AUC | Train Top10 | Val n | Val AUC | Val PR-AUC | Val Top10 | Val Top10净均值 | AUC gap | Uplift gap |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `R_FULL_B0_69` | D1 | 9376 | 0.6636 | 55.65% | 10452 | 0.5945 | 0.3719 | 43.21% | 0.0185 | 0.0691 | 0.0891 |
| `R_FULL_B0_69` | D2 | 19838 | 0.6509 | 53.02% | 14145 | 0.5598 | 0.3488 | 38.02% | 0.0060 | 0.0912 | 0.1416 |
| `R_FULL_B0_69` | D3 | 33416 | 0.6336 | 48.86% | 18052 | 0.5854 | 0.4108 | 43.52% | 0.0190 | 0.0482 | 0.0864 |
| `D_NO_G1_T1_MA7` | D1 | 9376 | 0.6626 | 54.69% | 10452 | 0.5950 | 0.3710 | 42.26% | 0.0173 | 0.0676 | 0.0891 |
| `D_NO_G1_T1_MA7` | D2 | 19838 | 0.6473 | 53.18% | 14145 | 0.5533 | 0.3440 | 36.89% | 0.0030 | 0.0940 | 0.1544 |
| `D_NO_G1_T1_MA7` | D3 | 33416 | 0.6259 | 48.03% | 18052 | 0.5842 | 0.4055 | 42.03% | 0.0152 | 0.0417 | 0.0930 |
| `D_NO_G2_EVENT_GEOMETRY` | D1 | 9376 | 0.6561 | 54.37% | 10452 | 0.6010 | 0.3723 | 41.49% | 0.0158 | 0.0551 | 0.0935 |
| `D_NO_G2_EVENT_GEOMETRY` | D2 | 19838 | 0.6479 | 52.47% | 14145 | 0.5636 | 0.3523 | 38.23% | 0.0072 | 0.0843 | 0.1340 |
| `D_NO_G2_EVENT_GEOMETRY` | D3 | 33416 | 0.6304 | 47.94% | 18052 | 0.5813 | 0.4031 | 43.30% | 0.0180 | 0.0491 | 0.0794 |
| `D_NO_G3_VOLATILITY` | D1 | 9376 | 0.6500 | 55.01% | 10452 | 0.5893 | 0.3733 | 44.74% | 0.0243 | 0.0608 | 0.0674 |
| `D_NO_G3_VOLATILITY` | D2 | 19838 | 0.6391 | 52.12% | 14145 | 0.5540 | 0.3469 | 38.30% | 0.0059 | 0.0851 | 0.1297 |
| `D_NO_G3_VOLATILITY` | D3 | 33416 | 0.6185 | 48.00% | 18052 | 0.5836 | 0.4265 | 50.44% | 0.0330 | 0.0348 | 0.0085 |
| `D_NO_G4_VOLUME` | D1 | 9376 | 0.6615 | 55.01% | 10452 | 0.5903 | 0.3696 | 43.31% | 0.0185 | 0.0712 | 0.0817 |
| `D_NO_G4_VOLUME` | D2 | 19838 | 0.6484 | 51.81% | 14145 | 0.5574 | 0.3415 | 35.55% | 0.0003 | 0.0910 | 0.1543 |
| `D_NO_G4_VOLUME` | D3 | 33416 | 0.6312 | 47.31% | 18052 | 0.5813 | 0.4034 | 42.14% | 0.0152 | 0.0499 | 0.0847 |
| `D_NO_G5_T1_MOMENTUM_LOCATION` | D1 | 9376 | 0.6336 | 49.79% | 10452 | 0.5685 | 0.3538 | 39.87% | 0.0129 | 0.0651 | 0.0639 |
| `D_NO_G5_T1_MOMENTUM_LOCATION` | D2 | 19838 | 0.6254 | 47.53% | 14145 | 0.5558 | 0.3501 | 39.36% | 0.0114 | 0.0695 | 0.0733 |
| `D_NO_G5_T1_MOMENTUM_LOCATION` | D3 | 33416 | 0.6100 | 45.21% | 18052 | 0.5793 | 0.4129 | 45.07% | 0.0203 | 0.0307 | 0.0344 |
| `D_NO_G6_T1_PATH_REGIME` | D1 | 9376 | 0.6593 | 53.94% | 10452 | 0.5943 | 0.3735 | 42.54% | 0.0167 | 0.0650 | 0.0787 |
| `D_NO_G6_T1_PATH_REGIME` | D2 | 19838 | 0.6463 | 51.51% | 14145 | 0.5643 | 0.3543 | 38.73% | 0.0085 | 0.0820 | 0.1194 |
| `D_NO_G6_T1_PATH_REGIME` | D3 | 33416 | 0.6298 | 48.00% | 18052 | 0.5786 | 0.4087 | 44.46% | 0.0207 | 0.0512 | 0.0683 |
| `O_G1_T1_MA7_ONLY` | D1 | 9376 | 0.5478 | 39.55% | 10452 | 0.5614 | 0.3422 | 38.15% | 0.0147 | -0.0135 | -0.0212 |
| `O_G1_T1_MA7_ONLY` | D2 | 19838 | 0.5639 | 42.04% | 14145 | 0.5284 | 0.3302 | 36.18% | 0.0070 | 0.0354 | 0.0501 |
| `O_G1_T1_MA7_ONLY` | D3 | 33416 | 0.5562 | 38.21% | 18052 | 0.5290 | 0.3647 | 36.10% | 0.0023 | 0.0272 | 0.0541 |
| `O_G2_EVENT_GEOMETRY_ONLY` | D1 | 9376 | 0.5690 | 45.42% | 10452 | 0.5268 | 0.3155 | 31.93% | -0.0080 | 0.0421 | 0.0996 |
| `O_G2_EVENT_GEOMETRY_ONLY` | D2 | 19838 | 0.5680 | 41.23% | 14145 | 0.5229 | 0.3371 | 38.59% | 0.0067 | 0.0451 | 0.0180 |
| `O_G2_EVENT_GEOMETRY_ONLY` | D3 | 33416 | 0.5547 | 40.78% | 18052 | 0.5599 | 0.4060 | 45.68% | 0.0220 | -0.0052 | -0.0160 |
| `O_G3_VOLATILITY_ONLY` | D1 | 9376 | 0.5899 | 36.89% | 10452 | 0.5477 | 0.3188 | 30.88% | -0.0102 | 0.0422 | 0.0248 |
| `O_G3_VOLATILITY_ONLY` | D2 | 19838 | 0.5841 | 37.20% | 14145 | 0.5520 | 0.3514 | 42.05% | 0.0141 | 0.0320 | -0.0569 |
| `O_G3_VOLATILITY_ONLY` | D3 | 33416 | 0.5777 | 39.74% | 18052 | 0.5790 | 0.4026 | 44.57% | 0.0177 | -0.0013 | -0.0154 |
| `O_G4_VOLUME_ONLY` | D1 | 9376 | 0.5257 | 33.80% | 10452 | 0.4958 | 0.2952 | 27.92% | -0.0104 | 0.0299 | 0.0235 |
| `O_G4_VOLUME_ONLY` | D2 | 19838 | 0.5565 | 33.11% | 14145 | 0.4875 | 0.3047 | 30.95% | -0.0057 | 0.0690 | 0.0132 |
| `O_G4_VOLUME_ONLY` | D3 | 33416 | 0.5289 | 32.97% | 18052 | 0.5553 | 0.3888 | 41.03% | 0.0264 | -0.0265 | -0.0475 |
| `O_G5_T1_MOMENTUM_LOCATION_ONLY` | D1 | 9376 | 0.6252 | 51.39% | 10452 | 0.5945 | 0.3685 | 41.01% | 0.0134 | 0.0307 | 0.0684 |
| `O_G5_T1_MOMENTUM_LOCATION_ONLY` | D2 | 19838 | 0.6180 | 46.93% | 14145 | 0.5435 | 0.3400 | 36.75% | 0.0034 | 0.0744 | 0.0934 |
| `O_G5_T1_MOMENTUM_LOCATION_ONLY` | D3 | 33416 | 0.5909 | 41.59% | 18052 | 0.5468 | 0.3836 | 43.13% | 0.0221 | 0.0441 | 0.0176 |
| `O_G6_T1_PATH_REGIME_ONLY` | D1 | 9376 | 0.5508 | 39.66% | 10452 | 0.5382 | 0.3314 | 36.52% | 0.0132 | 0.0126 | -0.0039 |
| `O_G6_T1_PATH_REGIME_ONLY` | D2 | 19838 | 0.5546 | 41.13% | 14145 | 0.5311 | 0.3315 | 34.20% | 0.0028 | 0.0235 | 0.0608 |
| `O_G6_T1_PATH_REGIME_ONLY` | D3 | 33416 | 0.5466 | 38.75% | 18052 | 0.5319 | 0.3730 | 39.15% | 0.0125 | 0.0147 | 0.0290 |
| `M_EVENT_25` | D1 | 9376 | 0.5847 | 44.67% | 10452 | 0.5300 | 0.3191 | 33.46% | -0.0015 | 0.0547 | 0.0768 |
| `M_EVENT_25` | D2 | 19838 | 0.5857 | 45.06% | 14145 | 0.5365 | 0.3477 | 41.41% | 0.0116 | 0.0492 | 0.0281 |
| `M_EVENT_25` | D3 | 33416 | 0.5743 | 42.61% | 18052 | 0.5695 | 0.4163 | 47.67% | 0.0252 | 0.0048 | -0.0176 |
| `M_EVENT_VOL_36` | D1 | 9376 | 0.6163 | 47.55% | 10452 | 0.5598 | 0.3369 | 36.23% | 0.0005 | 0.0566 | 0.0779 |
| `M_EVENT_VOL_36` | D2 | 19838 | 0.6121 | 44.71% | 14145 | 0.5477 | 0.3465 | 38.87% | 0.0095 | 0.0644 | 0.0500 |
| `M_EVENT_VOL_36` | D3 | 33416 | 0.6016 | 42.88% | 18052 | 0.5698 | 0.3946 | 42.75% | 0.0151 | 0.0318 | 0.0343 |

## 6. B0复现对账

| Metric | P4 B0 | P3R B0 reference |
| --- | ---: | ---: |
| Macro AUC | 0.5799 | 0.5799 |
| Worst fold AUC | 0.5598 | 0.5598 |
| OOF raw AUC | 0.5716 | 0.5716 |
| legacy pooled-raw Top10 | 41.22% | 41.22% |

## 7. 六个删除式消融结果

| Candidate | Decision | Macro AUC diff 95% CI | Top10 diff 95% CI | q | Net mean diff 95% CI | Worst fold | Long | Short | Non-overlap | Asset-holdout macro |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `D_NO_G1_T1_MA7` | `INCONCLUSIVE_FACTOR_ROLE` | -0.0024 [-0.0072, 0.0026] | -0.0124 [-0.0293, 0.0049] | 0.3280 | -0.0029 [-0.0060, 0.0006] | -0.0065 | -0.0048 | -0.0016 | -0.0050 | NA |
| `D_NO_G2_EVENT_GEOMETRY` | `INCONCLUSIVE_FACTOR_ROLE` | 0.0021 [-0.0040, 0.0079] | -0.0045 [-0.0150, 0.0127] | 0.8440 | -0.0007 [-0.0031, 0.0030] | -0.0041 | 0.0025 | 0.0003 | -0.0007 | NA |
| `D_NO_G3_VOLATILITY` | `INCONCLUSIVE_FACTOR_ROLE` | -0.0042 [-0.0160, 0.0084] | 0.0340 [0.0108, 0.0545] | 0.0090 | 0.0073 [0.0025, 0.0113] | -0.0058 | 0.0016 | -0.0020 | -0.0016 | NA |
| `D_NO_G4_VOLUME` | `REQUIRED_DEVELOPMENT_EVIDENCE` | -0.0035 [-0.0078, -0.0000] | -0.0138 [-0.0221, -0.0036] | 0.0090 | -0.0035 [-0.0053, -0.0012] | -0.0041 | 0.0002 | -0.0095 | -0.0028 | NA |
| `D_NO_G5_T1_MOMENTUM_LOCATION` | `INCONCLUSIVE_FACTOR_ROLE` | -0.0120 [-0.0276, 0.0052] | 0.0028 [-0.0337, 0.0426] | 0.8440 | 0.0010 [-0.0065, 0.0089] | -0.0259 | -0.0100 | -0.0191 | -0.0116 | NA |
| `D_NO_G6_T1_PATH_REGIME` | `INCONCLUSIVE_FACTOR_ROLE` | -0.0008 [-0.0058, 0.0046] | 0.0047 [-0.0103, 0.0184] | 0.7650 | 0.0011 [-0.0021, 0.0043] | -0.0068 | 0.0026 | -0.0039 | -0.0046 | NA |

## 8. 六个单组模型结果

| Candidate | Group | Feature count | Macro AUC | Worst fold AUC | Top10成功率 | Top10净均值 | Long AUC | Short AUC |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `O_G1_T1_MA7_ONLY` | `G1_T1_MA7_STATE` | 12 | 0.5396 | 0.5284 | 36.63% | 0.0069 | 0.5396 | 0.5197 |
| `O_G2_EVENT_GEOMETRY_ONLY` | `G2_EVENT_GEOMETRY` | 13 | 0.5365 | 0.5229 | 39.96% | 0.0096 | 0.5157 | 0.5455 |
| `O_G3_VOLATILITY_ONLY` | `G3_VOLATILITY_STATE` | 11 | 0.5596 | 0.5477 | 40.38% | 0.0097 | 0.5065 | 0.5887 |
| `O_G4_VOLUME_ONLY` | `G4_VOLUME_ACTIVITY` | 5 | 0.5129 | 0.4875 | 34.47% | 0.0067 | 0.4682 | 0.5435 |
| `O_G5_T1_MOMENTUM_LOCATION_ONLY` | `G5_T1_MOMENTUM_LOCATION` | 21 | 0.5616 | 0.5435 | 40.50% | 0.0138 | 0.5392 | 0.5704 |
| `O_G6_T1_PATH_REGIME_ONLY` | `G6_T1_PATH_REGIME` | 7 | 0.5338 | 0.5311 | 36.86% | 0.0095 | 0.5221 | 0.5301 |

## 9. 两个压缩模型结果

| Candidate | Decision | Macro AUC diff 95% CI | Top10 diff 95% CI | q | Net mean diff 95% CI | Worst fold | Long | Short | Non-overlap | Asset-holdout macro |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `M_EVENT_25` | `COMPRESSED_CANDIDATE_NOT_NONINFERIOR` | -0.0345 [-0.0590, -0.0073] | 0.0049 [-0.0374, 0.0432] | 0.9400 | -0.0004 [-0.0101, 0.0077] | -0.0644 | -0.0144 | -0.0502 | -0.0234 | -0.0349 |
| `M_EVENT_VOL_36` | `COMPRESSED_CANDIDATE_NOT_NONINFERIOR` | -0.0208 [-0.0412, 0.0007] | -0.0176 [-0.0655, 0.0270] | 0.7440 | -0.0049 [-0.0145, 0.0039] | -0.0347 | -0.0226 | -0.0294 | -0.0206 | -0.0212 |

## 10. fold-relative Top 10%结果

| Candidate | Top10 n | 成功率 | Uplift | 净收益均值 | 净收益中位数 | 最差fold | fold std |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `R_FULL_B0_69` | 4267 | 41.62% | 0.0935 | 0.0146 | -0.0445 | 38.02% | 0.0252 |
| `D_NO_G1_T1_MA7` | 4267 | 40.38% | 0.0811 | 0.0116 | -0.0458 | 36.89% | 0.0248 |
| `D_NO_G2_EVENT_GEOMETRY` | 4267 | 41.18% | 0.0891 | 0.0139 | -0.0446 | 38.23% | 0.0210 |
| `D_NO_G3_VOLATILITY` | 4267 | 45.02% | 0.1275 | 0.0219 | -0.0334 | 38.30% | 0.0496 |
| `D_NO_G4_VOLUME` | 4267 | 40.24% | 0.0797 | 0.0111 | -0.0468 | 35.55% | 0.0342 |
| `D_NO_G5_T1_MOMENTUM_LOCATION` | 4267 | 41.90% | 0.0963 | 0.0155 | -0.0425 | 39.36% | 0.0258 |
| `D_NO_G6_T1_PATH_REGIME` | 4267 | 42.09% | 0.0982 | 0.0157 | -0.0436 | 38.73% | 0.0238 |
| `O_G1_T1_MA7_ONLY` | 4267 | 36.63% | 0.0436 | 0.0069 | -0.0546 | 36.10% | 0.0094 |
| `O_G2_EVENT_GEOMETRY_ONLY` | 4267 | 39.96% | 0.0769 | 0.0096 | -0.0422 | 31.93% | 0.0561 |
| `O_G3_VOLATILITY_ONLY` | 4267 | 40.38% | 0.0811 | 0.0097 | -0.0422 | 30.88% | 0.0595 |
| `O_G4_VOLUME_ONLY` | 4267 | 34.47% | 0.0221 | 0.0067 | -0.0570 | 27.92% | 0.0560 |
| `O_G5_T1_MOMENTUM_LOCATION_ONLY` | 4267 | 40.50% | 0.0823 | 0.0138 | -0.0454 | 36.75% | 0.0266 |
| `O_G6_T1_PATH_REGIME_ONLY` | 4267 | 36.86% | 0.0460 | 0.0095 | -0.0490 | 34.20% | 0.0202 |
| `M_EVENT_25` | 4267 | 42.11% | 0.0985 | 0.0141 | -0.0402 | 33.46% | 0.0582 |
| `M_EVENT_VOL_36` | 4267 | 39.86% | 0.0760 | 0.0097 | -0.0456 | 36.23% | 0.0268 |

## 11. legacy pooled-raw Top 10%对账

| Candidate | Top10 n | 成功率 | Uplift | 净收益均值 | 净收益中位数 | Bottom10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `R_FULL_B0_69` | 4265 | 41.22% | 0.0895 | 0.0145 | -0.0430 | 20.24% |
| `D_NO_G1_T1_MA7` | 4265 | 39.60% | 0.0733 | 0.0110 | -0.0446 | 20.90% |
| `D_NO_G2_EVENT_GEOMETRY` | 4265 | 40.98% | 0.0872 | 0.0143 | -0.0422 | 20.17% |
| `D_NO_G3_VOLATILITY` | 4265 | 43.42% | 0.1116 | 0.0197 | -0.0365 | 23.38% |
| `D_NO_G4_VOLUME` | 4265 | 39.18% | 0.0691 | 0.0096 | -0.0462 | 20.80% |
| `D_NO_G5_T1_MOMENTUM_LOCATION` | 4265 | 40.52% | 0.0825 | 0.0141 | -0.0452 | 21.27% |
| `D_NO_G6_T1_PATH_REGIME` | 4265 | 41.55% | 0.0928 | 0.0147 | -0.0425 | 20.80% |
| `O_G1_T1_MA7_ONLY` | 4265 | 36.20% | 0.0393 | 0.0069 | -0.0536 | 26.85% |
| `O_G2_EVENT_GEOMETRY_ONLY` | 4265 | 35.69% | 0.0342 | 0.0026 | -0.0457 | 26.01% |
| `O_G3_VOLATILITY_ONLY` | 4265 | 37.42% | 0.0515 | 0.0040 | -0.0455 | 19.68% |
| `O_G4_VOLUME_ONLY` | 4265 | 33.22% | 0.0096 | 0.0033 | -0.0576 | 31.61% |
| `O_G5_T1_MOMENTUM_LOCATION_ONLY` | 4265 | 39.93% | 0.0766 | 0.0127 | -0.0446 | 23.52% |
| `O_G6_T1_PATH_REGIME_ONLY` | 4265 | 36.27% | 0.0400 | 0.0093 | -0.0507 | 27.95% |
| `M_EVENT_25` | 4265 | 38.45% | 0.0618 | 0.0079 | -0.0448 | 25.87% |
| `M_EVENT_VOL_36` | 4265 | 37.40% | 0.0513 | 0.0059 | -0.0480 | 22.26% |

## 12. 20日non-overlap结果

| Candidate | n | AUC | Top10成功率 | Top10净均值 |
| --- | ---: | ---: | ---: | ---: |
| `R_FULL_B0_69` | 15427 | 0.5671 | 38.30% | 0.0100 |
| `D_NO_G1_T1_MA7` | 15427 | 0.5620 | 37.72% | 0.0088 |
| `D_NO_G2_EVENT_GEOMETRY` | 15427 | 0.5664 | 38.11% | 0.0098 |
| `D_NO_G3_VOLATILITY` | 15427 | 0.5655 | 39.66% | 0.0123 |
| `D_NO_G4_VOLUME` | 15427 | 0.5643 | 36.55% | 0.0051 |
| `D_NO_G5_T1_MOMENTUM_LOCATION` | 15427 | 0.5555 | 36.75% | 0.0075 |
| `D_NO_G6_T1_PATH_REGIME` | 15427 | 0.5625 | 38.11% | 0.0085 |
| `O_G1_T1_MA7_ONLY` | 15427 | 0.5410 | 34.93% | 0.0048 |
| `O_G2_EVENT_GEOMETRY_ONLY` | 15427 | 0.5340 | 34.28% | 0.0005 |
| `O_G3_VOLATILITY_ONLY` | 15427 | 0.5381 | 33.83% | -0.0012 |
| `O_G4_VOLUME_ONLY` | 15427 | 0.5012 | 30.27% | -0.0017 |
| `O_G5_T1_MOMENTUM_LOCATION_ONLY` | 15427 | 0.5428 | 37.33% | 0.0077 |
| `O_G6_T1_PATH_REGIME_ONLY` | 15427 | 0.5305 | 34.74% | 0.0042 |
| `M_EVENT_25` | 15427 | 0.5437 | 37.72% | 0.0060 |
| `M_EVENT_VOL_36` | 15427 | 0.5465 | 34.41% | 0.0005 |

## 13. long/short分层

| Candidate | Stratum | n | AUC | Top10成功率 | Top10净均值 |
| --- | --- | ---: | ---: | ---: | ---: |
| `R_FULL_B0_69` | `long` | 21300 | 0.5446 | 36.15% | 0.0044 |
| `R_FULL_B0_69` | `short` | 21349 | 0.5992 | 46.14% | 0.0245 |
| `M_EVENT_25` | `long` | 21300 | 0.5302 | 35.12% | -0.0005 |
| `M_EVENT_25` | `short` | 21349 | 0.5490 | 41.31% | 0.0142 |
| `M_EVENT_VOL_36` | `long` | 21300 | 0.5220 | 34.37% | -0.0010 |
| `M_EVENT_VOL_36` | `short` | 21349 | 0.5698 | 41.08% | 0.0159 |

## 14. 年份分层

| Candidate | Stratum | n | AUC | Top10成功率 | Top10净均值 |
| --- | --- | ---: | ---: | ---: | ---: |
| `R_FULL_B0_69` | `2022` | 10452 | 0.5945 | 43.21% | 0.0185 |
| `R_FULL_B0_69` | `2023` | 14145 | 0.5598 | 38.02% | 0.0060 |
| `R_FULL_B0_69` | `2024` | 18052 | 0.5854 | 43.52% | 0.0190 |
| `M_EVENT_25` | `2022` | 10452 | 0.5300 | 33.46% | -0.0015 |
| `M_EVENT_25` | `2023` | 14145 | 0.5365 | 41.41% | 0.0116 |
| `M_EVENT_25` | `2024` | 18052 | 0.5695 | 47.67% | 0.0252 |
| `M_EVENT_VOL_36` | `2022` | 10452 | 0.5598 | 36.23% | 0.0005 |
| `M_EVENT_VOL_36` | `2023` | 14145 | 0.5477 | 38.87% | 0.0095 |
| `M_EVENT_VOL_36` | `2024` | 18052 | 0.5698 | 42.75% | 0.0151 |

## 15. 资产五组分层

| Candidate | Stratum | n | AUC | Top10成功率 | Top10净均值 |
| --- | --- | ---: | ---: | ---: | ---: |
| `R_FULL_B0_69` | `0` | 9458 | 0.5772 | 39.85% | 0.0105 |
| `R_FULL_B0_69` | `1` | 10284 | 0.5753 | 43.44% | 0.0181 |
| `R_FULL_B0_69` | `2` | 7995 | 0.5672 | 39.50% | 0.0130 |
| `R_FULL_B0_69` | `3` | 7753 | 0.5715 | 41.11% | 0.0170 |
| `R_FULL_B0_69` | `4` | 7159 | 0.5642 | 40.92% | 0.0121 |
| `M_EVENT_25` | `0` | 9458 | 0.5518 | 38.69% | 0.0123 |
| `M_EVENT_25` | `1` | 10284 | 0.5417 | 38.48% | 0.0055 |
| `M_EVENT_25` | `2` | 7995 | 0.5367 | 39.75% | 0.0100 |
| `M_EVENT_25` | `3` | 7753 | 0.5335 | 38.66% | 0.0104 |
| `M_EVENT_25` | `4` | 7159 | 0.5294 | 37.01% | 0.0020 |
| `M_EVENT_VOL_36` | `0` | 9458 | 0.5581 | 37.53% | 0.0045 |
| `M_EVENT_VOL_36` | `1` | 10284 | 0.5486 | 37.22% | 0.0053 |
| `M_EVENT_VOL_36` | `2` | 7995 | 0.5428 | 38.75% | 0.0102 |
| `M_EVENT_VOL_36` | `3` | 7753 | 0.5465 | 36.47% | 0.0058 |
| `M_EVENT_VOL_36` | `4` | 7159 | 0.5327 | 37.43% | 0.0054 |

## 16. 15单元时间×资产holdout

| Candidate | 15-unit Macro AUC | Worst unit AUC | Top10成功率 | 资产组方向翻转 |
| --- | ---: | ---: | ---: | --- |
| `D_NO_G1_T1_MA7` | 0.5770 | 0.5399 | 40.34% | `True` |
| `D_NO_G2_EVENT_GEOMETRY` | 0.5815 | 0.5499 | 40.73% | `True` |
| `D_NO_G3_VOLATILITY` | 0.5758 | 0.5406 | 44.40% | `True` |
| `D_NO_G4_VOLUME` | 0.5760 | 0.5431 | 40.67% | `True` |
| `D_NO_G5_T1_MOMENTUM_LOCATION` | 0.5670 | 0.5287 | 41.27% | `True` |
| `D_NO_G6_T1_PATH_REGIME` | 0.5782 | 0.5510 | 41.63% | `True` |
| `M_EVENT_25` | 0.5448 | 0.5146 | 40.56% | `False` |
| `M_EVENT_VOL_36` | 0.5584 | 0.5239 | 39.48% | `False` |
| `R_FULL_B0_69` | 0.5796 | 0.5417 | 41.28% | `False` |

## 17. 系数稳定性与相关性

| Group | high | same-sign coef ratio | median | max | high-corr pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| `G1_T1_MA7_STATE` | 12 | 0.9167 | 0.1230 | 1.8559 | 4 |
| `G2_EVENT_GEOMETRY` | 13 | 0.5385 | 0.1154 | 1.1930 | 3 |
| `G3_VOLATILITY_STATE` | 10 | 0.4545 | 0.2809 | 1.4578 | 14 |
| `G4_VOLUME_ACTIVITY` | 5 | 0.8000 | 0.3109 | 1.1957 | 2 |
| `G5_T1_MOMENTUM_LOCATION` | 21 | 0.6667 | 0.1073 | 0.5857 | 8 |
| `G6_T1_PATH_REGIME` | 7 | 0.5714 | 0.0438 | 0.1443 | 0 |

## 18. 训练-验证差距

| Candidate | Avg AUC gap | Avg Top10 uplift gap | Overfit folds |
| --- | ---: | ---: | --- |
| `R_FULL_B0_69` | 0.0695 | 0.1057 |  |
| `D_NO_G1_T1_MA7` | 0.0678 | 0.1122 |  |
| `D_NO_G2_EVENT_GEOMETRY` | 0.0628 | 0.1023 |  |
| `D_NO_G3_VOLATILITY` | 0.0602 | 0.0686 |  |
| `D_NO_G4_VOLUME` | 0.0707 | 0.1069 |  |
| `D_NO_G5_T1_MOMENTUM_LOCATION` | 0.0551 | 0.0572 |  |
| `D_NO_G6_T1_PATH_REGIME` | 0.0660 | 0.0888 |  |
| `O_G1_T1_MA7_ONLY` | 0.0164 | 0.0277 |  |
| `O_G2_EVENT_GEOMETRY_ONLY` | 0.0273 | 0.0339 |  |
| `O_G3_VOLATILITY_ONLY` | 0.0243 | -0.0158 |  |
| `O_G4_VOLUME_ONLY` | 0.0241 | -0.0036 |  |
| `O_G5_T1_MOMENTUM_LOCATION_ONLY` | 0.0498 | 0.0598 |  |
| `O_G6_T1_PATH_REGIME_ONLY` | 0.0169 | 0.0287 |  |
| `M_EVENT_25` | 0.0363 | 0.0291 |  |
| `M_EVENT_VOL_36` | 0.0509 | 0.0541 |  |

## 19. bootstrap置信区间与BH校正

| Candidate | Decision | Macro AUC diff 95% CI | Top10 diff 95% CI | q | Net mean diff 95% CI | Worst fold | Long | Short | Non-overlap | Asset-holdout macro |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `D_NO_G1_T1_MA7` | `INCONCLUSIVE_FACTOR_ROLE` | -0.0024 [-0.0072, 0.0026] | -0.0124 [-0.0293, 0.0049] | 0.3280 | -0.0029 [-0.0060, 0.0006] | -0.0065 | -0.0048 | -0.0016 | -0.0050 | NA |
| `D_NO_G2_EVENT_GEOMETRY` | `INCONCLUSIVE_FACTOR_ROLE` | 0.0021 [-0.0040, 0.0079] | -0.0045 [-0.0150, 0.0127] | 0.8440 | -0.0007 [-0.0031, 0.0030] | -0.0041 | 0.0025 | 0.0003 | -0.0007 | NA |
| `D_NO_G3_VOLATILITY` | `INCONCLUSIVE_FACTOR_ROLE` | -0.0042 [-0.0160, 0.0084] | 0.0340 [0.0108, 0.0545] | 0.0090 | 0.0073 [0.0025, 0.0113] | -0.0058 | 0.0016 | -0.0020 | -0.0016 | NA |
| `D_NO_G4_VOLUME` | `REQUIRED_DEVELOPMENT_EVIDENCE` | -0.0035 [-0.0078, -0.0000] | -0.0138 [-0.0221, -0.0036] | 0.0090 | -0.0035 [-0.0053, -0.0012] | -0.0041 | 0.0002 | -0.0095 | -0.0028 | NA |
| `D_NO_G5_T1_MOMENTUM_LOCATION` | `INCONCLUSIVE_FACTOR_ROLE` | -0.0120 [-0.0276, 0.0052] | 0.0028 [-0.0337, 0.0426] | 0.8440 | 0.0010 [-0.0065, 0.0089] | -0.0259 | -0.0100 | -0.0191 | -0.0116 | NA |
| `D_NO_G6_T1_PATH_REGIME` | `INCONCLUSIVE_FACTOR_ROLE` | -0.0008 [-0.0058, 0.0046] | 0.0047 [-0.0103, 0.0184] | 0.7650 | 0.0011 [-0.0021, 0.0043] | -0.0068 | 0.0026 | -0.0039 | -0.0046 | NA |
| `M_EVENT_25` | `COMPRESSED_CANDIDATE_NOT_NONINFERIOR` | -0.0345 [-0.0590, -0.0073] | 0.0049 [-0.0374, 0.0432] | 0.9400 | -0.0004 [-0.0101, 0.0077] | -0.0644 | -0.0144 | -0.0502 | -0.0234 | -0.0349 |
| `M_EVENT_VOL_36` | `COMPRESSED_CANDIDATE_NOT_NONINFERIOR` | -0.0208 [-0.0412, 0.0007] | -0.0176 [-0.0655, 0.0270] | 0.7440 | -0.0049 [-0.0145, 0.0039] | -0.0347 | -0.0226 | -0.0294 | -0.0206 | -0.0212 |

## 20. 因子角色裁决

| Group | Decision |
| --- | --- |
| `G1_T1_MA7_STATE` | `INCONCLUSIVE_FACTOR_ROLE` |
| `G2_EVENT_GEOMETRY` | `INCONCLUSIVE_FACTOR_ROLE` |
| `G3_VOLATILITY_STATE` | `INCONCLUSIVE_FACTOR_ROLE` |
| `G4_VOLUME_ACTIVITY` | `REQUIRED_DEVELOPMENT_EVIDENCE` |
| `G5_T1_MOMENTUM_LOCATION` | `INCONCLUSIVE_FACTOR_ROLE` |
| `G6_T1_PATH_REGIME` | `INCONCLUSIVE_FACTOR_ROLE` |

## 21. 压缩模型裁决

| Candidate | Decision | Gate checks |
| --- | --- | --- |
| `M_EVENT_25` | `COMPRESSED_CANDIDATE_NOT_NONINFERIOR` | `{"asset_holdout_not_obviously_worse": false, "long_short_auc": false, "macro_auc_ci_low": false, "non_overlap_auc": false, "top10_net_mean_ci_low": false, "top10_success_ci_low": false, "train_validation_gap": true, "two_of_three_years_top10_not_below_b0": true, "worst_fold_auc": false}` |
| `M_EVENT_VOL_36` | `COMPRESSED_CANDIDATE_NOT_NONINFERIOR` | `{"asset_holdout_not_obviously_worse": false, "long_short_auc": false, "macro_auc_ci_low": false, "non_overlap_auc": false, "top10_net_mean_ci_low": false, "top10_success_ci_low": false, "train_validation_gap": true, "two_of_three_years_top10_not_below_b0": false, "worst_fold_auc": false}` |

## 22. 为什么本轮不是策略

- P4 只给 MA7 穿越事件打概率分，不产生持仓、仓位、组合调度、权益曲线、年化收益或 Sharpe。
- 2022-2024 已经被 P2/P3R 多次查看，只能视为开发期 walk-forward 证据。
- 即使压缩模型通过，也只是供未来全新 OOS 验证的候选，不是 promotion、dry-run 或 live-ready。

## 23. 后续真正新OOS要求

- 需要等待 2026-06-30 后此前未参与特征设计、候选冻结或模型选择的新 donor 数据。
- 新 OOS 必须先复用本 P4 锁定的候选、因子组、Top10 fold 内排名、校准和非劣门槛；不能用 2024 单年或本次结果再调结构。
