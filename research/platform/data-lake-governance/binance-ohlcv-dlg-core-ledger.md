# Binance-OHLCV-Data-Lake-Governance Core Ledger

## Family Identity

- Full family name / alias：`Binance-OHLCV-Data-Lake-Governance` / `BIN-OHLCV-DLG`。
- Market / timeframe：Binance USD-M USDT perpetual OHLCV；底座为 accepted normalized `15m`。
- Mechanism：用 `dataset_id` 固定数据身份与 scope；partial/unaccepted 数据 fail closed；由 15m 生成版本化 1h/4h/1d；cache 只能作为可重建家族产物。
- Boundary：这是平台数据治理线，不是交易策略；不得把治理完成解释为策略 PASS，也不得覆盖 legacy normalized 1h。

## Current State

- Current observation：消费者门禁改为 deny-by-default：扫描 `research/**/scripts/*.py` 的 `read_parquet` 与湖路径字面量；未登记、非受控例外、不在 `frozen_research_scripts.txt` 的新脚本 FAIL。Round 3 可信读取 / 闭合截止 / 内容哈希 / 研究缺口边界仍保留。
- Status（分项，不以笼统 READY 代替缺口）：基础设施门禁 `READY`；数据集 15m 与 `from_15m.v1` 行质量 `PASS`、历史覆盖 `INTERNAL_GAPS`；4h 全市场研究 `gap_policy=reject` 为 `UNFIT`；legacy 1h 仍是 `PARTIAL_SCOPE_LEGACY`；家族缓存仍是 `FAMILY_CACHE`；消费者 `PARTIAL`（历史直读已冻结清单，新直读默认拒绝）；legacy 1h `quote_volume` 有本地追溯但仍保留 blocker。这不是策略 PASS。
- Runner / dry-run / live：none。
- Next gate：不自动开始 4h MA7 研究；不删除旧数据；破坏性清理、面板重建、历史脚本迁移仍待用户批准。冻结清单只减不增。

## Version Rules

- 数据版本与策略版本分离。`from_15m.v1` 是衍生数据集版本，不是策略 `V1`。
- 已发布 derived 目录不可覆盖；公式、phase、来源裁决、输入窗口或 cutoff 变化必须新 `vN`。
- cache sidecar 不是新数据版本；缺字段 / `LINEAGE_INCOMPLETE` 不得进入新研究可信消费。
- Round 3 修读取门禁，不发布生产新的 OHLCV 数据版本。

## Version Table

| Observation | Status | Role / Core Idea | Key Frozen Metrics | Evidence | Decision |
| --- | --- | --- | --- | --- | --- |
| `15m.normalized.v1` | `TRUSTED_BASE` | Binance 全市场可信底座 | 60,266,362 行 / 853 symbols；库存指纹 `c615a4c1…` | [inventory](diagnostics/binance-ohlcv-dataset-inventory-2026-09-02.md) · [SQL R3](diagnostics/binance-ohlcv-trusted-quality-audit-r3-2026-09-03.md) | 新研究必须用 dataset-id 入口 |
| `1h.normalized.legacy` | `PARTIAL_SCOPE_LEGACY` | 残缺 1h；原生 quote_volume 不可加 | 以现场审计与 R3 RCA 为准 | [inventory](diagnostics/binance-ohlcv-dataset-inventory-2026-09-02.md) · [RCA R3](diagnostics/binance-ohlcv-volume-rca-r3-2026-09-03.md) | `FULL_MARKET` fail closed |
| `1h/4h/1d.from_15m.v1` | `TRUSTED_DERIVED` | UTC 完整桶聚合；v1 cutoff 为 null | 1h 15,066,337；4h 3,766,251 / 缺口 5,577；1d 627,283 | derived `_MANIFEST.json` · [SQL R3](diagnostics/binance-ohlcv-trusted-quality-audit-r3-2026-09-03.md) | 消费须显式 cutoff；全市场 `reject` UNFIT |
| `1d.cache` / MA7 RC panels | `FAMILY_CACHE` | 可重建，非标准 OHLCV | sidecar `.cache-meta.json` | cache sidecar | 不得当其他家族事实源 |
| Round 2 | 基础设施当时 `READY`；本轮不沿用为前提 | 可信读取第一轮收口 | 受保护文件 327,640 未变 | [第二轮契约](specs/binance-ohlcv-round2-trusted-load-contract-2026-09-03.md) · [验收](diagnostics/binance-ohlcv-round2-acceptance-2026-09-03.md) | 历史消费者未全迁 |
| Round 3 | 基础设施 `READY`；数据集 `PASS`+缺口；消费者 `PARTIAL` | 闭合 cutoff、严格 manifest、内容哈希、缺口边界、原始 RCA | 4h 库存指纹 `a52be016…`；机器 blocker 仍在 RCA | [第三轮契约](specs/binance-ohlcv-round3-trusted-load-contract-2026-09-03.md) · [验收](diagnostics/binance-ohlcv-round3-acceptance-2026-09-03.md) | 门禁收口；不发生产 v2 |

## Shared Assumptions

- Data：只治理现有本地数据，不下载新行情。
- Source union：Vision monthly 优先于 Futures API；未列入来源排除。
- Aggregation：4/16/96 根连续闭合合法 15m；不补 K；输出 bar 须 `ts + timeframe <= cutoff`。
- Cost / execution：不适用。

## Evidence Map

- [Family README](README.md)
- [身份契约](specs/binance-ohlcv-dataset-identity-contract-2026-09-02.md)
- [第三轮契约](specs/binance-ohlcv-round3-trusted-load-contract-2026-09-03.md)
- [第三轮验收](diagnostics/binance-ohlcv-round3-acceptance-2026-09-03.md)
- [问题矩阵](diagnostics/binance-ohlcv-round3-issue-matrix-2026-09-03.md)
- [第二轮契约](specs/binance-ohlcv-round2-trusted-load-contract-2026-09-03.md)
- [第二轮验收](diagnostics/binance-ohlcv-round2-acceptance-2026-09-03.md)
- [现场审计](diagnostics/binance-ohlcv-dataset-inventory-2026-09-02.md)
- [对账](diagnostics/binance-ohlcv-reconciliation-2026-09-02.md)
- [成交额追溯 R3](diagnostics/binance-ohlcv-volume-rca-r3-2026-09-03.md)
- [全量 SQL 质量 R3](diagnostics/binance-ohlcv-trusted-quality-audit-r3-2026-09-03.md)
- [消费者迁移 R3](diagnostics/binance-ohlcv-consumer-migration-r3-2026-09-03.md)
- [4H P0R 交接](specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md)
- [产物索引](artifacts/README.md)
- [data-lake-spec §16](../../../docs/data-lake-spec.md)
- [catalog.py](../../../src/strategy_lab/data/catalog.py)
