# BIN-4H-MA7-RC P0R-DATA 交接

日期：2026-09-02  
本文件只交接数据范围重跑，不执行 P0R，不改策略统计代码，不覆盖现有 P0 artifacts 或 `.sha256`。

家族内已使用 `P0R1`/`P0R2` 表示 funding 时间归一的配置修订。本次数据范围重跑命名为 **`P0R-DATA`**，避免覆盖那两次配置身份。

## 为什么必须重跑

当前 P0 行级质量审计通过，但缺少全市场 scope gate。主 `SMA7` 样本只有六个长期历史币、`5,947` 个事件。现有 `NO-GO` 只能解释为 `DATA_SCOPE_INCOMPLETE / six-asset diagnostic-only`，不能外推到 Binance 全市场。

独立修正诊断：[../../../asset-portfolios/4h-ma7-regime-continuation/diagnostics/binance-4h-ma7-regime-continuation-p0-data-scope-correction-2026-09-02.md](../../../asset-portfolios/4h-ma7-regime-continuation/diagnostics/binance-4h-ma7-regime-continuation-p0-data-scope-correction-2026-09-02.md)

## 冻结假设（不得根据现有六资产结果调参）

保持现有 P0 合同中的机制、事件定义、PIT 规则、成本、first-hit、持有期和 PASS/NO-GO 口径。只替换 OHLCV 输入：

- 禁止再读 `binance.perp.ohlcv.1h.normalized.legacy`
- 必须读 `binance.perp.ohlcv.4h.from_15m.v1`（标准衍生 4h）
- 若策略仍需 1h 路径做 first-hit，只允许 `binance.perp.ohlcv.1h.from_15m.v1`
- 输出写入新的 `p0r-data` artifacts 文件名，不得覆盖 `*-p0-*-2026-09-02.*`

## 两个非数据 blocker（本轮不改代码）

1. 当前只统计 2023–2025 三个完整年度，却要求至少四个正年度，PASS 在现口径下不可达。
2. horizon 表先写 bootstrap `p_value`，随后 `**cluster` 用同名 `p_value` 覆盖，导致 CI、p-value、q-value 检验对象不一致。见 `research_binance_4h_ma7_regime_continuation_p0.py` 约 1210–1235 行。

P0R-DATA 可以记录这两项，但修复统计代码属于另一次明确授权，不在本治理任务内。

## 建议执行提示词

把下面整段交给新会话，不要在本治理会话中运行：

```text
仓库：/Users/ZK/OpenCode/quant-strategy-lab
任务：执行 Binance-4H-MA7-Regime-Continuation 的 P0R-DATA。
这是数据范围重跑，不是调参。

必须先读：
- research/asset-portfolios/4h-ma7-regime-continuation/README.md
- research/asset-portfolios/4h-ma7-regime-continuation/binance-4h-ma7-rc-core-ledger.md
- research/asset-portfolios/4h-ma7-regime-continuation/specs/binance-4h-ma7-regime-continuation-p0-contract-2026-09-02.md
- research/asset-portfolios/4h-ma7-regime-continuation/diagnostics/binance-4h-ma7-regime-continuation-p0-data-scope-correction-2026-09-02.md
- research/platform/data-lake-governance/specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md
- docs/data-lake-spec.md

硬约束：
1. 不覆盖任何现有 P0 artifact 或 .sha256。
2. 不读取 normalized legacy 1h。
3. 通过 dataset_id 加载 binance.perp.ohlcv.4h.from_15m.v1；如需 1h 路径，加载 binance.perp.ohlcv.1h.from_15m.v1。
4. 冻结 P0 假设，不得因六资产 NO-GO 增加过滤器、改 MA、改方向或改持仓期。
5. 新结果写入独立 P0R-DATA 文件名。
6. 不要修复 horizon p_value 覆盖，也不要改完整年度窗口，除非用户另外授权；但必须在报告中复述这两项 blocker。
7. 不得把本次结果自动晋升，也不得写入 quant-runner。
```

## 数据支持判断

现场结果：derived 4h 共 853 个代码、825 个 ≥30 日、533 个 ≥365 日，2020–2026 每年均 ≥50 个代码。`full_market_p0r_data_support.can_support_all_market_history_p0r = true`。

该字段只判断数据范围能否支撑全市场历史 P0R，不判断策略能否通过。详见 [binance-ohlcv-reconciliation-2026-09-02.md](../diagnostics/binance-ohlcv-reconciliation-2026-09-02.md)。
