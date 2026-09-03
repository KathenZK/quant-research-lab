# Binance OHLCV 第三轮契约（Round 3 / R3）

日期：2026-09-03  
范围：现有本地 Binance USD-M USDT perpetual OHLCV 的可信读取、截止时间、manifest、内容指纹、版本登记、缺口边界与成交额追溯。  
状态：门禁已冻结；验收见 [binance-ohlcv-round3-acceptance-2026-09-03.md](../diagnostics/binance-ohlcv-round3-acceptance-2026-09-03.md)。不覆盖 2026-09-02 身份契约，不把第二轮“基础设施 READY”当作本轮验收前提。

## 硬门禁

1. 输出 bar 必须 `bar_open + timeframe <= cutoff`。cutoff 用于输入选择、聚合、发布身份和最终读取，不能只写进 manifest。
2. 幂等身份 = 输入快照 + cutoff + 公式/来源规则 + 相关配置。任一变化必须拒绝同版本覆盖。
3. 研究消费必须显式 cutoff。整库治理审计必须声明 `purpose=governance_audit`。请求窗口超出可用范围默认拒绝。
4. 消费者从 `verified_parquet_files` 再查时必须使用同一闭合截止，不得退回 `ts < cutoff`。
5. derived manifest 用严格 schema；注册信息、manifest、实际数据的 exchange/market_type/timeframe/版本/scope/根路径必须一致。
6. 四种哈希分离：manifest 文件哈希、manifest 规范化内容指纹、parquet 内容库存指纹、输入快照指纹。内容指纹必须重算校验。
7. 历史 v1 `cutoff_exclusive_utc=null` 是登记例外，不得改写旧 manifest；读取必须另给显式消费截止。
8. SQL 审计按文件核验真实 schema，禁止靠 `union_by_name` / 强制 CAST / 自动补 UTC 把坏类型变成 PASS。
9. 严格可信读取必须验证 parquet 内容哈希。`size+mtime` 快路径必须显式标记，不得冒充严格验证。
10. 缓存 sidecar 缺字段、空值、`LINEAGE_INCOMPLETE`、未知 quality 均不得进入新可信消费。
11. 新版本必须走“构建 → 审计 → 发布 → 登记 → 查询 → 精确读取”；禁止扫描整个 data 根并自动信任所有 manifest。
12. 新研究必须显式选择 `gap_policy=reject` 或 `contiguous_segments`；不得默认 `report_only` 后继续算指标。
13. 成交额追溯必须落到本地原始文件；没有证据记 `UNRESOLVED`，机器 blocker 必须出现在验收和主账。

## 允许的研究入口

`load_trusted_research_dataset(...)`：必填 `end`/`cutoff`、`gap_policy`、`purpose="research"`。  
`load_trusted_dataset(..., purpose="governance_audit")`：仅治理整库扫描。  
`read_verified_ohlcv(...)`：对已通过的 trusted load 按闭合截止再取行。
