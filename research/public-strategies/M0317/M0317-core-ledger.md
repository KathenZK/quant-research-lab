# M0317 研究主账

| 字段 | 冻结内容 |
|---|---|
| 稳定ID及家族 | M0317 / PUBLIC-M0317-MABSTRA |
| 版本 | M0317-BTCUSDT-4H-MABSTRA-DEFAULT-20261003 |
| 运行 | M0317-20261003-first-replay |
| 状态 | 完成固定默认参数诊断及本地恢复，远端保存待协调者 |
| 保真上限 | HYPOTHESIS |
| 数据状态 | DIAGNOSTIC_ONLY / trusted=false |
| 严格复现数 | 0 |
| 源码 | mabStra.py，f3340ce11f5bdf62f598522e64d1f5638eaa13f5，4044B |
| 源SHA256 | 1c483a549398a0244ca6d87f9736a76ed462056aca8a5ee9affd9aa65efd9393 |
| 协议SHA256 | eb78a360cd1de6c68a3ef465e92d3af541615f03e3b59b7e2df21eb2cee246ae |
| 真实收益运行 | 2026-10-03 11:01:00至11:01:03 UTC，exit0 |
| 评价窗口 | 2023-01-01至2025-01-01不含，4386根4h / 731日 |
| 参数与成本 | 原default不修正，4固定执行/费率情景和1买持；零参数搜索 |
| 主情景 | 净收益304.9944%，收盘最大回撤32.7071%，日Sharpe1.7871 |
| 同仓位买持 | 净收益441.8735%，收盘最大回撤29.6538%，日Sharpe2.0056 |
| 关键诊断 | 买入4386/4386、卖出0/4386；100完成回合，89ROI和11止损退出 |
| 决策 | 不晋升，不修阈值，不恢复优化表现，不绑定/部署Graph |

证据：[报告](diagnostics/M0317-default-replay-report.md)、[协议](specs/protocol.json)、[C2](artifacts/C2-validation-receipt.json)、[本地恢复](artifacts/local-recovery.json)、[结果](artifacts/results/summary.json)。
