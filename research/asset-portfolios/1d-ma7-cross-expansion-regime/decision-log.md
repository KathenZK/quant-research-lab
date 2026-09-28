# Decision log

## 2026-09-04

决策：新开独立家族 `BIN-1D-MA7-CER`，P0 只审计 MA7 Cross 是否为无方向 future expansion marker；不继承 CTP 方向预测假设，不训练 ML，不创建策略。

证据：[P0 合同](specs/binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-contract-2026-09-04.md)。

## 2026-09-04

决策：P0 唯一全局裁决为 `NO_EXPANSION_EDGE`。MA7 Cross 不是可靠的未来无方向 expansion predictor；不进入 P1，并停止本条 MA7 expansion 研究路线。

证据：[P0 报告](diagnostics/binance-1d-ma7-cer-p0-direction-agnostic-expansion-audit-2026-09-04.md) · [实现审计](diagnostics/binance-1d-ma7-cer-p0-implementation-audit-2026-09-04.md)。
