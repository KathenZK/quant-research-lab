# v8：V3生效参数显式化

冻结日期2026-09-24。引擎SHA256：`6b153c4e8362252813083645695360643383ef1918ecae083bb90e4a9b917ff0`。父v7保持不变，默认特征与账户旧字段逐值等价。消费者用自然就绪mask覆盖历史默认额外预热，实验参数传入features与simulate保持一致。

暴露MA/ATR/RSI周期、初始ATR倍数、下限、每日步长、RSI门槛、加速幅度与前日跌幅比较；支持独立移除RSI/加速子条件/净浮盈条件，固定止损MA或ATR锚，以及空仓侧状态入场对照。所有实际止损仍只收窄。

消费方为HYPE-1D-MA7-CAR的[参数研究](../../../hype/1d-ma7-cross-atr-ratchet/diagnostics/v3-parameter-stability-results-20260924.md)，[独立pin](../../../hype/1d-ma7-cross-atr-ratchet/specs/v3-parameter-engine-pin-20260924.json)。23项检查及121账户独立核验通过。代码v8不代表策略V8或晋升。

引擎已被SHA引用，禁止原地修改；后续修正须另建版本。
