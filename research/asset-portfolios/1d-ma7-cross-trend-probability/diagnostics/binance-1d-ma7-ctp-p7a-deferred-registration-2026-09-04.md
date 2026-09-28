# BIN-1D-MA7-CTP P7A 延迟登记说明

P7A 完成时，同一家族的 P7 可能仍在另一窗口修改共享文档。本文件记录以后应如何把 P7A 登记进共享文档，而本轮不修改这些文件。

## 以后应更新的文件

1. `research/asset-portfolios/1d-ma7-cross-trend-probability/README.md`：增加 P7A 入口链接；不要覆盖 P7 条目。
2. `binance-1d-ma7-ctp-core-ledger.md`：Current State 增加 P7A sidecar 一行；Version Table 增加 P7A 行，状态 `explore / diagnostic-only / placebo-audit / not promoted / not live-ready`，裁决 `CROSS_MOVEMENT_EFFECT_WITHOUT_DIRECTIONAL_EDGE`。
3. `decision-log.md`：新增 2026-09-04 一条，只写一句话结论和证据链接。
4. `artifacts/README.md`：增加 P7A 产物清单。
5. `research/README.md` 与 `research/asset-portfolios/README.md`：仅在需要指向 P7A 报告时加链接，不复述指标。

## 登记时必须保留

- P7 已有修改全部保留，禁止为整理工作树 reset/checkout/clean。
- P7A 文件一律 `p7a` 前缀，不得改名成 P7。
- 主状态不得写成 promotion / live-ready。

## 建议的 decision-log 草稿（登记时再写入）

决策：P7A 安慰剂审计裁决 `CROSS_MOVEMENT_EFFECT_WITHOUT_DIRECTIONAL_EDGE`。真实 MA7 成功率 31.9700%，同 Cross asset-date 随机方向 31.0272%，同日 non-cross 随机方向 29.9074%；directional edge +0.9428 pp，cross movement +1.1198 pp。约 30% 不应再被直接写成“MA7 穿越后形成趋势的概率”。不晋升、不改 runner。

证据：`diagnostics/binance-1d-ma7-ctp-p7a-placebo-base-rate-audit-2026-09-04.md`。

