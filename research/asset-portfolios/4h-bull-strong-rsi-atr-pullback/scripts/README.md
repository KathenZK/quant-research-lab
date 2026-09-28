# 复现脚本

当前家族一次性研究脚本，不是active package code。

- [build_p0_features.py](build_p0_features.py)：必须调用组合启动API并直接消费返回帧，按有效段生成特征；拒绝覆盖既有输出目录。
- [replay_p0.py](replay_p0.py)：验证同家族特征/契约哈希，逐币回放固定11组规则；不读取其他家族或数据湖。
- [package_p0_results.py](package_p0_results.py)：验证回放清单，独立验算原价毛收益/双边成本和时序，生成中文报告。
- [build_p1_inputs.py](build_p1_inputs.py)：调用独立日线/4h组合启动，生成有明确可用时点的市场与排名特征，验证P0未改动。
- [research_p1_states.py](research_p1_states.py)：验证输入哈希，生成未来3/7/14日标签、市场分层和同日选币配对，保留完整分母与区间。
- [replay_p1_entries.py](replay_p1_entries.py)：在统一止损、资金与执行顺序下比较四种入场，分别运行4/8bps滑点压力。
- [package_p1_results.py](package_p1_results.py)：独立核对真实标签和逐笔预算恒等式，保存事后退出归因并生成中文报告与交付清单。

先读相应[P0契约](../specs/p0-contract.md)、[P0复现说明](../diagnostics/p0-results-2026-09-07.md#复现与验证)或[P1契约](../specs/p1-contract.md)、[P1报告](../diagnostics/p1-market-strength-entry-2026-09-07.md#复现入口)。不得把price_diagnostic改名成净收益。产物中的源码快照以.txt保存作为执行证据，不是新增active消费者。
