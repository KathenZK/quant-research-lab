# Artifacts — Binance OHLCV Data Lake Governance

本目录保存现场审计、对账和完整性快照。新衍生 OHLCV 发布在 `data/derived/datasets/`，不放在这里。

- [pre_governance_parquet_inventory.csv](pre_governance_parquet_inventory.csv)：治理前 raw/normalized/cache/4H P0 产物的 path/size/mtime/SHA256。
- [binance_ohlcv_dataset_inventory_2026-09-02.json](binance_ohlcv_dataset_inventory_2026-09-02.json)：现场数据集登记。
- [binance_ohlcv_symbol_spans_2026-09-02.csv](binance_ohlcv_symbol_spans_2026-09-02.csv)：逐 symbol 起止。
- [binance_ohlcv_consumers_2026-09-02.csv](binance_ohlcv_consumers_2026-09-02.csv)：直接路径消费者。
- [binance_ohlcv_reconciliation_2026-09-02.json](binance_ohlcv_reconciliation_2026-09-02.json)：P0/P3、日K缓存与六资产 4h 对账。
- [binance_4h_from_15m_year_coverage_2026-09-02.csv](binance_4h_from_15m_year_coverage_2026-09-02.csv)
- [binance_4h_six_asset_15m_vs_1h_mismatch_2026-09-02.csv](binance_4h_six_asset_15m_vs_1h_mismatch_2026-09-02.csv)
- [pre_round2_protected_inventory_2026-09-03.csv](pre_round2_protected_inventory_2026-09-03.csv)：第二轮受保护资产快照，不覆盖上一轮 inventory。
- [binance_ohlcv_trusted_quality_audit_2026-09-03.json](binance_ohlcv_trusted_quality_audit_2026-09-03.json)：15m 与 derived v1 全量 SQL 审计。
- [binance_ohlcv_volume_rca_2026-09-03.json](binance_ohlcv_volume_rca_2026-09-03.json)：成交额独立追溯。
- [binance_ohlcv_no_chat_usage_2026-09-03.json](binance_ohlcv_no_chat_usage_2026-09-03.json)：无聊天查询/读取/拒绝示例 bundle。
- [pre_round3_protected_inventory_2026-09-03.csv](pre_round3_protected_inventory_2026-09-03.csv)：第三轮受保护资产快照，不覆盖前两轮 inventory。
- [binance_ohlcv_r3_pre_fix_repro_2026-09-03.json](binance_ohlcv_r3_pre_fix_repro_2026-09-03.json)：第三轮修复前复现。
- [binance_ohlcv_trusted_quality_audit_r3_2026-09-03.json](binance_ohlcv_trusted_quality_audit_r3_2026-09-03.json)：R3 全量 SQL v2 + 严格内容哈希。
- [binance_ohlcv_4h_gap_table_r3_2026-09-03.csv](binance_ohlcv_4h_gap_table_r3_2026-09-03.csv)：4h 逐 symbol 内部缺口。
- [binance_ohlcv_volume_rca_r3_2026-09-03.json](binance_ohlcv_volume_rca_r3_2026-09-03.json)：R3 成交额独立追溯。
- [binance_ohlcv_volume_rca_r3_six_asset_2026-09-03.csv](binance_ohlcv_volume_rca_r3_six_asset_2026-09-03.csv)
- [binance_ohlcv_volume_rca_r3_hour_trace_2026-09-03.csv](binance_ohlcv_volume_rca_r3_hour_trace_2026-09-03.csv)
- [binance_ohlcv_volume_rca_r3_components_2026-09-03.csv](binance_ohlcv_volume_rca_r3_components_2026-09-03.csv)
- [binance_ohlcv_no_chat_usage_r3_2026-09-03.json](binance_ohlcv_no_chat_usage_r3_2026-09-03.json)：R3 无聊天查询/读取/拒绝示例 bundle。
- [binance_ohlcv_r3_test_summary_2026-09-03.json](binance_ohlcv_r3_test_summary_2026-09-03.json)：R3 测试与 preflight 摘要。
