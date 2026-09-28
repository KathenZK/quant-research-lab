# BIN-1D-MA7-CTP P7B 延迟登记说明

P7B 完成时，同一家族的 P7 / P7A 或其他窗口可能仍在修改共享文档。本文件记录以后应如何把 P7B 登记进共享文档，而本轮不修改这些文件。

## 以后应更新的文件

1. `research/asset-portfolios/1d-ma7-cross-trend-probability/README.md`：增加 P7B 入口链接；不要覆盖 P7 / P7A 条目。
2. `binance-1d-ma7-ctp-core-ledger.md`：Current State 增加 P7B sidecar 一行；Version Table 增加 P7B 行，状态 `explore / diagnostic-only / placebo-audit / not promoted / not live-ready`。
3. `decision-log.md`：新增 2026-09-04 一条，只写一句话结论和证据链接。
4. `artifacts/README.md`：增加 P7B 产物清单。
5. `research/README.md` 与 `research/asset-portfolios/README.md`：仅在需要指向 P7B 报告时加链接，不复述指标。

## 建议的 decision-log 草稿（登记时再写入）

决策：P7B 市场状态条件方向安慰剂审计裁决 `REGIME_DRIFT_EXPLAINS_APPARENT_EDGE`。BULL_UP incremental +1.2635 pp，BEAR_DOWN incremental -0.0048 pp，alignment -0.3228 pp。不晋升、不改 runner。

证据：`diagnostics/binance-1d-ma7-ctp-p7b-regime-conditional-direction-placebo-audit-2026-09-04.md`。

