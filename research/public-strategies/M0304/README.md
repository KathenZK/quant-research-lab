# M0304 · Strategy002 · 原生5m

**最新状态（2026-10-03）：已完成4个预注册配置+1个同窗对照，独立实际账本审核及clean恢复通过。HYPOTHESIS / DIAGNOSTIC_ONLY，严格复现0，不晋升。**

基准配置2024年净收益 **−2.1551%**，全5m收盘MDD **12.8746%**，日Sharpe **−0.1627**；同窗95%资金buyhold **+115.0304%**。24轮中23赢1亏仍净亏，不能凭高胜率选优。其余fee0、fee20、delay2均为负收益，无结果后再搜索。

- [最新完整报告](diagnostics/execution-v1-report.md) · [当前主账](m0304-core-ledger.md) · [时间线](decision-log.md)
- [执行C0协议](specs/execution-v1/protocol.json) · [独立C0放行](specs/execution-v1/run-gate.json)
- [当前catalog记录](artifacts/catalog-record.json) · [精确结果](artifacts/execution-v1/summary.json) · [独立171fills/527040marks审核](artifacts/execution-v1/independent-historical-ledger-audit.json) · [clean恢复](artifacts/execution-v1/clean-recovery.json)
- [可运行恢复命令](diagnostics/execution-v1-recovery.md) · [输出指纹](artifacts/execution-v1/result-manifest.json)
- [原始策略/参考运行时来源](specs/source-manifest.json) · [全部原类属性](specs/source-ast-attributes.json)

初次403阻塞和预审包作为历史保留：[12:25预审说明](diagnostics/source-and-blocker-report.md)、[原入口字节](diagnostics/history/preparation-v2/README.md)、[原manifest](diagnostics/history/preparation-v2/publication-manifest-preparation-v2.json)。后来获授权同源单次恢复成功，不改写原失败事实。[恢复成功回执](artifacts/execution-v1/data-recovery-safe-v2.json)

固定输入114336根5m、2024评估105408根。窗口按可用性预选、非OOS，不与旧两年总收益直接比较。exit_profit_only=true及trailing_stop=false均保留；原作者runtime未知，替代限价/路径模型不冒充原框架严格复现。公开无原始行情、长曲线、完整事件或私有Graph。
