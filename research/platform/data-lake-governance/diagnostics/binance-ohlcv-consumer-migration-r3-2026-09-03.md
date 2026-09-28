# 消费者迁移清单 R3（2026-09-03）

本清单更新 [2026-09-03 第二轮迁移表](binance-ohlcv-consumer-migration-2026-09-03.md)，不覆盖原文件。不改冻结策略定义，不跑收益。

检查范围：`scripts/governance/check_trusted_consumers.py` 对整个 `research/` 扫描 catalog API（`load_trusted_dataset` / `load_trusted_research_dataset` / `load_canonical_binance_perp_1d` / `read_verified_ohlcv`）。湖路径 token 额外监视 `research/asset-portfolios/4h-ma7-regime-continuation/scripts/`。治理脚本 `research/platform/data-lake-governance/scripts/` 为受控例外。未登记新消费者必须加入 `BINANCE_CATALOG_CONSUMERS`、`FROZEN_LEGACY_OHLCV_GLOBS` 或受控例外，否则 preflight 失败。

| 消费者 | 标记 | 入口 | 说明 |
| --- | --- | --- | --- |
| 新研究（本轮之后） | 必用研究 API | `load_trusted_research_dataset` + 显式 cutoff + `gap_policy=reject\|contiguous_segments` | 不得默认 `report_only` |
| `BIN-4H-MA7-RC` P0R-DATA | 已登记历史取数 | `load_trusted_dataset` → `4h/1h.from_15m.v1` | 仍为 `purpose` 未指定 / `report_only`；不原地改冻结脚本；全市场 `reject` 会 UNFIT |
| `BIN-4H-MA7-RC` P0 | 冻结历史复现 | `ohlcv_1h_globs` / legacy 1h | 不得改写 |
| 1d 历史家族 | 冻结历史复现 | 旧 1d cache | sidecar 多为 `LINEAGE_INCOMPLETE`；新实验用 canonical 1d |
| 治理脚本 | 受控例外 | `research/platform/data-lake-governance/scripts/` | 允许扫描物理根，结果不得当 trusted 研究输入 |

完整旧路径表仍见 [binance_ohlcv_consumers_2026-09-02.csv](../artifacts/binance_ohlcv_consumers_2026-09-02.csv)。
