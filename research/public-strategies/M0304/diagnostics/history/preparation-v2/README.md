# M0304 · Strategy002 · 原生 5m 源码与预审准备

**截至 2026-10-03 12:25 UTC：BLOCKED_SOURCE_INPUT。真实策略配置运行 0，对照运行 0，严格复现 0。**

原始数据恢复的首个官方 CHECKSUM 请求遇到 tunnel 403。没有完整源对象、规范 CSV、实际本地原始 QA 或独立 raw rebuild 成功；114336 行、105408 评估 bar、39 个对象均仅为期望契约。当前准备包不能当作回测结果或完整收益恢复包。后续同源有限重试由整合方按用户新授权另行执行，本条目不自动重试。

- [独立条目报告](diagnostics/source-and-blocker-report.md)
- [家族主账](m0304-core-ledger.md) · [decision log](decision-log.md)
- [完整原类属性](specs/source-ast-attributes.json) · [源指纹与参考运行时边界](specs/source-manifest.json)
- [事前假设方案](specs/pre-run-plan.json) · [实际依赖环境](specs/environment.json)
- [合成公式测试](artifacts/synthetic-formula-validation.json) · [本轮失败事实](artifacts/data-recovery-blocker-safe.json)
- [准备包与未来原始输入恢复说明](diagnostics/recovery.md)

原固定源码：freqtrade/freqtrade-strategies @ f3340ce11f5bdf62f598522e64d1f5638eaa13f5 的 Strategy002.py，4363 bytes，SHA256 d1ca86a4ceb68ef828b35490ce1112330dad209cc3bb1e1b6c303c21ab3d8a90。指标公式移植保持 5m、exit_profit_only=true、trailing_stop=false。仅在明确的人工执行假设下可评估，保真度上限 HYPOTHESIS，数据/研究状态 DIAGNOSTIC_ONLY，不晋升、不接实盘。
