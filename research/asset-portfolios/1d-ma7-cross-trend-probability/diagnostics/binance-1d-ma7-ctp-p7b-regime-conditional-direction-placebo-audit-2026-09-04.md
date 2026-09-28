# BIN-1D-MA7-CTP P7B 市场状态条件下 MA7 穿越方向安慰剂审计

BULL_UP: Real success = 35.8026%
Same-cross random = 33.2158%
Cross directional edge = +2.5867 pp

Bull non-cross long = 33.2347%
Bull non-cross random = 31.9115%
Bull regime directional drift = +1.3232 pp

BULL_UP incremental MA7 edge = +2.5867 pp - +1.3232 pp = +1.2635 pp
95% CI = [-0.1985 pp, +2.7274 pp]

BEAR_DOWN: Real success = 29.7956%
Same-cross random = 28.6963%
Cross directional edge = +1.0993 pp

Bear non-cross short = 29.0388%
Bear non-cross random = 27.9347%
Bear regime directional drift = +1.1041 pp

BEAR_DOWN incremental MA7 edge = +1.0993 pp - +1.1041 pp = -0.0048 pp
95% CI = [-0.9747 pp, +0.9516 pp]

REGIME_ALIGNMENT_EFFECT = -0.3228 pp
95% CI = [-1.7477 pp, +1.1221 pp]

一句话：表面上的格子差异主要来自市场本身的方向漂移，不是 MA7 增量。

- 状态：`explore / diagnostic-only / placebo-audit / not promoted / not live-ready`
- `research_id`：`BIN-1D-MA7-CTP-P7B-2026-09-04`
- 合同锁：`FROZEN_BEFORE_P7B_REGIME_OUTCOME_READ`
- 全局裁决：`REGIME_DRIFT_EXPLAINS_APPARENT_EDGE`
- 本轮是已经观察过总体 P7A 与部分 P6 六格历史后的 targeted diagnostic，不是新盲测。
- 禁止把 Bull 本身的 Long drift 或 Bear 本身的 Short drift 算成 MA7 增量。

## 六格完整结果

| Regime | Cross | N | Real | Same-Cross Random | Direction Edge | Non-Cross Same-Side | Regime Drift | Incremental MA7 Edge |
| ------ | ----- | -: | ---: | ----------------: | -------------: | ------------------: | -----------: | -------------------: |
| BULL | UP | 14328 | 35.8026% | 33.2158% | +2.5867 pp | 33.2347% | +1.3232 pp | +1.2635 pp |
| BULL | DOWN | 13704 | 29.7715% | 31.2240% | -1.4524 pp | 29.1104% | -1.6276 pp | +0.1752 pp |
| BEAR | UP | 22542 | 30.0009% | 27.8621% | +2.1388 pp | 27.4351% | +0.9440 pp | +1.1948 pp |
| BEAR | DOWN | 22655 | 29.7956% | 28.6963% | +1.0993 pp | 29.0388% | +1.1041 pp | -0.0048 pp |
| MIXED | UP | 13781 | 33.4373% | 33.8074% | -0.3701 pp | 32.0851% | -0.7282 pp | +0.3581 pp |
| MIXED | DOWN | 14019 | 35.4355% | 34.7150% | +0.7206 pp | 34.4831% | +1.6119 pp | -0.8913 pp |

## 主检验

- BULL_UP incremental +1.2635 pp，p=0.0900，BH q=0.2699，CI [-0.1985 pp, +2.7274 pp]。
- BEAR_DOWN incremental -0.0048 pp，p=0.9765，BH q=0.9765，CI [-0.9747 pp, +0.9516 pp]。
- REGIME_ALIGNMENT_EFFECT -0.3228 pp，p=0.7046，BH q=0.9765，CI [-1.7477 pp, +1.1221 pp]。
- BEAR_DOWN N=22655，dates=841，CI width=+1.9263 pp；BULL_UP N=14328，dates=657，CI width=+2.9259 pp。

## 年份

| Period | BULL_UP inc | BEAR_DOWN inc | Alignment |
| --- | ---: | ---: | ---: |
| full | +1.2635 pp | -0.0048 pp | -0.3228 pp |
| pre_2022 | +4.4071 pp | +0.7294 pp | +1.5131 pp |
| 2022 | +2.3150 pp | -1.2458 pp | +0.1544 pp |
| 2023 | +2.0108 pp | +1.6777 pp | +1.8953 pp |
| 2024 | +1.5670 pp | -0.8854 pp | -0.1073 pp |
| 2025 `ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS` | -2.2989 pp | +0.5263 pp | -2.3036 pp |
| 2026 `ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS` | +0.6428 pp | -0.5265 pp | -0.2616 pp |
| 2025+ `ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS` | -0.8988 pp | +0.2580 pp | -1.6547 pp |

## Mixed 与反趋势 Cross

- MIXED_UP incremental +0.3581 pp（N=13781）。
- MIXED_DOWN incremental -0.8913 pp（N=14019）。
- 反趋势 BULL_DOWN incremental +0.1752 pp；BEAR_UP incremental +1.1948 pp。

## Vol/liquidity matched

- BULL_UP matched incremental +1.1769 pp，match rate 99.0578%。
- BEAR_DOWN matched incremental +0.0773 pp，match rate 98.7729%。
- Alignment matched -0.1947 pp。

## 当前证据可以确认什么 / 不能确认什么

- 可以确认：在 P6 冻结 BULL/BEAR/MIXED 与 P7A canonical 标签下，六格 directional edge、regime drift 与 incremental MA7 edge 的分解；全局裁决 `REGIME_DRIFT_EXPLAINS_APPARENT_EDGE`。
- 不能确认：可交易策略、账户收益、新 OOS、live-ready，或把 Bull/Bear 本身的同侧漂移写成 MA7 预测价值。

## 图表

- [binance_1d_ma7_ctp_p7b_chart_01_six_grid_real_vs_random.svg](../artifacts/binance_1d_ma7_ctp_p7b_chart_01_six_grid_real_vs_random.svg)
- [binance_1d_ma7_ctp_p7b_chart_02_six_grid_directional_edge.svg](../artifacts/binance_1d_ma7_ctp_p7b_chart_02_six_grid_directional_edge.svg)
- [binance_1d_ma7_ctp_p7b_chart_03_six_grid_regime_drift.svg](../artifacts/binance_1d_ma7_ctp_p7b_chart_03_six_grid_regime_drift.svg)
- [binance_1d_ma7_ctp_p7b_chart_04_six_grid_incremental_edge.svg](../artifacts/binance_1d_ma7_ctp_p7b_chart_04_six_grid_incremental_edge.svg)
- [binance_1d_ma7_ctp_p7b_chart_05_bull_up_decomposition.svg](../artifacts/binance_1d_ma7_ctp_p7b_chart_05_bull_up_decomposition.svg)
- [binance_1d_ma7_ctp_p7b_chart_06_bear_down_decomposition.svg](../artifacts/binance_1d_ma7_ctp_p7b_chart_06_bear_down_decomposition.svg)
- [binance_1d_ma7_ctp_p7b_chart_07_yearly_bull_up_edge.svg](../artifacts/binance_1d_ma7_ctp_p7b_chart_07_yearly_bull_up_edge.svg)
- [binance_1d_ma7_ctp_p7b_chart_08_yearly_bear_down_edge.svg](../artifacts/binance_1d_ma7_ctp_p7b_chart_08_yearly_bear_down_edge.svg)
- [binance_1d_ma7_ctp_p7b_chart_09_aligned_vs_counter.svg](../artifacts/binance_1d_ma7_ctp_p7b_chart_09_aligned_vs_counter.svg)
- [binance_1d_ma7_ctp_p7b_chart_10_breadth_bins.svg](../artifacts/binance_1d_ma7_ctp_p7b_chart_10_breadth_bins.svg)
- [binance_1d_ma7_ctp_p7b_chart_11_leave_one_month_out.svg](../artifacts/binance_1d_ma7_ctp_p7b_chart_11_leave_one_month_out.svg)
- [binance_1d_ma7_ctp_p7b_chart_12_vol_liq_matched.svg](../artifacts/binance_1d_ma7_ctp_p7b_chart_12_vol_liq_matched.svg)

## 产物

- [合同](../specs/binance-1d-ma7-ctp-p7b-regime-conditional-direction-placebo-audit-2026-09-04.md)
- [summary](../artifacts/binance_1d_ma7_ctp_p7b_summary.json)
- [manifest](../artifacts/binance_1d_ma7_ctp_p7b_manifest.json)
- [implementation audit](binance-1d-ma7-ctp-p7b-implementation-audit-2026-09-04.md)
- [deferred registration](binance-1d-ma7-ctp-p7b-deferred-registration-2026-09-04.md)

本轮未修改 family README、core ledger、decision log 或顶层索引。

