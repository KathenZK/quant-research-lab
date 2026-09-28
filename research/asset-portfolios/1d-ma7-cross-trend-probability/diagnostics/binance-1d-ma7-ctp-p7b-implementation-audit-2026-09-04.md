# BIN-1D-MA7-CTP P7B 实现审计

- 状态：`explore / diagnostic-only / placebo-audit / not promoted / not live-ready`
- 全局裁决：`REGIME_DRIFT_EXPLAINS_APPARENT_EDGE`
- 合同锁：`FROZEN_BEFORE_P7B_REGIME_OUTCOME_READ`
- config sha256：`6754e32e0946a4694f14b472a682354cd55ba20da7ce0e73d713829cd0e03386`
- contract sha256：`56a21f7fb2b46ddbf225b279df22018221084db597eace4ad2e7cd1dcf0b4402`
- manifest sha256：`f868a1317c5ed3d9d0b197c286a7c5f2bd4b601e635fd83e741644668fb5d837`

## 输入隔离

- P7 输入文件数：`0`（必须为 0）
- B0 分数未作为研究输入：`True`
- HYPE 原始分区读取：`False`
- HYPE 行数：`0`
- HYPER 行数：`76`
- P7A dual-side 复现：`True`
- P6 regime parity：`True`

## 未做的事

- 无 ML 模型、无 B0 训练/打分、无策略权益曲线、无 Sharpe/CAGR、未改 P0–P7A 冻结产物、未改共享 README/ledger/decision log。

运行命令：`/Users/ZK/OpenCode/quant-strategy-lab/.venv/bin/python research/asset-portfolios/1d-ma7-cross-trend-probability/scripts/run_binance_1d_ma7_ctp_p7b_regime_conditional_direction_placebo_audit.py`

