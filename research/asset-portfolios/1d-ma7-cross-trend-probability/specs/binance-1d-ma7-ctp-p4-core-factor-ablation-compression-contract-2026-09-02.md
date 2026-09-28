# BIN-1D-MA7-CTP P4 Core Factor Ablation + Compressed Tail-Ranking Audit 合同

- Family：`Binance-1D-MA7-Cross-Trend-Probability`（`BIN-1D-MA7-CTP`）
- Experiment：`P4 Core Factor Ablation + Compressed Tail-Ranking Audit`
- 中文名：`P4 MA7核心因子消融、模型压缩与高分穿越稳定性审计`
- 日期：2026-09-02
- 固定随机种子：`20260901`
- 状态：`explore / diagnostic-only / not promoted / not live-ready`
- 本合同在读取 P4 标签率、AUC、Top 10% 或任何消融结果之前冻结。P4 是 P2/P3R 之后的独立诊断实验，不覆盖 P0、P1、P2、P3 或 P3R。

## 1. 唯一研究问题

P4 只研究：一个资产在完整 UTC 日 K 收盘时发生严格 MA7 方向穿越后，从下一 UTC 日 open 开始，未来 20 日是否先顺向达到 `+2 ATR`，而不是先逆向达到 `-1 ATR`。

P4 回答 P2 B0 的 69 个 `F1_MA7_PATH` 特征中哪些因子组对样本外排序和 fold-relative 最高 10% 穿越识别必要，哪些在当前线性模型和相关特征共存时可删除，以及 `M_EVENT_25` 或 `M_EVENT_VOL_36` 能否作为未来全新 OOS 的压缩候选。`2022-2024 IS REUSED DEVELOPMENT HISTORY, NOT NEW BLIND OOS`。

P4 不是新特征搜索、不是 MA30 或一般 asset-day 模型、不是 LightGBM 搜索、不是退出/continuation/反手/账户回测，也不是策略版本或 live-ready 实验。

## 2. 唯一允许输入

只允许读取：

1. `../1d-cross-asset-trend-lifecycle/artifacts/p0r_donor_directional_modeling_panel/**/*.parquet`
2. `../1d-cross-asset-trend-lifecycle/artifacts/binance_1d_catl_p0r_feature_blocks.json`
3. `../1d-cross-asset-trend-lifecycle/artifacts/binance_1d_catl_p0r_manifest.json`
4. `artifacts/binance_1d_ma7_ctp_p2_feature_spec.json`
5. `artifacts/binance_1d_ma7_ctp_p2_summary.json`
6. `artifacts/binance_1d_ma7_ctp_p2_model_card.json`
7. `artifacts/binance_1d_ma7_ctp_p3r_feature_spec.json`
8. `artifacts/binance_1d_ma7_ctp_p3r_summary.json`
9. `artifacts/binance_1d_ma7_ctp_p3r_model_card.json`
10. P2、P3R 脚本与测试，仅作为预处理、切分、校准、bootstrap 和审计实现参考。

禁止读取或使用 HYPE K 线、标签、预测、交易路径、P0-P8/V7.1 结果、P1 的 2025+ 历史预测文件或任何 2025+ 事件进行训练、校准、选模或预测。

## 3. 样本与时间门禁

事件过滤固定为：

```text
probe_raw_ma7_cross_dir == true
AND model_eligible_entry_p0r == true
AND ts < 2025-01-01 00:00:00 UTC
AND label_end_ts_20d < 2025-01-01 00:00:00 UTC
```

必须复现：

- 原始 pre-2025 MA7 事件：`54,137`
- 严格样本：`52,563`
- 资产：`338`
- long：`26,237`
- short：`26,326`
- 最早事件：`2019-11-27`
- 最晚事件：`2024-12-10`
- 最大 `label_end_ts_20d`：`2024-12-31`
- 正例率约 `32.53%`
- 非 MA7 穿越、重复 `asset+ts`、空标签、不完整 20 日路径、HYPE、已知 TradFi 严格事件均为 `0`

时间门禁固定为：

```text
feature_known_at == entry_ts
entry_ts == ts + 1 day
feature_known_at == ts + 1 day
feature_known_at < entry_ts: 0
feature_known_at > entry_ts: 0
```

任一数据审计失败，立即裁决 `DATA_BLOCK_NOT_READY`；若 HYPE 出现在输入、严格事件、OOF 或模型卡，裁决 `HOLDOUT_CONTAMINATED`；若事件、标签或模型目标偏离 MA7 穿越入场概率研究，裁决 `OBJECTIVE_MISALIGNED`。

## 4. 冻结六个因子组

P4 将 P2 B0 的 69 个 `F1_MA7_PATH` 特征完整、无重复地划分为六组，六组并集必须精确等于 P2 原始字段顺序：

- `G1_T1_MA7_STATE`：前一日 MA7 状态，12 个。
- `G2_EVENT_GEOMETRY`：穿越日 MA7 与 K 线几何，13 个。
- `G3_VOLATILITY_STATE`：当前及前一日波动状态，11 个。
- `G4_VOLUME_ACTIVITY`：成交活跃度，5 个。
- `G5_T1_MOMENTUM_LOCATION`：前置动量与区间位置，21 个。
- `G6_T1_PATH_REGIME`：前置路径效率与状态，7 个。

必须断言 `12 + 13 + 11 + 5 + 21 + 7 = 69`。factor group spec 必须保存每组字段、字段数量、P2 原始字段顺序、并集一致性、重复字段检查、缺失字段检查、额外字段检查和 SHA256。

## 5. 冻结候选模型

候选集合在读标签前冻结，不得按结果新增组合。

| Candidate | 角色 | 特征 |
| --- | --- | --- |
| `R_FULL_B0_69` | 参考模型 | `G1+G2+G3+G4+G5+G6` |
| `D_NO_G1_T1_MA7` | 删除式消融 | 删除 `G1_T1_MA7_STATE` |
| `D_NO_G2_EVENT_GEOMETRY` | 删除式消融 | 删除 `G2_EVENT_GEOMETRY` |
| `D_NO_G3_VOLATILITY` | 删除式消融 | 删除 `G3_VOLATILITY_STATE` |
| `D_NO_G4_VOLUME` | 删除式消融 | 删除 `G4_VOLUME_ACTIVITY` |
| `D_NO_G5_T1_MOMENTUM_LOCATION` | 删除式消融 | 删除 `G5_T1_MOMENTUM_LOCATION` |
| `D_NO_G6_T1_PATH_REGIME` | 删除式消融 | 删除 `G6_T1_PATH_REGIME` |
| `O_G1_T1_MA7_ONLY` | 单组解释 | 仅 `G1_T1_MA7_STATE` |
| `O_G2_EVENT_GEOMETRY_ONLY` | 单组解释 | 仅 `G2_EVENT_GEOMETRY` |
| `O_G3_VOLATILITY_ONLY` | 单组解释 | 仅 `G3_VOLATILITY_STATE` |
| `O_G4_VOLUME_ONLY` | 单组解释 | 仅 `G4_VOLUME_ACTIVITY` |
| `O_G5_T1_MOMENTUM_LOCATION_ONLY` | 单组解释 | 仅 `G5_T1_MOMENTUM_LOCATION` |
| `O_G6_T1_PATH_REGIME_ONLY` | 单组解释 | 仅 `G6_T1_PATH_REGIME` |
| `M_EVENT_25` | 预注册压缩 | `G1+G2`，25 个 |
| `M_EVENT_VOL_36` | 预注册压缩 | `G1+G2+G3`，36 个 |

单组模型只解释独立预测能力，不用于选择最终模型。禁止根据删除式消融结果事后拼新压缩模型。

## 6. 模型与预处理

所有候选统一使用 pooled direction-aligned 模型、训练折数值中位数填充、训练折类别 one-hot、`StandardScaler`、`LogisticRegression(penalty='l2', solver='lbfgs', max_iter=1000, random_state=20260901)`。若候选不含 `t1_volatility_state_p0r`，不得创建该类别列。

禁止独立 long/short 模型、调 `C`、调 penalty/solver、自动特征选择、L1/ElasticNet、交互项、多项式特征、LightGBM/XGBoost/ExtraTrees/随机森林/神经网络。

## 7. 时间 walk-forward 与 Top 10%

保持与 P2/P3R 一致：

| Fold | Validation | Training |
| --- | --- | --- |
| `D1` | 2022 全年 | `label_end_ts_20d < 2022-01-01` 的此前事件 |
| `D2` | 2023 全年 | `label_end_ts_20d < 2023-01-01` 的此前事件 |
| `D3` | 2024 年，且标签在 2025 前结束 | `label_end_ts_20d < 2024-01-01` 的此前事件 |

所有候选每折必须使用完全相同训练行和验证行。主要 Top 10% 按验证 fold 内 raw score 百分位定义：`score_percentile >= 0.90`；报告时再合并三折最高 10%。必须保存 raw probability、fold-relative percentile、fold-relative decile 和 forward-calibrated probability。额外的 pooled raw Top 10% 只能标注为 `legacy pooled-raw diagnostic`，不得作为 P4 主裁决依据。

## 8. 前向概率校准

复用 P2/P3R 修复后的前向校准：D1 无更早 OOF 保持 raw；D2 只用 D1 已完成标签 OOF；D3 只用 D1-D2 已完成标签 OOF。当前 fold 和未来 fold 不得进入校准器。raw score 与 forward-calibrated probability 分列保存；排序、AUC 和 Top 10% 使用 raw/fold-relative percentile；Brier、LogLoss、ECE 和概率阈值使用 forward-calibrated probability。

## 9. 评价、bootstrap 与裁决

主要指标按优先顺序为 fold-relative Top 10% 成功率、相对全体事件 uplift、成本后事件净收益均值和中位数、三折最差 Top 10% 成功率、三折 Top 10% 成功率标准差。次要指标包括每折 ROC-AUC、Macro ROC-AUC、PR-AUC、Brier、Brier skill、LogLoss、ECE10、asset-balanced AUC、20 日 non-overlap AUC/Top 10%、bottom 10%、top-bottom 差、训练-验证差距、overfit warning、long/short、年份、资产五组和 `time walk-forward × leave-asset-group-out` 15 单元。

六个删除式模型相对 `R_FULL_B0_69` 做同样本 paired 比较，使用每 fold 内 28 日 UTC 日期块 bootstrap，2,000 次，固定随机种子，并对六个删除式主检验做 Benjamini-Hochberg 校正。单组模型和两个压缩模型与删除式主检验分开。

因子组裁决只允许：`REQUIRED_DEVELOPMENT_EVIDENCE`、`HARMFUL_OR_NOISY_DEVELOPMENT_EVIDENCE`、`REMOVABLE_NONINFERIOR`、`INCONCLUSIVE_FACTOR_ROLE`。压缩裁决只允许：通过时 `COMPRESSED_CANDIDATE_NONINFERIOR_DEVELOPMENT_ONLY`，否则记录未通过原因。全局裁决只允许：`COMPRESSED_CORE_CANDIDATE_FROZEN`、`FULL_B0_REMAINS_REFERENCE`、`PARTIAL_REDUNDANCY_IDENTIFIED_NO_LOCKED_COMPRESSION`、`NO_STABLE_FACTOR_STRUCTURE`、`DATA_BLOCK_NOT_READY`、`HOLDOUT_CONTAMINATED`、`OBJECTIVE_MISALIGNED`。

非劣门槛冻结为：

- Macro AUC 差 95% CI 下界不低于 `-0.003`
- fold-relative Top 10% 成功率差 95% CI 下界不低于 `-0.010`
- Top 10% 净收益均值差 95% CI 下界不低于 `-0.002`
- 最差 fold AUC 差不低于 `-0.005`
- long/short AUC 差均不低于 `-0.010`
- 压缩模型额外要求 20 日 non-overlap AUC 差不低于 `-0.005`、至少两个年份 Top 10% 成功率不低于 B0、训练-验证 AUC gap 不比 B0 扩大超过 `0.01`、资产 holdout 不明显恶化。

事件收益仅解释为独立 first-hit 事件结果，不复利、不代表组合收益、不代表账户收益、不计算年化或 Sharpe。

## 10. 输出边界

机器产物统一前缀 `binance_1d_ma7_ctp_p4_`。P4 必须生成合同锁、factor group spec、fold metrics、OOF predictions、ablation comparisons、only group metrics、asset holdout metrics、decile metrics、coefficient stability、model card、summary 和 manifest。P4 不生成策略仓位、权益曲线、live spec、runner handoff 或交易路径 HTML。
