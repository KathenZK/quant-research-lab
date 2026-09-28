# BIN-1D-MA7-CTP-P3R Time-Boundary Repair + Independent Context Feature Block Audit 合同

- Family：`Binance-1D-MA7-Cross-Trend-Probability`（`BIN-1D-MA7-CTP`）
- Experiment：`P3R Time-Boundary Repair + Independent Context Feature Block Audit`
- 日期：2026-09-02
- 固定随机种子：`20260901`
- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 本合同是 P3 的审计修复版；P3 历史记录保持 `DATA_BLOCK_NOT_READY`，P3R 不覆盖 P0、P0R、P1、P2、P3 的合同、脚本、报告、测试或产物。

## 1. 唯一研究问题

P3R 仍只研究：一个资产在完整 UTC 日 K 收盘时刚刚发生严格 MA7 方向穿越后，从下一 UTC 日开盘开始，未来 20 日是否先顺向达到 `+2 ATR`，而不是先逆向达到 `-1 ATR`。

P3R 只回答：在 P2 的 MA7 自身价格路径基础上，流动性/交易规模代理、MA30 慢趋势背景、全市场与 BTC 环境、funding 状态是否提供独立增量。

P3R 不是一般 asset-day 趋势模型，不是 MA30 穿越模型，不修改 MA7 事件定义，不训练持仓、退出、加仓或反手模型。

## 2. 唯一允许修复

P3 的错误门禁要求 `feature_known_at < entry_ts`。P0 字段字典定义为：

- `ts` 是评估 UTC 日 K 线开盘时间；
- 该日 K 线在下一 UTC 日 `00:00` 完整闭合；
- `feature_known_at = ts + 1 day`；
- `entry_ts = ts + 1 day`。

P3R 只修复这一处时间边界，严格要求：

```text
feature_known_at == entry_ts
entry_ts == ts + 1 day
feature_known_at == ts + 1 day
feature_known_at > entry_ts 的行数为 0
feature_known_at < entry_ts 的行数为 0
```

不得把入场时间再滞后一天，不得改变标签起点，不得改变 `entry_ref`，不得重新计算收益标签。

## 3. 禁止事项

- 不得覆盖或修改 P0、P0R、P1、P2、P3 既有合同、脚本、报告、测试和产物。
- 不得修改标签、ATR、`+2/-1 ATR` 屏障、20 日窗口或下一 UTC open 起算规则。
- 不得加入非 MA7 穿越日；不得使用 2025 年及以后发生的事件；所有事件必须满足 `label_end_ts_20d < 2025-01-01 00:00 UTC`。
- 不得训练 long/short 独立模型，不得把 `asset`、资产编码、日期、年份、`side`、`side_sign` 加入 X。
- 不得读取 HYPE 的 K 线、标签、预测、交易路径或任何 HYPE P0-P8/V7.1 结果；不得读取 P1 的 2025+ historical prediction。
- 不得使用 OI、open interest、taker buy/sell、真实市值、链上数据；冻结 P0R 面板没有这些字段。
- 不得重新扫描或重建原始/normalized 数据湖。
- 不得做策略回测、权益曲线、仓位、年化收益、Sharpe 或 live-ready 产物。

任一数据审计失败，裁决 `DATA_BLOCK_NOT_READY` 或 `HOLDOUT_CONTAMINATED` 并停止训练。

## 4. 唯一允许输入

只允许读取：

1. `../1d-cross-asset-trend-lifecycle/artifacts/p0r_donor_directional_modeling_panel/**/*.parquet`
2. `../1d-cross-asset-trend-lifecycle/artifacts/binance_1d_catl_p0r_feature_blocks.json`
3. `../1d-cross-asset-trend-lifecycle/artifacts/binance_1d_catl_p0r_manifest.json`
4. `binance_1d_ma7_ctp_p2_feature_spec.json`
5. `binance_1d_ma7_ctp_p2_summary.json`
6. `binance_1d_ma7_ctp_p2_model_card.json`
7. P2/P3 脚本仅作为实现参考。

必须核对 SHA256：

- P0R manifest：`033e12bf77c5d67f4871845e3fc2650dfa26a09ca8f74983f379d84e388f93ef`
- P2 feature spec：`ac4feb1270bb2d0b1da4d1523a84763ada808ec02b409559a603608cceec2c68`
- 原 P3 feature spec：`0862eed0a974684ba16a962ebe146cdefbbc6af7cd6e7532f69c8a4554b61f8b`

必须保持 `holdout_read=false`；HYPE 输入、严格事件、OOF、模型卡、报告均为 0 行；不读取或预测任何 2025+ 事件；不做 HYPE reveal。

## 5. 样本审计

读取标签前先写入本合同与 P3R feature spec，并冻结 `contract_lock`。随后在 contract lock 后加载严格样本并复现：

- 原始 pre-2025 MA7 事件：`54,137`
- 严格样本：`52,563`
- 资产：`338`
- long：`26,237`
- short：`26,326`
- 最早事件：`2019-11-27`
- 最晚事件：`2024-12-10`
- 最大 `label_end_ts_20d`：`2024-12-31`
- 非 MA7 穿越：`0`
- 重复 `asset+ts`：`0`
- 空标签：`0`
- 不完整 20 日未来路径：`0`
- HYPE：`0`

严格样本形成后必须审计已知 TradFi 标的：

```text
AAPL AMZN COIN CRCL GOOGL HOOD META MSFT MSTR NVDA PLTR TSLA
SPX SPY QQQ TSM UBER XAU XAG XPD XPT
```

预期严格样本 TradFi 事件为 `0`。若不为 0，裁决 `DATA_BLOCK_NOT_READY`，不得事后删除样本。

## 6. 冻结特征与模型

P3R feature spec 的 `B0-B4` 特征数组必须与原 P3 feature spec 逐字段一致。除版本元数据和时点审计说明外，不得修改任何特征。

固定候选只有：

- `B0_P2_F1_LOGIT`
- `B1_LIQUIDITY_LOGIT`
- `B2_MA30_CONTEXT_LOGIT`
- `B3_CROSS_MARKET_LOGIT`
- `B4_FUNDING_LOGIT`

B0 精确复用 P2 `F1_MA7_PATH`。B1-B4 精确复用原 P3 feature spec，每次只在 B0 上增加一个块。禁止新增 `B_ALL`、组合多个上下文块、删除特征、新增特征、调阈值、使用 LightGBM/ExtraTrees/神经网络、按资产训练模型或训练 long/short 独立头。

每个候选统一使用训练折中位数填充、训练折类别 one-hot、训练折 `StandardScaler`、`LogisticRegression(max_iter=1000, solver='lbfgs', L2, random_state=20260901)`。

## 7. 时间切分与校准

只允许扩展式 walk-forward：

- D1：验证 2022 全年；训练为此前事件，且 `label_end_ts_20d < 2022-01-01`。
- D2：验证 2023 全年；训练为此前事件，且 `label_end_ts_20d < 2023-01-01`。
- D3：验证 2024 年但仅保留 `label_end_ts_20d < 2025-01-01` 的事件；训练为此前事件，且 `label_end_ts_20d < 2024-01-01`。

所有候选必须使用完全相同的样本行。禁止随机拆分、随机 K-fold、打乱样本、按资产随机切分或使用 2025+ early stopping。

概率校准复用 P2 修复后的前向交叉校准：D1 无更早 OOF 保持 raw；D2 只用 D1 已完成标签 OOF；D3 只用 D1-D2 已完成标签 OOF；最终校准器只用 `label_end_ts_20d < 2025-01-01` 的 OOF。raw score 与 forward-calibrated probability 分列保存；AUC 与增量检验使用 raw score，Brier、LogLoss、ECE 与概率阈值使用前向校准概率。

## 8. 评价与裁决

每个候选、每个 fold 必须同时报告训练期与验证期的日期范围、样本数、资产数、long/short、正例率、ROC-AUC、PR-AUC、PR baseline、Brier、Brier skill、LogLoss、ECE10、Top 10% 成功率、Top 10% 成本后净收益均值/中位数、train-validation AUC 差、train-validation Top 10% uplift 差和 overfit warning。

每个 B1-B4 必须相对 B0 报告 paired ROC-AUC 差、PR-AUC 差、Brier skill 差、Top 10% 成功率差、Top 10% 成本后净收益差、fold 方向、worst-fold 差异、macro AUC 差异、20 日 non-overlap AUC 差、long/short、年份、流动性五分位、上市年龄、PIT universe size、波动状态、`sha256(asset)%5` 五组稳定性和新增标准化系数符号稳定性。

使用 28 日 UTC 日期块 paired bootstrap 2,000 次，固定随机种子；四个主增量检验执行 Benjamini-Hochberg 校正并报告 p/q 值。

单块裁决：

- `INCREMENTAL_BLOCK_CONFIRMED`：paired AUC 差点估计大于 0；95% CI 下界大于 0；BH `q < 0.10`；至少 2/3 验证 fold AUC 高于 B0；最差 fold 不比 B0 差超过 0.005；20 日 non-overlap AUC 差大于 0；long/short 任一方向不比 B0 恶化超过 0.01 AUC；最高 10% 成功率及成本后净收益不得同时恶化。
- `SUGGESTIVE_INCREMENT_NOT_CONFIRMED`：点估计为正、至少 2/3 folds 改善，但 CI 包含 0 或 BH 门未通过。
- 其他：`NO_INCREMENT_BEYOND_P2`。

全局裁决只能是 `ONE_OR_MORE_CONTEXT_BLOCKS_CONFIRMED`、`SUGGESTIVE_CONTEXT_INCREMENT_ONLY`、`NO_CONTEXT_INCREMENT_BEYOND_P2`、`DATA_BLOCK_NOT_READY`、`HOLDOUT_CONTAMINATED`、`OBJECTIVE_MISALIGNED`。无论裁决如何，保持 `explore / diagnostic-only / not promoted / not live-ready`。
