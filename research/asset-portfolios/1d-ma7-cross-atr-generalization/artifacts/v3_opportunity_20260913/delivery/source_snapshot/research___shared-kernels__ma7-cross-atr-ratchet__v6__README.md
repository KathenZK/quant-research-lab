# V3 机会与损耗实验，共享代码 v6

本版本在冻结 v5 上新增两个互斥实验，默认关闭时保留全部旧交易、止损、权益和事件字段的精确结果；summary 仅多出默认配置 entry_wait_policy=bounded。代码 v6 不是正式策略 V6，也不改写 V1/V2/V3。

- `entry_wait_policy=until_invalid`：仅原空仓、就绪、斜率未达标的新穿越建立候选；不按日数到期，回到或触及 MA7、出现新穿越或未就绪则取消；首次斜率严格达标且越过原穿越日收盘，使用确认日指标次日开仓。候选在尝试成交前消费，止损或开盘无效也不重试。
- `short_exit=accel1_rsi30_protect`：原空单加速、RSI6≤30、扣费估算收益为正的条件首次出现时，以该完整日最低价加该日固定 ATR14 建立保护；后续只更新完整日累计最低价，次日生效。旧止损、原 V3 正常更新和保护线取最低；四日停滞后每日减少 0.2、下限 0.5 的原规则继续工作。
- 两实验强制原 V3 执行控制且不得叠加，不加 MA30、反手、额外方向或仓位筛选。消费者固定 fee=.001、slip=.0004。

## 审核字段

E_STATE 保留 `entry_events` 原字段并新增 `CANDIDATE_EVENT_COLUMNS`：原穿越收盘、候选年龄、正确侧、斜率、越过原收盘条件。`stage=candidate` 下记录 created/conditions_pending/confirmed/ma_side_invalid/fresh_cross_supersedes/not_ready/sample_end_unresolved。建议保存 DataFrame(events)，不要用旧列清单丢掉新证据。

TP_PROTECT 的交易和止损含 `tp_protect_active/signal_day/event_atr/extreme_low/candidate/trigger_rsi/trigger_close/eligible_signal_count/suppressed_count`。止损另含 `triggered_this_day/eligible_signal/actually_suppressed`（均带 tp_protect_ 前缀）。eligible_signal_count 是完整日满足旧 TP 条件的次数；suppressed_count 只统计开盘止损优先检查后确实到达并被替代的旧 TP 调用。若新保护线在开盘已触发，记录触发证据但实际抑制调用计零。保护并不保证盈利。

固定同入场退出对照沿用 `simulate(..., fixed_episode={entry_time, entry_equity, qty, side}, start=entry_time, end=segment_end)`，首笔退出后停止。已知资金费在边界先计入旧 TP 资格；funding=None 仍是价格诊断，不能声称资金费为零。

## 验证

`tests/test_ma7_car_v3_opportunity.py`：44 项合成测试通过。包括 v5 精确等价、双向候选与失效、严格阈值、不按日数到期、消费后不重试、持仓中信号不缓存、完整日生效、跳空/小时顺序、固定 ATR 与单向止损、原四日收紧继续、边界资金费、可能亏损、固定同入场与未来前缀因果。本版本未用真实市场结果来选参数。

消费契约：`research/asset-portfolios/1d-ma7-cross-atr-generalization/specs/contract-v3-opportunity-20260913.md`。
