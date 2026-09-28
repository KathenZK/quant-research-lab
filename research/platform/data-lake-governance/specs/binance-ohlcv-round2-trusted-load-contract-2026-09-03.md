# Binance OHLCV 第二轮可信读取与版本契约

日期：2026-09-03  
范围：Binance USD-M USDT perpetual OHLCV 身份、质量验证、版本发布、读取接口、缓存与消费者迁移。  
状态：本文件冻结本轮门禁，不覆盖 2026-09-02 身份契约。

## 硬门禁

1. `inspect_dataset` / `list_registered_datasets` 只做查询，`trusted=False`。
2. `load_trusted_dataset` 必须 SQL 全量质量审计；不得因行数跳过审计，也不得返回空 `audit`。
3. derived 可信读取必须验证已发布 `_MANIFEST.json`：缺失、多文件、文件增删改、身份冲突、质量未接受一律拒绝。
4. 闭合 cutoff：`ts + timeframe <= cutoff`；不得用 wall-clock now。
5. 同版本同输入同公式：验证后幂等成功。同版本不同输入：拒绝，要求新 `vN`。失败 staging 不得覆盖旧发布。
6. 15m 底座冻结身份是 `_INPUT_SNAPSHOT.json` 的 parquet 库存指纹，不是“目录名叫 v1”。
7. 不得修改已发布 v1 manifest 来补 cutoff。v1 的 `cutoff_exclusive_utc=null` 是历史事实。
8. `LINEAGE_INCOMPLETE` 默认不能进入新可信消费。家族缓存不能冒充 canonical OHLCV。
9. 旧 1h 不能满足 `FULL_MARKET`。

## 已接受版本（本轮读取）

| dataset_id | 用途 | 限制 |
| --- | --- | --- |
| `binance.perp.ohlcv.15m.normalized.v1` | 全市场底座 | 需 `_INPUT_SNAPSHOT.json`；内部缺口 report_only |
| `binance.perp.ohlcv.{1h,4h,1d}.from_15m.v1` | canonical 派生 | cutoff 为 null；调用方必须传显式闭合截止；绑定当时输入指纹与当时 builder，不要求等于今天工作区代码 |
| `binance.perp.ohlcv.1h.normalized.legacy` | 单币/诊断 | 禁止 FULL_MARKET |
| `binance.perp.ohlcv.1d.cache.from_15m` 等 | 历史缓存 | 非标准 OHLCV |

## 命令

见 [docs/data-lake-spec.md](../../../../docs/data-lake-spec.md) 第 16 节。
