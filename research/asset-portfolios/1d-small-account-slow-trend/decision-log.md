# 决策日志

| 日期 | 决策 | 证据 |
| --- | --- | --- |
| 2026-09-08 | 新建独立 7ETF 小账户慢趋势家族；12M 主规则、12 个预定变体和经济增量评价在读取账户收益前冻结 | [契约](specs/p0-contract.json)、[曝光记录](specs/exposure-log.md) |
| 2026-09-08 | PDBC 33 个早期零成交日使原始 2016 年账户窗口 DATA_STARTUP_FAILED。结果尚未生成时冻结共同有效段与14M预热后2017-03起窗口，保留原契约不覆盖 | [补充](specs/data-admissibility.json)、[原生输入清单](artifacts/raw-manifest.json) |
| 2026-09-08 | 完成12变体账户和同口径对照；12M趋势相对同风险静态牺牲2.41pp CAGR，超过事前1pp上限，经济增量NO-GO。未将10M或静态对照事后升格 | [研究报告](diagnostics/p0-account-study-2026-09-08.md)、[汇总](artifacts/summary.json) |
| 2026-09-08 | 独立检查银行非结算日与买单实际结算字段；12变体历史权益不变。补全满仓SPY数学机会成本参考，明确非可执行账户 | [实现核查记录](specs/implementation-audit-note.json)、[SPY参考](artifacts/spy-fully-invested-reference.json) |
| 2026-09-08 | 保留全对象与可复现入口；不登记、不晋级、不启动未来运行。后续优先项限定为静态小账户执行核验，必须另固定新对象 | [主账](xa-1d-sast-core-ledger.md)、[复现说明](scripts/README.md) |
