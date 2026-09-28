# BIN-1D-CATL-P0 数据质量报告

- Family：`Binance-1D-Cross-Asset-Trend-Lifecycle`（`BIN-1D-CATL`）
- 数据截断：`2026-05-31 00:00:00+00:00`；最后特征日：`2026-05-30 00:00:00+00:00`
- 价格源：normalized Binance perp `15m` closed K；四根 `15m` 聚合闭合 `1h`，24 根连续 `1h` 聚合完整 UTC 日。
- `holdout_read=false`；HYPE 最大特征日：`2026-05-30 00:00:00+00:00`。
- P0 裁决：`DATASET_READY_FOR_MODELING_RESEARCH`；状态保持 `explore / diagnostic-only / not promoted / not live-ready`。

## 覆盖

- 历史资产数：`733`。
- Asset-Day 行数：`564805`；P0 tradable marker 行数：`481586`。
- 每日 point-in-time universe：最小 `0`，中位 `146`，最大 `542`。
- 单资产行数：最小 `1`，中位 `536`，最大 `2456`。

## 质量边界

- funding 缺失日比例：`4.43%`；缺失时净收益只用已存在 funding 记录，报告保留缺失边界。
- OI 历史点位覆盖本轮未确认，不纳入 P0 特征。
- `complete_day` 只接受 24 根完整 `1h`；每根 `1h` 必须由 4 根闭合连续 `15m` 聚合。
- 资产资格在标签计算前冻结为 `tradable_marker_p0`，没有按标签表现修改流动性、上市年龄或连续性条件。

## 特征缺失率 Top 30

| 字段 | 缺失率 |
| --- | ---: |
| `ma60_slope_accel_5d` | 14.82% |
| `ma60_slope_change_3d` | 14.63% |
| `ma60_slope_5d_atr` | 13.80% |
| `ma60_slope_3d_atr` | 13.60% |
| `path_efficiency_60d` | 13.40% |
| `ma60_slope_1d_atr` | 13.40% |
| `close_ma60_dist_atr` | 13.30% |
| `distance_to_high_60d_atr` | 13.29% |
| `range_pos_60d` | 13.28% |
| `distance_to_low_60d_atr` | 13.28% |
| `days_since_ma60_cross` | 11.37% |
| `ma30_slope_accel_5d` | 11.21% |
| `ma30_slope_change_3d` | 11.04% |
| `ma30_slope_5d_atr` | 10.80% |
| `ma30_slope_3d_atr` | 10.60% |
| `quote_volume_to_30d` | 10.47% |
| `path_efficiency_30d` | 10.41% |
| `ma30_slope_1d_atr` | 10.41% |
| `close_ma30_dist_atr` | 10.30% |
| `distance_to_high_30d_atr` | 10.28% |
| `atr14_to_atr30` | 10.28% |
| `distance_to_low_30d_atr` | 10.28% |
| `volume_to_30d` | 10.28% |
| `atr7_to_atr30` | 10.28% |
| `range_pos_30d` | 10.28% |
| `ma14_slope_accel_5d` | 9.30% |
| `ma14_slope_5d_atr` | 9.19% |
| `ma7_slope_accel_5d` | 9.17% |
| `ma14_slope_change_3d` | 9.17% |
| `ma7_slope_change_3d` | 9.04% |

## 隔离检查

- HYPE cutoff 之后特征行：`0`。
- 未读取 HYPE validation 预测、validation 交易路径或后 81 日验证产物。
- 所有标签窗口不足的 landmark 均标记为 incomplete，不向 `2026-05-31` 之后补未来路径。
