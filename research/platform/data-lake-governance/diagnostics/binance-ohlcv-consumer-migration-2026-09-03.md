# 消费者迁移清单（2026-09-03）

本清单更新 [2026-09-02 迁移表](binance-ohlcv-consumer-migration-2026-09-02.md)，不覆盖原文件。本轮只做数据层与取数层等价，不改家族研究契约、不跑收益。

| 消费者 | 标记 | 入口 | 说明 |
| --- | --- | --- | --- |
| `BIN-4H-MA7-RC` P0 | 冻结历史复现，明确保留 legacy | `ohlcv_1h_globs` / `binance.perp.ohlcv.1h.normalized.legacy` | 不得改写；结论仍是 `DATA_SCOPE_INCOMPLETE` |
| `BIN-4H-MA7-RC` P0R-DATA 取数 | 已迁移 | `load_trusted_dataset` → `binance.perp.ohlcv.4h.from_15m.v1` / `binance.perp.ohlcv.1h.from_15m.v1` | 先 SQL 质量+manifest，再用 `verified_parquet_files`；未跑策略结果 |
| 新的公共日K实验 | 已提供入口 | `load_canonical_binance_perp_1d` → `binance.perp.ohlcv.1d.from_15m.v1` | 不要用 `data/cache/binance_perp_1d_from_15m` |
| `BIN-1D-MCSM-LS3` / `L10` / `BIN-1D-MA7-CTP` 历史脚本 | 冻结历史复现 | 旧 1d cache | sidecar 多为 `LINEAGE_INCOMPLETE`；禁止无提示换 canonical 后沿用旧面板 |
| `BIN-1D-MA7-RC` P0/P3 面板 | 冻结历史复现 | `binance-1d-ma7-rc-p0/p3` | 仅本家族重建；其他家族不得直接依赖 |
| 治理构建/审计脚本 | 受控例外 | `research/platform/data-lake-governance/scripts/` | 允许扫描 raw/normalized/derived 根，不得把扫描结果当 trusted 研究输入 |

完整旧路径表仍见 [binance_ohlcv_consumers_2026-09-02.csv](../artifacts/binance_ohlcv_consumers_2026-09-02.csv)。
