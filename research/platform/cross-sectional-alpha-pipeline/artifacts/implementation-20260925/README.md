# 2026-09-25 落地与恢复证据

这是长期研究证据，不是临时缓存。完整结论在[自包含报告](../../diagnostics/implementation-results-20260925.md)，本轮不修改任何旧策略版本和生产状态。

| 文件 | 保留原因 |
|---|---|
| [acceptance.json](acceptance.json) / [测试记录](acceptance-tests.txt) / [测试明细](acceptance-tests.xml) | 定向测试、局部门禁、冻结源一致性和备份验收 |
| [因子审计](factor-boundary-audit.json) / [旧源码](source-before/cross_sectional.py) | 实际跨币错误、版本变化和影响范围 |
| [合成组合账户](synthetic-joint-account.json) | 分数、预算、净仓位、部分成交、资金费和恢复连通；不是行情绩效 |
| [数据摘要](data-capabilities/summary.json) / [代码能力表](data-capabilities/observed-code-capabilities.csv) / [精确窗口凭据](data-capabilities/price-startup-receipt.json) | 874代码覆盖与预先固定三币范围的真实检查结果 |
| [曝光登记摘要](exposure-bootstrap-summary.json) | 120条、56家族；全部历史累计搜索数未知 |
| [最终候选包清单](candidate-bundle-r3/manifest.json) / [备份凭据](backup-receipt-r3.json) | 21个实际冻结文件及项目外副本位置和SHA |
| [项目外恢复结果](candidate-restore-result.json) / [离线恢复结果](offline-restore-result.json) / [依赖安装包清单](dependency-wheels-manifest.json) | 干净环境和关闭联网安装重放；17列指标、18笔交易、逐笔独立核账 |
| [开发修正](restore-development-corrections.json) | 保留r1/r2恢复脚本失败，r3为合格包；源策略和结果未变 |
| [全仓治理](repository-governance.json) | 73项其他路径问题单独记录，不冒充全仓通过 |

完整二进制默认保留在本地忽略路径；本轮未提交Git、未清理历史文件、未上传外部存储。候选包约1.6MB；项目外依赖安装包共约51.1MB。重复恢复开发包只保留本轮r1/r2/r3，不按无限试跑复制。SHA与关键摘要进入文档便于核验，实际恢复仍需要完整包及相容Python环境。
