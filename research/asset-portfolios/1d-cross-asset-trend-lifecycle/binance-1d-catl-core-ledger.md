# Binance-1D-CATL Core Ledger

## Family Identity

- Full family name：`Binance-1D-Cross-Asset-Trend-Lifecycle`
- Alias：`BIN-1D-CATL`
- 市场/周期：Binance USD-M USDT 永续合约全市场，完整 UTC 日 K。
- 机制边界：每日收盘后构造跨资产归一化特征，对 long/short 两个方向分别生成下一 UTC open 后的趋势 entry/continuation first-hit 标签。
- 碰撞警告：不是 HYPE MA7 机器学习家族，不继承或修改 HYPE P0-P8/V7.1；MA7/MA30 只作 causal feature 与 diagnostic probe。

## Current State

- 当前实验：`P1 Donor-Only Walk-Forward Entry/Continuation Modeling` 已完成。
- 主状态：`explore / diagnostic-only / not promoted / not live-ready`
- P0 裁决：`DATASET_READY_FOR_MODELING_RESEARCH`
- P0R 裁决：`MODELING_INPUT_READY`
- P1 Entry / Continuation 裁决均为：`LEARNABLE_BUT_NOT_INCREMENTAL_BEYOND_MA`；两者通过 donor learnability 门，但 cross-market 增量门失败。
- 运行/交接状态：无 runner、无 dry-run、无 live spec、无 handoff overlay。
- 隔离状态：P1 输入、OOF、terminal prediction 与模型卡中 `HYPE/USDT:USDT` 均为 0 行；`HYPER/USDT:USDT` 保留；HYPE 未 reveal。
- 下一决策门：如用户另行授权，只能按已锁 P1 身份进入独立 P2 HYPE one-shot reveal；本轮不自动启动。

## Version Rules

- `P0/P1/...` 表示研究实验，不是可交易策略版本。
- 只有用户明确要求“登记/冻结 Vx”时才创建 registered strategy version；P0 数据集本身不登记为策略。
- 未来若修改标签定义、数据截断、资产资格或核心 feature schema，应新开 `P1` 或新的 evidence revision，不覆盖 P0 裁决。

## Version Table

| 版本/观察 | 状态 | 角色/核心内容 | 关键冻结指标 | 证据 | 决策与 live-readiness |
| --- | --- | --- | --- | --- | --- |
| `P0 Dataset and Label Atlas` | `explore / diagnostic-only / not promoted / not live-ready` | 全市场 daily causal feature panel + long/short directional first-hit label atlas | 733 资产；564,805 asset-day；1,129,610 landmarks；完整 20d entry 1,004,106；完整 5d continuation 1,024,804；entry 成功率 29.71%；continuation 成功率 34.75% | [合同](specs/binance-1d-catl-p0-dataset-label-atlas-contract-2026-08-31.md)、[数据质量](diagnostics/binance-1d-catl-p0-data-quality-2026-08-31.md)、[标签分布](diagnostics/binance-1d-catl-p0-label-distribution-2026-08-31.md)、[summary](artifacts/binance_1d_catl_p0_summary.json)、[manifest](artifacts/binance_1d_catl_p0_manifest.json) | 数据集可进入下一轮 modeling research；不代表策略、不给 live-ready 结论 |
| `P0R Modeling Input Repair` | `explore / diagnostic-only / not promoted / not live-ready` | 不覆盖 P0；修复非因果波动分档、错误流动性排名和极端价格尺度资格，输出 HYPE-free donor panel | 732 donor；1,128,880 landmarks；合格完整 entry 933,002；合格完整 continuation 950,490；HYPE 0 行 | [合同](specs/binance-1d-catl-p0r-modeling-input-repair-contract-2026-08-31.md)、[修复报告](diagnostics/binance-1d-catl-p0r-modeling-input-repair-2026-08-31.md)、[summary](artifacts/binance_1d_catl_p0r_summary.json)、[manifest](artifacts/binance_1d_catl_p0r_manifest.json) | `MODELING_INPUT_READY`；只允许 donor-only P1，HYPE 封存待一次性 reveal |
| `P1 Donor-Only Walk-Forward Modeling` | `explore / diagnostic-only / not promoted / not live-ready` | Entry 与 Continuation 独立 donor 时间 walk-forward、terminal lockbox 与稳定性裁决 | Entry terminal AUC 0.5698、95% CI [0.5344, 0.6066]；Continuation 0.5661、[0.5448, 0.5895]；两者 top uplift 与 Brier skill 为正，但 cross-market 增量门均失败 | [合同](specs/binance-1d-catl-p1-donor-walk-forward-modeling-contract-2026-08-31.md)、[Entry](diagnostics/binance-1d-catl-p1-entry-model-2026-08-31.md)、[Continuation](diagnostics/binance-1d-catl-p1-continuation-model-2026-08-31.md)、[审计](diagnostics/binance-1d-catl-p1-modeling-audit-2026-08-31.md)、[summary](artifacts/binance_1d_catl_p1_summary.json)、[manifest](artifacts/binance_1d_catl_p1_manifest.json) | 两目标均 `LEARNABLE_BUT_NOT_INCREMENTAL_BEYOND_MA`；可由独立实验 one-shot reveal HYPE，但不构成策略或 promotion |

## Shared Assumptions

- 数据源：`data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m`；四根闭合 `15m` 聚合为 `1h`，24 根连续 `1h` 聚合 UTC 日。
- Funding：`data/normalized/funding_rates/exchange=binance/market_type=perp`，用于独立 landmark 的成本后假设收益；缺失边界在数据质量报告记录。
- 截断：所有读取全局限制为 `< 2026-05-31 00:00 UTC`，最后特征日 `2026-05-30`。
- 成本模型：1.0x leverage；每次 fill fee `0.001`；每次 fill adverse slippage `4 bps`；入场和退出均计成本；每个 landmark 独立计算，不复利。
- 资产资格：`complete_day=true`、上市年龄不少于 60 日、30 日完整率不低于 `0.95`、30 日 quote volume 有限且为正；资格规则在标签计算前冻结。

## Evidence Map

- [家族 README](README.md)
- [P0 可复现脚本](scripts/run_binance_1d_catl_p0_dataset_label_atlas.py)
- [Asset-Day Feature Panel](artifacts/p0_asset_day_feature_panel/)
- [Directional Landmark Panel](artifacts/p0_directional_landmark_panel/)
- [字段字典](artifacts/binance_1d_catl_p0_field_dictionary.md)
- [标签质量 HTML](artifacts/binance_1d_catl_p0_label_quality_atlas.html)
- [Artifact index](artifacts/README.md)
- [针对性测试](../../../tests/test_binance_1d_catl_p0_dataset_label_atlas.py)
- [P0R 针对性测试](../../../tests/test_binance_1d_catl_p0r_modeling_input_repair.py)
- [P1 可复现脚本](scripts/run_binance_1d_catl_p1_donor_walk_forward_modeling.py)
- [P1 针对性测试](../../../tests/test_binance_1d_catl_p1_donor_walk_forward_modeling.py)
- [P1 Cursor 提示词](prompts/binance-1d-catl-p1-walk-forward-modeling-cursor-prompt-2026-08-31.md)
