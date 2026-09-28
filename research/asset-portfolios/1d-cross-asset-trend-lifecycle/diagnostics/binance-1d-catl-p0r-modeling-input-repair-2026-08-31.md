# BIN-1D-CATL-P0R 建模输入修复报告

## 裁决

`MODELING_INPUT_READY / diagnostic-only / not promoted / not live-ready`

P0 原始证据未覆盖；P0R 只生成 donor-only 建模输入。`HYPE/USDT:USDT` 全资产封存，输出为 `0` 行；HYPE 不参与 donor 市场聚合、流动性排名或任何标签统计。本轮仍未读取 `2026-05-31 00:00 UTC` 及之后的 HYPE 冻结验证数据。

## 修复结果

- donor：`732` 个资产，`1,128,880` 条 long/short landmark。
- tradable landmarks：`962,562`；基础模型资格：`955,392`。
- 完整且合格的 20d entry：`933,002`，成功率 `29.88%`。
- 完整且合格的 5d continuation：`950,490`，成功率 `34.94%`。
- 单日价格尺度异常：`18` 行；ATR/entry 超过 0.50：`2,404` 行。
- 非 tradable 却带 P0R 流动性排名：`0` 行（必须为 0）。
- 因果波动状态只使用更早历史；不足 30 条历史的方向行：`60,572`。

## 按方向审计

| side | entry n | entry 成功率 | entry 净收益均值 | 20d MFE/ATR 均值 | 20d MAE/ATR 均值 | continuation n | continuation 成功率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| long | 466,501 | 30.05% | -0.71% | 3.120 | 2.348 | 475,245 | 34.12% |
| short | 466,501 | 29.70% | 0.17% | 2.348 | 3.120 | 475,245 | 35.75% |

MFE 与 MAE 必须按方向分别看；把 long/short 成对汇总会因为路径镜像而产生相同总体分布，这不是标签生成错误。

## 因果波动状态审计

| state | entry n | entry 成功率 | continuation n | continuation 成功率 |
| --- | ---: | ---: | ---: | ---: |
| high | 207,240 | 22.40% | 209,762 | 26.94% |
| insufficient_history | 0 | NA | 0 | NA |
| low | 452,282 | 33.00% | 462,118 | 38.64% |
| mid | 273,480 | 30.39% | 278,610 | 34.82% |

这里的状态差异仅用于数据诊断，不能据此选特征、调阈值或宣称策略有效。

## P1 边界

P1 只能读取 `artifacts/p0r_donor_directional_modeling_panel/` 和冻结 allowlist；Entry 与 continuation 分开做 walk-forward。HYPE 只能在模型、特征集、超参数、校准和判定规则全部锁定后，进入一次性独立 reveal。
