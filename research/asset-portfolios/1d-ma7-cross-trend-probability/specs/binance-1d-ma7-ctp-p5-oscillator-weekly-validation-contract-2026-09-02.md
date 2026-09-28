# BIN-1D-MA7-CTP P5 RSI6、完整周线趋势增量与2025+验证审计合同

- Family：`Binance-1D-MA7-Cross-Trend-Probability`（`BIN-1D-MA7-CTP`）
- Experiment：`P5 Oscillator + Completed-Weekly-Regime Increment and 2025+ Validation Audit`
- 中文名：`P5 RSI6、完整周线趋势增量与2025+验证审计`
- 日期：2026-09-02
- 固定随机种子：`20260901`
- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 本合同、P5 feature spec 与 P5 contract lock 必须在读取 P5 标签率、AUC、Top10、任何 2025+ 验证标签或验证表现前冻结，锁状态为 `FROZEN_BEFORE_P5_LABEL_AND_2025_VALIDATION_READ`。

## 1. 唯一研究问题

P5 只研究：一个资产在完整 UTC 日 K 收盘时发生严格 MA7 方向穿越后，从下一 UTC 日 open 开始，未来 20 日是否先顺向达到 `+2 ATR`，而不是先逆向达到 `-1 ATR`。

本轮只检验三件事：

1. P4 中删除 `G3_VOLATILITY_STATE` 后 Top10 改善，能否在 2025+ 复用验证集复现。
2. 固定 Wilder `RSI6` 的短期超买超卖、恢复和跨越 50 状态，是否在 B0 既有价格路径之外提供增量。
3. 只用已经完整闭合 UTC 周 K 构造的周线趋势状态，是否区分顺大周期启动与逆大周期短暂穿越。

P5 不是策略版本，不训练 continuation、动态退出、反手、加仓/仓位、账户组合、权益曲线或 Sharpe；不生成 live spec、runner handoff 或交易路径 HTML。

## 2. 输入与数据角色

允许读取：

1. CATL P0R donor directional modeling panel：`../1d-cross-asset-trend-lifecycle/artifacts/p0r_donor_directional_modeling_panel/**/*.parquet`。
2. CATL P0 asset-day feature panel 中非 HYPE donor 资产对应分区：`../1d-cross-asset-trend-lifecycle/artifacts/p0_asset_day_feature_panel/asset_slug_partition=<donor>/year=*/part-*.parquet`。
3. CATL P0/P0R 合同、manifest、feature block spec、数据质量报告和字段字典。
4. P2/P3/P3R/P4 的合同、报告、审计、脚本、测试、feature spec、model card、summary 和 manifest，只作为 B0、切分、校准、bootstrap 与审计口径来源。

P5 必须先从 P0R donor panel 取得资产清单，排除 `HYPE/USDT:USDT`，再按对应 `asset_slug_partition` 读取 P0 asset-day；禁止先读取包含 HYPE 的全部 price panel 后再过滤。`HYPER/USDT:USDT` 必须保留。

开发集严格定义为：

```text
probe_raw_ma7_cross_dir == true
AND model_eligible_entry_p0r == true
AND ts < 2025-01-01 00:00:00 UTC
AND label_end_ts_20d < 2025-01-01 00:00:00 UTC
```

必须复现 P4 严格样本：`52,563` 事件、`338` 资产、long/short `26,237/26,326`、日期 `2019-11-27` 至 `2024-12-10`、最大 `label_end_ts_20d=2024-12-31`，HYPE 与已知 TradFi 均为 0。

2025+ 外层验证集定义为 `ITERATIVE_REUSED_VALIDATION_2025_PLUS`：`ts >= 2025-01-01` 且拥有完整 20 日路径的 MA7 穿越事件。它可用于本轮六个预注册候选比较与选择，但不能参与训练、缺失填充、Scaler、OneHot、概率校准或阈值拟合；它已被 P1 历史观察过，不是最终盲测。报告必须分列 2025、2026 与 pooled 2025+。

已知 TradFi base-symbol 固定为：

```text
AAPL AMZN COIN CRCL GOOGL HOOD META MSFT MSTR NVDA PLTR TSLA
SPX SPY QQQ TSM UBER XAU XAG XPD XPT
```

TradFi 不进入主要训练/验证统计和候选裁决，只可作为 `unsupported_tradfi_diagnostic` 单独报告。2025+ 主验证还必须分为 `seen_asset` 与 `new_asset`。

## 3. 标签和执行时序

P5 不修改 P0/P2/P4 标签和执行时序：

- 事件：完整 UTC 日 K 收盘发生严格 SMA7 方向穿越。
- 入场参考：下一 UTC 日 open。
- ATR 锚点、20 日 horizon、`+2/-1 ATR` first-hit、同小时双触不利优先、手续费和滑点成本均沿用 P0R/P4。
- `label_entry_net_return` 只作事件层诊断，不构造账户权益。
- `feature_known_at == entry_ts == ts + 1 day`；不得把入场滞后一天。

若事件目标偏离 MA7 穿越入场概率研究，裁决 `OBJECTIVE_MISALIGNED`；若 HYPE 进入输入、事件、OOF、验证预测或报告，裁决 `HOLDOUT_CONTAMINATED`。

## 4. 新特征块

### `G7_RSI6_OSCILLATOR`

RSI 必须从非 HYPE donor 全市场日线 close 逐资产计算，周期固定为 6。采用 Wilder 初始化：

```text
delta_t = close_t - close_t-1
gain_t = max(delta_t, 0)
loss_t = max(-delta_t, 0)
avg_gain_6 在第 6 个 delta 后初始化为前 6 个 gain 的算术均值
avg_loss_6 在第 6 个 delta 后初始化为前 6 个 loss 的算术均值
之后 avg_t = (avg_{t-1} * 5 + current) / 6
RSI6 = 100 - 100 / (1 + avg_gain_6 / avg_loss_6)
```

若 `avg_loss_6=0` 且 `avg_gain_6>0`，`RSI6=100`；若二者均为 0，`RSI6=50`。RSI6 当日值只使用当日及以前 close；`t1_` 特征只使用前一有效日及以前 close。

固定 10 个特征：

- `dir_rsi6_centered`
- `dir_rsi6_delta_1d`
- `dir_rsi6_delta_3d`
- `dir_rsi6_recovery_from_5d_adverse_extreme`
- `dir_rsi6_cross_50`
- `t1_dir_rsi6_centered`
- `t1_dir_rsi6_delta_1d`
- `t1_dir_rsi6_delta_3d`
- `t1_dir_rsi6_recovery_from_5d_adverse_extreme`
- `t1_dir_rsi6_cross_50`

方向对齐固定：

```text
centered = (rsi6 - 50) / 50
dir_rsi6_centered = side_sign * centered
dir_rsi6_delta_1d = side_sign * (rsi6_t - rsi6_t-1) / 100
dir_rsi6_delta_3d = side_sign * (rsi6_t - rsi6_t-3) / 100
long recovery = (rsi6_t - rolling_min_rsi6_5d) / 100
short recovery = (rolling_max_rsi6_5d - rsi6_t) / 100
long cross = rsi6_t > 50 and rsi6_t-1 <= 50
short cross = rsi6_t < 50 and rsi6_t-1 >= 50
```

不得增加其他 RSI 周期或事后阈值。

### `G8_COMPLETED_WEEKLY_REGIME`

周 K 使用 UTC 周期：Monday 00:00 UTC 开始，下一 Monday 00:00 UTC 才完整闭合。只有 7 个完整日 K 组成的闭合周才能作为周线特征。日线 MA7 信号按 `feature_known_at` as-of join 最近一个 `weekly_feature_known_at <= feature_known_at` 的闭合周；必须保存 `weekly_feature_known_at`，报告 `<` 与 `==` 行数。任何 `weekly_feature_known_at > feature_known_at` 立即裁决 `WEEKLY_LOOKAHEAD_CONTAMINATION`。

固定 11 个特征：

- `dir_w_ret_1w`
- `dir_w_ret_4w`
- `dir_w_ret_12w`
- `dir_w_close_sma4_dist_watr6`
- `dir_w_close_sma13_dist_watr6`
- `dir_w_sma4_slope_1w_watr6`
- `dir_w_sma13_slope_1w_watr6`
- `dir_w_ma4_ma13_alignment`
- `w_atr6_pct`
- `w_path_efficiency_12w`
- `weekly_history_13w_complete`

`watr6` 定义为最近 6 个已闭合完整周 true range 的算术均值；收益、均线距离和斜率乘 `side_sign`，`w_atr6_pct` 与 `w_path_efficiency_12w` 不做方向翻转。周线数值缺失不得删除 MA7 事件，只能由当前训练折中位数填充；`weekly_history_13w_complete` 保留为 0/1 完整性标记。

## 5. 候选模型

所有候选统一为 pooled direction-aligned Logistic Regression：

```text
LogisticRegression(penalty="l2", solver="lbfgs", max_iter=1000, random_state=20260901)
```

预处理固定为训练折中位数填充、训练折类别 one-hot、训练折 `StandardScaler`。禁止 LightGBM/XGBoost/RandomForest/ExtraTrees/神经网络、L1/ElasticNet、自动特征选择、超参数搜索、多空独立模型、临时交互项和根据 2025+ 结果新增候选。

固定六个候选：

| Candidate | Features | Count |
| --- | --- | ---: |
| `R_B0_69` | P4 完整 B0 | 69 |
| `C_NO_G3_58` | B0 删除 `G3_VOLATILITY_STATE` | 58 |
| `C_B0_PLUS_RSI_79` | B0 + `G7_RSI6_OSCILLATOR` | 79 |
| `C_B0_PLUS_WEEKLY_80` | B0 + `G8_COMPLETED_WEEKLY_REGIME` | 80 |
| `C_B0_PLUS_RSI_WEEKLY_90` | B0 + G7 + G8 | 90 |
| `C_NO_G3_PLUS_RSI_WEEKLY_79` | B0 - G3 + G7 + G8 | 79 |

Feature spec 必须记录完整字段顺序、数量、并集、缺失、重复和 forbidden 检查。

## 6. 切分、校准与验证

开发期固定 D1/D2/D3：

| Fold | Training | Validation |
| --- | --- | --- |
| `D1` | `label_end_ts_20d < 2022-01-01` | 2022 |
| `D2` | `label_end_ts_20d < 2023-01-01` | 2023 |
| `D3` | `label_end_ts_20d < 2024-01-01` | 2024，且标签在 2025 前结束 |

主要 Top10 按每个 validation fold 内 raw score percentile 定义。D1 无更早 OOF，校准保持 raw；D2 只用 D1 OOF；D3 只用 D1-D2 OOF。最终 2025+ 校准器只使用 pre-2025 D1-D3 OOF，阈值只由 pre-2025 OOF 冻结。

2025+ 验证时每个候选统一使用全部 52,563 条 pre-2025 严格事件重训，一次性预测全部合格 2025+ 事件，保存 raw probability、calibrated probability 与 frozen-threshold selection，不得在 2025+ 上重新训练、重新校准或重新定阈值。

## 7. 评价、统计比较与裁决

开发期必须报告 train/validation n、正例率、ROC-AUC、PR-AUC、Brier、LogLoss、ECE10、Top10、uplift、净收益均值/中位数、Bottom10、Top-Bottom、train-validation gap、Macro AUC、worst-fold AUC、long/short、20 日 non-overlap、asset-balanced AUC、五组 leave-asset-group-out、RSI/周线缺失率和概率校准。

2025+ 必须报告 `year-relative Top10`、`pooled validation Top10`、`frozen-threshold selection`，并分列 2025、2026、pooled、long、short、seen/new asset、20 日 non-overlap、月度与 28 日块稳定性、每日事件和每日入选数量。

所有挑战者相对 `R_B0_69` 做同事件 paired 比较。开发期与 2025+ 分开执行 28 日 UTC 日期块 bootstrap，2,000 次，固定种子 `20260901`，同一 period 内所有候选使用同一组 draws。报告 AUC diff、PR-AUC diff、Top10 success diff、Top10 net mean diff、asset-balanced AUC diff、non-overlap AUC diff、long/short AUC diff 与 95% CI，并对五个挑战者主检验做 Benjamini-Hochberg 校正。

候选裁决只允许：

- `VALIDATION_CONFIRMED_INCREMENT`
- `TAIL_SPECIALIST_VALIDATED`
- `DEVELOPMENT_ONLY_NOT_REPLICATED`
- `NO_NEW_INCREMENT_B0_REMAINS_REFERENCE`
- `DIRECTION_OR_REGIME_UNSTABLE`
- `DATA_BLOCK_NOT_READY`
- `HOLDOUT_CONTAMINATED`
- `WEEKLY_LOOKAHEAD_CONTAMINATION`
- `OBJECTIVE_MISALIGNED`

即使候选通过，也只能标记 `validation candidate / diagnostic-only / not promoted / not live-ready`；不得登记策略版本，不得执行 HYPE reveal。

## 8. 输出边界

P5 产物统一前缀 `binance_1d_ma7_ctp_p5_`，必须包含 feature spec、contract lock、data audit、fold metrics、pre-2025 OOF、2025+ validation predictions、paired comparisons、strata、calibration、model card、summary、manifest，以及主报告、建模审计和周线因果审计。不得生成策略、权益、Sharpe、live、handoff、trade path 或 HYPE 产物。
