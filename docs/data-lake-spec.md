# Data Lake Specification

本文件是 `quant-research-lab` 数据湖结构、身份、schema、质量门禁、写入和消费规则的
唯一规范来源。根 README、Cursor 规则、研究入口和脚本说明只应引用本文件，不得
另行维护一份通用数据湖约定。研究报告仍须记录其实际数据来源、范围和审计结果。

## 1. 范围与所有权

本仓库只维护一个本地数据湖。加密货币、股票及后续其他市场共用
`data/raw`、`data/normalized`、`data/features` 三层，不得按资产、策略或提供方
建立 `data/external`、`data/stocks` 或策略私有数据根目录。

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
```

- `raw`：保留提供方原生字段、真实来源和抓取口径，不静默补造字段。
- `normalized`：只保存通过身份、schema、时间、来源和质量审计的标准数据。
- `features`：只保存可追溯到已接受输入数据与冻结构建逻辑的特征或因子。
- `cache`：可重建，不构成研究证据，不得替代 raw/normalized 数据。

raw 层可按 `source` 保存同一市场数据的多个原始版本。normalized 层必须先明确
选择或裁决来源，不能让相同业务键的多个提供方版本静默共存。

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

默认 `LAB_OHLCV_V1` 的 normalized 或可信 OHLCV 必填字段（既有 reader 和质量检查保持不变）：

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

### 4.1 显式选择的 OHLCV 核心研究契约

`TRUSTED_OHLCV_CORE_V1` 是新的、必须写入冻结研究合同的独立 profile。旧数据不会自动
迁移，也不能通过删除字段或修改 acceptance 标记进入新 profile。该 profile 只供离线研究，
不授予实盘、跨提供方替代或公开再分发权限。

| 层 | 要求 |
|---|---|
| 核心原生行情 | `ts/open/high/low/close/volume`；UTC 开盘时间、完整周期网格、合法 OHLC、非负有限成交量 |
| 身份与来源 | `exchange/market_type/timeframe/symbol/source`，提供方原生 market ID；官方字段定义、单位、未调整口径的原文快照 |
| 可选质量字段 | 原生 `trade_count/quote_volume/vwap/taker_volume`；存在就校验，缺失明确列出，不写 0、不估算 VWAP、不从价格反算成交额 |
| 策略字段 | Rule AST 与 ExecutionContract 推导的集合；与核心字段取并集。策略用到的可选字段立即变成必需字段 |
| 收盘证据 | 原生收盘标记，或经过审查的独立收盘证据。当前实现只接受下文的历史双次抓取协议，不伪造 `is_closed` |

trade count、quote volume、VWAP 有助于成交活动与单位校验，但不能证明请求完整、来源可信
或 K 线已结束；对只使用原生 OHLCV 的策略，它们不是普遍必要条件。省去这些可选列仍必须
独立通过身份、许可、coverage、schema、calendar、integrity、hashes、finality、provenance
九项检查。`FAIL` 为 `REJECTED`，存在 `UNKNOWN` 为 `DIAGNOSTIC_ONLY`，全部 `PASS` 才是
`TRUSTED`。不能只凭无缺口就放行。

历史收盘协议 `closed-grid-newer-bar-stable-recapture-v1` 要求：官方周期/当前 K 线语义、完整
UTC 网格、提供方响应时钟与本次抓取时间吻合、同市场同周期已出现更晚的当前桶、请求结束
时间不晚于该桶开盘，以及先后两轮完整历史抓取逐条相等。两轮原始 bytes、请求、页边界、
HTTP 元数据、官方说明和独立审核都固定摘要。这是“截至抓取时已结束且两轮稳定”的证据，
不是交易所永不修订的承诺；以后新快照必须重新审核。仅凭本机时间推算不合格。

分页使用预定、互不重叠的目标窗口；静默 cap 或窗口截断触发保留父响应的二分重抓，直到
完整或单根仍缺失而失败。接口包含/不包含边界的差异通过带证据的边缘观察排除处理；内部
重复、乱序、缺口不得靠去重、排序、补值掩盖。仅严格倒序的原生页允许显式反转。原始响应
留在 `data/raw/ohlcv/.../snapshot=.../`，通过离线重建审计后才写
`data/normalized/ohlcv/.../snapshot=.../`。每个 normalized snapshot 带 profile、manifest
和原始 capture 摘要；消费时重新构造全部观测，并逐字节比较 normalized 结果。

实现与回归检查分别见 [market_core.py](../src/strategy_lab/knowledge/market_core.py)、
[分页抓取](../research/platform/quantgraph-integration/scripts/fetch_market_paged.py) 和
[独立验收测试](../tests/test_market_core.py)。

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

- 以下按日 Parquet 写入规则继续适用于默认 profile。第 4.1 节核心 profile 使用不可变的
  全历史 snapshot 容器：仍位于标准 data/raw、data/normalized 的真实市场/类型/周期分区，
  以摘要化 dataset ID、逐行身份和完整日历审核代替按日文件目录；整个容器原子发布，目录
  已存在就拒绝覆盖。它不进入旧 Warehouse 的隐式发现路径。
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

研究消费应优先使用 `DuckDBWarehouse.load_trusted_ohlcv()`。它在普通读取之上
检查 schema、UTC、闭合 K、连续性、timeframe 和真实来源，并把结构化结果写入
`DataFrame.attrs["ohlcv_audit"]`。crypto 未传 policy 时继续使用
`continuous_24_7`；equity 必须显式传入 session policy，NASDAQ regular 数据传
`xnas_regular`，必要时同时固定 `closure_as_of` 以便复现。

`load_dataset()` 只提供读取与过滤能力，不表示数据已获信任。读取 raw equity
或其他未接受数据时，不得把普通加载成功解释为质量通过。

raw/normalized 对齐使用 `audit_raw_normalized_ohlcv()`。任何研究脚本若绕过可信
加载器，必须在对应报告中给出等价的数据质量审计和明确理由。

核心 profile 显式使用 `read_market_dataset()` → `read_core()`：旧 Warehouse 要求的
原生可选列与此 profile 不同，因此不混用 loader。每次消费重新验证所有原始页、许可、
时间、完整网格、收盘、逐字节归一化一致性及审核代码摘要，任何不一致拒绝消费。

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
- [`lake.py`](../src/strategy_lab/data/lake.py)：分层与分区路径；
- [`store.py`](../src/strategy_lab/data/store.py)：身份校验、按日和原子写入；
- [`sessions.py`](../src/strategy_lab/data/sessions.py)：session policy 与 XNAS
  regular-session 权威 bar 网格；
- [`quality.py`](../src/strategy_lab/data/quality.py)：schema、重复、连续性与对齐审计；
- [`warehouse.py`](../src/strategy_lab/data/warehouse.py)：过滤读取与 trusted loader；
- [`authenticity.py`](../src/strategy_lab/data/authenticity.py)：真实来源审计。

实现与本规范冲突时，必须先修正规范或实现并补测试，不得在其他文档建立第二套约定。
