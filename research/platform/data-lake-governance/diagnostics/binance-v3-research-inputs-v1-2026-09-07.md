# Binance V3 统一研究输入治理

## 结论边界

价格侧已完成：V3 15m 为唯一输入，配套 1h/4h/1d v2 已发布、登记并通过独立可信读取验收。新研究具备显式版本、截止、零成交/缺口分段和身份有效期门禁。

**本轮不能写成整套数据湖已无条件 READY。** 资金费率官方接口两次在部分成功后返回 403；第二轮程序遇到拒绝后即停止后续请求。当前已完成 233/867 个 API 查询，其余 634 个未完成（第二轮 1 个实际 HTTP 403、633 个在本地停止后未发出），不是 634 个区间均已由官方确认无数据。历史月度归档独立下载与校验，不能替代尚未取得的 9 月尾部。

资金费率阶段性快照已发布并独立验收，状态为 `PARTIAL_COVERAGE`，不是全量补齐。执行于北京时间 2026-09-07 12:04 收口为 `PARTIAL_BLOCKED_FUNDING_ACCESS`，下载与验收进程均已结束；没有承诺后台自动补齐。

统一输入清单：[research_input_bundle.json](../artifacts/binance_v3_research_inputs_v1_20260907/research_input_bundle.json)；[执行验收](../artifacts/binance_v3_research_inputs_v1_20260907/execution_closeout.json)。清单中的资金费率状态和已知限制不得由价格 PASS 覆盖。历史身份仍未证明完整 PIT，旧消费者未自动迁移。

## 输入身份与保护

- 唯一 15m 输入：`binance.perp.ohlcv.15m.history.v3`；manifest SHA256 `e90fe921e03bccf78dea0b29675470a3661baa5cd38af8dadc2202bb0e475e8f`。
- 原 V3 是已接受旧底座加官方增量和补洞，不是全历史远端重下载。本轮没有重新认证全部旧历史远端修订。
- 总冻结截止：`2026-09-05T15:45:00Z`；不是执行结束时的实时数据。
- 原 normalized V1、15m V2/V3、旧高周期 v1 的内容指纹均复核一致，见 [保护验收](../artifacts/binance_v3_research_inputs_v1_20260907/protected_versions.json)。
- 原 15m 的零成交和 12 段边界保留，不删行以制造完整性，不覆盖冻结策略或缓存。

## 配套价格版本

以下均为 874 个观测合约，不代表 874 个当前活跃加密币。时间均为 UTC。

| 数据集后缀 | 行数 | 最早 bar open | 最晚 bar open | 最晚完整收盘 | 段数 | 内部空位 |
| --- | ---: | --- | --- | --- | ---: | ---: |
| `1h.from_15m.v2` | 15,393,559 | 2019-09-08 18:00 | 2026-09-05 14:00 | 2026-09-05 15:00 | 886 | 261 |
| `4h.from_15m.v2` | 3,847,414 | 2019-09-08 20:00 | 2026-09-05 08:00 | 2026-09-05 12:00 | 886 | 69 |
| `1d.from_15m.v2` | 640,378 | 2019-09-09 00:00 | 2026-09-04 00:00 | 2026-09-05 00:00 | 886 | 17 |

行质量全量 SQL 均 PASS；表中空位仍受研究 reject/分段门禁约束。来源保留 V3 已裁决结果，包含日度补洞；没有重新按旧 V1 白名单过滤。聚合沿用 UTC 00:00 相位、4/16/96 根完整组件，源不足或未到收盘不输出。

完整桶分别排除 1,368 / 1,659 / 1,744 个候选桶，含首尾不完整窗口、V3 边界及冻结截止；这与内部缺口数不是同一个指标。[组件台账](../artifacts/binance_v3_research_inputs_v1_20260907/component_accounting.json)

- [1h 发布后验收](../artifacts/binance_v3_research_inputs_v1_20260907/1h_acceptance.json) · [连续段](../artifacts/binance_v3_research_inputs_v1_20260907/1h_segments.csv)
- [4h 发布后验收](../artifacts/binance_v3_research_inputs_v1_20260907/4h_acceptance.json) · [连续段](../artifacts/binance_v3_research_inputs_v1_20260907/4h_segments.csv)
- [1d 发布后验收](../artifacts/binance_v3_research_inputs_v1_20260907/1d_acceptance.json) · [连续段](../artifacts/binance_v3_research_inputs_v1_20260907/1d_segments.csv)
- [独立聚合对账](../artifacts/binance_v3_research_inputs_v1_20260907/independent_aggregation.json)：BTC、ETH、SOL、HYPE、BNX、AIA、LIT 全部已观测历史，独立 pandas 实现对照三个周期。键完全一致，数值在冻结容差内一致；不是只比较同一个聚合函数的两次输出。

首次按年构建曾触及内存上限；未发布临时输出，后改成按月处理完成。未修改已发布价格构建脚本及其指纹。

## 标的、零成交与连续窗口

[身份库存](../artifacts/binance_v3_research_inputs_v1_20260907/identity_inventory.csv) 记录每个标的的已观测范围、正成交行数和冻结元数据分类。874 个观测代码中，当前快照分类为 COIN 652、INDEX 3、其他已分类 188、UNKNOWN 31；这只是快照分类，不是历史可投资集合证明。

新 [读取与有效性实现](../../../../src/strategy_lab/data/research_inputs.py) 提供：

1. `load_v3_research_ohlcv()`：固定数据版本、UTC 对齐窗口及明确截止，使用 catalog 严格内容验证，不回退旧缓存。
2. `segment_research_bars()`：先拒绝乱序和重复，再按缺口、零成交、身份边界分段。`observed_valid` 不等于可成交；默认 `require_verified` 还需要带证据的历史身份有效期。
3. `complete_window_mask()`：回看及未来标签必须完整落在同一有效段。滚动计算必须按 `research_segment_id` 分组。
4. `observed_diagnostic` 是显式诊断选择，不是 PIT 或可交易性承诺。不能用当前 TRADING 名单过滤过去全部历史后声称无幸存者偏差。

实际新入口已试读 BTC 日线 2026-08-01 至 2026-09-05：35 根，MA7 有完整回看窗口 29 根。旧 `load_canonical_binance_perp_1d()` 仍保留 v1 行为；新研究须显式使用新入口或 v2 ID。

## 资金费率治理约束

原主标准化目录有 2,506,280 行、2,500,787 个精确 `(symbol,ts)` 键。精确重叠费率没有冲突，但同小时存在不同时间戳；其中有的可能涉及传统资产特殊结算，不能全部视为重复后取整合并。

本轮规则：

- 保留实际毫秒时间和来源，不将费率派生成零值；旧 `funding_interval_hours` 不直接当历史日历。
- 精确时间重叠必须费率一致、不得出现多种已明确的 Regular/Special 类型，否则拒绝发布；一致时优先保留有显式类型的 API 记录。
- 同小时多事件保留并标为歧义，默认拒绝净收益消费，不擅自相加或删除。
- API 完整分页，保存原文、URL、抓取时间和哈希；403/418/429 停止。公开归档验证 SHA256、CRC、月份、字段和原始记录往返一致性。
- `load_verified_funding_snapshot()` 只承诺读取已核对快照，不承诺全历史完整；`require_funding_window()` 需要独立的期望结算时间证据，遇缺失、额外或歧义事件拒绝净收益计算。期望日历不能由待检数据自身推导。

查询计划：[plan.json](../artifacts/binance_v3_research_inputs_v1_20260907/funding/plan.json)。接口限制记录：[fetch_errors.json](../artifacts/binance_v3_research_inputs_v1_20260907/funding/fetch_errors.json)。官方的分页、限额及 Regular/Special 字段定义见 [Binance 官方资金费率接口](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#get-funding-rate-history)。

### 实际发布结果

- 数据集：`binance.perp.funding.v3_inputs.v1`，独立于 OHLCV catalog，用专用读取入口。
- 2,660,857 个精确时间键，比原去重库存增加 160,070 个；这不是已经确认新增 160,070 次独立经济结算，同小时歧义仍保留。
- 全库存时间为 2019-09-10 08:00 UTC 至 2026-09-05 12:00:00.007 UTC；这是全库最早/最晚观测，不代表每个标的都覆盖这一范围。
- 精确时间费率冲突 0，明确 Regular/Special 类型冲突 0；10,972 个同小时多事件组、21,944 行默认不能直接用于净收益。仍有 11 个超过 8 小时 5 秒的观测间隔，不能仅靠固定 8 小时规则断定实际漏结算。
- 2,326 份月度归档查询已全部处理，1,344 份通过 CHECKSUM/CRC/原文往返校验，982 份官方 404。404 只证明该归档路径当时不存在，不证明对应交易或结算从未发生。两次连接中断和 7 份中文路径编码失败均已修复/补取；最终归档错误为 0。
- 原资金费率目录内容指纹未变；发布快照有 85 个 parquet 文件，严格读取指纹通过。后续若继续补齐，应发布新版本，不能把新增下载追加入本次已冻结快照。

证据：[费率验收](../artifacts/binance_v3_research_inputs_v1_20260907/funding/acceptance.json) · [归档结果](../artifacts/binance_v3_research_inputs_v1_20260907/funding/archive_summary.json) · [逐标的覆盖](../artifacts/binance_v3_research_inputs_v1_20260907/funding/symbol_inventory.csv) · [查询覆盖](../artifacts/binance_v3_research_inputs_v1_20260907/funding/query_coverage.csv) · [歧义清单](../artifacts/binance_v3_research_inputs_v1_20260907/funding/ambiguous_event_hours.csv) · [长间隔](../artifacts/binance_v3_research_inputs_v1_20260907/funding/remaining_long_intervals.csv) · [冻结来源索引](../artifacts/binance_v3_research_inputs_v1_20260907/funding/published_input_receipts.json)。

### 价格与费率不能按库存数量混为一谈

资金快照保留了 910 个历史代码，其中只有 864 个与 V3 的 874 个价格代码相交；另 10 个价格代码没有任何已取得费率。保留的 46 个范围外旧代码含其他计价币标记和旧命名，未自动改写或认定为 USDT 合约，不得纳入 V3 价格样本的净收益。

**864 个有观测也不等于 864 个资金费率完整。** 还需逐研究窗口检查身份和独立结算日历。范围证据：[范围审计](../artifacts/binance_v3_research_inputs_v1_20260907/funding/price_scope_audit.json) · [价格/费率连接清单](../artifacts/binance_v3_research_inputs_v1_20260907/funding/price_scope_inventory.csv)。

## 测试、使用范围与未完成项

最终定向测试 **59 passed**，包括隔离临时目录中的资金费率部分发布及严格回读、中文归档路径、不同时间精度和无时区费率拒绝。新增读取/分段/资金费率/归档代码 Ruff 通过。[测试记录](../artifacts/binance_v3_research_inputs_v1_20260907/targeted_tests_execution.json) · [独立验收执行](../artifacts/binance_v3_research_inputs_v1_20260907/final_verification_execution.json)。全仓消费者检查仍有原先 5 个未登记直读脚本错误；本轮没有扩充冻结白名单或修改那些策略来消除报错。

构建过程中，首次按年价格构建触及内存上限；首次费率输出遇到分区字段语法问题，均未发布不完整结果。调整为月度价格构建、修复费率输出并增加完整发布回读测试后，发布验收通过；未放宽数据校验容差。

空间：本轮新增高周期约 824 MiB（1h 601、4h 178、1d 45），费率快照约 8.4 MiB；加上新归档、API 原文、审计记录及保留的约 22 MiB 未发布临时输出，总增量约 0.9 GiB。验收时磁盘剩余约 191 GiB。本轮未下载全市场 1m/5m，也未删除旧数据腾空间。

可用：15m 及配套高周期的价格/量价研究，显式有效段下的观测样本市场风格诊断。

仍有限制：634 个未完成资金费率查询、同小时事件歧义、范围外旧费率代码身份、完整历史结算日历、完整历史资产身份/PIT、旧消费者迁移。继续完成费率尾部需要官方接口恢复稳定可访问后按原查询范围补取，并另发版本；不通过代理绕开拒绝。不能把治理结果推广成策略 PASS、净收益无缺漏或实盘准备完成。

契约：[统一输入治理契约](../specs/binance-v3-research-inputs-v1-2026-09-07.md)。读取规范和示例：[data-lake-spec 第 17 节](../../../../docs/data-lake-spec.md#17-v3-配套统一研究输入)。
