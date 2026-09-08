# Decision Log — Binance-OHLCV-Data-Lake-Governance

## 2026-09-07 — 统一 Agent 路由、组合 v2 与研究启动门禁

决策：按用户授权新增不可变组合 v2，统一绑定价格 V3、高周期 v2 和费率 v2；新研究按规范第 19 节冻结请求并通过启动检查。文件完整性与研究窗口资格分开，身份或费率日历不足时拒绝净收益；不改旧组合、读取器、数据和消费者。

证据：[发布契约](specs/binance-v3-research-input-bundle-v2-2026-09-07.md)、[固定清单](specs/binance-v3-research-input-bundle-v2.json)、[交接验收](diagnostics/binance-research-bundle-v2-startup-2026-09-07.md)。

## 2026-09-07 — 资金费率 v2 事件治理，保留覆盖限制

决策：按用户确认发布不可变 `funding.v3_inputs.v2`，官方原文裁决毫秒表示差异、独立保留 Regular / Special，不覆盖旧数据和消费者。事件歧义清零仍保留 `PARTIAL_COVERAGE`，净收益必须通过历史频率与独立身份门禁；剩余未检索区间的零成交价格证据不能证明无结算，本轮不是全历史日历完成或策略 PASS。

证据：[契约](specs/binance-funding-v3-inputs-v2-2026-09-07.md)、[验收与限制](diagnostics/binance-funding-v3-inputs-v2-2026-09-07.md)、[机器验收](artifacts/binance_funding_v3_inputs_v2_20260907/acceptance.json)。

## 2026-09-07 — V3 配套高周期与保守研究读取门禁

决策：显式发布基于 V3 的高周期 v2，旧版本和冻结消费者保留。价格验收通过，但资金费率补齐遇远端 403、历史身份/结算日历仍有限制，整套统一研究输入不作无条件 READY 或策略 PASS 声明。

执行结果：费率 `v3_inputs.v1` 以 `PARTIAL_COVERAGE` 发布，2,660,857 精确时间键；634 个 API 查询保留未完成。2,326 份归档查询全部处理，其中 1,344 份文件通过校验。价格/费率范围单独对账，未把 46 个范围外旧费率代码映射进 V3。59 项定向测试通过；本轮状态 `PARTIAL_BLOCKED_FUNDING_ACCESS`，后续补齐不覆盖本次版本。

证据：[契约](specs/binance-v3-research-inputs-v1-2026-09-07.md)、[治理报告](diagnostics/binance-v3-research-inputs-v1-2026-09-07.md)、[机器清单](artifacts/binance_v3_research_inputs_v1_20260907/research_input_bundle.json)。

## 2026-09-06 — V3 全历史扫描、补洞与边界分段治理收口

决策：发布 `binance.perp.ohlcv.15m.history.v3`，记录 `GOVERNED_WITH_EXPLICIT_BOUNDARY_EXCLUSIONS`；可恢复历史记录已补入，残余上线/重开边界保留并禁止跨越，不将其包装为原始网格无空位、完整 PIT 或全仓消费者治理完成。

证据：[V3 主契约](specs/binance-15m-history-v3-contract-2026-09-06.md)、[别名补充](specs/binance-15m-history-v3-alias-evidence-2026-09-06.md)、[V3 验收与使用限制](diagnostics/binance-15m-history-v3-closeout-2026-09-06.md)。

## 2026-09-06 — 15m V2 发布；历史治理部分完成

用户授权优先治理并更新 15m，不下载 1m/5m。发布 `binance.perp.ohlcv.15m.refreshed.v2` 并通过发布后严格内容哈希及全量 SQL 验收：61,291,949 行，冻结闭合截止北京时间 2026-09-05 23:45。526 个当前活跃 COIN/INDEX 合约尾部齐全，旧底座指纹未变。原缺口补回 80,352 根，但最终快照仍有 143 段 / 286,882 个缺失网格位置，其中 126 段涉及非活跃合约衔接窗口未完整探测。行质量 PASS 不代表历史完整性治理完成；不自动更新高周期或迁移旧消费者。

证据：[V2 契约](specs/binance-15m-refresh-v2-contract-2026-09-05.md)、[验收与执行偏差](diagnostics/binance-15m-refresh-v2-acceptance-2026-09-06.md)。

## 2026-09-02 — 启动 Binance OHLCV 身份治理

决策：把 Binance 数据流固定为 `raw → accepted normalized 15m → versioned derived 1h/4h/1d → family cache → research artifacts`；当前 normalized 1h 登记为 `PARTIAL_SCOPE_LEGACY`，公共日K与 MA7 RC 面板登记为 `FAMILY_CACHE`。本轮只做非破坏性治理，不覆盖旧 parquet，不重跑策略。

证据：[身份契约](specs/binance-ohlcv-dataset-identity-contract-2026-09-02.md)、[data-lake-spec](../../../docs/data-lake-spec.md)。

## 2026-09-02 — 治理基础就绪

决策：现场审计、scope gate、cache sidecar、15m→1h/4h/1d 发布与对账均完成，状态 `GOVERNANCE_FOUNDATION_READY`。legacy 1h 不能再经新入口冒充 `FULL_MARKET`。旧 parquet 未改写。不把该状态解释为策略通过。

证据：[现场审计](diagnostics/binance-ohlcv-dataset-inventory-2026-09-02.md)、[对账](diagnostics/binance-ohlcv-reconciliation-2026-09-02.md)、[P0R-DATA 交接](specs/binance-4h-ma7-rc-p0r-data-handoff-2026-09-02.md)。

## 2026-09-03 — 第二轮可信读取门禁收口

决策：基础设施记 `READY`，15m 与 `from_15m.v1` 全量 SQL `PASS`，消费者仍 `PARTIAL`。不以笼统 READY 覆盖 legacy 1h、家族缓存和未迁移历史脚本。不把本轮解释为策略通过，也不外推 4H 全市场结论。

证据：[第二轮契约](specs/binance-ohlcv-round2-trusted-load-contract-2026-09-03.md)、[验收](diagnostics/binance-ohlcv-round2-acceptance-2026-09-03.md)、[SQL 审计](diagnostics/binance-ohlcv-trusted-quality-audit-2026-09-03.md)、[成交额追溯](diagnostics/binance-ohlcv-volume-rca-2026-09-03.md)。

## 2026-09-03 — 第三轮可信读取与截止契约

决策：Round 3 基础设施门禁记 `READY`；15m 与 `from_15m.v1` 行质量 `PASS` 但历史覆盖为内部缺口；4h 全市场研究 `gap_policy=reject` 为 `UNFIT`；消费者仍 `PARTIAL`；legacy 1h `quote_volume` 已按小时追溯但仍保留机器 blocker。不把本轮解释为策略通过，不发布生产新版本，不自动开始 4h MA7 研究。

证据：[第三轮契约](specs/binance-ohlcv-round3-trusted-load-contract-2026-09-03.md)、[验收](diagnostics/binance-ohlcv-round3-acceptance-2026-09-03.md)、[问题矩阵](diagnostics/binance-ohlcv-round3-issue-matrix-2026-09-03.md)、[SQL 审计 R3](diagnostics/binance-ohlcv-trusted-quality-audit-r3-2026-09-03.md)、[成交额追溯 R3](diagnostics/binance-ohlcv-volume-rca-r3-2026-09-03.md)。

## 2026-09-03 — 消费者门禁改为 deny-by-default + frozen 清单

决策：`check_trusted_consumers.py` 扫描全部 `research/**/scripts/*.py`。出现 `read_parquet` 或 `data/normalized|data/derived|data/cache|data/raw` 字面量、且不在已登记白名单 / `CONTROLLED_EXCEPTION_PREFIXES` / `scripts/governance/frozen_research_scripts.txt` 的脚本 FAIL。首次把当前命中脚本全部写入冻结清单，之后清单行数只减不增。不改冻结脚本行为，不删数据。`data/cache/binance_perp_1d_from_15m` 的 `input_manifest_sha256` / `config_parameter_sha256` 无法无损回填（构建早于 manifest 哈希约定），保持 `LINEAGE_INCOMPLETE`，新代码改用 `binance.perp.ohlcv.1d.from_15m.v1`。

证据：[data-lake-spec §12–§15](../../../docs/data-lake-spec.md)、[frozen_research_scripts.txt](../../../scripts/governance/frozen_research_scripts.txt)、[check_trusted_consumers.py](../../../scripts/governance/check_trusted_consumers.py)。
