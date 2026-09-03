# Data Lake Specification

本文件是 `quant-strategy-lab` 数据湖结构、身份、schema、质量门禁、写入和消费规则的
唯一规范来源。根 README、Cursor 规则、研究入口和脚本说明只应引用本文件，不得
另行维护一份通用数据湖约定。研究报告仍须记录其实际数据来源、范围和审计结果。

## 1. 范围与所有权

本仓库只维护一个本地数据湖。加密货币、股票及后续其他市场共用
`data/raw`、`data/normalized`、`data/derived`、`data/features` 与 `data/cache`
这些层，不得按资产、策略或提供方建立 `data/external`、`data/stocks` 或策略私有
数据根目录。`derived` 是版本化标准 OHLCV 发布层，不是第三层的临时别名。

`data/` 是本地数据资产，不因未提交 Git 而降低质量要求。被研究结论引用的审计
报告、迁移清单和可复现脚本必须保存在对应 `research/` 目录。

## 2. 分层结构

```text
data/
  raw/
    ohlcv/
      exchange=<真实交易场所>/
        market_type=<spot|perp|futures|equity>/
          timeframe=<周期>/
            source=<数据提供方>/
              date=<UTC 日期>/
                symbol=<标准化代码>.parquet
  normalized/
    ohlcv/
      exchange=<真实交易场所>/
        market_type=<spot|perp|equity>/
          timeframe=<周期>/
            date=<UTC 日期>/
              symbol=<标准化代码>.parquet
  features/
    <特征或因子数据集>/
  cache/
    <可删除缓存、注册表和临时状态>/
  derived/
    datasets/
      <dataset_slug>/
        _MANIFEST.json
        ohlcv/
          date=<UTC 日期>/
            *.parquet
    _staging/
      <unpublished dataset_slug>/
```

- `raw`：保留提供方原生字段、真实来源和抓取口径，不静默补造字段。
- `normalized`：只保存通过身份、schema、时间、来源和质量审计的标准数据。当前 Binance 全市场可信底座是 accepted normalized `15m`，不是 normalized `1h`。
- `derived`：由 accepted 输入按冻结公式生成的版本化标准 OHLCV。每个 `dataset_id` 使用独立 slug 目录，不得写入会被旧 `normalized/**/*.parquet` glob 自动混读的路径。先写 `_staging/`，审计通过后在 `datasets/` 内原子发布；已发布目录不得覆盖，修正必须新 `vN`。
- `features`：只保存可追溯到已接受输入数据与冻结构建逻辑的特征或因子。
- `cache`：可重建，不构成研究证据，不得替代 raw/normalized/derived 数据，也不得成为其他家族的事实源。

raw 层可按 `source` 保存同一市场数据的多个原始版本。normalized 层必须先明确
选择或裁决来源，不能让相同业务键的多个提供方版本静默共存。`derived` 层必须记录
输入 `dataset_id`、输入 manifest hash、来源裁决版本和聚合公式版本。

## 3. 市场身份与业务键

标准 OHLCV 业务键为：

```text
exchange + market_type + timeframe + symbol + ts
```

字段含义：

- `exchange`：真实交易场所，例如 `binance`、`nasdaq`；不得填写 Polygon、
  Yahoo 等数据提供方。
- `market_type`：当前合法值为 `spot`、`perp`、`futures`、`equity`。
- `futures` 数据必须额外记录具体合约或连续合约身份、换月/调整口径、结算价或成交价
  口径及 session 语义。缺少这些 provenance 的连续合约只能停留在
  `raw_unaccepted`，不得进入 trusted normalized 或支持 promotion 结论。
- `symbol`：标准化证券或合约代码；同名资产依靠 exchange 与 market_type 隔离。
- `timeframe`：行内必填身份，也是分区身份；两者不一致必须拒绝写入。
- `source`：数据提供方或抓取渠道，例如 `binance_vision`、`polygon_api`、
  `yahoo_finance`。
- `ts`：K 线开盘时间，必须为带 UTC 时区的 timestamp。

任何数据集在支持研究结论前，都必须明确数据来源、交易场所、市场类型、symbol、
timeframe、UTC 范围和 schema。

## 4. 标准 OHLCV Schema

normalized 或可信 OHLCV 必填字段：

```text
ts
exchange
symbol
market_type
timeframe
open
high
low
close
volume
quote_volume
trade_count
vwap
is_closed
source
```

最低约束：

- `open/high/low/close/volume/quote_volume/vwap` 必须为有效数值；
- OHLC 必须满足合法价格区间，价格不得为非正值，成交量不得为负；
- `trade_count` 必须是非负计数；
- `is_closed` 必须是显式布尔值，是 closed-bar 可用性的唯一权威；
- 不得根据 `ts`、文件位置或当前时间猜测 `is_closed`；
- 必填字段不得有 critical null；
- `source` 不得为空、`unknown` 或无法核实。

缺字段、critical null、非法 OHLC、重复业务键、未知来源、不可靠闭合状态或
错误时区均是 data-quality blocker。

股票 intraday normalized 数据还必须保留可机审的 session/closure provenance：
`session`、`session_type`、`session_calendar`、`session_policy`、
`session_open`、`session_close`、`bar_close_ts`、`session_provenance` 与
`closure_provenance`。其中 `is_closed` 可由交易所日历中的 bar 结束时间与固定
`audit_as_of` 判定，但必须记录日历、日历依赖版本、公式与审计时点；仅凭 `ts`
或脚本运行时“看起来已过去”不能生成可信闭合状态。

## 5. Raw 数据与接受状态

提供方原生 raw 快照可以暂时缺少标准字段，但必须：

- 保留全部原生字段，不把代理值伪装成原始值；
- 补齐可确认的市场身份和来源字段；
- 记录 source dataset identity、调整口径、session 范围等 provenance；
- 明确标记为 `raw_unaccepted` 或等价的不可信状态；
- 不进入 trusted loader，不写入 normalized，不支持注册指标、promotion 或
  live-ready 结论。

未接受或部分审计数据只可用于显式标记的 exploratory plumbing、schema discovery
或 diagnostic probing；其输出必须保持 `explore / untrusted`。

## 6. 连续性与市场日历

- `continuous_24_7` policy 保持加密货币既有行为：按对应 timeframe 的全天候
  时间网格检查缺 K 和异常间隔。
- 股票 trusted load 必须显式指定 session policy，不能回落到 24/7。NASDAQ
  regular-session 数据使用 `xnas_regular`，其权威网格由 `exchange-calendars`
  的 `XNAS` calendar 提供，包含 `America/New_York` 时区、DST、节假日和提前
  收市。
- `xnas_regular` 只接受交易所常规时段中的 bar open；盘前、盘后、周末及休市日
  行不属于连续网格，normalized 中出现这些行必须报 `out_of_session_rows`。
- session-aware 审计必须报告 expected bars、session 数、缺 K、session 外行、
  closure mismatch 与固定 `closure_as_of`；不得把休市时段误报为缺 K。
- 日 K 必须明确 session 与 timestamp 语义，不能仅凭相邻自然日推断缺失。
- 期货连续合约必须按其交易所日历检查；不得把通用工作日当成交易所日历，也不得
  在缺少逐合约映射时声称已核验 roll return、换月成本或价格调整方法。
- 缺口或可疑行应优先通过交易所 API、官方数据、Binance Vision 或保留的 raw
  证据核验；无法核验时记录 blocker，不得继续参数搜索。

## 7. Raw/Normalized 对齐门禁

数据进入可信状态前至少检查：

- UTC timestamp 与 timeframe 网格；
- 业务键唯一性和重复键组数；
- 缺 K、异常间隔和 stale 数据；
- critical null、字段类型、OHLC 合法性；
- `is_closed` 可靠性；
- raw 与 normalized 的 OHLCV、`quote_volume`、`trade_count`、`vwap` 对齐；
- 数据文件位于标准数据湖，而非仅存在于 cache、scratch 或临时目录；
- 来源在真实来源白名单内，且不存在测试、scenario、proxy 等伪数据标记。

任何失败都必须 fail closed。不得因为全周期回测漂亮而绕过数据质量 blocker。

## 8. 派生字段

派生或合成字段只能显式 opt-in，不能作为缺失原始字段的隐式替代。

当前 OHLCV 数据层仅允许调用方通过 `OHLCVDerivationPolicy` 明确申请：

- `quote_volume = close × volume`；
- `vwap = quote_volume ÷ volume`。

每次派生必须持久化：

- 公式与公式版本；
- 源字段；
- source dataset identity；
- 生成时间；
- null/fill policy；
- 代码或 artifact hash；
- 审计原因。

输出必须带 `derivation_provenance` 与 `quality_flags`。`trade_count` 和
`is_closed` 没有通用代理派生模式；不得填 `trade_count = 0` 或猜测
`is_closed = true`。提供方原生非标准字段可以在来源固定且逐行无损时映射，例如
Polygon `transactions -> trade_count`，但必须保留原字段与映射 provenance。
缺少原生计数的 Yahoo 数据不能使用该映射，也不能放宽 schema。raw 层禁止写入
代理字段。

## 9. 写入、分区与重复处理

- 单次写入只能包含一个 UTC `date` 分区；跨日数据必须按 UTC 日期拆分。
- exchange、market_type、symbol、timeframe、source 的行内值必须与写入分区一致。
- 写入必须使用原子替换，失败时不得留下半成品。
- 同一输入重复执行应可检测或保持幂等，不得静默叠加重复业务键。
- 跨刷新读取遇到重复键默认报错。
- 确需保留最新记录时，调用方必须显式选择 `DuplicatePolicy.KEEP_LAST`，并保留
  duplicate rows、duplicate groups 和 dropped rows 统计。
- 多来源 raw 数据进入 normalized 前必须完成来源裁决，不能靠 `KEEP_LAST`
  随机选择提供方。

## 10. 消费规则

新的治理过研究必须通过 `dataset_id` 入口读取：`strategy_lab.data.catalog.load_trusted_dataset()`。
它解析注册表中的物理根、执行来源裁决、检查声明 status/scope 与覆盖，并**始终**做全量
SQL 质量审计。`TrustedLoad` 必须带非空 `audit`、`source_counts`、覆盖范围和验证身份；
未物化 pandas 不能让 `audit={}`。只做覆盖统计时使用 `inspect_dataset()` / `list_registered_datasets()`，
这两个接口明确 `trusted=False`，不得冒充 trusted。

固定截止时间使用闭合 K 语义：纳入条件是 `ts + timeframe <= cutoff`，不是仅仅 `ts < cutoff`，
也不得用运行时“现在”代替冻结截止。已发布 derived 必须验证 `_MANIFEST.json`（缺失、文件增删改、
身份冲突、质量未接受一律拒绝）。历史 v1 的 `cutoff_exclusive_utc` 可以为 null；调用方仍须传入
明确 cutoff，并阅读 `known_limits`。

找不到规范路径时必须直接失败，不得回退扫描整个数据根并把结果当 trusted。
普通读取、预览或 `load_dataset()` 不得静默升级为 trusted。

`DuckDBWarehouse.load_trusted_ohlcv()` 仍保留给旧研究。它在普通读取之上
检查 schema、UTC、闭合 K、连续性、timeframe 和真实来源，并把结构化结果写入
`DataFrame.attrs["ohlcv_audit"]`。crypto 未传 policy 时继续使用
`continuous_24_7`；equity 必须显式传入 session policy，NASDAQ regular 数据传
`xnas_regular`，必要时同时固定 `closure_as_of` 以便复现。该旧入口不得用于加载
`derived` 层；`layer="derived"` 必须报错并指向 catalog。

`load_dataset()` 只提供读取与过滤能力，不表示数据已获信任。读取 raw equity
或其他未接受数据时，不得把普通加载成功解释为质量通过。旧 API 在缺少精确分区
时仍可能回退扫描 dataset root；这是兼容行为，不能当作 trusted 全市场覆盖。

raw/normalized 对齐使用 `audit_raw_normalized_ohlcv()`。任何研究脚本若绕过可信
加载器，必须在对应报告中给出等价的数据质量审计和明确理由。

本仓库不提供一个隐式通吃所有市场的数据同步 CLI。数据抓取、补洞和一次性迁移
脚本放在对应 `research/.../scripts/`，并记录来源、覆盖范围与质量校验。

## 11. 研究证据与修复记录

- 数据问题一经发现，应立即停止依赖同一错误假设的参数优化。
- 若数据问题削弱或改变既有结论，必须在相关 diagnostics、core ledger 或
  decision log 记录影响与修复状态。
- Markdown 报告引用的迁移清单、审计 JSON/CSV 等必须保存在对应
  `research/.../artifacts/`，不得只留在 scratch。
- 未解决 blocker 必须在报告中明确写出，不得用散文将其包装为已接受数据。

## 12. 实现入口

本规范的主要代码实现位于：

- [`models.py`](../src/strategy_lab/data/models.py)：市场类型与数据集 schema；
- [`lake.py`](../src/strategy_lab/data/lake.py)：分层与分区路径，含 `derived/`；
- [`store.py`](../src/strategy_lab/data/store.py)：身份校验、按日和原子写入；
- [`sessions.py`](../src/strategy_lab/data/sessions.py)：session policy 与 XNAS
  regular-session 权威 bar 网格；
- [`quality.py`](../src/strategy_lab/data/quality.py)：schema、重复、连续性与对齐审计；
- [`warehouse.py`](../src/strategy_lab/data/warehouse.py)：过滤读取与旧 trusted loader；
- [`authenticity.py`](../src/strategy_lab/data/authenticity.py)：真实来源审计，含
  `composite:` 混合来源；
- [`catalog.py`](../src/strategy_lab/data/catalog.py)：dataset_id 注册表、scope gate、
  trusted load；
- [`manifest.py`](../src/strategy_lab/data/manifest.py)：dataset manifest 与
  `.cache-meta.json`；
- [`resample.py`](../src/strategy_lab/data/resample.py)：accepted 15m 完整桶聚合。

实现与本规范冲突时，必须先修正规范或实现并补测试，不得在其他文档建立第二套约定。

## 13. 数据集身份、scope 与 fail-closed

每个可被研究结论引用的 OHLCV 或家族面板必须有稳定 `dataset_id`，并显式声明：

- layer：`raw` / `normalized` / `derived` / `cache`；
- status：`TRUSTED_BASE` / `TRUSTED_DERIVED` / `PARTIAL_SCOPE` /
  `PARTIAL_SCOPE_LEGACY` / `FAMILY_CACHE` / `UNACCEPTED` / `DEPRECATED`；
- declared scope：`FULL_MARKET` / `PARTIAL` / `SINGLE_SYMBOL` /
  `FAMILY_PANEL` / `EXPLICIT_DIAGNOSTIC`；
- 物理根路径、来源裁决规则、cutoff、是否可重建。

请求 `FULL_MARKET` 时，数据集必须同时满足：

1. status 为 `TRUSTED_BASE` 或 `TRUSTED_DERIVED`；
2. 声明 scope 为 `FULL_MARKET`；
3. 覆盖门禁同时检查日历跨度、symbol-day、长期历史 symbol 数和短快照占比，
   不能只看 distinct symbol。覆盖门禁检查的是**已发布数据集的全量覆盖**，
   不是本次 `start/end` 查询窗口。FULL_MARKET 可以带固定时间切片；切片上的
   SQL 质量审计针对选中行，但短窗口不能绕过整库覆盖门槛。

`PARTIAL_SCOPE_LEGACY`、`UNACCEPTED`、`DEPRECATED` 以及 coverage 不足的数据
在 `FULL_MARKET` 请求下必须直接报错。单币或明确标记的 partial diagnostic 可以
用 `SINGLE_SYMBOL` / `PARTIAL` / `EXPLICIT_DIAGNOSTIC` 显式读取。家族面板不是
标准 OHLCV，不能走 trusted OHLCV loader。

当前 Binance 登记：

- `binance.perp.ohlcv.15m.normalized.v1`：`TRUSTED_BASE` / `FULL_MARKET`；
- `binance.perp.ohlcv.1h.normalized.legacy`：`PARTIAL_SCOPE_LEGACY` / `PARTIAL`，
  不得冒充全市场；
- `binance.perp.ohlcv.{1h,4h,1d}.from_15m.v1`：`TRUSTED_DERIVED`；
- `binance.perp.ohlcv.1d.cache.from_15m` 与 `binance.perp.panel.1d.ma7_rc.p0/p3`：
  `FAMILY_CACHE`。

## 14. 标准衍生 OHLCV

Binance 1h/4h/1d 标准衍生数据只能由 accepted normalized 15m 生成，公式版本
`ohlcv_resample_from_15m_v1`，来源裁决 `binance_perp_15m_priority_union_v1`
（`binance_vision_kline_monthly` 优先于 `binance_futures_kline_api`；未列入来源
被排除，不进入 trusted union）。

聚合规则：

- primary phase 统一为 UTC `00:00`；
- 1h / 4h / 1d 分别需要 4 / 16 / 96 根连续、闭合、合法 15m，且首尾时间戳与桶对齐；
- 不补 K、不插值、不向前填充；组件不足的输出 bar 直接排除并计入审计；
- `open` 取第一根，`high`/`low` 取极值，`close` 取最后一根；
- `volume` / `quote_volume` / `trade_count` 求和；
- `vwap = sum(quote_volume) / sum(volume)`；零成交量时 `vwap` 等于输出 `close`；
- `is_closed` 仅在全部组件闭合且组件数、间隔完全正确时为 true；
- `ts` 为 UTC 输出 bar 开盘时间。

来源语义：

- 单一来源组成的 bar 继承该 source；
- 混合来源必须写成 `composite:<src1>+<src2>`（小写、排序、`+` 连接），禁止伪装成
  单一 Vision/API 来源；
- 每个输出数据集必须记录 upstream source 集合、priority union 版本、输入 manifest
  hash、聚合公式版本、要求组件数和 null policy。

衍生数据已经在构建时完成来源裁决。catalog 读取 derived 数据集时必须 passthrough
已写出的 `source`（含 `composite:`），不得再次按 15m 白名单过滤而丢掉混合来源 bar。

## 15. Cache manifest

`data/cache/` 下被研究引用的缓存必须带 sidecar `.cache-meta.json`，至少包含：
cache identity/version、输入 `dataset_id`、输入 manifest SHA256、builder 文件和
SHA256、config/parameter SHA256、generated_at、cutoff、rows、distinct keys、
symbols、start/end、duplicate/overlap 裁决、completeness rules、null/fill policy、
rebuild command、quality status。

不能确认的 lineage 字段必须标记 `LINEAGE_INCOMPLETE`，不得猜测。sidecar 与 parquet 库存指纹不一致，或 quality 为 `STALE` / `MISMATCH` /
`REJECTED`，或 `LINEAGE_INCOMPLETE` 出现在输入/builder 哈希或 quality_status 上时，
新的 trusted 消费必须拒绝——即使调用方没有传入 expected hash。历史复现可显式
`allow_incomplete_lineage=True`。补充 sidecar 不得改写原 parquet。

家族面板（含指标、标签、未来路径字段）不是标准 OHLCV。长期目标是从 canonical
derived 1d 重建这些面板，而不是让其他家族直接依赖它们。

## 16. Binance OHLCV：查询 → 选版本 → 验证 → 读取 → 固定输入

机器可读目录由 `strategy_lab.data.catalog.list_registered_datasets()` 提供。
下面命令均已实现；输出以现场运行为准，不得把覆盖预览写成 trusted。

查询可用数据：

```bash
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py list
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py inspect \
  --dataset-id binance.perp.ohlcv.4h.from_15m.v1 --scope FULL_MARKET
```

验证并读取（单币 4h；固定窗口全市场 4h 不物化 pandas；canonical 1d）：

```bash
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py load \
  --dataset-id binance.perp.ohlcv.4h.from_15m.v1 --scope SINGLE_SYMBOL \
  --symbol BTC/USDT:USDT --end 2026-08-24T08:00:00Z

python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py load-research \
  --dataset-id binance.perp.ohlcv.4h.from_15m.v1 --scope SINGLE_SYMBOL \
  --symbol BTC/USDT:USDT --end 2026-08-24T08:00:00Z --gap-policy reject

python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py load \
  --dataset-id binance.perp.ohlcv.4h.from_15m.v1 --scope FULL_MARKET \
  --start 2026-08-01T00:00:00Z --end 2026-08-24T08:00:00Z \
  --max-materialize-rows 0

python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py load-1d \
  --scope SINGLE_SYMBOL --symbol BTC/USDT:USDT --end 2026-08-25T00:00:00Z
```

一次性捕获上述查询/读取/拒绝示例：

```bash
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py bundle
```

研究输入应记录：`dataset_id`、`parquet_inventory_fingerprint` 或 published
`manifest_sha256`、显式闭合截止（`end` / `cutoff_exclusive_utc`）、`gap_policy`，
以及 `row_quality=PASS`。新研究用 `load_trusted_research_dataset(..., gap_policy="reject"|"contiguous_segments")`，
必须给截止；不得默认 `report_only`。整库治理扫描必须声明 `purpose="governance_audit"`。
请求窗口超出最后一根已闭合 K 的收盘时间时默认拒绝。

当前已接受派生版本是 `binance.perp.ohlcv.{1h,4h,1d}.from_15m.v1`；底座是
`binance.perp.ohlcv.15m.normalized.v1`。v1 的 `cutoff_exclusive_utc` 为 null（历史事实，
不得改写）；消费时必须另给显式截止。数据实际结束于最后一根完整闭合 K，不是“今天”。
输出 bar 必须满足 `bar_open + timeframe <= cutoff`。

新版本必须先构建、审计、发布，再写入 `derived/datasets/_DATASET_REGISTRY.json`；
禁止扫描整个 data 根并自动信任所有 manifest。`--check` / `--dry-run` 不得与
`--write-15m-snapshot` 或 `--register` 同时使用，也不得改写发布数据。

幂等核对（只读，不写快照、不覆盖已发布 v1）：

```bash
python research/platform/data-lake-governance/scripts/build_binance_derived_ohlcv_from_15m.py \
  --check --timeframe all
```

临时湖上的发布→登记→查询→读取示例：

```bash
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py publish-register-load
```

预期拒绝（必须失败）：

```bash
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py reject --case legacy-1h-full-market
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py reject --case cache-as-ohlcv
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py reject --case missing-dataset
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py reject --case bad-fingerprint
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py reject --case missing-manifest
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py reject --case over-range-window
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py reject --case missing-lineage
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py reject --case bad-manifest
```

