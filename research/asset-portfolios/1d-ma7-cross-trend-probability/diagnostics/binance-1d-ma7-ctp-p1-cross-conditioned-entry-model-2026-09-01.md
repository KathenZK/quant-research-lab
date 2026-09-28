# BIN-1D-MA7-CTP P1：MA7 穿越事件入场价值模型

> 2026-09-01 08:10:21.592450+00:00。状态：`explore / diagnostic-only / not promoted / not live-ready`。
> 2025+ 是 `model-unseen / hypothesis-revealed historical test`，不是严格盲测。
> 本轮没有读取 HYPE、没有训练退出模型、不是策略、not live-ready。

## 裁决

**UNSTABLE_MA7_EVENT_SIGNAL** / `explore / diagnostic-only / not promoted / not live-ready`

- 确认只训练了真实 MA7 穿越事件：`101187` 行，非穿越 0 行。
- HYPE 行数：输入 `0`，OOF `0`，历史测试 `0`。
- HYPER 保留：`77` 条事件。

## 事件样本

- 事件 `101187`，资产 `655`，多头 `50738`，空头 `50449`。
- 区间 `2019-11-27 00:00:00+00:00` 至 `2026-05-10 00:00:00+00:00`；2025 年前 `54137`。

## D1/D2/D3 训练与验证对照

| Head | Fold | Train n | Train 正例率 | Train AUC | Val n | Val 正例率 | Val AUC | AUC 差 | Uplift 差 | 过拟合标记 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| LONG_HEAD | D1 | 4664 | 39.37% | 0.8828 | 5252 | 24.83% | 0.6146 | 0.2681 | 0.4047 | SEVERE_OVERFIT_WARNING |
| LONG_HEAD | D2 | 9941 | 32.27% | 0.7647 | 7063 | 34.35% | 0.5516 | 0.2131 | 0.3856 | SEVERE_OVERFIT_WARNING |
| LONG_HEAD | D3 | 16771 | 32.92% | 0.6728 | 9786 | 33.90% | 0.5627 | 0.1101 | 0.1682 | SEVERE_OVERFIT_WARNING |
| SHORT_HEAD | D1 | 4712 | 27.76% | 0.8314 | 5200 | 35.23% | 0.6459 | 0.1855 | 0.4327 | SEVERE_OVERFIT_WARNING |
| SHORT_HEAD | D2 | 9897 | 31.07% | 0.7808 | 7082 | 27.32% | 0.6268 | 0.1540 | 0.2353 | SEVERE_OVERFIT_WARNING |
| SHORT_HEAD | D3 | 16645 | 29.88% | 0.9300 | 9840 | 33.30% | 0.6358 | 0.2941 | 0.5347 | SEVERE_OVERFIT_WARNING |
| POOLED_SIDE_ALIGNED_CONTROL | D1 | 9376 | 33.53% | 0.6845 | 10452 | 30.00% | 0.5978 | 0.0866 | 0.1281 |  |
| POOLED_SIDE_ALIGNED_CONTROL | D2 | 19838 | 31.67% | 0.6893 | 14145 | 30.83% | 0.5659 | 0.1234 | 0.2345 | SEVERE_OVERFIT_WARNING |
| POOLED_SIDE_ALIGNED_CONTROL | D3 | 33416 | 31.40% | 0.7515 | 19626 | 33.60% | 0.5629 | 0.1887 | 0.3234 | SEVERE_OVERFIT_WARNING |

## 2025 年前训练集 vs 2025+ 历史测试

| Head | 2025前 n | 2025前 AUC | 2025+ n | 2025+ AUC | AUC 差 | 过拟合标记 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| LONG_HEAD | 26237 | 0.7059 | 23700 | 0.5232 | 0.1827 | SEVERE_OVERFIT_WARNING |
| SHORT_HEAD | 26326 | 0.8556 | 23350 | 0.5314 | 0.3242 | SEVERE_OVERFIT_WARNING |
| POOLED_SIDE_ALIGNED_CONTROL | 52563 | 0.6925 | 47050 | 0.5591 | 0.1335 | SEVERE_OVERFIT_WARNING |

## 系统级 2025+ 门禁

- 2025+ AUC 0.5202，95% CI [0.4400, 0.6012]
- top-decile uplift 0.0187，95% CI [-0.0777, 0.1194]
- Brier skill 0.0018
- non-overlap AUC 0.5483
- LAGO 中位数 0.5264，最小 0.5046
- LONG 2025+ AUC 0.5232；SHORT 0.5314
- 年度稳定性：head gate=PASS；system gate=FAIL
- vs SLOPE paired AUC 差 CI 下界 -0.1013
- vs F0 logit paired AUC 差 CI 下界 -0.1303

### 2025+ 年度分段

| Head | Year | n | 成功率 | AUC | 方向翻转 |
| --- | ---: | ---: | ---: | ---: | --- |
| LONG_HEAD | 2025 | 16117 | 29.50% | 0.5138 | NO |
| LONG_HEAD | 2026 | 7583 | 36.52% | 0.5322 | NO |
| SHORT_HEAD | 2025 | 16056 | 35.11% | 0.5244 | NO |
| SHORT_HEAD | 2026 | 7294 | 24.25% | 0.5860 | NO |
| POOLED_SIDE_ALIGNED_CONTROL | 2025 | 32173 | 32.30% | 0.5705 | NO |
| POOLED_SIDE_ALIGNED_CONTROL | 2026 | 14877 | 30.50% | 0.5327 | NO |
| SYSTEM | 2025 | 32173 | 32.30% | 0.5415 | NO |
| SYSTEM | 2026 | 14877 | 30.50% | 0.4753 | YES |

## 十分位（系统 2025+）

| Decile | n | 成功率 | uplift | 净收益均值 | 净收益中位数 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4705 | 29.39% | -0.0234 | -0.00867 | -0.07647 |
| 2 | 4705 | 28.44% | -0.0329 | -0.01399 | -0.07316 |
| 3 | 4705 | 30.82% | -0.0091 | -0.00528 | -0.06604 |
| 4 | 4705 | 30.44% | -0.0129 | -0.00202 | -0.06304 |
| 5 | 4705 | 33.79% | 0.0206 | 0.00977 | -0.05716 |
| 6 | 4705 | 31.05% | -0.0068 | 0.00186 | -0.06329 |
| 7 | 4705 | 33.60% | 0.0187 | 0.00758 | -0.06170 |
| 8 | 4705 | 33.62% | 0.0189 | 0.00999 | -0.05970 |
| 9 | 4705 | 32.54% | 0.0081 | 0.00728 | -0.05831 |
| 10 | 4705 | 33.60% | 0.0187 | 0.00271 | -0.05765 |

## 人工规则（不参与选择）

### 开发期 OOF

| Head | 规则 | n | 覆盖率 | 成功率 | 净收益均值 |
| --- | --- | ---: | ---: | ---: | ---: |
| LONG_HEAD | all_ma7_cross | 22101 | 100.00% | 31.89% | -0.00367 |
| LONG_HEAD | slope_aligned | 10586 | 47.90% | 34.01% | 0.00026 |
| LONG_HEAD | slope_ge_0p02 | 9190 | 41.58% | 33.74% | -0.00071 |
| LONG_HEAD | quote_volume_ge_1p5 | 3211 | 14.53% | 32.98% | -0.00214 |
| LONG_HEAD | slope_and_volume | 1964 | 8.89% | 31.67% | -0.00576 |
| LONG_HEAD | path_30d_adverse | 14194 | 64.22% | 31.58% | -0.00184 |
| SHORT_HEAD | all_ma7_cross | 22122 | 100.00% | 31.84% | 0.00426 |
| SHORT_HEAD | slope_aligned | 10848 | 49.04% | 34.53% | 0.00738 |
| SHORT_HEAD | slope_ge_0p02 | 9123 | 41.24% | 35.27% | 0.00874 |
| SHORT_HEAD | quote_volume_ge_1p5 | 1752 | 7.92% | 41.44% | 0.02454 |
| SHORT_HEAD | slope_and_volume | 1073 | 4.85% | 47.44% | 0.03837 |
| SHORT_HEAD | path_30d_adverse | 11417 | 51.61% | 31.79% | 0.00809 |

### 2025+ 历史测试

| Head | 规则 | n | 覆盖率 | 成功率 | 净收益均值 |
| --- | --- | ---: | ---: | ---: | ---: |
| LONG_HEAD | all_ma7_cross | 23700 | 100.00% | 31.74% | -0.00563 |
| LONG_HEAD | slope_aligned | 11401 | 48.11% | 32.44% | -0.00449 |
| LONG_HEAD | slope_ge_0p02 | 9685 | 40.86% | 32.63% | -0.00389 |
| LONG_HEAD | quote_volume_ge_1p5 | 4485 | 18.92% | 33.58% | -0.00021 |
| LONG_HEAD | slope_and_volume | 2637 | 11.13% | 34.77% | 0.00184 |
| LONG_HEAD | path_30d_adverse | 17830 | 75.23% | 30.83% | -0.00829 |
| SHORT_HEAD | all_ma7_cross | 23350 | 100.00% | 31.72% | 0.00757 |
| SHORT_HEAD | slope_aligned | 12923 | 55.34% | 31.01% | 0.00671 |
| SHORT_HEAD | slope_ge_0p02 | 11160 | 47.79% | 31.01% | 0.00640 |
| SHORT_HEAD | quote_volume_ge_1p5 | 2027 | 8.68% | 33.05% | 0.01016 |
| SHORT_HEAD | slope_and_volume | 1331 | 5.70% | 30.58% | 0.00447 |
| SHORT_HEAD | path_30d_adverse | 9518 | 40.76% | 30.14% | 0.00410 |
| SYSTEM | all_ma7_cross | 47050 | 100.00% | 31.73% | 0.00092 |
| SYSTEM | slope_aligned | 24324 | 51.70% | 31.68% | 0.00146 |
| SYSTEM | slope_ge_0p02 | 20845 | 44.30% | 31.76% | 0.00162 |
| SYSTEM | quote_volume_ge_1p5 | 6512 | 13.84% | 33.42% | 0.00302 |
| SYSTEM | slope_and_volume | 3968 | 8.43% | 33.37% | 0.00272 |
| SYSTEM | path_30d_adverse | 27348 | 58.13% | 30.59% | -0.00398 |

## 特征方案开发期 macro AUC

| Head | F0 | F1 | F2 | F3 | 锁定 |
| --- | ---: | ---: | ---: | ---: | --- |
| LONG_HEAD | 0.5542 | 0.5611 | 0.5763 | 0.5381 | F2_MA7_CONTEXT |
| SHORT_HEAD | 0.5816 | 0.5821 | 0.5845 | 0.6362 | F3_MA7_FULL_MARKET |
| POOLED_SIDE_ALIGNED_CONTROL | 0.5525 | 0.5755 | 0.5706 | 0.5635 | F1_MA7_PATH |

## 相对基准与一般 asset-day 模型

开发期 D1-D3 验证集：LONG 锁定 F2 macro AUC 0.5763，SHORT 锁定 F3 0.6362，但 SHORT F3 主要吃到 `t1_pit_universe_size_p0r` 与 BTC/市场环境，属于时间/体制代理，不是稳定的穿越质量。2025+ 上 CATL P1 一般 asset-day Entry 冻结预测在同一 MA7 事件子集上：LONG 0.5628，SHORT 0.5888，均高于本轮 MA7 事件 LGBM（0.5232 / 0.5314）。机器学习没有稳定超过斜率/放量人工规则，也没有超过一般 asset-day 模型。

## 过拟合与失效模式

- 所有主方向折都出现 `SEVERE_OVERFIT_WARNING`：训练 AUC 0.67–0.93，验证 AUC 0.55–0.65。
- 2025 年前重训 AUC 仍高（LONG 0.7059，SHORT 0.8556），2025+ 降到 0.52–0.53。
- 开发期 SHORT F3 三折 AUC 0.63–0.65 在 2025+ 失效；LONG F3 在 D3 已降到 0.4722。
- 十分位几乎不分层：top 成功率 33.60%，裸穿越 31.73%，净收益中位数仍为负。
- 成交量/斜率人工规则只在开发期 SHORT 上抬升，2025+ 上重新接近裸穿越。

## 解释要点

主模型锁定 LONG=`F2_MA7_CONTEXT` / SHORT=`F3_MA7_FULL_MARKET`。permutation 块消融显示模型更依赖穿越前路径/状态。成交量块 T1_FLOW 平均 AUC 下降 0.0021（long）、0.0081（short）；慢均线 T1_SLOW_MA_CONTEXT 为 0.0160 / -0.0012；市场环境 T1_CROSS_MARKET 为 0.0155 / 0.0868。这些是预测依赖，不是因果关系。

1. 模型更依赖穿越前路径/市场状态，而不是穿越当日 K 线质量。
2. MA7 斜率本身增量有限：SLOPE_ONLY 与 F0 已接近开发期大部分信号，2025+ paired AUC 差 CI 穿过 0。
3. 成交量块 permutation 下降很小（long 0.002 / short 0.008），不是稳定增量。
4. 慢均线在 long 上有一点开发期 permutation 下降（0.016），short 上接近 0 甚至为负。
5. 市场环境只在 short F3 上“很强”，但被宇宙规模/BTC 收益代理，2025+ 不能复现。
6. long 学路径位置与 funding，short 学市场广度与 BTC；两边学到的状态不同，且都不稳定。
7. 机器学习没有明显超过人工斜率、放量和路径过滤。

## 边界

- 没有生成策略、仓位、账户权益或 live-ready 产物。
- 2025+ 已被全市场 MA7 统计和 CATL 研究间接揭示，只是模型未见。
- HYPE 未读取、未预测、未揭示。

