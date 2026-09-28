# V3 配套资金费率 v2 治理与验收

## 结论

资金费率 v2 已独立发布并通过完整回读、77 项定向测试与旧输入指纹保护。事件歧义已清零，状态仍为 `PARTIAL_COVERAGE`：**数据治理本轮已收口，但不能宣称全历史净收益可直接计算**。

本轮只治理资金费率：价格 V3、配套高周期 v2、资金费率 v1 和冻结消费者不迁移、不覆盖。截止仍为 **2026-09-05 15:45 UTC / 北京时间 23:45**，不是执行当天。

## 数据与解决的问题

| 项目 | v2 发布结果 | 解释 |
| --- | --- | --- |
| 资金事件 | 2,654,430 行 / 874 个 V3 价格代码 | 每币有记录不等于每币全历史完整 |
| 全局首末事件 | 2019-09-10 08:00 至 2026-09-05 15:00 UTC | 不代表所有标的都覆盖这一跨度 |
| 待裁决同小时组 | 57,409 组，全部完成 | 包含旧 10,972 组歧义及新增来源的类型/时间表示差异 |
| 无法裁决事件 | 0 行 | 仅为事件解释层面通过，不代替覆盖门禁 |
| 特殊结算 | 34 条，全部保留 | 32 条 EQUITY、2 条 KR_EQUITY；不合并进普通费率 |
| 原生频率证据 | 1,484 个通过 CHECKSUM/CRC 的月档 | 本轮新增 140 个，不是全市场全历史月档全集 |
| 可证明连续结算片段 | 639 段 / 585 个标的 / 178,994 个期望事件 | 只准片段内消费，不外推首尾、频率切换或 API-only 尾部 |

同一小时、费率相同、时间相差几毫秒，只是重复候选。本轮依据完整官方小时查询或原生月档逐一对应，才把旧键映射到官方原始毫秒事件；不是统一取整时间戳。合并输入共有 2,712,098 个精确时间＋类型表示键，清理 57,668 个重复表示，保留逐条映射。

旧 27 组不同费率的股票类双事件，官方逐小时查询全部明确返回 `Regular` 和 `Special`。按[官方资金费率文档](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#get-funding-rate-history)，Special 为股票合约股息产生的额外结算；不能作为异常重复删除。另有近期 7 条 Special，因此本版共 34 条。

v1 的 910 个历史库存代码中，46 个不属于 V3 的 USDT 价格范围；本版不自动转换旧命名或计价币，旧快照及原文仍保留。原来完全没有费率记录的 10 个 V3 代码，本轮已获得近期官方事件。

## 下载和覆盖账：三个层次不能混淆

1. **直接执行账**：原 634 个未完成逐币查询，本轮先完成 130 个 COIN 查询；另 504 个没有直接执行，包含 351 个 COIN 查询。逐币队列在 IR 的历史尾部请求返回 HTTP 403 后停止，不能断言其原因就是限流。
2. **检索范围账**：复用已验证月档，加上本轮月档及近期全市场查询后，634 个原查询范围中，563 个被官方检索范围覆盖，剩余 71 个未覆盖。已被其他证据覆盖的范围没有伪记为逐币执行完成。
3. **结算日历账**：检索完整、返回空、价格有记录均不能证明全历史应结算事件完整。净收益仍须逐窗口通过历史频率、事件和值一致性检查。

同一官方接口允许不指定 `symbol`。冷却后，本轮在同一地址执行 9 月 1 日至冻结截止的 5 个 UTC 日块，共 28 页，保留 17,270 个唯一原生事件、767 个交易所原生代码；其中只有精确对应 V3 的代码进入 v2。没有改用代理或替代地址。

全市场查询采用末时间戳重叠分页，防止同毫秒多个合约或普通/特殊事件被截断。另做 7 次逐币交叉验证：BTC、ETH、SOL、HYPE、TRX、ZEC 非空结果一致；IR 两种查询都为空，后者仍不是历史无结算证明。另执行 27 次股票事件类型核验，全部成功。

证据：[执行计划](../artifacts/binance_funding_v3_inputs_v2_20260907/plan.json)、[全市场尾部补充契约](../specs/binance-funding-v2-global-tail-supplement-2026-09-07.md)、[全市场结果与逐币对照](../artifacts/binance_funding_v3_inputs_v2_20260907/global_parity.json)、[股票类型核验](../artifacts/binance_funding_v3_inputs_v2_20260907/stock_event_types.json)、[逐范围覆盖账](../artifacts/binance_funding_v3_inputs_v2_20260907/query_evidence_coverage.csv)。

### 剩余 71 个范围是否影响可交易研究

对 V3 进行了严格内容哈希可信读取，并按整根 15m K 线的重叠范围核查成交笔数、成交量和成交额：

- 71 个范围共对应 1,898,147 根价格记录，全部三项成交字段为零。
- 任一成交字段大于零的记录为 0；正成交闭合 K 线为 0。
- 因此这些范围属于价格研究已排除的零成交区间，没有与本次 V3 的正成交观测区间重合。
- **不能据此宣称合约已退市、当时没有资金结算或费率应填零**；跨越这些范围的持仓、标签和净收益仍拒绝。

证据：[逐范围成交审计](../artifacts/binance_funding_v3_inputs_v2_20260907/uncovered_price_activity.csv)、[可信输入与汇总](../artifacts/binance_funding_v3_inputs_v2_20260907/uncovered_price_activity.json)。这项审计只解释 71 个未检索范围，不把其余已检索范围自动升级为结算日历完整。

## 新读取契约

新数据 ID 为 `binance.perp.funding.v3_inputs.v2`，事件与覆盖证据独立分区存储：

- `events/month=YYYY-MM/data.parquet`：原生毫秒、费率、事件类型、资产分类快照、来源证据及稳定事件 ID。
- [coverage/segments.parquet](../../../../data/derived/datasets/binance_perp_funding_v3_inputs_v2/coverage/segments.parquet)：经过原生月档频率验证的连续片段。
- [coverage/expected_events.parquet](../../../../data/derived/datasets/binance_perp_funding_v3_inputs_v2/coverage/expected_events.parquet)：片段内应计入的事件、类型、数值和证据哈希。
- [_MANIFEST.json](../../../../data/derived/datasets/binance_perp_funding_v3_inputs_v2/_MANIFEST.json)：全部 parquet 内容指纹、冻结截止、源码/契约/输入索引哈希与明确限制。

入口：[funding_v2.py](../../../../src/strategy_lab/data/funding_v2.py)。`load_funding_v2()` 必须显式固定 manifest SHA256；`require_funding_v2_window()` 对 `(start, end]` 做全窗口核验，缺失、额外事件、歧义、篡改和跨证据边界均拒绝。

调用方还必须提供独立历史身份凭据。当前接口保存并要求非空 `identity_evidence`，**不会自动鉴定这段字符串的真实性**；不能随便填字符串获得 PIT 认证。真实读取冒烟测试中的凭据仅为测试占位标签，不构成交易身份确认。

只有完整落在已证明片段内、且该子窗口确实没有应结算事件时，才允许返回空事件集。这与把未观测到的费率补成零完全不同。股票类特殊事件虽已解析，尚未获得完整股票交易/股息结算日历，不能借 COIN 片段门禁直接计算其全历史净收益。

旧 [research_inputs.py](../../../../src/strategy_lab/data/research_inputs.py) 与旧 bundle 保持冻结，新研究显式选 v2，旧研究不会自动换数据。使用规则见 [data-lake-spec](../../../../docs/data-lake-spec.md) 第 18 节。

## 验收与执行偏差

逐事件对账覆盖全部 2,654,430 条输出：无法对应旧输入或官方原生费率值的事件为 0；V3 范围内旧键既未保留又无证据映射的数量为 0。证据：[值与旧键保留审计](../artifacts/binance_funding_v3_inputs_v2_20260907/value_lineage_audit.json)、[映射明细](../artifacts/binance_funding_v3_inputs_v2_20260907/event_mapping.csv)。

第一次写出因同时打开过多日分区触及 2 GB 数据库内存限制，在发布前失败；没有覆盖旧数据或发布半成品。改为单月分批压缩写出后重新执行全量原文校验、事件裁决及验收。治理契约、输入证据和数据语义未改。

最终发布为 85 个 UTC 月事件分区加 2 个覆盖文件，共 87 个 parquet、116,026,108 字节（约 111 MiB）。本轮快照、原文与审计材料合计约 141 MiB；独立验收时磁盘仍有约 188 GiB 可用。

- manifest SHA256：`398cc19eac88d0e8c55258c118f6cae2481c6b2d1a5e6253778344b9f25a1076`。
- parquet 内容指纹：`314fa51dfb7915cada0e7cea351f8def1744955d546db2c6610e75f367d9e423`。
- 暂存与正式快照分别通过新读取器完整内容验证；独立验收再次读回 2,654,430 条记录。
- 真实 BTC 证据窗口通过；删掉期望事件会拒绝；虽有近期 API 记录、但没有日历证据的 9 月窗口仍正确拒绝。证明片段内无结算的子窗口合法返回空集。
- 15m V3、1h/4h/1d 配套 v2、费率 v1 的 manifest 与完整 parquet 内容指纹未变；旧 normalized 费率指纹及旧研究读取源码未变。
- 定向测试 **77 passed**，本轮新增代码 Ruff 通过。
- 全仓消费者检查仍有原有 5 个未登记直读错误（CTP P6/P7/P7a/P7b、CER P0），不属于本轮新文件；没有扩大白名单来制造全仓通过，也未擅自修改这些研究家族。

证据：[发布验收](../artifacts/binance_funding_v3_inputs_v2_20260907/acceptance.json)、[独立真实读取](../artifacts/binance_funding_v3_inputs_v2_20260907/real_reader_smoke.json)、[旧输入指纹保护](../artifacts/binance_funding_v3_inputs_v2_20260907/closeout_protection.json)、[测试日志](../artifacts/binance_funding_v3_inputs_v2_20260907/targeted_tests_execution.json)、[消费者检查](../artifacts/binance_funding_v3_inputs_v2_20260907/consumer_gate_execution.json)、[本轮收口记录](../artifacts/binance_funding_v3_inputs_v2_20260907/execution_closeout.json)。

## 尚未宣称完成的事项

本轮完成事件解释和部分覆盖治理，不是全历史重下载。完整历史结算日历、完整 PIT 身份和旧消费者迁移仍未完成。后续若要全市场跨年净收益，需要继续补足所需日期的原生频率/历史身份证据，并发布新版本；不能解除门禁或覆盖本版快照。

主契约：[资金费率 v2](../specs/binance-funding-v3-inputs-v2-2026-09-07.md)。本轮不是策略晋升，不构成可上线证明。
