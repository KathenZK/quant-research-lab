# MA120本轮材料

仅执行用户指定的Top10加MA120入场/退出，不搜索参数，不叠加原弱币退出或20%止损。

- [规格](../../specs/binance-1d-mcsm-ma120-round-20260911.md)
- [本轮报告](../../diagnostics/binance-1d-mcsm-ma120-round-20260911.md)
- [全部月度持仓与盈亏](monthly-holdings-and-pnl.md)
- [年度汇总](yearly-results.md)
- [8条账户摘要](summary.json)
- [独立信号与现金核查](independent-audit.json)
- [月初买入判断](entry-decisions.parquet) / [每日退出判断](signal-days.parquet) / [退出计划](exit-plan.parquet)
- [已实际返回的成交参考价](execution-prices.parquet) / [请求及目标预先保存](plan.json)

每条账户目录保存净值、交易、资金费、逐月与年度记录；legs文件记录全部760个候选及未买入原因、实际数量、价格与资金盈亏。

输入复用原哈希绑定的返回帧；新增只保留16批请求需要的价格切片，没有复制日线或完整资金费。最多50MiB，本地证据不加入普通Git。可按规格复制到外置对象存储并验证恢复后再决定迁移；本次不删除或迁移旧文件。

生成：在项目根目录，以src和本家族scripts为模块路径，运行research_mcsm_ma120_20260911.py prepare、execute，随后audit_mcsm_ma120_20260911.py和report_mcsm_ma120_20260911.py。已存在的冻结结果不能覆盖；复现应指定独立工作副本。
