# BIN-1D-CATL Decision Log

## 2026-08-31：P0 Dataset and Label Atlas 可进入建模研究

决定：`BIN-1D-CATL-P0` 完成全市场日频因果特征与 long/short directional first-hit 标签图谱构建，裁决为 `DATASET_READY_FOR_MODELING_RESEARCH`；研究线保持 `explore / diagnostic-only / not promoted / not live-ready`，不形成交易策略、不触发 promotion。

证据：[P0 合同](specs/binance-1d-catl-p0-dataset-label-atlas-contract-2026-08-31.md)、[数据质量报告](diagnostics/binance-1d-catl-p0-data-quality-2026-08-31.md)、[标签分布报告](diagnostics/binance-1d-catl-p0-label-distribution-2026-08-31.md)、[summary](artifacts/binance_1d_catl_p0_summary.json)、[manifest](artifacts/binance_1d_catl_p0_manifest.json)。

## 2026-08-31：P0R 建模输入修复通过

决定：保留 P0 不变，P0R 修复因果波动状态、donor-only PIT 横截面和价格尺度资格后裁决为 `MODELING_INPUT_READY`；P1 必须完全排除 `HYPE/USDT:USDT`，HYPE 只作为锁模后的独立一次性揭示集。

证据：[P0R 合同](specs/binance-1d-catl-p0r-modeling-input-repair-contract-2026-08-31.md)、[修复报告](diagnostics/binance-1d-catl-p0r-modeling-input-repair-2026-08-31.md)、[summary](artifacts/binance_1d_catl_p0r_summary.json)、[manifest](artifacts/binance_1d_catl_p0r_manifest.json)。

## 2026-08-31：P1 donor 信号可学习但无 cross-market 增量

决定：Entry 与 Continuation 均通过冻结 donor learnability 门，但都未通过 cross-market 增量项，裁决为 `LEARNABLE_BUT_NOT_INCREMENTAL_BEYOND_MA`；P1R1 只补全 raw/calibrated、十分位及分层报告并修正测试断言，冻结模型预测哈希与首次运行完全一致，研究线保持 `explore / diagnostic-only / not promoted / not live-ready`。

证据：[P1 合同](specs/binance-1d-catl-p1-donor-walk-forward-modeling-contract-2026-08-31.md)、[Entry 报告](diagnostics/binance-1d-catl-p1-entry-model-2026-08-31.md)、[Continuation 报告](diagnostics/binance-1d-catl-p1-continuation-model-2026-08-31.md)、[建模审计](diagnostics/binance-1d-catl-p1-modeling-audit-2026-08-31.md)、[summary](artifacts/binance_1d_catl_p1_summary.json)、[manifest](artifacts/binance_1d_catl_p1_manifest.json)。
