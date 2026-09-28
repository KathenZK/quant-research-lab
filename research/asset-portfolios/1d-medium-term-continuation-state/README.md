# Binance-1D-Medium-Term-Continuation-State

别名：`BIN-1D-MTCS`。Binance 加密日线的事前方向／状态识别、中期延续与收益捕获研究。

研究单位是标的×时点×方向。独立于 MA7-BTG、TPSA、CTP；不继承它们的输入缓存、模型、参数优化结果或成功失败裁决。

状态：`explore / diagnostic-only / not promoted / not live-ready`。用户于2026-09-08授权的本轮有限研究已完成：10个固定单元无达标历史候选，M_LONG未达到冻结最低识别增量，其他9个证据不足。未注册交易版本或上线，没有新时间确认。

先读[研究结论与后续边界](diagnostics/research-report-20260908.md)。MA7混合了已有方向推进、方向转换和回撤后重启；部分状态的有利均值主要出现在第5—20日，但不足以证成可稳定使用的事前识别器。该裁决不等于全部中期趋势假设失败。

- [主账](binance-1d-mtcs-core-ledger.md)
- [冻结研究合同](specs/research-contract.md)
- [用户目标与授权](specs/user-objective.md)
- [原审阅方案](../1d-ma7-bidirectional-trend-generalization/notes/research-proposal-medium-term-continuation-20260908.md)
- [决策记录](decision-log.md)
- [执行与复现说明](scripts/README.md)
- [产物索引](artifacts/README.md)
- [统计计算精度修复](specs/statistics-exact-computation-repair.md)
- [独立资金账审计](diagnostics/p2-independent-audit.md)
- [数据与资金费范围](diagnostics/data-scope-and-funding.md)
- [验证与交付](diagnostics/validation-and-delivery.md)
