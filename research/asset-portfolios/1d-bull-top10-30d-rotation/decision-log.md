# 决策记录

- 2026-09-07：按用户要求建立独立的牛市Top10、持有30日研究；只保留无牛市过滤的Top10对照，不增加择时指标。证据：[冻结规则](specs/p0-contract.md)。

- 2026-09-07：P0的完整30日轮次支持继续验证简化规则，但BNX终止/结算价值未核验导致两条完整账户路径失败；Binance USDT永续诊断均扣每边0.1%手续费与4/8bps滑点、未扣funding。保留轮次发现，不发布全窗净绩效，不改变规则或删除异常轮次；证据：[报告](diagnostics/p0-results-2026-09-07.md)、[路径状态](artifacts/p0-20260907/summary.json)、[BNX来源复核](artifacts/p0-20260907/bnx-terminal-source-review.json)。
