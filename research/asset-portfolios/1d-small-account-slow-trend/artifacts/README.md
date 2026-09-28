# 产物清单

- [summary.json](summary.json)：整合接口，身份、状态、裁决、有效覆盖、12变体结果、限制与主入口。
- [metrics.csv](metrics.csv)：全部变体同口径指标；[annual.csv](annual.csv)、[market-blocks.csv](market-blocks.csv)、[recent.csv](recent.csv)：年度、阶段、近期切片。
- [equity-drawdown.png](equity-drawdown.png)：主候选与三个整股账户对照的净值/回撤。
- [raw-manifest.json](raw-manifest.json)、[data-audit.json](data-audit.json)、[distribution-events.csv](distribution-events.csv)：原生快照指纹、日历/行核查与显式分配。
- [主候选净值/现金/持仓](trend_12m_risk10/account.csv)、[订单](trend_12m_risk10/orders.csv)、[决策](trend_12m_risk10/decisions.csv)、[现金事件](trend_12m_risk10/cash-events.csv)、[逐资产PnL](trend_12m_risk10/asset-pnl.csv)、[贡献汇总](trend_12m_risk10/asset-contribution.csv)。另11个变体目录均保留相同账本集合。
- [归因](attribution.json)、[事后等波动静态参考](expost-vol-matched-static-diagnostic.csv)：只作分解，不是可交易策略或预测alpha证明。
- [满仓SPY数学参考](spy-fully-invested-reference.json)、[对应净值](spy-fully-invested-reference.csv)：与整股SPY账户分开。
- [人工算术例子](manual-arithmetic-check.json)、[真实交易/发行人分配样本](real-trade-and-distribution-checks.json)、[导出账本核验](exported-ledger-arithmetic-audit.json)、[小账户份额核验](small-account-lot-check.csv)。
- [环境](environment.json)、[来源上下文指纹](prior-context-source-manifest.json)、[完整产物指纹](hashes.json)。
- [新目录离线复现证据](offline-reproduction-evidence.json)：复制本家族后用留存原生数据运行，一一比较账户/指标等输出内容，不访问原仓库或网络。

原生 `raw/*.json` 与 `bars-*.csv` 保留以支持复现；并非通用可信 normalized 发布物。不要把本目录里的日线代理搬入旧冻结数据或共享湖。图和结果全部属于复用历史诊断。
