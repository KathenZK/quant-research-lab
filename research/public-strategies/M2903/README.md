---
research_classification: strategy_family
---
# M2903 比特币日线 EMA20 交叉

状态：registered / not promoted / not live-ready；收益前实现与合成验证，历史运行0，新控制0。共享输入适配层已独审pin，C0-v1已冻结，等待本家族exact-C0独审与root单独放行；不授权读取历史特征。

[策略说明](M2903.md) · [主账](M2903-core-ledger.md) · [冻结原规则](specs/root-frozen-rules.json) · [实现规格](specs/protocol-v1.json) · [决策](decision-log.md)。

HYPOTHESIS_FROM_CATALOG_NOT_SOURCE_VERIFIED / ADAPTED_EXECUTION_PROXY；严格复现0，窗口已曝光非OOS，PIT未知。完整行情、原记录与账户日志仅私有保存。

共享input/view已合并远端43becf3c，独审receipt与代码hash精确pin；实际wrapper合成/映射/输入拒绝及freshprocess通过。下一步正式C0和独审后仍需root单独放行；无历史运行。
