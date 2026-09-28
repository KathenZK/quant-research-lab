# Decision Log — Binance-4H-MA7-Regime-Continuation

## 2026-09-02 — 启动 P0 无条件延续性 kill test

决策：正式启动 `Binance-4H-MA7-Regime-Continuation`（`BIN-4H-MA7-RC`）作为全新的 `4h` 独立家族，当前仅处于 `explore / diagnostic-only / not promoted / not live-ready`；P0 是事件研究和机制 kill test，不登记 `V1`，不生成 runner 或 live spec。

证据：[P0 冻结合同](specs/binance-4h-ma7-regime-continuation-p0-contract-2026-09-02.md)、[P0 冻结配置](configs/binance-4h-ma7-regime-continuation-p0.json)、[输入数据 manifest](artifacts/binance_4h_ma7_rc_p0_dataset_manifest_2026-09-02.json)。

## 2026-09-02 — P0R1 配置在 outcome 前作废并冻结 P0R2

决策：首次运行在 funding 审计阶段发现同一名义资金费时点存在毫秒级 archive offset，尚未读取 MA7 事件、forward return 或 first-hit outcome；因此作废 P0R1 配置 hash `afdac0134562709dd52b1951c4b91f1d36e185028db3f0a328e18d4f2997da0d`，冻结 P0R2 的秒级名义 funding 时间归一，P0R2 配置 hash 为 `eb62108271cf1d22992fb53c0c1a7438d605581d96cb079d75b0579143c84642`。

证据：[P0 冻结合同](specs/binance-4h-ma7-regime-continuation-p0-contract-2026-09-02.md)、[P0R2 配置](configs/binance-4h-ma7-regime-continuation-p0.json)。

## 2026-09-02 — P0 完成，两侧均 NO-GO

决策：P0 完成后 long 与 short 均裁决为 `NO-GO`，不允许进入 P1；家族保持 `explore / diagnostic-only / not promoted / not live-ready`，不登记版本、不 promotion、不 live-ready、不创建 runner 或 live spec。

证据：[P0 结果报告](diagnostics/binance-4h-ma7-regime-continuation-p0-results-2026-09-02.md)、[P0 summary](artifacts/binance_4h_ma7_rc_p0_summary_2026-09-02.json)、[first-hit 表](artifacts/binance_4h_ma7_rc_p0_first_hit_2026-09-02.csv)、[固定期限收益表](artifacts/binance_4h_ma7_rc_p0_horizon_returns_2026-09-02.csv)。

## 2026-09-03 — 冻结并验收 P0R-GAP-GUARD 缺口保护

决策：在同一家族内落地缺口保护，不覆盖 P0 / P0R-DATA。规则先冻结再盘点。验收为缺口保护 `PASS`（15 项合成测试、BTC 连续窗口新旧一致、AERGO 现场缺口不跨段计时、全量窗口盘点完成）。这不是策略有效、全研究通过或可上线。

证据：[P0R-GAP-GUARD 合同](specs/binance-4h-ma7-regime-continuation-p0r-gap-guard-contract-2026-09-03.md)、[验收报告](diagnostics/binance-4h-ma7-regime-continuation-p0r-gap-guard-2026-09-03.md)、[盘点 summary](artifacts/binance_4h_ma7_rc_p0r_gap_guard_inventory_summary_2026-09-03.json)。

## 2026-09-03 — 冻结 P0R-DATA 数据范围重跑，不覆盖 P0

决策：在读取新 outcome 前冻结 `P0R-DATA`。机制、PIT、成本、first-hit 与 PASS 口径沿用 P0；OHLCV 改为 catalog `dataset_id` 加载 `binance.perp.ohlcv.4h.from_15m.v1` 与 `1h.from_15m.v1`。禁止读取 legacy normalized 1h。不覆盖任何 P0 artifact。本轮不修复完整年度窗口与 horizon `p_value` 覆盖。不晋升、不写 runner。

证据：[P0R-DATA 合同](specs/binance-4h-ma7-regime-continuation-p0r-data-contract-2026-09-03.md)、[P0R-DATA 配置](configs/binance-4h-ma7-regime-continuation-p0r-data.json)、[输入 manifest](artifacts/binance_4h_ma7_rc_p0r_data_dataset_manifest_2026-09-03.json)、[数据交接](../../platform/data-lake-governance/specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md)。

## 2026-09-02 — P0 数据范围不完整，NO-GO 不得外推全市场

决策：确认当前 P0 只是六资产诊断。行级质量通过，但输入 normalized 1h 为 `PARTIAL_SCOPE_LEGACY`，主 MA7 样本仅 6 个长期历史币。现有 `NO-GO` 记为 `DATA_SCOPE_INCOMPLETE / six-asset diagnostic-only`，不能代表 Binance 全市场。后续只允许不覆盖原 artifacts 的 `P0R-DATA`，冻结假设，禁止根据现有结果调参。

证据：[数据范围修正](diagnostics/binance-4h-ma7-regime-continuation-p0-data-scope-correction-2026-09-02.md)、[P0R-DATA 交接](../../platform/data-lake-governance/specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md)。
