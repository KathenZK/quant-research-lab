# 原 Top10 基线：资金费结算标记价可获得性（2026-09-08）

## 结论

状态为 `FUNDING_MARK_SOURCE_PARTIALLY_RECOVERABLE_NOT_NET_VERIFIED`。

**一部分缺失不是源端拿不到，而是冻结输入尚未留存：**本轮从 Binance 官方资金费历史接口取回 HOME、LAB、H 在 2026 年 6 月共 1,235 个事件的原生 `markPrice`。这些事件与之前核验过 CHECKSUM 的官方月档，按原生毫秒时间逐条一对一对应，费率差全为零。因此，这三笔异常费率来源现在已经补到了计算持仓现金流所需的结算标记价。

**但早期历史仍存在明确源端缺失：**BTC 2020 年 3 月的官方接口返回 93 个资金费事件，所有 `markPrice` 均为空字符串。这一窗口不能靠再次下载同一接口补齐精确结算标记价。仅此负例已足以阻止宣称原 2020 年起基线的全历史精确资金费账通过；不据此推断其他早期资产和窗口全部不可获得。

没有用成交价、日收盘价或 mark Kline 的 open 冒充资金费实际结算 mark；没有修改或发布数据湖，没有修改持仓名单，没有发布组合收益。

## 六个预先固定的来源探针

探针先冻结计划，再按单线程、请求间隔至少 2 秒执行；任一 HTTP 错误即停止，不重试、不切换主机。全部 6 个请求均成功，未触发限流或绕过限制。

| 官方请求范围（UTC，末端不含） | 返回事件 | 有效原生 mark | 结论 |
| --- | ---: | ---: | --- |
| HOME，2026-06-01 至 2026-07-01 | 524 | 524 | 可补结算 mark |
| LAB，同上 | 410 | 410 | 可补结算 mark |
| H，同上 | 301 | 301 | 可补结算 mark |
| BTC，2020-03-01 至 2020-04-01 | 93 | 0 | 原生字段空，不能精确计算现金流 |
| BTC，2026-06-01 至 2026-07-01 | 90 | 90 | 近期正对照 |
| BTC，2026-09-01 至 2026-09-05 | 12 | 12 | 近期正对照，不纳入旧基线 |

每个响应均小于 1,000 条上限；保存原始响应字节、请求 URL、开始/结束时间、HTTP 状态/响应头及 SHA256。接口列表未被 limit 截断，不等于独立历史日历已证明。

Binance 官方 API 文档把 `markPrice` 定义为对应特定资金费结算的标记价，并规定 `/fapi/v1/fundingRate` 的起止时间均包含端点、按时间升序、上限 1,000 条。本轮因此把期末不含边界转换为期末毫秒减一；未对返回的毫秒时间取整。[官方接口文档](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)

## 已有本地输入究竟缺在哪里

对 `data/raw/funding_rates/.../source=binance_futures_funding_rate_api` 的 428 份原始响应逐文件验证对应 receipt 内容哈希，共见 97,011 行（含查询重叠），其中 92,752 行带有效 mark，涉及 822 个代码。HOME/LAB/H 的上述 6 月窗口、BTC 2020 年 3 月和 2026 年 6 月在这批 API 原文中均没有匹配事件；BTC 9 月正对照已有原文。这个 raw 目录已见的最早有效 mark 在 2024-02-01，不代表全市场 mark 开始可用的日期。

另外做了只读字段可获得性盘点，而非可信研究输入读取：

- `data/normalized/funding_rates/exchange=binance/market_type=perp`：8,902 个文件、2,506,280 行，其中 75,974 行 mark 非空且正数；大部分是 2026 年 7 月以后。最早的有限 mark 样本见 BTC/ETH 的 2023-10-31；尚未核实这些旧记录的逐份原文 lineage，不能自动导入基线。
- 旧 `data/normalized/funding/exchange=binance/market_type=perp`：6 个文件、13,741 行，其中 11,684 行 mark 有效；BTC、ETH、BNB、SOL 的有值窗口始于 2024 年 8 月，HYPE 始于 2025 年 5 月，TRX 始于 2026 年 5 月。依旧只是可补证线索，不是净值输入核准。
- 本地还存在大量 mark Kline 文件；它们是区间价格，不能自动证明某一原生毫秒结算事件的精确 mark，未被使用。

因此，上轮“旧持仓在固定资金费 v2 中 97,529 个事件全部缺 mark”的结论是**该冻结版本的输入事实**，不是“币安全部历史 mark 永远无法获取”。后续补证应独立保存和核验，不能反向修改旧冻结复现。

## 三个异常月的确切补证与日历边界

HOME/LAB/H 新 API 响应与旧官方 ZIP：原生时间一对一，数量分别 524/410/301，费率最大差均为 0，类型均为 `Regular`。月档与 CHECKSUM 再次验证，ZIP CRC 通过。合并表保留两份原文哈希、频率、结算 mark 和每一单位多头的事件资金费。

仅供检查单位换算：若恰好在整月每一个返回结算时点都持有 1 个币，已返回事件的 `-Σ(mark × rate)` 分别为 HOME 0.04049334、LAB 17.37251775、H 0.21367463 USDT。这不是策略收益率；真实基线必须使用实际持仓数量、准确的进出时点和完整日历，不得直接拿这些整月金额除以任意价格。

**资金费 mark、事件费率、覆盖日历是三个不同条件。** HOME/LAB/H 月档存在 2/3/2 次频率变化。按当前资金费 v2 规则，频率切换与首尾仍打断连续覆盖；本轮只验证 520/405/297 条同频相邻连接，没有授予整个持仓窗口 `NET_INPUT_WINDOW_VERIFIED`。即使两份官方来源的已返回事件一致，也不能把观察事件列表当成独立应结算日历。

后续基线有界补证应由预先固定的实际持仓名单生成资产窗口，不能按利润挑月。新标记价证据可补的窗口逐一补齐；源端空字段单列缺口。全历史净值若仍需区间 mark 近似，应另列“估算账”并明确授权/契约，不能把它改名为精确账。

## 追加：首月原 Top10 的第一个持仓后结算即缺精确 mark

原 2026-08-18 `adv10m_top10_long_only` 持仓 artifact 的 2020 年 3 月名单为 LINK、ETH、XRP、BTC、TRX、ADA、LTC、EOS、BCH、ETC。该文件 SHA256 为 `bb745da2e2df58af258aa6fa5e7fcae0ba10f7a6ccbfad5582c837aef8b889d1`。本轮计划在 3 月 1 日 00:15 UTC 入场，所以第一个入场后资金事件不是月初 00:00，而是 **2020-03-01 08:00 UTC**。

BTC 复用已保留的官方完整月响应；其第一个持仓后事件原生值是：`fundingTime=1583049600000`、`fundingRate="0.00027933"`、`markPrice=""`、`rateType="Regular"`。这是非零费率，不能利用“费率为零则现金流为零”的代数简化跳过 mark。

另外对其他 9 币各做一次单日有界查询，窗口为 `(2020-03-01 00:15, 2020-03-02 00:15] UTC`，共 9 请求、全部 HTTP 200，不重试。每币返回 3 个事件且 mark 全为空；这 9 币第一个返回事件均在 3 月 1 日 08:00。连同 BTC，**原首月 10 个成员的第一个持仓后结算 mark 都缺失**。因此，不需要等到 2025 年退市异常才遇到净账阻断，资金费精确结算在首个持仓日就已经无法完成。

有一项必须保留的名单语义修正：单日探针冻结时，新版完整日 K 观测候选清单只有 9 币，漏了 ADA，所以机器记录中的 `actual_first_month_observed_candidate` 对 ADA 为 false。之后查原冻结名单确认 ADA 是原 Top10 成员，其上市首日不满 96 根 15m 的端点正在主基线任务中独立复核。故 ADA 应读作“**原 Aug18 首月成员，端点复核中**”，不是新策略或事后增添的对照币。原探针计划与 receipts 不改写，另存 [成员分类补充说明](../artifacts/baseline-verification-20260908/funding-evidence/first-held-day/member-classification-addendum.json)。观测候选、原 artifact 成员、已批准历史可交易成员三种状态不混同。

- [单日有界计划](../artifacts/baseline-verification-20260908/funding-evidence/first-held-day/plan.json)与[九个请求结果摘要](../artifacts/baseline-verification-20260908/funding-evidence/first-held-day/summary.json)。
- [BTC 首个持仓后事件及完整原文回执定位](../artifacts/baseline-verification-20260908/funding-evidence/first-held-day/BTC-first-held-event-existing-source.json)。
- [BTC 原生事件 fixture](../artifacts/baseline-verification-20260908/funding-evidence/first-held-day/BTC-20200301T080000-native-event-fixture.json)，为完整官方响应中原对象的字段值摘出，不是另外抓取或合成数据，可用于会计内核拒绝缺 mark 的实证测试。

## 证据与复现

主基线关闭阶段已完成 ADA 端点重查：2020-01-31 有 64 根 15m，原端点门槛通过。上述探针初始分类及回执仍保留不改；最终解释见[ADA 重查摘要](../artifacts/baseline-verification-20260908/formation-recheck/summary.json)。这只关闭该端点疑问，不授予全历史名单或净输入资格。

- [探针冻结计划](../artifacts/baseline-verification-20260908/funding-evidence/probe-plan.json)
- [六次原始响应及 receipts 摘要](../artifacts/baseline-verification-20260908/funding-evidence/probe-summary.json)
- [本地 API 原文逐文件哈希盘点](../artifacts/baseline-verification-20260908/funding-evidence/local-native-api-inventory.json)
- [月档一对一核验与 normalized 字段盘点](../artifacts/baseline-verification-20260908/funding-evidence/native-mark-reconciliation-summary.json)
- [HOME 逐事件合并表](../artifacts/baseline-verification-20260908/funding-evidence/HOME-native-mark-archive-parity.csv)、[LAB](../artifacts/baseline-verification-20260908/funding-evidence/LAB-native-mark-archive-parity.csv)、[H](../artifacts/baseline-verification-20260908/funding-evidence/H-native-mark-archive-parity.csv)
- [探针脚本](../scripts/probe_mcsm_baseline_funding_marks_20260908.py)、[离线核验脚本](../scripts/reconcile_mcsm_baseline_funding_marks_20260908.py)

脚本默认拒绝覆盖已有证据。探针已执行完毕，不需为复查重新联网；核验脚本中 9 个断言检查通过，三币 exact merge、费率、mark 有效性、CHECKSUM 与 CRC 均已通过。完整账户盈亏、PIT、历史可交易性及实盘可运行性均未由本次来源审计核准。
