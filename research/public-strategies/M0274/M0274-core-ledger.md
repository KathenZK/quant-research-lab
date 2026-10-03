# M0274 GodStra 主账

## 版本身份

- original_id / family_id：M0274；本轮版本M0274-GODSTRA-BTCUSDT-12H-20261003-BLOCKED-v1
- 原提交f3340ce11f5bdf62f598522e64d1f5638eaa13f5，SHA256 48e405f6d073944da9b993dfbce03aa980d0eea8a5da3c4a6b60f2f1b7264b86
- scope：公开catalog单条策略诊断；固定BTCUSDT现货12h，不是原作者全池复现
- 当前状态：BLOCKED / HYPOTHESIS / DIAGNOSTIC_ONLY；strict_reproductions=0；actual_strategy_backtests=0

## 冻结与结论

[规则](specs/source-rules-v1.json)保留买入阈值0.06295、卖出np.isclose阈值0.8779、ROI分钟阶梯、-34.549%止损、追踪全部参数及AgeFilter30。没有参数优化。

[收益前计划](specs/pre-performance-plan-v1.json) SHA256 4b296cdb7bbbcaa8abaf0e77fd76e0f8bcd5d707f95cf992786ce6e3832c36c2；[阻塞诊断冻结](specs/blocked-diagnostic-freeze-v1.json) SHA256 4806681ebf2bd5cc9b11111a7ca4d578810b02f24d9a78a75b421c6dcc43388f。

完整输入要求25月1524行，仅14月854行已取得，访问拒绝后停止。完整输入未绑定，不能标正式C1输入就绪。原完整特征变换因果反例可复现，未默修；真实行情评价信号有无受影响未知。

## 证据及当前门槛

- [行质量/覆盖](artifacts/partial-input-independent-qa-v1.json)：14月PASS，完整窗口INCOMPLETE_BLOCKED
- [因果反例](artifacts/synthetic-causality-v1.json)：11列前缀不稳定；合成输入，非行情收益
- [结果状态](artifacts/results-status-v1.json)：所有绩效为null，未计算
- [离线恢复](artifacts/offline-recovery-v1.json)：换目录复现静态、合成及partial校验；完整网络恢复NOT_RUN
- [独立审核摘要](artifacts/independent-partial-review-v1.json)

promotion/live-ready：拒绝。C3远端读回与私有备份由协调者后续完成；本worker没有执行或宣称完成。

原始14月留在独立work数据快照，不在公开包；完整源码全文也不分发。公开边界以publication-manifest.json为准。
