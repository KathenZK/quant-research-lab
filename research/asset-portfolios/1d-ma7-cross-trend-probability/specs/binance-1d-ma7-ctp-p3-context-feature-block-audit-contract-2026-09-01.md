# BIN-1D-MA7-CTP-P3 Independent Context Feature Block Audit 合同

- Family：`Binance-1D-MA7-Cross-Trend-Probability`（`BIN-1D-MA7-CTP`）
- Experiment：`P3 Independent Context Feature Block Audit`
- 日期：2026-09-01
- 固定随机种子：`20260901`
- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 本合同在读取 P3 严格事件样本标签率、AUC 或增量结果前冻结。看到结果后不得新增特征、删除年份、改阈值、扩大模型网格或修改标签。

## 1. 唯一研究问题

P3 仍只研究：一个资产在完整 UTC 日 K 收盘时刚刚发生严格 MA7 方向穿越后，从下一 UTC 日开盘开始，未来 20 日是否先顺向达到 `+2 ATR`，而不是先逆向达到 `-1 ATR`。

P3 只回答：在 P2 的 MA7 自身价格路径基础上，流动性、MA30 慢趋势背景、全市场环境和 funding 是否提供独立增量。

P3 不是一般 asset-day 趋势模型，不是 MA30 穿越模型，不修改 MA7 事件定义，不训练持仓、退出或反手模型。

## 2. 禁止事项

- 不得覆盖或修改 P0、P0R、P1、P2 的合同、脚本、报告和产物。
- 不得修改标签、ATR、`+2/-1 ATR` 屏障、20 日窗口或下一 UTC open 起算规则。
- 不得加入非 MA7 穿越日；不得使用 2025 年及以后发生的事件；所有事件必须满足 `label_end_ts_20d < 2025-01-01 00:00 UTC`。
- 不得训练 long/short 独立模型，不得把 `asset`、资产编码、日期、年份、`side`、`side_sign` 加入 X。
- 不得读取 HYPE 的 K 线、标签、预测、交易路径或任何 HYPE P0-P8 结果。
- 不得使用 OI、open interest、taker buy/sell、真实市值、链上数据；冻结 P0R 面板没有这些字段。
- 不得重新扫描或重建原始/normalized 数据湖。
- 不得做策略回测、权益曲线、仓位、年化收益、Sharpe 或 live-ready 产物。

任一数据审计失败，裁决 `DATA_BLOCK_NOT_READY` 或 `HOLDOUT_CONTAMINATED` 并停止训练。

## 3. 唯一允许输入

只允许读取：

1. `research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/p0r_donor_directional_modeling_panel/**/*.parquet`
2. `research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/binance_1d_catl_p0r_feature_blocks.json`
3. `research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/binance_1d_catl_p0r_manifest.json`
4. `research/asset-portfolios/1d-ma7-cross-trend-probability/artifacts/binance_1d_ma7_ctp_p2_feature_spec.json`
5. `research/asset-portfolios/1d-ma7-cross-trend-probability/artifacts/binance_1d_ma7_ctp_p2_summary.json`
6. `research/asset-portfolios/1d-ma7-cross-trend-probability/artifacts/binance_1d_ma7_ctp_p2_model_card.json`
7. P2 修复后脚本，仅用于复用时间切分、预处理、前向校准、bootstrap 和审计实现。

禁止读取 P1/P2 的 2025+ 预测文件及任何 HYPE 文件。

## 4. 运行前数据审计

读取标签前必须先写入本合同并冻结 `contract_lock`。随后验证：

- P0R manifest 全部 artifact SHA256 匹配。
- `holdout_read=false`。
- `HYPE/USDT:USDT` 在输入面板中为 0 行，`HYPER/USDT:USDT` 不因名称模糊被删除。
- 原始 pre-2025 MA7 事件为 `54,137` 条。
- 加上 `label_end_ts_20d < 2025-01-01` 后，严格样本为 `52,563` 条、`338` 个资产。
- 严格样本日期为 `2019-11-27` 至 `2024-12-10`。
- `asset + ts + side` 重复键为 0；非 MA7 穿越为 0；不完整 20 日未来路径为 0；空标签为 0。
- `feature_known_at < entry_ts` 全部成立；`side` 只能是 `long/short`。
- HYPE 输入、事件、OOF、报告、模型卡全部为 0；2025+ 事件读取和预测全部为 0。

## 5. 冻结特征方案

所有候选基于同一个 P2 基准：`B0_P2_F1_LOGIT`。B0 必须精确复用 P2 `F1_MA7_PATH` 特征、训练折中位数填充、训练折类别 one-hot、训练折 `StandardScaler` 和 `LogisticRegression(max_iter=1000, solver='lbfgs', L2, random_state=20260901)`。

只允许每次在 B0 上增加一个特征块：

### `B1_LIQUIDITY_SIZE_PROXY`

- `liquidity_rank_pct_p0r`
- `log1p_listing_age_days`
- `liquidity_rank_centered_sq = (liquidity_rank_pct_p0r - 0.5)^2`

`liquidity_rank_pct_p0r` 是同日 PIT 可交易池内 30 日 quote volume 排名，是流动性/交易额代理，不是真实市值。P2 已有相对成交量因子，但没有绝对流动性排名。

### `B2_MA30_CONTEXT`

- `dir_close_ma30_dist_atr`
- `dir_ma30_slope_1d_atr`
- `dir_ma30_slope_3d_atr`
- `dir_ma30_slope_5d_atr`
- `dir_price_side_ma30`
- `days_since_ma30_cross`
- `ma30_cross_count_14d`
- `dir_ma_stack_score`
- `fast_slow_ma_direction_aligned`
- `ma7_cross_with_ma30_opposite_slope`
- `dir_price_ma7_ma30_joint_state`

MA7 仍是唯一触发器，MA30 只作为慢趋势背景。

### `B3_CROSS_MARKET_CONTEXT`

- `pit_universe_size_p0r`
- `dir_market_breadth_ma7_p0r`
- `dir_market_breadth_ma30_p0r`
- `dir_market_up_ratio_1d_p0r`
- `market_ret_1d_dispersion_p0r`
- `dir_market_ret_7d_median_p0r`
- `dir_market_ret_30d_median_p0r`
- `dir_btc_ret_7d`
- `dir_btc_ret_30d`
- `dir_btc_price_side_ma7`
- `dir_btc_price_side_ma30`
- `dir_relative_to_btc_ret_7d`
- `dir_relative_to_btc_ret_30d`
- `dir_relative_to_market_median_ret_7d_p0r`
- `dir_relative_to_market_median_ret_30d_p0r`

所有市场聚合来自物理排除 HYPE 的 P0R donor panel。额外报告 PIT universe size 不少于 20 / 50 的敏感性，防止早期小币池自身包含效应主导结果。

### `B4_FUNDING_CARRY`

- `funding_missing`
- `dir_funding_carry_1d`
- `dir_funding_carry_7d`
- `dir_funding_carry_30d`
- `dir_funding_carry_change_3d`

`funding_missing` 必须保留。缺失 funding 对应的 carry 零值不能解释为真实零 funding。

固定候选只有：`B0_P2_F1_LOGIT`、`B1_LIQUIDITY_LOGIT`、`B2_MA30_CONTEXT_LOGIT`、`B3_CROSS_MARKET_LOGIT`、`B4_FUNDING_LOGIT`。禁止创建 `B_ALL`，禁止临时组合多个块。

## 6. 时间切分与校准

只允许扩展式 walk-forward：

- D1：验证 2022 全年；训练为此前事件，且 `label_end_ts_20d < 2022-01-01`。
- D2：验证 2023 全年；训练为此前事件，且 `label_end_ts_20d < 2023-01-01`。
- D3：验证 2024 年但仅保留 `label_end_ts_20d < 2025-01-01` 的事件；训练为此前事件，且 `label_end_ts_20d < 2024-01-01`。

所有候选必须使用完全相同的样本行。禁止随机拆分、随机 K-fold、打乱样本、按资产随机切分或使用 2025+ early stopping。

概率校准复用 P2 修复后的前向交叉校准：

- D1 没有更早 OOF，保持 raw。
- D2 校准器只能使用标签在 D2 开始前完成的 D1 OOF。
- D3 校准器只能使用标签在 D3 开始前完成的 D1-D2 OOF。
- 最终校准器只能使用 `label_end_ts_20d < 2025-01-01` 的 OOF。
- raw score 和 forward-calibrated probability 必须分列保存。
- AUC 与候选增量检验使用 raw score；Brier、LogLoss 与概率阈值使用前向校准概率。

## 7. 评价与裁决

每个候选、每个 fold 必须同时报告训练期与验证期的 n、资产数、日期范围、正例率、ROC-AUC、PR-AUC、PR baseline、Brier、Brier skill、LogLoss、ECE10、train-validation AUC 差、train-validation top-decile uplift 差和 overfit warning。

必须额外报告：worst-fold AUC、macro AUC；每个验证年内最高 10% 事件数、成功率、净收益均值/中位数；D2-D3 前向校准概率最高 10%；更早 OOF 校准概率 90% 分位形成的前向固定阈值结果；20 日 non-overlap；28 日 UTC 日期块 paired bootstrap 2,000 次；asset-balanced AUC；`sha256(asset)%5` 五组稳定性；long/short、年份、流动性五分位、上市年龄、PIT universe size、波动状态分层；四个增量块相对 B0 的 paired AUC 差、PR-AUC 差、Brier skill 差、Top 10% 成功率差；逻辑回归新增特征标准化系数方向稳定性；四个增量块主检验的 Benjamini-Hochberg q 值。

单块裁决：

- `INCREMENTAL_BLOCK_CONFIRMED`：paired AUC 差点估计大于 0；28 日 block-bootstrap 95% CI 下界大于 0；BH `q < 0.10`；至少 2/3 验证 fold AUC 高于 B0；最差 fold 不比 B0 差超过 0.005；20 日 non-overlap AUC 差大于 0；long/short 任一方向不比 B0 恶化超过 0.01 AUC；最高 10% 成功率及成本后净收益不得同时恶化。
- `SUGGESTIVE_INCREMENT_NOT_CONFIRMED`：点估计为正、至少 2/3 folds 改善，但 CI 包含 0。
- 其他：`NO_INCREMENT_BEYOND_P2`。

全局裁决只能是：`ONE_OR_MORE_CONTEXT_BLOCKS_CONFIRMED`、`SUGGESTIVE_CONTEXT_INCREMENT_ONLY`、`NO_CONTEXT_INCREMENT_BEYOND_P2`、`DATA_BLOCK_NOT_READY`、`HOLDOUT_CONTAMINATED`、`OBJECTIVE_MISALIGNED`。无论裁决如何，保持 `explore / diagnostic-only / not promoted / not live-ready`。
