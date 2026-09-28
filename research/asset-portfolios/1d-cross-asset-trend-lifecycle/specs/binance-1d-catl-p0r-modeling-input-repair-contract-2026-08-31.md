# BIN-1D-CATL-P0R 建模输入修复合同

## 1. 身份与目的

- Family：`Binance-1D-Cross-Asset-Trend-Lifecycle`（`BIN-1D-CATL`）。
- Evidence revision：`P0R Modeling Input Repair`；它不是策略版本，也不是 P1 模型。
- 目的：保留 P0 标签原始证据不变，修复进入 P1 前发现的因果特征、横截面排名和异常价格尺度资格问题，输出一份物理隔离 HYPE 的 donor-only 建模面板。
- 状态：`diagnostic-only / not promoted / not live-ready`。

## 2. 冻结输入与禁止覆盖

- 输入只能来自：
  - `artifacts/p0_asset_day_feature_panel/**/*.parquet`
  - `artifacts/p0_directional_landmark_panel/**/*.parquet`
- P0 原始 panel、summary、manifest、HTML 和报告全部只读，不得覆盖或回写。
- 全局数据截止仍为 `< 2026-05-31 00:00 UTC`；不得读取 HYPE 后 81 日冻结验证期。
- P0R manifest 必须记录 P0 manifest 的 SHA256，形成输入血缘。

## 3. HYPE 封存揭示边界

- 精确封存资产：`HYPE/USDT:USDT`；`HYPER/USDT:USDT` 是另一资产，不得误删。
- P0R donor panel 中 `HYPE/USDT:USDT` 必须为 0 行。
- HYPE 不参与 donor 横截面市场状态、流动性排名、训练、验证、特征筛选、超参数选择、概率校准、阈值选择或误差分析。
- P1 锁模前不得生成任何 HYPE 预测、标签表现或按 HYPE 调整的结果。
- HYPE 只允许在后续独立 reveal 实验中一次性揭示；该 reveal 不属于 P0R 或 P1。

## 4. 三项冻结修复

### 4.1 因果波动状态

P0 的 `volatility_state` 使用单资产完整历史分位排名，会让过去样本间接使用未来分布，因此禁止进入 P1。

P0R 定义：

- 对每个 donor asset 按 `ts` 排序；
- 仅使用当前行之前的 `atr14_pct`，计算 expanding 1/3 与 2/3 分位数；
- 历史有效观察少于 30 条时标记 `insufficient_history`；
- 否则当前 `atr14_pct <= q33` 为 `low`，`<= q67` 为 `mid`，其余为 `high`；
- 字段名为 `volatility_state_p0r`；原 `volatility_state` 不得出现在 P1 feature allowlist。

### 4.2 donor-only PIT 横截面

- 横截面集合只含当日 `tradable_marker_p0=true` 且资产不是 HYPE 的 donor。
- 在该集合上重新计算：`pit_universe_size_p0r`、MA7/MA30 breadth、1 日上涨比例、1 日收益离散度、7/30 日市场收益中位数和 `liquidity_rank_pct_p0r`。
- 非 tradable donor 的 `liquidity_rank_pct_p0r` 必须为空。
- P0 的原 `liquidity_rank_pct` 和原市场聚合字段不得进入 P1 feature allowlist。

### 4.3 模型资格与价格尺度异常

P0R 不删除标签行，先生成透明资格标记：

```text
base_model_eligible_p0r =
    tradable_marker_p0
    AND entry_ref > 0
    AND atr_anchor > 0
    AND atr_anchor / entry_ref <= 0.50
    AND abs(ret_1d) <= 3.00
```

- `atr_to_entry_p0r = atr_anchor / entry_ref`。
- `price_scale_discontinuity_p0r = abs(ret_1d) > 3.00`。
- `extreme_atr_scale_p0r = atr_to_entry_p0r > 0.50`。
- `model_eligible_entry_p0r = base_model_eligible_p0r AND future_path_complete_20d`。
- `model_eligible_continue_p0r = base_model_eligible_p0r AND future_path_complete_5d`。
- 3.00 单日绝对收益和 0.50 ATR/entry 上限属于数据质量/经济尺度门，不得根据模型表现回调。

## 5. 输出结构

- `artifacts/p0r_donor_directional_modeling_panel/`：按 `year/side_partition` 分区的 donor-only directional panel。
- `artifacts/binance_1d_catl_p0r_feature_blocks.json`：P1 允许特征块、身份字段、标签字段和禁止字段。
- `artifacts/binance_1d_catl_p0r_summary.json`：修复前后 donor 样本数、资格排除原因和逐方向标签分布；不得包含 HYPE 标签表现。
- `artifacts/binance_1d_catl_p0r_manifest.json`：输入血缘及输出 SHA256。
- `diagnostics/binance-1d-catl-p0r-modeling-input-repair-2026-08-31.md`：中文审计结论。

## 6. P1 使用边界

- P1 只能读取 P0R donor panel 和 P0R feature allowlist，不能回退读取 P0 panel 来补特征。
- Entry 与 continuation 必须分别建模；不得将 future path、first-hit、MFE/MAE、净收益或任何 `label_*` 字段放入 X。
- 时间拆分必须 walk-forward，并按标签最大观察窗执行 purge/embargo；禁止随机拆分。
- P1 只回答“跨资产可学习性和概率排序是否稳定”，不形成仓位、交易回测或 live-ready 结论。

## 7. 通过条件

全部满足才可裁决 `MODELING_INPUT_READY`：

1. P0 文件未改变且 P0 manifest 哈希匹配；
2. donor panel 中 HYPE 为 0 行；
3. `volatility_state_p0r` 对每行只使用更早历史；
4. 流动性排名只在 donor tradable PIT 集合内计算，非 tradable 行为空；
5. 资格标记可由原始字段逐行重建；
6. 输出中不存在 cutoff 后记录；
7. targeted tests 全部通过。

任一失败则裁决 `DATASET_INTEGRITY_FAILED`，不得进入 P1。
