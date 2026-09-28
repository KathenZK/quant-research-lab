# v7：可选双触发一步降到0.5ATR

2026-09-13冻结。默认关闭，保留v6的原经济字段；新增adverse_ma_floor_atr和stagnation_floor。完整持仓日收盘反向超阈值，或高低价连续4日不刷新时，止损倍数次日可直接降到0.5，实际价格仍只收窄。两者同日触发只执行一次。

当前消费方仅HYPE-1D-MA7-CAR的HYPE双触发实验，未运行全市场。16项边界与默认兼容检查、四账户81笔独立核验通过。代码v7不是策略V7，也不是正式V4。

引擎SHA256：`9faaa9737ebf783079ec6d4981d7baa889cfbaad227daf9807979dfb83efb0bf`。

[消费方规格](../../../hype/1d-ma7-cross-atr-ratchet/specs/v3-immediate-floor-20260913.md) · [消费方pin](../../../hype/1d-ma7-cross-atr-ratchet/specs/v3-immediate-floor-engine-pin-20260913.json) · [结果](../../../hype/1d-ma7-cross-atr-ratchet/diagnostics/v3-immediate-floor-results-20260913.md)。v1至v6保留，禁止原地修改冻结引擎。
