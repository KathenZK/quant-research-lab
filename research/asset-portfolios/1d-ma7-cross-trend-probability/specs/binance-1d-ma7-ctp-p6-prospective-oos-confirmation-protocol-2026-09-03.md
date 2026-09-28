# BIN-1D-MA7-CTP P6 Prospective OOS Confirmation Protocol

- 状态：`prospective / frozen-after-historical-audit / not active`
- 触发条件：只有 P6 历史审计达到同日同方向 Top5 相对基准 +5pp、事件标签净收益增量为正、集中度可接受、且用户明确授权时，才消耗新 OOS。
- 当前结论：`PENDING_FRESH_OOS`；本轮没有读取合格未揭示标签窗口。

未来若执行：

1. 使用数据湖 canonical `binance.perp.ohlcv.1d.from_15m.v1` 与必要 `1h/15m` 路径，先完成第 16 节查询、选版本、验证、读取、固定输入。
2. 在读取新标签前冻结唯一待确认对象、适用六格/方向、B0/M1 分数来源、阈值、同日 Top5 指标、paired bootstrap、最小日期块和样本量。
3. 先完成 P0R/P5 重叠窗口迁移对账：事件键、OHLCV、B0 69 字段、ATR、小时 first-hit、funding、B0 预测。
4. 禁止看新结果边跑边改规则，禁止反复查看显著性后择时停止。

本协议不是定时任务，不授权 runner，不登记策略版本。
