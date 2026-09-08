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
- `normalized`：只保存通过身份、schema、时间、来源和质量审计的标准数据。Binance 历史底座为 accepted normalized `15m`；当前新研究的 V3 组合在 `derived`，见第 19 节。normalized `1h` 不是全市场输入。
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
- [`settings.py`](../src/strategy_lab/data/settings.py)：仓库根路径与共享/本地存储配置；
- [`fs.py`](../src/strategy_lab/data/fs.py)：文件锁与原子写入；
- [`lake.py`](../src/strategy_lab/data/lake.py)：分层与分区路径，含 `derived/`；
- [`store.py`](../src/strategy_lab/data/store.py)：身份校验、按日和原子写入；
- [`normalize.py`](../src/strategy_lab/data/normalize.py)：时区与列规范化；
- [`sessions.py`](../src/strategy_lab/data/sessions.py)：session policy 与 XNAS
  regular-session 权威 bar 网格；
- [`quality.py`](../src/strategy_lab/data/quality.py)：schema、重复、连续性与对齐审计；
- [`sql_audit.py`](../src/strategy_lab/data/sql_audit.py)：DuckDB SQL 质量审计，输出
  `load_audit.quality_status` 为 `PASS` / `FAIL`；
- [`windows.py`](../src/strategy_lab/data/windows.py)：cutoff、闭合 bar 窗口与
  `gap_policy`；
- [`warehouse.py`](../src/strategy_lab/data/warehouse.py)：过滤读取；其中
  `load_trusted_ohlcv` 是**兼容层，新研究禁用**；
- [`authenticity.py`](../src/strategy_lab/data/authenticity.py)：真实来源审计，含
  `composite:` 混合来源；
- [`catalog.py`](../src/strategy_lab/data/catalog.py)：dataset_id 注册表、scope gate、
  trusted load；
- [`manifest.py`](../src/strategy_lab/data/manifest.py)：dataset manifest 与
  `.cache-meta.json`；
- [`resample.py`](../src/strategy_lab/data/resample.py)：accepted 15m 完整桶聚合。

新研究读取标准 OHLCV 的必经步骤：

Binance 新实验先走第 19 节组合启动 API；该 API 内部落实以下 catalog 门禁。下列底层接口单独通过不替代组合与研究窗口检查。

1. `catalog.load_trusted_research_dataset(..., end=..., gap_policy="reject"|"contiguous_segments")`（强制 `purpose="research"` 与严格指纹）；
2. `catalog.require_passing_trusted(loaded)`，确认 `load_audit.quality_status=PASS` 且存在 `verified_parquet_files`；
3. 只用返回的 verified 文件或 `read_verified_ohlcv`，禁止自行 `read_parquet` 湖路径。

`warehouse.load_trusted_ohlcv` 仅供尚未迁移的历史脚本。新家族、新阶段、新实验不得再调用。

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
- `binance.perp.ohlcv.15m.refreshed.v2`：`TRUSTED_DERIVED` / `FULL_MARKET`；保留旧 15m 业务键并加入官方 API 缺失键的同周期快照，非重采样；闭合截止 `2026-09-05T15:45:00Z`，历史仍有内部缺口；
- `binance.perp.ohlcv.15m.history.v3`：`TRUSTED_DERIVED` / `FULL_MARKET`；在 V2 上以官方 API、月/日度 CHECKSUM 补洞，截止不变；残余上线/重开边界保留，研究只能显式按段消费，不能声称完整 PIT；
- `binance.perp.ohlcv.1h.normalized.legacy`：`PARTIAL_SCOPE_LEGACY` / `PARTIAL`，
  不得冒充全市场；
- `binance.perp.ohlcv.{1h,4h,1d}.from_15m.v1`：`TRUSTED_DERIVED`；
- `binance.perp.ohlcv.{1h,4h,1d}.from_15m.v2`：`TRUSTED_DERIVED` / `FULL_MARKET`，唯一输入为价格 V3，当前新研究组合见第 19 节；
- `binance.perp.ohlcv.1d.cache.from_15m` 与 `binance.perp.panel.1d.ma7_rc.p0/p3`：
  `FAMILY_CACHE`。

### 质量词表对照表

这四套词**不是**同一个字段，禁止互相替换或把 `PASS` 写成数据集 `status`。

| 词表 | 字段 / 载体 | 含义 | 允许值 |
| --- | --- | --- | --- |
| `registered_status` | `DatasetStatus`（注册表 / catalog record `status`） | 数据集身份与 scope 资格 | `TRUSTED_BASE` / `TRUSTED_DERIVED` / `PARTIAL_SCOPE` / `PARTIAL_SCOPE_LEGACY` / `FAMILY_CACHE` / `UNACCEPTED` / `DEPRECATED` |
| `publish_quality` | derived `_MANIFEST.json` 的 `quality_status` | 发布时自证的质量标签 | **新写规范值唯一** `TRUSTED_DERIVED`。读取仍兼容 `ACCEPTED` / `PASS` / `TRUSTED`（见 `ACCEPTED_DERIVED_QUALITY`） |
| `load_audit` | `sql_audit` / `TrustedLoad.audit["quality_status"]` | 本次读取窗口的 SQL 行质量 | `PASS` / `FAIL`。`require_passing_trusted` 要求 `PASS` |
| legacy attrs 审计 | `DataFrame.attrs["ohlcv_audit"]`（`warehouse.load_trusted_ohlcv`） | 兼容层 pandas 帧内审计，不是 catalog 审计 | 由 `quality.audit_ohlcv_frame` 的 dict 构成；不得当作 `load_audit` |

`FULL_MARKET` 读取必须同时满足：注册 `status` 为 `TRUSTED_BASE` 或 `TRUSTED_DERIVED`，且本次 `load_audit` 为 `PASS`。`publish_quality=TRUSTED_DERIVED` 不能替代 SQL `PASS`。

## 14. 标准衍生 OHLCV

Binance 1h/4h/1d 标准衍生数据只能由已接受的标准 15m 数据生成，输入可以是
accepted normalized V1 或显式锁定的已发布 15m V3；不得混合输入版本。v1 公式版本
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

`data/cache/binance_perp_1d_from_15m`（`binance.perp.ohlcv.1d.cache.from_15m`）
的 sidecar 中 `input_manifest_sha256` 与 `config_parameter_sha256` 现为
`LINEAGE_INCOMPLETE`。该缓存只允许 `scripts/governance/frozen_research_scripts.txt`
上的冻结脚本读取。新实验按第 19 节组合入口选择 `binance.perp.ohlcv.1d.from_15m.v2`，不从缓存或旧 canonical 函数隐式选版本。

未能无损补齐这两项哈希：缓存由 2026-08-18 的 MCSM-LS3 构建标记生成，早于
derived `_MANIFEST.json` 与参数哈希约定；`_build_complete.json` 只有月份列表与
文字 provenance，没有当时 15m manifest SHA 或 config digest。用今天的 15m
manifest 或当前 builder 文件哈希回填会伪造 lineage，因此保持 `LINEAGE_INCOMPLETE`。

## 16. Binance OHLCV：查询 → 选版本 → 验证 → 读取 → 固定输入

机器可读目录由 `strategy_lab.data.catalog.list_registered_datasets()` 提供。
下面命令均已实现；输出以现场运行为准，不得把覆盖预览写成 trusted。

本节 v1 命令为历史冻结版本与底层 API 示例，不是当前新研究推荐版本。当前组合和必需的研究启动检查统一见第 19 节；不能仅因旧函数含 canonical 字样推断已升级。

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

历史已接受派生版本 `binance.perp.ohlcv.{1h,4h,1d}.from_15m.v1` 的底座是
`binance.perp.ohlcv.15m.normalized.v1`。v1 的 `cutoff_exclusive_utc` 为 null（历史事实，
不得改写）；消费时必须另给显式截止。数据实际结束于最后一根完整闭合 K，不是“今天”。
输出 bar 必须满足 `bar_open + timeframe <= cutoff`。

15m 刷新版本 `binance.perp.ohlcv.15m.refreshed.v2` 已独立发布，截止北京时间
2026-09-05 23:45；它不改变上述 1h/4h/1d v1 的输入和截止。其 874 个合约包含
历史合约及传统资产，不能当作当前纯加密币集合。行质量 PASS 但历史治理部分完成，
具体执行偏差及缺口见 [V2 验收](../research/platform/data-lake-governance/diagnostics/binance-15m-refresh-v2-acceptance-2026-09-06.md)。
读取时显式指定该 dataset-id、闭合截止及研究缺口策略，不自动切换旧消费者。

后续 15m 全历史观测网格治理发布为 `binance.perp.ohlcv.15m.history.v3`，保留 V2
全部已有业务行并补回可得记录。残余 12 段上线/重开边界仍由通用 24/7 SQL 报告为空位，
不能放宽 `reject`；`contiguous_segments` 消费须按 [V3 连续段清单与验收](../research/platform/data-lake-governance/diagnostics/binance-15m-history-v3-closeout-2026-09-06.md)
分段构建特征和标签。原生零成交记录保留，但不是可交易性或历史成分证明。

```bash
python research/platform/data-lake-governance/scripts/example_binance_ohlcv_usage.py load-research \
  --dataset-id binance.perp.ohlcv.15m.history.v3 --scope FULL_MARKET \
  --end 2026-09-05T15:45:00Z --gap-policy contiguous_segments --max-materialize-rows 0
```

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

## 17. V3 配套统一研究输入

价格配套的历史发布范围见 [V3 研究输入治理契约](../research/platform/data-lake-governance/specs/binance-v3-research-inputs-v1-2026-09-07.md)。
原 [v1 组合清单](../research/platform/data-lake-governance/artifacts/binance_v3_research_inputs_v1_20260907/research_input_bundle.json) 绑定的是旧费率 v1，保留冻结；当前完整组合已升级到第 19 节 v2，不覆盖原文件。

新增 `binance.perp.ohlcv.{1h,4h,1d}.from_15m.v2` 的唯一输入为
`binance.perp.ohlcv.15m.history.v3`。数值聚合公式及 UTC 相位不变，来源使用
`v3_already_adjudicated_passthrough_v1`：V3 已完成来源裁决，保留日度修复来源，
不得再次套用旧 V1 仅两来源的过滤规则。新版本不覆盖旧高周期 v1。

冻结总截止仍为 `2026-09-05T15:45:00Z`。请求完整闭合高周期时，可用最后收盘分别为
1h `2026-09-05T15:00:00Z`、4h `2026-09-05T12:00:00Z`、1d `2026-09-05T00:00:00Z`。
旧 `load_canonical_binance_perp_1d()` 仍固定 v1，避免破坏冻结复现；新实验必须显式
按第 19 节通过组合启动入口选择上述 v2 ID。[research_inputs.py](../src/strategy_lab/data/research_inputs.py)
中的 `load_v3_research_ohlcv()` 保留为冻结底层接口，不是完整的新组合启动检查；不得因函数含 canonical 字样推断其已自动升级。

该入口先执行严格可信读取，然后拒绝乱序/重复，按缺口、零成交、显式身份边界重置
`research_segment_id`。rolling、收益和未来标签必须按此字段分组，使用
`complete_window_mask(backward=..., forward=...)` 拒绝不完整窗口。没有自动向前填充。

标的有效性分为 `observed_valid` 和 `identity_verified`。默认 `require_verified`
需要调用方提供带来源的历史身份有效期；没有证据不自动通过。显式
`observed_diagnostic` 只用于观测样本诊断，不证明历史 PIT 或可交易性；当前
exchangeInfo 分类和当前 TRADING 名单都不能替代历史身份。

以下是底层分段接口示例，解释历史调用语义（不宣称 PIT/可交易）；新消费者的完整写法见第 19 节：

```python
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.settings import default_settings
from strategy_lab.data.research_inputs import load_v3_research_ohlcv, complete_window_mask

bars = load_v3_research_ohlcv(
    layout=DataLakeLayout.from_settings(default_settings()),
    timeframe="1d", symbol="BTC/USDT:USDT",
    start="2026-08-01T00:00:00Z", end="2026-09-05T00:00:00Z",
    identity_policy="observed_diagnostic",
)
valid = complete_window_mask(bars, backward=7, forward=0)
ma7 = bars.groupby("research_segment_id").close.transform(
    lambda prices: prices.rolling(7, min_periods=7).mean()
).where(valid)
```

全市场或大窗口仍通过 catalog 的显式 dataset ID、截止和严格验证文件分批读取，
每币调用 `segment_research_bars()`；不要先删掉零成交行再假装剩余行连续。

资金费率独立于 OHLCV；配套快照即使行质量通过，也不得借用价格的 PASS 宣称完整。
`load_verified_funding_snapshot()` 验证内容后仍不承诺覆盖；净收益须额外调用
`require_funding_window()`，提供独立冻结的历史期望结算时间和证据。缺失、额外事件、
同小时歧义均拒绝；毫秒时间不取整，缺失费率不填 0。期望时间不得从待检数据本身
反推，当前 fundingInfo 不作为全历史结算日历。

本轮最初发布的资金快照 ID 为 `binance.perp.funding.v3_inputs.v1`，状态 `PARTIAL_COVERAGE`。
其 910 个历史库存代码仅有 864 个与 V3 的 874 个价格代码相交；不能按库存数量推断
资金费率完整。范围外的旧命名/其他计价币代码只保留审计，不自动改写或纳入 V3 净收益。
详见 [价格与费率范围审计](../research/platform/data-lake-governance/artifacts/binance_v3_research_inputs_v1_20260907/funding/price_scope_audit.json)。
该 v1 发布时有 634 个 API 查询未完成，后续增量不得追加入该冻结快照。续治理已独立发布下节 v2，旧 bundle 和旧读取函数保持不变。

## 18. 资金费率 v2：事件治理与结算覆盖分离

新快照为 `binance.perp.funding.v3_inputs.v2`，见[治理契约](../research/platform/data-lake-governance/specs/binance-funding-v3-inputs-v2-2026-09-07.md)、[验收与限制](../research/platform/data-lake-governance/diagnostics/binance-funding-v3-inputs-v2-2026-09-07.md)。这是独立资金事件数据，不通过 OHLCV catalog 接口读取，也不自动改变旧研究的数据依赖。

本版只包含 V3 的 874 个观测价格代码，共 2,654,430 个事件；范围、截止固定在 manifest。资金事件不铺成 15m 行，缺失不填 0。按 UTC 月压缩保存事件，历史覆盖证据另外保存；业务身份包含 `symbol + 原生毫秒 ts + rate_type`，同毫秒的 `Regular` 与 `Special` 不得合并。

时间相近/费率相等不足以去重。只有完整官方小时查询或校验月档提供唯一对应，且费率一致、偏移不超过 2 秒时，才保留原生事件并记录旧键映射。特殊股息结算保留原始类型；本轮事件歧义清零不等于任意持仓窗口费用完整。

底层独立入口为 [funding_v2.py](../src/strategy_lab/data/funding_v2.py)，以下解释其冻结语义；新研究通过第 19 节组合门禁统一绑定该 manifest 和身份证据，不只调用此函数：

```python
from pathlib import Path
from strategy_lab.data.funding_v2 import load_funding_v2, require_funding_v2_window

funding = load_funding_v2(
    Path("/Users/ZK/OpenCode/quant-strategy-lab/data/derived/datasets/binance_perp_funding_v3_inputs_v2"),
    expected_manifest_sha256="398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076",
)

def funding_for_verified_identity(symbol, start, end, identity_evidence):
    return require_funding_v2_window(
        funding, symbol=symbol, start=start, end=end,
        identity_evidence=identity_evidence,
    )
```

`start`、`end` 必须带时区，结算窗口为 `(start, end]`。调用方必须自行核实 `identity_evidence` 所指的历史身份来源及有效期：接口检查非空并保留文本，不自动鉴定证据真实性，不能用任意字符串冒充 PIT。

净收益门禁要求整个窗口处于同一已证明连续结算片段，再逐条比较应有/实有事件 ID、原生时间、类型和费率。缺事件、多事件、歧义、值变化或跨边界都拒绝。只有在已证明片段内且没有应结算事件的子窗口，才允许合法空集；未知覆盖不能零填充。

历史频率仅采用已留存原生月档的 `funding_interval_hours`，相邻事件须与声明间隔一致；频率切换、缺证据、首尾和多事件小时断开。不能从观察到的时间差反推全历史日历，不能用当前 `fundingInfo` 外推历史，也不能用完整 API 返回替代日历证明。

本轮只有 585 个标的的 639 个部分历史片段具有该证据，**不是 585 个标的全历史通过**；API-only 的 2026 年 9 月尾部和股票特殊结算尚不能直接通过这一净收益门禁。当前 `PARTIAL_COVERAGE` 保留。剩余 71 个未检索范围虽均为 V3 零成交价格区间，也不构成费率为零或历史已退市的证明。旧消费者迁移和完整 PIT 均未完成。

## 19. Agent 统一入口、固定组合与研究启动前校验

**当前新研究组合：`binance.v3.research_inputs.v2`**。选择入口是 [current-research-inputs.json](../research/platform/data-lake-governance/specs/current-research-inputs.json)，不可变发布物是 [binance-v3-research-input-bundle-v2.json](../research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2.json)，发布契约见 [组合 v2 契约](../research/platform/data-lake-governance/specs/binance-v3-research-input-bundle-v2-2026-09-07.md)。指针只帮助初次选择，研究配置必须冻结清单路径、ID 和 SHA256；后续复现读取自己的 pin，不跟随指针变化。

| 角色 | 固定输入 | 可用最后完整收盘 / 事件（UTC） |
| --- | --- | --- |
| 15m 价格 | `binance.perp.ohlcv.15m.history.v3` | 2026-09-05 15:45 收盘 |
| 1h 价格 | `binance.perp.ohlcv.1h.from_15m.v2` | 2026-09-05 15:00 收盘 |
| 4h 价格 | `binance.perp.ohlcv.4h.from_15m.v2` | 2026-09-05 12:00 收盘 |
| 1d 价格 | `binance.perp.ohlcv.1d.from_15m.v2` | 2026-09-05 00:00 收盘 |
| 资金费率 | `binance.perp.funding.v3_inputs.v2` | 2026-09-05 15:00 事件；日历仅部分历史 |

发布日期 2026-09-07 不等于数据更新到当天。五个组件均固定 manifest 和 Parquet 全内容指纹；高周期父输入必须与组合内价格 V3 一致。完整身份/PIT、全历史结算日历与可交易性仍未证明，不因清单发布而升级状态。

### 19.1 先选择检查层级，不能把文件检查当研究就绪

在仓库根使用已安装本仓库依赖的 Python：

```bash
python scripts/governance/check_research_startup.py --contract-only
python scripts/governance/check_research_startup.py --bundle-only
python scripts/governance/check_research_startup.py \
  --request research/platform/data-lake-governance/specs/research-startup-price-example-v2.json
```

- `--contract-only`：检查指针、组合结构和冻结读取器；不读取数据湖。状态 `CONTRACT_ONLY_NOT_DATA_READY`，已接入 [preflight.py](../scripts/governance/preflight.py) 与现有 CI。
- `--bundle-only`：五组 manifest 与 Parquet 全内容哈希一致才返回 `BUNDLE_INTEGRITY_PASS_NOT_RESEARCH_READY`；未检查某研究窗口。
- `--request`：执行组合检查、catalog STRICT_CONTENT 行质量和精确范围的有效窗口检查；任一失败返回非零退出码。价格模式成功为 `PRICE_DIAGNOSTIC_INPUTS_VERIFIED`；净收益输入窗口通过额外门禁才为 `NET_INPUT_WINDOW_VERIFIED`。两者都不代表策略 PASS、PIT 完整或 live-ready。

正式运行须加 `--output <本家族新的 artifacts 报告.json>` 留证；拒绝覆盖已有报告或写入数据湖。`--project-root` 与 `--data-root` 可显式指定代码和共享数据根；找不到文件会失败，不扫描其他任务、旧版或缓存。请求按标的分批读取，避免一次物化全历史全市场；仍需预留所请求价格帧与费率事件的内存。

### 19.2 固定本研究范围，再使用返回的数据

可复制的最小观测价格请求见 [research-startup-price-example-v2.json](../research/platform/data-lake-governance/specs/research-startup-price-example-v2.json)。将它复制到本家族 `specs/`，在看到研究结果前固定标的、周期、范围、缺口政策和回看/未来长度；不能用示例 BTC 窗口通过推断自己的全市场研究通过。

价格按 `[start,end)` 的开盘网格选择，且每根必须完整闭合；`start/end` 必须带时区并与周期对齐。请求范围须包含所需预热和标签尾部；`backward_bars` 含当前 bar，`forward_bars` 为之后的 bar 数。不自动补取范围外数据、不静默丢标的。`gap_policy=reject` 拒绝缺首尾/缺 K/零成交/无效值/身份边界；`contiguous_segments` 则在报告中列出缺失与无效行，只准按段使用 `research_window_valid=True` 的窗口。不得先删零成交行再拼成连续历史。

```python
from pathlib import Path
from strategy_lab.data.research_bundle import read_json, require_research_startup

root = Path("/Users/ZK/OpenCode/quant-strategy-lab")  # 换成明确的当前工作区
request = read_json(root / "research/platform/data-lake-governance/specs/research-startup-price-example-v2.json")
inputs = require_research_startup(request, project_root=root)
bars = inputs.prices["BTC/USDT:USDT"]
ma7 = bars.groupby("research_segment_id").close.transform(
    lambda p: p.rolling(7, min_periods=7).mean()
).where(bars.research_window_valid)
assert inputs.report["funding_window_verified"] is False  # 此模式只做价格诊断
```

实际研究必须消费 API 返回的帧和 mask；CLI 不自动启动策略，过去一次的成功报告也不是之后重读原始湖路径的许可证。新脚本调用 `require_research_startup` 会被既有消费者扫描发现，仍须登记对应 entrypoint/required call 并验证整个消费链；不得扩展历史 frozen 清单绕过登记，也不能把字符串扫描说成覆盖一切动态代码的强制沙箱。

### 19.3 净收益模式不能靠任意证据字符串开绿灯

`mode=price_diagnostic` 不核准历史身份。`asset_policy=crypto_only` 仅按清单观测分类排除非 COIN/UNKNOWN，不证明纯加密历史 PIT 池；需要混合传统资产样本必须显式选择 `observed_mixed_diagnostic`，且只准价格诊断。标的列表必须明确，不能用 `*` 或自动取今天活跃集合冒充历史股票池。

`mode=net_research` 当前只接受 `crypto_only`，额外要求请求中的 `identity_review={"path": "本仓库相对证据复核JSON路径", "sha256": "实际文件SHA256"}`。复核 JSON 须包含非空 `reviewed_by`、`review_status="ACCEPTED_FOR_IDENTITY_ONLY"`、`windows` 数组；每个请求标的恰有一段完整覆盖请求范围的 `symbol/start/end/evidence_path/evidence_sha256`。复核文件与每份来源文件必须实际存在、哈希相符；不得把测试材料、当前 exchangeInfo 或任意字符串登记为已复核历史证据。门禁验证文件与覆盖，不自动鉴定材料真实性，研究方必须负责独立复核。

价格有效性通过后，每个标的的整个 `(start,end]` 还须通过第 18 节历史费率日历门禁。缺费率、无日历、跨片段或事件歧义均中止，不回填 0，不从净收益模式降级成价格模式继续发布净值。这个启动版本采取保守的整请求窗口检查；跨越未证明费率范围的长历史研究会失败，即便部分持仓子窗口可能可验证。若要只研究子窗口，应先冻结独立请求，不按结果选择。

通过时返回的 `inputs.funding[symbol]` 为已验证结算事件，仍须按真实持仓时点、方向和名义金额结算；手续费、滑点、执行时序、跨价格缺口持仓、PIT 池及 OOS 必须另过研究契约。所有启动报告的 `strategy_approved`、`pit_universe_proven`、`tradability_proven` 均保持 false。

### 19.4 其他 Agent / 工作区的可见性边界

同一目录内的 Agent 可从 `AGENTS.md → research/README.md → 本节 → 当前指针 → 固定请求/API` 自主发现，不依赖聊天记忆。清单、指针、启动器和规格位于可版本管理路径，但只有实际提交/同步这些文件后，其他 checkout/worktree 才能获得本轮更新；本地 `data/` 和大部分 `artifacts/` 被 Git 忽略，不会随代码自动复制。共享数据根需显式配置并重新验指纹。本轮不自动提交、推送、迁移旧研究或分发数据。
