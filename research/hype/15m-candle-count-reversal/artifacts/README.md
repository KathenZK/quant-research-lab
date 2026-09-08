# HYPE-CC Artifacts

This directory is for retained JSON, CSV, and HTML outputs that support current `HYPE-CC` Markdown reports.

Top-level `reports/` is retired; migrated Canvas notes should point to retained `artifacts/` or explicit archive paths.

## 2026-09-07 — V35 极值 Maker 入场审计

- [汇总 JSON](hype_cc_v35_maker_entry_summary_2026-09-07.json)：结论、数据身份、
  主窗口指标、因子拆分与 blockers。
- [全对照 CSV](hype_cc_v35_maker_entry_comparison_2026-09-07.csv)：主窗口、连续状态、
  `1d / 7d / 1m / 3m / 6m / 1y` 切片及成本敏感性。
- [逐笔交易 CSV](hype_cc_v35_maker_entry_trades_2026-09-07.csv)：主窗口各变体、各成本
  口径的订单与退出记录。
- [输入快照](hype_cc_v35_maker_entry_input_2026-09-07.parquet)：从 warm-up 起保留的冻结输入；
  SHA256 `1d4353c22b03b23c76357007c72fc35bfa45a715853e4a0088fb75f80bbcf072`。

对应解释见
[诊断报告](../diagnostics/hype-cc-v35-maker-entry-audit-2026-09-07.md)，研究契约见
[审计契约](../specs/hype-cc-v35-maker-entry-audit-contract-2026-09-07.md)。
