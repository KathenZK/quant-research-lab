# BIN-1D-CATL-P1 Continuation donor-only 模型

## 裁决

`LEARNABLE_BUT_NOT_INCREMENTAL_BEYOND_MA / explore / diagnostic-only / not promoted / not live-ready`

问题：下一 UTC open 起 5 日内先到 +1 ATR 而非 -0.75 ATR。本轮只评价 donor 概率排序，不构造交易规则。

## D1-D3 开发期 walk-forward

- LightGBM 参数：`L3`；特征方案：`FULL_NO_CROSS_MARKET`（111 个字段）。
- terminal 固定轮数：开发三折最佳轮数中位数 `33`。
- 概率校准：`platt`；校准器只拟合 D1-D3 OOF，terminal 标签使用量为 `0`。

| Fold | n / 资产 | UTC 范围 | 正例率 | ROC-AUC | PR-AUC | Log loss | Brier skill | Top uplift |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| D1 | 93,686 / 160 | 2022-01-01–2022-12-31 | 34.28% | 0.5528 | 0.3795 | 0.6413 | 0.37% | 5.86% |
| D2 | 127,766 / 220 | 2023-01-01–2023-12-31 | 35.43% | 0.5551 | 0.3906 | 0.6466 | 0.62% | 5.60% |
| D3 | 189,180 / 327 | 2024-01-01–2024-12-31 | 35.52% | 0.5714 | 0.4105 | 0.6446 | 1.18% | 10.23% |

三折 raw/calibrated macro ROC-AUC `0.5598` / `0.5598`，log loss `0.6443` / `0.6442`，Brier `0.2262` / `0.2261`。校准后 Brier skill `0.72%`。

## 2025+ donor terminal OOS

- n=`444,696`，资产 `613`，正例率 `34.58%`。
- ROC-AUC `0.5661`，28d block-bootstrap 95% CI `[0.5448, 0.5895]`。
- PR-AUC `0.3911`（正例率基线 `0.3458`），log loss `0.6382`，Brier `0.2233`，Brier skill `1.30%`。
- Top-decile uplift `6.60%`，95% CI `[2.29%, 12.29%]`；top-bottom 差 `21.95%`。
- 校准 intercept/slope `0.495/1.824`，ECE10 `1.255%`。
- raw/calibrated terminal log loss `0.6379` / `0.6382`，Brier `0.2232` / `0.2233`。
- 每资产倒数加权 AUC/Brier `0.5710` / `0.2214`。

### Terminal 概率十分位与经济排序诊断

| 十分位 | n | 成功率 | 相对总体 uplift | 净收益均值 | 净收益中位数 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 44,470 | 19.22% | -15.36% | -0.42% | -0.56% |
| 2 | 44,470 | 30.51% | -4.07% | -0.27% | -1.91% |
| 3 | 44,469 | 32.93% | -1.65% | -0.47% | -3.50% |
| 4 | 44,470 | 34.74% | 0.16% | -0.47% | -3.78% |
| 5 | 44,469 | 35.64% | 1.06% | -0.42% | -3.69% |
| 6 | 44,470 | 36.71% | 2.14% | -0.34% | -3.56% |
| 7 | 44,469 | 37.48% | 2.91% | -0.27% | -3.45% |
| 8 | 44,470 | 38.28% | 3.70% | -0.20% | -3.47% |
| 9 | 44,469 | 39.09% | 4.51% | -0.17% | -3.53% |
| 10 | 44,470 | 41.18% | 6.60% | 0.04% | -2.83% |

净收益只用于同一标签定义下的排序诊断；这些重叠 landmark 不得累加或年化。

## 相对 MA baseline 的增量

- 相对 `MA_PROBE_LOGIT` AUC 差 `0.0431`，95% CI `[0.0177, 0.0744]`。
- 相对 `G_ONLY_LOGIT` AUC 差 `0.0465`，95% CI `[0.0144, 0.0837]`。
- cross-market 开发期增量门：`False`；锁定方案相对 `FULL_NO_CROSS_MARKET` macro AUC 差 `0.0000`。

## 稳定性

- long/short terminal AUC：`0.5526` / `0.5798`。
- 2025/2026 AUC：`0.5691` / `0.5602`。
- non-overlap（间隔 5 日）AUC：`0.5574`，n=`89,298`。
- leave-asset-group-out 五组 AUC 中位数/最小值：`0.5554` / `0.5462`。

### 流动性五分位

| 分层 | n | 正例率 | ROC-AUC | Brier | Top uplift |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 88,194 | 36.35% | 0.5601 | 0.2291 | 6.80% |
| 2 | 89,314 | 34.98% | 0.5577 | 0.2251 | 6.28% |
| 3 | 89,142 | 34.53% | 0.5581 | 0.2236 | 5.14% |
| 4 | 89,114 | 33.58% | 0.5707 | 0.2199 | 6.22% |
| 5 | 88,932 | 33.47% | 0.5801 | 0.2190 | 7.89% |

### 上市年龄三分位

| 分层 | n | 正例率 | ROC-AUC | Brier | Top uplift |
| --- | ---: | ---: | ---: | ---: | ---: |
| middle | 148,232 | 34.63% | 0.5674 | 0.2234 | 6.80% |
| old | 148,232 | 35.16% | 0.5602 | 0.2255 | 5.55% |
| young | 148,232 | 33.94% | 0.5698 | 0.2212 | 7.43% |

### 因果波动状态

| 分层 | n | 正例率 | ROC-AUC | Brier | Top uplift |
| --- | ---: | ---: | ---: | ---: | ---: |
| high | 95,948 | 24.99% | 0.5781 | 0.1887 | 3.84% |
| low | 215,108 | 38.97% | 0.5289 | 0.2378 | 4.22% |
| mid | 133,640 | 34.39% | 0.5308 | 0.2250 | 3.88% |

## 模型依赖的 feature blocks

- `price_path`：开发折平均 gain share `33.24%`。
- `ma_geometry`：开发折平均 gain share `30.80%`。
- `volatility_and_candle`：开发折平均 gain share `24.66%`。
- `flow_and_carry`：开发折平均 gain share `11.28%`。

这些重要性只表示模型的预测依赖，不是因果证据。

## HYPE 隔离与研究边界

- 输入、OOF、terminal 输出中的 `HYPE/USDT:USDT` 均为 `0` 行；`HYPER/USDT:USDT` 保留。
- HYPE K 线、funding、标签、表现、路径和预测均未读取或生成。
- 事件标签高度重叠，经济字段只是排序诊断；没有仓位、组合约束、成交状态机或账户回测，因此不是交易策略，也不支持 promotion/live-ready。

## 证据

- [P1 summary](../artifacts/binance_1d_catl_p1_summary.json)
- [逐折与分层指标](../artifacts/binance_1d_catl_p1_fold_metrics.parquet)
- [开发 OOF 预测](../artifacts/binance_1d_catl_p1_oof_predictions.parquet)
- [terminal 预测](../artifacts/binance_1d_catl_p1_terminal_predictions.parquet)
- [模型卡](../artifacts/binance_1d_catl_p1_model_card.json)
