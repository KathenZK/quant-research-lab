# BIN-1D-MA7-CER P0 无方向价格扩张事件审计

5D median max excursion: Cross = 1.7136; Non-cross = 1.6851; Difference = 0.0284; 95% CI = [0.0082, 0.0549]
5D future range: Cross = 2.4776; Non-cross = 2.4984; Difference = -0.0208; 95% CI = [-0.0584, 0.0138]
5D realized-vol expansion ratio: Cross = 1.2693; Non-cross = 1.2822; Difference = -0.0129; 95% CI = [-0.0443, 0.0124]
5D path efficiency: Cross = 0.4584; Non-cross = 0.4580; Difference = 0.0004; 95% CI = [-0.0033, 0.0041]

需要结合主 5D outcome 与 lagging 对照一起判断；单一曲线不能单独改写预注册裁决。

全局裁决：`NO_EXPANSION_EDGE`

- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- `research_id`：`BIN-1D-MA7-CER-P0-2026-09-04`
- 合同锁：`FROZEN_BEFORE_P0_EXPANSION_OUTPUT_READ`
- data/event parity：`True`
- 官方 Cross N：101029
- 2025+ 未纳入官方样本的额外 probe：58（不进入主分析）
- 5D abs terminal: Cross = 1.1223; Non-cross = 1.1263; Difference = -0.0040; 95% CI = [-0.0244, 0.0152]

## 主 5D outcome（相对 DATE_MATCHED_NON_CROSS）

| Metric | Cross mean | Non-cross mean | Δ mean | Δ median | 95% CI (Δ mean) | BH q |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| max_abs_excursion | 2.0126 | 2.0179 | -0.0053 | 0.0284 | [-0.0391, 0.0266] | 0.8276 |
| future_range | 2.4776 | 2.4984 | -0.0208 | 0.0131 | [-0.0584, 0.0138] | 0.8276 |
| vol_expansion_ratio | 1.2693 | 1.2822 | -0.0129 | 0.0117 | [-0.0443, 0.0124] | 0.8276 |
| path_efficiency | 0.4584 | 0.4580 | 0.0004 | 0.0021 | [-0.0033, 0.0041] | 0.8276 |
| abs_terminal | 1.1223 | 1.1263 | -0.0040 | 0.0253 | [-0.0244, 0.0152] | 0.8276 |

## Pre vs post

- T-3→T0 range Δ mean = -0.2383
- T0 day range Δ mean = 0.1006
- T+1→T+5 range Δ mean = -0.0208
- 5D post/pre range ratio Cross = 1.4073 vs non-cross 1.2338
- 5D post/pre vol ratio Cross = 1.2693 vs non-cross 1.2822
- 解读：Cross 的 post/pre range 比值更高，主要来自 T-3→T0 相对更安静（Δ=-0.238 ATR），不是未来 5D range 更大。

## Event-time

事件时间 T-3..T0 Δ range≈-0.0164，T+1..T+5 Δ range≈-0.0117。

## 年份

| Period | N | Δ mean excursion | Δ mean range |
| --- | ---: | ---: | ---: |
| full | 101009 | -0.0053 | -0.0208 |
| pre_2022 | 9894 | -0.0964 | -0.1212 |
| pre_2025 | 54117 | -0.0208 | -0.0456 |
| 2022 | 10452 | 0.0363 | 0.0148 |
| 2023 | 14145 | -0.0672 | -0.0972 |
| 2024 | 19626 | 0.0202 | -0.0026 |
| 2025 | 32111 | 0.0312 | 0.0288 |
| 2026 | 14781 | -0.0277 | -0.0374 |

## Up / down Cross（描述性）

- up-cross 5D max abs excursion mean = 2.0884 (N=50651)
- down-cross 5D max abs excursion mean = 1.9361 (N=50378)
不得解释为方向预测。

## 其他 placebo

- same-asset exact Δ mean excursion = 0.0168
- vol-matched Δ mean excursion = -0.0299 (coverage 0.9984)
- liq+vol matched Δ mean excursion = -0.0340 (coverage 0.9925)

## Horizon 敏感性（次要，不得替代 5D）

| Horizon | Δ mean excursion | Δ mean range | Δ mean vol ratio | Δ mean efficiency | Δ mean terminal |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1D | -0.0101 | -0.0164 | NA | NA | -0.0068 |
| 3D | -0.0015 | -0.0130 | -0.1481 | 0.0011 | 0.0007 |
| 5D | -0.0053 | -0.0208 | -0.0129 | 0.0004 | -0.0040 |
| 10D | 0.0093 | -0.0108 | 0.0084 | 0.0012 | 0.0055 |
| 20D | -0.0385 | -0.0522 | 0.0061 | -0.0026 | -0.0401 |

## 市场状态（描述性，不寻优）

| State | N | Δ mean excursion |
| --- | ---: | ---: |
| BULL | 28024 | -0.1135 |
| BEAR | 45187 | 0.0329 |
| MIXED | 27798 | 0.0417 |

## 可以确认 / 不能确认

- 可以确认：官方 MA7 Cross identity 可复现；相对同日 non-cross，5D 预注册无方向 expansion 均值增量的 95% 块 bootstrap CI 覆盖 0，且 median 增量远小于 0.20 ATR 物质性门槛。
- 不能确认：不能确认任何交易策略、方向预测、ML 价值，或把 T0 当日略高的 range 解释成未来扩张。
- P1：STOP。不要进入 P1，并停止整条 MA7 研究路线。

## 图表

- [binance_1d_ma7_cer_p0_chart_01_max_abs_excursion.svg](../artifacts/binance_1d_ma7_cer_p0_chart_01_max_abs_excursion.svg)
- [binance_1d_ma7_cer_p0_chart_02_future_range.svg](../artifacts/binance_1d_ma7_cer_p0_chart_02_future_range.svg)
- [binance_1d_ma7_cer_p0_chart_03_realized_vol_expansion.svg](../artifacts/binance_1d_ma7_cer_p0_chart_03_realized_vol_expansion.svg)
- [binance_1d_ma7_cer_p0_chart_04_path_efficiency.svg](../artifacts/binance_1d_ma7_cer_p0_chart_04_path_efficiency.svg)
- [binance_1d_ma7_cer_p0_chart_05_terminal_displacement.svg](../artifacts/binance_1d_ma7_cer_p0_chart_05_terminal_displacement.svg)
- [binance_1d_ma7_cer_p0_chart_06_event_time_volatility.svg](../artifacts/binance_1d_ma7_cer_p0_chart_06_event_time_volatility.svg)
- [binance_1d_ma7_cer_p0_chart_07_event_time_range.svg](../artifacts/binance_1d_ma7_cer_p0_chart_07_event_time_range.svg)
- [binance_1d_ma7_cer_p0_chart_08_prepost_expansion_ratio.svg](../artifacts/binance_1d_ma7_cer_p0_chart_08_prepost_expansion_ratio.svg)
- [binance_1d_ma7_cer_p0_chart_09_yearly_effect.svg](../artifacts/binance_1d_ma7_cer_p0_chart_09_yearly_effect.svg)
- [binance_1d_ma7_cer_p0_chart_10_up_down_cross.svg](../artifacts/binance_1d_ma7_cer_p0_chart_10_up_down_cross.svg)

本轮未修改旧 `BIN-1D-MA7-CTP` 产物或 verdict。
