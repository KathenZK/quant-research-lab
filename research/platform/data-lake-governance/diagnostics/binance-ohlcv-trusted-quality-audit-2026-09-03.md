# Binance OHLCV 全量 SQL 质量审计（2026-09-03）

本轮对 accepted 15m 与已发布 1h/4h/1d 派生集做 DuckDB 全量质量扫描，不把覆盖预览当作 trusted，也不把抽样当作全量。

总体：`PASS`；`partial=False`。

## `binance.perp.ohlcv.15m.normalized.v1`

- quality_status：`PASS`
- materialized：`False`（应为 false）
- inspect.trusted：`False`（预览不得为 true）
- rows / symbols：`60266362` / `853`
- 范围：`2019-09-08T17:45:00+00:00` → `2026-08-24T23:45:00+00:00`
- cutoff_exclusive_utc：`None`
- parquet_inventory_fingerprint：`c615a4c12cd8392fbf083ad2b0ffaa693d65837da19f797813e7f726d377475a`
- internal_missing_bars：`89152`（report_only）
- unaligned_gap_transitions：`0`
- unverified_source_rows：`0`
- illegal_ohlc_rows：`0`
- duplicate_business_key_rows：`0`

## `binance.perp.ohlcv.1h.from_15m.v1`

- quality_status：`PASS`
- materialized：`False`（应为 false）
- inspect.trusted：`False`（预览不得为 true）
- rows / symbols：`15066337` / `853`
- 范围：`2019-09-08T18:00:00+00:00` → `2026-08-24T23:00:00+00:00`
- cutoff_exclusive_utc：`None`
- parquet_inventory_fingerprint：`d8eebe27f3d0dbfda4cb5756d5041ae244bb1c576937f65970d6a7dd01b11596`
- internal_missing_bars：`22293`（report_only）
- unaligned_gap_transitions：`0`
- unverified_source_rows：`0`
- illegal_ohlc_rows：`0`
- duplicate_business_key_rows：`0`

## `binance.perp.ohlcv.4h.from_15m.v1`

- quality_status：`PASS`
- materialized：`False`（应为 false）
- inspect.trusted：`False`（预览不得为 true）
- rows / symbols：`3766251` / `853`
- 范围：`2019-09-08T20:00:00+00:00` → `2026-08-24T20:00:00+00:00`
- cutoff_exclusive_utc：`None`
- parquet_inventory_fingerprint：`a52be016421363b2bfbcdcc6d61b02288de206dfc330d3b4df0a2fa11d0be8a6`
- internal_missing_bars：`5577`（report_only）
- unaligned_gap_transitions：`0`
- unverified_source_rows：`0`
- illegal_ohlc_rows：`0`
- duplicate_business_key_rows：`0`

## `binance.perp.ohlcv.1d.from_15m.v1`

- quality_status：`PASS`
- materialized：`False`（应为 false）
- inspect.trusted：`False`（预览不得为 true）
- rows / symbols：`627283` / `853`
- 范围：`2019-09-09T00:00:00+00:00` → `2026-08-24T00:00:00+00:00`
- cutoff_exclusive_utc：`None`
- parquet_inventory_fingerprint：`6c8f1b834fceb2f84f3c0e11858a412e0199e979bda1102e87cd5d6a7fac2b81`
- internal_missing_bars：`935`（report_only）
- unaligned_gap_transitions：`0`
- unverified_source_rows：`0`
- illegal_ohlc_rows：`0`
- duplicate_business_key_rows：`0`

机器结果：[binance_ohlcv_trusted_quality_audit_2026-09-03.json](../artifacts/binance_ohlcv_trusted_quality_audit_2026-09-03.json)。
