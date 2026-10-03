# M0298 Simple：当前已回测，HYPOTHESIS / DIAGNOSTIC_ONLY

当前版本已完成2024年BTCUSDT现货原生5m固定4配置+1同窗对照，独立全账本/指标审计和独立重建输入的干净恢复通过。base总收益+31.51%、全5m MDD−39.68%；同窗95%买入持有+115.03%/−32.02%。严格复现0、OOS声明false，不晋升、不部署。

- [完整中文结果](diagnostics/M0298-native5m-results-20261003.md)
- [主账](m0298-core-ledger.md) · [决策记录](decision-log.md)
- [执行协议](specs/execution-plan-v1.json) · [收益前C0](specs/C0-20261003-v1.json)
- [实际账本审计](artifacts/execution-v1/M0298-historical-ledger-audit-v1.json) · [冻结恢复](artifacts/execution-v1/recovery-receipt.json)
- [可运行恢复命令](RECOVERY-execution-v1.md) · [Graph公开记录](artifacts/graph-record.json)
- [当前公开manifest](publication-manifest.json)

时间线：首个恢复请求Tunnel403 → 用户授权等待后同源有限重试 → 完整39对象/114336行QA及独立字节重建通过 → 收益前C0/独立审核 → 固定4+1 → 全账本审计与干净恢复。完整[旧21文件阻塞准备包](history/preparation-v0/README.md)按原字节保留；旧状态是当时事实，不是当前结果。

公共包不包含原始行情、完整第三方源码、长曲线、私人备份标识或私人Graph detail。5个日度权益投影各366点只供展示，MDD来自全105408根5m收盘净值加初始现金。
