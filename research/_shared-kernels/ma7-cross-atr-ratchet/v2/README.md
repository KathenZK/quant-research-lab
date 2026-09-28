# MA7 / ATR内核v2：四项机制对照

新增方向入场限制、MA30入场过滤、按初始止损风险确定数量，以及刷新有利日高/低后取消收紧启动。新字段的默认值关闭这些变化；合成数据中原v1的指标列、summary原字段以及trades/equity/stops/funding原列均逐值精确一致。原v1及历史市场结果未改写、未重跑。

消费方为[BIN-1D-MA7-CAR-GEN](../../../asset-portfolios/1d-ma7-cross-atr-generalization/README.md)，具体研究定义见[四项验证规格](../../../asset-portfolios/1d-ma7-cross-atr-generalization/specs/contract-four-tests-20260910.md)。这是共享实现的版本号，不是HYPE策略V2。

## 新配置

| 字段 | 默认值 | 可选值与作用 |
| --- | --- | --- |
| direction_mode | both | long只开多、short只开空；不改真实cross、不影响已有仓位退出 |
| trend_filter | none | ma30_ready只限制MA30和前值可用；ma30_direction另要求价格与MA30变化方向同向，均严格比较 |
| risk_fraction | None | 0.005为每笔初始止损计划损失不超过开仓前权益0.5% |
| notional_fraction | 1 | 名义数量上限乘此值；本轮小仓位参照为1/30 |
| progress_policy | permanent | reset_on_new_extreme在严格新高/低时取消当前armed，重新等4日；已有倍数和实际止损均不放宽 |

MA30新增特征不改变原29日ready。MA30和前值需要31根完整日K；缺少时只拒绝入口，账户起止不裁短。

单位止损计划损失为`side*(entry_fill-stop_fill)+fee*(entry_fill+stop_fill)`，其中`stop_fill=initial_stop*(1-side*slip)`。数量上限按`E*notional_fraction/(entry_fill*(1+fee))`计算；风险模式再与`E*risk_fraction/unit_risk`取小值。压力滑点会重算单位风险和数量。未知未来资金费和额外持仓成本不算入初始预算；实际跳空或成本可能使损失超预算。非正初始止损只新增标记，未额外改变原样本或拒绝条件。

## 账本和入口事件

`simulate`保持原5份返回值，末尾新增可选`entry_events=list`参数。事件列由`ENTRY_EVENT_COLUMNS`公开；消费方可按该列定义保存空表。事件只在可处理的空仓穿越或实际尝试时记录；持仓占用的穿越、被止损/RSI退出消耗的当次信号不计作过滤失败。

首个失败原因顺序：日线ready、斜率、方向限制、MA30可用、MA30方向、初始止损有效、权益为正、风险单位损失有效。每次机会只保存一个终态；本轮状态为rejected或filled，旧等待功能另可能出现waiting。`flat_ready_crosses`表示ready的空仓穿越总数；`entry_attempts`只计斜率通过后进入开仓检查的次数，包含方向和MA30拒绝；`entry_fills`表示实际开仓。

trades增加MA30值、方向/过滤配置、初始止损预估成交价、单位计划损失、数量上限、计划损失金额和百分数（0.5即0.5%）及非正止损标记。stops增加progress_policy/armed_reset/first_arm_day/ever_armed/arm_count/reset_count。`arm_day`和`armed`描述当前状态，reset时清除；历史首次启动、启动次数、重置次数独立保留。到0.5倍数后仍记录新极值重置。summary旧字段不改含义，另加ever_armed_trades和入口计数。

## 验证与冻结

[86项合成测试](../../../../tests/test_ma7_car_four_tests.py)覆盖默认精确兼容、双向入场、MA30严格比较/额外预热/因果性、风险数量与费滑点、名义数量上限、跳空和持仓成本超预算、刷新后重新等待及下限、部分持仓日、短仓提前止盈开关和条件、退出优先级及入口拒绝计数。没有使用历史市场重跑作为这份兼容证据。

engine和测试SHA见[manifest.json](manifest.json)。一经消费方固定SHA引用，禁止原地修改；任何后续修正须另开版本。
