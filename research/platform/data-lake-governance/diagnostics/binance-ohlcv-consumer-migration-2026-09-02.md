# 消费者迁移清单

日期：2026-09-02  
本清单不重跑策略，只说明旧路径应迁到哪个 `dataset_id`。完整文件列表见 [binance_ohlcv_consumers_2026-09-02.csv](../artifacts/binance_ohlcv_consumers_2026-09-02.csv)。

| 旧路径 | 身份 | 新入口 | 迁移要求 |
| --- | --- | --- | --- |
| `data/normalized/ohlcv/.../timeframe=15m` | `TRUSTED_BASE` | `binance.perp.ohlcv.15m.normalized.v1` | 新治理研究改用 `load_trusted_dataset`；旧脚本可暂留 |
| `data/normalized/ohlcv/.../timeframe=1h` | `PARTIAL_SCOPE_LEGACY` | 禁止 `FULL_MARKET`；全市场改用 `1h.from_15m.v1` 或 `4h.from_15m.v1` | 单币诊断仍可显式 `SINGLE_SYMBOL` / `EXPLICIT_DIAGNOSTIC` |
| `data/cache/binance_perp_1d_from_15m` | `FAMILY_CACHE` | `binance.perp.ohlcv.1d.from_15m.v1` | 月档优先规则只描述旧缓存；新研究不要把它当 canonical 1d |
| `data/cache/binance-1d-ma7-rc-p0` | `FAMILY_CACHE` 面板 | 仅 `BIN-1D-MA7-RC` P0 重建 | 其他家族不得直接依赖 |
| `data/cache/binance-1d-ma7-rc-p3` | `FAMILY_CACHE` 面板 | 仅 `BIN-1D-MA7-RC` P3 重建 | 其他家族不得直接依赖 |

主要旧 1h 消费者：`BIN-4H-MA7-RC` P0。必须通过 `P0R-DATA` 改读 derived 4h/1h，且不覆盖原 artifacts。

主要公共日K缓存消费者：`BIN-1D-MCSM-LS3`、`BIN-1D-MCSM-L10`、`BIN-1D-MA7-CTP` 全市场脚本。历史证据保留；新实验改读 derived 1d。

2026-09-03 更新见 [binance-ohlcv-consumer-migration-2026-09-03.md](binance-ohlcv-consumer-migration-2026-09-03.md)。
