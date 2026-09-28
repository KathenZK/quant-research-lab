# 月频与周频比较材料

本分支固定比较 2020-04-01 00:15 至 2026-07-01 00:15 UTC。B0 为原月度名单在这个时间段重新从 100,000 USDT 开始；M28 为每月按过去 28 日选币；W28 为每周一按相同 28 日选币；W7 为每周一按过去 7 日选币。周策略保留首次周三建仓及最后不足一周的持仓。

这里只有扣每边 0.1% 手续费及 0.04% / 0.08% 滑点的价格对照，**不包含资金费，不是永续合约实盘净收益**。`funding_pnl_usdt` 留空意味着没有计算，不是费用为零。过去日历、完整当时身份、保证金/强平和盘口容量均未得到认证。

实际完成 4 条月频账户，4 条周频账户明确停止。4 / 8 bp 滑点下，B0 收益分别为 +1428.03% / +1352.47%，最大回撤 95.43% / 95.57%；M28 收益 +2210.85% / +2094.10%，最大回撤 96.51% / 96.62%。M28 更赚钱但回撤更大，不能据此推出周频更好或更差。

W28 在 2022-02-16 00:00 第一次无法给持仓估值：缺少 KEEP 的 2 月 15 日完整日线，并且没有冻结的合约终止价格材料。W7 在 2021-12-20 00:00 同样因 BZRX 的 12 月 19 日完整日线及终止价格材料缺失而停止。失败原因字符串使用的是**日线标签日期**，不是次日观察日期。未来端点还缺这两币原计划下周换仓时的四条 00:00 / 00:15 记录，见 `future-input-gaps.json`。没有跳周、删除持仓、转成新币或猜结算价，故**本轮尚未得到完整的周频收益比较**。

## 复现与阅读顺序

1. `nomination-freeze.json`、`ranked-candidates.parquet`、`qualification-plan.json`：先锁定只依赖过去完整日线的全部候选排名，以及入场前 00:00 已闭合活动检查请求。
2. `qualification/requests`、`qualification/reports`、`qualification/returned-targets`、`qualification/receipts`：64 批完整本地启动检查，只留前置资格投影。原月初返回资料还由 77 份原 receipt 及全局 catalog 哈希证明链引用，不复制原全历史数据。
3. `prior-activity-decisions.parquet`、`qualified-nomination-freeze.json`、`nominations.parquet`、`holding-windows.parquet`：按既定排名及前置活动选满十币，再锁定全部 8,040 条持仓窗口；绝不按未来退出是否有价重挑。
4. `execution-plan.json`、`execution-started.json`及本层 `requests/reports/returned-targets/receipts`：再读取 41 批未来参考端点。各账户的原/新、周/月净值使用同一批日末和月周交界时点。
5. 各 `B0/M28/W28/W7-{4,8}bp/summary.json` 记录账户结果或明确的最早失败原因。缺价或没有可用终止材料时，不补零、不跳过持仓、不发布拼接的全期收益。

## 明细字段

- `holding-windows.parquet`：原始冻结名单，含每次建仓、预定退出、已知终止事件调整后的退出、排名与事前成交额；`priced-holding-windows.parquet` 另附参考进出价及可用性，绝不改原名单。
- 账户目录中的 `monthly.csv`：每个自然月的期初/期末权益、盈亏金额/比例、价格损益、手续费、滑点、月初持币及月内实际持有过的所有币。边界为每月 1 日 00:00，首期初始及末期最终清仓采用实际 00:15；不是旧账户“调仓后到下次调仓后”的月份。
- `periods.csv`：每次选币到下一次选币的账户盈亏、起止换手、名单、持有天数及短周标记。该表按换仓后的账户边界记录，不应与自然月表混成一个周期。
- `trades.parquet`：全部实际净额调仓的旧/新数量、参考价、换手、手续费和滑点；同币保留的数量不会人为重复全卖全买。
- `leg-price-pnl.parquet`：本期调仓后实际数量乘期间价格差。它只拆价格损益，不把下一次调仓的新币费用硬分给旧十币；账户费用请看交易表和月度现金拆分。
- `funding-window-coverage.csv` / `funding-coverage-summary.json`：列观察到的资金事件、原月度估值能覆盖的事件、已知原生标记价事件和已发布日历包含的持仓窗口。仅为已保存资料覆盖盘点，不是完整原始文件重扫描或净收益通过。

`b0-original-adapter-recheck.json` 已将原 76 个月 B0 的 2,390 个净值时点、价格损益和全部交易成本一一复现，误差为零。本适配器没有 S1 单币退出事件，不声称自己复现了 S1；该复现由本轮扩大退出分支完成。

`implementation-failure-001/002/003.json` 保留计划阶段的类型实现错误、一次受控并发重启，以及新收益产生前发现的原生标记价覆盖字段识别修正；`implementation-guard-qa.json` 记录独立审阅后新增的完整日程和旧 receipt 哈希防护。这些不是改选币参数。资金覆盖按已复查来源标签识别原生价格，不能继续用旧表滞后的 `native_mark` 布尔字段统计。

`postrun-integrity.json` 复核 77 份原始 receipt、64 批过去资格投影、41 批未来目标、全部冻结名单及月年现金合计。运行入口为家族脚本目录中的 [audit_mcsm_weekly_postrun_20260911.py](../../../scripts/audit_mcsm_weekly_postrun_20260911.py)，只读取已有验证返回投影与研究输出，不启动新市场数据读取；原位置运行记录保留在 `postrun-integrity-superseded-001.json`。`../independent-audit/weekly-summary.json` 另有不调用本回放器的逐事件独立现金审计。`summary.json` 的 `common_grid_points=390` 指共同月/周 00:15 边界数量；完整账户另包含逐日 00:00 估值，每条成功账户共 2,672 个净值时点。

全部产物为可从固定输入重建的本地研究证据，预算 40 MiB；不重复复制原行情全文，不删除或迁移旧资料，不进入普通 Git 大文件。
