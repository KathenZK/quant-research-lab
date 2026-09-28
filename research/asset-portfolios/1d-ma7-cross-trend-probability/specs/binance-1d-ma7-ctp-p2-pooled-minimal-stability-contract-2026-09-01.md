# BIN-1D-MA7-CTP-P2 Pooled-Minimal Stability Audit 合同

- Family：`Binance-1D-MA7-Cross-Trend-Probability`（`BIN-1D-MA7-CTP`）
- Experiment：`P2 Pooled-Minimal MA7 Cross Stability Audit`
- 日期：2026-09-01
- 固定随机种子：`20260901`
- 主状态：`explore / diagnostic-only / not promoted / not live-ready`
- 本合同在读取 P2 事件样本标签率、AUC 或模型结果之前冻结。看到 D1-D3 或任何历史结果后，禁止新增特征、修改标签、改变时间边界、扩大模型或调参。

## 1. 唯一研究问题

在一个资产完整 UTC 日 K 收盘刚刚发生严格 MA7 方向穿越后，能否使用一个全市场共用、方向对齐、极简的 pooled 模型，稳定判断从下一 UTC 日开盘开始，未来 20 日是否先达到顺向 `+2 ATR`，而不是先达到逆向 `-1 ATR`。

P2 只验证 P1 pooled 控制组的弱排序是否来自可重复的 MA7 穿越质量。它不是一般趋势预测、不是多空双头、不是 continuation / exit / 持仓 / 反手模型，也不是交易策略。

禁止事项：

- 禁止重新训练所有 asset-day 一般趋势模型。
- 禁止加入非 MA7 穿越日。
- 禁止分别训练 `LONG_HEAD` 和 `SHORT_HEAD`。
- 禁止搜索 MA 周期，禁止把 MA7 换成 MA30 后挑赢家。
- 禁止增加新特征，禁止使用 F2/F3、慢均线、funding、流动性排名、市场 breadth、BTC 状态或相对市场字段。
- 禁止生成策略回测、账户收益、仓位、权益曲线或 live-ready 产物。
- 禁止使用 2025+ 或 HYPE 做模型、特征、轮数、校准或阈值选择。

若 P2 输入或训练行出现非 MA7 穿越事件，立即裁决 `OBJECTIVE_MISALIGNED` 并停止训练。若任何 P2 输入、OOF、模型卡或报告中出现 HYPE 行，立即裁决 `HOLDOUT_CONTAMINATED`。

## 2. 唯一允许输入

物理建模输入只允许：

1. `research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/p0r_donor_directional_modeling_panel/**/*.parquet`
2. `research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/binance_1d_catl_p0r_feature_blocks.json`
3. `research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/binance_1d_catl_p0r_manifest.json`
4. P1 冻结 feature spec：`research/asset-portfolios/1d-ma7-cross-trend-probability/artifacts/binance_1d_ma7_ctp_p1_feature_spec.json`

P0R、P1 产物均只读，不得覆盖。P2 不读取 P1 的 2025+ 预测，不把 P1 2025+ 结果作为验证证据。若 CATL P1 一般 asset-day 冻结预测文件在当前工作树中不存在，则只记录控制组不可用，不另找替代输入。

建模前必须验证：

- P0R manifest 中全部 artifact SHA256 匹配。
- `holdout_read=false`。
- `hype_asset_excluded='HYPE/USDT:USDT'`。
- donor panel 中 HYPE 为 0 行，`HYPER/USDT:USDT` 存在。
- P1 feature spec SHA256 匹配 P1 manifest。
- P2 所有读取、训练、验证和预测产物均满足 `max(ts) < 2025-01-01 00:00:00 UTC`。

## 3. HYPE 隔离

封存资产：`HYPE/USDT:USDT`。`HYPER/USDT:USDT` 是不同资产，必须保留。

P2 禁止读取或使用 HYPE 的 K 线、funding、MA7 事件、标签、365 日表现、后 81 日表现、P0-P8 预测、交易路径、汇总统计或误差分析。不得读取 HYPE 对照报告或产物。P2 不执行 HYPE reveal。

## 4. 样本与标签

事件必须同时满足：

```text
probe_raw_ma7_cross_dir == true
AND model_eligible_entry_p0r == true
AND ts < 2025-01-01 00:00:00 UTC
```

每个 `asset + ts` 只能保留一个实际穿越方向。P2 选择和 OOF 样本预期约 `54,137` 条；最终重训进一步使用 `label_end_ts_20d < 2025-01-01` 的事件，预期约 `52,563` 条。HYPE 必须为 0，非穿越必须为 0。

唯一主标签：`label_entry_success_20d`。

- 信号日收盘评估，下一 UTC 日开盘进入。
- 使用闭合 1 小时路径判断 first-hit。
- 顺向先达到 `+2 ATR` 记为 1；逆向先达到 `-1 ATR` 或未成功记为 0。
- 同小时双触按不利先触发。
- ATR 使用冻结的 `atr_anchor`。
- 成本使用冻结手续费、滑点和真实 funding。
- `label_entry_net_return` 只用于排序诊断，不进入 X。

## 5. 模型与特征

主模型只有一个：`POOLED_DIRECTION_ALIGNED`。long 和 short 事件合并训练，所有输入特征已方向对齐。`side`、`side_sign`、`asset` 和任何时间编码不得进入 X。评价时按 long / short 子集分层，但不得训练独立多空头。

P2 严格复用 P1 feature spec 的原始字段定义，只允许：

- `F0_MA7_CORE` = `T1_MA7_HISTORY + EVENT_T0`
- `F1_MA7_PATH` = `F0_MA7_CORE + T1_OWN_PRICE_PATH`

禁止进入 X 的字段包括：F2/F3 块、慢均线、funding、liquidity rank、PIT universe size、市场 breadth、BTC/相对 BTC/相对市场、`asset`、`side`、日期/年份编码、资格标记、所有 `label_*`、所有 `future_*`、净收益、MFE/MAE、`persist_*`、`recross_*`、文件名/分区/行号/资产编码、当前行 MA7 cross/probe 字段。

## 6. 模型候选与选择

固定候选：

1. `CONST_PRIOR`
2. `SLOPE_ONLY_LOGIT`
3. `F0_LOGIT`
4. `F1_LOGIT`
5. `F0_T1`
6. `F0_T2`
7. `F1_T1`
8. `F1_T2`

LightGBM 共同参数：`objective=binary`、`learning_rate=0.02`、`n_estimators=1000`、`early_stopping_rounds=100`、`bagging_fraction=1.0`、`bagging_freq=0`、`deterministic=true`、`random_state=20260901`。

| ID | num_leaves | max_depth | min_data_in_leaf | feature_fraction | lambda_l2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| T1 | 7 | 3 | 1000 | 0.75 | 10 |
| T2 | 15 | 4 | 2000 | 0.75 | 20 |

选择顺序：

1. 比较 D1/D2/D3 最差 fold AUC，优先最差年份更高。
2. 再比较三折 macro AUC。
3. 再比较 macro Brier 和 log loss。
4. 复杂模型相对简单模型 AUC 提升不足 `0.005` 时选择更简单模型。
5. Logistic 与 LightGBM 差异不足 `0.005` 时优先 Logistic。
6. 不能以训练集 AUC 选择模型。

最终 LightGBM 轮数使用 D1-D3 最佳轮数中位数。概率校准只用 D1-D3 OOF raw probability 拟合 Platt；若未改善 Brier 或 log loss，则冻结 raw。

## 7. 时间切分

只允许扩展式 walk-forward：

| Fold | Validation | Training |
| --- | --- | --- |
| D1 | 2022 全年 | 此前事件并精确 purge |
| D2 | 2023 全年 | 此前事件并精确 purge |
| D3 | 2024 全年 | 此前事件并精确 purge |

每折必须满足 `max(training.label_end_ts_20d) < validation_start_ts`。禁止随机拆分、随机 K-fold、打乱样本、用 2025+ early stopping、用 2025+ 选择 F0/F1、模型、轮数或校准。P2 不输出 2025+ 预测。

## 8. 评价与稳定性

每个模型、每个 fold 同时报告 training 与 validation 的样本数、正例率、ROC-AUC、PR-AUC、log loss、Brier、AUC 差与 top-decile uplift 差。若 `train AUC - validation AUC > 0.10`，标记 `SEVERE_OVERFIT_WARNING`。

必须报告：D1/D2/D3 年度结果、同一 pooled 模型在 long/short 子集上的 AUC、20 日 non-overlap OOF、28 日 block bootstrap 1000 次、`sha256(asset)%5` leave-asset-group-out、asset-balanced sensitivity、波动状态/上市年龄/流动性分层、Top/Bottom 十分位成功率与成本后事件收益、F1 相对 F0 paired AUC 差及 95% CI。不得年化、不得合成账户权益。

## 9. 裁决

P2 不能给出 live-ready 或未来有效确认。所有裁决继续保持 `explore / diagnostic-only / not promoted / not live-ready`。

`POOLED_MINIMAL_CANDIDATE_FROZEN_AWAITING_NEW_OOS` 必须同时满足：

1. D1/D2/D3 验证 AUC 均大于 `0.52`。
2. 三折 macro AUC 大于 `0.55`。
3. 三折均不触发 `SEVERE_OVERFIT_WARNING`。
4. OOF 28 日 block-bootstrap AUC 下界大于 `0.50`。
5. OOF top-decile uplift 置信区间下界大于 `0`。
6. non-overlap OOF AUC 大于 `0.52`。
7. leave-asset-group-out 五组 AUC 中位数大于 `0.52`，最小值不低于 `0.49`。
8. pooled 模型在 long 和 short 子集 AUC 均大于 `0.50`。
9. 没有年度方向翻转。

若上述稳定门通过，但 F1 相对 F0 paired AUC 差 95% CI 下界不大于 0，则裁决 `SIGNAL_EXPLAINED_BY_MA7_CORE`。若稳定门未过但 OOF / fold 中仍存在弱排序，则裁决 `UNSTABLE_POOLED_SIGNAL`；若接近随机且无可学习排序，则裁决 `NO_LEARNABLE_POOLED_SIGNAL`。

真正的新验证只能来自 2026-06-30 后新收集、此前未用于特征设计的 donor 市场数据，或用户以后明确授权的独立封存揭示实验。
