# Binance-OHLCV-Data-Lake-Governance Core Ledger

## Family Identity

- Full family name / alias：`Binance-OHLCV-Data-Lake-Governance` / `BIN-OHLCV-DLG`。
- Market / timeframe：Binance USD-M USDT perpetual OHLCV；底座为 accepted normalized `15m`。
- Mechanism：用 `dataset_id` 固定数据身份与 scope；partial/unaccepted 数据 fail closed；由 15m 生成版本化 1h/4h/1d；cache 只能作为可重建家族产物。
- Boundary：这是平台数据治理线，不是交易策略；不得把治理完成解释为策略 PASS，也不得覆盖 legacy normalized 1h。

## Current State

- Current observation：`15m.history.v3` 完成 V2 全部观测历史扫描、官方 API/Vision 补洞与边界分段，状态 `GOVERNED_WITH_EXPLICIT_BOUNDARY_EXCLUSIONS`；原网格仍有 12 段空位，不等于无缺口或完整 PIT。截止仍为北京时间 2026-09-05 23:45，526 个活跃 COIN/INDEX 尾部齐全。可信读取、内容哈希及消费者 deny-by-default 保留。
- Status（分项，不以笼统 READY 代替缺口）：基础设施门禁 `READY`；数据集 15m 与 `from_15m.v1` 行质量 `PASS`、历史覆盖 `INTERNAL_GAPS`；4h 全市场研究 `gap_policy=reject` 为 `UNFIT`；legacy 1h 仍是 `PARTIAL_SCOPE_LEGACY`；家族缓存仍是 `FAMILY_CACHE`；消费者 `PARTIAL`（历史直读已冻结清单，新直读默认拒绝）；legacy 1h `quote_volume` 有本地追溯但仍保留 blocker。这不是策略 PASS。
- Runner / dry-run / live：none。
- Next gate：新研究显式锁定 V3 或配套高周期 v2、截止及有效连续段；12 段边界禁止跨越。2026-09-07 资金费率续治理独立发布 v2，消除事件歧义并补到所有 V3 代码有观测；净收益只允许通过已验证片段及独立身份门禁的窗口。完整 PIT/结算日历、全历史远端修订复核及旧消费者迁移不冒充已完成。

## Version Rules

- 数据版本与策略版本分离。`from_15m.v1` 是衍生数据集版本，不是策略 `V1`。
- 已发布 derived 目录不可覆盖；公式、phase、来源裁决、输入窗口或 cutoff 变化必须新 `vN`。
- cache sidecar 不是新数据版本；缺字段 / `LINEAGE_INCOMPLETE` 不得进入新研究可信消费。
- Round 3 修读取门禁，不发布生产新的 OHLCV 数据版本。

## Version Table

| Observation | Status | Role / Core Idea | Key Frozen Metrics | Evidence | Decision |
| --- | --- | --- | --- | --- | --- |
| `15m.normalized.v1` | `TRUSTED_BASE` | Binance 全市场可信底座 | 60,266,362 行 / 853 symbols；库存指纹 `c615a4c1…` | [inventory](diagnostics/binance-ohlcv-dataset-inventory-2026-09-02.md) · [SQL R3](diagnostics/binance-ohlcv-trusted-quality-audit-r3-2026-09-03.md) | 新研究必须用 dataset-id 入口 |
| `15m.refreshed.v2` | `TRUSTED_DERIVED`；行质量 `PASS`；历史 `INTERNAL_GAPS` | 保留旧键，官方 API 补缺键，同周期独立快照 | 61,291,949 行 / 874 合约；新增 1,025,587 行；526 活跃尾部齐；143 段 / 286,882 网格位置缺口 | [V2 验收](diagnostics/binance-15m-refresh-v2-acceptance-2026-09-06.md) | 本轮截止 2026-09-05 15:45 UTC；历史治理部分完成；旧高周期未更新 |
| `15m.history.v3` | `TRUSTED_DERIVED`；行质量 `PASS`；边界排除治理收口 | API、月度/日度 CHECKSUM 与 settled 别名补洞，旧键保留 | 61,577,807 行 / 874 合约；补回 285,858 根；残余 12 段 / 1,024 网格位置有排除处置 | [V3 验收](diagnostics/binance-15m-history-v3-closeout-2026-09-06.md) | 只允许显式分段消费；不是无缺口/全 PIT/策略 PASS |
| `1h.normalized.legacy` | `PARTIAL_SCOPE_LEGACY` | 残缺 1h；原生 quote_volume 不可加 | 以现场审计与 R3 RCA 为准 | [inventory](diagnostics/binance-ohlcv-dataset-inventory-2026-09-02.md) · [RCA R3](diagnostics/binance-ohlcv-volume-rca-r3-2026-09-03.md) | `FULL_MARKET` fail closed |
| `1h/4h/1d.from_15m.v1` | `TRUSTED_DERIVED` | UTC 完整桶聚合；v1 cutoff 为 null | 1h 15,066,337；4h 3,766,251 / 缺口 5,577；1d 627,283 | derived `_MANIFEST.json` · [SQL R3](diagnostics/binance-ohlcv-trusted-quality-audit-r3-2026-09-03.md) | 消费须显式 cutoff；全市场 `reject` UNFIT |
| `1h/4h/1d.from_15m.v2` | `TRUSTED_DERIVED`；行质量 `PASS`；保留边界缺口 | 唯一 V3 输入，完整桶；已通过发布后独立读取验收 | 874 合约；1h 15,393,559；4h 3,847,414；1d 640,378 | [统一输入契约](specs/binance-v3-research-inputs-v1-2026-09-07.md) · [清单](artifacts/binance_v3_research_inputs_v1_20260907/research_input_bundle.json) | 旧 v1 不改；资金费率/历史身份不随价格 PASS 自动通过 |
| `funding.v3_inputs.v1` | 行质量 `PASS`；`PARTIAL_COVERAGE` | 保留原始毫秒及歧义，独立费率读取，不与 OHLCV 混表 | 2,660,857 精确键；增加 160,070；V3 价格 864/874 有任意费率观测；634 查询未完成 | [费率验收](artifacts/binance_v3_research_inputs_v1_20260907/funding/acceptance.json) · [范围审计](artifacts/binance_v3_research_inputs_v1_20260907/funding/price_scope_audit.json) | 910 库存代码不等于 910 个可用 USDT 标的；缺日历/有歧义的净收益拒绝，后续补齐须新版本 |
| `funding.v3_inputs.v2` | 行质量 `PASS`；`PARTIAL_COVERAGE` | 官方原生事件裁决、特殊结算分离、历史频率片段门禁 | 2,654,430 行 / 874 代码；0 歧义 / 34 Special；639 片段 / 585 标的；71 个未检索范围全为零成交价格区间 | [v2 验收与边界](diagnostics/binance-funding-v3-inputs-v2-2026-09-07.md) · [机器验收](artifacts/binance_funding_v3_inputs_v2_20260907/acceptance.json) | 只准已验证片段内净收益；不是全历史完整，旧 v1/价格/读取入口不改 |
| `1d.cache` / MA7 RC panels | `FAMILY_CACHE` | 可重建，非标准 OHLCV | sidecar `.cache-meta.json` | cache sidecar | 不得当其他家族事实源 |
| Round 2 | 基础设施当时 `READY`；本轮不沿用为前提 | 可信读取第一轮收口 | 受保护文件 327,640 未变 | [第二轮契约](specs/binance-ohlcv-round2-trusted-load-contract-2026-09-03.md) · [验收](diagnostics/binance-ohlcv-round2-acceptance-2026-09-03.md) | 历史消费者未全迁 |
| Round 3 | 基础设施 `READY`；数据集 `PASS`+缺口；消费者 `PARTIAL` | 闭合 cutoff、严格 manifest、内容哈希、缺口边界、原始 RCA | 4h 库存指纹 `a52be016…`；机器 blocker 仍在 RCA | [第三轮契约](specs/binance-ohlcv-round3-trusted-load-contract-2026-09-03.md) · [验收](diagnostics/binance-ohlcv-round3-acceptance-2026-09-03.md) | 门禁收口；不发生产 v2 |

## Shared Assumptions

- Data：Round 1–3 只治理本地数据；V2/V3 经用户授权下载官方 15m 增量与历史缺口，保留原始证据，不构成全历史远端重下载。
- Source union：Vision monthly 优先于 Futures API；未列入来源排除。
- Aggregation：4/16/96 根连续闭合合法 15m；不补 K；输出 bar 须 `ts + timeframe <= cutoff`。
- Cost / execution：不适用。

## Evidence Map

- [Family README](README.md)
- [资金费率 v2 治理与限制](diagnostics/binance-funding-v3-inputs-v2-2026-09-07.md)
- [V3 统一研究输入治理](diagnostics/binance-v3-research-inputs-v1-2026-09-07.md)
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
