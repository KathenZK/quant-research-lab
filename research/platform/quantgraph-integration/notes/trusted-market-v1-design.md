# 首条可信行情研究链：设计与来源审查

本轮只实现 Knowledge Graph → Research Lab 的离线研究闭环。先完成 BTC/EUR 日线
PRICE_SMA 的固定 SMA50，网格为 40/50/60；不根据收益选择数据源或参数。旧 V4 合同、原始
记录和未通过验收的数据保持原样。本轮新合同保留完整请求区间、IS/OOS、手续费和滑点。

## 提供方评估

2026-09-28 重新读取官方条款与接口说明。下表是本任务使用场景下的结论，不是对各提供方
所有产品的法律判断；公开 API 可以访问不等于可用于商业研究。

| 提供方 | 权利与 API 能力核查 | 本轮处理 |
|---|---|---|
| Bit2Me | [市场数据条款](https://legal.bit2me.com/en/support/solutions/articles/35000293283-market-data)明确允许内部存储、分析和衍生作品；禁止第三方再分发，含衍生研究；[官方 OpenAPI](https://api.bit2me.com/openapi.json)提供公共 spot OHLCV、起止时间及上限 1000 | 选择为首条候选。仅私有内部用途，广义 commercial 权利仍为未知；完整历史必须实际分页验证 |
| Bitfinex | [市场数据条款](https://www.bitfinex.com/legal/general/market-data/)允许内部分析；[API 条款](https://api-pub.bitfinex.com/v2/conf/pub:legal:terms:api)账号前提与[公共 API 文档](https://docs.bitfinex.com/docs/requirements-and-limitations)无需账号表述存在适用范围疑问；[candles](https://docs.bitfinex.com/reference/rest-public-candles)支持时间分页 | 用户账号/书面授权未确认，不放行；未索取密钥 |
| Coinbase | [当前市场数据条款](https://www.coinbase.com/en-au/legal/market_data)包含研究用途和更广的自动化/衍生使用限制，不能仅凭一段许可作无条件授权 | 不放行 |
| Bitstamp | [官方 API 页面](https://www.bitstamp.net/api/)说明商业市场数据使用需要 Data License Agreement；OHLC 支持分页 | 没有对应协议，不放行 |
| Kraken | [REST OHLC](https://docs.kraken.com/api/docs/rest-api/get-ohlc-data/)仅最近 720 条；[历史文件](https://support.kraken.com/articles/360047124832-downloadable-historical-ohlcvt-open-high-low-close-volume-trades-data)可补较早历史，但商用授权范围未核实 | 不把下载能力当作授权；本轮不选 |
| Gemini | [市场数据协议](https://www.gemini.com/legal/market-data-agreement)允许受限内部分析；[candles](https://developer.gemini.com/trading/rest-api/market-data/list-candles)未提供覆盖本任务的历史分页参数，trades 历史有限 | 无法证明原冻结区间完整，不选 |
| Coin Metrics community | [community data](https://github.com/coinmetrics/data)为 CC BY-NC 4.0；API 软件许可与市场数据许可不同 | 不能据此支持商业内部研究，不选 |
| Binance public data | [公开数据仓库](https://github.com/binance/binance-public-data)代码开放不能自动授予底层行情商用权利 | 未获得充分、明确的当前使用权证据，不放行 |

Bit2Me 的官方条款、OpenAPI 原始 bytes、URL、抓取时间、摘要保存在本机 `data/raw/rights/`。
独立 `ReviewedRightsEvidence` 引用该原文包；fetcher 只验证、复制和引用，不能创造许可。
raw 行情和衍生账户曲线、统计、逐笔记录、Graph 私有日志不得进入公开 Git。公开代码附带
的测试全是隔离的合成夹具，不计为真实研究成功。

## 字段与信任边界

完整规范见 [data-lake-spec](../../../../docs/data-lake-spec.md#41-显式选择的-ohlcv-核心研究契约)。
新增 opt-in 核心契约，没有改变旧 `LAB_OHLCV_V1` 的必需列和既有 validator。可选的原生
count、quote volume、VWAP 缺失必须披露；策略需要时仍然必需。新契约增加独立九项 trust
assessment、两次全历史原始比对、时钟和更晚桶的收盘证据，以及每次正式消费前的全量离线重建。

## 分页协议

固定 64 根目标窗口，与 API 返回条数无关；请求起点前移 1 毫秒处理包含/不包含起点的差异。
仅目标边缘一根额外观察可明确排除并记录，不能隐藏内部重复或缺口。部分窗口被接口截断时，
保留该父响应，递归二分请求到完整叶窗口；单根仍缺失就失败。原始倒序只能显式反转，乱序拒绝。
两个完整抓取轮次之间的任何历史数值修订都阻止信任。HTTP 429 遵守 Retry-After，有限重试后
保留失败快照，不更换账户或 IP 绕过限制。

## 研究与回写

Graph 验证合同、许可、数据、manifest 和 trust assessment 的摘要及相互绑定，并自己计算
ELIGIBLE。Lab 的正式入口先检查该候选，再运行被冻结的 v2 账户引擎及 reference validated
统计实现。完整网格、非零双边成本、IS/OOS、参数敏感性和限制写入本地 evidence。历史 holdout
已在 V3 诊断中部分暴露，仍标记 `RETROSPECTIVE_PREVIOUSLY_OBSERVED`。

固定规则没有拟合步骤，不能把事后分片命名为训练式 walk-forward。已有顺序时间分片只用于
稳定性描述。DSR 是固定候选族的条件诊断；PBO 是 8 块 CSCV，未 purge/embargo；均不能把
重复使用历史样本包装成新的前瞻证据。是否研究通过与本轮数据链是否打通分别判断。

复现入口依次为 [抓取](../scripts/fetch_market_paged.py)、[离线验收](../scripts/audit_market_core.py)、
[正式研究](../scripts/research_v4.py)。正式调用必须先有受审的 rights artifact 和 Graph 候选；
公开仓库不自带可绕过这些条件的真实数据样本。
