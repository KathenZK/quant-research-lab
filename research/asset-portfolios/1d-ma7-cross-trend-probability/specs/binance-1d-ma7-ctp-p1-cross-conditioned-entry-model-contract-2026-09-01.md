# BIN-1D-MA7-CTP-P1 Cross-Conditioned Entry-Value 建模合同

- Family：`Binance-1D-MA7-Cross-Trend-Probability`（`BIN-1D-MA7-CTP`）
- Experiment：`P1 Cross-Conditioned Entry-Value Modeling`
- 日期：2026-09-01
- 固定随机种子：`20260901`
- 主状态：`explore / diagnostic-only / not promoted / not live-ready`
- 本合同在读取新事件样本的标签率、AUC 或模型结果之前冻结。看到结果后禁止新增特征、修改标签、调整时间边界或扩大超参数搜索。

## 1. 唯一研究问题

一个资产在完整 UTC 日 K 收盘时，刚刚发生严格 MA7 方向穿越。只针对这次已经发生的穿越，模型判断它是否值得沿穿越方向入场：从下一 UTC 日开盘开始，未来 20 日内是否先达到顺向 `+2 ATR`，而不是先达到逆向 `-1 ATR`。

这是 MA7 穿越事件打分模型，不是一般趋势预测模型。

禁止事项：

- 禁止对所有 asset-day 的 long/short 方向逐日预测。
- 禁止把 MA7 穿越仅作为普通特征或诊断探针。
- 禁止训练“任何时候是否会上涨/下跌”的泛化模型。
- 禁止把 MA7 替换为 MA14、MA30、MA60 并选择赢家；禁止搜索均线周期。
- 禁止训练 continuation、exit、持仓管理或反手模型。
- 禁止生成账户回测、仓位、权益曲线或交易策略。
- 禁止为了提高结果而在运行后新增特征、修改标签、调整时间边界或扩大超参数搜索。

每一条训练样本都必须对应一次真实 MA7 穿越。若最终训练样本中存在非 MA7 穿越日，立即裁决 `OBJECTIVE_MISALIGNED` 并停止训练。

## 2. 唯一允许的物理输入

1. `research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/p0r_donor_directional_modeling_panel/**/*.parquet`
2. `research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/binance_1d_catl_p0r_feature_blocks.json`
3. `research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/binance_1d_catl_p0r_manifest.json`

建模前必须验证：manifest 全部输入哈希匹配、`holdout_read=false`、`hype_asset_excluded='HYPE/USDT:USDT'`、donor panel 中 HYPE 为 0 行、`HYPER/USDT:USDT` 仍然存在、不存在 cutoff 后记录、P0R 原始产物只读。

禁止回退读取 P0 原始 panel、全市场 MA7 SCOUT 事件表、normalized K 线或其他研究产物补标签。全市场 MA7 统计报告只允许作为预先形成的特征假设来源；其事件 Parquet 使用另一套 ATR、起算点和日收盘 first-hit 口径，不得直接作为本轮训练数据。

可选只读对照（不进入 X、不参与选择）：已冻结的 CATL P1 Entry OOF/terminal 预测，仅在能按 `asset + ts + side` 无歧义对齐时作为 `GENERAL_DAY_MODEL_CONTROL`。

## 3. HYPE 绝对隔离

精确封存资产：`HYPE/USDT:USDT`。`HYPER/USDT:USDT` 是另一资产，必须保留。

本轮禁止读取或使用 HYPE 的 K 线、funding、MA7 事件、标签、365 日训练表现、后 81 日验证表现、P0-P8 预测、交易路径、汇总统计或误差分析。特别禁止读取 `diagnostics/binance-1d-ma7-cross-trend-probability-hype-vs-universe-2026-08-31.md`。

任何输入、派生事件表、OOF、历史测试预测、模型卡或报告中出现一行 HYPE，立即裁决 `HOLDOUT_CONTAMINATED`。本轮不执行 HYPE reveal，也不生成 HYPE 预测。

## 4. 事件样本

主样本必须同时满足：

```text
probe_raw_ma7_cross_dir == true
AND model_eligible_entry_p0r == true
```

每个 `asset + ts` 最多保留一行，即真实穿越方向对应的 long 或 short 行。

必须断言：

- 所有样本都是 MA7 方向穿越。
- 同一 `asset + ts` 不存在 long/short 重复。
- long 样本只能来自向上穿越；short 样本只能来自向下穿越。
- HYPE 行数为 0。

当前冻结 P0R 输入的预期样本审计值（只验证过滤，不代表独立样本数）：

```text
eligible MA7 events = 101,187
assets = 655
long = 50,738
short = 50,449
HYPE = 0
最早事件日 = 2019-11-27 UTC
最晚事件日 = 2026-05-10 UTC
2025-01-01以前事件 = 54,137
```

数字不一致时先查明数据版本、manifest 或过滤实现差异，不得直接继续训练。

## 5. 标签合同

唯一主标签：`label_entry_success_20d`。

- 信号在完整 UTC 日 K 收盘后形成。
- 从下一 UTC 日开盘开始计算。
- 使用真实重聚合的闭合 1 小时路径判断 first-hit 顺序。
- 顺向先达到 `+2 ATR` 记为 1；逆向先达到 `-1 ATR` 或未成功记为 0。
- 同一小时同时触及两个屏障时，按不利先触发。
- ATR 使用 P0/P0R 已经冻结的 `atr_anchor`，不得改成 ATR7。
- 经济诊断使用 P0 已经冻结的手续费 `0.001`、不利滑点 `4 bps` 和真实 funding。
- `label_entry_net_return` 只用于概率分层后的经济诊断，不得进入 X。

禁止修改屏障、观察期、成交时点或成本后重新挑选表现更好的标签。

## 6. 特征时点

### A. `SETUP_T1`

代表穿越发生前一日收盘已经知道的状态。从 P0R donor panel 按 `asset + side + ts` 排序，将允许字段严格滞后一个有效日。不得从穿越日反推前一日特征。T1 列名一律加 `t1_` 前缀。

### B. `EVENT_T0`

代表穿越当日收盘已经知道的事件质量。当前行的 MA7 cross 字段只用于筛选事件，不进入 X，因为在事件样本中它是常量。

## 7. 冻结特征方案

四套方案在看标签率之前冻结。不得运行后依据 feature importance 新增第五套。斜率、成交量、路径和波动率均以连续变量进入模型，不得把报告中表现较好的分桶写成硬门槛。后续 SHAP 或 permutation importance 只用于解释已冻结模型。

### `T1_MA7_HISTORY`

- `t1_dir_close_ma7_dist_atr`
- `t1_dir_ma7_slope_1d_atr`
- `t1_dir_ma7_slope_3d_atr`
- `t1_dir_ma7_slope_5d_atr`
- `t1_dir_ma7_slope_change_3d`
- `t1_dir_ma7_slope_accel_5d`
- `t1_days_since_ma7_cross`
- `t1_ma7_cross_count_7d`
- `t1_ma7_cross_count_14d`
- `t1_dir_price_side_ma7`
- `t1_dir_favorable_run_days`
- `t1_dir_opposite_run_days`

### `T1_OWN_PRICE_PATH`

- `t1_dir_ret_1d` / `3d` / `7d` / `14d` / `30d` / `60d`
- `t1_dir_range_pos_3d` / `7d` / `14d` / `30d` / `60d`
- `t1_dir_distance_to_favorable_extreme_{3,7,14,30,60}d_atr`
- `t1_dir_distance_from_adverse_extreme_{3,7,14,30,60}d_atr`
- `t1_path_efficiency_{7,14,30,60}d`
- `t1_shock_day`
- `t1_sideways_state`
- `t1_reexpansion_state`
- `t1_atr7_pct` / `t1_atr14_pct` / `t1_atr30_pct`
- `t1_atr14_to_atr30` / `t1_atr7_to_atr30`
- `t1_volatility_state_p0r`

P0R 没有独立 `repair` 列；穿越前冲击/横盘/再扩张状态以 `shock_day`、`sideways_state`、`reexpansion_state` 表示。顺向/逆向连续日数已列入 `T1_MA7_HISTORY`，本块不再重复。

### `T1_SLOW_MA_CONTEXT`

- MA14/MA30/MA60 距离、`1/3/5d` 斜率、斜率变化、斜率加速度
- `t1_dir_price_side_ma14` / `ma30` / `ma60`
- `t1_dir_ma_stack_score`
- `t1_fast_slow_ma_direction_aligned`
- `t1_ma7_cross_with_ma30_opposite_slope`
- `t1_dir_price_ma7_ma30_joint_state`

### `T1_FLOW`

- `t1_volume_to_7d` / `t1_quote_volume_to_7d` / `t1_volume_to_30d` / `t1_quote_volume_to_30d` / `t1_volume_change_1d`
- `t1_dir_funding_carry_1d` / `7d` / `30d` / `t1_dir_funding_carry_change_3d` / `t1_funding_missing`
- `t1_liquidity_rank_pct_p0r`

### `T1_CROSS_MARKET`

- `t1_pit_universe_size_p0r`
- `t1_dir_market_breadth_ma7_p0r` / `t1_dir_market_breadth_ma30_p0r`
- `t1_dir_market_up_ratio_1d_p0r` / `t1_market_ret_1d_dispersion_p0r`
- `t1_dir_market_ret_7d_median_p0r` / `t1_dir_market_ret_30d_median_p0r`
- `t1_dir_btc_ret_7d` / `30d`、`t1_dir_btc_price_side_ma7` / `ma30`
- `t1_dir_relative_to_btc_ret_7d` / `30d`
- `t1_dir_relative_to_market_median_ret_7d_p0r` / `30d`

### `EVENT_T0`

- `dir_close_ma7_dist_atr`
- `dir_ma7_slope_1d_atr` / `3d` / `5d`
- `dir_ma7_slope_change_3d` / `dir_ma7_slope_accel_5d`
- `large_cross_degree_atr`
- `dir_ret_1d`
- `daily_range_atr` / `body_atr` / `dir_close_location`
- `dir_favorable_wick_atr` / `dir_adverse_wick_atr`
- `atr7_pct` / `atr14_pct` / `atr30_pct` / `atr14_to_atr30` / `atr7_to_atr30`
- `volume_to_7d` / `quote_volume_to_7d` / `volume_to_30d` / `quote_volume_to_30d` / `volume_change_1d`

### 四套方案

1. `F0_MA7_CORE` = `T1_MA7_HISTORY` + `EVENT_T0`
2. `F1_MA7_PATH` = `F0` + `T1_OWN_PRICE_PATH`
3. `F2_MA7_CONTEXT` = `F1` + `T1_SLOW_MA_CONTEXT` + `T1_FLOW`
4. `F3_MA7_FULL_MARKET` = `F2` + `T1_CROSS_MARKET`

类别特征仅：`t1_volatility_state_p0r`、`t1_dir_price_ma7_ma30_joint_state`。布尔字段按数值进入模型。

## 8. 泄漏黑名单

不得进入 X：`asset`、`asset_slug`、`side`、`side_sign`、时间戳和日历字段、`entry_ts`、`entry_ref`、`atr_anchor`、绝对价格、资格标记、所有 `label_*`、所有 `future_*`、result、hours-to-hit、MFE、MAE、净收益、`persist_*`、`recross_*`、文件名、分区名、行号或资产编码、当前行 MA7 cross / probe 字段。特征名中若出现无法证明在信号收盘时已经知道的字段，默认禁止使用。

## 9. 模型结构

分别训练：

1. `LONG_HEAD`：只用向上穿越事件。
2. `SHORT_HEAD`：只用向下穿越事件。
3. `POOLED_SIDE_ALIGNED_CONTROL`：多空合并、使用方向对齐特征，但不允许 `side` 进入 X；它只是控制组。

最终系统的主模型是 LONG_HEAD 和 SHORT_HEAD。不得因为 pooled 表现更好就取消多空分层报告。

### Baseline

每个方向必须有：`CONST_PRIOR`、`SLOPE_ONLY_LOGIT`（仅 EVENT_T0 的 `dir_ma7_slope_{1,3,5}d_atr`）、`F0_MA7_CORE_LOGIT`、`F1_MA7_PATH_LOGIT`；以及能无歧义对齐时的 `GENERAL_DAY_MODEL_CONTROL`（CATL P1 Entry 冻结预测在同一 MA7 事件子集上的表现）。

人工规则不参与模型选择，只在完全相同的 P0R 标签上报告覆盖率、成功率和成本后净收益：

1. 全部 MA7 穿越
2. 斜率同向：`dir_ma7_slope_1d_atr > 0`
3. 同向斜率不低于 0.02：`dir_ma7_slope_1d_atr >= 0.02`
4. quote volume 不低于 1.5 倍：`quote_volume_to_7d >= 1.5`（P0R 冻结 7 日相对成交额，不是 SCOUT 的 20 日中位数）
5. 斜率 0.02 加放量 1.5 倍
6. 冻结的 30 日路径方向过滤：`t1_dir_ret_30d < 0`（方向对齐后的穿越前 30 日收益为负，对应 SCOUT 的多头 R<1 / 空头 R>1 口径）

### LightGBM

共同参数：`objective=binary`、`learning_rate=0.03`、`n_estimators=1500`、`early_stopping_rounds=100`、`bagging_fraction=1.0`、`bagging_freq=0`、deterministic CPU、`random_state=20260901`。

| ID | num_leaves | max_depth | min_data_in_leaf | feature_fraction | lambda_l2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| L1 | 7 | 3 | 250 | 0.75 | 1 |
| L2 | 15 | 4 | 500 | 0.75 | 3 |
| L3 | 31 | 5 | 500 | 0.75 | 5 |
| L4 | 31 | 6 | 1000 | 0.90 | 8 |

选择顺序：

1. 先用 F1 在 D1-D3 选择 L1-L4。
2. AUC 差小于 0.002 时选择更浅、更简单的模型。
3. 锁定 LightGBM 参数后，再比较 F0/F1/F2/F3。
4. 以 D1-D3 验证集 macro ROC-AUC 为首要指标，log loss 和 Brier 为并列判据。
5. 2025+ 历史测试不得参与模型、特征或轮数选择。

每个方向独立完成上述选择。

## 10. 时间切分

禁止随机拆分、随机 K-fold 和打乱样本。开发期使用扩展式 walk-forward：

| Fold | Validation | Training |
| --- | --- | --- |
| D1 | 2022 全年 | 更早事件，并满足标签结束时间早于验证起点 |
| D2 | 2023 全年 | 更早事件，并精确 purge |
| D3 | 2024 全年 | 更早事件，并精确 purge |

每折必须满足 `max(training.label_end_ts_20d) < validation_start_ts`。模型、特征方案、轮数和概率校准只能由 D1-D3 决定。

冻结后：使用 `label_end_ts_20d < 2025-01-01` 的全部事件重训；对 2025-01-01 以后的 donor 事件做一次 post-selection historical test。2025+ 已经受此前全市场统计和 CATL 研究间接揭示，因此不得称为“完全未揭示 OOS”或“严格盲测”。正确称呼是：`model-unseen / hypothesis-revealed historical test`。看过 2025+ 结果后禁止重训。HYPE 仍然不揭示。

## 11. 概率校准

LONG_HEAD 和 SHORT_HEAD 分别处理：保存 D1-D3 OOF raw probability；只使用 D1-D3 OOF 预测拟合 Platt calibration；同时报告 raw 与 calibrated 指标；如果 Platt 没有改善 Brier 或 log loss，则冻结为不校准；禁止使用 2025+ 标签调整校准器。

## 12. 评价指标

每个模型、每个方向、每个 fold 必须并列表格报告 training 与 validation 的样本数、正例率、ROC-AUC、PR-AUC、log loss、Brier，以及 training 与 validation 的 AUC 差和 top-decile uplift 差。最终重训也必须并列 2025 年前训练集与 2025+ 历史测试。

若训练 AUC 减验证 AUC 超过 0.10，标记 `SEVERE_OVERFIT_WARNING`。若训练和验证 AUC 都接近 0.50，说明欠拟合或特征没有可学习信息，不得用“泛化很好”粉饰。

还必须报告：校准 intercept/slope/ECE10、概率十分位成功率与成本后净收益、top/bottom decile 差、相对 SLOPE_ONLY_LOGIT 与 F0_MA7_CORE_LOGIT 的 paired AUC 差、相对一般 asset-day 模型控制组的差异、long/short、分年份、流动性、上市年龄、波动状态分层。不要把重叠事件收益累加成年化收益、Sharpe 或账户权益。

## 13. 重叠和跨资产稳定性

1. 以连续 28 个 UTC 日为 block 的 paired bootstrap，1000 次；每次重采样对候选模型和 baseline 使用完全相同的日期块。
2. non-overlap sensitivity：每个 `asset + side` 每 20 日最多保留一个事件。
3. deterministic leave-asset-group-out：`sha256(asset) % 5`。
4. asset-balanced sensitivity：按验证期内每个资产事件数的倒数加权。
5. 分年份、分多空检查，不得只报告合并结果。

## 14. 冻结裁决

数据和目标正确优先于模型表现。最终只能给出以下裁决之一：

- `INCREMENTAL_MA7_EVENT_SIGNAL`
- `LEARNABLE_BUT_NOT_BEYOND_SIMPLE_MA7`
- `UNSTABLE_MA7_EVENT_SIGNAL`
- `NO_LEARNABLE_MA7_EVENT_SIGNAL`
- `OBJECTIVE_MISALIGNED`
- `HOLDOUT_CONTAMINATED`
- `DATASET_INTEGRITY_FAILED`

`LEARNABLE_MA7_EVENT_SIGNAL` 必须同时满足：2025+ AUC 的 28 日 block-bootstrap 95% CI 下界大于 0.50；top-decile uplift 的 95% CI 下界大于 0；Brier skill 相对 CONST_PRIOR 大于 0；non-overlap AUC 大于 0.50；leave-asset-group-out 五组 AUC 中位数大于 0.52，最小值不低于 0.49；LONG_HEAD 和 SHORT_HEAD 的 AUC 均不低于 0.50；主要年份分段没有明显方向翻转。

`INCREMENTAL_BEYOND_SIMPLE_MA7` 在通过上门后还必须满足：相对 SLOPE_ONLY_LOGIT 与 F0_MA7_CORE_LOGIT 的 paired AUC 差 95% CI 下界大于 0；F1/F2/F3 至少一套相对 F0 提供稳定增量；top-decile 成功率和成本后净收益均优于全部 MA7 裸穿越；不能只靠单一年份、少数资产或重叠事件通过。

无论结果如何，都保持 `explore / diagnostic-only / not promoted / not live-ready`。不得为了通过门禁调阈值、改变标签或查看 HYPE。
