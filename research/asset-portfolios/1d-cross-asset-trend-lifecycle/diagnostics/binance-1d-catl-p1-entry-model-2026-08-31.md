# BIN-1D-CATL-P1 Entry donor-only 模型

## 裁决

`LEARNABLE_BUT_NOT_INCREMENTAL_BEYOND_MA / explore / diagnostic-only / not promoted / not live-ready`

问题：下一 UTC open 起 20 日内先到 +2 ATR 而非 -1 ATR。本轮只评价 donor 概率排序，不构造交易规则。

## D1-D3 开发期 walk-forward

- LightGBM 参数：`L2`；特征方案：`GPV`（91 个字段）。
- terminal 固定轮数：开发三折最佳轮数中位数 `91`。
- 概率校准：`platt`；校准器只拟合 D1-D3 OOF，terminal 标签使用量为 `0`。

| Fold | n / 资产 | UTC 范围 | 正例率 | ROC-AUC | PR-AUC | Log loss | Brier skill | Top uplift |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| D1 | 92,148 / 159 | 2022-01-01–2022-12-31 | 28.70% | 0.5699 | 0.3430 | 0.5941 | 1.29% | 10.45% |
| D2 | 127,736 / 220 | 2023-01-01–2023-12-31 | 30.21% | 0.5750 | 0.3523 | 0.6087 | 0.79% | 7.99% |
| D3 | 189,000 / 327 | 2024-01-01–2024-12-31 | 30.27% | 0.5488 | 0.3305 | 0.6100 | 0.56% | 4.56% |

三折 raw/calibrated macro ROC-AUC `0.5646` / `0.5646`，log loss `0.6100` / `0.6043`，Brier `0.2094` / `0.2072`。校准后 Brier skill `0.88%`。

## 2025+ donor terminal OOS

- n=`428,990`，资产 `610`，正例率 `29.69%`。
- ROC-AUC `0.5698`，28d block-bootstrap 95% CI `[0.5344, 0.6066]`。
- PR-AUC `0.3412`（正例率基线 `0.2969`），log loss `0.6018`，Brier `0.2062`，Brier skill `1.23%`。
- Top-decile uplift `6.62%`，95% CI `[1.02%, 12.41%]`；top-bottom 差 `20.69%`。
- 校准 intercept/slope `0.845/2.051`，ECE10 `1.673%`。
- raw/calibrated terminal log loss `0.6000` / `0.6018`，Brier `0.2058` / `0.2062`。
- 每资产倒数加权 AUC/Brier `0.5737` / `0.2044`。

### Terminal 概率十分位与经济排序诊断

| 十分位 | n | 成功率 | 相对总体 uplift | 净收益均值 | 净收益中位数 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 42,899 | 15.63% | -14.06% | -0.92% | -9.07% |
| 2 | 42,899 | 25.93% | -3.76% | -0.59% | -7.73% |
| 3 | 42,899 | 28.35% | -1.34% | -0.73% | -6.94% |
| 4 | 42,899 | 29.10% | -0.59% | -0.66% | -6.71% |
| 5 | 42,899 | 29.92% | 0.23% | -0.53% | -6.60% |
| 6 | 42,899 | 31.03% | 1.34% | -0.31% | -6.42% |
| 7 | 42,899 | 32.22% | 2.54% | -0.06% | -6.27% |
| 8 | 42,899 | 33.41% | 3.72% | 0.18% | -6.08% |
| 9 | 42,899 | 34.99% | 5.30% | 0.40% | -5.79% |
| 10 | 42,899 | 36.31% | 6.62% | 0.71% | -5.84% |

净收益只用于同一标签定义下的排序诊断；这些重叠 landmark 不得累加或年化。

## 相对 MA baseline 的增量

- 相对 `MA_PROBE_LOGIT` AUC 差 `0.0506`，95% CI `[0.0145, 0.0906]`。
- 相对 `G_ONLY_LOGIT` AUC 差 `0.0507`，95% CI `[0.0154, 0.0973]`。
- cross-market 开发期增量门：`False`；锁定方案相对 `FULL_NO_CROSS_MARKET` macro AUC 差 `0.0004`。

## 稳定性

- long/short terminal AUC：`0.5678` / `0.5885`。
- 2025/2026 AUC：`0.5682` / `0.5736`。
- non-overlap（间隔 20 日）AUC：`0.5285`，n=`21,972`。
- leave-asset-group-out 五组 AUC 中位数/最小值：`0.5527` / `0.5490`。

### 流动性五分位

| 分层 | n | 正例率 | ROC-AUC | Brier | Top uplift |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 85,210 | 31.35% | 0.5615 | 0.2133 | 5.94% |
| 2 | 86,140 | 30.52% | 0.5655 | 0.2099 | 6.81% |
| 3 | 85,980 | 30.02% | 0.5640 | 0.2078 | 6.53% |
| 4 | 86,004 | 28.69% | 0.5710 | 0.2020 | 5.91% |
| 5 | 85,656 | 27.87% | 0.5816 | 0.1981 | 7.43% |

### 上市年龄三分位

| 分层 | n | 正例率 | ROC-AUC | Brier | Top uplift |
| --- | ---: | ---: | ---: | ---: | ---: |
| middle | 142,996 | 30.17% | 0.5744 | 0.2079 | 7.44% |
| old | 142,997 | 29.51% | 0.5628 | 0.2059 | 5.14% |
| young | 142,997 | 29.38% | 0.5721 | 0.2048 | 7.09% |

### 因果波动状态

| 分层 | n | 正例率 | ROC-AUC | Brier | Top uplift |
| --- | ---: | ---: | ---: | ---: | ---: |
| high | 93,520 | 21.27% | 0.5876 | 0.1684 | 3.28% |
| low | 206,522 | 33.24% | 0.5453 | 0.2212 | 6.92% |
| mid | 128,948 | 30.10% | 0.5405 | 0.2097 | 2.38% |

## 模型依赖的 feature blocks

- `ma_geometry`：开发折平均 gain share `38.13%`。
- `price_path`：开发折平均 gain share `37.18%`。
- `volatility_and_candle`：开发折平均 gain share `24.70%`。

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
