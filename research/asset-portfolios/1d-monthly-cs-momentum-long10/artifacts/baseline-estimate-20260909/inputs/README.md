# 2026-09-09 原 Top10 估算账输入与名单

本目录只重建输入和确定性名单，不计算账户收益。状态为 `EXPLORATORY_SCOPED_EQUIVALENT_AUDIT` / `EXPLORE_UNTRUSTED_BASELINE_INPUTS_RECONSTRUCTED`，不宣称逐月调用 `require_research_startup` 成功，也不宣称净收益输入、历史 PIT 或实盘通过。

## 已交付

- [持仓 Parquet](holdings.parquet)、[JSON](holdings.json)：2020-03 至 2026-06，共 76 月、760 个资产月、301 个代码。权重为 0.1；进入时点为月初 00:15，普通退出为下月 00:15。BNX 2025-03、VIDT 2025-04 按官方事件提前截断，`exit_price=null` 明确保留给独立终止估算，不用占位价。
- [换月参考价](monthly_execution_prices.parquet)：`ts,symbol,price,prior_activity_valid,already_terminal,selected_new,held_old`，覆盖旧仓和新仓。`already_terminal=true` 的旧仓已经提前关闭，不能再按这里的占位价平仓。
- [完整形成候选](ranked-candidates.parquet)：11,734 行，在活动检查和账户收益计算前冻结。按上一完整月端点涨幅降序、ADV 降序、symbol 升序。
- [逐候选选择理由](selection-decisions.csv)：只用 00:00–00:15 已闭合 bar 的活动信息；00:15 bar 后续成交量不进入资格判断。入场前已生效终止/禁开仓的合约按原排序补位，不按未来存活选择。
- [原规则日桶](daily-original-buckets.parquet)、[明确补回的部分日桶](partial-original-buckets.parquet)：原同家族治理返回日线加必要 15m 部分日聚合，保留 `bars_15m`、来源角色及部分日的实际最后 bar 时间。不是新的受信任湖数据集。
- [独立名单 QA](independent-selection-qa.json)：21 项通过，包含 116 份有界子请求及返回帧指纹、76 月每月十名、原端点/覆盖/ADV 门槛、活动时序及禁用未来存活选择。

## 来源与范围

[事前输入计划](frozen-input-plan.json)固定 bundle v2 内容指纹、原同家族返回日线指纹、官方终止证据指纹以及补证政策。[全局申请](global-scoped-audit-request.json)的 15m 审计范围是 `[2020-01-01T00:00Z, 2026-07-01T00:30Z)`。

为避免逐月重复全量内容哈希，本次按主研究明确批准的独立 explore 方法，在同一进程执行一次 `read_bundle_contract`、`verify_bundle_files` 和 `load_trusted_research_dataset` 的 FULL_MARKET / STRICT_CONTENT 审计，然后仅用同一 `verified_parquet_files` 对有界子请求调用 `read_verified_ohlcv`。每次子请求先落盘，确认范围不超出全局审计，逐标的运行 `validate_price_frame`；全零或空子窗口显式保留拒绝证据，不当作活动有效窗口。[全局回执](catalog-receipt.json)、`requests/`、`receipts/`、`returned-scoped-15m/` 均保留，不直接读取旧 cache 或绕过受信任读取器扫描湖文件。

补证共 58 个标的日、39 个自然日、52 个标的，包括月末首/尾部分日与全部内部缺日。ADA 2020-01-31 的 64 根部分日被恢复；它是最终持仓中唯一实际用到部分月末端点的标的。形成期依旧允许原规则的 `>=48` 根端点、`>=80%` 覆盖和完整 30 个日桶 ADV，不偷偷改为新日线的 96 根门槛或连续 30 个 observed-valid 日。

## 下游必须保留的限制

1. 日线 `ts` 是开盘时间，日末估值时间应为 `ts+1d`。原规则日桶文件保留至 2026-07-01 open；账户在 2026-07-01 00:15 结束，绝不能使用随后完整一天的 close。持有期间更早的终止事件也必须先处理，不用终止后的日线占位价估值。
2. 部分日桶最后观测价可能不是 23:45 bar 的 close，参见 `actual_2345_close_present` 和 `last_15m_ts`；不能把部分日直接称为完整日或正式现金结算价。
3. 入场活动检查与参考开盘价不证明实际订单能成交；原观察池不等于历史身份/PIT 已验证。
4. 与旧冻结名单有 7 个月不同：4 个月来自已终止合约的确定性补位；2022-03/04/05 另有输入版本造成的名单差异，详见 QA。不能把两条不同输入/名单路径的最终差异全部归因于资金费或会计修正。
5. 本目录不认证资金费结算事件/标记价格，不提供精确终止现金金额，也不宣称净值有效。

## 保留

目录约 29 MiB；`daily-original-buckets.parquet` 为 18,731,988 字节，属于 B-review 可再生本地中间数据。保留理由是让独立会计代码消费同一治理输入和显式部分日补证，不重复复制完整 15m 历史。完整 Parquet 不应进入普通 Git，不自动删除既有证据。生成器为 [build_mcsm_baseline_inputs_20260909.py](../../../scripts/build_mcsm_baseline_inputs_20260909.py)，冻结源码指纹记录在输入计划与摘要；在本目录不存在的干净复现环境执行，已有目录会拒绝覆盖。
