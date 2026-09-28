# BIN-1D-CATL-P1 Donor-Only Walk-Forward 建模合同

## 1. 身份、问题与状态

- Family：`Binance-1D-Cross-Asset-Trend-Lifecycle`（`BIN-1D-CATL`）。
- Experiment：`P1 Donor-Only Walk-Forward Entry/Continuation Modeling`。
- 固定随机种子：`20260831`。
- Entry-value：每日 UTC 收盘后，对每个 donor 资产的 long/short 方向分别判断，从下一 UTC open 开始，未来 20 日内是否先到 `+2 ATR` 而不是 `-1 ATR`。
- Continuation-value：每日 UTC 收盘后，对每个 donor 资产的 long/short 方向分别判断，从下一 UTC open 开始，未来 5 日内是否先到 `+1 ATR` 而不是 `-0.75 ATR`。
- Entry 与 continuation 是两个独立模型、独立样本、独立指标和独立裁决。
- P1 只做统计建模诊断，不做仓位、组合回测、开平仓阈值优化、promotion、dry-run 或 live-ready 结论；状态固定为 `explore / diagnostic-only / not promoted / not live-ready`。

## 2. 唯一输入与完整性门

物理数据输入只允许：

1. `artifacts/p0r_donor_directional_modeling_panel/**/*.parquet`
2. `artifacts/binance_1d_catl_p0r_feature_blocks.json`
3. `artifacts/binance_1d_catl_p0r_manifest.json`

禁止回退读取 P0 原始 feature/landmark panel、normalized K 线、funding 或其他研究产物补字段。建模前必须逐项验证 P0R manifest 的全部 artifact SHA256、`holdout_read=false`、`hype_asset_excluded='HYPE/USDT:USDT'`、P0 输入血缘哈希与 donor panel 中 HYPE 为 0 行；任一失败立即裁决 `DATASET_INTEGRITY_FAILED` 或 `HOLDOUT_CONTAMINATED` 并停止。

## 3. HYPE terminal holdout 绝对封存

- P1 任一阶段均禁止读取或使用 `HYPE/USDT:USDT` 的任何 K 线、funding、P0/P8 标签、365 日/后 81 日表现、交易路径、预测或汇总结果。
- P1 训练、开发 walk-forward、特征选择、消融、超参数选择、early stopping、概率校准、阈值/分位点选择及误差分析均不得出现 HYPE。
- `HYPER/USDT:USDT` 是不同 donor 资产，必须保留。
- P1 不执行 HYPE reveal，不创建 HYPE 预测文件。HYPE 只能在模型身份、特征集、超参数、校准器、评价规则和裁决全部冻结后，由后续独立实验一次性揭示。
- P1 的任何输入、OOF、terminal prediction、summary、model card 或报告中一旦发现 HYPE，立即 fail closed 为 `HOLDOUT_CONTAMINATED`。

## 4. 样本、目标与泄漏边界

### Entry

- 资格：仅 `model_eligible_entry_p0r=true`。
- 目标：`label_entry_success_20d`。
- 经济排序诊断：`label_entry_net_return`，不得进入 X。
- 精确 purge：每折训练样本必须满足 `label_end_ts_20d < validation_start_ts`。

### Continuation

- 资格：仅 `model_eligible_continue_p0r=true`。
- 目标：`label_continue_success_5d`。
- 经济排序诊断：`label_continue_net_return`，不得进入 X。
- 精确 purge：每折训练样本必须满足 `label_end_ts_5d < validation_start_ts`。

### 共同边界

- X 只能来自 P0R feature spec 的 `all_allowed_features`。
- `asset`、`asset_slug`、`side`、`side_sign`、时间戳、绝对价格、`entry_ref`、`atr_anchor`、资格标记、任何 `label_*`、任何 `future_*`、result、hours-to-hit、净收益、MFE、MAE 不得进入 X。
- 不得通过文件名、分区名、行号或编码资产身份让模型记住币种；主模型不使用 `side`。
- 只允许确定性时间切分；禁止 `train_test_split`、随机 K-fold 或随机打散分层。
- 同一 asset-day 的 long/short 两行必须由时间边界一起切分。
- 缺失值处理、类别字典、标准化器与校准器只能在各自训练数据上拟合。

## 5. 冻结时间结构

所有日期为 UTC：

| Fold | validation | training |
| --- | --- | --- |
| `D1` | `2022-01-01` 至 `2022-12-31` | 此前 eligible 记录，按目标 `label_end_ts` 精确 purge |
| `D2` | `2023-01-01` 至 `2023-12-31` | 此前全部 eligible 记录，按目标精确 purge |
| `D3` | `2024-01-01` 至 `2024-12-31` | 此前全部 eligible 记录，按目标精确 purge |

- donor terminal lockbox：`2025-01-01` 至 P0R 中该目标最后 eligible 日期。
- 模型族、特征方案、超参数、early-stopping 轮数规则与校准方法只能用 D1-D3 选择。
- 锁定后，用 `label_end_ts < 2025-01-01` 的全部 donor eligible 数据重训一次，再且仅再对 terminal 预测一次。
- terminal 不参与 early stopping。最终 boosting 轮数取 D1-D3 对锁定参数与特征方案所得最佳轮数的中位数，然后固定轮数重训。
- 看过 terminal 结果后禁止重训、换特征、换参数、换校准或换裁决门。

## 6. 冻结 baseline

每个目标均实现：

1. `CONST_PRIOR`：仅用当折训练标签率预测。
2. `MA_PROBE_LOGIT`：只用 MA7/MA30 的距离、斜率、穿越、价格同侧及 event probe；逻辑回归。
3. `G_ONLY_LOGIT`：只用 `ma_geometry` block；缺失指示、训练折中位数填充、标准化、明确类别 one-hot，L2 Logistic Regression。
4. `FULL_LOGIT`：全部 allowlist，使用相同线性预处理与 L2 Logistic Regression。

线性管线的数值/类别列由冻结 feature spec 确定，不能加入资产类别。

## 7. 冻结 LightGBM 候选与选择顺序

共同参数：

- `objective=binary`
- `learning_rate=0.03`
- `n_estimators=2000`
- `early_stopping_rounds=100`
- `bagging_fraction=1.0`
- `bagging_freq=0`
- `random_state=20260831`
- CPU deterministic 设置，禁止更换模型规避 LightGBM 依赖。

| id | num_leaves | max_depth | min_data_in_leaf | feature_fraction | lambda_l2 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `L1` | 15 | 4 | 1000 | 0.75 | 1 |
| `L2` | 31 | 6 | 1000 | 0.75 | 3 |
| `L3` | 31 | 6 | 3000 | 0.75 | 5 |
| `L4` | 63 | 8 | 3000 | 0.90 | 8 |

开发期选择顺序固定：

1. 用 `FULL` 在 D1-D3 比较 L1-L4，以三折 macro ROC-AUC 为首要、macro log loss 为并列判据；与最佳 AUC 差异小于 `0.002` 时选更浅、叶子更少的模型。
2. 锁定 LightGBM 参数后，只比较：`G`、`GPV=ma_geometry+price_path+volatility_and_candle`、`FULL`、`FULL_NO_EVENT=FULL-event_probes`、`FULL_NO_CROSS_MARKET=FULL-cross_market`。
3. 只能根据 D1-D3 锁定最终特征方案；terminal 不参与选择。

类别特征严格等于 P0R feature spec 的 `categorical_features`；不得新增资产类别。

## 8. 概率校准

- 保存 D1-D3 OOF raw probability。
- 只用 D1-D3 OOF raw probability 与标签拟合一个 Platt calibration。
- 同时报告 raw 与 calibrated 指标。
- 若 Platt 在开发 OOF 的 Brier 与 log loss 未同时形成至少一项改善且另一项不恶化，则冻结为 `none`；不得在 terminal 后改用 isotonic。
- terminal 标签不得拟合或调整校准器。

## 9. 冻结评价指标

每个目标、每个开发折、开发折 macro 与 terminal 总体至少报告：

- 样本数、资产数、日期范围、正例率；
- ROC-AUC；
- PR-AUC 与正例率基线；
- log loss、Brier、相对 `CONST_PRIOR` 的 Brier skill；
- calibration intercept、slope、10-bin ECE；
- 概率十分位的 n、成功率、相对总体 uplift、对应 `label_*_net_return` 均值与中位数；
- top decile 与 bottom decile 成功率差；
- 相对 `MA_PROBE_LOGIT`、`G_ONLY_LOGIT` 的 paired AUC 差；
- long/short 分层；
- terminal 的 2025/2026 分层；
- 流动性五分位、上市年龄三分位及 `volatility_state_p0r` 分层。

经济字段仅作排序诊断，不得把独立重叠事件净收益累加或年化为策略收益。

## 10. 重叠样本与稳定性

1. terminal 以连续 28 个 UTC 日为 block 做 `1000` 次 paired bootstrap，seed=`20260831`。同一重采样索引必须同时作用于候选模型和全部 baseline，给出 AUC、相对 baseline AUC 差、top-decile uplift、Brier skill 的 95% percentile CI。
2. non-overlap sensitivity：每个 `asset+side` 按时间排序，Entry 每 20 日最多保留一个 landmark，Continuation 每 5 日最多保留一个，重算核心指标。
3. deterministic leave-asset-group-out：按 `int(sha256(asset).hexdigest(),16) % 5` 分组。对最终参数/特征方案，在 D1-D3 中每次从训练排除一组资产，只在相应未来 validation 的该组资产评价；报告五组 AUC、中位数、最小值与 top-decile uplift；不得包含 HYPE。
4. asset-balanced sensitivity：默认每行等权外，再按每个验证期内资产总行数倒数加权报告 AUC 与 Brier。
5. 开发折 cross-market permutation importance：对锁定模型和锁定方案，在每个 D1-D3 validation 上使用确定性 permutation；记录 cross-market block 总体 AUC decrease 的方向，作为增量裁决第三项的备选证据。

## 11. 冻结裁决门

Entry 与 continuation 分开裁决。

### `LEARNABLE_DONOR_SIGNAL`

必须同时满足：

1. terminal ROC-AUC 的 28d block-bootstrap 95% CI 下界 `> 0.50`；
2. terminal top-decile 成功率 uplift 的 95% CI 下界 `> 0`；
3. terminal Brier skill 相对 `CONST_PRIOR` `> 0`；
4. non-overlap ROC-AUC `> 0.50`；
5. leave-asset-group-out 五组 AUC 中位数 `> 0.52` 且最小值 `>= 0.49`；
6. long、short terminal AUC 均 `>= 0.50`，2025、2026 分段均 `>= 0.49`。

### `INCREMENTAL_BEYOND_MA`

在通过 learnable 门后还必须满足：

1. terminal 相对 `G_ONLY_LOGIT` paired AUC 差的 95% CI 下界 `> 0`；
2. terminal 相对 `MA_PROBE_LOGIT` paired AUC 差的 95% CI 下界 `> 0`；
3. `FULL_NO_CROSS_MARKET` 的 D1-D3 macro AUC 比锁定方案至少低 `0.002`，或 cross-market block permutation importance 在 D1-D3 三折方向一致为正。

最终每个目标只能裁决为：

- `INCREMENTAL_CROSS_ASSET_SIGNAL`
- `LEARNABLE_BUT_NOT_INCREMENTAL_BEYOND_MA`
- `UNSTABLE_DONOR_SIGNAL`
- `NO_LEARNABLE_DONOR_SIGNAL`
- `HOLDOUT_CONTAMINATED`
- `DATASET_INTEGRITY_FAILED`

映射规则：数据/隔离失败优先；learnable 六项全通过且 incremental 三项全通过为 `INCREMENTAL_CROSS_ASSET_SIGNAL`；仅 learnable 全通过为 `LEARNABLE_BUT_NOT_INCREMENTAL_BEYOND_MA`；有正向总体排序但任一稳定性门失败为 `UNSTABLE_DONOR_SIGNAL`；否则为 `NO_LEARNABLE_DONOR_SIGNAL`。

## 12. 冻结输出与审计

必须生成：

- `scripts/run_binance_1d_catl_p1_donor_walk_forward_modeling.py`
- `tests/test_binance_1d_catl_p1_donor_walk_forward_modeling.py`
- Entry、Continuation 与 Modeling Audit 三份中文 diagnostics
- summary、fold metrics、terminal predictions、OOF predictions、model card 与 manifest

预测文件只允许 donor；model card 必须标明 donor-only、训练截止、feature hash 与 `not live-ready`。manifest 必须记录本合同、合同哈希锁、脚本、测试、报告、模型卡和核心 artifacts 的 SHA256。

## 13. evidence revision 纪律

本合同落盘并记录 SHA256 后，才允许计算分折标签率或运行模型。任何研究结果不得反向修改合同；若发现实现错误，只能在 audit 与 decision log 登记 evidence revision 原因，修复脚本后按原合同完整重跑。
