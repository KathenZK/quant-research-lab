# BIN-1D-MA7-CTP P7A 安慰剂基础成功率与屏障几何归因审计

Real MA7 success rate = 31.9700%

Same-cross asset-date random-side expectation = 31.0272%

Date-matched non-cross random-side expectation = 29.9074%

MA7 directional edge = 31.9700% - 31.0272% = +0.9428 pp

Cross movement effect = 31.0272% - 29.9074% = +1.1198 pp

原来看到的约 30% 成功率，主要来自 **barrier/base-rate**（同日 non-cross random-side = 29.9074%）。Cross movement effect 为 +1.1198 pp；MA7 directional edge 为 +0.9428 pp，其 95% 块 bootstrap CI 覆盖 0，因此不能把约 30% 写成 MA7 方向的趋势预测概率。全局裁决 `CROSS_MOVEMENT_EFFECT_WITHOUT_DIRECTIONAL_EDGE`。

- 状态：`explore / diagnostic-only / placebo-audit / not promoted / not live-ready`
- `research_id`：`BIN-1D-MA7-CTP-P7A-2026-09-04`
- 合同锁：`FROZEN_BEFORE_P7A_PLACEBO_OUTPUT_READ`
- 本轮是与 P7 并行的独立 sidecar diagnostic，未读取 P7 产物，不训练模型。

## 主表

| Group | Success Rate | vs Non-Cross Random | Net Mean | Net Median | Effective N |
| ---------------------------------------------- | -----------: | ------------------: | -------: | ---------: | ----------: |
| REAL_MA7_CROSS | 31.9700% | +2.0626 pp | 0.001362 | -0.061272 | 101029 |
| SAME_CROSS_ASSET_DATE_RANDOM_SIDE_EXPECTATION | 31.0272% | +1.1198 pp | -0.000505 | nan | 101029 |
| DATE_MATCHED_ELIGIBLE_RANDOM_SIDE_EXPECTATION | 30.5406% | +0.6332 pp | -0.001181 | nan | 101029 |
| DATE_MATCHED_NON_CROSS_RANDOM_SIDE_EXPECTATION | 29.9074% | +0.0000 pp | -0.002024 | nan | 101029 |
| DATE_MATCHED_NON_CROSS_1D_MOMENTUM | 30.6121% | +0.7046 pp | -0.000753 | nan | 101029 |
| DATE_MATCHED_NON_CROSS_MA7_SIDE | 29.8509% | -0.0566 pp | -0.001556 | nan | 101029 |

Barrier / non-cross random base rate = 29.9074%

Cross movement effect = +1.1198 pp

MA7 directional edge = +0.9428 pp

Observed real MA7 rate = 31.9700%

## 理论 sanity check

连续零漂移对称 Brownian motion 下 `P(hit +2 first vs -1) = 1/3 ≈ 33.333%`。这不是真实 crypto placebo。本轮 empirical non-cross random-side base rate 见上表，与 33.33% 的差不得被解释成 MA7 信息。

## 主检验（28 日块 bootstrap）

- Directional edge +0.9428 pp，95% CI [-0.0874 pp, +1.9926 pp]，bootstrap mean +0.9406 pp。
- Cross movement +1.1198 pp，95% CI [+0.7655 pp, +1.4515 pp]。
- Total vs non-cross +2.0626 pp，95% CI [+0.9249 pp, +3.1752 pp]。
- Bonferroni α = 0.0167；BH q 见 summary JSON。

## Long / Short

- REAL LONG success 32.5739%（N=50651），相对同日反方向 short counterfactual +3.1549 pp。
- REAL SHORT success 31.3629%（N=50378），相对同日反方向 long counterfactual +0.6094 pp。

## 年度

| Period | N | Real MA7 | Same-cross RS | Non-cross RS | Edge | Movement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| full | 101029 | 31.9700% | 31.0272% | 29.9074% | +0.9428 pp | +1.1198 pp |
| pre_2025 | 54137 | 32.1906% | 30.8495% | 29.9528% | +1.3410 pp | +0.8967 pp |
| 2022 | 10452 | 30.0038% | 29.3006% | 28.9563% | +0.7032 pp | +0.3444 pp |
| 2023 | 14145 | 30.8307% | 30.4065% | 30.0109% | +0.4242 pp | +0.3956 pp |
| 2024 | 19626 | 33.5983% | 31.6468% | 29.9217% | +1.9515 pp | +1.7251 pp |
| 2025 | 32111 | 32.2849% | 31.7710% | 30.0523% | +0.5138 pp | +1.7188 pp |
| 2026 | 14781 | 30.4783% | 30.0622% | 29.4264% | +0.4161 pp | +0.6358 pp |
| 2025+ | 46892 | 31.7154% | 31.2324% | 29.8550% | +0.4830 pp | +1.3774 pp |

## 屏障敏感性

| TP | SL | Real MA7 | Same-Cross Random Side | Non-Cross Random Side | Directional Edge | Cross Movement Effect |
| -: | -: | -------: | ---------------------: | --------------------: | ---------------: | --------------------: |
| 1.0 | 1.0 | 50.2212% | 49.2091% | 48.6650% | +1.0121 pp | +0.5441 pp |
| 1.5 | 1.0 | 39.7975% | 38.7329% | 37.7496% | +1.0645 pp | +0.9833 pp |
| 2.0 | 1.0 | 31.9700% | 31.0272% | 29.9074% | +0.9428 pp | +1.1198 pp |
| 2.5 | 1.0 | 25.5857% | 24.8869% | 23.8919% | +0.6988 pp | +0.9950 pp |
| 3.0 | 1.0 | 20.4624% | 19.9364% | 19.1968% | +0.5261 pp | +0.7396 pp |
| 2.0 | 0.5 | 20.3892% | 19.8715% | 18.9454% | +0.5177 pp | +0.9262 pp |
| 2.0 | 1.5 | 37.8921% | 36.8751% | 36.0131% | +1.0170 pp | +0.8619 pp |
| 2.0 | 2.0 | 41.0605% | 40.1320% | 39.4302% | +0.9284 pp | +0.7018 pp |

## Timeout 敏感性

| Horizon | Real MA7 | Same-cross RS | Non-cross RS | Fav-first | Adv-first | Ambiguous | Timeout | Net mean | N |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5D | 15.6797% | 14.9898% | 14.6492% | 15.6797% | 40.1657% | 0.0257% | 44.1289% | -0.000708 | 101029 |
| 10D | 25.4788% | 24.6043% | 23.5651% | 25.4788% | 53.1679% | 0.0366% | 21.3167% | 0.001664 | 101029 |
| 20D | 31.9700% | 31.0272% | 29.9074% | 31.9700% | 60.8122% | 0.0436% | 7.1742% | 0.001463 | 101029 |
| 40D | 34.3958% | 33.6322% | 32.5565% | 34.3958% | 63.8194% | 0.0466% | 1.7382% | 0.001106 | 98666 |

## 预注册研究问题

1. 完全不利用 MA7 时，empirical success base rate（同日 non-cross random-side）为 29.9074%。

2. 是：该 empirical placebo 为 29.9074%，落在约 30%～33% 附近。

3. 理论 Brownian 33.33% 与 empirical non-cross placebo 相差 -3.4259 pp。不得用理论值替代实证。

4. 真实 MA7 31.9700% 中，29.9074% 这一层可归因于屏障/市场路径 base rate；其余为 movement +1.1198 pp 与 direction +0.9428 pp。

5. 同一 Cross asset-date 上随机 Long/Short 的精确期望成功率为 31.0272%。

6. 真实 MA7 方向相对随机方向的差为 +0.9428 pp。裁决 `CROSS_MOVEMENT_EFFECT_WITHOUT_DIRECTIONAL_EDGE`。

7. Cross asset-date 相对同日 non-cross 的 movement effect 为 +1.1198 pp。

8. MA7 的增量结构：timing/movement +1.1198 pp，direction +0.9428 pp。

9. 相对最简单 1D momentum：MA7 31.9700% vs momentum 30.6121%，差 +1.3580 pp。

10. 相对普通 MA7-side rule：MA7 31.9700% vs MA7-side 29.8509%，差 +2.1192 pp。

11. LONG 32.5739%，SHORT 31.3629%；相对反方向 counterfactual 分别为 +3.1549 pp 与 +0.6094 pp。

12. 2022–2026 directional edge：2022:+0.7032 pp, 2023:+0.4242 pp, 2024:+1.9515 pp, 2025:+0.5138 pp, 2026:+0.4161 pp。

13. 屏障从 1:1 改到 3:1 时，success rate 主要随 TP/SL 几何变化，见敏感性表；directional edge 是否接近 0 以该表为准。

14. horizon 从 5D 到 40D 的变化见 timeout 表；用于判断是否趋近屏障几何基础概率。

15. “MA7 穿越后约有 30% 的概率形成趋势”不应再作为无条件表述；应改为标签正样本率相对 placebo 的分解。

16. 在下一开盘进入、+2 ATR/-1 ATR、最长 20 日 first-hit 标签定义下，MA7 Cross 事件的 positive rate 约为 31.9700%；同日期 non-cross random-side empirical base rate 为 29.9074%，因此 MA7 Cross 相对于 placebo 的总增量为 +2.0626 pp，其中 directional increment 为 +0.9428 pp。

## 当前证据可以确认什么 / 不能确认什么

- 可以确认：在 P0R canonical `+2/-1/20D` 标签下，empirical placebo 与真实 MA7 的三层分解；全局裁决 `CROSS_MOVEMENT_EFFECT_WITHOUT_DIRECTIONAL_EDGE`。
- 不能确认：可交易策略、账户收益、新 OOS、live-ready、最优 TP/SL，或把 label positive rate 直接叫做趋势概率（除非 directional edge 被支持）。

## 图表

- [binance_1d_ma7_ctp_p7a_chart_01_base_rate_decomposition.svg](../artifacts/binance_1d_ma7_ctp_p7a_chart_01_base_rate_decomposition.svg)
- [binance_1d_ma7_ctp_p7a_chart_02_yearly_rates.svg](../artifacts/binance_1d_ma7_ctp_p7a_chart_02_yearly_rates.svg)
- [binance_1d_ma7_ctp_p7a_chart_03_directional_edge_by_year.svg](../artifacts/binance_1d_ma7_ctp_p7a_chart_03_directional_edge_by_year.svg)
- [binance_1d_ma7_ctp_p7a_chart_04_cross_movement_by_year.svg](../artifacts/binance_1d_ma7_ctp_p7a_chart_04_cross_movement_by_year.svg)
- [binance_1d_ma7_ctp_p7a_chart_05_barrier_geometry_sensitivity.svg](../artifacts/binance_1d_ma7_ctp_p7a_chart_05_barrier_geometry_sensitivity.svg)
- [binance_1d_ma7_ctp_p7a_chart_06_timeout_sensitivity.svg](../artifacts/binance_1d_ma7_ctp_p7a_chart_06_timeout_sensitivity.svg)
- [binance_1d_ma7_ctp_p7a_chart_07_long_short.svg](../artifacts/binance_1d_ma7_ctp_p7a_chart_07_long_short.svg)
- [binance_1d_ma7_ctp_p7a_chart_08_monte_carlo_validation.svg](../artifacts/binance_1d_ma7_ctp_p7a_chart_08_monte_carlo_validation.svg)

## 产物

- [合同](../specs/binance-1d-ma7-ctp-p7a-placebo-base-rate-audit-contract-2026-09-04.md)
- [summary](../artifacts/binance_1d_ma7_ctp_p7a_summary.json)
- [manifest](../artifacts/binance_1d_ma7_ctp_p7a_manifest.json)
- [implementation audit](binance-1d-ma7-ctp-p7a-implementation-audit-2026-09-04.md)
- [deferred registration](binance-1d-ma7-ctp-p7a-deferred-registration-2026-09-04.md)

本轮未修改 family README、core ledger、decision log 或顶层索引。
