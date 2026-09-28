# Binance OHLCV 第三轮验收（2026-09-03）

性质：代码实现与独立验收。不沿用第二轮「基础设施 READY」作为前提。先复现，再修复，再对真实数据跑 `sql_audit_v2` + `strict_content`。不覆盖第一、二轮证据，不发布生产新数据版本，不自动开始 4h MA7 研究。

## 分项结论

| 分项 | 状态 | 含义 |
| --- | --- | --- |
| 基础设施门禁 | `READY` | 闭合 cutoff、严格 manifest、逐文件 schema、内容哈希、缓存 lineage、显式登记、研究缺口策略均有回归测试；越界窗口与坏清单默认拒绝 |
| 各数据集 | `PASS` / 缺口保留 | 15m 与 `1h/4h/1d.from_15m.v1` 行质量 `PASS`；历史覆盖均为 `INTERNAL_GAPS`；legacy 1h 仍是 `PARTIAL_SCOPE_LEGACY`；家族缓存仍是 `FAMILY_CACHE` |
| 消费者迁移 | `PARTIAL` | 新研究入口是 `load_trusted_research_dataset`；P0R-DATA 仍走已登记的 `load_trusted_dataset`+`report_only` 历史路径；其余历史脚本未迁 |
| 原始差异追溯 | `EXPLAINED_WITH_LOCAL_EVIDENCE` / blocker 保留 | 新 4h 与独立 15m 重聚一致；18 个 legacy 1h 差异小时均有本地 raw；legacy `quote_volume` 仍不可作新研究可加字段 |
| 文档与 preflight | 见文末核验 | 第 16 节与用法 bundle 已跑；平台表不再当策略状态；消费者发现范围已写明 |

这不是策略 PASS，也不是 4h 全市场研究窗口 `FIT`。

## 后续 Agent 可使用的精确版本

| 用途 | dataset_id | 操作入口 |
| --- | --- | --- |
| 15m 底座 | `binance.perp.ohlcv.15m.normalized.v1` | `load_trusted_dataset(..., purpose="governance_audit")` 或研究 API + 显式 cutoff / `gap_policy` |
| 标准 1h/4h/1d | `binance.perp.ohlcv.{1h,4h,1d}.from_15m.v1` | `load_trusted_research_dataset`；钉死 `parquet_inventory_fingerprint` 与 manifest 身份；v1 `cutoff_exclusive_utc` 为 null，必须另给消费截止 |
| canonical 日K | 同上 1d | `load_canonical_binance_perp_1d`；不要用 `data/cache/binance_perp_1d_from_15m` |
| 4h 单币连续样本 | `4h.from_15m.v1` + `SINGLE_SYMBOL` | BTC 4h 缺口表无内部缺口，`gap_policy=reject` 可用；全市场 `reject` 为 `UNFIT` |
| 整库治理扫描 | 已登记版本 | 必须 `purpose="governance_audit"`，不得冒充新研究 |
| 查询目录 | `list_registered_datasets` | 示例脚本 `list` / `inspect`；`inspect.trusted` 恒为 false |

4h 钉死身份（本轮严格审计）：库存指纹 `a52be016421363b2bfbcdcc6d61b02288de206dfc330d3b4df0a2fa11d0be8a6`；manifest 文件哈希 `de567a5cea103f104dc52a0bd925db9ea9d3bf824b62cc7d4b8cb82246e612cf`；内容指纹 `a766fc203621e73c2025b11e87676f4b53d5b27d16c2b373184ede0b5ad82522`。15m 输入快照仍为 `c615a4c12cd8392fbf083ad2b0ffaa693d65837da19f797813e7f726d377475a`。

## 真实数据（本轮重跑，不复用第二轮 SQL PASS）

证据：[binance-ohlcv-trusted-quality-audit-r3-2026-09-03.md](binance-ohlcv-trusted-quality-audit-r3-2026-09-03.md)。规则 `binance_ohlcv_sql_audit_v2`，`fingerprint_mode=strict_content`，`purpose=governance_audit`。

| dataset_id | rows | symbols | 内部缺失 K | row_quality | 观测止 |
| --- | --- | --- | --- | --- | --- |
| `15m.normalized.v1` | 60,266,362 | 853 | 89,152 | PASS | 2026-08-24T23:45Z |
| `1h.from_15m.v1` | 15,066,337 | 853 | 22,293 | PASS | 2026-08-24T23:00Z |
| `4h.from_15m.v1` | 3,766,251 | 853 | 5,577 | PASS | 2026-08-24T20:00Z |
| `1d.from_15m.v1` | 627,283 | 853 | 935 | PASS | 2026-08-24T00:00Z |

4h 全市场 `purpose=research` + `gap_policy=reject` 被拒绝（`missing_bars=5577`）。逐 symbol 缺口 132 段，原因 `unknown`，不得把首尾当成已确认上市/退市。

## 硬门禁对照

| ID | 结果 |
| --- | --- |
| R3-01 闭合 cutoff 贯穿构建/发布/消费 | 通过 |
| R3-02 严格 manifest 与研究输入身份 | 通过 |
| R3-03 逐文件真实 schema / 市场身份 | 通过 |
| R3-04 内容指纹与审计缓存失效 | 通过 |
| R3-05 缓存 lineage 与版本登记闭环 | 通过（临时湖 e2e；生产未发 v2） |
| R3-06 研究缺口边界 | 通过（缺口保留，全市场 reject 拒绝） |
| R3-07 成交额追溯到原始证据 | 新派生通过；legacy blocker 保留在 RCA/主账 |
| R3-08 文档、入口、防回退 | 通过（preflight 细节见文末） |

## 成交额

[R3 RCA](binance-ohlcv-volume-rca-r3-2026-09-03.md)：六资产新 4h 与独立 15m 完整桶 `quote_volume` 失配 0。18 个 legacy 1h 实质差异小时分类为 SOURCE_REVISION 9、SEMANTIC_DIFFERENCE_WITH_LOCAL_RAW_EVIDENCE 4、RAW_1H_EQUALS_FIRST_15M_COMPONENT 4、PROXY_FIELD 1。机器 blocker：legacy 原生 1h `quote_volume` 与 15m 之和不一致，不能当可信可加字段。新派生正确 ≠ 旧源问题已关闭。

## 核验

- 相关 pytest：106 passed（ohlcv R1/R2/R3、data layer、trusted consumers、docs consistency、live specs、P0R-DATA）
- 受保护文件：327,640 个未变（[verify_round3_protected_integrity.py](../scripts/verify_round3_protected_integrity.py)）
- 用法 bundle：[binance_ohlcv_no_chat_usage_r3_2026-09-03.json](../artifacts/binance_ohlcv_no_chat_usage_r3_2026-09-03.json)
- 测试摘要：[binance_ohlcv_r3_test_summary_2026-09-03.json](../artifacts/binance_ohlcv_r3_test_summary_2026-09-03.json)
- `check_trusted_consumers.py`：通过
- 文档一致性：28 passed（含平台表不按策略 glossary 计分）
- 完整 `preflight.py`：trusted consumers 与文档通过；`promotion surface` 与 `live artifact budget` 仍因既有 HYPE/大文件失败，其中 R2/R3 保护清单 CSV 约 70MB 与第二轮相同量级。不把这些既有失败改名成 R3 通过。
- `tests/` 下 ruff 仍有 3 个既有 CTP 测试问题；本轮改动文件 ruff 通过，未为凑绿灯修改那些 CTP 文件。
- 问题矩阵：[binance-ohlcv-round3-issue-matrix-2026-09-03.md](binance-ohlcv-round3-issue-matrix-2026-09-03.md)

无聊天入口：[docs/data-lake-spec.md](../../../../docs/data-lake-spec.md) 第 16 节。

## 明确未做 / 未关闭

1. 不删除、不覆盖 raw / normalized / 已发布 v1 / 旧 artifacts。
2. 不把 4h 全市场当连续研究窗；P0R-DATA 结果会话未自动开始。
3. legacy 1h `quote_volume` 仍不可信。
4. 历史 MCSM / CTP / 日面板缓存未迁移。
5. 全库 ruff 若仍失败于既有 CTP 测试文件，不记为本轮治理门禁，也不为凑绿灯改那些文件。
