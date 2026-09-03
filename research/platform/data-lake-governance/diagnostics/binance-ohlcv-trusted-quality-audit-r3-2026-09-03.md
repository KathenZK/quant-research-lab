# Binance OHLCV 全量质量审计 R3（2026-09-03）

本轮使用 `SQL_AUDIT_RULE_VERSION=binance_ohlcv_sql_audit_v2` 与 `fingerprint_mode=strict_content`。
不复用第二轮 SQL PASS。整库扫描声明 `purpose=governance_audit`；4h 内部缺口另行报告研究窗口适用性。
首尾 K 线没有上市/退市证据，`listing_evidence=unknown`。

行质量全部 PASS：`True`；`partial=False`。

## `binance.perp.ohlcv.15m.normalized.v1`

- row_quality / quality_status：`PASS` / `PASS`
- historical_coverage：`INTERNAL_GAPS`
- research_window_fitness（report_only）：`GAPS_REPORTED_ONLY`
- listing_evidence：`unknown`
- materialized：`False`（应为 false）
- inspect.trusted：`False`（预览不得为 true）
- rows / symbols：`60266362` / `853`
- 范围：`2019-09-08T17:45:00+00:00` → `2026-08-24T23:45:00+00:00`
- cutoff_exclusive_utc：`None`
- parquet_inventory_fingerprint：`c615a4c12cd8392fbf083ad2b0ffaa693d65837da19f797813e7f726d377475a`
- fingerprint_mode：`strict_content`
- internal_missing_bars：`89152`
- unaligned_gap_transitions：`0`
- schema_errors：`[]`
- research reject：`None`

## `binance.perp.ohlcv.1h.from_15m.v1`

- row_quality / quality_status：`PASS` / `PASS`
- historical_coverage：`INTERNAL_GAPS`
- research_window_fitness（report_only）：`GAPS_REPORTED_ONLY`
- listing_evidence：`unknown`
- materialized：`False`（应为 false）
- inspect.trusted：`False`（预览不得为 true）
- rows / symbols：`15066337` / `853`
- 范围：`2019-09-08T18:00:00+00:00` → `2026-08-24T23:00:00+00:00`
- cutoff_exclusive_utc：`None`
- parquet_inventory_fingerprint：`d8eebe27f3d0dbfda4cb5756d5041ae244bb1c576937f65970d6a7dd01b11596`
- fingerprint_mode：`strict_content`
- internal_missing_bars：`22293`
- unaligned_gap_transitions：`0`
- schema_errors：`[]`
- research reject：`None`

## `binance.perp.ohlcv.4h.from_15m.v1`

- row_quality / quality_status：`PASS` / `PASS`
- historical_coverage：`INTERNAL_GAPS`
- research_window_fitness（report_only）：`GAPS_REPORTED_ONLY`
- listing_evidence：`unknown`
- materialized：`False`（应为 false）
- inspect.trusted：`False`（预览不得为 true）
- rows / symbols：`3766251` / `853`
- 范围：`2019-09-08T20:00:00+00:00` → `2026-08-24T20:00:00+00:00`
- cutoff_exclusive_utc：`None`
- parquet_inventory_fingerprint：`a52be016421363b2bfbcdcc6d61b02288de206dfc330d3b4df0a2fa11d0be8a6`
- fingerprint_mode：`strict_content`
- internal_missing_bars：`5577`
- unaligned_gap_transitions：`0`
- schema_errors：`[]`
- research reject：`{'status': 'REJECTED', 'error': "dataset binance.perp.ohlcv.4h.from_15m.v1 is not trusted (quality blockers): {'missing_bars': 5577}"}`

## `binance.perp.ohlcv.1d.from_15m.v1`

- row_quality / quality_status：`PASS` / `PASS`
- historical_coverage：`INTERNAL_GAPS`
- research_window_fitness（report_only）：`GAPS_REPORTED_ONLY`
- listing_evidence：`unknown`
- materialized：`False`（应为 false）
- inspect.trusted：`False`（预览不得为 true）
- rows / symbols：`627283` / `853`
- 范围：`2019-09-09T00:00:00+00:00` → `2026-08-24T00:00:00+00:00`
- cutoff_exclusive_utc：`None`
- parquet_inventory_fingerprint：`6c8f1b834fceb2f84f3c0e11858a412e0199e979bda1102e87cd5d6a7fac2b81`
- fingerprint_mode：`strict_content`
- internal_missing_bars：`935`
- unaligned_gap_transitions：`0`
- schema_errors：`[]`
- research reject：`None`

## 4h 逐 symbol 缺口表

共 `132` 段内部缺口。原因未知则标 `unknown`，不得把首尾当成已确认上市/退市。
机器表：[binance_ohlcv_4h_gap_table_r3_2026-09-03.csv](../artifacts/binance_ohlcv_4h_gap_table_r3_2026-09-03.csv)。

机器结果：[binance_ohlcv_trusted_quality_audit_r3_2026-09-03.json](../artifacts/binance_ohlcv_trusted_quality_audit_r3_2026-09-03.json)。
