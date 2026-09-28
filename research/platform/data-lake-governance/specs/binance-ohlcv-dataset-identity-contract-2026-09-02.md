# Binance OHLCV 数据集身份契约

日期：2026-09-02  
状态：冻结治理口径；不下载新数据、不覆盖 legacy parquet。

## 目标数据流

```text
Binance 原始来源 → raw → accepted normalized 15m
                 → versioned derived 1h/4h/1d
                 → family cache
                 → research artifacts
```

## 注册表

| dataset_id | status | scope | 物理根 |
| --- | --- | --- | --- |
| `binance.perp.ohlcv.15m.normalized.v1` | `TRUSTED_BASE` | `FULL_MARKET` | `data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=15m` |
| `binance.perp.ohlcv.1h.normalized.legacy` | `PARTIAL_SCOPE_LEGACY` | `PARTIAL` | `data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=1h` |
| `binance.perp.ohlcv.1h.from_15m.v1` | `TRUSTED_DERIVED` | `FULL_MARKET` | `data/derived/datasets/binance_perp_1h_from_15m_v1` |
| `binance.perp.ohlcv.4h.from_15m.v1` | `TRUSTED_DERIVED` | `FULL_MARKET` | `data/derived/datasets/binance_perp_4h_from_15m_v1` |
| `binance.perp.ohlcv.1d.from_15m.v1` | `TRUSTED_DERIVED` | `FULL_MARKET` | `data/derived/datasets/binance_perp_1d_from_15m_v1` |
| `binance.perp.ohlcv.1d.cache.from_15m` | `FAMILY_CACHE` | `FAMILY_PANEL` | `data/cache/binance_perp_1d_from_15m` |
| `binance.perp.panel.1d.ma7_rc.p0` | `FAMILY_CACHE` | `FAMILY_PANEL` | `data/cache/binance-1d-ma7-rc-p0` |
| `binance.perp.panel.1d.ma7_rc.p3` | `FAMILY_CACHE` | `FAMILY_PANEL` | `data/cache/binance-1d-ma7-rc-p3` |

## Fail-closed

- 请求 `FULL_MARKET` 时，`PARTIAL_SCOPE_LEGACY` / unaccepted / coverage 不足必须报错。
- coverage 必须看时间跨度、symbol-day、长期历史 symbol 和短快照占比，不能只看 distinct symbol。
- catalog 找不到物理根时不得扫描整个 `data/`。
- 不同 `dataset_id` 不得被递归 glob 混读。
- 重复业务键、未知来源、scope 不足阻止 trusted load。

## 衍生公式

- union：`binance_perp_15m_priority_union_v1`
- formula：`ohlcv_resample_from_15m_v1`
- 1h=4、4h=16、1d=96 根连续闭合合法 15m
- UTC phase `00:00`；不补 K
- 混合来源：`composite:<sorted+sources>`

## 重建命令

```text
python research/platform/data-lake-governance/scripts/audit_binance_ohlcv_dataset_inventory.py
python research/platform/data-lake-governance/scripts/write_binance_cache_sidecars.py
python research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py --timeframe all
python research/platform/data-lake-governance/scripts/reconcile_binance_derived_ohlcv.py
python research/platform/data-lake-governance/scripts/verify_pre_governance_integrity.py
```

细则以 [docs/data-lake-spec.md](../../../../docs/data-lake-spec.md) 为准。
