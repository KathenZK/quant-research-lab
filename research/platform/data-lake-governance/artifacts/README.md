# Artifacts — Binance OHLCV Data Lake Governance

本目录保存现场审计、对账和完整性快照。新衍生 OHLCV 发布在 `data/derived/datasets/`，不放在这里。

- [binance_research_bundle_v2_20260907/](binance_research_bundle_v2_20260907/)：五组内容哈希、真实价格启动、负向门禁与旧输入保护证据；[交接验收](../diagnostics/binance-research-bundle-v2-startup-2026-09-07.md)。可同步的固定组合清单位于 `specs/`，不依赖本目录自动随 Git 分发。

- [data_lake_structure_cleanup_audit_20260907/](data_lake_structure_cleanup_audit_20260907/)：只读结构、分层占用、已发布指纹、清理依赖与旧 ZIP 比对；[适用性与清理风险报告](../diagnostics/data-lake-structure-readiness-cleanup-audit-2026-09-07.md)。未删除、移动或改写数据。

- [binance_funding_v3_inputs_v2_20260907/](binance_funding_v3_inputs_v2_20260907/)：资金费率 v2 原文索引、事件映射、特殊类型、覆盖片段、未检索范围零成交审计、发布回读与旧指纹保护；[验收报告](../diagnostics/binance-funding-v3-inputs-v2-2026-09-07.md)。事件质量通过不等于全历史结算覆盖。

- [binance_v3_research_inputs_v1_20260907/](binance_v3_research_inputs_v1_20260907/)：V3 配套高周期验收、独立聚合/组件对账、连续段、身份边界与资金费率补齐记录；[治理报告](../diagnostics/binance-v3-research-inputs-v1-2026-09-07.md)。资金费率与 PIT 限制不被价格 PASS 覆盖。

- [binance_15m_history_v3_20260906/](binance_15m_history_v3_20260906/)：V3 全历史缺口取证、CHECKSUM、历史别名映射、raw/旧输入保护、发布后验收、边界处置与历史连续段；[解读与限制](../diagnostics/binance-15m-history-v3-closeout-2026-09-06.md)。

- [binance_15m_refresh_v2_20260905/](binance_15m_refresh_v2_20260905/)：15m V2 冻结配置、官方请求回执索引、raw 对齐、合并审计、逐合约新鲜度、全部剩余缺口与发布后 `acceptance.json`；解读见 [V2 验收](../diagnostics/binance-15m-refresh-v2-acceptance-2026-09-06.md)，不得仅以行质量 PASS 宣称历史治理完成。

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
