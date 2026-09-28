# 原始 Top10 基线：观察资金费估算输入补证（2026-09-09）

状态：`EXPLORE_UNTRUSTED_OBSERVED_FUNDING_CASH_INPUTS`。本报告只交付资金费现金账输入，不计算策略收益，不替代完整资金费日历、历史合约身份或实盘认证。严格复核中的早期 native mark 缺失事实没有被推翻；本轮按照用户授权，明确采用官方 1 分钟标记价作估算。

对应[估算契约](../specs/binance-1d-mcsm-baseline-estimate-20260909.md)、[最终修正输入](../artifacts/baseline-estimate-20260909/inputs-identity-corrected/summary.json)、[最终资金费摘要](../artifacts/baseline-estimate-20260909/funding-identity-corrected/summary.json)及[独立输出审计](../artifacts/baseline-estimate-20260909/funding-identity-corrected/independent-output-audit.json)。未改已发布数据湖、旧 Sep08 严格证据或共享内核；主账与账户结果由总任务统一引用。

## 交付范围

实际窗口为 2020-03-01 00:15 UTC 至 2026-07-01 00:15 UTC，76 个月、760 条资产月持仓；BNX 和 VIDT 按已冻结终止事件提前截断。独立修正持仓删除两个身份断裂形成：2025 May AERGO 换为 LAYER、2026 Jan LIT 换为 Q，其他 758 条持仓不变。替换由原资格与排名产生，不按收益选择。

| 最终修正版观察事件 | 数量 |
| --- | ---: |
| 实际持仓内观察资金费事件 | 97,421 |
| hash 核验的原生 API mark | 1,233 |
| 官方 1m mark 代理 | 96,188 |
| 观察事件中仍缺 mark | 0 |
| 源类型未指定、模型明确假定 Regular | 95,912 |
| 空持仓窗口 | 0 |

相对于保留的旧名单输入：删除 AERGO 186 事件、LIT 186 事件，增加 LAYER 648 事件、Q 186 事件。其余 758 条持仓对应 96,587 事件的时间、rate、类型、mark 中心及上下情景均**逐值完全相同**。只有 LAYER 旧 April 持仓末次 2025-05-01 00:00 事件的 source container 由单分钟 API 变为新 May 需求的整月 ZIP；两份原文均保留，open=3.0374、low=3.03508423、high=3.03802015 完全一致，不是价格修订。

## 来源与估算含义

- 固定 bundle `binance.v3.research_inputs.v2`，bundle SHA256 `d2a729d03be71d67aa9c5522fb242bbf010b6c64400233c27d9cb2406f567008`；资金费 manifest SHA256 `398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076`。按其原生毫秒事件加载，不以当前默认替换冻结输入。
- 有可逐条唯一匹配、原文 hash 核验的官方 `fundingRate` API `markPrice` 时，使用该原生 mark；原生 mark 行的 low=center=high。无可证实 native mark 时，使用该观察事件所在 UTC 分钟的官方 `markPriceKlines` open 为中心，low/high 为条件情景；不用交易 K 线价格冒充标记价。
- `proxy_center=OFFICIAL_MARK_1M_EVENT_MINUTE_OPEN`；`proxy_bounds=EVENT_MINUTE_LOW_HIGH_CONDITIONAL_NOT_CONFIDENCE_INTERVAL`。分钟 high/low 是条件情景，不是精确结算 mark 的已证误差界、置信区间或成交滑点。
- `frozen_ts` 和 `frozen_rate_type` 保留冻结输入；`source_rate_type` 保留原生匹配后源类型。Unspecified→Regular 仅在输出模型类型中显式假定，逐行标注 `ESTIMATE_ASSUMES_REGULAR_UNSPECIFIED_SOURCE`。没有以该假定宣称源提供了 Regular 类型。
- 原生时间调整只允许独立完整响应内唯一 rate/type 对应；调整后重新核对实际持仓开区间/闭区间 `(entry_ts, exit_ts]`。`minute_ms` 仅作分钟代理键，不覆盖原生事件时间。

官方分钟来源为 `data.binance.vision/data/futures/um/monthly/markPriceKlines/.../1m/` 月 ZIP + CHECKSUM，及 `fapi.binance.com/fapi/v1/markPriceKlines` 有界 1m 窗口。请求时间、原文、响应与 SHA 都随 receipts 保存。最终 plan 独立冻结，旧来源只按相同 URL 与实际重算 SHA 复用，不继承旧账户净值。

最终修正版主计划 1,390 项。5 个空的小窗口 API 转同月官方分钟档；币安人生 May2026 月档 404 转该持仓所需的 31 个有界日内 API 窗口；月档内部共 220 个必要分钟缺口另外冻结 70 个日内窗口补齐。这些是**mark 来源补证**，不是资金费日历补造。主源缺失、原失败回执与补充计划全保留。4 worker 全局每 0.5 秒最多发一请求；429/418/403 即停，没有重试绕过。

## 日历仍未认证

[部分已证日历核对](../artifacts/baseline-estimate-20260909/funding-identity-corrected/calendar-observed-audit.json)仅覆盖冻结日历能证明的片段：实际持仓中期望 1,650 事件全部存在，已知缺项为 0；另外 **95,771 个观察事件位于该部分已证日历之外**。观察事件的相邻且同源声明频率检查没有发现大于 2 秒的间隔异常，但这不证明片段首尾和全部历史日历完整。

因此 `calendar_complete_proven=false`，未知或缺失事件不填零；输入足够让总任务运行“已观察事件 + 明示标记价代理”的估算账户，**不足以称为完整真实净值**。其余 PIT、合约身份及终止价格的约束继续由主契约保留。

## 校验及不可变证据

独立输出审计通过：观察 event_id 无删除/重复，`(symbol, ts, rate_type)` 经济键唯一；所有事件位于修正后持仓窗口内，原毫秒时间/类型/rate 保留；UTC 分钟键逐条反算一致；所有场景 mark 为有限正值且 low≤center≤high；对实际使用的 **1,493 份原文、668,326,955 字节**独立重算 hash 通过；758 条未修正持仓全部现金相关数值精确一致。解析与时间回归测试 11 项通过；这不是策略盈利或完整日历验证。

| 证据 | SHA256 |
| --- | --- |
| corrected holdings.parquet | `2765cc3fade0b8c571871c5e2bfff88ad6e5bc65198a5fff35e261afa6df61e4` |
| corrected plan-v2.json | `2dc88e90258dc1004e2c5e82523d638e205bb569180cde783bdeb40c43990b3e` |
| corrected estimated-funding-events.parquet | `4bebab8e1d78549b38aaef3f1cb84d980d11cb686ca896d47a1c27c4fb3a85ee` |
| corrected summary.json | `2840645f820708d6046fc9a26213e001b759dd5e185091889e693112548b58b4` |

实施时的两个来源问题明确留档：最初旧 `funding/plan.json` 因 pandas 微秒单位误按纳秒换算产生无效 1970 请求，立即停止，旧计划/投影/空响应保留并由 `funding/plan-v2.json` 更正；任何收益计算前已做 UTC 反算断言。另有未发出的 scheduler cancellation/Unicode URL 编码失败保存原回执，只恢复确定未发出的请求，真正的源失败没有原 endpoint 重试。修正版所有原文取自校验后的计划和来源；上述旧无效计划不是最终输入。

最终事件文件为 [estimated-funding-events.parquet](../artifacts/baseline-estimate-20260909/funding-identity-corrected/estimated-funding-events.parquet)。旧 [funding/summary.json](../artifacts/baseline-estimate-20260909/funding/summary.json) 及 96,959 观察事件仅保留为身份修正前输入对照，不应拿它运行最终策略账户。
