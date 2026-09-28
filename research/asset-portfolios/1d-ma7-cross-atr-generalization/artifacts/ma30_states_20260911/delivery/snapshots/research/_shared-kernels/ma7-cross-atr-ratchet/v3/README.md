# MA7退出状态内核v3

这是实现版本，不是策略V3的新定义，也不是正式V4。默认精确保留v2行为；新defense/trend/extension配置对应消费方退出状态机规格。

新增闭合完整持仓日的失败/回撤防守、健康暂停、固定ATR观察段的延伸/衰竭保护。所有stop单向、倍数不增加、同日最多减一次；fixed_episode保留给定入场数量和本金，第一笔退出即结束，用于同一笔入场的退出对照。

[规则](../../../asset-portfolios/1d-ma7-cross-atr-generalization/specs/contract-exit-state-machine-20260910.md) · [用户成本变更](../../../asset-portfolios/1d-ma7-cross-atr-generalization/specs/exit-state-cost-amendment-20260910.md) · [93项合成检查](../../../../tests/test_ma7_car_exit_state_machine.py)。manifest固定本次源码和检查哈希，消费后不原地修改。
