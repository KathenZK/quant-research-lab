# Binance OHLCV 第二轮验收（2026-09-03）

性质：第二轮收口。不重跑全量 SQL 质量审计，不覆盖 2026-09-02 身份证据，不重跑策略。

## 分项结论

| 分项 | 状态 | 含义 |
| --- | --- | --- |
| 基础设施 | `READY` | `inspect` 非 trusted；`load_trusted_dataset` 走 SQL 全量审计且不得空 `audit`；derived 校验 `_MANIFEST.json`；闭合 cutoff；同输入幂等、异输入拒覆盖 |
| 数据集 | `PASS` / 缺口保留 | 15m 与 `1h/4h/1d.from_15m.v1` 全量 SQL `PASS`；legacy 1h 仍是 `PARTIAL_SCOPE_LEGACY`；家族缓存仍是 `FAMILY_CACHE` |
| 消费者 | `PARTIAL` | `BIN-4H-MA7-RC` P0R-DATA 已接 catalog；P0 与 1d 历史脚本冻结在旧路径；未批准不得删库或重建面板 |

这不是策略 PASS，也不是 4H 全市场 `NO-GO`。

## 硬门禁对照

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| `inspect` / `list` 的 `trusted=False` | 通过 | 现场审计四套 `inspection_trusted_flag=false`；用法 bundle 含 `inspect_4h` |
| trusted load 必有 SQL 审计 | 通过 | 四套 `quality_status=PASS`、`partial=False`、`materialized=False` |
| derived manifest 身份 | 通过 | 缺 manifest / 错 fingerprint 现场拒绝 |
| 闭合 cutoff，不用 wall-clock | 通过 | 单元测试；v1 `cutoff_exclusive_utc=null`，观测止于最后完整闭合 K |
| 同输入幂等、异输入新版本 | 通过 | `--check` 三套均为 `already_published`；单元测试覆盖拒覆盖 |
| 15m 身份是库存指纹 | 通过 | `_INPUT_SNAPSHOT.json` = `c615a4c12cd8392fbf083ad2b0ffaa693d65837da19f797813e7f726d377475a` |
| 不改 v1 manifest 补 cutoff | 通过 | `--check` 仍为 `cutoff_exclusive_utc=None` |
| `LINEAGE_INCOMPLETE` / 缓存冒充 OHLCV | 通过 | 缓存加载拒绝；sidecar 无预期哈希则拒绝 |
| legacy 1h 不能 `FULL_MARKET` | 通过 | 现场拒绝 |

## 现场质量（未重跑）

来源：[binance-ohlcv-trusted-quality-audit-2026-09-03.md](binance-ohlcv-trusted-quality-audit-2026-09-03.md)，写于 11:47，断线前已落盘。

| dataset_id | rows | symbols | 内部缺口 report_only | fingerprint |
| --- | --- | --- | --- | --- |
| `binance.perp.ohlcv.15m.normalized.v1` | 60,266,362 | 853 | 89,152 | `c615a4c1…d377475a` |
| `binance.perp.ohlcv.1h.from_15m.v1` | 15,066,337 | 853 | 22,293 | `d8eebe27…01b11596` |
| `binance.perp.ohlcv.4h.from_15m.v1` | 3,766,251 | 853 | 5,577 | `a52be016…1d0be8a6` |
| `binance.perp.ohlcv.1d.from_15m.v1` | 627,283 | 853 | 935 | `6c8f1b83…7fac2b81` |

非法 OHLC、重复业务键、未验证来源、非对齐缺口均为 0。内部缺口只报告、不补 K。

## 成交额

[volume RCA](binance-ohlcv-volume-rca-2026-09-03.md)：已发布 4h 与独立 15m 完整桶求和，在事先声明容差内一致。legacy 1h 原生 `quote_volume` 与同时段 15m 之和不一致，记为来源/字段语义不同，不是 15m 求和不可加。公共日K缓存无 `volume` / `trade_count`，记 `NOT_IN_CACHE_SCHEMA`。

## 收口核验（本轮补做）

- `tests/test_ohlcv_round2_governance.py` + `tests/test_ohlcv_dataset_governance.py` + `tests/test_trusted_consumers.py` + `tests/test_data_layer.py`：60 passed
- `verify_round2_protected_integrity.py`：327,640 个受保护文件未变
- 拒绝用例：legacy 1h `FULL_MARKET`、缓存当 OHLCV、未知 `dataset_id`、错误 fingerprint、缺 manifest
- `check_trusted_consumers.py`：通过；P0R-DATA 登记为 catalog 消费者
- derived `--check --write-15m-snapshot --timeframe all`：1h/4h/1d 均为 `already_published`，未覆盖 v1

无聊天取数入口：[docs/data-lake-spec.md](../../../../docs/data-lake-spec.md) 第 16 节与 [example_binance_ohlcv_usage.py](../scripts/example_binance_ohlcv_usage.py)。机器 bundle：[binance_ohlcv_no_chat_usage_2026-09-03.json](../artifacts/binance_ohlcv_no_chat_usage_2026-09-03.json)。

## 仍待用户批准

1. 删除/归档 legacy normalized 1h
2. 从 canonical 1d 重建家族日面板
3. 把 MCSM / CTP 等历史脚本迁到 `dataset_id`（会改变旧复现路径）
4. 隔离或修复 ccxt 15m 空值来源
5. 另开会话跑 4H 全市场 `P0R-DATA` 结果；本轮只完成取数门禁
