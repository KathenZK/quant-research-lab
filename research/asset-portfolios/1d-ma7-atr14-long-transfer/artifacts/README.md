# 留存产物

20260907 为本次固定参数迁移诊断：

- [指标摘要](20260907/summary.json)、[CSV](20260907/summary.csv)
- [近期切片](20260907/recent-slices.csv)
- [启动校验报告](20260907/startup-report.json)、[实际窗口](20260907/resolved-windows.json)
- [回放校验](20260907/validation.json)、[图表校验](20260907/visual-validation.json)、[浏览器校验](20260907/browser-validation.json)
- [完整图表数据](20260907/chart-data.json)、[七币交易路径 HTML](20260907/七币交易路径.html)
- `inputs/` 保存本次已通过启动门禁的数据切片及有效掩码；是可审计回放证据，不是其他家族的行情事实源。
- `results/<window>/<coin>/<mode>/` 保存逐笔交易、日权益和回测 JSON。
- `hyperliquid-reference/` 仅保存前一次独立市场的合同、摘要与校验结果；未参与本次 Binance 回放。

产物由本主题脚本生成，正文解释见[诊断报告](../diagnostics/report-20260907.md)。


## full-market-20260908

- [主报告](../diagnostics/full-market-report-20260908.md)、[交互研究面板](full-market-20260908/全市场研究面板.html)
- [覆盖账本](full-market-20260908/coverage-ledger.csv)、[主窗口每币结果](full-market-20260908/main-symbol-results.csv)、[全部时间窗口与连续段](full-market-20260908/all-window-results.csv)
- [全部分析](full-market-20260908/analysis.json)、[入场条件对照](full-market-20260908/entry-feature-contrasts.csv)、[盈利来源分解](full-market-20260908/mechanism-decomposition.json)
- [主段交易](full-market-20260908/main-window-trades.csv.gz)、[全历史交易](full-market-20260908/full-history-trades.csv.gz)、[近期切片](full-market-20260908/recent-slices.csv)
- [回放检查](full-market-20260908/replay-validation.json)、[输入与结果保留指纹](full-market-20260908/run-output-manifest.json)
- `verified-inputs/` 为本研究已通过启动接口的回放证据，不是供其他家族复用的行情湖；`startup-requests/`、`startup-reports/` 保留每批精确合同与校验报告。
- `main-replays/` 保存每币主段的价格与三种成本回放；HTML 仅展示基础成本净值和交易概况，不宣称重新实现逐笔日内成交。

旧 20260907 七币产物保持不变。全市场报告已披露窗口长度、历史中断、异常提示、身份分类与资金费率边界；不以全市场平均数冒充可执行组合。
