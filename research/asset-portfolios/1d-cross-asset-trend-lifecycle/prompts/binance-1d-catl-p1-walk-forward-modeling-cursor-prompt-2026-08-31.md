# 给 Cursor 的完整任务提示：BIN-1D-CATL-P1 跨资产 Walk-Forward 建模

你正在 `/Users/ZK/OpenCode/quant-strategy-lab` 仓库中工作。请完整执行下面的研究任务，不要只给方案；需要实现脚本、运行模型、生成可审计产物、补测试并更新家族文档。

## 一、研究身份与唯一问题

研究家族：`Binance-1D-Cross-Asset-Trend-Lifecycle`（`BIN-1D-CATL`）。

本轮实验名：`P1 Donor-Only Walk-Forward Entry/Continuation Modeling`。

本轮只回答两个统计学习问题：

1. `Entry-value`：每日 UTC 收盘后，对每个资产的 long/short 方向分别判断，从下一 UTC open 开始，未来 20 日内是否更可能先到 `+2 ATR` 而不是 `-1 ATR`。
2. `Continuation-value`：每日 UTC 收盘后，对每个资产的 long/short 方向分别判断，从下一 UTC open 开始，未来 5 日内是否更可能先到 `+1 ATR` 而不是 `-0.75 ATR`。

Entry 和 continuation 必须是两个独立模型、独立样本、独立指标和独立裁决。P1 是建模诊断，不是交易策略，不做仓位、组合回测、开平仓阈值优化、promotion、dry-run 或 live-ready 结论。

## 二、开始前必须读取

先读取并遵守：

1. `/Users/ZK/OpenCode/quant-strategy-lab/AGENTS.md`
2. `/Users/ZK/OpenCode/quant-strategy-lab/research/README.md`
3. `/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/README.md`
4. `/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/1d-cross-asset-trend-lifecycle/README.md`
5. `/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/1d-cross-asset-trend-lifecycle/binance-1d-catl-core-ledger.md`
6. `/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/1d-cross-asset-trend-lifecycle/specs/binance-1d-catl-p0r-modeling-input-repair-contract-2026-08-31.md`
7. `/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/1d-cross-asset-trend-lifecycle/diagnostics/binance-1d-catl-p0r-modeling-input-repair-2026-08-31.md`

先检查 git status；不要覆盖、回滚或清理用户已有改动。

## 三、HYPE 是绝对封存揭示集

这是最高优先级硬约束：

- P1 训练、开发期 walk-forward、特征选择、消融、超参数选择、early stopping、概率校准、阈值或分位点选择、误差分析，全部禁止使用 `HYPE/USDT:USDT` 的任何一行。
- 禁止读取 HYPE 的 K 线、funding、P0/P8 标签、365 日表现、后 81 日表现、交易路径、预测或任何汇总结果。
- 不要把 `HYPER/USDT:USDT` 当成 HYPE；它是另一资产，仍属于 donor。
- P1 不执行 HYPE reveal，也不创建 HYPE 预测文件。HYPE 只能在 P1 模型身份、特征集、超参数、校准器、评价规则和裁决全部冻结后，由后续独立实验一次性揭示。
- 所有 P1 数据输出、OOF 预测和报告必须断言 `asset == 'HYPE/USDT:USDT'` 为 0 行。
- 如果任何 P1 输入或输出出现 HYPE，立即 fail closed 为 `HOLDOUT_CONTAMINATED`，停止研究。

物理输入只允许：

- `/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/p0r_donor_directional_modeling_panel/**/*.parquet`
- `/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/binance_1d_catl_p0r_feature_blocks.json`
- `/Users/ZK/OpenCode/quant-strategy-lab/research/asset-portfolios/1d-cross-asset-trend-lifecycle/artifacts/binance_1d_catl_p0r_manifest.json`

不得回退读取 P0 原始 feature/landmark panel 补字段。开始建模前校验 P0R manifest 内所有哈希、`holdout_read=false`、`hype_asset_excluded='HYPE/USDT:USDT'`、panel 内 HYPE 为 0 行。

## 四、先冻结 P1 合同，再读取标签表现

先创建：

`research/asset-portfolios/1d-cross-asset-trend-lifecycle/specs/binance-1d-catl-p1-donor-walk-forward-modeling-contract-2026-08-31.md`

合同必须逐字冻结本提示中的数据输入、目标、时间切分、模型候选、特征候选、指标、bootstrap、稳定性检查和裁决门。合同落盘并记录 SHA256 后，才能计算分折标签率或运行模型。不得根据结果回改合同；若代码错误只能登记 evidence revision，说明原因后重跑。

## 五、样本与泄漏边界

### Entry 模型

- 只用 `model_eligible_entry_p0r=true`。
- 目标：`label_entry_success_20d`。
- X 只能来自 `binance_1d_catl_p0r_feature_blocks.json` 的 `all_allowed_features`。
- 精确 purge：训练样本必须满足 `label_end_ts_20d < validation_start_ts`，不能只按行数近似。

### Continuation 模型

- 只用 `model_eligible_continue_p0r=true`。
- 目标：`label_continue_success_5d`。
- X 同样只能来自冻结 allowlist。
- 精确 purge：训练样本必须满足 `label_end_ts_5d < validation_start_ts`。

### 通用禁止项

- `asset`、`asset_slug`、`side`、`side_sign`、时间戳、绝对价格、`entry_ref`、`atr_anchor`、资格标记、任何 `label_*`、任何 `future_*`、result、hours-to-hit、净收益、MFE、MAE 都不得进入 X。
- 不得通过文件名、分区名、行号或编码后的资产身份让模型记住币种。
- 所有方向相关特征已经对 long/short 对齐；主模型不使用 `side`。
- 只允许确定性时间切分；禁止 `train_test_split`、随机 K-fold、随机打散后分层。
- 同一 asset-day 的 long/short 两行不得跨集合；时间切分天然同时切走。
- 缺失值处理必须只在每折训练部分拟合，再应用到验证部分；类别字典、标准化器、校准器同理。

## 六、冻结时间结构

所有日期按 UTC：

### 开发 walk-forward（只用于选择模型）

1. Fold D1：validation 为 `2022-01-01` 至 `2022-12-31`；training 使用此前记录，并按各目标 label end 精确 purge。
2. Fold D2：validation 为 `2023-01-01` 至 `2023-12-31`；training 为此前全部记录，并精确 purge。
3. Fold D3：validation 为 `2024-01-01` 至 `2024-12-31`；training 为此前全部记录，并精确 purge。

### donor terminal lockbox

- `2025-01-01` 起至 P0R 中该目标最后一个 eligible 日期，作为一次性 terminal donor OOS。
- 模型族、特征方案、超参数、early-stopping 轮数规则和校准方法只能用 D1-D3 选定。
- 锁定后，用 `label_end_ts < 2025-01-01` 的全部 donor 数据重训一次，再对 2025+ terminal lockbox 预测一次。
- 看过 terminal 结果后禁止重训、换特征、换参数、换校准、换裁决门；失败就如实失败。

不要让 2025/2026 terminal lockbox 参与 early stopping。最终 boosting 轮数使用 D1-D3 各折最佳轮数的中位数，随后在 terminal 训练集固定轮数重训。

## 七、模型和特征方案

固定随机种子 `20260831`；随机性只能来自模型内部和 bootstrap，不能改变数据划分。

### Baseline

每个目标都必须有：

1. `CONST_PRIOR`：仅用当折训练标签率预测。
2. `MA_PROBE_LOGIT`：只用 MA7/MA30 的距离、斜率、穿越、价格同侧和事件 probe；逻辑回归。
3. `G_ONLY_LOGIT`：只用 `ma_geometry` block；带缺失指示、训练折中位数填充、标准化、one-hot 类别，Elastic-Net 或 L2 Logistic Regression。
4. `FULL_LOGIT`：使用全部 allowlist 的同样线性管线。

### 主模型

使用浅层 LightGBM 二分类，目标不是暴力搜参。先固定下面四个候选，禁止扩大搜索空间：

| id | num_leaves | max_depth | min_data_in_leaf | feature_fraction | lambda_l2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| L1 | 15 | 4 | 1000 | 0.75 | 1 |
| L2 | 31 | 6 | 1000 | 0.75 | 3 |
| L3 | 31 | 6 | 3000 | 0.75 | 5 |
| L4 | 63 | 8 | 3000 | 0.90 | 8 |

共同参数：`learning_rate=0.03`、`n_estimators=2000`、`early_stopping_rounds=100`、`bagging_fraction=1.0`、`bagging_freq=0`、固定 seed、CPU deterministic 设置。若环境没有 LightGBM，可以在项目虚拟环境中加入明确依赖，但不要换成其他模型来规避。

开发期选择顺序必须固定：

1. 用完整特征 `FULL` 在 D1-D3 比较 L1-L4，以三折 macro ROC-AUC 为首要、log loss 为并列判据；若差异小于 0.002，选更浅、叶子更少的模型。
2. 锁定 LightGBM 参数后，比较以下冻结特征方案：
   - `G`：`ma_geometry`
   - `GPV`：`ma_geometry + price_path + volatility_and_candle`
   - `FULL`
   - `FULL_NO_EVENT`：FULL 去掉 `event_probes`
   - `FULL_NO_CROSS_MARKET`：FULL 去掉 `cross_market`
3. 只能根据 D1-D3 选择最终特征方案；terminal lockbox 不参与选择。

类别特征只包括 feature spec 中明确列出的 categorical features。不得加入资产类别。

## 八、概率校准

- 开发折必须保存 OOF raw probability。
- 只用 D1-D3 的 OOF 预测拟合一个 Platt calibration；同时报告未校准与已校准指标。
- 不使用 terminal 标签拟合或调整校准器。
- 如果 Platt 在开发 OOF 的 Brier/log loss 都没有改善，则冻结为“不校准”，不能在 terminal 结果出来后改用 isotonic。

## 九、必须报告的指标

每个目标、每个开发折、开发折 macro、terminal 总体都至少报告：

- 样本数、资产数、日期范围、正例率；
- ROC-AUC；
- PR-AUC 与正例率基线；
- log loss、Brier score、Brier skill 相对 `CONST_PRIOR`；
- calibration intercept、slope、10-bin ECE；
- 概率十分位的 n、成功率、相对总体 uplift、`label_*_net_return` 均值和中位数；
- top decile 与 bottom decile 差；
- 相对 `MA_PROBE_LOGIT` 和 `G_ONLY_LOGIT` 的 paired AUC 差；
- long、short 分开；
- 2025、2026 分开；
- 流动性五分位、上市年龄三分位、`volatility_state_p0r` 分层。

经济字段只做“排序诊断”，不是组合回测。不得把单事件净收益简单累加成年化策略收益。

## 十、重叠样本与稳健性

日频 5d/20d 标签高度重叠，普通逐行标准误会虚高。必须同时做：

1. terminal 按连续 28 个 UTC 日为 block 的 paired bootstrap，`1000` 次，固定 seed；同一次重采样必须同时作用于候选模型和 baseline，给 AUC、AUC 差、top-decile uplift、Brier skill 的 95% CI。
2. non-overlap sensitivity：每个 `asset + side` 按时间排序，Entry 每 20 日最多保留一个 landmark，Continuation 每 5 日最多保留一个，再重算核心指标。
3. deterministic leave-asset-group-out：`sha256(asset) % 5` 分五组。对最终参数/特征方案，在 D1-D3 中每次从训练排除一组资产、只在相应未来 validation 的该组资产上评价；报告五组 AUC、中位数、最小值和 top-decile uplift。这个检查不能包含 HYPE。
4. asset-balanced sensitivity：除默认每行等权外，再用每个验证期内资产总行数倒数加权报告 AUC/Brier，防止长历史资产主导。

## 十一、冻结裁决门

Entry 与 continuation 分别裁决，不能互相替代。

### `LEARNABLE_DONOR_SIGNAL`

同时满足：

1. terminal ROC-AUC 的 28d block-bootstrap 95% CI 下界 `> 0.50`；
2. terminal top-decile 成功率 uplift 的 95% CI 下界 `> 0`；
3. terminal Brier skill 相对 CONST_PRIOR `> 0`；
4. non-overlap sensitivity ROC-AUC `> 0.50`；
5. leave-asset-group-out 五组 AUC 中位数 `> 0.52`，且最小值不低于 `0.49`；
6. long 和 short terminal AUC 均不低于 `0.50`，2025 与 2026 分段均不低于 `0.49`。

### `INCREMENTAL_BEYOND_MA`

在通过上面门后，还必须满足：

1. terminal 相对 `G_ONLY_LOGIT` 的 paired AUC 差 95% CI 下界 `> 0`；
2. terminal 相对 `MA_PROBE_LOGIT` 的 paired AUC 差 95% CI 下界 `> 0`；
3. `FULL_NO_CROSS_MARKET` 在 D1-D3 的 macro AUC 比锁定方案至少低 `0.002`，或者 cross-market block 的 permutation importance 在三个开发折方向一致为正。此项只用于判断“跨市场信息是否增量”，不得在 terminal 上二次择优。

最终每个目标只能给以下之一：

- `INCREMENTAL_CROSS_ASSET_SIGNAL`
- `LEARNABLE_BUT_NOT_INCREMENTAL_BEYOND_MA`
- `UNSTABLE_DONOR_SIGNAL`
- `NO_LEARNABLE_DONOR_SIGNAL`
- `HOLDOUT_CONTAMINATED`
- `DATASET_INTEGRITY_FAILED`

无论哪个裁决，整个 P1 都保持 `diagnostic-only / not promoted / not live-ready`。不得为了通过门而改阈值、加杠杆、构造交易规则或查看 HYPE。

## 十二、必须生成的实现和产物

至少创建：

- `scripts/run_binance_1d_catl_p1_donor_walk_forward_modeling.py`
- `tests/test_binance_1d_catl_p1_donor_walk_forward_modeling.py`
- `specs/binance-1d-catl-p1-donor-walk-forward-modeling-contract-2026-08-31.md`
- `diagnostics/binance-1d-catl-p1-entry-model-2026-08-31.md`
- `diagnostics/binance-1d-catl-p1-continuation-model-2026-08-31.md`
- `diagnostics/binance-1d-catl-p1-modeling-audit-2026-08-31.md`
- `artifacts/binance_1d_catl_p1_summary.json`
- `artifacts/binance_1d_catl_p1_fold_metrics.parquet`
- `artifacts/binance_1d_catl_p1_terminal_predictions.parquet`
- `artifacts/binance_1d_catl_p1_oof_predictions.parquet`
- `artifacts/binance_1d_catl_p1_model_card.json`
- `artifacts/binance_1d_catl_p1_manifest.json`

模型二进制可以保存，但必须标明 donor-only、训练截止、特征 hash 和 `not live-ready`。预测文件只允许 donor；manifest 记录合同、脚本、测试、报告、模型卡和核心 artifacts 的 SHA256。

更新本家族 `README.md`、core ledger、decision log 和 artifacts index；不要登记策略版本，不要修改 HYPE P0-P8/V7.1 家族。

## 十三、针对性测试与最终自审

测试至少覆盖：

1. 输入 manifest 哈希完整；
2. P1 输入、OOF、terminal predictions、模型卡中 HYPE 为 0；
3. `HYPER/USDT:USDT` 未被误删；
4. allowlist 外字段不进入 X；
5. Entry/continuation 的 eligibility 和 target 不串用；
6. 每折训练 `max(label_end_ts) < validation_start_ts`；
7. 2025+ terminal 从未参与模型/特征/参数/校准选择；
8. 所有预处理只在训练折 fit；
9. OOF 每行只被预测一次且没有 train/validation 重叠；
10. paired bootstrap 使用相同重采样索引；
11. 模型结果可由 summary、fold metrics 和 predictions 对账；
12. 没有策略回测、仓位或 live-ready artifact。

运行新增 targeted tests，并回归运行 P0/P0R tests。若运行中发现实现问题，先修复并重跑；若是研究门失败，不能“优化到通过”，必须如实登记失败。

## 十四、最终回复格式

用中文，结论先行，分别汇报 Entry 与 continuation：

1. 最终裁决；
2. 开发期 D1-D3 样本内/样本外表现；
3. 2025+ terminal donor OOS 表现及 bootstrap CI；
4. 相对 MA baseline 是否有增量；
5. long/short、年份、资产组是否稳定；
6. 模型最依赖的 feature blocks，但不要把重要性误写成因果；
7. HYPE 隔离证明；
8. 为什么仍然不是交易策略；
9. 所有关键文件的可点击绝对路径；
10. 精确复现命令和测试命令。

如果 P1 donor 证据通过，也只能建议“可以进入独立 P2 HYPE one-shot reveal”；本轮绝对不要提前揭示 HYPE。
