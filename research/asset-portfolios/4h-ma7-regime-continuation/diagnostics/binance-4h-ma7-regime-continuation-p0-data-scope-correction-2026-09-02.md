# BIN-4H-MA7-RC P0 数据范围修正

日期：2026-09-02  
性质：独立数据范围诊断。不覆盖 [binance-4h-ma7-regime-continuation-p0-results-2026-09-02.md](binance-4h-ma7-regime-continuation-p0-results-2026-09-02.md) 或其 `.sha256`。

## 结论

当前 P0 行级质量审计通过，但全市场 scope gate 缺失。主 `SMA7` 样本只有六个长期历史币、`5,947` 个事件。现结论应记为：

`DATA_SCOPE_INCOMPLETE / six-asset diagnostic-only`

现有 `NO-GO` 不能外推到 Binance 全市场。后续必须建立不覆盖原结果的 `P0R-DATA`，并保持冻结假设，不允许根据现有六资产结果调参。

## 已核验事实

- P0 读取 normalized `1h`，再聚合成 `4h`。该 `1h` 现登记为 `binance.perp.ohlcv.1h.normalized.legacy` / `PARTIAL_SCOPE_LEGACY`。
- 选中约 `398,235` 根 1h、`543` 个代码，但长期连续历史主要只有 6 个币；其余多为 2026-07 短快照。
- 原生 `0h` / `SMA7` PIT 事件 `5,947`（long `2,974`、short `2,973`、6 symbols）。
- 行级 OHLC/闭合/重复键审计可以通过，仍不等于全市场覆盖。

## 后续 P0R-DATA

- 输入改为 `binance.perp.ohlcv.4h.from_15m.v1`；如需 1h 路径则用 `binance.perp.ohlcv.1h.from_15m.v1`。
- 禁止再把 legacy 1h 的 distinct symbol 数当成全市场。
- 交接文件：[../../../platform/data-lake-governance/specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md](../../../platform/data-lake-governance/specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md)

## 非数据 blocker（记录但不在本治理任务中修改）

1. 统计代码只把 2023–2025 当作完整年度，PASS 却要求至少四个正年度，故 PASS 不可达。
2. horizon 表先写 bootstrap `p_value`，随后被 cluster `p_value` 同名覆盖，CI 与 p/q-value 检验对象不一致。
