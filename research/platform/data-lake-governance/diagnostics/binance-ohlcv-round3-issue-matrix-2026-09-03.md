# Binance OHLCV Round 3 问题矩阵

日期：2026-09-03  
性质：独立复现后修复。不把第二轮 READY 当前提。修复前机器结果：[binance_ohlcv_r3_pre_fix_repro_2026-09-03.json](../artifacts/binance_ohlcv_r3_pre_fix_repro_2026-09-03.json)。

| ID | 问题 | 修复前复现 | 实现 | 回归测试 | 真实数据 / 范围 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| R3-01 | cutoff 不约束聚合/发布身份；越界窗口静默截短仍 PASS | 截止 `2026-07-01T01:00:00Z` 仍产出 `end=02:00`（收盘 `03:00`）；改 cutoff 仍 `already_published`；请求 `2026-09-03` 对 4h 实际 `2026-08-24T20:00Z` 仍 PASS | `windows.py` 闭合截止；`resample.py` 输出 `ts+tf<=cutoff`；发布身份含 cutoff；`catalog`/`read_verified_ohlcv` 同一闭合语义；越界默认 `REQUEST_WINDOW_EXCEEDS_AVAILABLE` | `test_r3_01_cutoff_applies_to_output_bars_and_unaligned_consumer`（含 `01:30`） | 用法 bundle 含超范围拒绝；生产 4h 最后一根 `2026-08-24T20:00Z` | 已解决 |
| R3-02 | 改错 exchange/market_type/timeframe/input/cutoff 后 manifest 仍 PASS | 假清单 `kraken` 被 `assert_published_derived_manifest` 接受 | 严格 derived schema；四种哈希分离；内容指纹重算；注册/清单/数据核对；历史 v1 空 cutoff 仅登记三套 `from_15m.v1` | `test_ohlcv_round3_governance.py` R3-02 段 | 生产 1h/4h/1d v1 严格读取 PASS；未改写旧 manifest | 已解决 |
| R3-03 | 非物化 SQL 把坏 schema/身份 CAST 成 PASS | 异交易所、spot、字符串 `is_closed`、naive `ts`、`trade_count=inf` 均曾 PASS | `sql_audit.py` v2：逐文件 DESCRIBE、禁止靠 union/CAST 洗类型、身份全量核对、`epoch_us` 网格、有限整数 `trade_count`；合法 numeric 类型按等价类比较（BIGINT/DOUBLE 同属 numeric） | `test_r3_03_sql_audit_rejects_bad_schema_and_identity`（含混合 BIGINT/DOUBLE PASS） | 15m/1h/4h/1d 全量 `schema_errors=[]`，`row_quality=PASS` | 已解决 |
| R3-04 | 同 size+mtime 改内容仍复用旧指纹/审计 | 代码快路径按 `(relpath,size,mtime)`；现场 XOR 复现未稳定打出 reused 缓存，属实现缺陷而非生产已污染 | `FingerprintMode.STRICT_CONTENT` 默认读内容哈希；`FAST_METADATA` 必须显式且不得声称内容证明；审计缓存绑定规则版本/窗口/缺口策略；损坏缓存重审 | `test_r3_04_strict_hash_detects_same_size_mtime_rewrite` | 本轮全量审计 `fingerprint_mode=strict_content`，未复用第二轮 SQL PASS | 已解决 |
| R3-05 | 删除 lineage 字段仍可能通过；新版本默认注册表不认识 | 缺 `input_manifest_sha256` 时 sidecar 通过 | 缓存 sidecar 完整 schema；缺/空/`LINEAGE_INCOMPLETE`/未知 quality 拒绝（历史仅 opt-in）；`_DATASET_REGISTRY.json` 显式登记，禁止扫全库信任 manifest；dry-run 不得写发布/快照/注册 | `test_r3_05_cache_missing_fields_and_registry_roundtrip`；用法 `publish-register-load` | 生产未发布新 v2（正确）；临时湖可查询读取新版本 | 已解决（生产无新版本） |
| R3-06 | 内部缺口只 report_only，研究默认可跨断档 | 第二轮 4h SQL `gap_policy=report_only`，5,577 根缺失 | 分行质量/历史覆盖/研究窗口适用性；新研究必须 `reject` 或 `contiguous_segments`；逐 symbol 缺口表；MA7/持有期窗口助手 | `test_ohlcv_round3_governance.py` 缺口与 MA7 助手 | 4h 132 段、5,577 根；全市场 `reject` 拒绝；`listing_evidence=unknown` | 已解决（缺口本身不补造） |
| R3-07 | 旧 1h 成交额差异未追溯到原始文件 | 第二轮机器仍有 blocker，文字写成语义不同 | 独立重聚；18 个实质差异小时全部落到本地 raw；分类见 RCA | RCA 脚本与 CSV | 新 4h 与独立 15m 重聚 0 笔 `quote_volume` 失配；legacy 1h 仍有 blocker，不得当可信可加字段 | 部分解决：有证据分类；旧源不可信未关闭 |
| R3-08 | 平台状态被策略 glossary 误伤；消费者检查覆盖面不清 | 文档一致性 16 pass / 1 fail | 跳过「研究平台」表；catalog API 在整个 `research/` 发现未登记脚本；治理脚本为受控例外 | `test_platform_routing_table_is_not_scored_as_strategy_status`；`test_unregistered_catalog_consumer_outside_watch_dir_is_detected` | 见第三轮验收的 preflight 记录 | 已解决 |
